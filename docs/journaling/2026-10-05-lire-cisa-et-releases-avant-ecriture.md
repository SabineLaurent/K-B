# Lire le catalogue CISA et la page de releases avant de les écrire

- **Date** : 2026-10-05
- **Branche** : `fix/validate-cisa-and-releases-before-writing`
- **Issue** : #53
- **Fichiers principaux** : `src/k_b/cisa_kev_source.py`, `src/k_b/github_releases_source.py`,
  leurs tests, et `docs/specs-collecte.md`.
- **Notes liées** : [collecte CISA KEV](2026-09-30-collecte-cisa-kev.md),
  [releases GitHub](2026-10-02-collecte-releases-github.md).

## Le pourquoi

Une source de K-B a deux temps : `fetch` télécharge la réponse et la renvoie, puis `collect.py`
l'écrit telle quelle dans `raw/automation/` et avance la date de dernière collecte. arXiv, les
alertes et les dépôts les plus étoilés lisaient déjà leur réponse dans `fetch` avant de la
renvoyer. CISA ne la lisait jamais, et les releases ne la lisaient pas à la première collecte.

Conséquence : une réponse 200 qui n'est pas le contenu attendu (page de maintenance, captcha,
objet d'erreur JSON) était écrite comme un `.csv` ou un `.json`, et la date avançait comme si
tout allait bien. L'erreur n'apparaissait qu'à la lecture, loin de sa cause. Le principe du dépôt
est de valider une entrée externe **à la frontière** : ici, dans `fetch`, avant toute écriture.

## Le comment

### 1. CISA : lire le catalogue, puis le renvoyer intact

`src/k_b/cisa_kev_source.py:31-39`

```python
        try:
            raw_catalog = download(CATALOG_URL, TRUSTED_URL_PREFIX, MAX_CATALOG_BYTES, headers)
        except HTTPError as error:
            ...
        read_new_vulnerabilities(raw_catalog, last_collected_at=None)
        return raw_catalog
```

`read_new_vulnerabilities` est le lecteur existant du catalogue (`cisa_kev.py`). Son résultat
n'est pas gardé : on l'appelle **pour ses exceptions**. S'il lève, `fetch` lève, et rien n'est
renvoyé. `last_collected_at=None` lui fait lire **toutes** les lignes, pas seulement les
nouvelles : le contrôle porte donc sur le catalogue entier. Ce qui est renvoyé est l'octet près
ce qui a été reçu : la règle du brut intact est tenue.

### 2. Releases : lire la page avant le cas de la première collecte

`src/k_b/github_releases_source.py:31-35`

```python
        # Read even at the first collection: a page that is not a list of releases raises.
        releases = read_releases(raw_response, self.repository)
        if last_collected_at is None:
            return raw_response
        publication_dates = [release.published_at for release in releases]
```

Avant, `read_releases` n'était appelé qu'**après** le `return` de la première collecte. Il suffit
de le remonter d'une ligne. Le résultat sert ensuite au calcul des dates de publication, comme
avant : la page n'est lue qu'une fois.

### 3. Pourquoi une exception suffit à « faire échouer la source »

Rien n'a changé dans `collect.py` : `collect_all_sources` entoure déjà chaque source d'un
`try/except Exception`. Une exception dans `fetch` y est journalisée, la source est marquée en
échec, **aucun brut n'est écrit** (l'écriture vient après `fetch`), et sa date n'est pas avancée.
Les autres sources continuent.

### 4. Quelles exceptions

Presque toutes sont des `ValueError` ou en dérivent :
- `cisa_kev.py:39` décode en `utf-8-sig` : un contenu non UTF-8 lève `UnicodeDecodeError`, une
  sous-classe de `ValueError` ;
- un CSV sans les colonnes attendues lève `ValueError("catalog without the columns …")` ;
- `github_releases.py:27` : `json.loads` lève `JSONDecodeError` (sous-classe de `ValueError`) sur
  un contenu qui n'est pas du JSON, puis `ValueError("expected a list of releases")` si ce n'est
  pas une liste.

