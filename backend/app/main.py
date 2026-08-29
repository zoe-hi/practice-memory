from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import make_url
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai import AIProvider
from app.audio import AudioStorage
from app.api.capture_sessions import router as capture_sessions_router
from app.api.decision_support import router as decision_support_router
from app.api.experiences import router as experiences_router
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.errors import (
    AppError,
    app_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.cleanup import cleanup_expired_sessions
from app.db.base import Base
from app.db.session import build_engine, build_session_factory
from app.dashscope_provider import build_ai_provider
import app.models  # noqa: F401  Ensures model metadata is registered.


def _ensure_runtime_directories(settings: Settings) -> None:
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    Path(settings.audio_storage_dir).expanduser().resolve().mkdir(parents=True, exist_ok=True)


def create_app(
    settings: Settings | None = None, ai_provider: AIProvider | None = None
) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine = build_engine(resolved_settings.database_url)
    session_factory = build_session_factory(engine)
    audio_storage = AudioStorage(
        resolved_settings.audio_storage_dir, resolved_settings.max_audio_bytes
    )
    logger = configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            _ensure_runtime_directories(resolved_settings)
            audio_storage.ensure_root()
            Base.metadata.create_all(engine)
            cleanup_result = cleanup_expired_sessions(session_factory, audio_storage)
            application.state.startup_cleanup_result = cleanup_result
            log_method = logger.warning if cleanup_result.failed else logger.info
            log_method(
                "event=startup_cleanup deleted=%d failed=%d skipped=%d",
                cleanup_result.deleted,
                cleanup_result.failed,
                cleanup_result.skipped,
            )
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="Practice Memory API", version="0.1.0", lifespan=lifespan)
    application.state.settings = resolved_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.ai_provider = (
        ai_provider if ai_provider is not None else build_ai_provider(resolved_settings)
    )
    application.state.audio_storage = audio_storage

    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_error_handler)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(capture_sessions_router, prefix="/api/v1")
    application.include_router(decision_support_router, prefix="/api/v1")
    application.include_router(experiences_router, prefix="/api/v1")
    return application


app = create_app()
