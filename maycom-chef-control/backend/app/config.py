from dataclasses import dataclass, field
import os
from pathlib import Path


def storage_bytes(directory: Path) -> int:
    total = 0
    for entry in directory.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except FileNotFoundError:
            # A worker may atomically replace or remove a temporary file.
            continue
    return total


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("MAYCOM_DATA_DIR", str(Path(__file__).resolve().parents[2] / ".data"))))
    fal_key: str = field(default_factory=lambda: os.getenv("FAL_KEY", ""))
    comfy_url: str = field(default_factory=lambda: os.getenv("MAYCOM_COMFY_URL", "http://127.0.0.1:8188"))
    access_token: str = field(default_factory=lambda: os.getenv("MAYCOM_ACCESS_TOKEN", ""))
    review_token: str = field(default_factory=lambda: os.getenv("MAYCOM_REVIEW_TOKEN", ""))
    desktop_mode: bool = False
    desktop_config_path: Path | None = None
    worker_enabled: bool = True
    poll_interval: float = 3.0
    max_job_seconds: int = 4 * 3600
    max_queue: int = 20
    max_upload_bytes: int = 150 * 1024 * 1024
    storage_quota_bytes: int = 10 * 1024 * 1024 * 1024
    allowed_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000")

    def prepare(self):
        if self.desktop_mode and (not self.access_token or not self.review_token):
            raise ValueError("O aplicativo portátil deve criar sua sessão privada antes de iniciar.")
        self.data_dir = self.data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data_dir.chmod(0o700)
        for name in ("assets", "jobs", "tmp"):
            directory = self.data_dir / name
            directory.mkdir(exist_ok=True, mode=0o700)
            directory.chmod(0o700)
