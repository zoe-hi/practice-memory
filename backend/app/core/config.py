from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite:///./data/app.db"
    audio_storage_dir: str = "./storage/audio"
    max_audio_bytes: int = 15 * 1024 * 1024
    session_ttl_hours: int = Field(default=24, gt=0)
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    ai_provider: str = "fake"
    ai_api_key: str = ""
    ai_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    ai_model: str = "qwen-plus"
    ai_asr_model: str = "qwen3-asr-flash"
    ai_timeout_seconds: int = Field(default=75, gt=0)
    ai_max_retries: int = Field(default=1, ge=0, le=1)

    demo_contributor_name: str = "吴瑶儿"
    demo_contributor_role: str = "乡村图书馆员"
    demo_org_context: str = (
        "本机构服务村庄儿童、青少年与妇女；活动设计应从当地需求和环境出发，"
        "保留一线工作者判断，不让 AI 替代当地经验。"
    )

    @model_validator(mode="after")
    def validate_provider(self) -> "Settings":
        self.app_env = self.app_env.strip().lower()
        origins = [value.strip() for value in self.cors_origins.split(",") if value.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin")
        if "*" in origins and len(origins) != 1:
            raise ValueError("CORS_ORIGINS cannot mix '*' with explicit origins")
        if self.app_env == "production" and "*" in origins:
            raise ValueError("CORS_ORIGINS cannot contain '*' in production")
        for origin in origins:
            if origin == "*":
                continue
            parsed_origin = urlsplit(origin)
            try:
                parsed_origin.port
            except ValueError as exc:
                raise ValueError("CORS_ORIGINS contains an invalid port") from exc
            if (
                parsed_origin.scheme not in {"http", "https"}
                or not parsed_origin.netloc
                or parsed_origin.username is not None
                or parsed_origin.password is not None
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
            ):
                raise ValueError("CORS_ORIGINS must contain only HTTP/HTTPS origins")
        self.cors_origins = ",".join(origins)
        self.log_level = self.log_level.strip().upper()
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
        self.ai_provider = self.ai_provider.strip().lower()
        self.demo_org_context = self.demo_org_context.strip()
        if not self.demo_org_context:
            raise ValueError("DEMO_ORG_CONTEXT must not be blank")
        if self.ai_provider not in {"fake", "dashscope"}:
            raise ValueError("AI_PROVIDER must be 'fake' or 'dashscope'")
        if self.ai_provider == "dashscope":
            if not self.ai_api_key.strip():
                raise ValueError("AI_API_KEY is required for AI_PROVIDER=dashscope")
            if not self.ai_model.strip():
                raise ValueError("AI_MODEL is required for AI_PROVIDER=dashscope")
            if not self.ai_asr_model.strip():
                raise ValueError("AI_ASR_MODEL is required for AI_PROVIDER=dashscope")
            parsed_url = urlsplit(self.ai_base_url.strip())
            if (
                parsed_url.scheme != "https"
                or not parsed_url.netloc
                or parsed_url.username is not None
                or parsed_url.password is not None
                or parsed_url.query
                or parsed_url.fragment
            ):
                raise ValueError(
                    "AI_BASE_URL must be an HTTPS URL without credentials, query, or fragment"
                )
            self.ai_api_key = self.ai_api_key.strip()
            self.ai_base_url = self.ai_base_url.strip().rstrip("/")
            self.ai_model = self.ai_model.strip()
            self.ai_asr_model = self.ai_asr_model.strip()
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return self.cors_origins.split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()
