"""The stylesheet of the site holds the chart of the mockups of 2026-11-09: the contrasts of its pairs
by the relative luminance of WCAG 2.1, the focus ring, sizes in rem, and nothing fetched from
elsewhere."""

import re
from importlib.resources import files

import pytest

STYLESHEET = (files("k_b.web") / "static" / "site.css").read_text(encoding="utf-8")
CUSTOM_PROPERTY = re.compile(r"(--[a-z-]+)\s*:\s*(#[0-9A-Fa-f]{6})\s*;")
DECLARATION = re.compile(r"(?<![-\w])([a-z-]+)\s*:\s*([^;{}]+);")
# The pairs of the chart (planche « Charte graphique ») the stylesheet uses, and their minimum: 4.5
# for a text, 3 for a component of the interface (WCAG 2.1, 1.4.3 and 1.4.11).
PAIRS = [
    ("--color-ink", "--color-paper", 4.5),
    ("--color-ink", "--color-card", 4.5),
    ("--color-slate", "--color-paper", 4.5),
    ("--color-slate", "--color-card", 4.5),
    ("--color-teal", "--color-paper", 4.5),
    ("--color-teal", "--color-card", 4.5),
    ("--color-teal-deep", "--color-paper", 4.5),
    ("--color-on-teal", "--color-teal", 4.5),
    ("--color-on-teal", "--color-teal-deep", 4.5),
    # The focus ring, a component, on the background of the pages.
    ("--color-teal", "--color-paper", 3),
    # The mark Exploitée (KEV), the messages of a field refused, the border of a field.
    ("--color-on-alert", "--color-alert", 4.5),
    ("--color-alert-deep", "--color-card", 4.5),
    ("--color-alert-deep", "--color-paper", 4.5),
    ("--color-field-border", "--color-card", 3),
]


def read_colours():
    return dict(CUSTOM_PROPERTY.findall(STYLESHEET))


def measure_luminance(colour):
    """The relative luminance of WCAG 2.1 of a colour #RRGGBB."""
    channels = [int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def measure_contrast(foreground, background):
    lighter, darker = sorted(
        (measure_luminance(foreground), measure_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_the_luminance_gives_the_ratio_of_the_chart():
    # Planche « Charte graphique » : #1C1E21 sur #FBFBF8, 16,11:1.
    assert round(measure_contrast("#1C1E21", "#FBFBF8"), 2) == 16.11


@pytest.mark.parametrize(("foreground", "background", "minimum"), PAIRS)
def test_each_pair_of_the_chart_has_its_contrast(foreground, background, minimum):
    colours = read_colours()

    assert measure_contrast(colours[foreground], colours[background]) >= minimum


def test_the_focus_ring_is_the_one_of_the_chart():
    rule = re.search(r":focus-visible\s*\{([^}]*)\}", STYLESHEET)

    assert rule is not None
    assert "outline: 3px solid var(--color-teal);" in rule.group(1)
    assert "outline-offset: 2px;" in rule.group(1)


def test_every_font_size_is_in_rem():
    sizes = [
        value.strip()
        for name, value in DECLARATION.findall(STYLESHEET)
        if name == "font-size"
    ]

    assert sizes
    assert all(re.fullmatch(r"[0-9.]+rem", size) for size in sizes)


def test_nothing_is_fetched_from_elsewhere():
    assert re.findall(r"@import|@font-face|url\(", STYLESHEET) == []


@pytest.mark.parametrize("links", [r"\.prose a", r"\.card-link"])
def test_a_link_visited_in_a_text_has_a_colour_of_its_own_of_the_chart(links):
    """Opquast 2025, rule 141: a link in a text, and the link of a card to its source; a menu is out
    of the rule. Its contrast on the pages and on a card: 4.5 at least."""
    rule = re.search(
        links + r"\s*\{[^}]*?&:visited\s*\{\s*color:\s*var\((--[a-z-]+)\);", STYLESHEET
    )
    colours = read_colours()

    assert rule is not None
    assert colours[rule.group(1)] != colours["--color-teal"]
    assert measure_contrast(colours[rule.group(1)], colours["--color-paper"]) >= 4.5
    assert measure_contrast(colours[rule.group(1)], colours["--color-card"]) >= 4.5


def test_a_field_reached_from_the_summary_of_the_errors_keeps_its_label_in_sight():
    """The browser scrolls a target to the top of the window: the label, the help and the message
    above the field would leave the screen."""
    assert re.search(
        r"\.field\s*\{[^}]*?& > input\s*\{\s*scroll-margin-block-start:\s*[0-9.]+rem;",
        STYLESHEET,
    )


def test_a_page_prints_without_its_navigation():
    """Opquast 2025, rules 195 and 196."""
    rule = re.search(r"@media print\s*\{\s*([^{]+)\{\s*display:\s*none;", STYLESHEET)

    assert rule is not None
    hidden = {selector.strip() for selector in rule.group(1).split(",")}
    assert {".skip-link", ".site-header", ".site-footer", ".error-actions"} <= hidden


def test_the_skip_link_is_a_target_of_the_size_of_the_others():
    """Opquast 2025, rule 186: 44 by 44 pixels, the --target-size of the chart."""
    assert re.search(
        r"\.skip-link\s*\{[^}]*min-block-size:\s*var\(--target-size\);", STYLESHEET
    )


def test_a_button_keeps_a_border_in_the_forced_colours_of_windows():
    """A transparent border, drawn in the colour of the text when the colours are forced."""
    assert re.search(
        r"\.button,\s*\.button-secondary\s*\{[^}]*border:\s*1px solid transparent;",
        STYLESHEET,
    )
