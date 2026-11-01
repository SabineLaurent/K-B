# Collecter l'édition générale de TLDR (`tech`)

- **Date** : 2026-11-01
- **Branche** : `fix/tldr-tech-edition` (sans issue)
- **Fichiers** : `src/k_b/etl/sources/tldr.py`, `src/k_b/core/config.py`, `docs/specs-collecte.md`,
  `docs/fiches-veille.md`, `tests/etl/sources/test_tldr.py`, `tests/etl/test_source_kinds.py`
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

**Un sujet pour ses articles.** Une acquisition de DoorDash n'entrait dans aucun des huit sujets
des fiches. Sabine a ajouté un neuvième sujet (`src/k_b/core/config.py:307`) :

```python
    DigestSubject(
        "tech_industry",
        "entreprises, produits, plateformes et matériel de la tech, hors IA",
    ),
```

Il vient en dernier : un article qui relève de plusieurs sujets va au premier de la liste, donc un
sujet générique ne prend que ce qu'aucun sujet précis ne prend. Le schéma de classement envoyé au
modèle est construit à partir de cette liste : au plafond de 50 articles par appel, il passe à
50 × 10 = 500 valeurs d'`enum` (9 sujets plus `no_suitable_subject`), pile à la limite la plus
stricte connue, que tient `test_the_schema_of_a_full_batch_is_within_the_bounds_of_strict_mode`.

## Choix faits et options écartées

| Retenu | Écarté, et pourquoi |
|---|---|
| Nom d'édition facultatif dans le motif | Un second motif propre à `tech` : deux règles pour une seule forme de titre. Comparer le nom du `h1` au dossier : la spec l'a écarté le 12/10 (il faudrait une table « ai → AI ») |
| Test sur la page `ai` déjà en fixture, titre remplacé | Une fixture tirée d'une page `tech` : la structure est la même. La vraie page du 30/10 a été lue hors des tests (voir Preuve) |
| `tech` en dernier dans le tuple | En tête : `tldr_tech` passerait avant `tldr_ai`, et l'ordre de collecte des sources existantes changerait |
| Un sujet `tech_industry`, en dernier (Sabine) | Rien : les articles généraux finiraient en `no_suitable_subject`, coûtant un appel sans rien donner. Un sujet « autre » : écarté le 15/10 ; un article hors tech reste en `no_suitable_subject` |
| Pas de test neuf pour le sujet | Un test qui recopie la liste : les tests utilisent leur propre liste de sujets (`docs/fiches-veille.md`) ; ceux qui lisent la vraie (borne du schéma, nom réservé) tournent |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Avant le code, 3 échecs : `ValueError: first h1 is not an edition title with its date: 'TLDR 2026-10-07'`, puis `tldr_tech` absent des deux listes de sources | Les tests vérifient bien le manque |
| `test_the_general_edition_is_read_though_its_title_names_no_edition` | Un `h1` « TLDR 2026-10-07 » donne le même article qu'avec « TLDR AI 2026-10-07 » |
| Tests de refus du `h1` inchangés et verts (« … and more », page d'accueil, `2026-13-45`) | Le motif élargi ne laisse pas passer une page qui n'est pas une édition |
| `uv run pytest` : 3113 passés ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Rien d'autre n'a cassé |
| La vraie page `https://tldr.tech/tech/2026-10-30`, téléchargée le 01/11 et lue par `read_articles` | Pas de refus : 14 articles, dont le premier est « DoorDash to Buy Instacart… » |
| `TldrSource("tech").read_pages` en réel sur le 31/10 et le 30/10 | Le 31/10 : `no edition page, redirected to https://tldr.tech/tech`, sauté ; le 30/10 : la page |
| Schéma de classement mesuré avec 8 puis 9 sujets | 450 puis 500 valeurs d'`enum`, 6 850 puis 7 500 caractères : sous les limites, sans marge sur l'`enum` |

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
- Je n'ai lancé aucun `kb digest` réel avec le neuvième sujet : ni la limite de 500 valeurs
  d'`enum`, atteinte exactement, ni la durée (98 s mesurées pour 8 sujets, limite de 200 s) n'ont
  été vérifiées sur le modèle. Je n'ai pas mesuré non plus combien d'articles `tech` iront à
  `tech_industry`, et combien à `no_suitable_subject`.

## Ce qui reste

- Les autres éditions candidates (`it`, `design`, `devops`, `data`, `hardware`) ne sont pas
  suivies. Pour chacune, il faudrait vérifier la forme de son `h1` avant de l'ajouter.
- Les documents datés (`docs/2026-10-04-flux-donnees.md`…) citent encore trois éditions. Ce sont
  des instantanés, je ne les ai pas modifiés.
- Un dixième sujet ferait passer le schéma à 550 valeurs d'`enum` : le test échouerait, et il
  faudrait des lots de moins de 50 articles.
