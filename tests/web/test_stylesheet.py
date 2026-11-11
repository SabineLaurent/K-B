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
