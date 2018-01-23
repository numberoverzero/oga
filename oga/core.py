# Core operations for downloading, searching on OpenGameArt.org
import asyncio
import aiohttp
import bs4
import enum
import json
import pathlib
import urllib.parse
from typing import List, Optional, NamedTuple, Dict
from configparser import ConfigParser

from oga._helpers import enable_speedups
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
            root_dir="~/.oga"
        )

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
            root_dir=section.get("root_dir", fallback=default.root_dir)
        )


class AssetType(enum.Enum):
    ART_2D = "2D Art"
    ART_3D = "3D Art"
    CONCEPT_ART = "Concept Art"
    TEXTURE = "Texture"
    MUSIC = "Music"
    SOUND_EFFECT = "Sound Effect"
    DOCUMENT = "Document"


class LicenseType(enum.Enum):
    CC_BY_40 = "CC-BY 4.0"
    CC_BY_30 = "CC-BY 3.0"
    CC_BY_SA_40 = "CC-BY-SA 4.0"
    CC_BY_SA_30 = "CC-BY-SA 3.0"
    GPL_30 = "GPL 3.0"
    GPL_20 = "GPL 2.0"
    OGA_BY_30 = "OGA-BY 3.0"
    CC0 = "CC0"
    LGPL_30 = "LGPL 3.0"
    LGPL_21 = "LGPL 2.1"


class AssetFile(NamedTuple):
    id: str
    etag: str
    size: int

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "etag": self.etag,
            "size": self.size
        }


class Asset:
    id: str
    author: str
    type: AssetType
    licenses: List[LicenseType]
    tags: List[str]
    favorites: int
    files: List[AssetFile]

    def __init__(self, id, author, type, licenses, tags, favorites, files) -> None:
        self.id = id
        self.author = author
        self.type = type
        self.licenses = licenses
        self.tags = tags
        self.favorites = favorites
        self.files = files

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "author": self.author,
            "type": self.type.value,
            "licenses": [license.value for license in self.licenses],
            "tags": self.tags,
            "favorites": self.favorites,
            "files": [file.to_json() for file in self.files]
        }

    def __repr__(self) -> str:
        return json.dumps(self.to_json(), sort_keys=True, indent=4)


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
            size=int(headers["Content-Length"])
        )

    async def download_asset(self, asset: Asset, root_dir: Optional[str]=None) -> None:
        if not asset.files:
            return
        tasks = [
            self.download_asset_file(asset.id, asset_file, root_dir=root_dir)
            for asset_file in asset.files
        ]
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


def parse_asset(asset_id: str, data: bytes) -> dict:
    text = data.decode("utf-8")
    soup = bs4.BeautifulSoup(text, "html.parser")

    # 0) author
    authors = soup.find_all(class_="field-name-author-submitter")
    assert len(authors) == 1
    authors = authors[0].find_all("a")
    for maybe_author in authors:
        if maybe_author["href"].startswith("/users/"):
            author = maybe_author["href"][7:]
            break
    else:
        author = None

    # 1) type
    types = soup.find_all(class_="field-name-field-art-type")
    assert len(types) == 1
    type = AssetType(types[0].a.text)

    # 2) licenses
    license_section = soup.find_all(class_="field-name-field-art-licenses")
    assert len(license_section) == 1
    licenses = [
        LicenseType(license.text)
        for license in license_section[0].find_all(class_="license-name")]

    # 3) tags
    tags_section = soup.find_all(class_="field-name-field-art-tags")
    assert len(tags_section) == 1
    tags = [tag.text for tag in tags_section[0].find_all("a")]

    # 4) favorites
    favorites_section = soup.find_all(class_="field-name-favorites")
    assert len(favorites_section) == 1
    favorites = int(favorites_section[0].find(class_="field-item").text)

    # 5) files
    files_section = soup.find_all(class_="field-name-field-art-files")
    assert len(files_section) == 1
    files = []
    for container_el in files_section[0].find_all(class_="file"):
        url = container_el.a["href"]
        file_id = urllib.parse.unquote(url).split("/sites/default/files/")[-1]
        files.append(file_id)
    return {
        "id": asset_id,
        "author": author,
        "type": type,
        "licenses": licenses,
        "tags": tags,
        "favorites": favorites,
        "files": files
    }
