# La collecte arXiv : une fenêtre qui recule pour ne perdre aucun papier

Suite de [la commande `kb collect`](2026-09-30-commande-kb-collect.md) et de
[la collecte des releases GitHub](2026-10-02-collecte-releases-github.md).

- **Date** : 2026-10-02
- **Branche** : `feat/arxiv` (commits `e77d34d`, `84aec0d`)
- **Issue** : #12 « Collecter les nouveaux papiers arXiv sélectionnés »
- **Fichiers principaux** : `src/k_b/arxiv_source.py` (collecte), `src/k_b/arxiv_papers.py`
  (lecture), leurs tests, et la fixture `tests/fixtures/arxiv_extract.xml`.
- **Autres fichiers** : `src/k_b/collect.py` (la source est ajoutée à `SOURCES`),
  `docs/specs-collecte.md` (état de la source), `docs/ADR/journal-decisions-projet.md`.

## Le pourquoi

La veille arXiv de K-B suit la sécurité de l'IA : les papiers classés à la fois en `cs.CR` et en
`cs.AI` dont le résumé contient un des 8 mots-clés décidés dans #6, soit environ 20 papiers par
semaine. Elle sert à repérer les papiers à lire, qu'on range ensuite dans Zotero.

L'issue demande deux choses : récupérer les métadonnées et le résumé par l'API arXiv, et reprendre
l'ingester de `brief09_assistant-veille-tech` **en corrigeant son bug de watermark**. Dans
brief09, le watermark est la date la plus récente déjà en base. Il avance sur ce que la collecte
a vu, pas sur ce qui existe, si bien que des papiers passent derrière lui et ne sont jamais
collectés. K-B ne reprend pas ce mécanisme : il le remplace (voir « La fenêtre »).

## Le comment

### Une source comme les autres

`ArxivSource` respecte le contrat `Source` de `collect.py` : un `name`, une `extension` et une
méthode `fetch(last_collected_at)` qui renvoie le brut, ou `None` s'il n'y a rien de neuf. Tout le
reste vient de `kb collect` : l'écriture du brut dans `raw/automation/arxiv/<horodatage>.xml`,
l'isolement des pannes, et la date de dernière collecte, qui n'avance **que si `fetch` réussit**.

```python
class ArxivSource:
    name = "arxiv"
    extension = "xml"
```
(`src/k_b/arxiv_source.py:34-36`)

L'extension est `xml` parce que l'API ne répond qu'en Atom, un format de flux écrit en XML.
Elle n'a pas d'option JSON, et la règle du brut intact interdit de convertir le flux avant de
l'écrire.

### La fenêtre : la correction du bug de watermark

```python
now = datetime.now(UTC)
if last_collected_at is None:
    window_start = FIRST_COLLECTION_START
else:
    window_start = last_collected_at - ANNOUNCEMENT_DELAY_MARGIN
raw_response = download(build_search_query(window_start, now))
```
(`src/k_b/arxiv_source.py:47-51`)

Le seul filtre de date de l'API est `submittedDate`, la date de **soumission**. Or un papier
n'apparaît dans l'API qu'au moment de son **annonce**. Un papier soumis le jeudi à 15 h (heure de
New York) n'est annoncé que le dimanche à 20 h. Si une collecte tourne le vendredi, il n'est pas
encore visible. Si la collecte suivante partait du vendredi, il serait hors fenêtre : perdu pour
toujours, sans aucun message.

