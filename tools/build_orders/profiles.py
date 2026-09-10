from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re

from .datastore import DATASTORE_FILENAME


_DOCUMENTS_FOLDER_ID = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"
_PROFILE_ID = re.compile(r"[A-Za-z0-9_-]+")


class ProfileResolutionError(ValueError):
    pass


class _Guid(ctypes.Structure):
    _fields_ = (
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", ctypes.c_ubyte * 8),
    )


def _documents_directory() -> Path:
    if os.name != "nt":
        raise ProfileResolutionError(
            "automatic AoE4 profile discovery is supported only on Windows"
        )

    ole32 = ctypes.OleDLL("ole32")
    shell32 = ctypes.OleDLL("shell32")
    guid = _Guid()
    result = ole32.CLSIDFromString(
        ctypes.c_wchar_p(_DOCUMENTS_FOLDER_ID), ctypes.byref(guid)
    )
    if result != 0:
        raise ProfileResolutionError(
            f"could not resolve the Windows Documents folder (CLSID error {result})"
        )

    value = ctypes.c_wchar_p()
    result = shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(value)
    )
    if result != 0 or not value.value:
        raise ProfileResolutionError(
            f"could not resolve the Windows Documents folder (known-folder error {result})"
        )
    try:
        return Path(value.value)
    finally:
        ole32.CoTaskMemFree(value)


def _validate_profile_id(profile_id: str) -> str:
    if not isinstance(profile_id, str) or _PROFILE_ID.fullmatch(profile_id) is None:
        raise ProfileResolutionError(
            "profile ID must contain only letters, digits, underscores, or hyphens"
        )
    return profile_id


def resolve_datastore_path(
    profile_id: str | None,
    documents_dir: Path | None = None,
) -> Path:
    documents = _documents_directory() if documents_dir is None else documents_dir
    users = documents / "My Games" / "Age of Empires IV" / "Users"

    if profile_id is None:
        profiles = (
            sorted(item.name for item in users.iterdir() if item.is_dir())
            if users.is_dir()
            else []
        )
        if not profiles:
            raise ProfileResolutionError(
                f"no AoE4 profiles found under {users}; provide --profile <id>"
            )
        if len(profiles) > 1:
            raise ProfileResolutionError(
                f"multiple AoE4 profiles found under {users}: {', '.join(profiles)}; "
                "provide --profile <id>"
            )
        profile_id = profiles[0]
    else:
        profile_id = _validate_profile_id(profile_id)

    return users / profile_id / "datastore" / DATASTORE_FILENAME
