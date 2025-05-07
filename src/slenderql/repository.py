import contextvars
import re
from collections.abc import Callable
from typing import Any

import psycopg
import sentry_sdk
from psycopg.rows import class_row
from psycopg_pool import AsyncConnectionPool

domain = contextvars.ContextVar("domain", default=None)


async def ensure_pool_opened(pool: AsyncConnectionPool) -> None:
    if pool.closed:
        await pool.open()


class BaseRepository:
    model = None

    def __init__(self, pool: AsyncConnectionPool, domain: str) -> None:
        self.pool = pool
        self.domain = domain

    async def fetchone(
        self, query: str, params: list[Any], model: Callable | None = None
    ) -> Any:
        domain.set(self.domain)
        await ensure_pool_opened(self.pool)
        async with (
            self.pool.connection() as conn,
            conn.cursor(row_factory=class_row(model or self.model)) as cur,
        ):
            return await self.fetchone_cur(cur, query, params)

    async def fetchone_cur(
        self,
        cur: psycopg.AsyncCursor,
        query: str,
        params: list[Any],
        model: Callable | None = None,
    ) -> Any:
        domain.set(self.domain)
        await ensure_pool_opened(self.pool)

        with sentry_sdk.start_span(op="db.sql.query", description=query):
            await cur.execute(*prepare_query_statements(query, params))

        if not model:
            return await cur.fetchone()

        current_row_factory = cur.row_factory

        cur.row_factory = class_row(model or self.model)
        try:
            result = await cur.fetchone()
        finally:
            cur.row_factory = current_row_factory

        return result

    async def fetchall_cur(
        self, cur: psycopg.AsyncCursor, query: str, params: list[Any]
    ) -> Any:
        domain.set(self.domain)
        await ensure_pool_opened(self.pool)
        with sentry_sdk.start_span(op="db.sql.query", description=query):
            await cur.execute(*prepare_query_statements(query, params))

        return await cur.fetchall()

    async def fetchall(
        self, query: str, params: list[Any], model: Callable | None = None
    ) -> Any:
        domain.set(self.domain)
        await ensure_pool_opened(self.pool)
        async with (
            self.pool.connection() as conn,
            conn.cursor(row_factory=class_row(model or self.model)) as cur,
        ):
            with sentry_sdk.start_span(op="db.sql.query", description=query):
                await cur.execute(*prepare_query_statements(query, params))

            return await cur.fetchall()

    async def fetch_value(self, query: str, params: list[Any]) -> Any:
        domain.set(self.domain)
        await ensure_pool_opened(self.pool)
        async with self.pool.connection() as conn, conn.cursor() as cur:
            return await self.fetch_value_cur(cur, query, params)

    async def fetch_value_cur(
        self, cur: psycopg.AsyncCursor, query: str, params: list[Any]
    ) -> Any:
        domain.set(self.domain)
        await ensure_pool_opened(self.pool)
        with sentry_sdk.start_span(op="db.sql.query", description=query):
            await cur.execute(*prepare_query_statements(query, params))

        result = await cur.fetchone()
        return result[0] if result else None


class InvalidQueryError(ValueError):
    pass


class OrAndNotSupportedError(ValueError):
    def __init__(self) -> None:
        super().__init__("AND {field} OR is not supported, use brackets to group ORs")


def find_all_or_filters(data: str) -> list[str]:
    if re.findall(r"\sAND\s+\{(\w+)\}\s+OR\s", data, flags=re.IGNORECASE):
        raise OrAndNotSupportedError

    groups = re.findall(
        r"\{(\w+)\}\s+OR\s+\{(\w+)\}(\s+OR\s+\{(\w+)\})?", data, flags=re.IGNORECASE
    )

    result = []
    grouped_result = []

    for group_index in range(len(groups)):
        group = groups[group_index]
        group_elements = [e for e in group if e]
        result.extend(group_elements)
        grouped_result.append(group_elements)

    return result, grouped_result


