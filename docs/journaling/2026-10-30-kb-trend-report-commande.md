# `kb trend-report` : demander le compte rendu des tendances, l'écrire, le noter au registre

- **Date** : 2026-10-30
- **Branche** : `feat/trend-report-command` (commits 53c4dc8, 60d2595, 17f7747, 41c07f7, a513f6d,
  1249481)
- **Issue** : #366, PR 2 sur 2 (`Closes #366`)
- **Série** : suit [l'API IA du compte rendu factuel](2026-10-30-api-ia-compte-rendu-factuel-tendances.md)
  (PR 1, `POST /trend-reports`) et [le contrat](2026-10-30-contrat-compte-rendu-tendances.md) (#364)
- **Fichiers principaux** : `src/k_b/commands/trend_report_command.py`,
  `src/k_b/post/trend_report_client.py`, `src/k_b/post/trend_report_registry.py`,
  `src/k_b/post/trend_report_sheets.py`, `src/k_b/post/ai_api_client.py`, `src/k_b/items.py`

## Le pourquoi

La PR 1 a donné à l'API IA une route qui calcule, sur les fenêtres de GH Archive, les dépôts
durables, nouveaux ou en accélération. Rien ne l'appelait. Cette PR écrit le côté `kb` :
la commande qui sait **quelle période demander** (celle qui suit le compte rendu précédent),
qui **relit la réponse comme une entrée non fiable**, l'écrit dans le coffre Obsidian
(`veille/tendances/<jour>.md`) et **note ce qu'elle a couvert** dans un registre, pour que le
compte rendu suivant reparte de là.

Le partage des rôles vient de la règle 7 de `poc.md` : l'API IA reste sans état (elle reçoit les
bornes de la période dans la demande), et seul `kb` lit le registre et écrit le coffre. Le coffre
n'est jamais relu pour retrouver le compte rendu précédent : le registre est la seule mémoire.

## Le comment

### 1. Une commande en étapes nommées

`src/k_b/commands/trend_report_command.py` (`run_trend_report`) se lit comme une recette :

```python
generated = read_now()
preparation = prepare_request(data_dir, environ, generated.date())
...
entry = make_entry(preparation.report_file, response, generated)
...
if not write_sheet(preparation.report_file, response, generated):
```

Chaque étape est une fonction qui rend soit son résultat, soit `None` (ou un `ExitCode`) après
avoir journalisé son échec. Le découpage n'est pas qu'esthétique : ruff mesure la complexité
(`C90`, seuil 10), et la commande écrite d'un bloc dépassait 13. L'instant du lancement est lu
**une fois** : il donne le jour du fichier, la date `generated` de l'en-tête et `written_at` du
registre. Relire l'horloge plus tard pourrait changer de jour à minuit entre le contrôle et
l'écriture.

L'ordre compte : tout ce qui peut refuser sans rien coûter passe avant la demande (coffre, clé,
registre, fichier du jour). Puis l'entrée du registre est **validée avant** l'écriture du fichier
(`make_entry`), pour qu'un refus n'arrive jamais après qu'un fichier est dans le coffre.

L'emplacement du fichier est un objet, `ReportFile` (`post/trend_report_sheets.py`) : le coffre,
le chemin complet et le chemin dans le coffre, calculés **une fois** par `locate_report_file` dans
`prepare_request`. Le contrôle d'avant la demande, l'entrée du registre (`file`), l'écriture et le
journal reçoivent le même objet : aucun ne recalcule le chemin, et l'écrivain n'accepte pas de
chemin libre (deuxième et troisième revues). Chaque échec après la réponse cite le `request_id`.

### 2. La réponse relue deux fois : par son schéma, puis contre la demande

