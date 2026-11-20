# Évaluer en CI le jeu de référence contre les seuils du 15/10

- **Date** : 2026-11-20
- **Branche** : `ci/digests-reference-thresholds`
- **Issue** : #482
- **Fichiers principaux** : `tests/ai_api/digests_evaluation.py`, `tests/ai_api/test_digests_evaluation.py`,
  `.github/workflows/ci.yml` (job `digests-reference`), `README.md` et
  `documentation/integration_continue_pour_docu.md` (description de la CI)
- **Série** : [enregistrer un jeu de référence des fiches](2026-11-08-enregistrer-un-jeu-de-reference-des-fiches.md)
  (#479), puis [définir la fidélité comme le code la mesure](2026-11-09-definir-la-fidelite-comme-le-code-la-mesure.md)
  (#518).

## 1. Le pourquoi

Le 15/10, Sabine a fixé trois seuils pour les sorties du modèle : 100 % de schémas valides après une nouvelle
tentative, au moins 95 % de fidélité, aucun item oublié. Jusqu'ici, c'était une grille de lecture des essais (journal
ADR, PR de #275, décision 7). Le 08/11, elle a décidé d'en faire des seuils d'échec en CI, pour `POST /digests` seul.

Le jeu de référence de #479 (`tests/fixtures/digests_reference.json`) enregistre de vraies sorties du modèle sur
6 items. Le rejouer par la route donne les lignes de métrique que K-B écrit en production. Ce travail ajoute un job
de CI qui rejoue ce jeu, mesure ces lignes et échoue sous un seuil. Comme `deploy.yml` refuse un commit dont la CI
n'est pas finie et verte, une sortie sous les seuils bloque aussi le déploiement.

Ce que le job juge : les contrôles de K-B appliqués à des sorties enregistrées. Le modèle lui-même se mesure à chaque
nouvel enregistrement du jeu, que seule Sabine lance (#520), et le jeu est périmé dès que la consigne change de
`prompt_version`.

## 2. Le comment

### 2.1 Un script lancé par le job, pas un test marqué

Le job lance un script et en lit le code de sortie (`.github/workflows/ci.yml:124`) :

```yaml
      - run: uv run python tests/ai_api/digests_evaluation.py reports/digests-reference-report.md
```

Le script vit à côté de l'enregistreur du jeu (`tests/ai_api/digests_reference.py`), qui se lance de la même façon. Il
réutilise le rejeu du test de #479, `replay_reference`, sans le modifier (`tests/ai_api/digests_evaluation.py:168`) :

```python
        response, requests = replay_reference(reference, Path(data_dir))
```

Ce rejeu construit une base à partir des extraits, sert l'API de données et l'API IA, et fait répondre le modèle par
`ReplayTransport`, qui rend les réponses enregistrées sans ouvrir de connexion.

### 2.2 Lire les lignes de métrique écrites sur stdout

L'API IA écrit une ligne JSON par appel au modèle sur la sortie standard (règle 4 de `poc.md`,
`src/k_b/ai_api/observability/metrics.py:50`, qui appelle `sys.stdout.write` à chaque ligne). Le script détourne
stdout le temps du rejeu (`tests/ai_api/digests_evaluation.py:166`), puis ne garde que les lignes d'appel
(`tests/ai_api/digests_evaluation.py:69`) :

```python
    calls = [line for line in lines if line.get("event") == LLM_CALL_EVENT]
```

Une autre ligne JSON (un autre événement) n'entre pas dans les comptes. Une ligne qui n'est pas du JSON fait échouer
`json.loads`, donc le job : l'échec reste fermé.

### 2.3 Trois mesures, et un rejeu conforme au jeu

`measure_replay` (`tests/ai_api/digests_evaluation.py:66`) compte, sur les lignes d'appel :

- les appels dont la dernière tentative est valide (`schema_valid` : `llm_client.py` garde celui de la dernière
  tentative) ;
- les faits vérifiés et les faits trouvés des rédactions (`facts_checked`, `facts_found`), dont `fidelity_rate` est le
  rapport ;
- les items que le classement a laissés sans réponse (`items_unanswered`, le seuil « aucun item oublié »,
  `docs/fiches-veille.md`, « Trois cas à la sortie »).

Ces mesures ne valent que si le rejeu a bien suivi le jeu. `judge_replay` le vérifie d'abord
(`tests/ai_api/digests_evaluation.py:90`) :

```python
        list(sent_stages) == list(recorded_stages) and status == REPLAY_STATUS,
```

Les étapes envoyées au modèle simulé doivent être celles du jeu, dans leur ordre, et la route doit répondre 200.
Sinon, un code qui sauterait un sujet laisserait des appels non rejoués, et les appels restants pourraient passer les
seuils : le job mesurerait un autre parcours que celui du jeu.

### 2.4 Les seuils comparés en entiers

Les seuils sont des constantes en pourcentage (`tests/ai_api/digests_evaluation.py:31-32`), comparées sur les comptes
(`tests/ai_api/digests_evaluation.py:126`) :

```python
    return whole > 0 and part * 100 >= minimum_percent * whole
```

Ce calcul en entiers n'arrondit jamais. Avec le taux arrondi à 4 décimales de la ligne de métrique, 1899 faits sur
1999 (94,9975 %) deviendraient 0,95 et passeraient le seuil. `whole > 0` fait échouer une mesure qui n'a rien à
compter (aucun appel, aucun fait vérifié) : échouer fermé.

### 2.5 Le rapport, même en échec

`evaluate` écrit le rapport avant de choisir le code de sortie (`tests/ai_api/digests_evaluation.py:180-190`). Le job
le dépose ensuite en artefact (`.github/workflows/ci.yml:125-131`) :

```yaml
      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
        if: ${{ !cancelled() }} # the report of a failing run is the one to read
```

Sans `if`, une étape ne tourne qu'après des étapes réussies : le rapport d'un run rouge, celui qu'on veut lire, serait
perdu. Chaque valeur est tronquée au centième (`format_share`, `tests/ai_api/digests_evaluation.py:134`), jamais
arrondie : 99 999 sur 100 000 s'affiche 99,99 %, et non « 100 % » à côté de « non tenu ». Le rapport ne contient que
des noms et des chiffres (modèle, `prompt_version`, mesures), jamais le texte d'un item : les artefacts d'un dépôt
public se téléchargent.

## 3. Choix faits et options écartées

| Choix | Retenu, pourquoi | Écarté, pourquoi |
|---|---|---|
| Forme du job | un script : il n'a besoin de rien de plus, et il écrit son rapport même en échec | un test pytest marqué et exclu par défaut, comme `e2e` : il faut déclarer un marqueur dans `tests/conftest.py`, et un test qui échoue n'écrit pas de rapport sans code de plus |
| Fidélité du jeu | Σ faits trouvés / Σ faits vérifiés : chaque fait pèse pareil | la moyenne des `fidelity_rate` par sujet : un sujet de 2 faits pèserait autant qu'un sujet de 100 |
| Comparaison au seuil | les comptes, en entiers | le taux arrondi à 4 décimales : un arrondi peut franchir le seuil (constat 4 de la revue) |
| Affichage | tronqué au centième | arrondi : une valeur sous le seuil pourrait s'afficher égale au seuil (constat 5) |
| Rejeu | conforme au jeu (étapes, ordre, statut 200), sinon échec | mesurer ce qui a été rejoué : un sujet sauté passerait inaperçu (constat 3) |
| Envoi du rapport | `if-no-files-found: error` | `warn` : un job sans rapport passerait sans bruit (constat 7, écarté) |
| Rejeu réutilisé | `replay_reference` importée du test de #479 | la déplacer dans `digests_reference.py` : la PR de #520 (#659) modifie ce fichier ; ce sera une suite, une fois les deux PR fusionnées (constat 8) |
| Seuils | ceux du critère, inchangés (décision de Sabine du 08/11) | aucun : le choix d'un seuil revient à Sabine |
| Conservation de l'artefact | 30 jours (RGESN 1.6) : le rapport se lit à la revue d'une PR | 90 jours, le défaut du dépôt |

Les constats de la revue ont été tranchés par time-knight, sur délégation de Sabine du 15/10.

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_replay_at_each_limit_meets_the_thresholds` | 19 faits sur 20 (95 %) passent : le seuil est inclusif |
| `test_a_replay_under_one_threshold_fails`, 6 cas | chaque seuil échoue juste au-delà ; aucun appel ou aucun fait échoue ; 1899 sur 1999 échoue, sans arrondi |
| `test_the_fidelity_weighs_each_fact_of_the_set_the_same` | 1 sur 2 et 100 sur 100 passent (101 sur 102), là où la moyenne des taux ferait 75 % |
| `test_a_line_of_another_event_is_not_counted` | une ligne d'un autre événement n'entre pas dans les comptes |
| `test_a_share_is_truncated_never_rounded_up_to_a_threshold` | 14 sur 26 donne 53,84 % ; 99 999 sur 100 000 donne 99,99 % |
| `test_the_replay_holds_only_with_the_calls_of_the_set_in_their_order_and_a_200` | un appel manquant, un ordre changé ou un statut 502 font échouer le rejeu |
| `test_a_degraded_set_fails_the_evaluation_and_its_report_says_which_threshold` | sur une copie du jeu où la première rédaction répond deux fois hors schéma, le script sort à 1 et la ligne des schémas dit « non tenu » |
| `uv run python tests/ai_api/digests_evaluation.py <rapport>` sur le jeu du 08/11 (gpt-6-luna) | sortie 1 : rejeu 3 sur 3, réponse 200 ; schémas 100 % ; fidélité 53,84 % (14 faits sur 26) sous 95 % ; 0 item oublié |
| La même commande sur le jeu du 20/11 (gpt-6.1-sol, à l'effort `low`), après la fusion de `main` dans la branche | sortie 0 : rejeu 4 sur 4, réponse 200 ; schémas 100 % (4 sur 4) ; fidélité 100 % (26 faits sur 26) ; 0 item oublié ; de même sur GitHub (run 44714259202) |
| `uv run pytest` | 5646 passed sur 00684824 ; 5649 passed sur 5d65a66c, après la fusion de `main` |

## 5. Ce que tu dois pouvoir défendre

**Le job était rouge sur le jeu du 08/11 : pourquoi le fusionner ?** Il ne se fusionne pas rouge. Le jeu du 08/11 a
été enregistré avec gpt-6-luna, et sa fidélité est de 53,84 % : fusionné rouge, le job aurait fait refuser chaque tag
par `deploy.yml`. Le jeu du 20/11, enregistré sur le modèle de production, gpt-6.1-sol (#520, PR #659), tient les
quatre lignes aux seuils du 15/10, inchangés : fidélité 100 % (26 faits sur 26). Le job est vert depuis la fusion de
`main` dans la branche (run 44714259202).

**Pourquoi rejouer plutôt qu'appeler le modèle en CI ?** Un appel est payant, ne se reproduit pas d'un run à l'autre, et
demanderait une clé dans la CI. Le rejeu juge les contrôles de K-B sur des sorties fixes ; le modèle se mesure à
chaque enregistrement du jeu (`digests_evaluation.py:1-7`).

**Que se passe-t-il si un changement de code saute une étape ?** Le rejeu n'envoie plus les appels du jeu dans leur
ordre : la ligne « Appels rejoués » est non tenue et le job échoue (`judge_replay`, `digests_evaluation.py:81-91`).

**Un arrondi peut-il faire passer 94,99 % ?** Non. La comparaison se fait en entiers sur les comptes
(`is_at_least`, `digests_evaluation.py:124-126`), et l'affichage est tronqué.

**Le rapport expose-t-il des données ?** Non : il ne contient que des noms de modèle et de consigne, et des chiffres
(`describe_set`, `format_report`). Aucun texte d'item, aucun auteur.

## 6. Zones non vérifiées

- Le job a tourné deux fois sur GitHub :
  - sur 00684824, avec le jeu de gpt-6-luna (run 44679310659). Le script échoue, comme attendu : fidélité 53,84 %,
    14 faits sur 26. L'étape `actions/upload-artifact` tourne après lui, et le rapport se télécharge par
    `gh run download 44679310659 -n digests-reference-report`.
  - sur 9590394e, après la fusion de `main` qui porte le jeu de gpt-6.1-sol (#520, PR #659 ; run 44714259202). Les
    quatre lignes du rapport sont tenues : 4 appels rejoués sur 4, réponse 200 ; schémas 100 % (4 sur 4) ; fidélité
    100 % (26 faits sur 26) ; aucun item oublié.
- `if: ${{ !cancelled() }}` est constaté après un échec (run 44679310659). Après une annulation, son effet vient de la
  documentation de GitHub Actions telle que je la connais : ni relu à la source dans cette session, ni essayé.
- L'import de `test_digests_reference` par le script repose sur le mode d'import par défaut de pytest (`prepend`) et sur
  le dossier du script, que Python place dans `sys.path`. Ces deux conditions sont vérifiées ici et sur le runner de
  GitHub ; un passage à `--import-mode=importlib` n'a pas été essayé.

## 7. Ce qui reste

- **Le seuil et l'ordre de fusion** : portés à Sabine tant que le job était rouge sur le jeu du 08/11. #659 est
  fusionnée la première (62248c15) ; sur le jeu du 20/11, le job tient les seuils du 15/10, inchangés.
- **La péremption** : aucune des deux PR ne compare les `prompt_version` du jeu à celles du code. Décision de Sabine du
  20/11 : elle reste une limite écrite au README jusqu'après la certification.
- **Le rejeu partagé** : déplacer `replay_reference` dans `digests_reference.py` une fois #482 fusionnée (#659 l'est).
- **Le ruleset** : `digests-reference` n'est pas un contrôle requis à la fusion (geste de Sabine, hors de #482).
- **`POST /trend-reports`** : ses seuils attendent leur revue (#370).
