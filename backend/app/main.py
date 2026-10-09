"""FastAPI application entry point. Run with: uvicorn app.main:app --reload"""
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.models_registry  # noqa: F401  (registers every model; mappers need them all)
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import register_middleware
from app.core.observability import init_sentry
from app.modules.auth.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.documents.router import router as documents_router
from app.modules.vehicles.router import router as vehicles_router

logger = logging.getLogger(__name__)
settings = get_settings()
configure_logging(settings.log_level, settings.log_format)
init_sentry()

app = FastAPI(title=settings.app_name)
register_error_handlers(app)
register_middleware(app)
# Added last so it is the outermost layer: even 401/429/500 responses carry CORS
# headers, otherwise the browser hides the real error behind a generic CORS failure.
# Auth uses a bearer header (no cookies), so credentials are not enabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
    max_age=600,
)

app.include_router(auth_router)
app.include_router(vehicles_router)
app.include_router(documents_router)
app.include_router(dashboard_router)


# func to report that the process is alive
@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe: answers as long as the process is running."""
    return {"status": "ok"}


# func to report that the app can serve traffic
@app.get("/health/ready", tags=["meta"])
def ready(db: Session = Depends(get_db)):
    """Readiness probe: 200 if the database answers, 503 if it does not."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB failure means "not ready"
        # Log the real cause (never sent to the client) so operators can see why.
        logger.exception("Readiness check failed: database unreachable")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ready"}
