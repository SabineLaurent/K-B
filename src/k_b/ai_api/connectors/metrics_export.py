"""The export of the metrics of the AI API in OpenTelemetry to an OTLP endpoint: its settings and
the meter provider; without endpoint and headers, nothing leaves.

No OTEL_* variable is accepted: the SDK reads the environment behind its caller, the headers too,
and logs a malformed one as it is."""

import logging
import re
import uuid
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
    MILLISECONDS_PER_SECOND,
)
from k_b.core.outbound import find_url_refusal
from k_b.core.quoting import quote_value

# The logs of the exporter and of the reader that calls it: their failures quote the reason phrase
# of the endpoint, the text of an exception or its traceback, which may hold a CR or a control
# character. By the module of each class: the reader lives in a private module of the SDK.
EXPORTER_LOGGERS = (
    logging.getLogger(OTLPMetricExporter.__module__),
    logging.getLogger(PeriodicExportingMetricReader.__module__),
)

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
    """The settings of the export, None without its endpoint and its headers, or why a variable
    is refused, never quoting the headers nor the endpoint."""
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
    # The URL of the metrics given in place of the base: K-B would add the path a second time.
    if endpoint.rstrip("/").casefold().endswith(METRICS_PATH):
        return f"{ENDPOINT_VARIABLE}: ends with {METRICS_PATH}, give the base URL"
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
        endpoint=endpoint.rstrip("/") + METRICS_PATH,
        headers=headers,
        environment=environment,
    )


def parse_headers(text: str) -> dict[str, SecretStr] | None:
    """The headers of the OTLP format, `name=value,name=value`, each value percent-decoded; None
    if a pair is not read."""
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
    """The service and its environment, nothing else: not Resource.create, which reads OTEL_* and
    its detectors (process.command_args). service.instance.id is drawn for each process, so that
    two processes never write the same cumulative series."""
    attributes: dict[str, str] = {
        "service.name": SERVICE_NAME,
        "service.instance.id": str(uuid.uuid4()),
    }
    if environment is not None:
        attributes["deployment.environment.name"] = environment
    return Resource(attributes)


def build_meter_provider(settings: MetricsExportSettings | None) -> MeterProvider:
    """The provider of the meters, with a reader if the export is on; the caller shuts it down
    (no atexit, which would log once the handlers of kb are removed)."""
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


class QuotingFilter(logging.Filter):
    """The values of a line of the exporter quoted as K-B quotes them (conventions.md, rule 3),
    the line kept."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(quote_argument(argument) for argument in record.args)
        elif isinstance(record.args, Mapping):
            record.args = {
                name: quote_argument(argument) for name, argument in record.args.items()
            }
        if record.exc_info:
            _, error, _ = record.exc_info
            if error is not None:
                record.msg = f"{record.msg} ({type(error).__name__})"
            record.exc_info = None
            record.exc_text = None
        return True


def quote_argument(argument: object) -> object:
    if isinstance(argument, BaseException):
        return type(argument).__name__
    if isinstance(argument, str):
        return quote_value(argument)
    return argument


QUOTING_FILTER = QuotingFilter()


def build_exporter(settings: MetricsExportSettings) -> OTLPMetricExporter:
    """The OTLP exporter over HTTP, with a session that reads neither a proxy, a certificate nor
    a .netrc of the environment."""
    # On the loggers themselves: a filter on the logger "opentelemetry" does not see the lines of
    # its children.
    for logger in EXPORTER_LOGGERS:
        if QUOTING_FILTER not in logger.filters:
            logger.addFilter(QUOTING_FILTER)
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
