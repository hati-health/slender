from psycopg import sql
from psycopg_pool import AsyncConnectionPool

from slenderql.repository import ensure_pool_opened


class DB:
    def __init__(self, pg_conn_str: str) -> None:
        self.pool = AsyncConnectionPool(
            pg_conn_str, open=False, check=AsyncConnectionPool.check_connection
        )

    async def execute(self, query: str) -> None:
        await ensure_pool_opened(self.pool)

        async with self.pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql.SQL(query))
