"""Role-to-scope policy for the Module 5 control plane."""

from collections.abc import Iterable
from typing import Literal

StreamingScope = Literal[
    "stream:create",
    "stream:read",
    "stream:write",
    "stream:control",
    "stream:admin",
    "stream:publish",
    "stream:emergency-stop",
    "channel:manage",
    "channel:read-operations",
    "recording:read",
    "recording:manage",
    "stream-key:manage",
    "distribution:read",
    "distribution:write",
    "geofence:admin",
]

ALL_SCOPES: frozenset[StreamingScope] = frozenset(
    {
        "stream:create",
        "stream:read",
        "stream:write",
        "stream:control",
        "stream:admin",
        "stream:publish",
        "stream:emergency-stop",
        "channel:manage",
        "channel:read-operations",
        "recording:read",
        "recording:manage",
        "stream-key:manage",
        "distribution:read",
        "distribution:write",
        "geofence:admin",
    }
)

ROLE_SCOPES: dict[str, frozenset[StreamingScope]] = {
    "admin": ALL_SCOPES,
    "chief_editor": frozenset(
        {
            "stream:create",
            "stream:read",
            "stream:write",
            "stream:control",
            "stream:publish",
            "stream:emergency-stop",
            "channel:manage",
            "channel:read-operations",
            "recording:read",
            "recording:manage",
            "stream-key:manage",
            "distribution:read",
            "distribution:write",
            "geofence:admin",
        }
    ),
    "producer": frozenset(
        {
            "stream:create",
            "stream:read",
            "stream:write",
            "stream:control",
            "stream:publish",
            "channel:manage",
            "channel:read-operations",
            "recording:read",
            "recording:manage",
            "stream-key:manage",
            "distribution:read",
            "distribution:write",
        }
    ),
    "operator": frozenset(
        {
            "stream:read",
            "stream:control",
            "channel:read-operations",
        }
    ),
    "editor": frozenset({"stream:read", "channel:read-operations", "recording:read", "distribution:read"}),
    "fact_checker": frozenset({"stream:read", "recording:read"}),
    "legal_reviewer": frozenset({"stream:read", "recording:read", "distribution:read"}),
    "reporter": frozenset({"stream:read", "recording:read"}),
    "viewer": frozenset({"stream:read", "recording:read"}),
}


def scopes_for_roles(roles: Iterable[str]) -> frozenset[StreamingScope]:
    scopes: set[StreamingScope] = set()
    for role in roles:
        scopes.update(ROLE_SCOPES.get(role, frozenset()))
    return frozenset(scopes)


def has_scope(*, roles: Iterable[str], required_scope: StreamingScope) -> bool:
    return required_scope in scopes_for_roles(roles)