`src/k_b/post/trend_report_client.py` déclare un schéma fermé (`TrendReportResponse`), puis des
contrôles croisés. Le schéma vérifie les types et les formes (un jour `AAAA-MM-JJ`, un rang de 1 à
30, un nom `owner/repo`). Les contrôles croisés vérifient ce qu'un schéma ne peut pas voir :
la cohérence avec la demande. Le plus important, `is_following` (`:150-162`) :

```python
if after is None:
    return not windows_capped
day_after = after + timedelta(days=1)
if windows_capped:
    return windows[0] > day_after and len(windows) == GH_ARCHIVE_MAX_CATCH_UP_WINDOWS
return windows[0] == day_after
```

La période doit partir du lendemain du compte rendu précédent, sauf si elle est plafonnée (au
plus 15 fenêtres) : alors elle compte exactement 15 fenêtres, plus récentes. Sans ce contrôle, une
réponse qui sauterait du 20 au 24 octobre ferait avancer le registre en perdant trois jours sans
que rien ne le dise (constat de la première revue). Les autres contrôles : fenêtres consécutives,
la dernière égale à la plus récente en base, aucune après le jour du lancement, chaque dépôt avec
une trajectoire alignée sur la période, un rang si et seulement s'il est dans le top, un meilleur
rang égal au minimum, des critères dans l'ordre, pas de « nouveau » quand il n'est pas évalué.

Un refus cite **la place et le contrôle**, jamais la valeur (`raise_invalid`,
`src/k_b/post/ai_api_client.py`) : un nom de dépôt n'arrive jamais dans un journal.

### 3. Le registre : un fichier d'état lu par un schéma fermé

`src/k_b/post/trend_report_registry.py:61-78` :

```python
try:
    content = (data_dir / TREND_REPORTS_FILENAME).read_bytes()
except FileNotFoundError:
    return []
...
return REGISTER.validate_json(content)
```

Absent, il vaut « premier compte rendu ». Présent, il est lu par `TypeAdapter(list[TrendReportEntry])`,
un modèle `extra="forbid"` qui refuse un champ en trop, une date mal écrite, une entrée dont la
première fenêtre suit la dernière ou qui en compte plus de 15 (`check_windows`, `:49`). Un registre
refusé arrête la commande en code 2, avant toute demande : un registre faux ferait demander une
période fausse. Il est réécrit en entier par `write_file_atomically` (règle 2 de `conventions.md`).

### 4. Le fichier : fait de valeurs vérifiées, pas de texte libre

`src/k_b/post/trend_report_sheets.py:187-198` :

```python
return (
    f"| <{GITHUB_URL}{repository.repository_name}> | {criteria}"
    f" | {repository.best_rank} | {trajectory} |"
)
```

Tout ce qui entre dans le fichier est fabriqué par le code : des dates, des entiers, des mots
d'une liste fermée (`CRITERION_LABELS`), et le nom du dépôt, validé par `is_repository_name`
(lettres ASCII, chiffres, `_ . -`, sans `.` ni `..`). Ce nom ne peut ni fermer le lien `<…>`, ni
ouvrir une cellule `|`, ni une syntaxe Obsidian. Il n'est **pas** passé par
`neutralize_digest_text` : cette fonction échappe `www.` en `www\.`, et une barre oblique inverse
est littérale dans un lien automatique ; le lien de `owner/www.site` aurait été cassé (constat de la
relecture du plan).

### 5. Ce qui a été rendu commun

- `Criterion` et `WindowState` passent de `ai_api/trajectories.py` à `items.py` (règle 4 de
  `conventions.md` : un type partagé par deux modules vit dans `items.py` ; `post` n'a pas le droit
  d'importer l'API IA). Ils restent des instructions `type`, pour que l'OpenAPI garde leurs noms.
- La règle « 15 fenêtres au plus » devient `has_too_many_windows` (`items.py:564`), lue par la
  demande, le registre et le client.
