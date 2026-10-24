"""The measures of the AI API in OpenTelemetry (#162), beside the JSON line of each call
(metrics.py): the same measures, as instruments a tool sums up and charts. The app, the router and
the commands see ModelMetrics only; OpenTelemetry is imported here and in
connectors/metrics_export.py, nowhere else.

The names follow the semantic conventions of OpenTelemetry for generative AI where they have one
(status Development, repository semantic-conventions-genai, read on 2026-10-24), under k_b.
otherwise. A measure carries closed attributes only: never a text, a title, a subject nor the id
of a request (.claude/rules/poc.md, rule 5; conventions.md, rule 3)."""

import logging
from collections.abc import Sequence

from opentelemetry.sdk.metrics import MeterProvider

from k_b.ai_api.connectors.llm_settings import LlmSettings
from k_b.ai_api.connectors.metrics_export import (
    MetricsExportSettings,
    build_meter_provider,
)
from k_b.ai_api.digests import StageCall
from k_b.ai_api.metrics import estimate_cost
from k_b.core.config import METRICS_STOP_TIMEOUT_SECONDS, MILLISECONDS_PER_SECOND

logger = logging.getLogger(__name__)

METER_NAME = "k_b.ai_api"
# The operation of the conventions: K-B calls chat/completions only.
OPERATION_NAME = "chat"
TEXT_MODALITY = "text"
OK_OUTCOME = "ok"
# The last answer of the provider came: its output went through the checks.
HTTP_OK = 200
# The buckets of gen_ai.client.inference.duration in the conventions, in seconds; the reading of the
# data API, an HTTP call too, takes them.
CALL_SECONDS_BUCKETS = (
    0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92,
)  # fmt: skip
# The checks of an output run in memory: a millisecond to a few seconds.
CHECK_SECONDS_BUCKETS = (
    0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5,
)  # fmt: skip


class ModelMetrics:
    """The instruments of the AI API, made once with the app: record the calls of a request and
    the reading of its window; stop sends what is not sent yet."""

    def __init__(self, meter_provider: MeterProvider) -> None:
        self._meter_provider = meter_provider
        meter = meter_provider.get_meter(METER_NAME)
        self._inference_duration = meter.create_histogram(
            "gen_ai.client.inference.duration",
            unit="s",
            description="Duration of a call to the model, both attempts and the wait between.",
            explicit_bucket_boundaries_advisory=CALL_SECONDS_BUCKETS,
        )
        self._input_tokens = meter.create_counter(
            "gen_ai.client.inference.usage.input_tokens",
            unit="{token}",
            description="Input tokens of the calls, as the provider counts them.",
        )
        self._output_tokens = meter.create_counter(
            "gen_ai.client.inference.usage.output_tokens",
            unit="{token}",
            description="Output tokens of the calls, reasoning tokens included.",
        )
        self._calls = meter.create_counter(
            "k_b.llm.calls",
            unit="{call}",
            description="Calls to the model, by outcome and by schema check.",
        )
        self._check_duration = meter.create_histogram(
            "k_b.llm.check.duration",
            unit="s",
            description="Duration of the checks of the outputs of a call.",
            explicit_bucket_boundaries_advisory=CHECK_SECONDS_BUCKETS,
        )
        self._cost = meter.create_counter(
            "k_b.llm.cost",
            unit="{USD}",
            description="Estimated cost of the calls, at the prices of core/config.py.",
        )
        self._claims_removed = meter.create_counter(
            "k_b.digest.claims_removed",
            unit="{claim}",
            description="Claims removed from the digests by the checks of fidelity.",
        )
        self._items_uncited = meter.create_counter(
            "k_b.digest.items_uncited",
            unit="{item}",
            description="Items no longer cited once the claims out of bounds are removed.",
        )
        self._data_fetch_duration = meter.create_histogram(
            "k_b.digest.data_fetch.duration",
            unit="s",
            description="Duration of the reading of the window by the data API.",
            explicit_bucket_boundaries_advisory=CALL_SECONDS_BUCKETS,
        )

    @classmethod
    def from_settings(cls, settings: MetricsExportSettings | None) -> "ModelMetrics":
        """The instruments of kb serve-ai: exported if the settings are given, dropped if not."""
        return cls(build_meter_provider(settings))

    def record_calls(
        self, llm_settings: LlmSettings, stage_calls: Sequence[StageCall]
    ) -> None:
        """The measures of each call of a request, the ones of its JSON line."""
        for stage_call in stage_calls:
            call = stage_call.llm_call
            attributes: dict[str, str | bool] = {
                "gen_ai.operation.name": OPERATION_NAME,
                # What K-B knows: openai_compatible or replay, not the company behind the URL.
                "gen_ai.provider.name": llm_settings.provider,
                "gen_ai.request.model": llm_settings.model,
                "k_b.stage": stage_call.stage,
            }
            self._inference_duration.record(
                call.llm_ms / MILLISECONDS_PER_SECOND,
                attributes
                if call.outcome == OK_OUTCOME
                else attributes | {"error.type": call.outcome},
            )
            token_attributes = attributes | {"gen_ai.token.modality": TEXT_MODALITY}
            self._input_tokens.add(call.tokens_in, token_attributes)
            self._output_tokens.add(call.tokens_out, token_attributes)
            self._calls.add(
                1,
                attributes
                | {"k_b.outcome": call.outcome, "k_b.schema_valid": call.schema_valid},
            )
            # A call without an answer (a timeout, a failed connection, a 5xx) ran no check: a 0
            # would pull the duration of the checks down.
            if call.http_status == HTTP_OK:
                self._check_duration.record(
                    call.check_ms / MILLISECONDS_PER_SECOND, attributes
                )
            self._cost.add(estimate_cost(call.tokens_in, call.tokens_out), attributes)
            if stage_call.claims_removed is not None:
                self._claims_removed.add(stage_call.claims_removed, attributes)
            if stage_call.items_uncited is not None:
                self._items_uncited.add(stage_call.items_uncited, attributes)

    def record_data_fetch(self, data_fetch_ms: int) -> None:
        """The reading of the window of a request, a model called or not."""
        self._data_fetch_duration.record(data_fetch_ms / MILLISECONDS_PER_SECOND)

    def stop(self) -> None:
        """Send what is not sent yet, within METRICS_STOP_TIMEOUT_SECONDS. A failure is logged by
        its type only: the SDK builds its message from the errors of its readers."""
        try:
            self._meter_provider.shutdown(
                timeout_millis=METRICS_STOP_TIMEOUT_SECONDS * MILLISECONDS_PER_SECOND
            )
        except Exception as error:  # noqa: BLE001 — the SDK raises a bare Exception
            logger.error("metrics: stop failed, %s", type(error).__name__)