La fenêtre part donc de **7 jours avant** la dernière collecte réussie. Ces 7 jours couvrent le
délai normal d'annonce (3,5 jours au plus) et les jours fériés. En contrepartie, deux bruts
successifs se recouvrent. Ce n'est pas un problème : la fusion dédoublonne déjà par identifiant
arXiv (`docs/specs-collecte.md`, « Du brut au jeu d'items »).

La première collecte, sans date précédente, remonte au **01/05/2026**, début de la formation de
Sabine (`FIRST_COLLECTION_START`). Choix de Sabine : la base et la liste de lecture Zotero
démarrent avec un vrai passé, 488 papiers et 1,2 Mo, mesurés par un appel réel le 2026-10-02.
Ça tient largement dans une page de 2 000.

### La requête

```python
return (
    f"cat:cs.CR AND cat:cs.AI AND ({keywords}) AND submittedDate:[{submission_window}]"
)
```
(`src/k_b/arxiv_source.py:69`)

Les mots-clés de plusieurs mots passent entre guillemets (`abs:"prompt injection"`), les autres
sans (`abs:jailbreak`). Les dates suivent le format de l'API, `AAAAMMJJHHMM` en GMT : `now` est en
UTC, et `last_collected_at` aussi, puisque `kb collect` refuse une date sans fuseau. La chaîne est
encodée par `urlencode` (`:80`) et n'est jamais assemblée à la main dans l'URL.

### Échouer plutôt que perdre

```python
if total_results > paper_count:
    # Failing keeps the last collection date: the next collection asks again.
    raise ValueError(f"{total_results} papers found, only {paper_count} returned")
```
(`src/k_b/arxiv_source.py:54-56`)

On demande une page de 2 000 résultats, le maximum de l'API. Si l'API annonce plus de résultats
que la page n'en contient, la source échoue au lieu d'écrire un brut incomplet. Comme la date de
dernière collecte n'avance pas, la fenêtre entière est redemandée la fois suivante. C'est
l'inverse de brief09, qui avançait son watermark après une page plafonnée et perdait le reste.

Une réponse `503` ou un délai dépassé lève une exception de `urlopen`, avec le même effet : la
source est marquée en échec et réessayée au prochain `kb collect`.

### Lire le flux sans lui faire confiance

```python
PAPER_ID = re.compile(r"https?://arxiv\.org/abs/(\d{4}\.\d{4,5})v(\d+)")
```
(`src/k_b/arxiv_papers.py:16`)

`read_papers` transforme chaque `<entry>` en un `Paper` figé (`frozen=True`). Chaque champ est
vérifié : l'identifiant doit être celui d'un papier, et le titre, le résumé, au moins un auteur
et deux dates avec fuseau sont obligatoires. Une entrée qui ne passe pas est **rejetée et
journalisée** avec sa position, et les autres sont lues quand même, comme le veut la spec
(« une ligne illisible est rejetée et journalisée, pas devinée »).

L'identifiant est coupé en deux : `2609.33401` et la version `2`. L'URL est reconstruite sans
version (`https://arxiv.org/abs/2609.33401`, `:104`) au lieu de reprendre le lien du flux. C'est
la clé de dédoublonnage prévue par la spec, et ça évite de stocker une URL fournie par la réponse.

### Ce que la collecte refuse, et ce qu'elle laisse à la lecture

```python
for entry in entries:
    entry_id = (entry.findtext(f"{ATOM}id") or "").strip()
    if API_ERROR_ID.match(entry_id):
        raise ValueError(f"the arXiv API reports an error: {entry_id!r}")
return len(entries)
```
(`src/k_b/arxiv_papers.py:56-60`, dans `count_papers`)

`fetch` contrôle le flux avant de le renvoyer, mais **pas chaque papier**. Il refuse un document
qui n'est pas un flux Atom, un `totalResults` absent, et l'entrée par laquelle arXiv signale une
erreur (`id` en `http://arxiv.org/api/errors#…`). En revanche, il compte toutes les entrées,
valides ou non. La revue de code a montré pourquoi : si un seul papier mal formé faisait échouer
la collecte, la date n'avancerait pas, la fenêtre garderait ce papier, et toutes les collectes
suivantes échoueraient. Le papier mal formé entre donc dans le brut, et c'est la lecture qui le
rejette.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Fenêtre `submittedDate` qui part de 7 jours avant la dernière collecte | Seul filtre de date de l'API, et le retard d'annonce peut atteindre 3,5 jours, plus les jours fériés | Tri par `lastUpdatedDate` arrêté au watermark (brief09) : c'est la cause de la perte. Une fenêtre qui part de la dernière collecte : même perte |
| Une page de 2 000, échec si `totalResults` dépasse | Environ 40 papiers par fenêtre ; échouer garde la fenêtre entière | Pagination avec 3 s de pause : du code sans usage à ce volume |
| `503` ou délai dépassé : échec, réessayé au prochain `kb collect` | Le mécanisme existe déjà dans `collect.py` | Réessais dans la même exécution : plus de code, et une attente qui bloque les autres sources |
| `xml.etree` de la bibliothèque standard | Aucune dépendance ; l'expat embarqué (2.6.3) refuse l'expansion d'entités | `defusedxml` : une dépendance et une modification de `pyproject.toml` ; `lxml` (brief09) : une dépendance, sans gain ici |
| URL reconstruite depuis l'identifiant, sans version | Clé de dédoublonnage de la spec | Le lien `rel="alternate"` du flux : il porte la version, et c'est une donnée externe de plus à valider |
| Une seule requête, sans boucle sur des « topics » | Le filtre de #6 tient en une requête | Une requête par topic (brief09) : c'est là que naissait son watermark global à tous les topics |
| Une entrée mal formée entre dans le brut et est rejetée à la lecture ; une entrée d'erreur de l'API fait échouer la collecte | Un papier invalide ne bloque pas la source pour toujours (constat de la revue) | Refuser tout le flux pour une entrée : blocage permanent, puisque la fenêtre garde le papier |
| Dates de la fenêtre converties en UTC (`astimezone`) | L'API lit les dates en GMT, et l'état des collectes accepte une date avec un autre fuseau (constat de la revue) | Supposer la date déjà en UTC |
| `User-Agent` K-B, délai de 30 s, 6 Mo au plus (2 000 papiers pèsent environ 5,3 Mo), redirection hors de `https://export.arxiv.org/api/query` refusée | Règles communes de la spec (`specs-collecte.md`) | Imposé par le dépôt |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_recorded_response_gives_one_paper_per_entry` | Une réponse réelle enregistrée le 2026-10-02 (3 entrées extraites sur 35) donne identifiants, titres, résumés, auteurs et dates attendus |
| `test_a_revised_paper_keeps_its_version_apart_from_its_identifier` | Un papier `v2` garde son identifiant sans version ; `published` et `updated` diffèrent |
| `test_an_entry_that_is_not_an_arxiv_paper_is_rejected_and_logged`, `test_an_entry_with_a_missing_or_invalid_field_is_rejected_and_logged` | Autre domaine, identifiant sans version, titre vide, aucun auteur, date absente ou sans fuseau : rejetés et journalisés |
| `test_a_rejected_entry_does_not_hide_the_valid_ones` | Le rejet d'une entrée n'empêche pas de lire les suivantes |
| `test_a_feed_reporting_an_api_error_is_refused`, `test_an_api_error_answered_with_http_200_is_refused` | L'entrée d'erreur d'arXiv fait échouer la collecte |
| `test_a_page_with_an_invalid_entry_is_still_returned` | Un papier mal formé ne bloque pas la collecte |
| `test_the_window_is_written_in_utc_whatever_the_stored_time_zone`, `test_the_window_ends_now` | Fenêtre en GMT quel que soit le fuseau stocké ; fin de fenêtre à maintenant |
| `test_the_window_reaches_back_seven_days_before_the_last_collection` | Dernière collecte le 30/09 à 10 h 05 → fenêtre à partir du 23/09 à 10 h 05 |
| `test_a_first_collection_reaches_back_to_may_2026` | Sans collecte précédente, la fenêtre commence le 01/05/2026 à 00 h 00 UTC |
| `test_a_page_that_does_not_hold_every_result_is_refused` | `totalResults` supérieur à la page → échec, donc pas d'avance de la date |
| `test_a_redirection_away_from_https_export_arxiv_org_is_refused`, `test_a_response_larger_than_the_limit_is_refused` | Contrôles de la frontière réseau |
| Appel réel, `fetch` avec dernière collecte au 28/09 | L'API accepte la requête : 47 papiers, soumis du 21/09 au 01/10, lus sans erreur |
| `uv run pytest` | 146 tests verts, aucun appel réseau |
| Revue dans un sous-agent (`/code-review`, `/security-review`) | Aucune faille ; 5 constats corrigés avec l'accord de Sabine (entrée invalide bloquante, plafond de taille, UTC, spec, tests) |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas un watermark comme brief09 ?** Il avance sur ce que la collecte a vu. Un papier
   annoncé en retard, avec une date de soumission antérieure au watermark, n'est jamais repris.
   La fenêtre qui recule de 7 jours le reprend (`arxiv_source.py:50`).
2. **Les bruts se recouvrent : ce n'est pas du gaspillage ?** Environ 20 papiers en double par
   semaine, quelques dizaines de Ko. C'est le prix de « ne rien perdre en silence » ; la fusion
   dédoublonne par identifiant.
3. **Que se passe-t-il si arXiv tombe pendant la collecte ?** `urlopen` lève une exception ;
   `collect_all_sources` marque `arxiv` en échec sans arrêter les autres sources, et ne fait pas
   avancer sa date. La collecte suivante redemande la même fenêtre, élargie.
4. **Où est la sécurité, face à un XML hostile ?** Taille plafonnée à 6 Mo, domaine vérifié
   après redirection (`arxiv_source.py`, fonction `download`), parseur qui ne résout pas les entités externes, chaque
   champ validé et l'URL reconstruite (`arxiv_papers.py`, `parse_paper`). Le contenu (titres, résumés)
   reste une donnée : rien ne l'exécute ni ne l'interprète.
5. **Pourquoi garder les noms d'auteurs ?** Ils identifient le papier et sont publiés par les
   auteurs eux-mêmes ; c'est prévu par le registre des traitements (ligne API arXiv).

## Zones non vérifiées

- **La résistance d'expat aux attaques par expansion d'entités** (« billion laughs ») repose sur
  la documentation Python (« XML vulnerabilities » : expat 2.4.1 et ultérieur n'y est pas
  vulnérable), relue de mémoire et non revérifiée dans cette session. La version 2.6.3 a été
  constatée sur la machine de Sabine, pas sur l'image de la CI.
- **Le délai d'annonce** vient de la page arXiv « Availability of submissions ». La durée d'une
  mise en modération n'est pas publiée : la marge de 7 jours ne la couvre pas forcément.
- **La version `v2` dans la fenêtre** : on a constaté que l'API renvoie la dernière version d'un
  papier (`2609.33401v2`, soumis le 27/09, révisé le 29/09). On n'a pas vérifié si un papier
  révisé reste trié selon la date de sa v1.
- **L'entrée d'erreur** (`http://arxiv.org/api/errors#…`) vient du manuel de l'API et du
  relecteur ; on n'a pas provoqué d'erreur réelle pour vérifier son code HTTP.
- Le test de fin de fenêtre compare à l'horloge réelle, avec 2 minutes de tolérance.

## Ce qui reste

- **Lecture et fusion dans la base** : transformer les `Paper` en items et dédoublonner le
  recouvrement des fenêtres. C'est l'epic « Fusion et base » (#20), pas cette issue.
- **Révisions d'anciens papiers** : la `v2` d'un papier soumis avant la fenêtre n'est pas
  collectée (limite assumée, journal ADR).
- **Factoriser le téléchargement** : le bloc `urlopen` + contrôle de redirection + plafond de
  taille existe maintenant en trois copies (GitHub, CISA KEV, arXiv). La règle du dépôt demande
  de factoriser à la troisième ; fait dans une PR à part, validée par Sabine, pour garder
  celle-ci chirurgicale.
- **Mots-clés** : ils sont en dur dans `KEYWORDS`. Les changer passe par une PR, comme pour les
  dépôts suivis.
