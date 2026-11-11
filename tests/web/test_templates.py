"""What the templates of the site never write: a value let through unescaped, a script, a style in a
tag, a resource of another site, an attribute without quotes, or a link built by url_for (the scheme
seen behind the ingress may be http)."""

import re
from importlib.resources import files

import pytest

TEMPLATES = files("k_b.web") / "templates"
TEMPLATE_NAMES = sorted(
    entry.name for entry in TEMPLATES.iterdir() if entry.name.endswith(".html")
)
FORBIDDEN = {
    "an unescaped value": re.compile(r"\|\s*safe\b|Markup|autoescape\s+false"),
    "a link built by url_for": re.compile(r"url_for"),
    "a script": re.compile(r"<script|\son[a-z]+=", re.IGNORECASE),
    "a style in a tag": re.compile(r"\sstyle=|<style", re.IGNORECASE),
    "a resource of another site": re.compile(
        r"""(src|srcset|action)=["']?(https?:)?//|<link[^>]*href=["']?(https?:)?//""",
        re.IGNORECASE,
    ),
}
TAG = re.compile(r"<[a-zA-Z][^>]*>")
QUOTED_VALUE = re.compile(r'"[^"]*"')
JINJA_STATEMENT = re.compile(r"\{%.*?%\}")
UNQUOTED_ATTRIBUTE = re.compile(r"=(?!\")")


def read_template(name):
    return (TEMPLATES / name).read_text(encoding="utf-8")


def test_the_site_has_its_templates():
    assert {"base.html", "404.html", "500.html", "403.html"} <= set(TEMPLATE_NAMES)


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
@pytest.mark.parametrize("what", sorted(FORBIDDEN))
def test_a_template_never_writes(name, what):
    assert FORBIDDEN[what].findall(read_template(name)) == []


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
def test_every_attribute_of_a_template_is_quoted(name):
    # A value in quotes and a statement of Jinja are set aside first: a = inside is no attribute.
    unquoted = [
        tag
        for tag in TAG.findall(read_template(name))
        if UNQUOTED_ATTRIBUTE.search(
            JINJA_STATEMENT.sub("", QUOTED_VALUE.sub('""', tag))
        )
    ]

    assert unquoted == []
