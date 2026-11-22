from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    role: str
    name: str | None = None
    rank: str | None = None


class CurrentUserResponse(BaseModel):
    id: str
    email: str
    role: str
    name: str | None = None
    rank: str | None = None
