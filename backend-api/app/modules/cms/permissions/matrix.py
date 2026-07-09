"""CMS RBAC role and scope matrix."""

from collections.abc import Iterable
from typing import Literal

CMSRole = Literal["admin", "chief_editor", "editor", "fact_checker", "reporter", "viewer"]
CMSScope = Literal["system:*", "asset:write", "asset:approve", "asset:fact-check", "asset:read-draft", "asset:read"]

ROLE_SCOPES: dict[str, frozenset[CMSScope]] = {
    "admin": frozenset({"system:*", "asset:write", "asset:approve", "asset:fact-check", "asset:read-draft", "asset:read"}),
    "chief_editor": frozenset({"asset:write", "asset:approve", "asset:read-draft", "asset:read"}),
    "editor": frozenset({"asset:write", "asset:read-draft", "asset:read"}),
    "fact_checker": frozenset({"asset:fact-check", "asset:read-draft", "asset:read"}),
    "reporter": frozenset({"asset:write", "asset:read-draft", "asset:read"}),
    "viewer": frozenset({"asset:read"}),
}


def scopes_for_roles(roles: Iterable[str]) -> frozenset[CMSScope]:
    scopes: set[CMSScope] = set()
    for role in roles:
        role_scopes = ROLE_SCOPES.get(role)
        if role_scopes is not None:
            scopes.update(role_scopes)
    return frozenset(scopes)


def has_scope(*, roles: Iterable[str], required_scope: CMSScope) -> bool:
    return required_scope in scopes_for_roles(roles)


class CMSPermissionChecker:
    """Default CMS permission checker."""

    def has_scope(self, *, roles: Iterable[str], required_scope: CMSScope) -> bool:
        return has_scope(roles=roles, required_scope=required_scope)
