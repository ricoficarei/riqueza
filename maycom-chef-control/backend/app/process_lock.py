"""Single-worker lock supported on Windows and Unix."""
import os
from pathlib import Path


def acquire_worker_lock(path: Path):
    handle = Path(path).open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError as exc:
        handle.close()
        raise RuntimeError("Use somente um processo do aplicativo por diretório de dados.") from exc
