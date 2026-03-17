"""
Thin re-export shim — all configuration lives in config/settings.py.
Import from either path; both resolve to the same singleton.
"""
from migration_platform.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
