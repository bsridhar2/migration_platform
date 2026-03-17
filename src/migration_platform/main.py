"""Application entry point — FastAPI app factory."""
from __future__ import annotations
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from migration_platform.api.routes.migration import init_router, router as migration_router
from migration_platform.config.settings import get_settings
from migration_platform.core.exceptions import MigrationPlatformError
from migration_platform.core.logging import configure_logging, get_logger
from migration_platform.storage.state_store import StateStore
from migration_platform.workflows.migration_graph import build_migration_graph

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    configure_logging()
    settings = get_settings()
    logger.info("Starting AI Migration Platform", version=settings.app_version)

    graph = build_migration_graph()
    state_store = StateStore(db_path=settings.duckdb_path)
    init_router(graph, state_store)

    app.state.graph = graph
    app.state.state_store = state_store

    logger.info("Platform ready", host=settings.host, port=settings.port)
    yield

    state_store.close()
    logger.info("Platform shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI-Powered Java Monolith Migration Platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(migration_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Log full Pydantic validation errors so they appear in the backend console."""
        body_bytes = await request.body()
        body_preview = body_bytes.decode("utf-8", errors="replace")[:500]
        logger.warning(
            "request.validation_error",
            method=request.method,
            url=str(request.url),
            raw_body=body_preview,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(MigrationPlatformError)
    async def platform_error_handler(
        request: Request, exc: MigrationPlatformError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": exc.message, "type": type(exc).__name__},
        )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "migration_platform.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
