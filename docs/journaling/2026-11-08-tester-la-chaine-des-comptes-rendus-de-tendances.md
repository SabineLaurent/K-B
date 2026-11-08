# Tester la chaîne des comptes rendus de tendances sur les deux API servies

- **Date** : 2026-11-08
- **Branche** : `test/live-trend-report`
- **Issue** : #462
- **Fichiers** : `tests/commands/test_live_apis.py` (le test et le montage) ; `docs/tendances.md` (une ligne
  « Chaîne » dans « Ce qui le prouve »). `src/` n'est pas touché.
- **Série** : suit [Tester la chaîne des fiches sur les deux API servies pour de vrai](2026-11-08-tester-la-chaine-des-fiches-sur-les-api-servies.md)
  (#26), dont ce test reprend le montage.

Note qui couvre le commit `729bbf4` (le test et la ligne de `docs/tendances.md`) ; les autres commits de la
branche ne touchent que cette note.

## Le pourquoi

#26 a fait passer `kb digest` et `kb smoke-test` par les deux API servies pour de vrai. `kb trend-report`, qui
appelle `POST /trend-reports`, n'était encore testé côté client que par `httpx2.MockTransport`
(`tests/commands/test_trend_report_command.py`), et la route que par des surcharges de dépendance
(`tests/ai_api/test_trend_report_router.py`). Personne ne vérifiait qu'une demande partie de `kb trend-report`
traverse l'API IA, puis l'API de données de la base de test, et revient écrite dans le coffre. La certif lit donc
C10.6 d'E3 (« les tests d'intégration couvrent tous les points de terminaison exploités ») comme partiel.

Critère de fin de #462 : « Un test lancé par `uv run pytest` appelle `kb trend-report`, qui passe par l'API IA
servie par uvicorn, puis par l'API de données de la base de test, sur le modèle de remplacement (`replay`) et un
GitHub simulé, et vérifie le compte rendu écrit. Il tourne en CI, sans clé ni réseau extérieur, sur le même
montage que `tests/commands/test_live_apis.py`. »

Restent simulés : le modèle (le rejeu) et GitHub, comme le demande le critère.

## Le comment

### Un montage, trois clients

Le montage `live_apis` de #26 construit les deux API par `run_serve_data` et `run_serve_ai`, puis les sert par
uvicorn sur `127.0.0.1:0`. Il servait `kb digest` et `kb smoke-test` ; il sert maintenant aussi
`kb trend-report`. Ce qui changeait d'un test à l'autre, les étapes rejouées par le modèle, devient une fixture :

```python
@pytest.fixture
def replay_steps():
    """The steps the AI API replays: those of the digests, unless a test gives its own by
    parametrize."""
    return VALID_STEPS
```
(`tests/commands/test_live_apis.py:121-125`)

`live_apis` la reçoit en paramètre et l'écrit dans le fichier de rejeu (l.149). Le test des tendances la remplace
par `@pytest.mark.parametrize("replay_steps", [TREND_REPORT_STEPS], ids=["two-chosen"])` (l.286) : pytest laisse
un paramètre de `parametrize` prendre la place d'une fixture du même nom, et cette valeur descend dans toutes les
fixtures qui en dépendent, `live_apis` compris. Les tests des fiches et de `kb smoke-test` ne changent pas : ils
gardent `VALID_STEPS`.

### Une clé par client

```python
digest_key = secrets.token_urlsafe(32)
# A key per client: kb serve-ai refuses one key for two.
trend_report_key = secrets.token_urlsafe(32)
```
(l.161-163)

`kb serve-ai` refuse de démarrer si deux clients ont la même clé. `kb trend-report` est le client
`KB_TREND_REPORT` de l'API IA, distinct de `kb digest` (MEMORY.md, « Interface ») : sa clé entre dans
l'environnement de `kb serve-ai` (`TREND_REPORT_KEY_VARIABLE`, l.167) et dans `LiveApis` (l.83), que la fixture
du test lit.

### GitHub simulé sur les dépôts de la base de test

L'API IA lit la fiche GitHub et le README de chaque dépôt choisi. Le test de la route a déjà un GitHub simulé,
`SimulatedGithub` (`tests/ai_api/test_trend_report_router.py:148`), qui sert la fiche des fixtures avec l'`id` du
dépôt demandé. Ici, ces `id` viennent de la base de test :

```python
connection = sqlite3.connect(database_path)
try:
    ids = dict(
        connection.execute("SELECT repository_name, repository_id FROM trend")
    )
```
(l.130-134)

Puis le montage remplace la dépendance qui ouvre le client GitHub :

```python
ai_app.dependency_overrides[open_github_client] = simulate_github_of(
    items_database
).client
```
(l.180-182)

