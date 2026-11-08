# Enregistrer un jeu de référence de sorties réelles de `POST /digests`

- **Date** : 2026-11-08
- **Branche** : `test/digests-reference-outputs`
- **Issue** : #479
- **Fichiers principaux** : `tests/ai_api/digests_reference.py` (l'enregistrement, et ce qu'il partage avec le
  rejeu), `tests/ai_api/test_digests_reference.py` (le rejeu), `tests/fixtures/digests_reference.json` (le jeu),
  `README.md` (une ligne du tableau « Contenus de tiers »).
- **Série** : le modèle de remplacement (*replay*) vient de
  [2026-10-15-appeler-le-modele-et-son-remplacement.md](2026-10-15-appeler-le-modele-et-son-remplacement.md) ;
  la chaîne servie pour de vrai, de
  [2026-11-08-tester-la-chaine-des-fiches-sur-les-api-servies.md](2026-11-08-tester-la-chaine-des-fiches-sur-les-api-servies.md).

## Le pourquoi

Les tests de l'API IA rejouent des réponses du modèle **écrites à la main** dans les tests (`VALID_STEPS`,
`tests/ai_api/test_digest_router.py`). Ils prouvent que les contrôles marchent sur ces réponses, mais rien de ce
qu'un vrai modèle écrit. Pour que la CI puisse évaluer des sorties réelles (#482 : schémas valides, fidélité,
items oubliés, contre les seuils du 15/10), il faut d'abord **des sorties réelles, enregistrées une fois et
rejouées ensuite sans réseau ni coût**. C'est ce jeu. L'appel réel a été fait une seule fois, par Sabine, qui a
l'accès au modèle.

## Le comment

### 1. Des items publiables, importés par le code de `kb import`

Le jeu ne doit contenir que des items dont le texte peut être publié, et aucun texte réécrit. Les items ne sont
donc pas recopiés à la main : la base est reconstruite depuis deux extraits de la collecte sous CC0 1.0, par la
porte de l'import (`tests/ai_api/digests_reference.py:156-174`) :

```python
    database_path = data_dir / "k-b.sqlite"
    create_database(database_path)
    import_raw_files(
        data_dir,
        database_path,
```

`import_raw_files` est la fonction qu'appelle `kb import` (`etl/pipeline.py`). Les textes de la base sont ceux
des extraits, par construction. La fenêtre de la demande (14 jours avant le 2026-10-08) prend les 3 papiers
d'`arxiv_extract.xml` et les 3 CVE de 2026 de `cisa_kev_extract.csv`.

### 2. Un transport qui garde chaque réponse telle qu'elle arrive

Le client du modèle accepte un transport (`build_http_client(settings, transport=...)`). L'enregistrement
enveloppe le vrai transport HTTP et garde chaque réponse (`tests/ai_api/digests_reference.py:294-325`) :

```python
            response = self.provider.handle_request(request)
            try:
                body = response.read()
            finally:
                response.close()
```

Le corps est gardé **entier**, en `ResponseStep(status, body)` : le *replay* le rend tel quel, sans aucune
conversion. Le transport rend ensuite une réponse neuve, sans `Content-Encoding` (ligne 325) : le corps est déjà
décodé, et le client le décoderait une seconde fois. Chaque pas porte aussi l'étape, la `prompt_version`, le
modèle demandé, celui qui a répondu, `reasoning_effort` et l'heure de l'appel.

### 3. N'écrire le jeu que si le rejeu donnera la même chose

Un 429, un 5xx ou une erreur réseau ne se rejouent pas de la même façon : un 429 rejoué fait vraiment attendre
le test. Le jeu n'est donc écrit que si chaque réponse est un 200 et qu'aucun sujet n'est indisponible
(`tests/ai_api/digests_reference.py:331-345`) :

```python
    for failed in response.json()["failed_subjects"]:
        if failed["error"] in UNAVAILABLE_STATES:
            return f"subject {failed['subject']}: {failed['error']}"
```

Une sortie refusée par un contrôle (schéma, fidélité) est gardée : c'est justement ce que #482 mesurera.

### 4. Le rejeu : la même demande, sur les mêmes items

Le test reconstruit la base, vérifie que l'API IA lit exactement les items du jeu, **ids compris** (le modèle
cite `i1` à `i6`), puis rejoue la route (`tests/ai_api/test_digests_reference.py:53-62`) :

```python
    assert response.status_code == 200
    # Each writing of the set answered at its first attempt: one digest each.
    assert response.json()["failed_subjects"] == []
```

