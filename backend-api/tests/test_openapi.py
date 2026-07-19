from collections.abc import Hashable, Mapping
from typing import Any, cast

from openapi_spec_validator import validate_spec

from app.main import app


def test_openapi_document_is_valid() -> None:
    schema = app.openapi()
    validate_spec(cast(Mapping[Hashable, Any], schema))
    assert "/api/v1/content/catalog" in schema["paths"]
    assert "delete" in schema["paths"]["/api/v1/cms/content/{content_id}"]


def test_every_editorial_operation_has_a_valid_openapi_response_schema() -> None:
    schema = app.openapi()
    validate_spec(cast(Mapping[Hashable, Any], schema))
    editorial_paths = {path: item for path, item in schema["paths"].items() if path.startswith("/api/v1/editorial")}
    assert len(editorial_paths) == 25
    assert "/api/v1/editorial/workflows/{workflow_id}/restore" in editorial_paths
    assert "/api/v1/editorial/notifications/{notification_id}" in editorial_paths

    methods = {"get", "post", "put", "patch", "delete"}
    for path, path_item in editorial_paths.items():
        for method, operation in path_item.items():
            if method not in methods:
                continue
            assert operation["tags"] == ["CMS Editorial Workflow"], f"{method.upper()} {path} missing tag"
            success_responses = [response for status, response in operation["responses"].items() if status.startswith("2")]
            assert success_responses, f"{method.upper()} {path} missing success response"
            for response in success_responses:
                content = response.get("content", {})
                if content:
                    assert "schema" in content["application/json"], f"{method.upper()} {path} missing JSON schema"
