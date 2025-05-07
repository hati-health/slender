import pytest
from pydantic import BaseModel

from slenderql.db import DB
from slenderql.repository import (
    GT,
    GTE,
    LT,
    LTE,
    BaseRepository,
    FieldStatement,
    Filter,
    ILike,
    OptionalValue,
    OrAndNotSupportedError,
    prepare_query_statements,
)


class SampleModel(BaseModel):
    sample_id: int
    name: str
    description: str | None


class SampleModelManager(BaseRepository):
    model = SampleModel

    async def get(self, sample_id: int) -> SampleModel:
        return await self.fetchone(
            "SELECT * FROM samples WHERE sample_id = %s", (sample_id,)
        )

    async def get_all(
        self, search: str | None = None, gt_id: int | None = None
    ) -> list[SampleModel]:
        return await self.fetchall(
            """
            SELECT *
            FROM samples
            WHERE
                {name} OR {description} OR {gt_id}
            """,
            (
                ILike("name", search),
                ILike("description", search),
                Filter("gt_id", "sample_id > %s", gt_id),
            ),
        )

    async def create(self, name: str) -> SampleModel:
        return await self.fetchone(
            "INSERT INTO samples (name) VALUES (%s) RETURNING *", (name,)
        )

    async def patch(self, sample_id: int, sample: dict[str, str]) -> SampleModel:
        return await self.fetchone(
            """
            UPDATE samples
            SET
                {name},
                {description}
            WHERE sample_id = %s
            RETURNING *
            """,
            (
                OptionalValue("name", sample.get("name")),
                OptionalValue("description", sample.get("description")),
                sample_id,
            ),
        )

    async def count(self) -> int:
        return await self.fetch_value("SELECT COUNT(*) FROM samples", ())


# using fixture db which creates table samples. With type annotations
class TestBaseManager:
    async def test_fetchone(self, db: DB) -> None:
        manager = SampleModelManager(db.pool, "test.sample")
        sample = await manager.create("test")
        assert await manager.get(sample.sample_id) == sample

    async def test_fetchall(self, db: DB) -> None:
        manager = SampleModelManager(db.pool, "test.sample")
        samples = await manager.get_all()
        assert len(samples) == 0

        await manager.create("test")
        samples = await manager.get_all()
        assert len(samples) == 1
        assert samples[0].name == "test"

    async def test_fetch_value(self, db: DB) -> None:
        manager = SampleModelManager(db.pool, "test.sample")
        await manager.create("test")
        assert await manager.count() == 1

    async def test_patch(self, db: DB) -> None:
        manager = SampleModelManager(db.pool, "test.sample")
        sample = await manager.create("test")
        assert sample.description is None

        sample = await manager.patch(
            sample.sample_id, {"description": "test description"}
        )
        assert sample.description == "test description"
        assert sample.name == "test"

    async def test_search(self, db: DB) -> None:
        manager = SampleModelManager(db.pool, "test.sample")
        await manager.create("test")
        await manager.create("another test")
        await manager.create("test")

        samples = await manager.get_all("test")
        assert len(samples) == 3

        samples = await manager.get_all("another")
        assert len(samples) == 1

        samples = await manager.get_all("not exists")
        assert len(samples) == 0

    async def test_filter(self, db: DB) -> None:
        manager = SampleModelManager(db.pool, "test.sample")
        s1 = await manager.create("test")
        s2 = await manager.create("another test")
        s3 = await manager.create("test")

        ids = sorted([s1.sample_id, s2.sample_id, s3.sample_id])

        samples = await manager.get_all(gt_id=ids[0])
        assert len(samples) == 2

        samples = await manager.get_all(gt_id=ids[1])
        assert len(samples) == 1

        samples = await manager.get_all(gt_id=ids[2])
        assert len(samples) == 0

    async def test_base_statement_does_nothing(self) -> None:
        s = FieldStatement("name", "query", "test")
        assert s.rendered_query == "query"
        assert s.rendered_params == ["test"]
        assert s.is_specified is True

    async def test_or_and_not_supported(self, db: DB) -> None:
        manager = SampleModelManager(db.pool, "test.sample")

        with pytest.raises(OrAndNotSupportedError):
            await manager.fetchall(
                """
                SELECT *
                FROM samples
                WHERE
                    {name} AND {description} OR {gt_id}
                """,
                (
                    ILike("name", "test"),
                    ILike("description", "test"),
                    Filter("gt_id", "sample_id > %s", 1),
                ),
            )


