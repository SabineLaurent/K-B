# Écrire la fiche de l'installation et de l'environnement de développement

- Date : 2026-11-09
- Branche : `docs/installation-sheet`
- Issue : #502 ; plus un commit à part pour #507 (d8e37c1)
- Fichiers principaux : `documentation/installation_pour_docu.md` (neuf), `documentation/api_ia_pour_docu.md`
  (renvois recalés)
- Série : [2026-11-08-ecrire-la-fiche-des-tests.md](2026-11-08-ecrire-la-fiche-des-tests.md) et
  [2026-11-08-ecrire-la-fiche-de-l-api-ia.md](2026-11-08-ecrire-la-fiche-de-l-api-ia.md).

La note couvre les cinq commits de la branche : cde4c9e (la fiche), fefa5e0 (la fiche datée à `875c638`), d8e37c1
(la fiche de l'API IA recalée, commit à part), 040e724 (les 9 constats de la première relecture), fa36aa7 (les 2 de la
seconde). Les autres commits et fichiers que liste l'outil (`src/k_b/ai_api/`, `tests/`, `docs/fiches-veille.md`…)
sont ceux de #507 et #518, déjà sur `main` : ils ne sont pas de cette PR.

## Le pourquoi

Le référentiel demande une documentation de la configuration de l'environnement et de l'exécution des tests (C12),
et une documentation technique (C17). Qui reprend K-B doit installer son environnement de développement et de test,
avec ses dépendances, à partir d'un seul fichier. Les faits existaient dans le README (« Installer et lancer »),
`pyproject.toml`, `uv.lock` et `.env.example`, mais dispersés et sans dire qui lit quelle variable. Décision de
Sabine du 08/11 : une fiche neuve dans `documentation/`, écrite d'après le code, sans toucher à `docs/` ni au README.

## Le comment

### Ce que fait le code, pas ce qu'il fera

`documentation/installation_pour_docu.md:58-61` :

```markdown
`KB_DATA_DIR` nomme le dossier des données, hors du dépôt. Toutes les commandes le lisent, sauf `kb openapi`
(`main`, `cli.py`). **`kb` ne crée pas ce dossier** (#356, encore ouverte le 2026-11-09): s'il n'existe pas, la
commande s'arrête en code 2, avant tout travail, sur `error: KB_DATA_DIR is not an existing directory`
```

C'est l'ajout (a) de Sabine au plan. Le code le confirme, `src/k_b/commands/environment.py:38-42` :

```python
    if not Path(data_dir).is_dir():
        print(
            f"error: {DATA_DIR_VARIABLE} is not an existing directory", file=sys.stderr
        )
        return None
```