def prepare_query_statements(query: str, params: list[Any]) -> tuple[str, tuple]:
    """Prepare query and params for psycopg.execute() method.

    Function iterates over all provided params, replaces
    instances of FieldStatement with rendered params and
    and then performs substitution of rendered query parts into
    the original query string.

    Example:

    >>> query = 'SELECT * FROM t WHERE {name} AND {description}'
    >>> params = [
        Filter("name", "name=%s", "test"),
        Filter("description", "description=%s", "test")
    ]
    >>> prepare_query_statements(query, params)
    ("SELECT * FROM t WHERE name=%s AND description=%s", ("test", "test"))

    """
    format_kwargs = {}
    effective_params = []

    all_matches, grouped_matches = find_all_or_filters(query)
    or_filters_names = set(all_matches)
    or_filters = {}

    for p in params:
        if isinstance(p, FieldStatement):
            if isinstance(p, Filter) and p.name in or_filters_names:
                p.or_mode()
                or_filters[p.name] = p

            format_kwargs[p.name] = p.rendered_query
            if "%s" in p.rendered_query:
                effective_params.extend(p.rendered_params)

            continue

        effective_params.append(p)

    for group in grouped_matches:
        found_specified = False
        group_filters = {f for f in group if f in or_filters}

        for filter_name in group_filters:
            if or_filters[filter_name].is_specified:
                found_specified = True
                break

        if found_specified:
            continue

        for filter_name in group_filters:
            or_filters[filter_name].and_mode()
            format_kwargs[filter_name] = or_filters[filter_name].rendered_query

    return query.format(**format_kwargs), tuple(effective_params)


class FieldStatement:
    def __init__(
        self,
        name: str,
        query: str,
        param: Any,
        not_specified_query: str | None = None,
    ) -> None:
        self.name = name
        self.query = query
        self.param = param
        self.not_specified_query = not_specified_query

    @property
    def rendered_query(self) -> str:
        return self.query

    @property
    def rendered_params(self) -> list[Any]:
        return [self.param]

    @property
    def is_specified(self) -> bool:
        return self.param is not None


class Filter(FieldStatement):
    def __init__(self, name: str, query: str, param: Any) -> None:
        super().__init__(name, query, param, "true")

    @property
    def rendered_query(self) -> str:
        if self.is_specified:
            return self.query

        return self.not_specified_query

    def or_mode(self) -> None:
        self.not_specified_query = "false"

    def and_mode(self) -> None:
        self.not_specified_query = "true"

    @property
    def rendered_params(self) -> list[Any]:
        if self.is_specified:
            return [self.param]

        return []


class GT(Filter):
    def __init__(self, name: str, param: Any, column_name: str | None = None) -> None:
        super().__init__(name, f"{column_name or name} > %s", param)


class LT(Filter):
    def __init__(self, name: str, param: Any, column_name: str | None = None) -> None:
        super().__init__(name, f"{column_name or name} < %s", param)


class GTE(Filter):
    def __init__(self, name: str, param: Any, column_name: str | None = None) -> None:
        super().__init__(name, f"{column_name or name} >= %s", param)


class LTE(Filter):
    def __init__(self, name: str, param: Any, column_name: str | None = None) -> None:
        super().__init__(name, f"{column_name or name} <= %s", param)


class ILike(Filter):
    def __init__(self, name: str, param: Any, column_name: str | None = None) -> None:
        super().__init__(name, f"{column_name or name} ILIKE %s", param)

    @property
    def rendered_params(self) -> list[Any]:
        if self.is_specified:
            return [f"%{self.param}%"]

        return []


class OptionalValue(FieldStatement):
    def __init__(self, name: str, param: Any) -> None:
        super().__init__(name, f"{name}=%s", param)

    @property
    def rendered_query(self) -> str:
        if self.is_specified:
            return self.query

        return f"{self.name}={self.name}"

    @property
    def rendered_params(self) -> list[Any]:
        if self.is_specified:
            return [self.param]

        return []


def escape(query_word: str) -> str:
    escape_symbols = "()|&:*!"
    return re.sub(f"([{re.escape(escape_symbols)}])", r"\\\1", query_word)
