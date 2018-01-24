__version__ = "1.0.0"

from ._helpers import enable_speedups
from .core import Session
from .primitives import Asset, AssetFile, AssetType, LicenseType

__all__ = [
    "Asset", "AssetFile", "AssetType", "LicenseType",
    "Session"
]

enable_speedups()

