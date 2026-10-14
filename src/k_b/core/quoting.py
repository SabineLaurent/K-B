"""How a value observed in an input is quoted in a log line or an error (conventions.md, rule 3)."""

# The longest value quoted, quotes and escapes included.
MAX_QUOTED_VALUE_LENGTH = 100


def quote_value(value: object) -> str:
    """The value with its line breaks and control characters escaped by repr, cut to a fixed
    length: it cannot write a line of its own in a log."""
    return repr(value)[:MAX_QUOTED_VALUE_LENGTH]
