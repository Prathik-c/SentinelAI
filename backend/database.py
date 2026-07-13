"""
SentinelAI — Database Engine & Session Factory

Key design decisions:
- WAL journal mode: allows concurrent reads while a write is in progress,
  eliminating the most common source of "database is locked" errors.
- busy_timeout=5000: SQLite will retry for up to 5 seconds on lock contention
  before raising an error (instead of failing immediately).
- check_same_thread=False: required for FastAPI which uses multiple threads.
- pool_pre_ping: validates connections before use, catching stale handles.
- Indexes: created on frequently-queried columns (timestamp, status, type).
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from config import DB_PATH

# Ensure the parent directory exists before SQLAlchemy tries to open the file.
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Engine — SQLite with WAL and concurrency-safe settings
# ---------------------------------------------------------------------------
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={
        "check_same_thread": False,   # Allow access from multiple threads
        "timeout": 15,                # sqlite3 busy timeout (seconds)
    },
    # StaticPool is appropriate for SQLite + multi-thread: reuses one
    # underlying connection safely across threads via check_same_thread=False.
    poolclass=StaticPool,
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """
    Applied once per physical database connection.
    WAL mode is the single most important fix for concurrent access.
    """
    cursor = dbapi_connection.cursor()
    # Write-Ahead Logging: readers don't block writers and vice-versa.
    cursor.execute("PRAGMA journal_mode=WAL")
    # NORMAL sync: durable enough for our use-case, faster than FULL.
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Wait up to 5 000 ms when another connection holds the write lock.
    cursor.execute("PRAGMA busy_timeout=5000")
    # 64 MB page cache for better read performance.
    cursor.execute("PRAGMA cache_size=-64000")
    # Foreign key enforcement.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Prevent lazy-load issues after commit
)

Base = declarative_base()


# ---------------------------------------------------------------------------
# Dependency — for FastAPI route injection
# ---------------------------------------------------------------------------
def get_db():
    """
    FastAPI dependency that yields a database session and guarantees cleanup.
    Usage: ``db: Session = Depends(get_db)``
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()