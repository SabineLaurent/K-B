"""The native OpenTelemetry of FastAPI (0.143), off in both APIs (#162).

On, it sends traces, HTTP metrics and the messages of the errors to the global providers; with
FASTAPI_OTEL_AUTO_CONFIGURE=true, it sets those providers itself, from the OTEL_* variables
(fastapi/telemetry/_runtime.py). A trace of the data API would carry the raw query of a request,
a name a client typed, to a recipient the register does not name. The measures of K-B go by
ModelMetrics alone (ai_api/metric_instruments.py); the traces are #281.
"""

from fastapi.telemetry import TelemetryConfig

NATIVE_TELEMETRY_OFF: TelemetryConfig = {
    "tracing": False,
    "metrics": False,
    "logs": False,
    "operation_spans": False,
    "auto_configure": False,
}