- `WrittenDayInStrictModel` (`items.py:216`) : dans un modèle strict, la garde `check_day_form` a
  déjà vu le texte `AAAA-MM-JJ`, et le mode strict refuserait ce texte comme date ; le champ est donc
  lâche sur ce seul point. Le mode strict accepte `"1761609600"` comme une date (essai du 30/10) :
  la garde reste indispensable.
- Le client HTTP de l'API IA (`post/ai_api_client.py`) devient commun aux deux commandes :
  `send_request`, `read_response` générique sur le schéma, la variable de la clé en paramètre
  obligatoire.
- La vérification de `KB_VAULT_DIR`, écrite trois fois, devient `read_vault_dir_or_refusal`
  (`etl/collected_sources.py:94`), à côté de la seule lecture de la variable.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté |
|---|---|---|
| Fichier nommé au jour du lancement | Seul jour connu avant la demande : un fichier présent est refusé sans rien demander (contrat ; confirmé par Sabine) | Le jour de la dernière fenêtre, connu après la réponse |
| Période non vide sans dépôt : le fichier est écrit | Le registre avance, l'absence est un résultat | Ne rien écrire : le compte rendu suivant relirait ces fenêtres |
| Trajectoire en rangs seuls | Les étoiles vues sont un échantillon d'environ 1 % ; des comptes proches sont dans le bruit | Un compte d'étoiles par point |
| Une clé de client neuve, `KB_TREND_REPORT` | Une clé par client : le journal de l'API nomme le bon client, révocation séparée | Réutiliser la clé de `kb digest` |
| Clé en paramètre **obligatoire** du client | Échouer fermé : un oubli enverrait en silence la clé des fiches | Une valeur par défaut `KB_DIGEST` |
| Même client HTTP que `kb digest` (lecture bornée à 240 s) | La route se borne à 60 s côté serveur | Un second jeu de délais |
| Entrée du registre validée avant le fichier | Un refus après l'écriture laisserait un fichier orphelin et une trace qui cite des valeurs (règle 5 de `poc.md`) | Valider après |
| Registre illisible → code 2 | Contrat et issue ; `kb collect` sort aussi en 2 sur un `collection_state.json` illisible | Code 1 |
| Base plus ancienne que le registre → avertissement, code 0 | Contrat (corrections du plan) | Un code d'échec |
| Fichier écrit, registre en échec → code 1, fichier gardé | Le compte rendu suivant reprend ces fenêtres ; limite dite | Effacer le fichier |
| Un seul `ReportFile` pour contrôler, noter et écrire | Le registre et le coffre ne peuvent pas désigner deux fichiers différents | Recalculer le chemin à chaque étape (1re version), ou le passer en `Path` libre (2e) |
| `read_vault_dir_or_refusal` dans `etl/collected_sources.py` | À côté de la seule lecture de `KB_VAULT_DIR` ; `run_log` n'importe plus l'ETL (BigQuery) | Dans `run_log` (1re version), ou dans un module bas de `commands/` qui importerait l'ETL |

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `uv run pytest` : 2 980 verts ; ruff, format, mypy `--strict` verts | Rien de cassé ailleurs, dont les tests d'architecture |
| `test_a_period_the_request_or_the_register_cannot_hold_is_refused` (16 cas) | Chaque contrôle de période refuse, cité par sa place |
| `test_a_repository_out_of_its_period_is_refused_by_its_place` | Les contrôles par dépôt, sans jamais citer le nom |
| `test_a_register_out_of_its_schema_is_refused_by_its_place` ; 15 fenêtres lues, 16 refusées | Le registre est une entrée relue, bornée comme la demande |
| `test_a_report_gives_its_period_its_limit_and_a_row_per_repository` | Le rendu exact, octet par octet |
| `test_the_url_of_a_valid_name_is_an_autolink_written_as_it_is` (dont `owner/www.site`) | Le lien n'est jamais cassé ni réécrit |
| `test_a_sigterm_after_the_report_keeps_it_and_leaves_the_register` | 143, fichier gardé, registre inchangé |
| `test_an_entry_the_register_would_refuse_writes_nothing_and_exits_1` | Aucun fichier écrit avant une entrée valide, `request_id` cité |
| `test_the_log_says_the_start_the_sheet_and_the_end_never_a_name` ; `test_a_response_refused_writes_nothing_and_never_quotes_a_name` | Aucun nom de dépôt dans le journal ni le bilan |
| Mutations sur une copie : 41/41, puis 9/9 et 3/3 sur les corrections | Chaque contrôle cassé exprès fait tomber un test |
| Revue de sécurité (xhigh) | Aucune vulnérabilité HIGH ni MEDIUM |
| Trois revues de code (medium) : 7, 8 et 7 constats ; 13 corrigés, 9 écartés avec leur raison (tri dans la PR) | Chaque correction a commencé par son test rouge |

