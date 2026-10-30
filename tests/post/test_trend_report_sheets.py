"""The trend reports in the vault: their path, their Markdown, and the refusals before and at the
writing."""

import json
from datetime import UTC, date, datetime

import pytest
from post.test_trend_report_client import change_period, make_report, repository

from k_b.core.config import DIGEST_SUBJECTS, TRENDS_DIR_NAME, WATCH_DIR_NAME
from k_b.post.digest_sheets import is_writable_url
from k_b.post.trend_report_client import TrendReportResponse
from k_b.post.trend_report_sheets import (
    GITHUB_URL,
    refuse_written_sheet,
    render_trend_report_sheet,
    write_trend_report_sheet,
)
from k_b.post.vault_files import VaultEntryRefusedError

GENERATED = datetime(2026, 11, 1, 10, 0, 5, tzinfo=UTC)
DAY = GENERATED.date()


def read(report):
    return TrendReportResponse.model_validate_json(json.dumps(report))


def render(report):
    return render_trend_report_sheet(read(report), GENERATED)


def test_the_folder_of_the_reports_is_reserved_under_veille():
    assert (WATCH_DIR_NAME, TRENDS_DIR_NAME) == ("veille", "tendances")
    assert TRENDS_DIR_NAME not in {subject.name for subject in DIGEST_SUBJECTS}


def test_a_report_gives_its_period_its_limit_and_a_row_per_repository():
    assert render(make_report()) == (
        "---\n"
        "generated: 2026-11-01T10:00:05Z\n"
        "first_window: 2026-10-28\n"
        "last_window: 2026-10-31\n"
        "windows: 4\n"
        "missing_windows: 0\n"
        "windows_capped: false\n"
        "first_report: false\n"
        "new_evaluated: true\n"
        "repositories_dropped: 0\n"
        "model: null\n"
        "request_id: 1b4e28ba-2fa1-4d2e-9b5c-6c8e1f0a7d3e\n"
        "---\n"
        "\n"
        "# Tendances GitHub du 2026-11-01\n"
        "\n"
        "Période : fenêtres du 2026-10-28 au 2026-10-31 (4 fenêtres de 3 jours).\n"
        "\n"
        "Les comptes viennent de GH Archive, un échantillon d'environ 1 % des étoiles données"
        " sur GitHub (mesure du 2026-10-29) : des rangs proches ne se départagent pas.\n"
        "\n"
        "## Dépôts qui ressortent\n"
        "\n"
        "| Dépôt | Critères | Meilleur rang | Trajectoire (rang par fenêtre) |\n"
        "|---|---|---|---|\n"
        "| <https://github.com/owner/rising-repository> | nouveau, en accélération | 2"
        " | 12 → 7 → 4 → 2 |\n"
        "| <https://github.com/steady/tool> | durable | 3 | 3 → hors top → 5 → 9 |\n"
        "\n"
        "Fenêtres manquantes : aucune.\n"
    )


def test_the_same_response_and_instant_give_the_same_bytes():
    assert render(make_report()) == render(make_report())


def test_the_counts_of_stars_are_never_written():
    sheet = render(make_report())

    assert "étoiles gagnées" not in sheet
    for stars in ("58", "53", "56"):
        assert stars not in sheet


