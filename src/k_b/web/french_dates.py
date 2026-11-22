"""The dates and the numbers of the site, the month in letters (Opquast 2025, rule 4) and the
thousands grouped: written by the site, never by the locale of the machine, which may not be
French."""

from datetime import date, datetime

# Groups the thousands of a count, as French writes them: 1 500 (chr, never an escape in the
# source, which a tool can turn into the character itself).
THOUSANDS_SEPARATOR = chr(0x202F)

MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def write_day(day: date) -> str:
    """A day as the site gives it: 1er novembre 2026; a moment, by its own day."""
    number = "1er" if day.day == 1 else str(day.day)
    return f"{number} {MONTHS[day.month - 1]} {day.year}"


def write_moment(moment: datetime) -> str:
    """A moment in UTC as the page 500 gives it: 1er novembre 2026 à 09:05 UTC."""
    return f"{write_day(moment)} à {moment:%H:%M} UTC"


def write_count(count: int) -> str:
    return f"{count:,}".replace(",", THOUSANDS_SEPARATOR)
