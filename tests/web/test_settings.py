"""The settings of kb serve-web: where it listens, the hosts it answers, whose header it checks, and
how it reads the data API; the check is off only on the machine, outside Azure Container Apps."""

import pytest
from pydantic import SecretStr
from site_client import OPERATOR_ID, TEST_API_KEY

from k_b.web.settings import DataApiAccess, WebSettings, read_web_settings_or_refusal

# The key of the client WEB, which kb serve-web needs whatever its access.
DATA_API_KEY = {"KB_DATA_API_KEY_WEB": TEST_API_KEY}
DEFAULT_DATA_API = DataApiAccess(
    base_url="http://127.0.0.1:8000", api_key=SecretStr(TEST_API_KEY)
)

# The address a container listens on, to be reached by the ingress.
ALL_INTERFACES = "0.0.0.0"  # noqa: S104 - a value refused or allowed, never bound by a test


def test_the_defaults_listen_on_the_machine_and_check_the_operator():
    assert read_web_settings_or_refusal(
        {"KB_WEB_OPERATOR_ID": OPERATOR_ID, **DATA_API_KEY}
    ) == WebSettings(
        host="127.0.0.1",
        port=8002,
        allowed_hosts=("127.0.0.1", "localhost"),
        operator_id=OPERATOR_ID,
        data_api=DEFAULT_DATA_API,
        version=None,
    )


def test_the_object_id_is_kept_in_lowercase():
    settings = read_web_settings_or_refusal(
        {"KB_WEB_OPERATOR_ID": OPERATOR_ID.upper(), **DATA_API_KEY}
    )

    assert isinstance(settings, WebSettings)
    assert settings.operator_id == OPERATOR_ID


def test_off_on_the_machine_checks_no_header():
    settings = read_web_settings_or_refusal({"KB_WEB_AUTH": "off", **DATA_API_KEY})

    assert isinstance(settings, WebSettings)
    assert settings.operator_id is None


def test_the_check_on_every_address_in_azure_container_apps():
    settings = read_web_settings_or_refusal(
        {
            "KB_WEB_OPERATOR_ID": OPERATOR_ID,
            "KB_WEB_HOST": ALL_INTERFACES,
            "KB_WEB_PORT": "8080",
            "KB_WEB_ALLOWED_HOSTS": "ca-kb-web.example.azurecontainerapps.io,10.0.0.4",
            "CONTAINER_APP_NAME": "ca-kb-web",
            "KB_DATA_API_URL": "https://ca-kb-data-api.internal.example.azurecontainerapps.io",
            "KB_VERSION": "v0.1.9",
            **DATA_API_KEY,
        }
    )

    assert settings == WebSettings(
        host=ALL_INTERFACES,
        port=8080,
        allowed_hosts=("ca-kb-web.example.azurecontainerapps.io", "10.0.0.4"),
        operator_id=OPERATOR_ID,
        data_api=DataApiAccess(
            base_url="https://ca-kb-data-api.internal.example.azurecontainerapps.io",
            api_key=SecretStr(TEST_API_KEY),
        ),
        version="v0.1.9",
    )


def test_an_empty_version_is_no_version():
    """The image built without the argument of deploy.yml (image.yml, compose.yaml, by hand) has
    KB_VERSION set, empty."""
    settings = read_web_settings_or_refusal(
        {"KB_WEB_AUTH": "off", "KB_VERSION": "", **DATA_API_KEY}
    )

    assert isinstance(settings, WebSettings)
    assert settings.version is None


@pytest.mark.parametrize("version", ["v0.0.0", "v10.20.30"])
def test_a_version_tag_of_deploy_yml_is_kept(version):
    settings = read_web_settings_or_refusal(
        {"KB_WEB_AUTH": "off", "KB_VERSION": version, **DATA_API_KEY}
    )

    assert isinstance(settings, WebSettings)
    assert settings.version == version


# A digit of full width: \d would take it, [0-9] does not.
FULL_WIDTH_ZERO = chr(0xFF10)


@pytest.mark.parametrize(
    "version",
    [
        "0.1.9",
        "v0.1",
        "v01.1.9",
        "v0.01.9",
        "v0.1.09",
        "v0.1.9-rc.1",
        "v0.1.9\n",
        " v0.1.9",
        f"v{FULL_WIDTH_ZERO}.1.9",
    ],
)
def test_a_version_that_is_not_a_tag_of_deploy_yml_is_refused_quoted(version):
    assert read_web_settings_or_refusal(
        {"KB_WEB_AUTH": "off", "KB_VERSION": version, **DATA_API_KEY}
    ) == (f"KB_VERSION: {version!r} not a version tag vMAJOR.MINOR.PATCH")


