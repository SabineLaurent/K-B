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
    # The banner of an item in the CISA KEV catalog: its title and its text on its background.
    ("--color-alert-deep", "--color-alert-wash", 4.5),
    ("--color-alert-ink", "--color-alert-wash", 4.5),
    # The packages of an advisory, each in its chip.
    ("--color-ink", "--color-chip", 4.5),
    # A card under the pointer or holding the focus: its texts and its links, visited or hovered,
    # on its tint.
    ("--color-ink", "--color-card-hover", 4.5),
    ("--color-slate", "--color-card-hover", 4.5),
    ("--color-teal", "--color-card-hover", 4.5),
    ("--color-teal-deep", "--color-card-hover", 4.5),
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


def test_the_kind_of_a_card_is_framed_as_in_the_mockups():
    """Maquettes-fil.dc.html (2026-11-09), at its three widths: a border of 1 px in the ink, corners
    of 4 px, 2 by 8 px within (Sabine, 2026-11-11)."""
    rule = re.search(r"\.card-kind\s*\{([^}]*)\}", STYLESHEET)

    assert rule is not None
    declarations = {
        name: value.strip() for name, value in DECLARATION.findall(rule.group(1))
    }
    assert declarations["border"] == "1px solid var(--color-ink)"
    assert declarations["border-radius"] == "4px"
    assert declarations["padding"] == "0.125rem 0.5rem"


