# SlenderQL
SlenderQL - Missing library for working with raw SQL in Python/psycopg

[![PyPI version](https://img.shields.io/pypi/v/slenderql.svg)](https://pypi.org/project/slenderql/)

<img align="left" width="440" height="142" alt="Missing raw SQL tooling for python" src="https://github.com/user-attachments/assets/96a58417-a655-444c-bc99-bf2f60f2ae81" />

- 💯 No ORM, no magic, just SQL
- 🎨 Highlighted by default in IDEs
- 🏜️ DRY you queries, without losing control

<br>
<br>

## Installation

```bash
pip install SlenderQL
```

or
```bash
uv add SlenderQL
```

## Usage

```python

from slenderql.repository import Filter, ILike, GTE, LT, BaseRepository, DB
from pydantic import BaseModel
from datetime import datetime


class User(BaseModel):
    name: str
    email: str
    joined_at: datetime


class UserRepository(BaseRepository):
    model = User

    async def all(
        self,
        query: str | None = None,
        after: datetime | None = None,
        before: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        return await self.fetchall(
            """
            SELECT * FROM users
            WHERE ({name} OR {email})
                AND {after}
                AND {before}
            ORDER BY joined_at DESC
            LIMIT %s OFFSET %s
            """,
            (
                ILike("name", query),
                ILike("email", query),
                GTE("after", after, "joined_at"),
                LT("before", before, "joined_at"),
                limit,
                offset,
            )
        )


class RepostoryManager(DB):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.users = UserRepository(self)


db = RepostoryManager(
    f"user=postgres "
    f"password=postgres "
    f"host=postgres "
    f"dbname=postgres"
)

users = await db.users.all(query="alex")
```