## Ce que tu dois pouvoir défendre

1. **Pourquoi relire la réponse d'une API que tu as écrite ?** Elle traverse le réseau et peut
   changer sans que `kb` change : c'est une entrée non fiable (OWASP API10). Une réponse fausse
   ferait reculer, sauter ou gonfler le registre ; le refus arrive avant toute écriture
   (`trend_report_client.py:108`).
2. **Que se passe-t-il si la commande est tuée entre le fichier et le registre ?** Le fichier
   reste, le registre n'avance pas. Relancée le même jour : code 2 (fichier présent). Le
   lendemain : un compte rendu reprend ces fenêtres. Limite assumée, dite dans la doc.
3. **Comment un nom de dépôt piégé pourrait-il atteindre Obsidian ?** Il ne peut pas : il passe
   `is_repository_name` à la lecture, puis il n'entre que dans un lien vers github.com dont les
   caractères sont tous inertes (`trend_report_sheets.py:187`).
4. **Pourquoi un registre et pas une relecture du coffre ?** Le coffre est en écriture seule pour
   `kb` ; un fichier déplacé ou modifié par Sabine ne doit pas changer la période. Le registre est
   un état que seul `kb` écrit, sous `KB_DATA_DIR` (règle 4 de `poc.md`).
5. **Pourquoi des types déplacés dans `items.py` ?** `post` n'importe pas l'API IA (test de
   couches) : sans ce déplacement, deux `Literal` auraient divergé un jour.

## Zones non vérifiées

- **Ordre de travail** : les tests de la première version ont été écrits **après** le code, à
  l'encontre de la règle 3 de `methode.md` (relevé par Sabine). Les mutations prouvent que les
  tests mordent, pas qu'ils ont guidé la forme du code. Les corrections des revues ont suivi le
  test rouge d'abord.
- **Lecture de la réponse sans borne de taille** : risque accepté pour `kb digest` le 21/10,
  étendu à `kb trend-report` par Sabine le 30/10 ; la borne commune est prévue avant le 08/11
  (journal ADR, « Décisions encore ouvertes »).
- **Aucun essai réel** : ni `kb serve-data` ni `kb serve-ai` n'ont tourné avec cette commande ; les
  tests passent par un faux transport HTTP. L'essai court est à faire par Sabine après la fusion.
- **Deux lancements qui se chevauchent** : chacun ajoute son entrée à la liste lue au début ; le
  dernier écrit l'emporte. Non testé, comme pour le coffre (#295).

## Ce qui reste

- **#367** : la fiche GitHub des candidats (les 60 que la PR 1 calcule déjà).
- **#368** : le choix par le modèle ; `model` et `choice_made` du registre se remplissent.
- **#369** : la rédaction des textes ; le rendu recevra du texte libre, qui passera alors par
  `neutralize_digest_text`.
- **#370** : l'essai réel et la révision des seuils (5 rangs, tranches de rangs).
- **Session cosmétique** : l'en-tête YAML des trois sortes de fichiers, le titre lisible des
  comptes rendus de veille, l'organisation des dossiers du coffre (remarques de Sabine du 30/10).
