"""The export of the metrics of the AI API in OpenTelemetry, to an OTLP endpoint (Grafana Cloud,
ADR of 2026-10-20, decision 4; #162): its settings, read from the environment, and the meter
provider. Without the endpoint and the headers, the provider has no reader: the measures are
dropped, nothing leaves.

K-B reads its own variables and gives each value to the SDK: the SDK reads the environment
behind the back of its caller, the headers too even when they are given
(opentelemetry/exporter/otlp/proto/http/_common/__init__.py, _resolve_headers, 1.45.1), and logs a
malformed one as it is. So no OTEL_* variable is accepted at all.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote

import requests
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from pydantic import SecretStr

from k_b.core.config import (
    METRICS_EXPORT_INTERVAL_SECONDS,
    METRICS_EXPORT_TIMEOUT_SECONDS,
)
from k_b.core.outbound import find_url_refusal
from k_b.core.quoting import quote_value

ENDPOINT_VARIABLE = "KB_OTLP_ENDPOINT"
HEADERS_VARIABLE = "KB_OTLP_HEADERS"
ENVIRONMENT_VARIABLE = "KB_DEPLOYMENT_ENVIRONMENT"
OPENTELEMETRY_VARIABLE_PREFIX = "OTEL_"
# The path the SDK adds to a base endpoint for the metrics.
METRICS_PATH = "/v1/metrics"
SERVICE_NAME = "k-b-ai-api"
type DeploymentEnvironment = Literal["sandbox", "production"]
DEPLOYMENT_ENVIRONMENTS: tuple[DeploymentEnvironment, ...] = ("sandbox", "production")
# A header name: a token of RFC 9110 (section 5.6.2).
HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
# A header value, once percent-decoded: words of printable ASCII, one space between two. Stricter
# than the parser of the SDK and than the check of requests, which would quote the value refused.
HEADER_VALUE = re.compile(r"[!-~]+( [!-~]+)*")
# Cumulative, as the SDK gives by default and as Grafana Cloud (Mimir) reads it; set here so that
# no variable changes it.
CUMULATIVE_TEMPORALITY: dict[type, AggregationTemporality] = {
    Counter: AggregationTemporality.CUMULATIVE,
    Histogram: AggregationTemporality.CUMULATIVE,
}
MILLISECONDS_PER_SECOND = 1000


@dataclass(frozen=True)
class MetricsExportSettings:
    # The URL of the metrics: the base endpoint and METRICS_PATH.
    endpoint: str
    # The values hold the token: never logged, never quoted.
    headers: Mapping[str, SecretStr]
    environment: DeploymentEnvironment


def read_metrics_export_settings_or_refusal(
    environ: Mapping[str, str],
) -> MetricsExportSettings | str | None:
    """The settings of the export, None without its endpoint and its headers, or why a variable is
    refused: never the headers, nor the endpoint, which a refused URL may carry a key in."""
    opentelemetry_names = sorted(
        name for name in environ if name.startswith(OPENTELEMETRY_VARIABLE_PREFIX)
    )
    if opentelemetry_names:
        return (
            f"{', '.join(opentelemetry_names)}: read by the OpenTelemetry SDK behind the back"
            f" of K-B, unset them ({ENDPOINT_VARIABLE} and {HEADERS_VARIABLE} set the export)"
        )
    # Empty is not set, as for every variable of kb.
    endpoint = environ.get(ENDPOINT_VARIABLE) or None
    headers_text = environ.get(HEADERS_VARIABLE) or None
    if endpoint is None and headers_text is None:
        return None
    if headers_text is None:
        return f"{HEADERS_VARIABLE}: not set, while {ENDPOINT_VARIABLE} is"
    if endpoint is None:
        return f"{ENDPOINT_VARIABLE}: not set, while {HEADERS_VARIABLE} is"
    refusal = find_url_refusal(ENDPOINT_VARIABLE, endpoint, ("https",))
    if refusal is not None:
        return refusal
    headers = parse_headers(headers_text)
    if headers is None:
        return (
            f"{HEADERS_VARIABLE}: not name=value pairs separated by commas, each name a"
            " token, each value printable ASCII once percent-decoded"
        )
    environment = environ.get(ENVIRONMENT_VARIABLE) or None
    if environment is None:
        return (
            f"{ENVIRONMENT_VARIABLE}: not set, {' or '.join(DEPLOYMENT_ENVIRONMENTS)}"
        )
    if environment not in DEPLOYMENT_ENVIRONMENTS:
        return (
            f"{ENVIRONMENT_VARIABLE}: {quote_value(environment)} not"
            f" {' nor '.join(DEPLOYMENT_ENVIRONMENTS)}"
        )
    return MetricsExportSettings(
        endpoint=endpoint.removesuffix("/") + METRICS_PATH,
        headers=headers,
        environment=environment,
    )


def parse_headers(text: str) -> dict[str, SecretStr] | None:
    """The headers of the OTLP format, `name=value,name=value`, each value percent-decoded (as
    Grafana Cloud gives `Authorization=Basic%20…`); None if a pair is not read."""
    headers: dict[str, SecretStr] = {}
    for pair in text.split(","):
        name, separator, encoded_value = pair.partition("=")
        try:
            value = unquote(encoded_value, errors="strict")
        except UnicodeDecodeError:
            return None
        if not (
            separator and HEADER_NAME.fullmatch(name) and HEADER_VALUE.fullmatch(value)
        ):
            return None
        headers[name] = SecretStr(value)
    return headers


def build_resource(environment: DeploymentEnvironment | None) -> Resource:
    """The service and its environment, nothing else: built by its constructor, not by
    Resource.create, which adds OTEL_RESOURCE_ATTRIBUTES, OTEL_SERVICE_NAME, a random
    service.instance.id and the detectors of OTEL_EXPERIMENTAL_RESOURCE_DETECTORS (process gives
    process.command_args and process.owner)."""
    attributes: dict[str, str] = {"service.name": SERVICE_NAME}
    if environment is not None:
        attributes["deployment.environment.name"] = environment
    return Resource(attributes)


def build_meter_provider(settings: MetricsExportSettings | None) -> MeterProvider:
    """The provider of the meters of the AI API: with a reader that exports every
    METRICS_EXPORT_INTERVAL_SECONDS, or without reader if the export is off. The caller shuts it
    down: no atexit handler, which would log once the handlers of kb are removed."""
    if settings is None:
        return MeterProvider(resource=build_resource(None), shutdown_on_exit=False)
    reader = PeriodicExportingMetricReader(
        build_exporter(settings),
        export_interval_millis=METRICS_EXPORT_INTERVAL_SECONDS
        * MILLISECONDS_PER_SECOND,
        export_timeout_millis=METRICS_EXPORT_TIMEOUT_SECONDS * MILLISECONDS_PER_SECOND,
    )
    return MeterProvider(
        metric_readers=[reader],
        resource=build_resource(settings.environment),
        shutdown_on_exit=False,
    )


def build_exporter(settings: MetricsExportSettings) -> OTLPMetricExporter:
    """The OTLP exporter over HTTP: every option given, and an HTTP session that reads neither a
    proxy, a certificate nor a .netrc of the environment (core/outbound.py). The transport of the
    SDK follows no redirection, but counts a 3xx as a success."""
    session = requests.Session()
    session.trust_env = False
    return OTLPMetricExporter(
        endpoint=settings.endpoint,
        headers={
            name: value.get_secret_value() for name, value in settings.headers.items()
        },
        timeout=METRICS_EXPORT_TIMEOUT_SECONDS,
        compression=Compression.Gzip,
        session=session,
        preferred_temporality=CUMULATIVE_TEMPORALITY,
    )
