"""Private desktop configuration; Windows credentials use per-user DPAPI."""
import ctypes
import json
import os
from pathlib import Path
import tempfile


class DesktopStoreError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt=False) -> bytes:
    if os.name != "nt":
        raise DesktopStoreError("A proteção Windows não está disponível neste sistema.")
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_wchar_p, ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Blob)]
    crypt32.CryptProtectData.restype = ctypes.c_int
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Blob)]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt32.CryptProtectData(ctypes.byref(source), "MAYCOM CHEF CONTROL", None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise DesktopStoreError("Não foi possível proteger ou ler a conexão. Salve a chave novamente nesta conta do Windows.")
    try:
        return ctypes.string_at(target.data, target.length)
    finally:
        kernel32.LocalFree(target.data)


def load_key(path: Path) -> str:
    path = Path(path)
    if not path.exists():
        return ""
    try:
        raw = path.read_bytes()
        if raw.startswith(b"MCC-DPAPI-1\n"):
            raw = _dpapi(raw.split(b"\n", 1)[1], decrypt=True)
        elif raw.startswith(b"MCC-LOCAL-1\n") and os.name != "nt":
            raw = raw.split(b"\n", 1)[1]
        else:
            raise DesktopStoreError("Formato de configuração inválido. Reconecte o motor de IA.")
        key = json.loads(raw)["fal_key"]
        if not isinstance(key, str):
            raise ValueError()
        return key
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DesktopStoreError("Não foi possível ler a conexão salva. Reconecte o motor de IA.") from exc


def save_key(path: Path, key: str):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps({"fal_key": key}).encode()
    if os.name == "nt":
        payload = b"MCC-DPAPI-1\n" + _dpapi(payload)
    else:
        # Development/test machines only. Windows builds never use this fallback.
        payload = b"MCC-LOCAL-1\n" + payload
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".settings-", delete=False) as out:
            temporary = Path(out.name)
            os.chmod(temporary, 0o600)
            out.write(payload)
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise DesktopStoreError("Não foi possível salvar a conexão neste computador.") from exc
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