Exception : un CSV mal formé peut aussi lever `csv.Error`, qui ne dérive pas de `ValueError`
(constat de la revue). La source échoue quand même, car `collect.py` rattrape toute
`Exception` ; seule la docstring de `fetch`, qui ne cite que `ValueError`, est trop étroite.

## Choix faits et options écartées

| Choix | Retenu parce que | Écarté |
|---|---|---|
| Réutiliser les lecteurs existants | la connaissance du format vit à un seul endroit (règle DRY du dépôt) | **Un contrôle de forme propre à `fetch`** (première ligne du CSV, type JSON) : il dupliquerait cette connaissance, et les deux pourraient diverger |
| Échouer sur une seule ligne ou release invalide | les lecteurs actuels lèvent dès un élément mal formé ; on échoue fermé (règle de sécurité du dépôt) | écarter l'élément et continuer : c'est #61, hors de cette issue |
| Lire tout le catalogue CISA (`last_collected_at=None`) | une ligne ancienne mal formée est aussi le signe d'un catalogue douteux | ne lire que les lignes récentes : laisserait passer un catalogue corrompu en partie |

La conception a été validée par Sabine sur l'issue #53 avant le code, limite comprise.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_page_that_is_not_the_catalog_fails_the_collection` (`tests/test_cisa_kev_source.py`) | une page HTML servie en 200 fait lever `ValueError` (« catalog without the columns ») dans `fetch` |
| `test_a_page_that_is_not_a_list_of_releases_fails_the_first_collection` (`tests/test_github_releases_source.py`) | à la première collecte, un objet JSON (`{"message": "Not Found"}`) fait lever `ValueError` |
| les deux tests ont échoué avant le code | ils testent bien le nouveau comportement |
| `CATALOG` des tests CISA remplacé par la fixture enregistrée `cisa_kev_extract.csv` | l'ancien `CATALOG` n'avait que deux colonnes : désormais lu, il aurait fait échouer les tests existants ; la fixture est un vrai extrait |
| `uv run pytest` : 175 tests passés | rien d'autre n'est cassé |

## Ce que tu dois pouvoir défendre

1. **Pourquoi valider dans `fetch` et pas à la transformation ?** Parce que c'est la frontière :
   après `fetch`, le contenu est écrit et la date avance. Valider plus tard, c'est découvrir
   l'erreur loin de sa cause, avec une fenêtre de collecte déjà sautée (`cisa_kev_source.py:38`).
2. **Le brut reste-t-il intact ?** Oui : on renvoie `raw_catalog` et `raw_response` tels que
   reçus. La lecture ne sert qu'à contrôler (`cisa_kev_source.py:39`, `github_releases_source.py:34`).
3. **Une seule release mal formée fait-elle échouer toute la source ?** Oui, jusqu'à #61. C'est
   plus strict que le critère de l'issue, accepté par Sabine : on préfère refuser que stocker un
   contenu douteux.
4. **Que se passe-t-il à la collecte suivante ?** La date n'ayant pas avancé, la même fenêtre est
   redemandée. Si la panne de la source persiste, la source échoue à chaque fois, visiblement,
   dans le résumé de `kb collect`.
5. **Et si CISA répond 304 ?** Rien n'est lu ni écrit : le 304 est traité avant la lecture
   (`cisa_kev_source.py:34-36`), comme avant.

## Zones non vérifiées

- Les pages de maintenance et captchas réels de cisa.gov et de l'API GitHub n'ont pas été
  observés : les tests utilisent une page HTML et un objet d'erreur écrits à la main.
- Le coût de la lecture complète du catalogue CISA (environ 1 Mo) à chaque collecte n'a pas été
  mesuré ; il est lu une fois en mémoire, comme à la transformation.

## Ce qui reste

- #61 : écarter et journaliser un élément invalide au sein d'une page valide, au lieu de faire
  échouer toute la source.
- #54 : refuser une redirection hors du préfixe de confiance avant de la suivre.
