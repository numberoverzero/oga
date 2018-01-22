# Core operations for downloading, searching on OpenGameArt.org
import asyncio
import aiohttp
import enum
import pathlib
from typing import Dict, List, Optional, NamedTuple
from configparser import ConfigParser

DEFAULT_CONFIG_LOCATION = "~/.oga/config"
CONFIG_SECTION_NAME = "oga"


class Config(NamedTuple):
    url: str
    max_conns: int
    assets_root_dir: str

    @classmethod
    def default(cls):
        return Config(
            url="https://opengameart.org",
            max_conns=5,
            assets_root_dir="~/.oga/assets"
        )

    @classmethod
    def from_file(cls, file_path: Optional[str]=None) -> Optional[Config]:
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
            assets_root_dir=section.get("assets_root_dir", fallback=default.assets_root_dir)
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
    size_in_bytes: int
    downloads: int


class Asset:
    id: str
    author: str
    type: AssetType
    licenses: List[LicenseType]
    tags: List[str]
    favorites: int
    files: List[AssetFile]


class Session:
    def __init__(self, config: Config, loop: Optional[asyncio.AbstractEventLoop]=None) -> None:
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.config = config

        # Set up connection limiting according to config
        conn = aiohttp.TCPConnector(limit=config.max_conns, limit_per_host=config.max_conns)
        self._session = aiohttp.ClientSession(connector=conn, loop=loop)

    def head_asset(self, asset_id: str) -> Asset:
        return self.head_assets([asset_id])[asset_id]

    def head_assets(self, asset_ids: List[str]) -> Dict[str, Asset]:
        assets = {}  # type: Dict[str, Asset]
        # TODO aiohttp batch download self.config.url / "content" / asset_id and parse
        return assets

    def download_asset(self, asset: Asset) -> None:
        dest = (
            pathlib.Path(self.config.assets_root_dir).expanduser() /
            "content" /
            asset.id
        )
        dest.mkdir(parents=True, exist_ok=True)
        # TODO aiohttp batch download to dest/asset_file.id
