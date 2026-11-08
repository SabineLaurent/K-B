"""The dashboard and the alert rules of the model, as Grafana Cloud imports them
(observability/grafana/): they read only the measures K-B emits, each through max_over_time,
tell nothing by colour alone, and keep one threshold per alert, that of the rules."""

import json
import re
from pathlib import Path

import yaml
from ai_api.test_digest_router import METRIC_ATTRIBUTES

from k_b.ai_api.observability.metric_instruments import ModelMetrics

GRAFANA_DIR = Path(__file__).parents[1] / "observability" / "grafana"
DASHBOARD_PATH = GRAFANA_DIR / "dashboard.json"
ALERT_RULES_PATH = GRAFANA_DIR / "alert-rules.yaml"
ENVIRONMENT_LABEL = "deployment_environment_name"
DASHBOARD_ENVIRONMENT_MATCHER = f'{ENVIRONMENT_LABEL}="$env"'
# The labels a series carries beyond the attributes of its point: the environment, a resource
# attribute Grafana Cloud promotes, and the bucket of a histogram.
LABELS_BEYOND_THE_ATTRIBUTES = {ENVIRONMENT_LABEL, "le"}
# The unit words Grafana Cloud adds to a name (docs/grafana-cloud otlp-format-considerations, and
# the OpenTelemetry specification: s is seconds); a unit in braces is dropped.
UNIT_WORDS = {"s": "seconds"}
HISTOGRAM_SUFFIXES = ("_bucket", "_count", "_sum")
# The names Grafana Cloud gave the measures of the sandbox, in Explore, on 2026-11-08 (count by
# (__name__) of the series labelled sandbox).
NAMES_SEEN_IN_GRAFANA = {
    "gen_ai_client_inference_duration_seconds_bucket",
    "gen_ai_client_inference_duration_seconds_count",
    "gen_ai_client_inference_duration_seconds_sum",
    "gen_ai_client_inference_usage_input_tokens_total",
    "gen_ai_client_inference_usage_output_tokens_total",
    "k_b_digest_claims_removed_total",
    "k_b_digest_data_fetch_duration_seconds_bucket",
    "k_b_digest_data_fetch_duration_seconds_count",
    "k_b_digest_data_fetch_duration_seconds_sum",
    "k_b_digest_facts_checked_total",
    "k_b_digest_facts_found_total",
    "k_b_digest_items_no_suitable_subject_total",
    "k_b_digest_items_removed_by_checks_total",
    "k_b_digest_items_unanswered_total",
    "k_b_digest_items_with_subject_total",
    "k_b_llm_calls_total",
    "k_b_llm_check_duration_seconds_bucket",
    "k_b_llm_check_duration_seconds_count",
    "k_b_llm_check_duration_seconds_sum",
    "k_b_llm_cost_total",
}
STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"')
RANGE = re.compile(r"\[[^\]]*\]")
MATCHER_LABEL = re.compile(r"([A-Za-z_]\w*)\s*(?:=~|!~|!=|=)")
GROUPING = re.compile(r"\b(?:by|without)\s*\(([^)]*)\)")
SELECTOR = re.compile(r"\{[^}]*\}")
IDENTIFIER = re.compile(r"[A-Za-z_:][\w:]*(?!\w)(?!\s*\()")
PROMQL_KEYWORDS = {
    "by",
    "without",
    "bool",
    "or",
    "and",
    "unless",
    "on",
    "ignoring",
    "group_left",
    "group_right",
    "offset",
}
# The comparison that ends the expression of a rule: its threshold.
RULE_THRESHOLD = re.compile(r"([<>])\s*([0-9.]+)\s*$")
# The line of a threshold on a curve of the dashboard: the only expression that reads no measure.
THRESHOLD_LINE = re.compile(r"vector\([0-9.]+\)")
# The matchers of a field override, as Grafana names them (FieldMatcherID, packages/grafana-data/
# src/transformations/matchers/ids.ts, v13.3.0): a name out of the list matches no field, and its
# override is dropped without a word.
FIELD_MATCHER_IDS = {
    "numeric",
    "time",
    "first",
    "firstTimeField",
    "byType",
    "byTypes",
    "byName",
    "byNames",
    "byRegexp",
    "byRegexpOrNames",
    "byFrameRefID",
    "byValue",
}
# The Prometheus data source of a Grafana Cloud stack, grafanacloud-<stack>-prom: the stack holds
# others, grafanacloud-ml-metrics first in the list (seen on 2026-11-08).
STACK_PROMETHEUS = re.compile(r"^grafanacloud-.+-prom$")


