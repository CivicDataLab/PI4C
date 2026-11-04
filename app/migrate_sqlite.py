"""Copy everything from the SQLite database into the database in DATABASE_URL (Postgres).

    uv run python -m app.migrate_sqlite                  # from data/pi4c.db
    uv run python -m app.migrate_sqlite path/to/other.db

Creates the tables if needed and refuses to run if the target already has data, so it can't
duplicate rows. IDs are kept (complaint numbers like PI4C-000012 stay the same) and each
Postgres ID sequence is moved past the highest copied ID. Media files stay in data/media.
"""

import sys
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select, text

from app import models  # noqa: F401  registers tables
from app.config import BASE_DIR
from app.db import Base, engine, init_db


def main() -> None:
    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR / "data" / "pi4c.db"
    if not source_path.exists():
        sys.exit(f"no SQLite database at {source_path}")
    if engine.dialect.name != "postgresql":
        sys.exit("DATABASE_URL must point at Postgres (set it in .env)")

    source = create_engine(f"sqlite:///{source_path.as_posix()}")
    init_db()
    tables = Base.metadata.sorted_tables  # parents first (clusters before reports before media)

    with engine.begin() as dst:
        for table in tables:
            if dst.scalar(select(func.count()).select_from(table)):
                sys.exit(f"target table {table.name} already has rows; use an empty database")

        with source.connect() as src:
            existing = set(inspect(src).get_table_names())
            for table in tables:
                if table.name not in existing:  # e.g. media_files, added after older databases were made
                    print(f"{table.name}: not in source, skipped")
                    continue
                rows = [dict(r._mapping) for r in src.execute(select(table))]
                if rows:
                    dst.execute(table.insert(), rows)
                print(f"{table.name}: {len(rows)} rows")

        for table in tables:
            pk = list(table.primary_key.columns)
            # Only own integer IDs have a sequence (not inbound_messages' text key or media_files' media_id)
            if len(pk) == 1 and pk[0].type.python_type is int and not pk[0].foreign_keys:
                dst.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk[0].name}'), "
                    f"COALESCE((SELECT MAX({pk[0].name}) FROM {table.name}), 0) + 1, false)"
                ))
    print(f"done: {source_path.name} copied to Postgres")


if __name__ == "__main__":
    main()
