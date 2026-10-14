"""The versioned OpenAPI of the data API (docs/api/openapi-donnees.json): the one the app
produces, and valid."""

import json
from pathlib import Path

from openapi_spec_validator import OpenAPIV31SpecValidator

from k_b.data_api.app import create_app

OPENAPI_PATH = Path(__file__).parents[2] / "docs" / "api" / "openapi-donnees.json"


def read_versioned_openapi():
    return json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))


def test_the_versioned_openapi_is_the_one_the_app_produces(tmp_path):
    produced = create_app(tmp_path / "k-b.sqlite", {}).openapi()

    # Through JSON, as kb openapi writes it: a tuple of the schema becomes a list.
    assert read_versioned_openapi() == json.loads(json.dumps(produced))


def test_the_versioned_openapi_is_valid_and_declares_its_security_scheme():
    openapi = read_versioned_openapi()

    OpenAPIV31SpecValidator(openapi).validate()
    assert openapi["info"]["version"] == "0.1.0"
    assert openapi["components"]["securitySchemes"] == {
        "HTTPBearer": {"type": "http", "scheme": "bearer"}
    }
    assert openapi["paths"]["/items"]["get"]["security"] == [{"HTTPBearer": []}]
