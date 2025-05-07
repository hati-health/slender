import os
from pathlib import Path

import pytest

from slenderql.db import DB

from .fixtures import *  # noqa: F403


def read_sql(path: str) -> str:
    with Path.open(path) as f:
        return f.read()


TEST_SCHEMA = read_sql("tests/schema.sql")


POSTGRES_USERNAME = os.getenv("POSTGRES_USERNAME", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")


test_db = DB(
    f"user={POSTGRES_USERNAME} "
    f"password={POSTGRES_PASSWORD} "
    f"host={POSTGRES_HOST} "
    f"dbname={POSTGRES_DB} "
)


tables = [
    "samples",
]


async def create_tables(db: DB) -> None:
    await db.execute(TEST_SCHEMA)


async def drop_tables(db: DB) -> None:
    for table in tables:
        await db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")  # - ok in tests


async def clean_tables(db: DB) -> None:
    await db.execute(f"TRUNCATE {','.join(tables)} CASCADE")


@pytest.fixture(scope="session")
async def prepared_db() -> DB:
    await drop_tables(test_db)
    await create_tables(test_db)

    yield test_db

    await drop_tables(test_db)


@pytest.fixture
async def db(prepared_db: DB) -> DB:
    await clean_tables(prepared_db)
    return prepared_db
