import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re

from aoe4.os.error import OsError
import aoe4.os.windows

_DOCUMENTS_FOLDER_ID = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"
_PROFILE_ID = re.compile(r"[A-Za-z0-9_-]+")


class ProfileResolutionError(ValueError):
    pass


def _validate_profile_id(profile_id: str) -> str:
    if not isinstance(profile_id, str) or _PROFILE_ID.fullmatch(profile_id) is None:
        raise ProfileResolutionError(
            "profile ID must contain only letters, digits, underscores, or hyphens"
        )
    return profile_id


def _documents_directory() -> str:
    try:
        if os.name != "nt":
            raise ProfileResolutionError(
                "automatic AoE4 profile discovery is supported only on Windows")
        else:
            return windows.documents_dir()

    except OsError e:
        raise ProfileResolutionError(e)

def profile_dir(documents_dir: Path | None = None) -> Path:
    if documents_dir is None:
        documents_dir = _documents_directory()
    return documents_dir / "My Games" / "Age of Empires IV" / "Users"

def list_profiles(
    users_dir: Path | None = None,
    documents_dir: Path | None = None
) -> List[str]:
    if users_dir is None:
        users_dir = profile_dir(documents_dir=documents_dir)
    if not users_dir.is_dir():
        raise ProfileResolutionError(f'{users_dir} is not a directory')
    
    # TODO: Is `name` correct here?
    return list(sorted(
        item.name for item in users.iterdir() if item.is_dir()))

def datastore_dir(
    profile_id: str | None,
    users_dir: Path | None = None,
    documents_dir: Path | None = None,
) -> Path:
    if users_dir is None:
        users_dir = profile_dir(documents_dir=documents_dir)
    if not users_dir.is_dir():
        raise ProfileResolutionError(f'{users_dir} is not a directory')
    profiles = list_profiles(users_dir=users_dir)
    if len(profiles) > 1:
        raise ProfileResolutionError(
            f"multiple AoE4 profiles found at {users_dir}: {', '.join(profiles)}; provide --profile <id>"
        )
    return users_dir / profiles[0] / "datastore"
