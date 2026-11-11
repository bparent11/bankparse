import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(os.environ.get("BANKPARSE_DATA_DIR", REPO_ROOT / "data")).resolve()
        self.database_url = os.environ.get("BANKPARSE_DATABASE_URL", f"sqlite:///{self.data_dir / 'bankparse.db'}")
        self.uploads_dir = self.data_dir / "uploads"
        self.max_upload_mb = int(os.environ.get("BANKPARSE_MAX_UPLOAD_MB", "20"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
