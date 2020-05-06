# Core operations for downloading, searching on OpenGameArt.org
import asyncio
import json
import pathlib
import urllib.parse
from configparser import ConfigParser
from typing import AsyncGenerator, Dict, Generator, List, Optional

import aiohttp

from ._helpers import synchronize_generator
from .parsing import (
    Translations,
    parse_asset,
    parse_last_search_page,
    parse_search_results,
)
from .primitives import Asset, AssetFile, AssetType, LicenseType


__all__ = ["Config", "Session", "SynchronizedSession"]

DEFAULT_CONFIG_LOCATION = "~/.oga/config"
CONFIG_SECTION_NAME = "oga"


class Config:
    url: str
    max_conns: int
    root_dir: str

    def __init__(self, *, url: str, max_conns: int, root_dir: str) -> None:
        self.url = url
        self.max_conns = max_conns
        self.root_dir = root_dir

    @classmethod
    def default(cls):
        return Config(
            url="https://opengameart.org",
            max_conns=5,
            root_dir="~/.oga")

    @classmethod
    def from_file(cls, file_path: Optional[str] = None) -> Optional["Config"]:
        file_path = file_path or DEFAULT_CONFIG_LOCATION
        try:
            filename = pathlib.Path(file_path).expanduser().resolve()
        except FileNotFoundError:
            return None
        default = Config.default()
        parser = ConfigParser()
        parser.read(filename)
        try:
            section = parser[CONFIG_SECTION_NAME]
        except KeyError:
            return default
        return Config(
            url=section.get("url", fallback=default.url),
            max_conns=section.getint("max_conns", fallback=default.max_conns),
            root_dir=section.get("root_dir", fallback=default.root_dir))


async def search(session: aiohttp.ClientSession, base_query: str) -> AsyncGenerator[str, None]:
    page = 0

    async def fetch() -> bytes:
        url = f"{base_query}&page={page}"
        async with session.get(url) as response:
            return await response.read()

    # Special case for first page since we may not continue
    data = await fetch()
    last_page = parse_last_search_page(data)
    asset_ids = parse_search_results(data)
    for asset_id in asset_ids:
        yield asset_id

    while page < last_page:
        page += 1
        data = await fetch()
        asset_ids = parse_search_results(data)
        for asset_id in asset_ids:
            yield asset_id


