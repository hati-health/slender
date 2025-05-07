# SlenderQL
SlenderQL - Missing library for working with raw SQL in Python/psycopg

[![PyPI version](https://img.shields.io/pypi/v/slenderql.svg)](https://pypi.org/project/slenderql/)

<img align="left" width="440" height="180" alt="Missing raw SQL tooling for python" src="https://github.com/user-attachments/assets/7f714119-e764-4427-b1b4-43051ead4a17" />

- No ORM, no magic, just SQL, but with a few helpers
- Optimizes work with multiple filters in SELECTs or optional values in UPDATEs
- Uses only python syntax, so highlighted by default in IDEs

### Usage

```python

from slenderql.repository import Filter, ILike
from pydantic import BaseModel


class User(BaseModel):
    name: str
    email: str
    age: int


class UserRepository(BaseRepository):
    model = User

    async def all(self, query: str | None = None, email: str | None = None) -> list[User]:
        return await self.fetchall(
            """
            SELECT * FROM users
            WHERE {query} AND {email}
            """,
            (
                ILike("name", query),
                Filter("email", "email = %s", email),
            )
        )
```
