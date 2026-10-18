# Choisir les sources collectées par `KB_COLLECT_ONLY`

- **Date** : 2026-10-18
- **Branche** : `feat/collect-only`
- **Issue** : #201
- **Fichiers principaux** : `src/k_b/cli.py`, `tests/test_cli.py`, `docs/specs-collecte.md`,
  `README.md`, `.env.example`, `src/k_b/etl/source_kinds.py` (commentaires seulement)
- **Série** : suit [Nommer les codes de sortie de kb](2026-10-18-nommer-les-codes-de-sortie-de-kb.md)
  (#193), qui a nommé `ExitCode.NOT_STARTED`, le code 2 utilisé ici.

## 1. Le pourquoi

Au POC du 25/10, la collecte est partagée entre deux machines. Le Mac collecte Zotero et les
clips, parce que ces deux sources lisent des fichiers personnels qu'on ne monte pas dans un
conteneur (journal ADR, « POC du 25/10 », décision 1). Les conteneurs collectent le reste. Or
`kb collect` lançait toutes les sources déclarées, sans moyen d'en choisir.

`KB_COLLECT_ONLY` est ce choix. Posée, elle ne laisse tourner que les sources nommées ; non posée,
la collecte reste exactement celle d'avant. Le nom vient d'une décision de Sabine du 18/10 : c'est
un filtre de `kb collect`, pas la définition des sources. L'issue disait d'abord `KB_SOURCES`.

## 2. Le comment

### 2.1 Le nom d'une source est le nom de son dossier

Une sorte de source (`SourceKind`) porte un `folder_prefix` : le nom de son dossier sous `raw/`.
C'est le nom que `KB_COLLECT_ONLY` accepte. On compare l'entrée à la liste construite au moment de
la vérification (`src/k_b/cli.py:471`) :

```python
folder_names = [kind.folder_prefix for kind in SOURCE_KINDS]
```

Il y a 9 noms : `cisa_kev`, `github_releases`, `github_advisories`, `github_most_starred`,
`arxiv_cscr_x_csai`, `tldr`, `zotero`, `clipping`, `gh_archive`. Un nom choisit toute sa sorte :
`tldr` lance toutes ses éditions (`tldr_ai`, `tldr_infosec`…).

La liste est lue dans `SOURCE_KINDS` à chaque appel, pas recopiée dans une constante. Ainsi, une
source ajoutée à `SOURCE_KINDS` devient un nom admis sans autre modification. Les tests en profitent :
ils remplacent `SOURCE_KINDS` par leurs propres sortes.

### 2.2 « Non posée » n'est pas « tout choisir »

`CollectOnly` (`src/k_b/cli.py:412-419`) distingue deux états :

```python
folder_names: frozenset[str] | None

def is_collected(self, folder_name: str) -> bool:
    return self.folder_names is None or folder_name in self.folder_names
```

`None` veut dire « pas de filtre ». Pourquoi pas l'ensemble des 9 noms ? Parce que Zotero, les clips
et GH Archive ne sont pas créés à partir de `SOURCE_KINDS` : `cli.py` les crée quand leur variable
est posée. Sans filtre, ils doivent continuer à suivre cette seule règle. Le relecteur du plan l'a
montré : avec « tous les noms », les tests de Zotero et des clips, qui remplacent `SOURCE_KINDS`,
auraient cassé.

`read_collect_only` rend `None` dans un autre sens, « refusé ». C'est le motif déjà suivi par
`read_serve_settings`. Il n'y a pas de confusion : le refus est un `None` à la place d'un
`CollectOnly`, et l'absence de filtre un `CollectOnly(None)`.

### 2.3 Lire une fois, vérifier tout, avant de collecter

`read_collect_only` (`src/k_b/cli.py:447-459`) découpe la valeur aux virgules une seule fois et
retire les espaces autour de chaque entrée :

```python
entries = tuple(entry.strip() for entry in value.split(","))
refusal = find_collect_only_refusal(entries, environ)
...
return CollectOnly(frozenset(entry.lower() for entry in entries))
```

La mise en minuscules se fait à deux endroits, chacun une fois : dans la boucle de vérification
(`name = entry.lower()`, `src/k_b/cli.py:474`) et pour l'ensemble retenu. `entries` garde la forme
tapée, sans les espaces autour, pour la citer dans un refus (`TLDR_AI` est cité `'TLDR_AI'`, pas
`'tldr_ai'`). La première revue avait relevé trois `.lower()` éparpillés. Un essai avec deux tuples
parallèles (`entries` et `names`) a été écarté à la seconde revue : deux appels d'une fonction pure
valent mieux qu'un second paramètre qui doit rester accordé au premier.

`find_collect_only_refusal` (`src/k_b/cli.py:462-485`) refuse, dans l'ordre :
- une valeur vide ou faite d'espaces (un seul élément vide après le découpage) ;
- une entrée vide (`zotero,`) ;
- un nom qui n'est pas un dossier de source ;
- une source choisie sans sa variable (`zotero` sans `KB_ZOTERO_DIR`).

Ce dernier cas répond à un fait relevé par le relecteur du plan. Si plus aucune source ne tourne,
`errors_by_source` est vide, et `find_collection_exit_code` rend 0, parce que `all([])` est vrai en
Python. Sans ce refus, `KB_COLLECT_ONLY=zotero` sans `KB_ZOTERO_DIR` sortirait avec 0 sans avoir rien
fait.

Le refus intervient avant `collect_all_sources` (`src/k_b/cli.py:426-428`) : ni brut ni
`collection_state.json` n'est écrit. Le refus va au journal, par `logger.error`, ouvert par `main`.

### 2.4 Une seule lecture de l'environnement

`run_collect` (`src/k_b/cli.py:422-444`) passe la même table, `os.environ`, aux trois fonctions :

```python
environ = os.environ
collect_only = read_collect_only(environ)
...
list_collected_sources(collect_only, environ),
```

La première version vérifiait les variables dans l'`environ` reçu, mais créait les sources en
relisant `os.environ`. En production, c'est le même objet. Mais la règle « ce qui est vérifié est
ce qui est utilisé » ne se lisait plus dans le code. C'est le constat 4 de la revue, corrigé.
Limite, écrite dans le commentaire : le client BigQuery lit lui-même `os.environ`, et pas cette
table. Une copie `dict(os.environ)` a été écartée pour cette raison : elle déplacerait l'écart au
lieu de le fermer.

### 2.5 Une ligne par source, même écartée

`print_skipped_sources` (`src/k_b/cli.py:509-519`) garde la règle « une ligne par source » de
`docs/specs-collecte.md` :

```python
for kind in SOURCE_KINDS:
    if not collect_only.is_collected(kind.folder_prefix):
        print(f"{kind.folder_prefix}: skipped (not in {COLLECT_ONLY_VARIABLE})")
for source_name, variable in VARIABLE_BY_SOURCE_NAME.items():
    if collect_only.is_collected(source_name) and not environ.get(variable):
        print(f"{source_name}: skipped ({variable} not set)")
```

Une source écartée par le filtre n'affiche que la première ligne, jamais aussi
`skipped (KB_ZOTERO_DIR not set)` : la seconde boucle ne regarde que les sources choisies. Le second
cas (« choisie, mais variable absente ») ne se produit qu'en l'absence de filtre, puisqu'avec un
filtre il est refusé en amont.

### 2.6 La citation d'une valeur reçue

Un nom refusé est cité par `quote_value` (`src/k_b/core/quoting.py`) : `repr`, puis une coupe à
100 caractères. Un nom qui contient un retour à la ligne ne peut donc pas écrire une fausse ligne de
journal. Les 9 noms de dossier listés dans le message sont des constantes du code, pas une entrée
(règle 3 de `.claude/rules/conventions.md`).

## 3. Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Nom de la variable | `KB_COLLECT_ONLY` : un filtre de `kb collect` (décision de Sabine, 18/10) | `KB_SOURCES` : laisse croire qu'elle définit les sources |
| Noms admis | `folder_prefix` (critère de #201) | `source.name` (`tldr_ai`) : n'existe pas pour Zotero, les clips et GH Archive avant leur création ; `source_code` : `github` regroupe trois sources (critère de #201) |
| Casse | Comparée en minuscules, entrée citée telle qu'écrite, sans les espaces autour (décision de Sabine, 18/10) | Comparaison exacte (plan d'origine) : `Zotero` échouait pour rien |
| Hôtes de l'API | `KB_DATA_API_ALLOWED_HOSTS` reste strict (`cli.py:155-158`) : `TrustedHostMiddleware` compare le `Host` reçu tel quel | Les aligner : une mise en minuscules y changerait ce que le contrôle de sécurité compare. Un nom de `KB_COLLECT_ONLY` ne fait que désigner un des 9 dossiers |
| Minuscules | Un `.lower()` dans la boucle de vérification, un pour l'ensemble retenu (seconde revue, tranché par time-knight) | Deux tuples parallèles gardés par `zip(strict=True)` : un paramètre de plus à garder accordé |
| Valeur vide | Refusée, code 2 (échouer fermé, comme `KB_DATA_API_ALLOWED_HOSTS`) | Vide = non posée, comme `KB_ZOTERO_DIR` : un filtre posé vide par erreur collecterait tout |
| Source choisie sans sa variable | Refusée, code 2 (décision de Sabine, option b) | (c) refuser seulement si rien ne tourne : `zotero,clipping` avec le coffre oublié sortirait 0 sans les clips ; (a) garder le saut : sortie 0 sans rien faire |
| Source écartée | Une ligne `skipped (not in KB_COLLECT_ONLY)` (décision de Sabine) | Rien afficher : le résultat ne dirait plus qu'un filtre a joué |
| Défaut dans `core/config.py` | Aucun : « toutes les sources » ne se nomme pas sans importer `etl`, ce que `core` ne fait pas (règle 5 de `conventions.md`) | Une constante de défaut : impossible sans remonter le courant des couches |
| Découpage aux virgules | Écrit à part de `split_allowed_hosts` : 2ᵉ occurrence, raisons de changer différentes (`code.md`, DRY) | Factoriser : touche `kb serve` pour un gain nul aujourd'hui |
| Signe Kelvin (`'K'.lower() == 'k'`) | Admis : le nom n'est comparé qu'aux 9 constantes (tranché par time-knight) | Refuser le non-ASCII : une règle de plus, sans risque à couvrir |

## 4. Preuve

| Test (`tests/test_cli.py`) ou sortie | Ce que ça démontre |
|---|---|
| `test_collect_only_runs_the_sources_chosen_and_keeps_the_date_of_the_others` | `zotero,clipping` ne lance que ces deux sources ; la date d'une source écartée reste dans l'état |
| `test_collect_without_collect_only_runs_every_source` | Sans la variable, tout est collecté, comme avant |
| `test_collect_only_prints_one_line_for_a_source_not_chosen` | Une seule ligne par source écartée, sans la ligne « variable non posée » |
| `test_collect_only_takes_the_names_with_spaces_around_in_any_case_and_twice` | Espaces, casse et doublons admis ; la source ne tourne qu'une fois |
| `test_collect_only_refuses_a_name_that_is_not_a_source_folder_and_quotes_it` | Nom inconnu : code 2, rien d'écrit, stdout vide, nom tronqué à 100 caractères et échappé (aucune fausse ligne) |
| `test_collect_only_quotes_a_name_refused_as_it_was_written` | Le refus cite `'TLDR_AI'`, la forme tapée |
| `test_collect_only_refuses_an_empty_value_or_entry` (4 cas) | Valeur vide, espaces, entrée vide : code 2, rien d'écrit |
| `test_collect_only_refuses_a_source_chosen_without_its_variable` (4 cas, dont `Zotero`) | Source choisie sans sa variable : code 2, rien d'écrit |
| Fixture `no_collect_only` ; `env` du test SIGTERM sans la variable | Un terminal qui exporte `KB_COLLECT_ONLY` ne fausse pas les tests |
| `uv run pytest -q` → 1756 passed ; `ruff check`, `ruff format --check`, `mypy --strict` verts | Rien d'existant n'est cassé |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi refuser `zotero` sans `KB_ZOTERO_DIR`, alors que sans filtre on saute simplement
   Zotero ?** Sans filtre, d'autres sources tournent toujours, et la ligne `skipped` le dit. Avec un
   filtre, un choix explicite qui ne peut pas tourner est un réglage faux. Et si c'était la seule
   source choisie, `all([])` ferait sortir avec 0 sans rien faire (`cli.py:482-484`).
2. **Pourquoi la casse ne compte pas ici, alors qu'elle compte pour les hôtes de l'API ?** Un nom
   de `KB_COLLECT_ONLY` ne fait que désigner un des 9 dossiers du code. Les minuscules ne peuvent
   rien élargir. Les hôtes de l'API, eux, sont comparés tels quels par `TrustedHostMiddleware` : un
   contrôle de sécurité qui ne doit pas être réinterprété (`cli.py:155-158`).
3. **Une valeur hostile dans `KB_COLLECT_ONLY` peut-elle toucher un fichier ou le journal ?**
   Non. Le nom n'est jamais joint à un chemin : il sert seulement à un test d'appartenance
   (`cli.py:418-419`). Un nom refusé est cité par `quote_value`, et un retour à la ligne ne peut pas
   forger une ligne. `/security-review` n'a rien relevé.
4. **Que devient la date d'une source écartée ?** Elle reste. `collect_all_sources` charge tout
   l'état et n'avance que les sources lancées. Le test 1 le vérifie.
5. **Pourquoi `None` dans `CollectOnly`, plutôt que la liste de toutes les sources ?** Zotero, les
   clips et GH Archive ne viennent pas de `SOURCE_KINDS`. « Pas de filtre » doit les laisser suivre
   leur variable, comme avant (§ 2.2).

## 6. Zones non vérifiées

- **Le chevauchement de deux collectes sur un même dossier de données.** Il n'a pas été testé. La
  revue de code l'a relevé, et le défaut existait avant #201 : chaque collecte réécrit tout
  `collection_state.json`, et la dernière l'emporte. Selon time-knight, le Mac et les conteneurs
  partagent l'état dès #200. Le correctif touche `etl/extract.py` : signalé, pas fait ici.
- **Le message de refus à l'échelle réelle.** Il liste les 9 dossiers ; les tests l'ont vérifié
  avec les sortes simulées seulement, pas avec le vrai `SOURCE_KINDS`.

## 7. Ce qui reste

- Le chevauchement de deux collectes (§ 6) : l'issue qui le portera reste à désigner par Sabine.
- Une liste d'exclusions (« tout sauf ») : une autre décision, hors de #201. Une source ajoutée
  plus tard à `SOURCE_KINDS` sera écartée des conteneurs tant que leur `KB_COLLECT_ONLY` ne la
  nomme pas.
- Pour #200 (compose) : ne pas passer `KB_COLLECT_ONLY` vide, sinon la collecte est refusée.
- Le message sur le jeton GitHub quand aucune source GitHub ne tourne : #63.
- La réécriture des codes de sortie dans `docs/specs-collecte.md:17` : #64.
