"""Role-based authorization scaffolding.

`require_role` is a dependency factory: `Depends(require_role(Role.MANAGER))`
on a route will (once auth is wired) reject users without that role.
It currently depends on `get_current_user`, which raises
`NotImplementedError` until Person D implements real authentication —
this is intentional so unauthenticated access fails closed, not open.
"""

from collections.abc import Callable
from enum import Enum

from fastapi import Depends

from app.api.deps import get_current_user
from app.core.exceptions import PermissionDeniedError


class Role(str, Enum):
    ENGINEER = "engineer"
    MANAGER = "manager"


def require_role(role: Role) -> Callable[..., dict[str, str]]:
    def dependency(user: dict[str, str] = Depends(get_current_user)) -> dict[str, str]:
        if user.get("role") != role.value:
            raise PermissionDeniedError(f"Requires role '{role.value}'")
        return user

    return dependency
