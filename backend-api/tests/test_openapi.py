from collections.abc import Hashable, Mapping
from typing import Any, cast

from openapi_spec_validator import validate_spec

from app.main import app


def test_openapi_document_is_valid() -> None:
    schema = app.openapi()
    validate_spec(cast(Mapping[Hashable, Any], schema))
    assert "/api/v1/content/catalog" in schema["paths"]
    assert "delete" in schema["paths"]["/api/v1/cms/content/{content_id}"]
