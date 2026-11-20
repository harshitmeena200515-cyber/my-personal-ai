"""
Windows Data Protection API (DPAPI) Integration.

Provides:
- CryptProtectData: Encrypts sensitive buffers (HMAC keys, tokens) using OS-level DPAPI bound to the local user.
- CryptUnprotectData: Decrypts DPAPI-encrypted buffers.
- Pure Python ctypes implementation without external compiled C extensions.
"""

import ctypes
from ctypes import wintypes
from typing import Optional


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


# Windows Crypt32 API bindings
crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32

# Flags
CRYPTPROTECT_UI_FORBIDDEN = 0x1


def dpapi_encrypt(plaintext: bytes, description: Optional[str] = "Antigravity Session Secret") -> bytes:
    """Encrypt sensitive bytes using Windows DPAPI bound to the local Windows user."""
    if not plaintext:
        return b""

    # Prepare input blob
    in_buf = (ctypes.c_byte * len(plaintext))(*plaintext)
    in_blob = DATA_BLOB(len(plaintext), in_buf)
    out_blob = DATA_BLOB()

    desc_w = ctypes.c_wchar_p(description) if description else None

    success = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        desc_w,
        None,  # Optional entropy
        None,  # Reserved
        None,  # Prompt struct
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )

    if not success:
        err = kernel32.GetLastError()
        raise OSError(f"CryptProtectData failed with Windows error code: {err}")

    try:
        encrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return encrypted_bytes
    finally:
        kernel32.LocalFree(out_blob.pbData)


def dpapi_decrypt(ciphertext: bytes) -> bytes:
    """Decrypt Windows DPAPI-protected bytes."""
    if not ciphertext:
        return b""

    # Prepare input blob
    in_buf = (ctypes.c_byte * len(ciphertext))(*ciphertext)
    in_blob = DATA_BLOB(len(ciphertext), in_buf)
    out_blob = DATA_BLOB()

    success = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,  # Description output
        None,  # Optional entropy
        None,  # Reserved
        None,  # Prompt struct
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )

    if not success:
        err = kernel32.GetLastError()
        raise OSError(f"CryptUnprotectData failed with Windows error code: {err}")

    try:
        decrypted_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return decrypted_bytes
    finally:
        kernel32.LocalFree(out_blob.pbData)
