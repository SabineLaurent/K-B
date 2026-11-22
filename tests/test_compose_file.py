"""The compose of the local preproduction keeps its rules: each rule is read in compose.yaml, its
templates, the Dockerfile and .gitignore, without Docker (the trial proves the run)."""

import re
from pathlib import Path

import pytest
import yaml

REPOSITORY_DIR = Path(__file__).parents[1]
COMPOSE_PATH = REPOSITORY_DIR / "compose.yaml"
CI_PATH = REPOSITORY_DIR / ".github" / "workflows" / "ci.yml"
DOCKERFILE_PATH = REPOSITORY_DIR / "Dockerfile"
ENV_EXAMPLE_PATH = REPOSITORY_DIR / ".env.example"
GITIGNORE_PATH = REPOSITORY_DIR / ".gitignore"

BASE_SERVICE = "postgres"
DATA_API_SERVICE = "api-donnees"
AI_API_SERVICE = "api-ia"
API_SERVICES = (DATA_API_SERVICE, AI_API_SERVICE)
JOB_SERVICES = ("create-db", "collecte", "import")
KB_SERVICES = API_SERVICES + JOB_SERVICES
SERVICES = (BASE_SERVICE, *KB_SERVICES)
# The three jobs read the same secrets: one file.
ENV_FILE_BY_SERVICE = {
    BASE_SERVICE: ".env.postgres",
    DATA_API_SERVICE: ".env.api-donnees",
    AI_API_SERVICE: ".env.api-ia",
    **dict.fromkeys(JOB_SERVICES, ".env.jobs"),
}
JOBS_PROFILE = "jobs"
DATA_DIR = "/var/lib/knowledge_base"
DATA_VOLUME = f"kb-data:{DATA_DIR}"
# A combination of Azure Container Apps, the one of the apps online
# (infra/modules/api-container-app.bicep:154-155).
CONTAINER_APP_CPUS = 0.5
CONTAINER_APP_MEMORY = "1g"
# The server of the base online, Standard_B1ms: 1 vCore, 2 GiB
# (infra/modules/postgresql-server.bicep:21).
BASE_CPUS = 1
BASE_MEMORY = "2g"
# Below the 30 s of the issue; the AI API waits as online (infra/main.bicep:337-339): the longest
# request the ingress lets through, 240 s, and a margin.
MAX_STOP_SECONDS = 30
AI_API_STOP_SECONDS = 250
ROOT_USERS = {"0", "root"}
# The AI API calls the data API in http, which only the sandbox allows (core/outbound.py); the data
# API runs as online (infra/main.bicep:296).
DEPLOYMENT_ENVIRONMENT_BY_API = {
    DATA_API_SERVICE: "production",
    AI_API_SERVICE: "sandbox",
}
# The mount point of a tmpfs in a container, not a temporary file of the tests.
TMPFS_PATH = "/tmp"  # noqa: S108
# A secret is known by its name; KB_DATABASE_URL carries the password of the base of the compose.
SECRET_NAME = re.compile(
    r"KB_DATA_API_KEY_\w+|KB_AI_API_KEY_\w+|\w+_TOKEN|KB_LLM_API_KEY|KB_OTLP_HEADERS"
    r"|KB_DATABASE_URL|POSTGRES_PASSWORD"
)
# A user and a password in a URL, whatever the name of its variable.
CREDENTIALS_IN_URL = re.compile(r"://[^/@\s]*:[^/@\s]*@")
HEALTHCHECK_HOST = re.compile(r"'Host': '([^']+)'")
# A line NAME=value of an example, set or commented out, as tests/architecture/test_environment.py
# reads it.
VARIABLE_LINE = re.compile(r"^#?[ \t]*([A-Z][A-Z0-9_]*)=", re.MULTILINE)
SET_VARIABLE_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$", re.MULTILINE)
DURATION_IN_SECONDS = re.compile(r"(\d+)s")


def read_services():
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))["services"]


def read_template(env_file):
    return (REPOSITORY_DIR / f"{env_file}.example").read_text(encoding="utf-8")


def read_image_user():
    users = [
        line.split()[1]
        for line in DOCKERFILE_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("USER ")
    ]
    assert users, DOCKERFILE_PATH
    return users[-1]


def read_seconds(duration):
    match = DURATION_IN_SECONDS.fullmatch(duration)
    assert match, duration
    return int(match.group(1))


def test_the_compose_holds_the_base_the_two_apis_and_the_three_jobs():
    assert set(read_services()) == set(SERVICES)


@pytest.mark.parametrize("service", SERVICES)
def test_a_published_port_listens_on_the_mac_only(service):
    for port in read_services()[service].get("ports", []):
        assert port.startswith("127.0.0.1:"), port


def test_the_base_publishes_no_port():
    assert "ports" not in read_services()[BASE_SERVICE]


@pytest.mark.parametrize("service", SERVICES)
def test_each_service_runs_with_an_init_on_a_read_only_file_system(service):
    settings = read_services()[service]

    assert settings["init"] is True
    assert settings["read_only"] is True
    assert TMPFS_PATH in settings["tmpfs"]


@pytest.mark.parametrize("service", KB_SERVICES)
def test_each_kb_service_has_the_resources_of_a_container_app(service):
    settings = read_services()[service]

    assert (settings["cpus"], settings["mem_limit"]) == (
        CONTAINER_APP_CPUS,
        CONTAINER_APP_MEMORY,
    )


def test_the_base_has_the_resources_of_the_server_online():
    settings = read_services()[BASE_SERVICE]

    assert (settings["cpus"], settings["mem_limit"]) == (BASE_CPUS, BASE_MEMORY)