class Session:
    """
    Provides asynchronous methods for querying and fetching
    (against a cache manifest) individual assets and collections.

    Usage::

        >>> session = Session()
        # easier blocking calls
        >>> run = session.loop.run_until_complete

        >>> asset = run(session.describe_asset("imminent-threat"))
        >>> run(session.download_asset(asset))
        # cache hit, returns immediately
        >>> run(session.download_asset(asset))

    """
    def __init__(self, config: Optional[Config] = None, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        if config is None:
            config = Config.default()
        if loop is None:
            loop = asyncio.new_event_loop()
        self.loop = loop
        self.config = config

        # Set up connection limiting according to config
        conn = aiohttp.TCPConnector(limit=config.max_conns, limit_per_host=config.max_conns, loop=loop)
        self._session = aiohttp.ClientSession(connector=conn, loop=loop)
        self._file_manager = LocalFileManager(config)

    async def close(self) -> None:
        await self._session.close()

    def search(
            self, *,
            keys: Optional[str] = None,
            title: Optional[str] = None,
            submitter: Optional[str] = None,
            sort_by: Optional[str] = None,
            descending: Optional[bool] = None,
            types: Optional[List[AssetType]] = None,
            licenses: Optional[List[LicenseType]] = None,
            tags: Optional[List[str]] = None,
            tag_operation: Optional[str] = None) -> AsyncGenerator[str, None]:
        """
        :param keys: appears to search the entire page (including comments, tags...)
        :param title: appears in the asset title
        :param submitter: part or all of the submitter's username.  Not always the author (eg. "submitted by")
        :param sort_by: "favorites", "created", "views"
        :param descending: True if sorting descending, False for ascending.
        :param types: allowed asset types.  Leave blank to allow all.
        :param licenses: allowed licenses.  Leave blank to allow all.
        :param tags: List of tags to match or avoid, depending on ``tag_operation``
        :param tag_operation: "or", "and", "not", "empty", "not empty"
        """
        # 0) Apply defaults
        keys = keys or ""
        title = title or ""
        submitter = submitter or ""
        sort_by = (sort_by or "favorites").lower()
        descending = True if descending is None else descending
        types = types or []
        licenses = licenses or []
        tags = tags or []
        tag_operation = (tag_operation or "or").lower()

        # 1) Validate enums
        def validate(param, param_name, allowed):
            if param not in allowed:
                raise ValueError(f"{param_name} must be one of {allowed} but was {param!r}")

        validate(sort_by, "sort_by", {"favorites", "created", "views"})
        validate(tag_operation, "tag_operation", {"or", "and", "not", "empty", "not empty"})

        # 2) transform params into request format
        sort_by = {
            "favorites": "count",
            "created": "created",
            "views": "totalcount",
        }[sort_by]
        sort_order = "DESC" if descending else "ASC"
        types = [Translations.asset_type_search_values[x] for x in types]
        licenses = [Translations.license_search_values[x] for x in licenses]
        url = f"{self.config.url}/art-search-advanced?"

        # 3) build values into url
        quote = urllib.parse.quote_plus
        base_query = "&".join([
            url,
            f"keys={quote(keys)}",
            f"title={quote(title)}",
            f"field_art_tags_tid_op={quote(tag_operation)}",
            f"field_art_tags_tid={quote(','.join(tags))}",
            f"name={quote(submitter)}",
            f"sort_by={sort_by}",
            f"sort_order={sort_order}",
            f"items_per_page=144"
        ])
        if types:
            type_query = "&".join([
                f"field_art_type_tid%5B%5D={type}"
                for type in types
            ])
            base_query += "&" + type_query
        if licenses:
            license_query = "&".join([
                f"field_art_licenses_tid%5B%5D={license}"
                for license in licenses
            ])
            base_query += "&" + license_query
        return search(self._session, base_query)

    async def describe_asset(self, asset_id: str) -> Asset:
        url = f"{self.config.url}/content/{asset_id}"
        async with self._session.get(url) as response:
            partial_asset = parse_asset(asset_id, await response.read())
        tasks = [
            self.describe_asset_file(asset_file_id)
            for asset_file_id in partial_asset["files"]]
        if tasks:
            tasks, _ = await asyncio.wait(
                tasks, loop=self.loop, return_when=asyncio.ALL_COMPLETED)
            partial_asset["files"] = [task.result() for task in tasks]
        return Asset(**partial_asset)

    async def describe_asset_file(self, asset_file_id: str) -> AssetFile:
        url = f"{self.config.url}/sites/default/files/{asset_file_id}"
        async with self._session.head(url) as response:
            headers = response.headers
        etag = headers["ETag"]  # type: str
        if etag.startswith("\"") and etag.endswith("\""):
            etag = etag[1:-1]
        return AssetFile(
            id=asset_file_id,
            etag=etag,
            size=int(headers["Content-Length"]))

    async def download_asset(self, asset: Asset) -> None:
        if not asset.files:
            return
        tasks = [
            self.download_asset_file(asset.id, asset_file)
            for asset_file in asset.files]
        await asyncio.wait(tasks, loop=self.loop, return_when=asyncio.ALL_COMPLETED)

    async def download_asset_file(self, asset_id: str, asset_file: AssetFile) -> None:
        current_etag = self._file_manager.get_etag(asset_id=asset_id, asset_file_id=asset_file.id)
        # cache hit
        if current_etag and current_etag == asset_file.etag:
            return

        url = f"{self.config.url}/sites/default/files/{asset_file.id}"
        async with self._session.get(url) as response:
            data = await response.read()
            self._file_manager.save(
                asset_id=asset_id,
                asset_file_id=asset_file.id,
                etag=asset_file.etag,
                data=data
            )


class LocalFileManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._cache = {}  # type: Dict[str, Dict[str, str]]

    def load(self, *, asset_id: str, asset_file_id: str) -> Optional[bytes]:
        asset_file_path = self._path_to_content_dir(asset_id) / asset_file_id
        try:
            return asset_file_path.read_bytes()
        except FileNotFoundError:
            return None

    def save(self, *, asset_id: str, asset_file_id: str, etag: str, data: bytes) -> None:
        asset_file_path = self._path_to_content_dir(asset_id) / asset_file_id
        asset_file_path.write_bytes(data)
        self._set_etag(asset_id=asset_id, asset_file_id=asset_file_id, etag=etag)

    def delete(self, *, asset_id: str, asset_file_id: str) -> None:
        asset_file_path = self._path_to_content_dir(asset_id) / asset_file_id
        asset_file_path.unlink()
        self._clear_etag(asset_id=asset_id, asset_file_id=asset_file_id)

    def get_etag(self, *, asset_id: str, asset_file_id: str) -> Optional[str]:
        """
        Also ensures asset file exists locally.
        File checksums aren't validated yet, because OGA doesn't publish them.
        """
        self._load_cache(asset_id=asset_id, force=False)
        last_etag = self._cache[asset_id].get(asset_file_id, None)
        asset_file_path = self._path_to_content_dir(asset_id) / asset_file_id
        if asset_file_path.exists():
            return last_etag
        # file doesn't exist but cache is stale
        if last_etag:
            self._clear_etag(asset_id=asset_id, asset_file_id=asset_file_id)
        return None

    def _set_etag(self, *, asset_id: str, asset_file_id: str, etag: str) -> None:
        self._load_cache(asset_id=asset_id, force=True)
        self._cache[asset_id][asset_file_id] = etag
        self._save_cache(asset_id=asset_id)

    def _clear_etag(self, *, asset_id: str, asset_file_id: str) -> None:
        self._load_cache(asset_id=asset_id, force=True)
        self._cache[asset_id][asset_file_id] = None
        self._save_cache(asset_id=asset_id)

    def _load_cache(self, *, asset_id: str, force: bool=False) -> None:
        if asset_id in self._cache and not force:
            return
        cache_file = self._path_to_cache(asset_id)
        try:
            data = json.loads(cache_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            cache_file.write_text("{}")
            data = {}
        self._cache[asset_id] = data

    def _save_cache(self, *, asset_id: str) -> None:
        self._load_cache(asset_id=asset_id, force=False)
        cache_file = self._path_to_cache(asset_id)
        cache_file.write_text(json.dumps(self._cache[asset_id], sort_keys=True, indent=4))

    def _path_to_cache(self, asset_id: str) -> pathlib.Path:
        path = (pathlib.Path(self.config.root_dir) / "cache" / asset_id).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _path_to_content_dir(self, asset_id: str) -> pathlib.Path:
        path = (pathlib.Path(self.config.root_dir) / "assets" / asset_id).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path


class SynchronizedSession:
    def __init__(self, session: Optional[Session] = None):
        if session is None:
            session = Session()
        self._session = session

    def search(
            self, *,
            keys: Optional[str] = None,
            title: Optional[str] = None,
            submitter: Optional[str] = None,
            sort_by: Optional[str] = None,
            descending: Optional[bool] = None,
            types: Optional[List[AssetType]] = None,
            licenses: Optional[List[LicenseType]] = None,
            tags: Optional[List[str]] = None,
            tag_operation: Optional[str] = None) -> Generator[str, None, None]:
        """
        :param keys: appears to search the entire page (including comments, tags...)
        :param title: appears in the asset title
        :param submitter: part or all of the submitter's username.  Not always the author (eg. "submitted by")
        :param sort_by: "favorites", "created", "views"
        :param descending: True if sorting descending, False for ascending.
        :param types: allowed asset types.  Leave blank to allow all.
        :param licenses: allowed licenses.  Leave blank to allow all.
        :param tags: List of tags to match or avoid, depending on ``tag_operation``
        :param tag_operation: "or", "and", "not", "empty", "not empty"
        """
        loop = self._session.loop
        search_task = self._session.search(
            keys=keys, title=title, submitter=submitter, sort_by=sort_by, descending=descending, types=types,
            licenses=licenses, tags=tags, tag_operation=tag_operation
        )
        return synchronize_generator(search_task, loop=loop)

    def batch_describe_assets(self, asset_ids: List[str]) -> Dict[str, Asset]:
        loop = self._session.loop
        tasks = [self._session.describe_asset(asset_id) for asset_id in asset_ids]
        if not tasks:
            return {}
        wait_for = asyncio.wait(tasks, loop=loop, return_when=asyncio.ALL_COMPLETED)
        done, _ = loop.run_until_complete(wait_for)
        assets = [task.result() for task in done]
        return {asset.id: asset for asset in assets}

    def batch_download_assets(self, assets: List[Asset]) -> None:
        loop = self._session.loop
        tasks = [self._session.download_asset(asset) for asset in assets]
        if not tasks:
            return
        wait_for = asyncio.wait(tasks, loop=loop, return_when=asyncio.ALL_COMPLETED)
        loop.run_until_complete(wait_for)