def read_block(text, opening):
    """The text between the brace that follows opening and the one that closes it."""
    match = re.search(opening, text, re.MULTILINE)
    assert match is not None, opening
    depth = 1
    for index in range(match.end(), len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if not depth:
            return text[match.end() : index]
    raise AssertionError(f"{opening} is not closed")


def strip_nested_rules(block):
    """The declarations of a block, without the rules nested in it."""
    kept = []
    depth = 0
    for character in block:
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        elif not depth:
            kept.append(character)
    return "".join(kept)


def read_rule(selector, media=None):
    """The declarations of the rule of selector, or of its media query nested in it: a rule that
    opens its line, nested by & or not; never one of another selector, such as & > .field-error."""
    rule = read_block(STYLESHEET, rf"^\s*(?:& )?{re.escape(selector)}\s*\{{")
    if media is None:
        return rule
    return read_block(rule, rf"@media {re.escape(media)}\s*\{{")


@pytest.mark.parametrize(
    ("selector", "media", "declaration"),
    [
        (".field-help", None, "margin: 0;"),
        (".field-error", None, "margin: 0;"),
        (".choices", None, "grid-template-columns: repeat(2, minmax(0, 1fr));"),
        (
            ".kind-choices",
            "(width >= 48rem)",
            "grid-template-columns: repeat(3, minmax(0, 1fr));",
        ),
        (".kind-choices", "(width >= 64rem)", "display: flex;"),
        (".period-choices", "(width >= 48rem)", "display: flex;"),
        (".period-group", "(width >= 48rem)", "display: flex;"),
        # The radios under their legend on a tablet, the date block on their right as in the
        # mockups; on a computer, the radios and the field centred on their line.
        (".period-group", "(width >= 48rem)", "align-items: flex-start;"),
        (".period-group", "(width >= 64rem)", "align-items: center;"),
        # The next page on the right, whatever the line it wraps to (Maquettes-fil.dc.html).
        ('a[rel="next"]', None, "margin-inline-start: auto;"),
        (
            ".period-field",
            "(width >= 64rem)",
            "grid-template-columns: auto minmax(10rem, 14rem);",
        ),
        (".results-line", None, "scroll-margin-block-start: 1rem;"),
        (".card-link", None, "font-size: 0.875rem;"),
        (".link-note", None, "font-size: 0.75rem;"),
        (".site-logout", None, "margin-inline-start: auto;"),
        # The title of a card clear of the line above and of the link below: its padding of 44 px
        # and its focus ring.
        (".card-title", None, "margin-block: 0.75rem;"),
        # Framed when Windows forces its colours, as the badge and the buttons.
        (".package", None, "border: 1px solid transparent;"),
        # The column of the detail and of its facts never wider than the page, whatever the
        # longest word at 200 % text (WCAG 1.4.10).
        (".item", None, "grid-template-columns: minmax(0, 1fr);"),
        (".item-facts", None, "grid-template-columns: minmax(0, 1fr);"),
    ],
)
def test_the_layout_of_the_mockups_holds_at_each_width(selector, media, declaration):
    """Maquettes-fil.dc.html (2026-11-09) at 390, 820 and 1280 px (Sabine, 2026-11-11): the helps
    against their label, the choices in two columns on a phone, the kinds in three on a tablet and
    one line on a computer, the start date after the radios, a page link landing on the results,
    the link of a card short. The heights measured are in the PR; this test keeps each rule, in
    the rule it names, never in one nested in it."""
    assert declaration in strip_nested_rules(read_rule(selector, media))


def test_a_card_takes_the_tint_of_its_mockup_under_the_pointer_or_the_focus():
    """Maquettes-fil.dc.html (2026-11-09), version (c): the first card hovered, in #E6F0F1; the
    same tint when a link of the card has the focus, for the keyboard."""
    rule = read_block(read_rule(".card"), r"&:hover,\s*&:focus-within\s*\{")

    assert "background: var(--color-card-hover);" in rule
    assert read_colours()["--color-card-hover"] == "#E6F0F1"


def test_the_date_field_spans_the_two_lines_of_its_label_and_its_help_on_a_computer():
    """A message refused comes on a third line, under them."""
    rule = read_block(read_rule(".period-field", "(width >= 64rem)"), r"& > input\s*\{")

    assert "grid-column: 2;" in rule
    assert "grid-row: 1 / span 2;" in rule


def test_nothing_is_fetched_from_elsewhere():
    assert re.findall(r"@import|@font-face|url\(", STYLESHEET) == []


@pytest.mark.parametrize(
    "links", [r"\.prose a", r"\.card-link", r"\.card-title a", r"\.trends-table a"]
)
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
    assert {
        ".skip-link",
        ".site-header",
        ".site-footer",
        ".error-actions",
        ".back-link",
        ".trends-filter",
    } <= hidden


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


@pytest.mark.parametrize(
    "selector",
    [".item h1", ".item-authors", ".item-text", ".item-facts dd", ".package"],
)
def test_a_long_text_of_a_detail_wraps_anywhere(selector):
    """100 packages of 255 characters, or a word of a source without space, hold at 320 px
    (RGAA 10.11)."""
    assert "overflow-wrap: anywhere;" in strip_nested_rules(read_rule(selector))


def test_the_notes_of_a_release_keep_their_lines():
    """D3 (Sabine, 2026-11-11): plain text, its line breaks kept."""
    assert "white-space: pre-wrap;" in strip_nested_rules(read_rule(".item-text p"))


def test_the_detail_has_the_width_of_its_mockups():
    """Maquette-papier.dc.html: 760 px with its padding, a line of text short."""
    assert "max-inline-size: 47.5rem;" in strip_nested_rules(read_rule(".item-page"))


@pytest.mark.parametrize(
    ("selector", "declaration"),
    [
        (".banner-alert", "background: var(--color-alert-wash);"),
        (".banner-neutral", "background: var(--color-card);"),
        (".package", "background: var(--color-chip);"),
    ],
)
def test_the_banner_and_the_packages_have_the_colours_of_their_mockups(
    selector, declaration
):
    """Maquette-alerte.dc.html and Maquette-faille.dc.html; the alert only for an item in the
    catalog (C4)."""
    assert declaration in strip_nested_rules(read_rule(selector))


@pytest.mark.parametrize("selector", [".card-title a", ".back-link", ".trends-table a"])
def test_a_link_of_a_detail_or_of_a_title_is_a_target_of_44_pixels(selector):
    """Opquast 2025, rule 186: by its padding, or its minimum height."""
    rule = strip_nested_rules(read_rule(selector))

    assert re.search(
        r"padding-block: 0\.75rem;|min-block-size: var\(--target-size\);", rule
    )


def test_a_button_wraps_its_label_and_its_announcement_with_large_text():
    """WCAG 1.4.4 and 1.4.10: on one line, its label and its announcement would widen the page of
    a phone with its text at 200 %."""
    assert re.search(
        r"\.button,\s*\.button-secondary\s*\{[^}]*flex-wrap:\s*wrap;", STYLESHEET
    )


def test_the_counts_of_the_trends_are_aligned_as_numbers():
    """Maquette-tendances.dc.html: on the right, in tabular figures, a count never cut."""
    rule = strip_nested_rules(read_rule(".trends-table .number"))

    assert "text-align: end;" in rule
    assert "font-variant-numeric: tabular-nums;" in rule
    assert "white-space: nowrap;" in rule


def test_the_name_of_a_repository_wraps_anywhere():
    """39 characters for an owner and 100 for a repository hold at 320 px (RGAA 10.11)."""
    assert "overflow-wrap: anywhere;" in strip_nested_rules(
        read_rule(".trends-table a")
    )