class RecordingMeter:
    """A meter that keeps the name, the kind and the unit of each instrument made."""

    def __init__(self):
        self.instruments = []

    def create_counter(self, name, unit="", description=""):
        self.instruments.append((name, "counter", unit))

    def create_histogram(self, name, unit="", description="", **advisory):
        self.instruments.append((name, "histogram", unit))


class RecordingMeterProvider:
    def __init__(self):
        self.meter = RecordingMeter()

    def get_meter(self, name):
        return self.meter


def read_emitted_instruments():
    provider = RecordingMeterProvider()
    ModelMetrics(provider)
    return provider.meter.instruments


def name_in_grafana(name, kind, unit):
    """The names of the series of an instrument in Grafana Cloud."""
    base = name.replace(".", "_")
    if not (unit.startswith("{") and unit.endswith("}")):
        assert unit in UNIT_WORDS, f"{name}: unit {unit!r} has no word in UNIT_WORDS"
        word = UNIT_WORDS[unit]
        if not base.endswith(f"_{word}"):
            base = f"{base}_{word}"
    if kind == "counter":
        return {f"{base}_total"}
    return {f"{base}{suffix}" for suffix in HISTOGRAM_SUFFIXES}


def read_emitted_names():
    return set().union(
        *(name_in_grafana(*instrument) for instrument in read_emitted_instruments())
    )


def read_dashboard():
    return json.loads(DASHBOARD_PATH.read_text("utf-8"))


def read_alert_rules():
    """The rules of every group of the file, in their order."""
    groups = yaml.safe_load(ALERT_RULES_PATH.read_text("utf-8"))["groups"]
    return [rule for group in groups for rule in group["rules"]]


def read_alert_thresholds():
    """The threshold of each alert, by its name: the number of the comparison its expression
    ends with."""
    thresholds = {}
    for rule in read_alert_rules():
        match = RULE_THRESHOLD.search(rule["expr"])
        assert match, rule["alert"]
        thresholds[rule["alert"]] = float(match.group(2))
    return thresholds


def read_dashboard_panels():
    return read_dashboard()["panels"]


def read_dashboard_expressions():
    return [
        target["expr"]
        for panel in read_dashboard_panels()
        for target in panel.get("targets", [])
    ]


def read_all_expressions():
    return read_dashboard_expressions() + [rule["expr"] for rule in read_alert_rules()]


def read_labels(expression):
    """The labels an expression names, in its selectors and its groupings."""
    text = RANGE.sub("", STRING_LITERAL.sub('""', expression))
    labels = set(MATCHER_LABEL.findall(text))
    for grouping in GROUPING.findall(text):
        labels.update(label.strip() for label in grouping.split(",") if label.strip())
    return labels


def read_measure_names(expression):
    """The names of the measures an expression reads: what is left once its strings, ranges,
    selectors, groupings, functions and keywords are out."""
    text = STRING_LITERAL.sub('""', expression)
    text = SELECTOR.sub(" ", GROUPING.sub(" ", RANGE.sub(" ", text)))
    return {name for name in IDENTIFIER.findall(text) if name not in PROMQL_KEYWORDS}


def test_the_names_k_b_gives_its_measures_are_those_grafana_cloud_showed():
    assert read_emitted_names() == NAMES_SEEN_IN_GRAFANA


