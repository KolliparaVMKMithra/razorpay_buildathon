import os
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        base = Path(__file__).resolve().parents[1]
        self.database_url = os.getenv(
            "DATABASE_URL", "postgresql://ringwatch:ringwatch@localhost:5432/ringwatch"
        )
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.model_dir = os.getenv("MODEL_DIR", str(base.parent / "ml" / "model"))
        self.data_dir = os.getenv("DATA_DIR", str(base.parent / "data"))
        self.stream_default_file = os.getenv(
            "STREAM_DEFAULT_FILE", "transactions_full_with_labels_v2.csv"
        )
        self.cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000")


settings = Settings()
