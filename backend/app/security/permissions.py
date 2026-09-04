"""Role-based authorization scaffolding.

`require_role` is a dependency factory: `Depends(require_role(Role.MANAGER))`
on a route rejects users without that role. It depends on
`get_current_user`, which validates the caller's Supabase JWT and
raises `UnauthorizedError`/`ServiceUnavailableError` if that fails —
so an unauthenticated or misidentified caller never reaches the role
check at all; access fails closed, not open.
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