@pytest.mark.parametrize(
    ("environ", "refusal"),
    [
        (
            {"KB_WEB_AUTH": "none"},
            "KB_WEB_AUTH: 'none' neither entra nor off",
        ),
        ({}, "KB_WEB_OPERATOR_ID: not set"),
        ({"KB_WEB_OPERATOR_ID": ""}, "KB_WEB_OPERATOR_ID: not set"),
        (
            {"KB_WEB_OPERATOR_ID": f"{{{OPERATOR_ID}}}"},
            "KB_WEB_OPERATOR_ID: not a GUID",
        ),
        (
            {"KB_WEB_OPERATOR_ID": OPERATOR_ID, "KB_WEB_HOST": ALL_INTERFACES},
            (
                "KB_WEB_HOST: '0.0.0.0' not a loopback address outside Azure Container Apps"
                " (CONTAINER_APP_NAME not set): any device of the network could send the"
                " header of the operator"
            ),
        ),
        (
            {"KB_WEB_AUTH": "off", "KB_WEB_HOST": ALL_INTERFACES},
            "KB_WEB_AUTH: off with KB_WEB_HOST '0.0.0.0', not a loopback address",
        ),
        (
            {"KB_WEB_AUTH": "off", "CONTAINER_APP_NAME": "ca-kb-web"},
            "KB_WEB_AUTH: off in Azure Container Apps (CONTAINER_APP_NAME set)",
        ),
        (
            {"KB_WEB_AUTH": "off", "KB_WEB_HOST": "localhost"},
            "KB_WEB_HOST: 'localhost' not an IPv4 address",
        ),
        (
            {"KB_WEB_AUTH": "off", "KB_WEB_PORT": "+8002"},
            "KB_WEB_PORT: '+8002' not an integer from 1 to 65535",
        ),
        (
            {"KB_WEB_AUTH": "off", "KB_WEB_ALLOWED_HOSTS": " "},
            "KB_WEB_ALLOWED_HOSTS: empty, set the hosts separated by commas",
        ),
        (
            {"KB_WEB_AUTH": "off", "KB_WEB_ALLOWED_HOSTS": "localhost,*.example.org"},
            "KB_WEB_ALLOWED_HOSTS: entry 2 of 2 '*.example.org' with '*', name each host",
        ),
    ],
)
def test_a_setting_refused_says_why(environ, refusal):
    assert read_web_settings_or_refusal(environ) == refusal


def test_an_object_id_refused_is_never_quoted():
    refusal = read_web_settings_or_refusal(
        {"KB_WEB_OPERATOR_ID": f"urn:uuid:{OPERATOR_ID}"}
    )

    assert isinstance(refusal, str)
    assert OPERATOR_ID not in refusal


@pytest.mark.parametrize(
    ("environ", "refusal"),
    [
        ({}, "KB_DATA_API_KEY_WEB: not set"),
        ({"KB_DATA_API_KEY_WEB": ""}, "KB_DATA_API_KEY_WEB: not set"),
        (
            {"KB_DATA_API_KEY_WEB": "short"},
            "'KB_DATA_API_KEY_WEB': key of 5 characters, minimum 32",
        ),
        (
            {"KB_DATA_API_KEY_WEB": "a" * 31 + " "},
            "'KB_DATA_API_KEY_WEB': key with a character outside [A-Za-z0-9_-]",
        ),
        (
            {**DATA_API_KEY, "KB_DATA_API_URL": "http://ca-kb-data-api.internal"},
            (
                "KB_DATA_API_URL: https required; http only to the machine (127.0.0.1 or"
                " localhost) or, in the sandbox, a compose service (api-donnees or api-ia)"
            ),
        ),
        (
            {**DATA_API_KEY, "KB_DATA_API_URL": "https://user:key@example.org"},
            "KB_DATA_API_URL: with user information",
        ),
    ],
    ids=["absent", "empty", "short", "space", "http-out-of-the-machine", "user"],
)
def test_the_access_to_the_data_api_is_refused_never_quoting_the_key_nor_the_url(
    environ, refusal
):
    result = read_web_settings_or_refusal({"KB_WEB_AUTH": "off", **environ})

    assert result == refusal
    assert "short" not in result
    assert "key@" not in result


def test_an_empty_url_of_the_data_api_is_its_default():
    settings = read_web_settings_or_refusal(
        {"KB_WEB_AUTH": "off", "KB_DATA_API_URL": "", **DATA_API_KEY}
    )

    assert isinstance(settings, WebSettings)
    assert settings.data_api == DEFAULT_DATA_API


def test_the_key_is_never_shown_by_the_settings():
    settings = read_web_settings_or_refusal({"KB_WEB_AUTH": "off", **DATA_API_KEY})

    assert TEST_API_KEY not in repr(settings)
