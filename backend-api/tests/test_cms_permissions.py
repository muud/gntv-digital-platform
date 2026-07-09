from app.modules.cms.permissions import CMSPermissionChecker, ROLE_SCOPES, has_scope, scopes_for_roles


def test_admin_has_all_cms_scopes() -> None:
    assert ROLE_SCOPES["admin"] == frozenset(
        {
            "system:*",
            "asset:write",
            "asset:approve",
            "asset:fact-check",
            "asset:read-draft",
            "asset:read",
            "content:write",
            "content:approve",
            "content:publish",
            "content:read-draft",
            "content:read",
        }
    )


def test_editor_can_write_but_not_approve_or_fact_check() -> None:
    assert has_scope(roles=["editor"], required_scope="asset:write") is True
    assert has_scope(roles=["editor"], required_scope="asset:approve") is False
    assert has_scope(roles=["editor"], required_scope="asset:fact-check") is False


def test_fact_checker_can_fact_check_but_not_write() -> None:
    assert has_scope(roles=["fact_checker"], required_scope="asset:fact-check") is True
    assert has_scope(roles=["fact_checker"], required_scope="asset:write") is False


def test_viewer_can_only_read_published_feed() -> None:
    assert has_scope(roles=["viewer"], required_scope="asset:read") is True
    assert has_scope(roles=["viewer"], required_scope="asset:read-draft") is False


def test_multiple_roles_union_scopes() -> None:
    scopes = scopes_for_roles(["viewer", "fact_checker"])

    assert "asset:read" in scopes
    assert "asset:fact-check" in scopes
    assert "asset:write" not in scopes


def test_permission_checker_uses_matrix() -> None:
    checker = CMSPermissionChecker()

    assert checker.has_scope(roles=["chief_editor"], required_scope="asset:approve") is True
    assert checker.has_scope(roles=["reporter"], required_scope="asset:approve") is False
