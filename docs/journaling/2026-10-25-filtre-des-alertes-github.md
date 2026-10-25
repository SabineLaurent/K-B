# Le filtre des alertes GitHub : `updated`, pas `reviewed`

- Date : 2026-10-25
- Branche : `fix/github-advisories-updated-filter`
- Issue : aucune (constat des fiches de sources du 2026-10-24, corrigé à la demande de Sabine)
- Fichiers : `src/k_b/etl/sources/github_advisories.py`, `tests/etl/sources/test_github_advisories.py`,
  `docs/specs-collecte.md`, `docs/requetes-extraction.md`

## Le pourquoi

K-B collecte les alertes de sécurité des paquets suivis, et ne veut que celles que GitHub a relues depuis la
dernière collecte : GitHub relit parfois une alerte des jours après l'avoir publiée. Pour cela, K-B envoyait
`reviewed=>=<veille de la dernière collecte>`. Ce filtre n'existe pas dans l'API, qui ignore un paramètre
inconnu sans erreur : `reviewed=>=2099-01-01` renvoie encore des alertes, `published=>=2099-01-01` aucune.
K-B recevait donc toujours les 100 alertes les plus récemment publiées, et ne triait sur la date de revue
qu'après. Une alerte ancienne relue récemment manquait dès que 100 alertes plus récentes la précédaient.

## Le comment

### La requête filtre et trie sur la date de mise à jour

`src/k_b/etl/sources/github_advisories.py:60-66` :

```python
            "sort": "updated",
            "per_page": ADVISORIES_PER_PAGE,
        }
        if last_collected_at is not None:
            # The filter is checked to the day only: a day of margin, then the exact comparison.
            since = last_collected_at.astimezone(UTC).date() - timedelta(days=1)
            query["updated"] = f">={since.isoformat()}"
```

L'API n'offre aucun filtre sur la date de revue. `updated_at` n'est jamais antérieur à `github_reviewed_at` :
une alerte relue depuis la dernière collecte a donc aussi été mise à jour depuis, et le filtre `updated`
la ramène. Il en ramène aussi d'autres (une alerte ancienne dont GitHub a seulement changé un champ) : la
comparaison exacte sur la date de revue, inchangée, les écarte.

### Ce qui est nouveau ne change pas

`fetch` compare toujours `reviewed_at` à la dernière collecte : seule la requête était fausse. Le tri
`sort=updated` met en tête les plus récemment mises à jour : si la page de 100 est pleine, ce sont les
mises à jour plus anciennes qui sont sur les pages suivantes. L'avertissement « page pleine » se fonde donc
sur la plus ancienne date de mise à jour de la page (`github_advisories.py:84-85`), d'où le champ
`updated_at` ajouté à `Advisory`, lu et vérifié comme les autres dates.

## Choix faits et options écartées

| Retenu | Écarté, et pourquoi |
|---|---|
| `updated` | `modified` (« publiée ou mise à jour ») : plus large sans gain, la mise à jour ne précède jamais la publication ni la revue |
| `sort=updated` à chaque collecte, première comprise | trier par publication (défaut) : une alerte ancienne relue récemment pourrait sortir de la page |
| Garder la marge d'un jour | la retirer : le filtre se lit au jour, comme celui d'avant |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| 200 alertes réelles (`pip`, `npm`, triées par mise à jour) : aucune avec `updated_at < github_reviewed_at` | le filtre `updated` ne perd aucune relecture |
| `updated=>=2099-01-01` → 0 alerte ; `reviewed=>=2099-01-01` → 100 | GitHub applique `updated` et ignore `reviewed` |
| Source réelle, dernière collecte au 2026-10-20 : 0 alerte (pip et npm) ; l'ancienne requête : 55 et 29 | la page n'est plus la même quelle que soit la date |
| Source réelle, npm depuis le 2026-07-01 : 3 alertes mises à jour, 2 relues après ; pip : 3 mises à jour, aucune relue, rien d'écrit | le filtre ramène, la comparaison sur la revue trie |
| `test_a_later_collection_asks_for_advisories_updated_from_the_day_before_the_last_one` | la requête porte `updated` et `sort`, plus jamais `reviewed` |
| `test_a_full_page_of_new_advisories_logs_the_count_read_and_the_oldest_date` | l'avertissement donne la plus ancienne mise à jour |
| 2 470 tests, ruff, mypy | rien d'autre n'a bougé |

## Ce que tu dois pouvoir défendre

- **Pourquoi l'erreur n'a-t-elle jamais échoué ?** L'API ignore un paramètre qu'elle ne connaît pas, sans
  erreur. Seule une requête qui doit renvoyer zéro (date en 2099) le montre.
- **Une mise à jour sans relecture fait-elle entrer une alerte ?** Non : `fetch` compare la date de revue à
  la dernière collecte (`github_advisories.py:78-79`) ; l'import écarte de toute façon une alerte déjà vue
  (`already_seen`).
- **Et si GitHub relisait une alerte sans changer `updated_at` ?** Rien ne l'a montré sur 200 alertes, et
  la relecture est elle-même une mise à jour ; c'est une observation, pas un contrat écrit de GitHub (voir
  plus bas).

## Zones non vérifiées

- La documentation de GitHub ne dit pas que `updated_at` suit `github_reviewed_at` : c'est observé sur
  200 alertes le 2026-10-25, pas garanti.
- Les tests e2e (11) n'ont pas été lancés.

## Ce qui reste

- Les pages suivantes ne sont toujours pas lues : seul l'avertissement le signale.
- `withdrawn_at` (alerte retirée par GitHub) n'est pas lu (constat des fiches de sources du 2026-10-24).

## Sources

| Source | Consultée |
|---|---|
| [REST API endpoints for global security advisories](https://docs.github.com/en/rest/security-advisories/global-advisories) | 2026-10-24 |
| Requêtes à `https://api.github.com/advisories`, sans jeton | 2026-10-25 |
