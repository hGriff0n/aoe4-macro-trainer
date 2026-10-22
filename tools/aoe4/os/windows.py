import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re

from aoe4.os.error import OsError

_DOCUMENTS_FOLDER_ID = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"
_PROFILE_ID = re.compile(r"[A-Za-z0-9_-]+")


class _Guid(ctypes.Structure):
    _fields_ = (
        ("data1", wintypes.DWORD),
        ("data2", wintypes.WORD),
        ("data3", wintypes.WORD),
        ("data4", ctypes.c_ubyte * 8),
    )


def documents_dir() -> Path:
    if os.name != "nt":
        raise OsError(
            "aoe4.os.windows functions are only supported on windows")

    ole32 = ctypes.OleDLL("ole32")
    shell32 = ctypes.OleDLL("shell32")
    guid = _Guid()
    result = ole32.CLSIDFromString(
        ctypes.c_wchar_p(_DOCUMENTS_FOLDER_ID), ctypes.byref(guid)
    )
    if result != 0:
        raise OsError(
            f"could not resolve the Windows Documents folder (CLSID error {result})"
        )

    value = ctypes.c_wchar_p()
    result = shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(value)
    )
    if result != 0 or not value.value:
        raise OsError(
            f"could not resolve the Windows Documents folder (known-folder error {result})"
        )
    try:
        return Path(value.value)
    finally:
        ole32.CoTaskMemFree(value)
