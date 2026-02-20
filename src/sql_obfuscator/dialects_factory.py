from __future__ import annotations

from .dialects_base import DialectProfile
from .dialects_hive import HiveProfile
from .dialects_tsql import TsqlProfile
from .errors import WorkspaceError


_PROFILES: dict[str, DialectProfile] = {
    "tsql": TsqlProfile(),
    "hive": HiveProfile(),
}


def supported_dialects() -> list[str]:
    return sorted(_PROFILES.keys())


def get_dialect_profile(name: str) -> DialectProfile:
    profile = _PROFILES.get(name.lower())
    if profile is None:
        supported = ", ".join(supported_dialects())
        raise WorkspaceError(f"Unsupported dialect '{name}'. Supported dialects: {supported}")
    return profile
