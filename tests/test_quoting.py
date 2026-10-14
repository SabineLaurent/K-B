from k_b.core.quoting import MAX_QUOTED_VALUE_LENGTH, quote_value


def test_a_value_is_quoted_with_its_line_breaks_and_control_characters_escaped():
    assert quote_value("a\nb\x1b[31m") == "'a\\nb\\x1b[31m'"


def test_a_long_value_is_cut_to_the_fixed_length():
    quoted = quote_value("x" * 500)

    assert len(quoted) == MAX_QUOTED_VALUE_LENGTH
    assert quoted.startswith("'xxx")
