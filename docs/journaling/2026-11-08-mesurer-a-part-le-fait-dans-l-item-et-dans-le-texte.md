# Mesurer à part le fait trouvé dans l'item et le fait repris dans le texte

- Date : 2026-11-08
- Branche : `feat/fidelity-separate-measures`
- Issue : #518 (première issue du découpage de la refonte de la fidélité, avant #519 et #520)
- Fichiers principaux : `src/k_b/ai_api/stages/fidelity.py`, `src/k_b/ai_api/stages/checking.py`,
  `src/k_b/ai_api/digests.py`, `src/k_b/ai_api/observability/metrics.py`,
  `src/k_b/ai_api/observability/metric_instruments.py`, `tests/ai_api/test_digests_reference.py`
- Note liée : [Vérifier chaque fait d'une fiche](2026-10-24-verifier-chaque-fait-d-une-fiche.md)
  (#207, la fidélité telle qu'elle est née) ;
  [Enregistrer un jeu de référence des fiches](2026-11-08-enregistrer-un-jeu-de-reference-des-fiches.md) (#479).

## Le pourquoi

La fidélité d'une fiche dit si chaque fait d'une affirmation est **dans l'item qu'elle cite et
dans sa phrase**. Elle répondait aux deux questions par un seul booléen. Sur le jeu de référence
de #479, le taux est de 54 % (14 faits sur 26), et la mesure ne permettait pas de dire si le
modèle inventait ou s'il ne recopiait pas ses faits dans la phrase. La recherche de time-knight du
08/11 répond : les 26 faits sont tous dans leur item, et 12 manquent seulement à la phrase
française. La cause est la consigne (#519), pas une invention.

Cette PR rend la réponse lisible en production : deux comptes de plus, partout où la fidélité est
mesurée (ligne JSON, compteurs OpenTelemetry, span, raison d'un retrait). Elle ne change ni la
consigne, ni la borne des faits (#520), ni les seuils. Le taux de fidélité, le tableau et les
alertes de #164 restent tels quels.

## Le comment

### Une recherche, deux réponses : `FactSearch`

`src/k_b/ai_api/stages/fidelity.py:110-129` :

```python
class FactSearch:
    is_in_item: bool
    is_in_text: bool

    @property
    def is_found(self) -> bool:
```

Avant, `is_fact_found` rendait `is_found(value, text) and any(...)` : le `and` fondait les deux
questions et s'arrêtait à la première fausse. `search_fact` (`fidelity.py:252`) pose maintenant les
deux questions sans court-circuit et rend leurs deux réponses. `is_found` les recombine : un fait
« trouvé » reste un fait trouvé aux deux endroits, ce qui garde son sens à `facts_found`.

### Les mêmes règles pour chaque moitié

`fidelity.py:258-268` : pour un fait CVE ou GHSA, la moitié « item » est l'égalité de la forme
canonique avec `cve_id` ou `ghsa_id`, et la moitié « texte » est la présence de cet identifiant
parmi ceux lus dans la phrase. Pour un fait ordinaire (`fidelity.py:270-279`), c'est `is_found`
entre deux limites, dans chaque champ où chercher, puis dans la phrase. Les règles de #207 sont
reprises telles quelles, seulement réparties. Conséquence assumée et documentée
(`docs/fiches-veille.md`, « Les deux moitiés du fait trouvé ») : une CVE que l'item ne porte que
dans un texte libre compte comme absente de l'item. Un fait sans forme canonique
(`CVE-2026-86950 critique`) ou sans lettre ni chiffre ne compte nulle part.

### Où manque le fait : le code de retrait

`fidelity.py:163-167` :

```python
    refusals = [
        f"{FACT_NOT_FOUND}:{index}:{item_by_ref[fact.item_id].item_id}:{missing}"
        for index, (fact, search) in enumerate(zip(claim.facts, searches, strict=True))
        if (missing := search.missing_place) is not None
    ]
```

`missing_place` (`fidelity.py:121`) rend `item`, `text` ou `both`, un `Literal` fermé
(`fidelity.py:107`) : la trace d'une affirmation retirée ne porte que des codes, jamais un texte
(règle 5 de `poc.md`). `fact_not_found:1:6:item` se lit : le fait n° 1 est dans la phrase, mais pas
dans l'item 6.

### Des comptes de l'affirmation aux mesures de l'appel

`ClaimFidelity` gagne `facts_found_in_item` et `facts_found_in_text` (`fidelity.py:182`), que
`to_digest` additionne par sujet (`checking.py:97`). `digests.py:127` les passe au `StageCall`, d'où
ils partent sur la ligne JSON (`metrics.py:97`), dans deux compteurs
`k_b.digest.facts_found_in_item` et `k_b.digest.facts_found_in_text` (`metric_instruments.py:113`),
et sur le span `write_subject` (`digests.py:188`). Les autres étapes (classement, choix et rédaction
des tendances) passent `None` : leur ligne porte deux `null`.

### Les compteurs optionnels, une seule boucle

Ajouter deux `if` à `ModelMetrics.record_calls` portait sa complexité à 12, au-delà des 10 que
`ruff` permet (C901). `metric_instruments.py:171-184` remplace les neuf
`if count is not None: counter.add(...)` par une boucle sur les paires (compteur, compte), avec le
même comportement.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Deux comptes à côté de `facts_found`, qui garde son nom et son sens | le tableau et les alertes de #164 lisent `k_b_digest_facts_found_total` (critère de #518) | redéfinir `facts_found` comme « dans l'item » : casserait le taux et l'alerte `KbModelLowFidelity` |
| `fact_not_found:<fait>:<item>:<où>` | le préfixe reste : une requête Loki sur `fact_not_found` marche encore | trois codes distincts (`fact_not_in_item`…) : cassent cette lecture |
| `FACT_NOT_FOUND` inchangé | il est partagé avec la rédaction des tendances, que #518 ne touche pas | — |
| `None` écrit à la main dans les `StageCall` des autres étapes | aucun champ de `StageCall` n'a de défaut : un oubli est une erreur de type | un défaut `None` : un oubli passerait sans bruit |
| Boucle sur les paires dans `record_calls` | tient C901 sans la contourner (écart tranché par time-knight, règle de Sabine du 08/11) | `# noqa: C901` (contourne) ; une méthode extraite aux neuf `if` (complexité 10, à la limite) |
| Pas de court-circuit dans `search_fact` | chaque moitié doit être connue ; coût mesuré : rejeu entier en 0,06 s | un cache des champs normalisés : complexité sans besoin (constat 4 de la revue, non retenu) |
| Noms Grafana dans `NAMES_SEEN_IN_GRAFANA` seulement après les avoir vus | consigne de Sabine : le test compare aux noms que Grafana Cloud a montrés, pas à ceux qu'on devine | les ajouter d'office : le test ne prouverait plus rien |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_facts_found_are_those_found_both_in_their_item_and_in_the_text` (`tests/ai_api/test_fidelity.py`) | 3 faits : 2 dans l'item, 2 dans le texte, 1 aux deux ; `facts_found` compte les faits trouvés aux deux |
| `test_a_fact_not_found_says_whether_it_misses_its_item_its_text_or_both`, six cas | `item`, `text` et `both`, pour un fait ordinaire, une CVE et un fait sans lettre ni chiffre |
| `test_each_call_writes_one_json_line_on_stdout_without_a_text`, `test_the_fidelity_rate_is_the_facts_found_over_the_facts_checked` (`tests/ai_api/test_digest_router.py`) | la ligne JSON porte les deux champs, à leur place, avec 2 et 3 sur un cas connu |
| `test_each_call_is_measured_in_opentelemetry_as_on_its_line` | chaque compteur vaut la somme des lignes `write` |
| `test_each_claim_removed_is_an_evaluation_tied_to_its_last_request` | l'évaluation dit `fact_not_found:1:6:item` ; le span porte `(3, 2, 2, 3)` |
| `test_the_facts_of_the_set_are_all_in_their_item_not_all_in_their_text` (`tests/ai_api/test_digests_reference.py`) | rejeu du jeu de #479 : 26 vérifiés, 26 dans l'item, 14 dans le texte, 14 trouvés |
| Les 12 tests ci-dessus lancés avant le code | 12 échecs (attribut, clé ou code absents) : les tests mordent |
| `make sandbox-alerts` sur la branche, puis Explore : `count by (__name__) ({deployment_environment_name="sandbox", __name__=~"k_b_digest_facts_.*"})` | Grafana Cloud montre `k_b_digest_facts_found_in_item_total` et `k_b_digest_facts_found_in_text_total` à côté des deux anciens : ces noms entrent dans `NAMES_SEEN_IN_GRAFANA` (`tests/test_grafana_files.py`) |
| `uv run pytest -q` après cet ajout | 4 087 tests passent |

## Ce que tu dois pouvoir défendre

- **Pourquoi ne pas avoir simplement changé `facts_found` ?** Parce que le tableau et l'alerte de
  #164 le lisent, avec le sens « dans l'item et dans le texte ». Les deux nouveaux comptes
  s'ajoutent sans rien casser (`metric_instruments.py:113`).
- **« Absent de l'item » veut-il dire « inventé » ?** Pas toujours : la moitié « item » suit les
  règles de la fidélité, et une CVE n'y est cherchée que dans `cve_id` et `ghsa_id`. Une CVE écrite
  dans le corps d'une release compte comme absente. D'où la formulation de la doc : « inventé ou
  pris hors de ces règles » (`fidelity.py:258-268`).
- **La trace d'un retrait peut-elle laisser fuir un texte ?** Non : `<où>` est un `Literal` fermé,
  la position et l'item sont des entiers (`fidelity.py:107`, `fidelity.py:164`).
- **Pourquoi toucher aux compteurs qui n'ont rien à voir avec la fidélité ?** Deux `if` de plus
  dépassaient la complexité permise (C901). La boucle traite les neuf compteurs optionnels de la
  même façon, et le test des compteurs prouve que le comportement n'a pas changé.
- **Le test du jeu de référence restera-t-il vrai ?** Non, et c'est voulu : il mesure `write-1`. Le
  nouvel enregistrement de Sabine après la nouvelle consigne (#519) changera ses nombres, et la
  comparaison aux 54 % se fera là.

## Zones non vérifiées

- Au bac à sable, le scénario du coût a échoué une fois sur un envoi de mesures
  (`Failed to export 'metrics' batch due to timeout, max retries or shutdown`), cause non établie ;
  les trois autres scénarios ont envoyé les deux compteurs.
- La production n'envoie plus de mesures depuis le passage de la pile à l'offre gratuite (jeton
  OTLP à refaire) : les deux compteurs n'y ont pas été vus.

## Ce qui reste

- Lire les deux compteurs dans le tableau de bord : relève de #164 (en option dans sa PR de
  fermeture).
- La consigne sans contradiction (#519), la borne des faits courts (#520), puis le nouvel
  enregistrement du jeu de référence et la fidélité remesurée.
- La même séparation pour la rédaction des tendances : hors de #518.
