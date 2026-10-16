import pytest
from pydantic import BaseModel, ValidationError

from k_b.core.quoting import MAX_QUOTED_VALUE_LENGTH, quote_value, without_values


def test_a_value_is_quoted_with_its_line_breaks_and_control_characters_escaped():
    assert quote_value("a\nb\x1b[31m") == "'a\\nb\\x1b[31m'"


def test_a_long_value_is_cut_to_the_fixed_length():
    quoted = quote_value("x" * 500)

    assert len(quoted) == MAX_QUOTED_VALUE_LENGTH
    assert quoted.startswith("'xxx")


class Summary(BaseModel):
    text: str


def test_an_error_without_values_keeps_its_field_and_type_but_not_its_value():
    with pytest.raises(ValidationError) as refusal:
        Summary.model_validate({"text": 1234567})

    described = str(without_values(refusal.value))

    assert "text" in described
    assert "string_type" in described
    assert "1234567" not in described