@pytest.mark.parametrize("service", SERVICES)
def test_only_the_ai_api_waits_beyond_30_seconds_to_stop(service):
    seconds = read_seconds(read_services()[service]["stop_grace_period"])

    if service == AI_API_SERVICE:
        assert seconds == AI_API_STOP_SECONDS
    else:
        assert seconds < MAX_STOP_SECONDS


def test_no_service_runs_as_root():
    services = read_services()

    assert services[BASE_SERVICE]["user"] == "postgres"
    # The kb services keep the user of the image.
    assert all("user" not in services[service] for service in KB_SERVICES)
    assert read_image_user().split(":")[0] not in ROOT_USERS


def test_the_base_runs_the_image_and_the_settings_of_the_ci():
    ci_base = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))["jobs"][
        "tests-postgresql"
    ]["services"]["postgres"]
    base = read_services()[BASE_SERVICE]

    assert base["image"] == ci_base["image"]
    assert (
        base["environment"]["POSTGRES_INITDB_ARGS"]
        == ci_base["env"]["POSTGRES_INITDB_ARGS"]
    )


@pytest.mark.parametrize("service", SERVICES)
def test_each_service_reads_its_secrets_from_its_file_beside_its_template(service):
    env_file = ENV_FILE_BY_SERVICE[service]

    assert read_services()[service]["env_file"] == [
        {"path": env_file, "required": True}
    ]
    assert (REPOSITORY_DIR / f"{env_file}.example").is_file()


@pytest.mark.parametrize("service", SERVICES)
def test_no_secret_is_written_in_the_compose_file(service):
    environment = read_services()[service].get("environment", {})

    # A list of NAME=value would hide the names from the checks below.
    assert isinstance(environment, dict)
    assert [name for name in environment if SECRET_NAME.fullmatch(name)] == []
    assert [
        name
        for name, value in environment.items()
        if CREDENTIALS_IN_URL.search(str(value))
    ] == []


@pytest.mark.parametrize("env_file", sorted(set(ENV_FILE_BY_SERVICE.values())))
def test_a_template_holds_no_value(env_file):
    assert {
        name: value
        for name, value in SET_VARIABLE_LINE.findall(read_template(env_file))
        if value
    } == {}


@pytest.mark.parametrize(
    "env_file", sorted({ENV_FILE_BY_SERVICE[service] for service in KB_SERVICES})
)
def test_every_variable_of_a_template_of_kb_is_in_the_example(env_file):
    example_names = set(
        VARIABLE_LINE.findall(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))
    )

    assert set(VARIABLE_LINE.findall(read_template(env_file))) - example_names == set()


def test_the_template_of_the_base_holds_its_password_only():
    assert VARIABLE_LINE.findall(read_template(ENV_FILE_BY_SERVICE[BASE_SERVICE])) == [
        "POSTGRES_PASSWORD"
    ]


def test_git_ignores_the_files_of_secrets_and_follows_their_templates():
    lines = GITIGNORE_PATH.read_text(encoding="utf-8").splitlines()

    # The last pattern that matches decides: the templates come back after the files are ignored.
    assert lines.index("!.env.*.example") > lines.index(".env.*")


@pytest.mark.parametrize("service", SERVICES)
def test_only_the_jobs_wait_to_be_run(service):
    profiles = read_services()[service].get("profiles", [])

    assert profiles == ([JOBS_PROFILE] if service in JOB_SERVICES else [])


@pytest.mark.parametrize("service", KB_SERVICES)
def test_only_the_jobs_keep_the_data_directory(service):
    settings = read_services()[service]

    assert settings["environment"]["KB_DATA_DIR"] == DATA_DIR
    assert settings.get("volumes", []) == (
        [DATA_VOLUME] if service in JOB_SERVICES else []
    )


@pytest.mark.parametrize("service", API_SERVICES)
def test_an_api_is_checked_by_python(service):
    command = " ".join(read_services()[service]["healthcheck"]["test"])

    assert command.startswith("CMD python -c ")


def test_the_data_api_is_checked_with_a_host_it_allows():
    settings = read_services()[DATA_API_SERVICE]
    host = HEALTHCHECK_HOST.search(" ".join(settings["healthcheck"]["test"]))

    assert host
    assert host.group(1) in settings["environment"]["KB_DATA_API_ALLOWED_HOSTS"].split(
        ","
    )


def test_the_base_is_checked_by_pg_isready_over_tcp():
    test = read_services()[BASE_SERVICE]["healthcheck"]["test"]

    assert test[:2] == ["CMD", "pg_isready"]
    # The temporary server of the first start answers on the socket only.
    assert "--host" in test
    assert test[test.index("--host") + 1] == "127.0.0.1"


@pytest.mark.parametrize("service", API_SERVICES)
def test_only_the_ai_api_runs_in_the_sandbox(service):
    environment = read_services()[service]["environment"]

    assert (
        environment["KB_DEPLOYMENT_ENVIRONMENT"]
        == DEPLOYMENT_ENVIRONMENT_BY_API[service]
    )


@pytest.mark.parametrize(
    ("service", "dependency"),
    [
        (DATA_API_SERVICE, BASE_SERVICE),
        ("create-db", BASE_SERVICE),
        ("import", BASE_SERVICE),
        # The AI API reads the base through the data API only.
        (AI_API_SERVICE, DATA_API_SERVICE),
    ],
)
def test_a_service_waits_for_what_it_reads_to_be_healthy(service, dependency):
    assert read_services()[service]["depends_on"] == {
        dependency: {"condition": "service_healthy"}
    }
