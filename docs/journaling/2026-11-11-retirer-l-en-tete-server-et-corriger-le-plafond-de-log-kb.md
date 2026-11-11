# Retirer l'en-tête `Server` des deux API, et dire ce que fait le plafond de `log-kb`

- Date : 2026-11-11
- Branche : `fix/server-header-and-log-cap`
- Issues : #569 (en-tête `Server`), #566 (commentaire du plafond journalier)
- Fichiers principaux : `src/k_b/commands/serve_data_command.py`, `src/k_b/commands/serve_ai_command.py`,
  `infra/modules/log-analytics.bicep`
- Série : [ouvrir le socle du site privé](2026-11-11-ouvrir-le-socle-du-site-prive.md) (le même réglage pour
  `kb serve-web`), [documenter les journaux de l'application](2026-11-11-documenter-les-journaux-de-l-application.md)
  (où le commentaire faux du plafond a été relevé)

Les commits de la branche sont `3263b26` (le code, les tests, le commentaire) et `cd4e86a` (le tri de la revue,
dans la doc). Les autres de la liste viennent de `main` : cette note n'en traite pas.

## Le pourquoi

Deux défauts relevés le même jour par deux relectures, tous deux petits et sans Azure.

- **#569.** Chaque réponse de `kb serve-data` et de `kb serve-ai` portait `server: uvicorn`. La règle 213 du
  référentiel Opquast 2025 demande que le serveur ne dise pas quels logiciels il utilise. Le site (`kb serve-web`,
  #572) le faisait déjà ; les deux API, non.
- **#566.** Le commentaire du plafond de l'espace Log Analytics `log-kb` disait « Beyond it, the day's logs are
  dropped ». Microsoft Learn dit autre chose : la collecte s'arrête jusqu'à une heure de remise à zéro, et pas
  exactement au plafond. `docs/specs-api.md:577` s'appuyait sur ce plafond pour dire le coût des journaux borné.

## Le comment

### D'où vient l'en-tête

uvicorn le pose lui-même, au niveau du protocole HTTP, pas l'app :

```python
self.encoded_headers = (
    [(b"server", b"uvicorn")] + encoded_headers
    if b"server" not in dict(encoded_headers) and self.server_header
    else encoded_headers
)
```

(`.venv/…/uvicorn/config.py:497-501`, uvicorn 0.54.0, où `server_header` vaut `True` par défaut, `:226`.) Ces
en-têtes par défaut sont ajoutés devant ceux de l'app au moment d'envoyer la réponse
(`uvicorn/protocols/http/h11_impl.py:471`, `headers = self.default_headers + list(message.get("headers", []))`).
Un middleware de l'app ne les voit donc jamais : c'est à uvicorn qu'il faut le dire.

### Le réglage, dans les deux commandes

```python
                log_config=None,
                access_log=False,
                # No header Server: uvicorn, which names the software (Opquast 2025, rule 213).
                server_header=False,
```

(`src/k_b/commands/serve_data_command.py:55-58`, et de même `serve_ai_command.py:107-110`.) Le commentaire est
celui de `kb serve-web` (`serve_web_command.py:39`), mot pour mot : la même règle se lit de la même façon dans les
trois commandes.

### Le test

```python
def test_serve_data_sends_no_server_header(monkeypatch, data_dir, uvicorn_calls):
    """uvicorn names itself in a header Server by default (Opquast 2025, rule 213)."""
    monkeypatch.setenv("KB_DATA_API_KEY_TERMINAL", make_key())

    cli.main(["serve-data"])

    [(_, options)] = uvicorn_calls
    assert options["server_header"] is False
```

(`tests/data_api/test_serve_data.py:150-157` ; son pendant est `tests/ai_api/test_serve_ai.py:127`.) La fixture
`uvicorn_calls`, déjà là, remplace `uvicorn.run` et garde ses arguments : le test lit ce que la commande demande à
uvicorn, sans ouvrir de port. Les deux tests qui comparent le dictionnaire entier des options (`…by_default…`,
`:146` et `:120`) prennent aussi la clé, sinon ils échouent.

### Le plafond de `log-kb`

```bicep
    // Far above the logs of K-B, which hold counts and states only: holds a runaway log near 0.2 GB
    // a day (2.76 $ a GB beyond the free 5 GB a month). Once it is reached, collection stops
    // until the reset hour of the workspace, which differs from one workspace to another and cannot
    // be configured. It does not stop exactly at the cap: the excess, larger when logs come fast, is
    // billed (Microsoft Learn, "Set daily cap on Log Analytics workspace", read on 2026-11-11).
```

(`infra/modules/log-analytics.bicep:15-19`.) Trois faits de la page Learn, lue le 2026-11-11 (datée du
2025-08-29) : « Data collection resumes at the reset time which is a different hour of the day for each
workspace. This reset hour can't be configured » ; « The daily cap can't stop data collection at precisely the
specified cap level and some excess data is expected » ; « If data is collected above the cap, it's still
billed ». La valeur, `dailyQuotaGb: json('0.2')`, ne change pas : rien ne change au déploiement.

### La doc qui s'appuyait sur ces lignes

Le commentaire passe de deux à cinq lignes : `workspaceCapping` descend de `:17-18` à `:20-21`. Les renvois de
`docs/specs-api.md:577` et de `documentation/monitoring_pour_docu.md:296-297` suivent, et la fiche prolonge son
tampon (« et le commentaire du plafond, par #566, d'après le code de sa PR », `:186-187`). Les mesures API8 des
deux API citent l'en-tête retiré et son test (`docs/specs-api.md:522`, `docs/fiches-veille.md:583-585`).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Où couper l'en-tête | `server_header=False` d'uvicorn : c'est lui qui le pose | Un middleware de l'app : il ne voit pas l'en-tête, ajouté après lui (`h11_impl.py:471`) ; un `--header server:…` : il dirait encore quelque chose |
| Le test | Un test nommé par commande, plus la clé dans les deux dictionnaires exacts (plan validé par Sabine) | La clé dans les seuls dictionnaires, comme `test_serve_web` : la règle serait cachée dans un test nommé pour l'hôte et le port. La revue a relevé la redondance ; gardé (tranché par time-knight) |
| Le commentaire du code | Celui de `kb serve-web`, mot pour mot | Une autre phrase : trois façons de dire la même règle |
| Le commentaire du plafond | « holds a runaway log near 0.2 GB a day », puis l'arrêt et l'excédent | Garder « bounds … at a few cents a day » : la phrase suivante dit que l'excédent n'est pas borné (constat 2 de la revue) |
| L'essai réel | Ports 18000 et 18001, variables fictives, dossier du scratchpad, `env -i` | Les ports 8000 et 8001 de l'issue : une autre session peut les tenir ; le `.env` : jamais lu |
| Les trois copies des options d'uvicorn | Une issue à part (accord de time-knight) | Factoriser ici : il faudrait toucher `serve_web_command.py`, hors de cette mission |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest … -k "server_header or by_default"` avant le code : 4 failed (`KeyError: 'server_header'`, dictionnaires différents) | Les tests voyaient l'absence du réglage |
| Le même après le code : 4 passed ; `uv run pytest` : 4493 passed | Le réglage est passé, rien d'autre n'a bougé |
| `curl -sI` puis un GET sur `127.0.0.1:18000/health` et `:18001/health`, le 2026-11-11 à 16:20:31 UTC : 405 au HEAD (la route n'accepte que GET), 200 au GET, aucune ligne `server` dans les quatre réponses | Le vrai serveur, lancé par `kb`, n'envoie plus l'en-tête |
| `lsof` et `pgrep` après l'essai : rien | Les deux API ont été arrêtées |
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les contrôles de la CI |

## Ce que tu dois pouvoir défendre

1. **Retirer `server: uvicorn` rend-il l'API sûre ?** Non. L'en-tête nomme le logiciel, sans sa version : c'est
   une information de moins pour qui le cherche, une couche de plus (défense en profondeur), pas une protection. La raison écrite
   est la règle 213 d'Opquast (`serve_data_command.py:57`).
2. **Et en ligne ?** L'entrée d'Azure Container Apps est devant uvicorn et peut poser son propre en-tête. Ce n'est
   pas constaté, et c'est écrit là où les mesures sont listées (`docs/specs-api.md:522`).
3. **Pourquoi pas un middleware ?** uvicorn ajoute ses en-têtes par défaut en envoyant la réponse, après l'app
   (`h11_impl.py:471`) : un middleware ne peut pas retirer ce qu'il ne voit pas.
4. **Que se passe-t-il quand `log-kb` atteint 0,2 Go dans la journée ?** La collecte s'arrête jusqu'à l'heure de
   remise à zéro de l'espace, qu'on ne choisit pas ; les journaux envoyés entre-temps ne sont pas reçus ; un
   excédent passe quand même, et il est facturé (`log-analytics.bicep:15-19`).
5. **Pourquoi le test n'ouvre-t-il pas de port ?** Il vérifie ce que `kb` demande à uvicorn ; ce qu'uvicorn en
   fait est son code, lu à la source. L'essai réel avec `curl`, fait une fois, relie les deux.

## Zones non vérifiées

- **En ligne** : l'en-tête que l'entrée d'ACA peut poser n'a pas été regardé (#569 le renvoie après le
  déploiement ; aucune commande `az` dans cette mission).
- **Avant la correction**, l'en-tête n'a pas été vu par un `curl` dans cette session : sa présence vient de la
  source d'uvicorn et du relevé de #569.
- **WebSocket** : la doc d'uvicorn dit que `--no-date-header` est sans effet sur l'implémentation `websockets`.
  K-B n'a aucune route WebSocket (aucune occurrence dans `src/k_b`), et seul `h11` est installé.
- **Page Learn** : une recherche web du jour a résumé un avertissement (« known issue », plafond appliqué de façon
  inexacte depuis fin 2024) absent de la page lue le même jour ; il n'est pas repris.

## Ce qui reste

- Les trois copies des options d'uvicorn, dans une issue à part : « Factoriser les options d'uvicorn communes aux
  trois commandes serve-* ».
- Vérifier, après un déploiement, l'en-tête `Server` des deux API en ligne.
