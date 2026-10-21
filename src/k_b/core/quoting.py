"""How a value observed in an input is quoted in a log line or an error (conventions.md, rule 3)."""

from pydantic import ValidationError
from pydantic_core import InitErrorDetails

# The longest value quoted, quotes and escapes included.
MAX_QUOTED_VALUE_LENGTH = 100


def quote_value(value: object) -> str:
    """The value with its line breaks and control characters escaped by repr, cut to a fixed
    length: it cannot write a line of its own in a log."""
    return repr(value)[:MAX_QUOTED_VALUE_LENGTH]


def without_values(error: ValidationError) -> ValidationError:
    """The same errors, without the value each one received: its text keeps the field, the type
    of error and its message (poc.md, rule 5).

    Each error is rebuilt by its type, which must be one pydantic knows: a validator raises a
    ValueError, never a PydanticCustomError, which this would refuse with a KeyError. Its place
    and message are kept: a place comes from the model, never from the input, and the message
    of a validator never quotes the value (a measure, or quote_value: conventions.md, rule 3).
    Behind it, the models that read a source hide their input too (hide_input_in_errors)."""
    line_errors = []
    for detail in error.errors():
        line_error: InitErrorDetails = {
            "type": detail["type"],
            "loc": detail["loc"],
            "input": None,
        }
        if "ctx" in detail:
            line_error["ctx"] = detail["ctx"]
        line_errors.append(line_error)
    return ValidationError.from_exception_data(
        error.title, line_errors, hide_input=True
    )


def locate_first_error(error: ValidationError) -> str:
    """The place and the type of the first error, on one line, never its value; the count when
    there are more (poc.md, rule 5). An error on the whole input has no place: it is the input."""
    first = error.errors(include_url=False, include_context=False, include_input=False)[
        0
    ]
    place = ".".join(str(part) for part in first["loc"]) or "input"
    count = error.error_count()
    more = f", {count} errors" if count > 1 else ""
    return f"{place} ({first['type']}){more}"
