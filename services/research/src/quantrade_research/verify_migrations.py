"""Apply every ordered migration to a disposable CI database."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from .config import Settings


MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def ordered_migrations(directory: Path) -> tuple[Path, ...]:
    migrations = tuple(sorted(directory.glob("*.sql")))
    if not migrations:
        raise ValueError(f"no migrations found in {directory}")
    for expected, migration in enumerate(migrations, start=1):
        match = MIGRATION_NAME.fullmatch(migration.name)
        if match is None:
            raise ValueError(f"invalid migration filename: {migration.name}")
        if int(match.group(1)) != expected:
            raise ValueError(
                f"migration sequence is not contiguous: expected {expected:04d}, found {migration.name}"
            )
    return migrations


def require_disposable_database(database_url: str, required_suffix: str = "_ci") -> str:
    parsed = urlparse(database_url)
    database = unquote(parsed.path.lstrip("/"))
    if parsed.scheme not in {"postgres", "postgresql"} or not database:
        raise ValueError("DATABASE_URL must identify a PostgreSQL database")
    if not required_suffix or not database.endswith(required_suffix):
        raise ValueError(
            f"migration verification refuses database '{database}'; its name must end with '{required_suffix}'"
        )
    return database


def verify_migrations(*, database_url: str, migration_directory: Path) -> tuple[int, int]:
    database = require_disposable_database(database_url)
    migrations = ordered_migrations(migration_directory)
    import psycopg

    with psycopg.connect(database_url, autocommit=True) as connection:
        for migration in migrations:
            connection.execute(migration.read_text(encoding="utf-8"))
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT COUNT(*)
                   FROM information_schema.tables
                   WHERE table_schema = 'quantrade' AND table_type = 'BASE TABLE'"""
            )
            table_count = int(cursor.fetchone()[0])
    if table_count < 1:
        raise RuntimeError("migrations completed without creating Quantrade tables")
    return len(migrations), table_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify all Quantrade migrations on a disposable *_ci database")
    parser.add_argument(
        "--migration-directory", type=Path,
        default=Path("services/research/db/migrations"),
    )
    args = parser.parse_args()
    settings = Settings.from_environment()
    if not settings.database_url:
        parser.error("DATABASE_URL is required")
    migrations, tables = verify_migrations(
        database_url=settings.database_url,
        migration_directory=args.migration_directory,
    )
    print(f"migration_verification=passed; migrations={migrations}; tables={tables}")


if __name__ == "__main__":
    main()