La dernière assertion compare l'étape de chaque requête rejouée (lue par le nom du schéma demandé,
`classification` ou `digest`) à celle de l'enregistrement : si le code envoyait une requête de plus ou de moins,
le test échouerait.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Un script lancé à la main (`uv run --env-file .env python tests/ai_api/digests_reference.py`) | un seul appel payant, au moment choisi | un test `e2e` : `-m e2e` le relancerait (et le paierait) à chaque fois, et `.env.e2e_test.example` devrait porter les `KB_LLM_*` |
| arXiv et KEV seulement | CC0 1.0 au README, textes réels | releases de `anthropics/claude-code` (« All rights reserved ») ; TLDR (textes réécrits, journal ADR, #278) ; avis GitHub (CC BY 4.0, mais publiés en juin, hors de la fenêtre de 14 jours ; une seconde demande doublerait les appels) |
| La réponse brute (`ResponseStep`) | rejeu exact, `usage` compris | `CompletionStep` : une conversion, et un `usage` absent deviendrait 0 |
| Les sujets réels, recopiés dans le jeu | le modèle a vu ces sujets ; le jeu reste juste si la liste du code change | les sujets des tests (`TEST_SUBJECTS`) : ce ne seraient pas les vraies consignes |
| Aucun échec si `prompt_version` change | la péremption du jeu se décide en #482 | faire échouer la CI à chaque nouvelle consigne, avant que #482 ait tranché |
| Base dans un dossier temporaire, seuls les `KB_LLM_*` lus | `uv run --env-file .env` charge tout le `.env` : une lecture de `KB_DATABASE_URL` aurait pu écrire dans la vraie base | passer par `kb import` en ligne de commande, qui lit l'environnement |

La revue (`/code-review`) a rendu 10 constats, triés par time-knight : 6 corrigés (dont l'`item_id` du point 4 et
la licence du README), 4 écartés.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest -k digests_reference` avant le code → `ModuleNotFoundError` ; puis `FileNotFoundError` sur le jeu | le test est écrit d'abord, et il échoue tant que le jeu n'existe pas |
| La commande de Sabine, le 2026-11-08 à 20:29 UTC → `digests_reference.json: 6 items, 3 calls` | un vrai appel : 1 classement, puis 2 rédactions (`vulnerabilities`, `llm_security`), en 200, sans nouvelle tentative, `gpt-6-luna-2026-09-22` |
| `uv run pytest -k digests_reference` → 1 passed | chaque sortie se rejoue par le *replay* |
| Essai sur un fournisseur simulé, en gzip, avant l'appel réel (scratchpad, non commité) | le corps est décodé une seule fois ; un second lancement est refusé sans appel |
| Au rejeu, `fidelity_rate` 0.625 et 0.5 ; 8 affirmations retirées sur 9 | un fait sur gpt-6-luna, que mesurera #482 ; le test ne le juge pas |

## Ce que tu dois pouvoir défendre

- **Pourquoi enregistrer, plutôt qu'appeler le modèle en CI ?** Un appel en CI coûte, dépend du réseau et rend
  une sortie différente à chaque fois. Le jeu figé rend le même score tant que le code ne change pas
  (`digests_reference.py`, `RecordingTransport`).
- **Comment sais-tu qu'aucun texte n'est réécrit ?** Le jeu ne porte pas les textes : la base est importée
  depuis les extraits par `import_raw_files`, et le test vérifie que les items lus sont ceux du jeu
  (`test_digests_reference.py:39-45`).
- **Que se passe-t-il si quelqu'un relance l'enregistrement ?** Il s'arrête avant tout appel : « already
  recorded, no call sent » (`digests_reference.py:350`). Le jeu s'ouvre en mode `"x"` (ligne 386).
- **Quelles données sont parties chez Azure ?** Les champs de 6 items sous CC0 1.0 (titres, résumés, CVE). Aucun
  auteur : la liste blanche de l'API IA ne les envoie pas (`ai_api/watch_items.py:1-4`).
- **Le test passe alors que 8 affirmations sur 9 sont retirées : n'est-il pas trop faible ?** Il prouve le rejeu,
  pas la qualité. Juger la qualité, c'est #482, contre les seuils du 15/10.

## Zones non vérifiées

- La licence du texte écrit par le modèle et des métadonnées du fournisseur (`id`, `routing`,
  `prompt_filter_results`) : non établie. La ligne du README le dit ; seuls les passages cités sont sous CC0 1.0.
- L'échéance de la demande pendant l'enregistrement : le transport lit le corps avant `read_bounded_body`, si
  bien que `is_late` ne s'y applique pas. Les appels ont duré de 1 à 4 s, pour une échéance de 200 s.
- Le comportement d'un enregistrement qui rencontrerait un 429 ou une sortie refusée puis reprise : il n'a pas
  été essayé sur le vrai modèle. Seul le cas tout en 200 l'a été, et le fournisseur simulé.

## Ce qui reste

- #482 : rejouer le jeu en CI et le mesurer contre les seuils. Limite à y écrire : si le nombre de requêtes
  change (découpage en lots, nouvelle tentative), le rejeu se décale, et seul un nouvel enregistrement par Sabine
  le répare.
- Le câblage de l'API IA en est à sa troisième copie (`make_ai_api` dans `test_digest_router.py`, celle de
  `test_trend_report_router.py`, et celle-ci) : pas de factorisation avant le 25/11.
