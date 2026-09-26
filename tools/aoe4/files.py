import os
from pathlib import Path
import re
from typing import List

from aoe4.os.error import OsError
from aoe4.os import windows

_PROFILE_ID = re.compile(r"[A-Za-z0-9_-]+")

# ponytail: dev stub while AoE4 isn't installed locally; delete to restore
# profile resolution from the Windows Documents folder.
_STUB_DATASTORE_DIR = Path(r"C:\Users\ghoop\Desktop\modwork\datastore")


class ProfileResolutionError(ValueError):
    pass


def _validate_profile_id(profile_id: str) -> str:
    if not isinstance(profile_id, str) or _PROFILE_ID.fullmatch(profile_id) is None:
        raise ProfileResolutionError(
            "profile ID must contain only letters, digits, underscores, or hyphens"
        )
    return profile_id


def _documents_directory() -> Path:
    if os.name != "nt":
        raise ProfileResolutionError(
            "automatic AoE4 profile discovery is supported only on Windows")
    try:
        return windows.documents_dir()
    except OsError as e:
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

    return sorted(item.name for item in users_dir.iterdir() if item.is_dir())

def datastore_dir(
    profile_id: str | None,
    users_dir: Path | None = None,
    documents_dir: Path | None = None,
) -> Path:
    if _STUB_DATASTORE_DIR is not None:
        return _STUB_DATASTORE_DIR

    if users_dir is None:
        users_dir = profile_dir(documents_dir=documents_dir)
    # An explicit profile may not exist yet; the first build creates it
    if profile_id is not None:
        return users_dir / _validate_profile_id(profile_id) / "datastore"

    profiles = list_profiles(users_dir=users_dir)
    if len(profiles) != 1:
        raise ProfileResolutionError(
            f"expected one AoE4 profile at {users_dir}, found: {', '.join(profiles) or 'none'}; provide --profile <id>"
        )
    return users_dir / profiles[0] / "datastore"