class TestAdvancedFiltering:
    def test_ilike(self) -> None:
        ilike = ILike("name", "test")
        assert ilike.rendered_query == "name ILIKE %s"
        assert ilike.rendered_params == ["%test%"]

    def test_ilike_none_case(self) -> None:
        ilike = ILike("name", None)
        assert ilike.rendered_query == "true"
        assert ilike.rendered_params == []

    def test_optional_value(self) -> None:
        optional = OptionalValue("name", "test")
        assert optional.rendered_query == "name=%s"
        assert optional.rendered_params == ["test"]

        optional = OptionalValue("name", None)
        assert optional.rendered_query == "name=name"
        assert optional.rendered_params == []

    def test_gt_lt(self) -> None:
        gt = GT("id", 1)
        assert gt.rendered_query == "id > %s"
        assert gt.rendered_params == [1]

        lt = LT("id", 1)
        assert lt.rendered_query == "id < %s"
        assert lt.rendered_params == [1]

        gte = GTE("id", 1)
        assert gte.rendered_query == "id >= %s"
        assert gte.rendered_params == [1]

        lte = LTE("id", 1)
        assert lte.rendered_query == "id <= %s"
        assert lte.rendered_params == [1]

        gt = GT("id", None)
        assert gt.rendered_query == "true"
        assert gt.rendered_params == []

        lt = LT("id", None)
        assert lt.rendered_query == "true"
        assert lt.rendered_params == []

        gte = GTE("id", None)
        assert gte.rendered_query == "true"
        assert gte.rendered_params == []

        lte = LTE("id", None)
        assert lte.rendered_query == "true"
        assert lte.rendered_params == []


class TestPrepareQuery:
    def test_filters(self) -> None:
        query = "SELECT * FROM table WHERE {name} OR {description} OR {gt_id}"
        params = (
            ILike("name", "test"),
            ILike("description", "test"),
            Filter("gt_id", "sample_id > %s", 1),
        )

        assert prepare_query_statements(query, params) == (
            (
                "SELECT * FROM table WHERE name ILIKE %s OR"
                " description ILIKE %s OR sample_id > %s"
            ),
            ("%test%", "%test%", 1),
        )

    def test_some_filters_absent(self) -> None:
        query = "SELECT * FROM table WHERE {name} OR {description} OR {gt_id}"
        params = (
            ILike("name", None),
            ILike("description", None),
            Filter("gt_id", "sample_id > %s", 1),
        )

        assert prepare_query_statements(query, params) == (
            "SELECT * FROM table WHERE false OR false OR sample_id > %s",
            (1,),
        )

    def test_no_filters(self) -> None:
        query = "SELECT * FROM table WHERE {name} OR {description} OR {gt_id}"
        params = (
            ILike("name", None),
            ILike("description", None),
            Filter("gt_id", "sample_id > %s", None),
        )

        assert prepare_query_statements(query, params) == (
            "SELECT * FROM table WHERE true OR true OR true",
            (),
        )

    def test_two_or_groups(self) -> None:
        query = """
            SELECT * FROM table WHERE
                ({name} OR {description})
                AND ({gt_id} OR {lt_id})
            """
        params = (
            ILike("name", None),
            ILike("description", None),
            Filter("gt_id", "sample_id > %s", 1),
            Filter("lt_id", "sample_id < %s", 3),
        )

        assert prepare_query_statements(query, params) == (
            """
            SELECT * FROM table WHERE
                (true OR true)
                AND (sample_id > %s OR sample_id < %s)
            """,
            (1, 3),
        )

    def test_lots_of_ors(self) -> None:
        query = """
            SELECT *
            FROM doctor
            WHERE
                {first_name}
                OR {last_name}
                OR {email}
                OR {phone_number}
                OR {description}
            ORDER BY doctor_id
        """
        params = (
            ILike("first_name", "1312"),
            ILike("last_name", "1312"),
            ILike("email", "1312"),
            ILike("phone_number", "1312"),
            ILike("description", "1312"),
        )

        expected_query = """
            SELECT *
            FROM doctor
            WHERE
                first_name ILIKE %s
                OR last_name ILIKE %s
                OR email ILIKE %s
                OR phone_number ILIKE %s
                OR description ILIKE %s
            ORDER BY doctor_id
        """

        assert prepare_query_statements(query, params) == (
            expected_query,
            ("%1312%", "%1312%", "%1312%", "%1312%", "%1312%"),
        )
