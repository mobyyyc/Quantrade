"""Create the deterministic local demonstration database safely."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit, urlunsplit

from .score_run import _dotenv_values


DEMO_DATABASE_NAME = "quantrade_demo"
_SAFE_DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]{2,62}_demo$")
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_demo_database_name(value: str) -> str:
    if not _SAFE_DATABASE_NAME.fullmatch(value):
        raise ValueError("Demo database names must be lowercase identifiers ending in _demo.")
    return value


def database_url_for(database_url: str, database_name: str) -> str:
    validate_demo_database_name(database_name)
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise ValueError("DATABASE_URL must be a PostgreSQL URI with a hostname.")
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{quote(database_name, safe='')}", parsed.query, parsed.fragment))


def require_local_database(database_url: str) -> None:
    parsed = urlsplit(database_url)
    if parsed.hostname not in _LOOPBACK_HOSTS:
        raise ValueError("The demo reset is restricted to a local PostgreSQL server.")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _database_url(env_file: Path) -> str:
    configured = os.environ.get("DATABASE_URL") or _dotenv_values(env_file).get("DATABASE_URL")
    if not configured:
        raise ValueError(f"DATABASE_URL is missing from {env_file}.")
    return configured


def create_demo_database(*, database_url: str, database_name: str = DEMO_DATABASE_NAME) -> dict[str, object]:
    import psycopg
    from psycopg import sql

    validate_demo_database_name(database_name)
    require_local_database(database_url)
    root = _repository_root()
    migration_directory = root / "services" / "research" / "db" / "migrations"
    fixture_path = root / "apps" / "web" / "e2e" / "seed.sql"
    migrations = sorted(migration_directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not migrations:
        raise RuntimeError("No ordered database migrations were found.")
    if not fixture_path.is_file():
        raise RuntimeError(f"Synthetic fixture is missing: {fixture_path}")

    parsed = urlsplit(database_url)
    admin_url = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment))
    target_url = database_url_for(database_url, database_name)

    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (database_name,),
        )
        connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}" ).format(sql.Identifier(database_name)))
        connection.execute(sql.SQL("CREATE DATABASE {}" ).format(sql.Identifier(database_name)))

    with psycopg.connect(target_url) as connection:
        for migration in migrations:
            connection.execute(migration.read_text(encoding="utf-8"))
        fixture = fixture_path.read_text(encoding="utf-8")
        connection.execute(fixture)
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                     (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'quantrade'),
                     (SELECT count(*) FROM quantrade.securities),
                     (SELECT count(*) FROM quantrade.score_snapshots),
                     (SELECT count(*) FROM quantrade.raw_artifacts)"""
            )
            table_count, security_count, score_count, artifact_count = cursor.fetchone()

    return {
        "contract": "quantrade_synthetic_demo_v1",
        "database": database_name,
        "migrationCount": len(migrations),
        "fixtureSha256": sha256(fixture_path.read_bytes()).hexdigest(),
        "tableCount": table_count,
        "securityCount": security_count,
        "scoreCount": score_count,
        "artifactCount": artifact_count,
        "containsProviderDocuments": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset and seed the local synthetic Quantrade demo database")
    parser.add_argument("--env-file", type=Path, default=Path(".env.demo"))
    parser.add_argument("--database-name", default=DEMO_DATABASE_NAME)
    arguments = parser.parse_args()
    result = create_demo_database(
        database_url=_database_url(arguments.env_file),
        database_name=arguments.database_name,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
