from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import psycopg2  # type: ignore[import-untyped]
from psycopg2 import sql
from psycopg2.extras import Json  # type: ignore[import-untyped]

BASE_DIR = Path(__file__).resolve().parent
SEED_DIR = BASE_DIR / "seed_data"

INSERT_ORDER: list[str] = [
    "users",
    "services",
    "service_dependencies",
    "incidents",
    "incident_services",
    "incident_tags",
    "incident_evidence",
    "resolutions",
    "escalation_contacts",
    "sessions",
    "messages",
    "investigation_evidence",
]

UPSERT_CONFLICT_COLUMNS: dict[str, list[str]] = {
    "users": ["id"],
    "incident_services": ["incident_id", "service_id"],
}

REPLACE_TABLES_ON_SEED: set[str] = {"incident_services"}


def get_connection() -> psycopg2.extensions.connection:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return psycopg2.connect(sync_url)

    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    missing = [
        key
        for key, value in {
            "DB_HOST": db_host,
            "DB_PORT": db_port,
            "DB_NAME": db_name,
            "DB_USER": db_user,
            "DB_PASSWORD": db_password,
        }.items()
        if not value
    ]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            f"Missing DB environment configuration. Set DATABASE_URL or all of: {missing_str}"
        )

    # Narrow Optional env values for static type checking after the runtime guard above.
    assert db_host is not None
    assert db_port is not None
    assert db_name is not None
    assert db_user is not None
    assert db_password is not None

    return psycopg2.connect(
        host=db_host,
        port=int(db_port),
        dbname=db_name,
        user=db_user,
        password=db_password,
    )


def load_records(table_name: str) -> list[dict[str, Any]]:
    path = SEED_DIR / f"{table_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing seed file: {path}")

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array in {path}, got {type(payload).__name__}")

    records: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Expected object at {path} index {index}, got {type(item).__name__}")
        records.append(item)

    return records


def adapt_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return Json(value)
    return value


def insert_record(
    cursor: psycopg2.extensions.cursor,
    table_name: str,
    record: dict[str, Any],
) -> int:
    if not record:
        raise ValueError(f"Cannot insert empty record into table '{table_name}'")

    columns = list(record.keys())
    values = [adapt_value(record[column]) for column in columns]
    conflict_columns = UPSERT_CONFLICT_COLUMNS.get(table_name)

    if conflict_columns:
        updatable_columns = [c for c in columns if c not in set(conflict_columns)]
        if updatable_columns:
            query = sql.SQL(
                "INSERT INTO {table} ({columns}) VALUES ({values}) "
                "ON CONFLICT ({conflict_cols}) DO UPDATE SET {updates}"
            ).format(
                table=sql.Identifier(table_name),
                columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                values=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                conflict_cols=sql.SQL(", ").join(
                    sql.Identifier(column) for column in conflict_columns
                ),
                updates=sql.SQL(", ").join(
                    sql.SQL("{col} = EXCLUDED.{col}").format(col=sql.Identifier(column))
                    for column in updatable_columns
                ),
            )
        else:
            query = sql.SQL(
                "INSERT INTO {table} ({columns}) VALUES ({values}) ON CONFLICT DO NOTHING"
            ).format(
                table=sql.Identifier(table_name),
                columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
                values=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            )
    else:
        query = sql.SQL(
            "INSERT INTO {table} ({columns}) VALUES ({values}) ON CONFLICT DO NOTHING"
        ).format(
            table=sql.Identifier(table_name),
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
            values=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )

    cursor.execute(query, values)
    return int(cursor.rowcount)


def seed_table(
    connection: psycopg2.extensions.connection,
    table_name: str,
) -> None:
    records = load_records(table_name)

    if not records:
        print(f"[SKIP] {table_name}: no records")
        connection.commit()
        return

    with connection.cursor() as cursor:
        if table_name in REPLACE_TABLES_ON_SEED:
            cursor.execute(sql.SQL("DELETE FROM {table}").format(table=sql.Identifier(table_name)))
        affected_rows = 0

        for record in records:
            affected_rows += insert_record(cursor, table_name, record)

    connection.commit()
    print(f"[OK] {table_name}: processed {len(records)} record(s), affected {affected_rows} row(s)")


def main() -> None:
    if not SEED_DIR.exists():
        raise FileNotFoundError(f"Seed directory not found: {SEED_DIR}")

    connection = get_connection()
    try:
        for table_name in INSERT_ORDER:
            seed_table(connection, table_name)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
