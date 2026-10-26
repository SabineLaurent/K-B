# Collecte sur données réelles — 2026-10-26

Compte rendu de #329 : les tests de bout en bout et la chaîne `kb collect` → `kb import` rejoués
sur les vraies sources après la refonte de l'ETL (PR #297), au premier temps (le Mac, sans
conteneur). Code de `main` au commit 7f9c5b7 (PR #338). La seule exécution réelle versionnée
avant celle-ci est celle du 2026-10-21 ([2026-10-21-collecte-reelle.md](2026-10-21-collecte-reelle.md)),
au commit 431637a. Chaque nombre vient de la sortie console d'une exécution, du rapport HTML des
tests, ou d'un `SELECT COUNT(*)` sur la base.

La chaîne tourne dans un dossier de données neuf et vide, en `0700`, ignoré par git. Zotero est la
bibliothèque de test. Les clips sont les 5 clips du coffre de `KB_VAULT_DIR`, copiés dans `raw/`
sans être modifiés. Le compte rendu ne cite ni titre, ni auteur, ni chemin.

## En bref

- **Rien n'est cassé par la refonte.** Les 11 tests de bout en bout passent. Les deux passages de
  la chaîne sortent en `0` (`SUCCEEDED`) à chaque commande, avec 0 rejet, aucune ligne
  `WARNING` ni `ERROR` à la console, et aucune correction de code.
- **La collecte incrémentale tient** : le 2e passage n'écrit aucun item ; l'import écarte 18 items
  déjà en base.
- **Les nombres suivent ceux du 21/10** : 3 035 items contre 3 022, l'écart venant des sources qui
  ont avancé en cinq jours (voir « Écarts avec le 21/10 »).
- **BigQuery** : 2 requêtes réelles, 134 Mo lues chacune, sur le quota gratuit de 1 Tio par mois.

## Tests de bout en bout

Lancés le 2026-10-26 avec la commande de
[2026-10-21-collecte-reelle.md](2026-10-21-collecte-reelle.md) (« Rejouer les tests de bout en
bout »). Le premier lancement (09:37:52 → 09:39:17 UTC) en passe 8 et en saute 3, faute de leur
variable dans `.env.e2e_test` (`KB_ZOTERO_DIR`, `KB_VAULT_DIR`, `GOOGLE_APPLICATION_CREDENTIALS`).
Ces trois variables ajoutées, les trois tests passent (09:43 UTC, `-k "zotero or clipping or gh_archive"`).

| Test | Codes (create-db, collect, import) | Items en base | Rejets | Lignes au-dessus d'INFO | Observé |
|---|---|---|---|---|---|
| `cisa_kev` | 0, 0, 0 | 1 756 `vulnerability` | 0 | 0 | — |
| `github_releases` | 0, 0, 0 | 400 `release` | 0 | 0 | 4 dépôts × 100 |
| `github_advisories` | 0, 0, 0 | 84 `advisory` | 0 | 0 | pip et npm |
| `github_most_starred` | 0, 0, 0 | 0 | 0 | 0 | 1 fichier de top dans le brut ; n'entre pas en base |
| `github_most_forked` | 0, 0, 0 | 0 | 0 | 0 | 1 fichier de top dans le brut ; n'entre pas en base |
| `arxiv_cscr_x_csai` | 0, 0, 0 | 559 `paper` | 0 | 0 | — |
| `tldr` | 0, 0, 0 | 226 `newsletter_article` | 0 | 0 | 1 min 02 s, la pause entre deux pages comprise |
| `zotero` | 0, 0, 0 | 5 `zotero_entry` | 0 | 0 | bibliothèque de test |
| `clipping` | 0, 0, 0 | 5 `clip` | 0 | 0 | — |
| `gh_archive` | 0, 0, 0 | 49 lignes de `trend` | 0 | 0 | 134 080 432 octets lus par BigQuery |
| export OpenTelemetry (`test_real_export.py`) | — | — | — | — | statut 200, export `SUCCESS` |

## Les deux passages de la chaîne

Dans un seul dossier de données neuf, l'un après l'autre : le 1er passage lance `kb create-db`,
`kb collect` sur toutes les sources (sans `KB_COLLECT_ONLY`), puis `kb import` ; le 2e, `kb collect`
puis `kb import`.

| Passage | Début (UTC) | `collect` | `import` | Bruts lus | Items écrits | Lignes de `trend` | Écartés | Rejets |
|---|---|---|---|---|---|---|---|---|
| 1 | 09:39:42 | 0 | 0 | 30 | 3 035 | 49 | 0 | 0 |
| 2 | 09:41:44 | 0 | 0 | 1 | 0 | 0 | 18 | 0 |

À chaque passage, `kb collect` rend `ok` pour les 16 sources : les 3 éditions TLDR, les 4 dépôts
des versions et les 2 écosystèmes des alertes comptent chacun pour une source. Au 2e passage :
TLDR ne redemande que le jour même (aucune édition publiée à 09:42 UTC), Zotero trouve un extrait
identique au dernier brut et ne l'écrit pas, et `gh_archive` ne lance aucune requête.

**Items par sorte après les deux passages**, comptés dans la base :

| Sorte | Items | Source |
|---|---|---|
| `vulnerability` | 1 756 | `cisa_kev` |
| `paper` | 559 | `arxiv_cscr_x_csai` |
| `release` | 400 | `github_releases` |
| `newsletter_article` | 226 | `tldr` |
| `advisory` | 84 | `github_advisories` |
| `zotero_entry` | 5 | `zotero` (et 6 lignes de `highlight`) |
| `clip` | 5 | `clipping` |
| **Total** | **3 035** | |

S'y ajoutent 49 lignes de `trend` et 31 lignes de `raw_data`. Le total du 1er passage est la somme
exacte des tests pris un à un, comme le 21/10.

**TLDR** : la fenêtre va du 19 au 26/10, soit 8 jours × 3 éditions. 15 éditions sont lues ; 9 sont
absentes (24 et 25/10, le week-end, et 26/10, pas encore publiée à 09:40 UTC).

## Écarts avec le 21/10

| | 21/10 (431637a) | 26/10 (7f9c5b7) | Pourquoi |
|---|---|---|---|
| Tests de bout en bout | 10 | 11 | `test_real_export.py` ajouté le 2026-10-24 (export OpenTelemetry) |
| `vulnerability` | 1 754 | 1 756 | 2 entrées de plus dans le catalogue KEV |
| `paper` | 551 | 559 | même départ (`ARXIV_FIRST_COLLECTION_START`, 2026-05-01), cinq jours de plus |
| `newsletter_article` | 223 | 226 | autre fenêtre de 8 jours |
| `release`, `advisory`, `zotero_entry`, `clip` | 400, 84, 5, 5 | identiques | — |
| `trend` | 49 lignes | 49 lignes | une fenêtre GH Archive |
| BigQuery, octets par requête | 147 Mo | 134 Mo | autre jour de GH Archive |

## Cas rencontrés

Aucun du côté des sources. Trois du côté de la mise en place, tous avant la première commande :

- **La base du `.env` datait du 2026-10-10**, à l'ancien schéma (8 tables, contre 16 pour une base
  neuve de 7f9c5b7), comme le disait #329. Le 1er passage tourne donc dans un dossier neuf ;
  l'ancien dossier reste intact.
