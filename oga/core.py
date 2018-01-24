# Core operations for downloading, searching on OpenGameArt.org
import asyncio
import aiohttp
import json
import pathlib
import urllib.parse
from typing import List, Optional, NamedTuple, Dict, AsyncGenerator
from configparser import ConfigParser

from ._helpers import enable_speedups
from .parsing import (
    Translations,
    parse_asset,
    parse_search_results,
    parse_last_search_page,
)
from .primitives import Asset, AssetFile, AssetType, LicenseType
enable_speedups()


DEFAULT_CONFIG_LOCATION = "~/.oga/config"
CONFIG_SECTION_NAME = "oga"


class Config(NamedTuple):
    url: str
    max_conns: int
    root_dir: str

    @classmethod
    def default(cls):
        return Config(
            url="https://opengameart.org",
            max_conns=5,
            root_dir="~/.oga")

    @classmethod
    def from_file(cls, file_path: Optional[str]=None) -> Optional["Config"]:
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
    def __init__(self, config: Optional[Config]=None, loop: Optional[asyncio.AbstractEventLoop]=None) -> None:
        if config is None:
            config = Config.default()
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.config = config

        # Set up connection limiting according to config
        conn = aiohttp.TCPConnector(limit=config.max_conns, limit_per_host=config.max_conns)
        self._session = aiohttp.ClientSession(connector=conn, loop=loop)
        self._asset_file_cache = {}  # type: Dict[str, Dict[str, str]]

    def __del__(self) -> None:
        self._session.close()

    def search(
            self, *,
            keys: Optional[str]=None,
            title: Optional[str]=None,
            submitter: Optional[str]=None,
            sort_by: Optional[str]=None,
            sort_order: Optional[str]=None,
            types: Optional[List[AssetType]]=None,
            licenses: Optional[List[LicenseType]]=None,
            tags: Optional[List[str]]=None,
            tag_operation: Optional[str]=None) -> AsyncGenerator[str, None]:
        """

        :param keys: appears to search the entire page (including comments, tags...)
        :param title: appears in the asset title
        :param submitter: part or all of the submitter's username.  Not always the author (eg. "submitted by")
        :param sort_by: "favorites", "created", "views"
        :param sort_order: "asc" or "desc"
        :param types: allowed asset types.  Leave blank to allow all.
        :param licenses: allowed licenses.  Leave blank to allow all.
        :param tags: List of tags to match or avoid, depending on ``tag_operation``
        :param tag_operation: "or", "and", "not", "empty", "not empty"
        :return:
        """
        # 0) Apply defaults
        keys = keys or ""
        title = title or ""
        submitter = submitter or ""
        sort_by = (sort_by or "favorites").lower()
        sort_order = (sort_order or "desc").lower()
        types = types or []
        licenses = licenses or []
        tags = tags or []
        tag_operation = (tag_operation or "or").lower()

        # 1) Validate enums
        def validate(param, param_name, allowed):
            if param not in allowed:
                raise ValueError(f"{param_name} must be one of {allowed} but was {param!r}")

        validate(sort_by, "sort_by", {"favorites", "created", "views"})
        validate(sort_order, "sort_order", {"asc", "desc"})
        validate(tag_operation, "tag_operation", {"or", "and", "not", "empty", "not empty"})

        # 2) transform params into request format
        sort_by = {
            "favorites": "count",
            "created": "created",
            "views": "totalcount",
        }[sort_by]
        sort_order = sort_order.upper()
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
            f"sort_order={sort_order.upper()}",
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

    async def download_asset(self, asset: Asset, root_dir: Optional[str]=None) -> None:
        if not asset.files:
            return
        tasks = [
            self.download_asset_file(asset.id, asset_file, root_dir=root_dir)
            for asset_file in asset.files]
        await asyncio.wait(tasks, loop=self.loop, return_when=asyncio.ALL_COMPLETED)

    async def download_asset_file(
            self, asset_id: str, asset_file: AssetFile, root_dir: Optional[str]=None) -> None:
        if root_dir is None:
            root_dir = self.config.root_dir

        # cache hit
        current_etag = self._get_cache_info(asset_id, asset_file.id, root_dir)
        if current_etag is not None and current_etag == asset_file.etag:
            return

        dest_parent = (pathlib.Path(root_dir) / "content" / asset_id).expanduser()
        dest_parent.mkdir(parents=True, exist_ok=True)
        dest = dest_parent / asset_file.id

        # cache miss
        url = f"{self.config.url}/sites/default/files/{asset_file.id}"
        async with self._session.get(url) as response:
            dest.write_bytes(await response.read())
            # update cache
            self._update_cache_info(asset_id, asset_file.id, root_dir, asset_file.etag)

    def _get_cache_info(self, asset_id: str, asset_file_id: str, root_dir: str) -> Optional[str]:
        if asset_id not in self._asset_file_cache:
            cache_dir = (pathlib.Path(root_dir) / "cache").expanduser()
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / asset_id
            try:
                data = cache_file.read_text()
            except FileNotFoundError:
                data = "{}"
                cache_file.write_text(data)
            self._asset_file_cache[asset_id] = json.loads(data)
        return self._asset_file_cache[asset_id].get(asset_file_id)

    def _update_cache_info(self, asset_id: str, asset_file_id: str, root_dir: str, etag: str) -> None:
        if asset_id not in self._asset_file_cache:
            self._get_cache_info(asset_id, asset_file_id, root_dir)
        self._asset_file_cache[asset_id][asset_file_id] = etag
        cache_file = (pathlib.Path(root_dir) / "cache" / asset_id).expanduser()
        cache_file.write_text(json.dumps(self._asset_file_cache[asset_id], sort_keys=True, indent=4))
