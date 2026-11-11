"""The settings of kb serve-web: where it listens, the hosts it answers, and whose header it checks;
the check is off only on the machine, outside Azure Container Apps."""

import pytest
from site_client import OPERATOR_ID

from k_b.web.settings import WebSettings, read_web_settings_or_refusal

# The address a container listens on, to be reached by the ingress.
ALL_INTERFACES = "0.0.0.0"  # noqa: S104 - a value refused or allowed, never bound by a test


def test_the_defaults_listen_on_the_machine_and_check_the_operator():
    assert read_web_settings_or_refusal(
        {"KB_WEB_OPERATOR_ID": OPERATOR_ID}
    ) == WebSettings(
        host="127.0.0.1",
        port=8002,
        allowed_hosts=("127.0.0.1", "localhost"),
        operator_id=OPERATOR_ID,
    )


def test_the_object_id_is_kept_in_lowercase():
    settings = read_web_settings_or_refusal({"KB_WEB_OPERATOR_ID": OPERATOR_ID.upper()})

    assert isinstance(settings, WebSettings)
    assert settings.operator_id == OPERATOR_ID


def test_off_on_the_machine_checks_no_header():
    settings = read_web_settings_or_refusal({"KB_WEB_AUTH": "off"})

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
        }
    )

    assert settings == WebSettings(
        host=ALL_INTERFACES,
        port=8080,
        allowed_hosts=("ca-kb-web.example.azurecontainerapps.io", "10.0.0.4"),
        operator_id=OPERATOR_ID,
    )


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
