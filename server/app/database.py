"""
database.py — SQLite engine setup and table creation.

Uses SQLModel (thin SQLAlchemy wrapper) with a synchronous SQLite engine.
All table definitions live in models.py; this module owns only the engine
and the create_all() bootstrap call.

Design decision: synchronous SQLite is perfectly adequate for a hackathon
(single-user, low concurrency). For production, migrate to async SQLAlchemy
with a PostgreSQL URL and use AsyncSession.
"""

from sqlmodel import SQLModel, Session, create_engine

from .config import get_settings

settings = get_settings()

engine = create_engine(
    settings.db_url,
    # check_same_thread=False is required for SQLite when multiple threads share
    # the same connection (background reader thread + request handlers).
    connect_args={"check_same_thread": False},
    echo=False,  # Set True to log every SQL statement — useful for debugging
)


def create_db_and_tables() -> None:
    """
    Create all tables defined via SQLModel metadata.
    Called once at server startup (from main.py lifespan).
    Safe to call on every startup — SQLModel skips existing tables.
    """
    SQLModel.metadata.create_all(engine)


def get_session():
    """
    FastAPI dependency: yields an ORM Session and closes it after the request.

    Usage in a route:
        def my_route(db: Session = Depends(get_session)): ...
    """
    with Session(engine) as session:
        yield session