`open_github_client` (`src/k_b/ai_api/dependencies.py:28`) construit le client à partir de
`app.state.github_settings`. La surcharge le remplace par `SimulatedGithub.client`, qui renvoie un client sur un
`httpx2.MockTransport` : aucune requête ne sort de la machine. Le jeton de `kb serve-ai` reste faux
(`github_pat_` suivi de hasard, l.174) : il est lu au démarrage, jamais envoyé.

La base a un seul `id` par nom (`tests/fixtures/items_database.sql:198-204`) : le `dict` ne perd rien.

### Deux réglages côté `kb`

```python
monkeypatch.setattr(
    trend_report_client,
    "SUBJECT_NAMES",
    tuple(subject.name for subject in TEST_SUBJECTS),
)
monkeypatch.setattr(trend_report_command, "read_now", lambda: TREND_REPORT_TIME)
```
(l.270-275)

- `SUBJECT_NAMES` : le client refuse un choisi dont les sujets ne sont pas les siens, dans l'ordre
  (`src/k_b/post/trend_report_client.py:424`). L'API IA tourne sur les sujets des tests (`TEST_SUBJECTS`, posés
  par `live_apis`, l.164) : le client doit avoir les mêmes.
- `read_now` : le client refuse une période dont la dernière fenêtre tombe après le jour du lancement
  (`trend_report_client.py:249`, `after_today`). La dernière fenêtre de la base de test est le 2026-10-10 : le
  lancement est fixé ce jour-là, à 09:00 UTC (l.225).

### Ce que le rejeu fait dire au modèle, et ce que le test vérifie

Les candidats viennent de la base. Seules les lignes qui gagnent des étoiles sont classées
(`src/k_b/ai_api/trajectories.py:59`) : 3 dépôts sur 5. Ils sont numérotés par meilleur rang
(`select_candidates`, `trajectories.py:186`) : c1 `morluto/rea`, c2 `storytold/photocraft`, c3
`boykopovar/AnyPS5`. Aucun ne remplit de critère : les deux fenêtres (09 et 10/10) font 3 jours et se
chevauchent, donc pas de `durable` (`is_durable`, `trajectories.py:158`).

```python
TREND_REPORT_STEPS = [
    answer(
        {"ref": "c2", "criteria": ["watch_subject"], "watch_subjects": ["agent_tools"]},
        {"ref": "c1", "criteria": ["watch_subject"], "watch_subjects": ["agent_tools"]},
    ),
    writing("c2"),
    writing("c1", sector=REMOVED_SECTOR),
]
```
(l.229-236)

Trois étapes, dans l'ordre des appels : le choix (c2 puis c1, par le seul sujet de la veille), puis une rédaction
par choisi. La seconde porte un secteur, « Bâti sur les type hints. », dont le fait (« type hints ») n'est pas
dans les topics de la fiche : les contrôles le retirent (`docs/tendances.md:202`, le secteur se vérifie dans les
topics). Chaque rédaction doit donc arriver sous son dépôt : si elles étaient échangées, le secteur retiré serait
sous `storytold/photocraft`.

Le test compare la section « Choisis par le modèle » du fichier du coffre, ligne à ligne, à `CHOSEN_SECTION`
(l.245-261) : le nombre retenu, chaque dépôt et son motif, ses faits tirés de la fiche GitHub (`CARD_FACTS`), son
secteur (gardé ou « non retenu par les contrôles »), son résumé du README et sa promesse. Il vérifie aussi la
ligne de période que `kb` affiche (l.300) : `Period: 2026-10-07 → 2026-10-10, 4 windows, 2 missing`. Un premier
compte rendu lit les 4 dernières fenêtres (`TREND_FIRST_REPORT_WINDOWS`, `src/k_b/core/config.py:92`) ; la base
n'a que le 09 et le 10 : ces deux fenêtres sont passées par l'API de données.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Reprendre `live_apis` pour les trois clients | Le critère de fin demande « le même montage » ; le code n'est écrit qu'une fois | Un second montage : une quarantaine de lignes copiées |
| Les étapes du rejeu par une fixture `replay_steps`, remplacée par `parametrize` | Le modèle reste celui que règle l'environnement de `kb serve-ai` (`replay` et son fichier) | Brancher le rejeu par une surcharge d'`open_llm_client` : le modèle ne serait plus celui de l'environnement |
| GitHub simulé par `dependency_overrides[open_github_client]` | Conception de time-knight, comme dans le test de la route ; aucun changement dans `src/` | Garder `open_github_client` et ne remplacer que son transport : il faudrait un point d'injection dans `src/` (constat 2 de la revue, écarté par time-knight) |
| Les `id` des dépôts lus dans la base de test | La fiche simulée porte l'`id` que l'API IA attend, sans recopier la base | Des `id` écrits en dur : une seconde copie de la fixture |
| Horloge de l'API IA laissée au 2026-10-08 (`REQUEST_TIME`, celle des fiches) | La route des tendances ne s'en sert que pour les prudences d'une fiche (`find_cautions`, sans effet sur une fiche de 2018) et le `Retry-After`, jamais appelé ici | Une horloge par test (point 5 du plan validé par Sabine ; constat 1 de la revue, écarté) |
| Comparer la seule section « Choisis par le modèle », écrite en entier | Conception : « les choisis, leurs faits et leurs lignes de textes » ; la sortie attendue se lit comme le fichier du coffre | Tout le fichier : les autres sections et `trend_reports.json` sont tenus par `test_trend_report_command.py` ; construire l'attendu depuis `WRITTEN` (constat 6, écarté) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_trend_report_writes_the_chosen_through_the_ai_api_and_the_data_api` vert | La chaîne `kb trend-report` → API IA → API de données → coffre marche, sur le rejeu et le GitHub simulé |
| Mutation 1, la seconde rédaction retirée du rejeu : `assert <ExitCode.FAILED: 1> == <ExitCode.SUCCEEDED: 0>` | Le rejeu est bien celui que lit l'API servie : à court d'étapes, il lève `ReplayExhaustedError` (`src/k_b/ai_api/connectors/llm_replay.py:97-100`), et `kb` sort en échec |
| Mutation 2, le secteur retiré déplacé : `At index 6 diff: '  Secteur : non retenu par les contrôles.' != '  Secteur : Framework web pour python.'` | La comparaison voit quelle rédaction arrive sous quel dépôt |
| `uv run pytest` → 4035 passed, 328 deselected | Les tests des fiches et de `kb smoke-test`, sur le même montage, restent verts |
| `uv run ruff check --no-cache`, `uv run ruff format --check`, `uv run mypy --strict` verts ; aucun caractère `Cc` ou `Cf` | Contrôles du dépôt |
| `/code-review medium` : 8 constats, tous écartés par time-knight (délégation de Sabine du 15/10) | Revue faite ; rien à corriger |