def test_each_expression_reads_only_measures_k_b_emits():
    emitted = read_emitted_names()
    expressions = read_all_expressions()

    assert read_dashboard_expressions()
    for expression in expressions:
        if THRESHOLD_LINE.fullmatch(expression):
            continue
        assert read_measure_names(expression), expression
        assert read_measure_names(expression) <= emitted, expression


def test_the_dashboard_and_the_rules_name_only_labels_k_b_emits():
    known = {
        attribute.replace(".", "_") for attribute in METRIC_ATTRIBUTES
    } | LABELS_BEYOND_THE_ATTRIBUTES

    for expression in read_all_expressions():
        assert read_labels(expression) <= known, expression


def test_each_measure_is_read_through_max_over_time():
    """A process of the AI API is a new series, whose first increment increase() and rate() do
    not see: 12 calls of 21 in the sandbox of 2026-11-08."""
    for expression in read_all_expressions():
        for name in read_measure_names(expression):
            all_reads = re.findall(rf"\b{name}\b", expression)
            reads_through_max = re.findall(rf"max_over_time\(\s*{name}\b", expression)
            assert len(reads_through_max) == len(all_reads), (name, expression)


def test_each_selector_of_the_dashboard_reads_the_environment_chosen():
    for expression in read_dashboard_expressions():
        for selector in SELECTOR.findall(expression):
            assert DASHBOARD_ENVIRONMENT_MATCHER in selector, expression


def test_each_rule_sums_by_environment():
    for rule in read_alert_rules():
        assert not re.findall(
            rf"\bsum\b(?!\s+by\s*\({ENVIRONMENT_LABEL}\))", rule["expr"]
        ), rule["alert"]


def test_no_panel_tells_by_colour_alone():
    """No colour of a value, of a cell nor of a threshold: a state is written, a threshold is a
    series named in the legend."""
    text = json.dumps(read_dashboard_panels())

    assert set(re.findall(r'"colorMode": "(\w+)"', text)) <= {"none"}
    assert '"thresholdsStyle": {"mode": "off"}' in text
    assert not re.findall(r'"thresholdsStyle": \{"mode": "(?!off)', text)
    assert "color-background" not in text


def test_each_state_of_the_dashboard_is_written():
    for panel in read_dashboard_panels():
        state_ids = {
            target["refId"]
            for target in panel.get("targets", [])
            if " bool " in target["expr"]
        }
        for ref_id in state_ids:
            [override] = [
                override
                for override in panel["fieldConfig"]["overrides"]
                if override["matcher"] == {"id": "byFrameRefID", "options": ref_id}
            ]
            [mappings] = [
                item["value"]
                for item in override["properties"]
                if item["id"] == "mappings"
            ]
            texts = {
                value: option["text"]
                for mapping in mappings
                for value, option in mapping["options"].items()
            }
            assert set(texts) == {"0", "1"}, panel["title"]
            assert all(texts.values()), panel["title"]


def test_each_override_names_a_matcher_of_grafana():
    for panel in read_dashboard_panels():
        for override in panel.get("fieldConfig", {}).get("overrides", []):
            assert override["matcher"]["id"] in FIELD_MATCHER_IDS, panel["title"]


def test_each_threshold_line_is_dashed():
    for panel in read_dashboard_panels():
        for target in panel.get("targets", []):
            if not THRESHOLD_LINE.fullmatch(target["expr"]):
                continue
            [override] = [
                override
                for override in panel["fieldConfig"]["overrides"]
                if override["matcher"]
                == {"id": "byFrameRefID", "options": target["refId"]}
            ]
            [style] = [
                item["value"]
                for item in override["properties"]
                if item["id"] == "custom.lineStyle"
            ]
            assert style["fill"] == "dash", panel["title"]


def test_the_dashboard_reads_the_prometheus_of_the_stack():
    [variable] = [
        variable
        for variable in read_dashboard()["templating"]["list"]
        if variable["type"] == "datasource"
    ]
    regex = variable["regex"].strip("/")

    assert variable["query"] == "prometheus"
    assert re.fullmatch(regex, "grafanacloud-mystack-prom")
    assert not re.fullmatch(regex, "grafanacloud-ml-metrics")
    assert regex == STACK_PROMETHEUS.pattern


