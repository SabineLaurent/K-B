# Collecte sur données réelles — 2026-10-21

Compte rendu de #25 : première exécution de bout en bout de `kb collect` et de `kb import` sur les
vraies sources, au premier temps (le Mac, sans conteneur). Code de la branche
`test/collect-real-sources`, partie de `main` au commit 431637a. Chaque nombre vient de la sortie
console ou du journal d'une exécution, ou d'un `SELECT COUNT(*)` sur la base d'essai.

Zotero est la bibliothèque Zotero réelle de Sabine, réduite pour le test (5 documents), lue par
une copie en lecture seule. Les clips viennent du coffre de développement : un dossier du dépôt ignoré par
git, tenu comme un vrai coffre. Rien n'a été écrit dans le vrai dossier de données. Chaque essai tourne dans un dossier neuf,
hors du dépôt, en `0700`. La sortie console, les codes de sortie et une copie de `logs/kb.log`
sont gardés sous ce dossier, hors de la rotation. Le compte rendu ne cite ni titre, ni auteur, ni
chemin.

## En bref

- **Tout est vert, sans aucun cas nouveau.** 10 tests de bout en bout, un par source, puis 3
  exécutions complètes et un `kb write-tops` : chaque commande sort en `0` (`SUCCEEDED`), avec 0
  rejet, 0 erreur non gérée et aucune correction de code.
- **Le critère « chaque cas rencontré est couvert par un test » est donc tenu sans test
  nouveau.** Les seuls tests ajoutés sont les tests de bout en bout et ceux de leur exclusion par
  défaut.
- **La collecte incrémentale tient.** Les 2e et 3e exécutions, le même jour, n'écrivent aucun
  item. Elles relisent 21 papiers arXiv, que l'import écarte comme doublons.
- **BigQuery** : 2 requêtes réelles, 147 Mo lues chacune, sur le quota gratuit de 1 Tio par
  mois.

## Tests de bout en bout, une source à la fois

Le test de chaque source (`tests/e2e/test_real_sources.py`) prend un `KB_DATA_DIR` neuf. Il lance
`kb create-db`, puis `KB_COLLECT_ONLY=<source> kb collect`, puis `kb import`. Il vérifie ensuite
le code de sortie de chacune et ce qui est arrivé en base. Lancés le 2026-10-21 entre 08:43 et
08:46 UTC :

| Source | Codes (create-db, collect, import) | Bruts lus | Items en base | Rejets | Observé |
|---|---|---|---|---|---|
| `cisa_kev` | 0, 0, 0 | 1 | 1 754 `vulnerability` | 0 | — |
| `arxiv_cscr_x_csai` | 0, 0, 0 | 1 | 551 `paper` | 0 | fenêtre depuis le 2026-05-01 |
| `tldr` | 0, 0, 0 | 15 | 223 `newsletter_article` | 0 | 3 éditions × 8 jours, 9 éditions absentes (17, 18 et 21/10) |
| `github_releases` | 0, 0, 0 | 4 | 400 `release` | 0 | 4 dépôts × 100 |
| `github_advisories` | 0, 0, 0 | 2 | 84 `advisory` | 0 | pip et npm |
| `github_most_starred` | 0, 0, 0 | 0 | 0 (relevé dans le brut) | 0 | n'entre pas en base |
| `github_most_forked` | 0, 0, 0 | 0 | 0 (relevé dans le brut) | 0 | n'entre pas en base |
| `clipping` | 0, 0, 0 | 5 | 5 `clip` | 0 | 5 clips lus, coffre de développement |
| `zotero` | 0, 0, 0 | 1 | 5 `zotero_entry` | 0 | bibliothèque Zotero réelle de Sabine, réduite pour le test (5 documents), 6 highlights |
| `gh_archive` | 0, 0, 0 | 1 | 49 lignes de `trend` | 0 | 1 fenêtre, 49 lignes |

## Les trois exécutions complètes

Les trois exécutions tournent dans un seul `KB_DATA_DIR` d'essai neuf, l'une après l'autre, le
même jour (décision de Sabine du 2026-10-21) : `kb collect` sur toutes les sources, sans
`KB_COLLECT_ONLY`, puis `kb import`. La 1re seule est précédée de `kb create-db`.

| Exécution | Début (UTC) | `collect` | `import` | Bruts lus | Items écrits | Lignes de `trend` | Écartés | Rejets |
|---|---|---|---|---|---|---|---|---|
| 1 | 08:46:31 | 0 | 0 | 30 | 3 022 | 49 | 0 | 0 |
| 2 | 08:48:01 | 0 | 0 | 1 | 0 | 0 | 21 | 0 |
| 3 | 08:48:22 | 0 | 0 | 1 | 0 | 0 | 21 | 0 |

À chaque exécution, `kb collect` rend `ok` pour les 16 sources : les 3 éditions TLDR, les 4
dépôts des versions et les 2 écosystèmes des alertes comptent chacun pour une source.

**Items par source après les trois exécutions**, comptés dans la base d'essai par sorte d'item :

| Sorte | Items | Source |
|---|---|---|
| `vulnerability` | 1 754 | `cisa_kev` |
| `paper` | 551 | `arxiv_cscr_x_csai` |
| `release` | 400 | `github_releases` |
| `newsletter_article` | 223 | `tldr` |
| `advisory` | 84 | `github_advisories` |
| `zotero_entry` | 5 | `zotero` (et 6 lignes de `highlight`) |
| `clip` | 5 | `clipping` |
| total | 3 022 | |

S'y ajoutent 49 lignes de `trend` (`gh_archive`). Les deux tables de référence en contiennent plus
que leurs items :
- `vulnerability` a 1 837 lignes, dont 1 754 liées à un item CISA KEV ; les autres sont citées
  par des alertes ;