## Ce que tu dois pouvoir défendre

1. **Pourquoi GitHub est-il simulé, alors que les deux API sont réelles ?** Le critère de fin le demande : le test
   tourne en CI sans clé ni réseau extérieur. Appeler GitHub demanderait un jeton réel et dépendrait d'un service
   qui change. L'essai réel est #370. (`test_live_apis.py:180-182`)
2. **Qu'est-ce qui prouve que la requête traverse vraiment l'API de données ?** Les candidats et la période ne
   viennent que d'elle : les dépôts `storytold/photocraft` et `morluto/rea`, les fenêtres du 09 et du 10/10 de la
   base de test. Ni `kb` ni l'API IA ne les connaissent autrement. (`test_live_apis.py:250, 255, 300`)
3. **Que se passe-t-il si les rédactions sont rattachées au mauvais dépôt ?** Le secteur retiré change de place, et
   la comparaison ligne à ligne échoue : c'est la mutation 2. (`test_live_apis.py:227-236`)
4. **Pourquoi deux réglages côté `kb` ?** Le client refuse des sujets qui ne sont pas les siens et une fenêtre
   après le jour du lancement. Le test aligne ses sujets sur ceux de l'API IA et fixe le jour au 2026-10-10.
   (`test_live_apis.py:270-275` ; `trend_report_client.py:249, 424`)
5. **Où est la sécurité ?** Aucune clé réelle : les trois clés sont tirées par `secrets.token_urlsafe(32)`, le jeton
   GitHub est faux et n'est jamais envoyé. Aucun réseau hors de `127.0.0.1` : les deux API écoutent sur un port
   libre de la machine, GitHub et le modèle passent par des `MockTransport`.

## Zones non vérifiées

- Le câblage du jeton GitHub, lu dans l'environnement dans `app.state.github_settings`, n'est pas éprouvé ici :
  `open_github_client` est surchargé (constat 2 de la revue).
- Seule la section « Choisis par le modèle » est comparée. Les autres sections du fichier et `trend_reports.json`
  sont tenus par `test_trend_report_command.py`, pas par ce test (constat 8).
- Mutation 1 : `ReplayExhaustedError` n'est rattrapée nulle part dans `src/` (grep). Le statut HTTP que l'API IA
  renvoie alors à `kb` n'a pas été lu, seul le code de sortie `FAILED` l'a été.
- L'horloge de l'API IA (2026-10-08) précède les fenêtres qu'elle sert (2026-10-10), ce qui n'arrive pas en
  production. Sans effet aujourd'hui (voir les choix) ; si la route compare un jour ses fenêtres à l'heure de la
  requête, ce test échouera et le dira.

## Ce qui reste

- L'essai réel de bout en bout, sur GitHub et le modèle : #370.
- Le test ne fait qu'un compte rendu, le premier (sans compte rendu précédent). La suite d'une période déjà tenue
  par `trend_reports.json` reste couverte par les tests de la commande, sur `MockTransport`.
