"""
SentinelAI — Database Auto-Migrator

A lightweight, zero-configuration SQLite migration engine.
Instead of failing on missing columns or requiring Alembic (which is complex to apply to
pre-existing unversioned data), this engine inspects the live SQLite schema on startup and
dynamically issues ALTER TABLE commands to add missing columns and CREATE INDEX commands
for missing indexes. All existing data is safely preserved.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import MetaData, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex


def sync_schema(engine: Engine, metadata: MetaData) -> None:
    """
    Synchronizes the physical SQLite schema with the SQLAlchemy models.
    
    1. Creates any entirely missing tables.
    2. Appends missing columns to existing tables using ALTER TABLE.
    3. Creates missing indexes on existing tables.
    """
    # 1. Let SQLAlchemy create any entirely missing tables first
    metadata.create_all(engine)

    with engine.begin() as conn:  # engine.begin() auto-commits at the end of the block
        for table_name, table in metadata.tables.items():
            
            # Get existing columns from SQLite
            result = conn.execute(text(f"PRAGMA table_info('{table_name}')"))
            existing_columns = {row[1] for row in result}

            # 2. Append missing columns
            for column in table.columns:
                if column.name not in existing_columns:
                    col_type = column.type.compile(engine.dialect)
                    
                    logger.info(f"Migrator: Adding column '{column.name}' ({col_type}) to '{table_name}'")
                    try:
                        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}"))
                        logger.success(f"Migrator: Successfully added {table_name}.{column.name}")
                    except Exception as exc:
                        logger.error(f"Migrator: Failed to add column {table_name}.{column.name}: {exc}")
                        raise

            # 3. Create missing indexes
            # PRAGMA index_list returns: seq, name, unique, origin, partial
            idx_result = conn.execute(text(f"PRAGMA index_list('{table_name}')"))
            existing_indexes = {row[1] for row in idx_result}

            for index in table.indexes:
                if index.name and index.name not in existing_indexes:
                    logger.info(f"Migrator: Creating index '{index.name}' on '{table_name}'")
                    try:
                        conn.execute(CreateIndex(index))
                        logger.success(f"Migrator: Successfully created index {index.name}")
                    except Exception as exc:
                        logger.error(f"Migrator: Failed to create index {index.name}: {exc}")
                        raise