- **`.env.e2e_test` n'était pas à la racine du dépôt**, et il lui manquait trois variables (voir
  « Tests de bout en bout »). Déplacé et complété par l'utilisatrice.
- **Le garde-fou des tests a tenu** : un second lancement s'est arrêté avant tout `kb` (code 4),
  parce que `.env.e2e_test` portait deux clés d'API (`KB_AI_API_KEY_KB_DIGEST`,
  `KB_DATA_API_KEY_AI_DIGEST`). Il les a nommées sans afficher leur valeur. Les deux lignes ont
  été retirées, puis les tests ont passé.

Deux constats sur l'API de données, faits le même matin, avant ce compte rendu, en lançant
`kb serve-data` sur la base du 2026-10-10 pour #210 :

- **Le journal dit `database_error: OperationalError` sans le nom de l'erreur SQLite** : c'est le
  manque relevé par la vérification de la certification du 2026-10-25 (gestion des erreurs de la
  base), observé ici sur un vrai cas.
- **`kb serve-data` démarre sur une base au mauvais schéma** et ne rend un 500 qu'à la première
  requête. Un contrôle du schéma au démarrage le refuserait (code 2). Aucune issue ne le couvre.

## Ce qu'on en conclut

- **La refonte de l'ETL n'a rien cassé sur les vraies sources** : mêmes codes de sortie, même
  forme des résultats, même somme exacte des sources prises une à une, aucun rejet.
- **L'incrémental est juste le même jour**, comme le 21/10.
- **Ce qui n'est pas mesuré ici** : les mêmes points que le 21/10 (une collecte le lendemain, une
  collecte après plusieurs jours manqués, le plafond de 2 000 papiers d'arXiv, #71).
- **Durée** : le 1er passage prend 88 s de collecte et moins d'une seconde d'import ; le 2e, 23 s
  de collecte.
