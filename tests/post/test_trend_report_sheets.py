"""The trend reports in the vault: their path, their Markdown, and the refusals before and at the
writing."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from post.test_trend_report_client import (
    NO_CANDIDATE_READ,
    NOT_WRITTEN,
    RISING,
    STEADY,
    TEXTS,
    WRITING_FAILURES,
    change_period,
    choose,
    make_report,
    repository,
)

from k_b.core.config import (
    DIGEST_SUBJECTS,
    MAX_TOPICS_FOR_SELECTION,
    TRENDS_DIR_NAME,
    WATCH_DIR_NAME,
)
from k_b.items import CAUTIONS, is_writable_url
from k_b.jobs.watch_download import find_sheet_text_refusal
from k_b.post.trend_report_client import DroppedCandidates, TrendReportResponse
from k_b.post.trend_report_sheets import (
    CAUTION_LABELS,
    DROP_REASON_LABELS,
    GITHUB_URL,
    MISSING,
    WRITING_FAILURE_REASONS,
    ReportFile,
    locate_report_file,
    refuse_written_sheet,
    render_trend_report_sheet,
    write_trend_report_sheet,
)
from k_b.post.vault_files import VaultEntryRefusedError

GENERATED = datetime(2026, 11, 1, 10, 0, 5, tzinfo=UTC)
DAY = GENERATED.date()
# The facts of RISING, those of a repository chosen by default.
FACTS_LINE = (
    "  Créé le 2026-10-27 ; Rust ; 1250 étoiles ; cli, llm ;"
    " Prudence : créé il y a moins de 7 jours, aucune licence reconnue par GitHub"
)


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
        'model: "gpt-6-luna"\n'
        "choice_failure: null\n"
        "request_id: 1b4e28ba-2fa1-4d2e-9b5c-6c8e1f0a7d3e\n"
        "---\n"
        "\n"
        "# Tendances GitHub du 2026-11-01\n"
        "\n"
        "Période : fenêtres du 2026-10-28 au 2026-10-31 (4 fenêtres de 3 jours).\n"
        "\n"
        "Les rangs viennent de GH Archive, un échantillon d'environ 1 % des étoiles données"
        " sur GitHub (mesure du 2026-10-29) : des rangs proches ne se départagent pas. Les"
        " dates de création et les étoiles totales sont lues sur GitHub.\n"
        "\n"
        "## Choisis par le modèle\n"
        "\n"
        "gpt-6-luna n'en a retenu aucun sur 1 candidat.\n"
        "\n"
        "## Dépôts qui ressortent\n"
        "\n"
        "| Dépôt | Critères | Meilleur rang | Trajectoire (rang par fenêtre) | Créé le"
        " | Étoiles totales | Prudence |\n"
        "|---|---|---|---|---|---|---|\n"
        "| <https://github.com/owner/rising-repository> | nouveau, en accélération | 2"
        " | 12 → 7 → 4 → 2 | 2026-10-27 | 1250"
        " | créé il y a moins de 7 jours, aucune licence reconnue par GitHub |\n"
        "| <https://github.com/steady/tool> | durable | 3 | 3 → hors top → 5 → 9 | — | — | — |\n"
        "\n"
        "« durable » : dans le top 30 de 2 fenêtres sans jour commun, lues sur la période et les"
        " 2 fenêtres qui la précèdent (non affichées dans le tableau).\n"
        "\n"
        "Fenêtres manquantes : aucune.\n"
    )


def test_the_reading_of_durable_is_said_only_when_a_repository_is_durable():
    durable = make_report(repositories=[repository(criteria=["durable"])])
    not_durable = make_report(repositories=[repository()])

    assert "« durable » : " in render(durable)
    assert "« durable » : " not in render(not_durable)


def test_the_same_response_and_instant_give_the_same_bytes():
    assert render(make_report()) == render(make_report())


def test_the_stars_gained_are_never_written():
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

    assert " | 12 → — → 4 → 2 | " in render(report)


@pytest.mark.parametrize(
    "name", ["owner/www.site", "a-b/c_d.e", "Owner/.github", "o/repo.", "x/y-"]
)
def test_the_url_of_a_valid_name_is_an_autolink_written_as_it_is(name):
    report = make_report(repositories=[repository(repository_name=name)])

    assert f"| <{GITHUB_URL}{name}> |" in render(report)
    assert is_writable_url(f"{GITHUB_URL}{name}")


def test_the_report_of_a_day_is_located_once_under_veille_tendances():
    assert locate_report_file(Path("vault"), DAY) == ReportFile(
        vault_dir=Path("vault"),
        path=Path("vault/veille/tendances/2026-11-01.md"),
        name="veille/tendances/2026-11-01.md",
    )


def test_a_report_is_written_where_it_is_located(tmp_path):
    report_file = locate_report_file(tmp_path, DAY)

    write_trend_report_sheet(report_file, read(make_report()), GENERATED)

    assert (tmp_path / report_file.name).read_text("utf-8") == render(make_report())


def test_a_report_of_the_day_written_meanwhile_is_refused_and_kept(tmp_path):
    sheet = tmp_path / "veille" / "tendances" / "2026-11-01.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_bytes(b"read by Sabine\n")

    with pytest.raises(VaultEntryRefusedError) as refused:
        write_trend_report_sheet(
            locate_report_file(tmp_path, DAY), read(make_report()), GENERATED
        )

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
        refuse_written_sheet(locate_report_file(tmp_path, DAY))
    refuse_written_sheet(locate_report_file(tmp_path, date(2026, 11, 2)))


def test_before_the_request_a_folder_linked_elsewhere_is_refused(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    vault = tmp_path / "vault"
    (vault / "veille").mkdir(parents=True)
    elsewhere.mkdir()
    (vault / "veille" / "tendances").symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(VaultEntryRefusedError) as refused:
        refuse_written_sheet(locate_report_file(vault, DAY))

    assert str(refused.value) == (
        "vault_link_refused: veille/tendances is a symbolic link"
    )
    assert not (vault / "veille" / "tendances" / "2026-11-01.md").exists()


def test_the_candidates_left_out_by_github_are_counted_by_reason_after_the_table():
    report = make_report(
        candidates={
            "selected": 10,
            "read": 6,
            "dropped": {
                "not_found": 1,
                "unavailable_for_legal_reasons": 0,
                "moved": 2,
                "id_mismatch": 0,
                "forbidden": 1,
            },
        }
    )

    assert render(report).endswith(
        "Fenêtres manquantes : aucune.\n"
        "\n"
        "Candidats écartés par GitHub : 4 (introuvables : 1, renommés ou déplacés : 2,"
        " refusés : 1).\n"
    )


def test_every_reason_of_github_has_its_label():
    dropped = {
        "not_found": 1,
        "unavailable_for_legal_reasons": 1,
        "moved": 1,
        "id_mismatch": 1,
        "forbidden": 1,
    }
    report = make_report(candidates={"selected": 6, "read": 1, "dropped": dropped})

    assert render(report).endswith(
        "Candidats écartés par GitHub : 5 (introuvables : 1, bloqués : 1, renommés ou"
        " déplacés : 1, remplacés : 1, refusés : 1).\n"
    )


def test_the_labels_of_the_reasons_follow_the_dropped_candidates():
    assert list(DROP_REASON_LABELS) == list(DroppedCandidates.model_fields)


# The choice of the model (#368): a section before the repositories.
def find_choice_section(sheet):
    start = sheet.index("## Choisis par le modèle\n")
    return sheet[start : sheet.index("## Dépôts qui ressortent\n")]


def test_the_repositories_chosen_are_listed_with_their_criteria_and_subjects():
    alone = STEADY.model_copy(
        update={"repository_id": 99, "repository_name": "only/subject", "criteria": []}
    )
    report = make_report(
        candidates={
            "selected": 3,
            "read": 3,
            "dropped": make_report()["candidates"]["dropped"],
        },
        chosen=[
            choose(
                RISING, ["new", "accelerating", "watch_subject"], ["coding_assistants"]
            ),
            choose(STEADY, ["durable"]),
            choose(alone, ["watch_subject"], ["llm_security", "coding_assistants"]),
        ],
    )

    assert find_choice_section(render(report)) == (
        "## Choisis par le modèle\n"
        "\n"
        "gpt-6-luna en a retenu 3 sur 3 candidats :\n"
        "\n"
        "- <https://github.com/owner/rising-repository> : nouveau, en accélération ;"
        " sujet de la veille (coding_assistants)\n"
        f"{FACTS_LINE}\n"
        "- <https://github.com/steady/tool> : durable\n"
        f"{FACTS_LINE}\n"
        "- <https://github.com/only/subject> : sujet de la veille (llm_security,"
        " coding_assistants)\n"
        f"{FACTS_LINE}\n"
        "\n"
    )


def chosen_facts_line(**facts):
    """The line of facts of a repository chosen, its facts changed."""
    report = make_report(chosen=[choose(RISING)])
    report["chosen"][0]["facts"] |= facts
    return find_choice_section(render(report)).splitlines()[5]


def test_the_facts_of_a_repository_chosen_without_caution_name_its_license():
    assert chosen_facts_line(license="MIT", cautions=[]) == (
        "  Créé le 2026-10-27 ; Rust ; MIT ; 1250 étoiles ; cli, llm"
    )


def test_a_fact_github_does_not_give_is_left_out_of_the_line():
    assert chosen_facts_line(license=None, language=None, topics=[], cautions=[]) == (
        "  Créé le 2026-10-27 ; 1250 étoiles"
    )


@pytest.mark.parametrize(
    ("language", "written"),
    [
        ("[C](http://evil) | <b>#", "\\[C\\](http\\://evil) \\| \\<b\\>\\#"),
        ("www.evil.example", "www\\.evil.example"),
        ("a:: b", "a\\: \\: b"),
    ],
)
def test_the_language_of_a_repository_chosen_makes_neither_link_nor_field(
    language, written
):
    assert f" ; {written} ; " in chosen_facts_line(language=language)


def test_a_license_makes_no_link():
    assert " ; www\\.evil.example ; " in chosen_facts_line(
        license="www.evil.example", cautions=[]
    )


def test_a_language_of_spaces_alone_is_left_out_of_the_line():
    assert " ;  ; " not in chosen_facts_line(language="   ")


def test_the_day_of_creation_is_the_one_in_utc():
    line = chosen_facts_line(created_at="2026-10-27T23:30:00-05:00")

    assert line.startswith("  Créé le 2026-10-28 ; ")


def test_the_topics_of_a_repository_chosen_are_as_many_as_the_model_reads():
    topics = [f"topic-{number}" for number in range(MAX_TOPICS_FOR_SELECTION + 1)]

    line = chosen_facts_line(topics=topics)

    assert f"topic-{MAX_TOPICS_FOR_SELECTION - 1}" in line
    assert f"topic-{MAX_TOPICS_FOR_SELECTION}" not in line


def test_one_star_is_written_in_the_singular():
    assert " ; 1 étoile ; " in chosen_facts_line(stars_total=1)


@pytest.mark.parametrize(
    ("cautions", "said"),
    [
        (["created_recently"], "créé il y a moins de 7 jours"),
        (["no_license"], "aucune licence reconnue par GitHub"),
        ([], MISSING),
    ],
)
def test_the_table_says_the_cautions_of_a_repository(cautions, said):
    report = make_report()
    report["repositories"][0]["facts"]["cautions"] = cautions

    assert f" | 1250 | {said} |\n" in render(report)


def test_every_caution_has_its_label():
    assert set(CAUTION_LABELS) == set(CAUTIONS)


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("llm_timeout", "le modèle n'a pas répondu à temps"),
        ("llm_rate_limited", "le quota du modèle est atteint"),
        ("llm_unavailable", "le modèle est indisponible"),
        (
            "llm_invalid_output",
            "sa réponse n'a pas passé les contrôles, relance comprise",
        ),
        ("llm_truncated", "sa réponse a été coupée"),
        ("llm_content_filtered", "le filtre de contenu d'Azure a refusé la demande"),
    ],
)
def test_a_choice_that_failed_says_why_and_keeps_the_factual_report(state, reason):
    sheet = render(make_report(model=None, choice_failure=state))

    assert find_choice_section(sheet) == (
        f"## Choisis par le modèle\n\nChoix non fait : {reason}.\n\n"
    )
    assert "\nchoice_failure: " + json.dumps(state) + "\n" in sheet
    assert "\nmodel: null\n" in sheet
    assert "| <https://github.com/steady/tool> | durable |" in sheet


def test_without_any_candidate_read_the_choice_is_said_not_made():
    sheet = render(make_report(model=None, candidates=NO_CANDIDATE_READ))

    assert find_choice_section(sheet) == (
        "## Choisis par le modèle\n\nChoix non fait : aucun candidat lu.\n\n"
    )


# The texts of the repositories chosen (#369, docs/tendances.md, "Ce que rend #369").
def text_lines(criteria=None, watch_subjects=(), **writing):
    """The lines under the facts of RISING, chosen with this writing."""
    report = make_report(
        chosen=[
            choose(RISING, criteria, watch_subjects)
            | {
                "readme": "read",
                "texts": TEXTS,
                "texts_removed": [],
                "writing_failure": None,
            }
            | writing
        ]
    )
    lines = find_choice_section(render(report)).splitlines()
    return lines[lines.index(FACTS_LINE) + 1 : -1]


def test_the_texts_of_a_repository_chosen_are_written_under_its_facts():
    lines = text_lines(
        ["new", "watch_subject"],
        ["llm_security"],
        texts=TEXTS | {"watch_link": "Il touche à la sécurité des modèles."},
    )

    assert lines == [
        "  Secteur : Outil en ligne de commande.",
        "  Lien avec la veille : Il touche à la sécurité des modèles.",
        "  D'après son README : Selon son auteur, un outil pour les LLM.",
        "  Promesse : Il promet la rapidité.",
    ]


def test_a_readme_cut_is_said_by_its_label():
    assert (
        "  D'après le début de son README : Selon son auteur, un outil pour les LLM."
        in (text_lines(readme="cut"))
    )


def test_a_text_removed_is_said_not_retained_by_the_checks():
    lines = text_lines(
        texts=TEXTS | {"sector": None, "promise": None},
        texts_removed=["sector", "promise"],
    )

    assert lines == [
        "  Secteur : non retenu par les contrôles.",
        "  D'après son README : Selon son auteur, un outil pour les LLM.",
        "  Promesse : non retenu par les contrôles.",
    ]


def test_an_empty_text_has_no_line():
    assert text_lines(texts=TEXTS | {"promise": None}) == [
        "  Secteur : Outil en ligne de commande.",
        "  D'après son README : Selon son auteur, un outil pour les LLM.",
    ]


@pytest.mark.parametrize(
    ("readme", "said"),
    [("absent", "  README : absent."), ("refused", "  README : non servi par GitHub.")],
)
def test_a_readme_github_does_not_give_is_said_in_place_of_its_summary(readme, said):
    lines = text_lines(
        readme=readme,
        texts=TEXTS | {"readme_summary": None},
        texts_removed=["readme_summary"],
    )

    assert lines == [
        "  Secteur : Outil en ligne de commande.",
        said,
        "  Promesse : Il promet la rapidité.",
    ]


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        ("llm_timeout", "le modèle n'a pas répondu à temps"),
        ("github_unavailable", "GitHub indisponible"),
        ("github_timeout", "GitHub n'a pas répondu à temps"),
        ("github_rate_limited", "le quota de GitHub est atteint"),
        ("github_unauthorized", "GitHub a refusé le jeton"),
        ("github_forbidden", "GitHub a refusé 3 lectures"),
        ("github_invalid_response", "la réponse de GitHub n'a pas passé les contrôles"),
    ],
)
def test_a_writing_that_failed_says_why_in_one_line(state, reason):
    assert text_lines(**NOT_WRITTEN, writing_failure=state) == [
        f"  Textes non écrits : {reason}."
    ]


def test_every_failure_of_a_writing_has_its_reason():
    assert set(WRITING_FAILURE_REASONS) == set(WRITING_FAILURES)


@pytest.mark.parametrize(
    ("sector", "written"),
    [
        ("[C](http://evil) | <b>#", "\\[C\\](http\\://evil) \\| \\<b\\>\\#"),
        ("www.evil.example", "www\\.evil.example"),
        ("a:: b", "a\\: \\: b"),
        # On one line: the dash no longer starts a list.
        ("Deux" + chr(10) + "- lignes", "Deux - lignes"),
        ("- Une liste", "\\- Une liste"),
    ],
)
def test_a_text_of_the_model_makes_neither_link_nor_markup_in_the_vault(
    sector, written
):
    [line, *_] = text_lines(texts=TEXTS | {"sector": sector})

    assert line == f"  Secteur : {written}"


def test_a_trend_report_passes_the_check_of_the_download():
    """kb download-watch-sheets refuses the Markdown kb never writes: a report kb writes passes,
    its texts trapped."""
    trapped = "```dataview ~~~ ![x](https://a.example/p.png) <img src=x> <% tp %> `= this` &#x202E;"
    report = make_report(
        chosen=[
            choose(RISING)
            | {
                "readme": "read",
                "texts": dict.fromkeys(TEXTS, trapped),
                "texts_removed": [],
                "writing_failure": None,
            }
        ]
    )

    assert find_sheet_text_refusal(render(report).encode()) is None
