__version__ = "1.0.0"

from . import _helpers
from .core import Config, Session, SynchronizedSession
from .primitives import Asset, AssetFile, AssetType, LicenseType


__all__ = [
    "Asset", "AssetFile", "AssetType", "LicenseType",
    "Config", "Session", "SynchronizedSession",
]


# Hooray for uvloop!
_helpers.enable_speedups()