La fiche ne promet pas `kb init` (#356) : elle dit la limite et donne le `mkdir -p` qui la contourne. L'issue est
datée (« encore ouverte le 2026-11-09 ») parce qu'un état d'issue change : le lecteur sait quand il a été lu.

### Chaque fait a sa source, et une source externe sa date

`documentation/installation_pour_docu.md:43-47` dit ce que fait `uv sync --locked`, et d'où on le sait : la
documentation de uv lue par Context7, avec la version et la date. La version compte : Context7 donne la 0.13.5, K-B
installe la 0.13.6 (`.github/workflows/ci.yml:20`). La fiche le dit (« la dernière que donne Context7 ») pour que le
lecteur ne croie pas K-B en 0.13.5. La sortie de `uv lock --check` est datée du 2026-11-08 : elle n'a pas été
relancée depuis.

### Le tableau des variables : qui la lit, pas ce qu'elle vaut

`.env.example` dit le rôle et la forme de chaque variable ; la fiche n'y ajoute que ce qui manquait pour installer :
quelle commande la lit, et si elle est obligatoire. Chaque ligne est revérifiée dans le code. Exemple corrigé à la
relecture, `documentation/installation_pour_docu.md:109` : `KB_VAULT_DIR` est aussi exigée par les deux routines
(`src/k_b/commands/daily_routine_command.py:94`, `src/k_b/commands/digest_watch_command.py:108`). Et une exception,
`documentation/installation_pour_docu.md:100-101` : avec `--dry-run`, les routines s'arrêtent avant de lire un réglage
du job, `src/k_b/cli.py:109-113` :

```python
    if is_dry_run:
        # KB_DATA_DIR and KB_LOG_TO_FILE checked as for a run, then the steps printed: nothing run
        # nor logged, and no setting of the job read (the criterion of #413 runs it without them).
        print(ROUTINE_BY_COMMAND[command].describe())
        return ExitCode.SUCCEEDED
```

Aucune valeur n'est recopiée : `.env.example` est lu pour les noms seulement.

### Les dépendances : plancher, borne, version figée, rôle

Le tableau des 16 dépendances donne, pour chacune, le plancher du `pyproject.toml`, la borne haute s'il y en a, la
version de `uv.lock` et le module de K-B qui l'importe. `uv.lock` figure 96 paquets ; la relecture a relevé que K-B
lui-même n'a pas d'empreinte, `uv.lock:874-876` :

```toml
name = "k-b"
version = "0.1.0"
source = { editable = "." }
```

Un paquet installé depuis le dépôt, en mode éditable, n'a pas de fichier téléchargé à vérifier : la fiche le dit
(`documentation/installation_pour_docu.md:128-129`).

### Une limite se dit comme une limite

`documentation/installation_pour_docu.md:188-197` : `uv run --env-file .env` donne tout le `.env` à chaque commande
(le moindre privilège n'est pas tenu sur la machine), et une variable exportée par le profil du shell est lue comme
une variable du `.env`. La seconde phrase ajoutée à la relecture en tire une conséquence vérifiée : une variable de
libpq (`PGHOST`, `PGPASSWORD`…) fait refuser `KB_DATABASE_URL`, `src/k_b/database/location.py:132-137` :

```python
    libpq_variables_set = sorted(LIBPQ_VARIABLES & environ.keys())
    if libpq_variables_set:
        return (
            f"{', '.join(libpq_variables_set)} set: libpq reads these variables besides"
            f" {DATABASE_URL_VARIABLE}"
        )
```

### Le commit à part : la fiche de l'API IA recalée

La PR #524 (#518) a déplacé des lignes de `fidelity.py` et `checking.py` que cite `api_ia_pour_docu.md`. d8e37c1 la
recale : un seul commit de référence, `875c638`, pour tous ses renvois (`documentation/api_ia_pour_docu.md:10`), et
chaque `fichier:ligne` pointé à nouveau (par exemple `ai_api/stages/fidelity.py:150-185`, `check_claim`). Le texte
ne change pas : la seconde relecture a vérifié que le contrôle de fidélité décrit reste vrai après #524.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Une fiche neuve, `documentation/installation_pour_docu.md` | décision de Sabine du 08/11 : une fiche par documentation demandée | compléter le README : interdit par la même décision |
| Renvoyer à `tests_pour_docu.md` pour le détail des tests, mais donner les commandes | ajout (b) de Sabine : la procédure d'installation du test doit se lire ici ; le détail existe déjà | tout recopier : deux copies divergeraient |
| Un tableau « variable → qui la lit → obligatoire » | c'est ce qui manque pour installer | recopier le tableau du README, détaillé par commande (écarté au plan) |
| Dater chaque observation externe (Context7, `brew info`, état de #356, `uv lock --check`) | un fait externe change ; sa date dit quand il était vrai | une affirmation sans date : invérifiable plus tard |
| La phrase `--dry-run` sous l'intro du tableau | elle couvre `KB_VAULT_DIR` et le stockage d'échange d'un coup (tranché par time-knight) | « (sauf `--dry-run`) » dans une cellule : à répéter sur deux lignes |
| Recaler `api_ia_pour_docu.md` dans cette PR, en commit à part | ses renvois étaient faux sur `main` depuis #524 ; tranché par time-knight | une PR de plus pour 10 lignes |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `awk '/^```/{c=!c;next} !c' documentation/installation_pour_docu.md \| grep -cE "[^ ] [:;]( \|$)"` → `0` | la ponctuation de la fiche suit le choix 30 |
| script Python : 0 caractère `Cc` ou `Cf` hors tabulation et saut de ligne | aucun caractère invisible |
| chaque lien relatif ouvre un fichier qui existe (4 liens) | aucun renvoi mort |
| `git diff --stat --diff-filter=M origin/main -- docs/ README.md` → vide | aucun fichier existant de `docs/` ni le README modifié |
| première relecture (9 constats) puis seconde sur le delta (2 constats), tous corrigés, triés par time-knight | chaque fait ajouté ou corrigé est vrai à `875c638` |
| `gh issue view 356` → `OPEN` ; `brew info --json=v2 postgresql@18` → `18.6` | les deux observations datées de la fiche |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `kb` ne crée-t-il pas `KB_DATA_DIR` ?** Parce que le code ne le fait pas encore (#356) : la fiche
   décrit le code, pas son évolution. Ce que le code fait : un chemin qui n'existe pas, faute de frappe comprise,
   arrête la commande en code 2, et aucun dossier n'est créé (`src/k_b/commands/environment.py:38-42`).
2. **Pourquoi `uv sync --locked` en CI et `uv sync` sur la machine ?** `--locked` échoue si `uv.lock` ne correspond
   plus au `pyproject.toml` : la CI teste exactement les versions figées. Sur la machine, `uv sync` peut mettre le
   verrou à jour après un ajout de dépendance (`documentation/installation_pour_docu.md:39-47`).
3. **Où est la sécurité de l'installation ?** Le `.env` est ignoré par git, `kb` ne le charge jamais lui-même, une clé
   d'API fait au moins 32 caractères (`MIN_API_KEY_LENGTH`), les variables `OTEL_*` et de libpq sont refusées. La
   limite est écrite : `uv run --env-file` donne tout le `.env` à chaque commande.
4. **Pourquoi PostgreSQL 18 de Homebrew ?** La CI teste sur `postgres:18.6` ; la formule `postgresql@18` donne la
   même version majeure, sans conteneur (`documentation/installation_pour_docu.md:170-179`).

## Zones non vérifiées

- `uv lock --check` n'a pas été relancé après le 2026-11-08 ; sa sortie est datée dans la fiche.
- La documentation de uv lue est celle de 0.13.5, pas de 0.13.6 que K-B installe ; l'écart de comportement de
  `--locked` entre les deux n'a pas été vérifié.
- L'installation n'a pas été rejouée de bout en bout sur une machine vierge (`git clone` puis `uv sync`) : chaque
  commande est vérifiée dans le code et la documentation, pas exécutée dans l'ordre de la fiche.

## Ce qui reste

- L'installation par compose : #202, après #419, ajoutera sa section à la fiche.
- `kb init` (#356) : quand il existera, la section « Le dossier de données et la base » changera.
