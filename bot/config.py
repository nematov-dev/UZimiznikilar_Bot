from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator
from typing import List, Optional, Any
from functools import lru_cache
import json
import os
import tempfile


class Settings(BaseSettings):
    # Telegram
    bot_token: str = Field(..., env="BOT_TOKEN")
    admin_ids: List[int] = Field(default_factory=list, env="ADMIN_IDS")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> List[int]:
        """
        ADMIN_IDS=123456789,987654321  → [123456789, 987654321]
        ADMIN_IDS=123456789            → [123456789]
        allaqachon list bo'lsa — o'zgarmaydi
        """
        if isinstance(v, list):
            return [int(i) for i in v]
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            return [int(i.strip()) for i in v.split(",") if i.strip()]
        return []

    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    db_host: str = Field("localhost", env="DB_HOST")
    db_port: int = Field(5432, env="DB_PORT")
    db_name: str = Field("bot_db", env="DB_NAME")
    db_user: str = Field("botuser", env="DB_USER")
    db_password: str = Field("", env="DB_PASSWORD")

    # Groq AI
    groq_api_key: str = Field("", env="GROQ_API_KEY")
    groq_model: str = Field("llama-3.3-70b-versatile", env="GROQ_MODEL")

    # Vertex AI (ixtiyoriy, eski — endi ishlatilmaydi)
    google_project_id: Optional[str] = Field(None, env="GOOGLE_PROJECT_ID")
    google_location: str = Field("us-central1", env="GOOGLE_LOCATION")
    vertex_embedding_model: str = Field("text-multilingual-embedding-002", env="VERTEX_EMBEDDING_MODEL")
    vertex_chat_model: str = Field("gemini-1.5-flash-002", env="VERTEX_CHAT_MODEL")
    google_service_account_json: Optional[str] = Field(None, env="GOOGLE_SERVICE_ACCOUNT_JSON")
    google_application_credentials: Optional[str] = Field(None, env="GOOGLE_APPLICATION_CREDENTIALS")

    # Redis
    redis_url: str = Field("redis://localhost:6379", env="REDIS_URL")

    # Admin Panel
    admin_panel_host: str = Field("0.0.0.0", env="ADMIN_PANEL_HOST")
    admin_panel_port: int = Field(8000, env="ADMIN_PANEL_PORT")
    secret_key: str = Field("change-me", env="SECRET_KEY")
    admin_username: str = Field("admin", env="ADMIN_USERNAME")
    admin_password: str = Field("changeme", env="ADMIN_PASSWORD")

    # Bot behavior
    max_warnings: int = Field(3, env="MAX_WARNINGS")
    mute_duration_minutes: int = Field(60, env="MUTE_DURATION_MINUTES")
    delete_join_leave_messages: bool = Field(True, env="DELETE_JOIN_LEAVE_MESSAGES")

    # RAG
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k_results: int = 5

    # Anti-flood
    flood_max_messages: int = Field(5, env="FLOOD_MAX_MESSAGES")
    flood_window_seconds: int = Field(10, env="FLOOD_WINDOW_SECONDS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @model_validator(mode="after")
    def setup_google_credentials(self) -> "Settings":
        """
        GOOGLE_SERVICE_ACCOUNT_JSON env da JSON string bo'lsa →
        uni vaqtinchalik faylga yozib GOOGLE_APPLICATION_CREDENTIALS ni o'rnatadi.
        Xato bo'lsa — xabar chiqarib davom etadi (crash bo'lmaydi).
        """
        if self.google_service_account_json:
            try:
                creds_data = json.loads(self.google_service_account_json)
            except (json.JSONDecodeError, ValueError):
                # Noto'g'ri JSON — Vertex AI o'chiriladi, bot ishlayveradi
                import sys
                print(
                    "[CONFIG] GOOGLE_SERVICE_ACCOUNT_JSON noto'g'ri JSON — "
                    "Vertex AI o'chirildi. RAG funksiyasi ishlamaydi.",
                    file=sys.stderr
                )
                self.google_service_account_json = None
                return self

            try:
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, prefix="gcp_sa_"
                )
                json.dump(creds_data, tmp, ensure_ascii=False)
                tmp.flush()
                tmp.close()
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
                self.google_application_credentials = tmp.name
            except Exception as e:
                import sys
                print(f"[CONFIG] Temp fayl yaratishda xato: {e}", file=sys.stderr)

        elif self.google_application_credentials:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_application_credentials

        return self

    def get_db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def get_service_account_info(self) -> Optional[dict]:
        """Vertex AI credentials dict ni qaytaradi (to'g'ridan-to'g'ri ishlatish uchun)."""
        if self.google_service_account_json:
            return json.loads(self.google_service_account_json)
        return None


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
