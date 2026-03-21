"""Role-based access (backend-ready; replace with JWT + IdP in production)."""

from __future__ import annotations

from enum import Enum

from fastapi import Header, HTTPException


class Role(str, Enum):
    staff = "staff"
    manager = "manager"
    admin = "admin"


def role_dependency(allowed: set[Role]):
    async def _dep(x_role: str | None = Header(default=None, alias="X-Role")) -> Role:
        if not x_role:
            raise HTTPException(status_code=401, detail="Missing X-Role header")
        try:
            role = Role(x_role.lower())
        except ValueError:
            raise HTTPException(status_code=403, detail="Invalid role")
        if role not in allowed:
            raise HTTPException(status_code=403, detail="Role not permitted for this endpoint")
        return role

    return _dep