- `publication` a 556 lignes, dont 551 liées à un item arXiv ; les autres sont citées par Zotero.

**Lignes extraites par les deux requêtes SQL**, relevées dans le journal :

| Requête | Exécution 1 | Exécution 2 | Exécution 3 |
|---|---|---|---|
| `EXTRACTION_QUERY` (Zotero) | 5 documents, 6 highlights | 5 documents, 6 highlights | 5 documents, 6 highlights |
| `TRENDS_QUERY` (GH Archive) | 49 lignes, 1 fenêtre (2026-10-20), 147 172 444 octets lus | non lancée | non lancée |

## `kb write-tops`

Lancé après la 3e exécution, dans le coffre de développement : un dossier du dépôt ignoré par git,
et non le coffre Obsidian de l'utilisatrice (vérifié avant le lancement). Juste avant, le brut des
deux tops a été copié à part (6 relevés, 3 par top), puisque `kb write-tops` supprime les relevés
antérieurs au dernier.

- Code de sortie : `0`.
- Fiches écrites : 2, une par top (`most_starred`, `most_forked`), toutes deux du 2026-10-21.
- Par top : 2 relevés sautés (`sheet_exists`, la fiche du jour existe déjà) et 2 relevés antérieurs
  supprimés ; il en reste 1 par top dans le brut.

## Cas rencontrés

**Aucun.** Aucune exécution n'a révélé de cas que les tests ne couvraient pas, et aucun code de
`src/` n'a été modifié. Quatre comportements sont observés ici sur vraies données pour la première
fois ; ils sont conformes au code et déjà couverts par ses tests :

1. **TLDR, jour sans édition** : la page demandée renvoie vers l'accueil de l'édition. C'est
   arrivé 9 fois, aux 17, 18 et 21/10 pour chacune des 3 éditions : le samedi, le dimanche et le
   jour même à 08:43 UTC. Le journal le dit (`no edition page, redirected to …`), et la source
   reste `ok`.
2. **Versions GitHub, première collecte** : 100 versions par dépôt, soit la première page
   seulement (`RELEASES_PER_PAGE`, `src/k_b/etl/sources/github_releases.py:29`).
3. **arXiv, collecte suivante** : la fenêtre recule de 7 jours avant la dernière collecte
   (`ANNOUNCEMENT_DELAY_MARGIN`). Les 21 papiers relus sont écartés à l'import
   (`revision_not_newer`) : aucun doublon n'entre en base.
4. **Tops, plusieurs relevés le même jour** : la fiche du jour vient du premier relevé du jour
   encore dans le brut. Les suivants sont sautés, puis tous les relevés sauf le dernier sont
   supprimés (`write_top_sheets`, `src/k_b/etl/top_sheets.py:91-93`). La fiche garde donc le
   premier relevé du jour, et le brut le dernier.

## Ce qu'on en conclut

- **La chaîne collecte → import tient sur les dix sources réelles** dans une base vide. Pour
  chaque source, le nombre d'items en base est celui que l'import annonce. Le total de
  l'exécution 1 (3 022) est la somme exacte des dix tests pris un à un : collecter les sources
  ensemble ne change rien à ce que chacune apporte.
- **L'incrémental est juste le même jour** : les exécutions 2 et 3 n'ajoutent rien et ne
  rejettent rien. Les sources à état (Zotero, CISA KEV) n'écrivent aucun brut nouveau quand rien
  n'a changé, et `gh_archive` ne lance aucune requête quand aucune fenêtre n'est due.
- **Ce qui n'est pas mesuré ici** :
  - une collecte le lendemain, avec une fenêtre GH Archive due et de nouvelles éditions TLDR ;
  - une collecte après plusieurs jours manqués ;
  - le plafond de 2 000 papiers d'arXiv (#71). La première collecte depuis le 01/05 en rend 551 :
    le plafond n'est pas proche.
- **Coût** : 2 requêtes BigQuery, de 147 Mo chacune. À ce rythme, une collecte quotidienne lit
  environ 4,4 Go par mois, sur 1 Tio gratuit.
- **Durée** : la 1re exécution complète prend 84 s de collecte et moins de 10 s d'import ; les
  suivantes, 17 à 21 s de collecte.

## Rejouer les tests de bout en bout

`uv run pytest` (la commande de la CI) ne les lance pas : ils sont comptés « deselected »
(`tests/conftest.py`). Pour les lancer, sur le Mac, avec les variables des sources :

```
uv run --env-file .env pytest -m e2e -rs
```

Une source seule : `-k <source>`, par exemple `-k cisa_kev`. Le test de `gh_archive` lance une
requête BigQuery réelle. Une source dont la variable manque (`KB_ZOTERO_DIR`, `KB_VAULT_DIR`,
`GOOGLE_APPLICATION_CREDENTIALS`) est sautée, et la raison nomme la variable. Au deuxième temps,
la même commande tournera dans le conteneur, sans `--env-file`, les variables venant de
l'environnement du conteneur (#200).

## Sources

| Source | URL | Consultée le |
|---|---|---|
| pytest, « Control skipping of tests according to command line option » (marqueur déclaré dans `conftest.py`, tests écartés par `pytest_collection_modifyitems`), par Context7 | https://github.com/pytest-dev/pytest/blob/main/doc/en/example/simple.rst | 2026-10-21 |
| pytest, « Registering custom markers », par Context7 | https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/writing_plugins.rst | 2026-10-21 |
| uv, « Environment variable files » (l'environnement prime sur `--env-file`), par Context7 | https://docs.astral.sh/uv/concepts/configuration-files | 2026-10-21 |
| Volumes et quota BigQuery de K-B | [`docs/bigquery.md`](bigquery.md) | 2026-10-21 |
