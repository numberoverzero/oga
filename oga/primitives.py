import enum
import json
from typing import List, NamedTuple


__all__ = ["Asset", "AssetFile", "AssetType", "LicenseType"]


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
            "size": self.size}


class Asset:
    id: str
    author: str
    type: AssetType
    licenses: List[LicenseType]
    tags: List[str]
    favorites: int
    files: List[AssetFile]
    attribution: str

    def __init__(self, id, author, type, licenses, tags, favorites, files, attribution=None) -> None:
        self.id = id
        self.author = author
        self.type = type
        self.licenses = licenses
        self.tags = tags
        self.favorites = favorites
        self.files = files
        self.attribution = attribution

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "author": self.author,
            "type": self.type.value,
            "licenses": [license.value for license in self.licenses],
            "tags": self.tags,
            "favorites": self.favorites,
            "files": [file.to_json() for file in self.files],
            "attribution": self.attribution
        }

    def __repr__(self) -> str:
        return json.dumps(self.to_json(), sort_keys=True, indent=4)
