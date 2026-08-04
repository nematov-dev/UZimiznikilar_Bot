from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List, Any
from functools import lru_cache


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

    # Anti-flood
    flood_max_messages: int = Field(5, env="FLOOD_MAX_MESSAGES")
    flood_window_seconds: int = Field(10, env="FLOOD_WINDOW_SECONDS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
