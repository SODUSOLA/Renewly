from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# func: FastAPI dependency: yield a DB session for one request and always close it
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a DB session for one request and always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