@pytest.mark.parametrize(
    ("report", "said"),
    [
        (
            change_period(
                make_report(repositories=[]), first_report=True, new_evaluated=False
            ),
            "Premier compte rendu : « nouveau » n'est pas évalué.",
        ),
        (
            change_period(make_report(repositories=[]), new_evaluated=False),
            (
                "Toutes les fenêtres du compte rendu précédent manquent : « nouveau »"
                " n'est pas évalué."
            ),
        ),
        (
            change_period(make_report(repositories=[]), windows_capped=True),
            (
                "Plafond : seules les 15 fenêtres les plus récentes sont lues ; les plus"
                " anciennes depuis le compte rendu précédent sont laissées de côté."
            ),
        ),
        (
            change_period(make_report(repositories=[]), windows=["2026-10-31"]),
            (
                "Période d'une fenêtre : ni « durable » ni « en accélération » ne"
                " peuvent ressortir."
            ),
        ),
        (
            change_period(
                make_report(repositories=[]), windows=["2026-10-30", "2026-10-31"]
            ),
            "Période de 2 fenêtres : « en accélération » se lit sur deux rangs.",
        ),
        (
            make_report(repositories=[]),
            "Aucun dépôt ne remplit un critère sur la période.",
        ),
        (
            make_report(repositories=[], repositories_dropped=2),
            "Dépôts écartés : 2 (nom inutilisable dans un chemin).",
        ),
        (
            change_period(
                make_report(repositories=[]),
                missing_windows=["2026-10-29", "2026-10-30"],
            ),
            "Fenêtres manquantes : 2026-10-29, 2026-10-30.",
        ),
    ],
)
def test_the_report_says_what_limits_its_period(report, said):
    assert f"\n{said}\n" in render(report)


def test_a_period_of_one_window_names_it_alone():
    report = change_period(make_report(repositories=[]), windows=["2026-10-31"])

    assert "\nPériode : la fenêtre du 2026-10-31, de 3 jours.\n" in render(report)


def test_a_missing_window_shows_in_the_trajectory():
    trajectory = repository()["trajectory"]
    trajectory[1] |= {"state": "missing", "rank": None, "stars_gained": None}
    report = change_period(
        make_report(repositories=[repository(trajectory=trajectory)]),
        missing_windows=["2026-10-29"],
    )

    assert " | 12 → — → 4 → 2 |\n" in render(report)


@pytest.mark.parametrize(
    "name", ["owner/www.site", "a-b/c_d.e", "Owner/.github", "o/repo.", "x/y-"]
)
def test_the_url_of_a_valid_name_is_an_autolink_written_as_it_is(name):
    report = make_report(repositories=[repository(repository_name=name)])

    assert f"| <{GITHUB_URL}{name}> |" in render(report)
    assert is_writable_url(f"{GITHUB_URL}{name}")


def test_a_report_is_written_once_under_veille_tendances(tmp_path):
    response = read(make_report())

    sheet = write_trend_report_sheet(tmp_path, response, GENERATED)

    assert sheet == "veille/tendances/2026-11-01.md"
    assert (tmp_path / sheet).read_text("utf-8") == render(make_report())


def test_a_report_of_the_day_written_meanwhile_is_refused_and_kept(tmp_path):
    sheet = tmp_path / "veille" / "tendances" / "2026-11-01.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"read by Sabine\n")

    with pytest.raises(VaultEntryRefusedError) as refused:
        write_trend_report_sheet(tmp_path, read(make_report()), GENERATED)

    assert str(refused.value) == (
        "sheet_exists: veille/tendances/2026-11-01.md is there;"
        " kb trend-report never rewrites a report"
    )
    assert sheet.read_bytes() == b"read by Sabine\n"


def test_before_the_request_a_report_of_the_day_is_refused(tmp_path):
    sheet = tmp_path / "veille" / "tendances" / "2026-11-01.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"read by Sabine\n")

    with pytest.raises(VaultEntryRefusedError, match="^sheet_exists: "):
        refuse_written_sheet(tmp_path, DAY)
    refuse_written_sheet(tmp_path, date(2026, 11, 2))


def test_before_the_request_a_folder_linked_elsewhere_is_refused(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    vault = tmp_path / "vault"
    (vault / "veille").mkdir(parents=True)
    elsewhere.mkdir()
    (vault / "veille" / "tendances").symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(VaultEntryRefusedError) as refused:
        refuse_written_sheet(vault, DAY)

    assert str(refused.value) == (
        "vault_link_refused: veille/tendances is a symbolic link"
    )
    assert not (vault / "veille" / "tendances" / "2026-11-01.md").exists()
