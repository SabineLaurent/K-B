# Définir la fidélité comme le code la mesure

- Date : 2026-11-09
- Branche : `docs/fidelity-definition`
- Issue : #164 (Part of, sans fermeture)
- Fichiers : `documentation/monitoring_pour_docu.md`, `observability/grafana/alert-rules.yaml`,
  `observability/grafana/dashboard.json`
- Note précédente du même sujet :
  [2026-11-08, mesurer à part le fait dans l'item et dans le texte](2026-11-08-mesurer-a-part-le-fait-dans-l-item-et-dans-le-texte.md)
  (#518)

## Le pourquoi

La fiche de monitorage, la description de l'alerte `KbModelLowFidelity` et celle du panneau « Fidélité sur 24 h »
disaient que la fidélité est la part des faits trouvés dans l'item que leur affirmation cite. Une relecture du 08/11
l'a jugé faux, et le jury lit ces trois textes. Un fait n'est pas compté trouvé s'il est seulement dans l'item : il doit
être aussi dans le texte où il est affirmé. Et les compteurs lus par l'alerte reçoivent aussi les faits du compte
rendu des tendances, qui n'ont pas d'item. La PR écrit une seule définition, celle du code, aux trois endroits, et
corrige le point « Ce que la fidélité mesure aujourd'hui » des limites.

## Le comment

### Un fait d'une fiche : dans le texte et dans l'item

```python
    @property
    def is_found(self) -> bool:
        """In the item it cites and in the text of its claim."""
        return self.is_in_item and self.is_in_text
```

`src/k_b/ai_api/stages/fidelity.py:115-118`. Le `and` est le cœur de la correction : l'ancien texte ne disait que
la moitié `is_in_item`. L'item cherché est celui que le fait désigne (`item_by_ref[fact.item_id]`,
`fidelity.py:155`), et la sortie du modèle est refusée si ce `item_id` n'est pas parmi les items que l'affirmation
cite (`stages/writing.py:173`). D'où « l'item que chacun désigne ».

### Un fait des tendances : dans son texte et dans la source de ce texte

```python
    return is_found(value, normalize(text)) and any(
        is_found(value, source) for source in sources
    )
```

`src/k_b/ai_api/stages/trend_writing.py:545-547`. Un fait des tendances est une chaîne seule
(`WrittenText.facts: list[str]`, `trend_writing.py:163`) : il ne désigne rien. Sa source est fixée par le nom du
texte où il est (`sources`, `trend_writing.py:383-391`). D'où « la source de leur texte ».

### Les deux étapes dans les mêmes compteurs, sommées

`metric_instruments.py:178-179` ajoute `stage_call.facts_checked` et `stage_call.facts_found` aux compteurs
`k_b.digest.facts_checked` et `k_b.digest.facts_found`, pour toute étape qui n'a pas `None`. Deux étapes en ont :
`write` (`digests.py:125-126`) et `write_trends` (`trend_writing.py:582-583`). L'alerte les somme sans filtre par
étape :

```yaml
          sum by (deployment_environment_name) (max_over_time(k_b_digest_facts_found_total[24h]))
            / (sum by (deployment_environment_name) (max_over_time(k_b_digest_facts_checked_total[24h])) > 0)
```

`observability/grafana/alert-rules.yaml:33-34`, de même dans le tableau (`dashboard.json:236`, `:248`, `:570`).
La définition écrite décrit donc ce mélange, puisque c'est lui que le jury voit.

### La phrase, aux trois endroits

« la part des faits retrouvés à la fois dans le texte où ils sont affirmés et dans leur source: l'item que chacun
désigne, pour les fiches de veille, la source de leur texte, pour le compte rendu des tendances »
(`monitoring_pour_docu.md:26`, `alert-rules.yaml:41`, `dashboard.json:218`). Le point des limites
(`monitoring_pour_docu.md:167-172`) parle des seules fiches (le jeu de #479) : il dit que le contrôle exige le fait
« mot pour mot après normalisation (un CVE ou un GHSA sous sa forme canonique) », à la fois dans le texte français et
dans l'item, car un CVE est comparé sous sa forme canonique (`fidelity.py:258-269`), pas comme du texte.

## Choix faits et options écartées

- **Décrire le mélange des deux étapes** (time-knight, délégation de Sabine du 15/10). Écarté : garder une phrase
  propre aux fiches et renvoyer l'écart à « Not verified » (le jury lirait une définition fausse pour une partie des
  faits comptés) ; ajouter un filtre `k_b_stage` aux expressions (constat en pause avec #164, hors de cette PR).
- **« l'item que chacun désigne » plutôt que « la source qu'ils désignent »** : un fait des tendances ne désigne
  rien (`trend_writing.py:163`).
- **« fiches de veille »**, le terme du dépôt et du reste de la fiche (`monitoring_pour_docu.md:29`, `:50`), plutôt
  que « comptes rendus de veille par sujet » (constat 5 de la relecture).
- **Pas d'espace avant les deux-points** : convention tenue par `test_no_text_has_a_space_before_a_colon_or_a_semicolon`
  (`tests/test_grafana_files.py`), choix 30 de Sabine.
- **Ne pas nommer les quatre sources des tendances** ni les champs cherchés d'un item : le détail est dans
  `docs/tendances.md:216-217` et `docs/fiches-veille.md`, « Fidélité » ; trois descriptions s'allongeraient.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest tests/test_grafana_files.py -q` → 17 passed | les deux fichiers Grafana restent conformes (seuil cité, pas d'espace avant `:`) |
| `uv run pytest -q` → 4091 passed, 332 deselected | rien d'autre n'est cassé |
| `git grep` de l'ancienne phrase, la commande du critère de fin de la mission → aucune ligne | l'ancienne définition a disparu, de cette note aussi |
| `git grep -n "leur source: l'item que chacun désigne"` → 4 lignes : les trois de la définition, et celle-ci | la même phrase aux trois endroits |
| relecture du delta par un sous-agent neuf, contre le code | 4 constats d'exactitude, 3 de style ; 1, 3 et 5 corrigés, les autres laissés (tri de time-knight) |

## Ce que tu dois pouvoir défendre

- **Pourquoi « à la fois » ?** Un fait dans l'item mais absent du texte n'est pas compté : le texte n'affirme pas ce
  fait. `fidelity.py:118`, `trend_writing.py:545`.
- **Pourquoi parler des tendances dans l'alerte des fiches ?** Parce que l'alerte somme leurs faits avec ceux des
  fiches (`alert-rules.yaml:33-34`, sans `k_b_stage`). Le filtre qui les séparerait est en pause avec #164.
- **Un fait peut-il citer un item que l'affirmation ne cite pas ?** Non : la sortie entière est refusée
  (`writing.py:173`).
- **« Mot pour mot » vaut-il pour un CVE ?** Non : il est comparé sous sa forme canonique, seulement aux champs
  `cve_id` et `ghsa_id` de l'item (`fidelity.py:258-269`, `:319-321`).

## Zones non vérifiées

- Le tableau et l'alerte de Grafana Cloud gardent l'ancien texte jusqu'au réimport des deux fichiers (en pause avec
  #164) : rien n'a été lu dans Grafana.
- « L'anglais de l'item » (`monitoring_pour_docu.md:172`) n'est pas un contrôle du code : c'est la langue observée
  des sources.

## Ce qui reste

Le filtre `k_b_stage`, le seuil, le réimport dans Grafana Cloud et l'essai d'accessibilité, en pause avec la
fermeture de #164.