def test_the_dashboard_keeps_the_threshold_of_each_rule():
    expressions = read_dashboard_expressions()

    for rule in read_alert_rules():
        operator, value = RULE_THRESHOLD.search(rule["expr"]).groups()
        state_end = re.compile(rf"\s{re.escape(operator)} bool {re.escape(value)}$")
        assert any(state_end.search(expression) for expression in expressions), rule[
            "alert"
        ]
        assert f"vector({value})" in expressions, rule["alert"]


def write_threshold(alert, value):
    """A threshold as the texts write it: a share in percent, the budget in USD."""
    if alert in THRESHOLDS_IN_USD:
        return f"{value:g} USD"
    return f"{value * 100:g} %"


def test_the_texts_quote_the_threshold_of_each_rule():
    legends = [
        target.get("legendFormat", "")
        for panel in read_dashboard_panels()
        for target in panel.get("targets", [])
    ]

    for rule in read_alert_rules():
        threshold = write_threshold(
            rule["alert"], float(RULE_THRESHOLD.search(rule["expr"]).group(2))
        )
        assert threshold in rule["annotations"]["summary"], rule["alert"]
        assert any(legend.endswith(f": {threshold}") for legend in legends), rule[
            "alert"
        ]


def read_rule_thresholds_written():
    """The threshold of each rule, as the texts write it."""
    return {
        write_threshold(
            rule["alert"], float(RULE_THRESHOLD.search(rule["expr"]).group(2))
        )
        for rule in read_alert_rules()
    }


def test_each_threshold_the_dashboard_writes_is_one_of_a_rule():
    text = json.dumps(read_dashboard(), ensure_ascii=False)
    written = set(QUOTED_THRESHOLD.findall(text))

    assert written == read_rule_thresholds_written()


def test_a_fidelity_without_a_checked_fact_gives_no_data():
    """0 facts checked would give NaN, and NaN < 0.95 is false: a state NORMAL never measured."""
    for expression in read_all_expressions():
        if "k_b_digest_facts_checked_total" not in expression:
            continue
        assert GUARDED_FACTS_CHECKED.search(expression), expression


# A threshold the texts of the dashboard write, in a legend or a description.
QUOTED_THRESHOLD = re.compile(r"(?:Seuil|Budget): ([0-9.]+ (?:%|USD))")
# The alerts whose threshold is an amount in USD; the others are shares.
THRESHOLDS_IN_USD = {"KbModelCostOverBudget"}
# The facts checked, divided by only when there is one: sum(...) > 0, by environment or not.
GUARDED_FACTS_CHECKED = re.compile(
    r"/ \(sum(?: by \(deployment_environment_name\) )?"
    r"\(max_over_time\(k_b_digest_facts_checked_total[^)]*\)\) > 0\)"
)
# A space before a colon or a semicolon, plain or no-break: the texts the jury reads in Grafana
# have none (choice 30 of Sabine, 2026-11-08), the expressions are not texts.
SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \u00a0][:;]")


def read_texts(value, key=None):
    """The strings of a dashboard or of a rule, but its expressions."""
    if key == "expr":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for name, item in value.items() for text in read_texts(item, name)]
    if isinstance(value, list):
        return [text for item in value for text in read_texts(item)]
    return []


def test_no_text_has_a_space_before_a_colon_or_a_semicolon():
    texts = read_texts(read_dashboard()) + read_texts(read_alert_rules())

    assert [text for text in texts if SPACE_BEFORE_PUNCTUATION.search(text)] == []


def test_the_three_alerts_of_the_criterion_are_there():
    assert set(read_alert_thresholds()) == {
        "KbModelInvalidOutputs",
        "KbModelLowFidelity",
        "KbModelCostOverBudget",
    }
