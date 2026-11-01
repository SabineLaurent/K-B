# Collecter l'édition générale de TLDR (`tech`)

- **Date** : 2026-11-01
- **Branche** : `fix/tldr-tech-edition` (sans issue)
- **Fichiers** : `src/k_b/etl/sources/tldr.py`, `src/k_b/core/config.py`, `docs/specs-collecte.md`,
  `tests/etl/sources/test_tldr.py`, `tests/etl/test_source_kinds.py`
- **Série** : [lecture des articles TLDR](2026-10-12-lecture-articles-tldr.md),
  [refuser une page qui n'est pas l'édition](2026-10-20-refuser-une-page-tldr-qui-n-est-pas-l-edition.md)

## Le pourquoi

TLDR publie une newsletter générale, sur la tech en général : `https://tldr.tech/tech/<date>`. On y
trouve les rubriques « Big Tech & Startups », « Science & Futuristic Technology » et
« Programming, Design & Data Science ». Elle faisait partie des neuf éditions candidates
(`docs/sources-detaillees.md`), mais K-B n'en suivait que trois : `ai`, `infosec` et `dev`.

Il ne suffisait pas de l'ajouter à la liste. Son titre ne nomme pas d'édition : « TLDR 2026-10-30 »,
alors que les autres s'intitulent « TLDR AI 2026-10-30 ». Le lecteur refusait donc chacune de ses
pages. La spécification le prévoyait comme limite : « forme non observée ; à vérifier quand une
édition est ajoutée ».

## Le comment

**Le titre lu dans la page.** Le lecteur tire la date de l'édition du premier `h1`, et refuse une
page dont le `h1` n'a pas la forme d'un titre d'édition (`src/k_b/etl/sources/tldr.py:187`) :

```python
EDITION_PAGE_TITLE = re.compile(r"TLDR (?:.+ )?(\d{4}-\d{2}-\d{2})")
```

Avant, le motif était `r"TLDR .+ (\d{4}-\d{2}-\d{2})"` : `.+ ` exigeait au moins un caractère,
puis une espace, entre « TLDR » et la date. Le groupe `(?:.+ )?` rend ce nom facultatif, sans
capture (`?:`), si bien que la date reste le groupe 1, lu par `read_edition_date`. Le motif est
appliqué par `fullmatch` (`tldr.py:248`) : la date doit toujours finir le titre. « TLDR AI
2026-10-07 and more » et la page d'accueil (« Keep up with AI in 5 minutes ») restent refusés.

**L'édition suivie.** Ajouter une édition, c'est ajouter son slug (`src/k_b/core/config.py:32`) :

```python
TLDR_TRACKED_EDITIONS = ("ai", "infosec", "dev", "tech")
```

Chaque slug devient une source `tldr_<slug>` (`src/k_b/etl/source_kinds.py:80`), collectée après
les autres : `tldr_tech` arrive en dernier, l'ordre des sources existantes ne change pas.

## Choix faits et options écartées

| Retenu | Écarté, et pourquoi |
|---|---|
| Nom d'édition facultatif dans le motif | Un second motif propre à `tech` : deux règles pour une seule forme de titre. Comparer le nom du `h1` au dossier : la spec l'a écarté le 12/10 (il faudrait une table « ai → AI ») |
| Test sur la page `ai` déjà en fixture, titre remplacé | Une fixture tirée d'une page `tech` : la structure est la même. La vraie page du 30/10 a été lue hors des tests (voir Preuve) |
| `tech` en dernier dans le tuple | En tête : `tldr_tech` passerait avant `tldr_ai`, et l'ordre de collecte des sources existantes changerait |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code, 3 échecs : `ValueError: first h1 is not an edition title with its date: 'TLDR 2026-10-07'`, puis `tldr_tech` absent des deux listes de sources | Les tests vérifient bien le manque |
| `test_the_general_edition_is_read_though_its_title_names_no_edition` | Un `h1` « TLDR 2026-10-07 » donne le même article qu'avec « TLDR AI 2026-10-07 » |
| Tests de refus du `h1` inchangés et verts (« … and more », page d'accueil, `2026-13-45`) | Le motif élargi ne laisse pas passer une page qui n'est pas une édition |
| `uv run pytest` : 3113 passés ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Rien d'autre n'a cassé |
| La vraie page `https://tldr.tech/tech/2026-10-30`, téléchargée le 01/11 et lue par `read_articles` | Pas de refus : 14 articles, dont le premier est « DoorDash to Buy Instacart… » |

## Ce que tu dois pouvoir défendre

- **Pourquoi `tech` n'était-elle pas collectée ?** Le choix des éditions date du 01/10 au 04/10 :
  `ai`, `infosec` et `dev`. Et même ajoutée, elle aurait été refusée, à cause de la forme de son
  titre (`tldr.py:187`).
- **Le motif élargi accepte-t-il des pages qu'il ne faut pas lire ?** Non : la date doit finir le
  titre (`fullmatch`). Et à la collecte, la date du `h1` doit être le jour demandé : une page d'un
  autre jour est refusée (`find_refusal`).
- **Risque de lenteur sur un `h1` piégé ?** `.+ ` revient en arrière au plus une fois par
  caractère du titre, ancré au début : le coût reste linéaire, comme avec l'ancien motif.
- **Quelle charge en plus ?** Une requête par jour demandé, week-end compris (un jour sans édition
  est redirigé), chacune précédée de la pause de 2 s. Une collecte quotidienne demande deux jours,
  car le jour de la dernière collecte est relu : environ 4 s de plus. La première collecte de
  `tldr_tech` remonte 7 jours.

## Zones non vérifiées

- Je n'ai lancé ni `kb collect` ni `kb import` en réel sur `tldr_tech`. La lecture a été vérifiée
  sur une seule page réelle, celle du 30/10.
- Je n'ai pas mesuré combien d'articles de culture tech générale recevront `no_suitable_subject`
  dans les fiches : la liste des huit sujets ne couvre pas, par exemple, une acquisition de
  DoorDash.

## Ce qui reste

- Les autres éditions candidates (`it`, `design`, `devops`, `data`, `hardware`) ne sont pas
  suivies. Pour chacune, il faudrait vérifier la forme de son `h1` avant de l'ajouter.
- Les documents datés (`docs/2026-10-04-flux-donnees.md`…) citent encore trois éditions. Ce sont
  des instantanés, je ne les ai pas modifiés.
