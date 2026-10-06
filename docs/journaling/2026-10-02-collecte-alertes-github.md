# La collecte des alertes de sécurité GitHub : les paquets des dépôts suivis, à leur date de revue

Suite de [la collecte des releases GitHub](2026-10-02-collecte-releases-github.md), dont elle
reprend la connexion (`github_api.py`) et la logique d'incrémental.

- **Date** : 2026-10-02
- **Branche** : `feat/github-advisories` (commits `d0b8bc7` pour la collecte, `4beb52a` pour la
  correction de la date suivie, le retrait de `langchain-classic` et les entrées d'ADR)
- **Issue** : #11 « Collecter les alertes de sécurité GitHub et les dépôts les plus étoilés » :
  **partie alertes seulement**. Les dépôts les plus étoilés feront l'objet d'une autre PR.
- **Fichiers principaux** : `src/k_b/tracked_repositories.py` (dépôts et paquets suivis),
  `src/k_b/github_advisories_source.py` (collecte), `src/k_b/github_advisories.py` (lecture), et
  leurs tests ; la fixture `tests/fixtures/github_advisories_extract.json`.
- **Autres fichiers** : `src/k_b/collect.py` (déclare les sources), `src/k_b/github_releases_source.py`
  (sa liste de dépôts part dans `tracked_repositories.py`), `docs/sources.md`, `docs/specs-collecte.md`,
  `docs/registre-traitements.md` (personnes créditées), journal ADR (trois décisions).

## Le pourquoi

La veille de K-B doit dire quand un outil suivi a une faille connue. Ici, ces outils sont
LangChain, LangGraph, LlamaIndex et Claude Code. GitHub tient une base publique de ces failles, les
*security advisories*, chacune identifiée par un `GHSA-…`, souvent doublé d'un `CVE-…`.

Le périmètre a été tranché par Sabine. **La sécurité de ses propres projets relève de
Dependabot**, déjà activé sur K-B : il lit les fichiers de verrouillage et propose les
corrections. **K-B ne fait que la veille** : les alertes des paquets publiés par les dépôts
qu'elle suit. CISA KEV, déjà en place, dit en plus si une faille est activement exploitée.

## Le comment

### 1. Une seule liste pour les releases et les alertes

```python
TRACKED_REPOSITORIES = (
    TrackedRepository(
        "langchain-ai/langchain", "pip", ("langchain", "langchain-core", "langchain-text-splitters")
    ),
    TrackedRepository("langchain-ai/langgraph", "pip", ("langgraph", "langgraph-checkpoint")),
    TrackedRepository("run-llama/llama_index", "pip", ("llama-index", "llama-index-core")),
    TrackedRepository("anthropics/claude-code", "npm", ("@anthropic-ai/claude-code",)),
)
```
(`src/k_b/tracked_repositories.py:19`)

En #10, la liste des dépôts était une simple suite de noms dans `github_releases_source.py`.
Chaque dépôt déclare maintenant aussi son écosystème (`pip` pour PyPI, `npm`) et ses paquets
principaux. Suivre un nouveau dépôt, c'est ajouter **une** ligne, qui donne à la fois ses releases
et ses alertes : la connaissance « ce que K-B suit sur GitHub » vit à un seul endroit (DRY).
L'écosystème est un `Literal["pip", "npm"]` : un type fermé, qui refuse toute autre valeur à la
vérification de types.

`list_packages_by_ecosystem` regroupe les paquets par écosystème, dans l'ordre des dépôts :

```python
        known_packages = packages_by_ecosystem.get(repository.ecosystem, ())
        packages_by_ecosystem[repository.ecosystem] = known_packages + repository.packages
```
(`src/k_b/tracked_repositories.py:34`)

`collect.py` en tire une source par écosystème : `github_advisories_pip` et
`github_advisories_npm` (`src/k_b/collect.py:36`).

### 2. La requête : seulement les paquets suivis, depuis la dernière revue

```python
        query = {
            "type": "reviewed",
            "ecosystem": self.ecosystem,
            "affects": ",".join(self.packages),
            "per_page": ADVISORIES_PER_PAGE,
        }
        if last_collected_at is not None:
            # The filter is checked to the day only: a day of margin, then the exact comparison.
            since = last_collected_at.astimezone(UTC).date() - timedelta(days=1)
            query["reviewed"] = f">={since.isoformat()}"
        raw_response = get_from_github_api(f"advisories?{urlencode(query)}")
```
(`src/k_b/github_advisories_source.py:36`)

- **`type=reviewed`** : seulement les alertes relues par l'équipe de GitHub. Les autres sont des
  imports bruts, non vérifiés.
- **`affects=`** : le filtre par paquets se fait **dans la requête**. C'est une exception à la
  règle du brut intact, comme pour arXiv, décidée et consignée dans l'ADR : sans elle, tout
  l'écosystème npm dépasse 100 alertes par semaine, et il faudrait paginer.
- **`reviewed=>=<veille de la dernière collecte>`** : la syntaxe a été testée sur l'API. Un
  intervalle ouvert `AAAA-MM-JJ..` est refusé (422), `>=AAAA-MM-JJ` est accepté. Le filtre est
  passé au jour près, donc on prend un jour de marge, puis on compare à la seconde près dans le
  code (section 3).
- **`urlencode`** échappe chaque valeur : le `@` et le `/` de `@anthropic-ai/claude-code`
  deviennent `%40` et `%2F`, et ne peuvent pas casser la requête. La revue de sécurité l'a vérifié.

### 3. Suivre la date de revue, pas la date de publication

```python
        review_dates = [advisory.reviewed_at for advisory in read_advisories(raw_response)]
        if not review_dates:
            return None
        if last_collected_at is None:
            return raw_response
        if not any(reviewed_at > last_collected_at for reviewed_at in review_dates):
            return None
```
(`src/k_b/github_advisories_source.py:47`)

C'est la correction apportée après la revue de code. La première version filtrait sur la date de
**publication**. Or, sur l'API, 12 alertes Maven sur 100 avaient été relues jusqu'à deux semaines
après leur publication. Le scénario de perte :
1. une alerte est publiée lundi, pas encore relue ;
2. la collecte de mardi ne la voit pas, puisqu'on ne demande que les alertes relues ;
3. elle est relue jeudi ;
4. la collecte suivante demande « publiées depuis mardi » : l'alerte, publiée lundi, n'en fait
   pas partie. Elle est **perdue pour toujours, sans avertissement**.

Avec la date de revue, l'étape 4 la ramène, puisqu'elle a été relue après mardi.

Le reste reprend la logique des releases : une réponse vide ou sans rien de neuf renvoie `None`,
donc aucun fichier n'est écrit. Quand il y a du neuf, la réponse entière est écrite octet pour
octet. Si la page de 100 est pleine et entièrement plus récente que la dernière collecte, un
avertissement est journalisé (`github_advisories_source.py:54`).

### 4. La lecture : des identifiants contrôlés, sans les personnes créditées

```python
GHSA_ID = re.compile(r"GHSA(-[23456789cfghjmpqrvwx]{4}){3}")
SEVERITIES = ("low", "medium", "high", "critical", "unknown")
```
(`src/k_b/github_advisories.py:10`)

`read_advisories` produit des `Advisory` : GHSA, CVE (ou `None`), résumé, gravité, URL, dates de
publication et de revue, paquets touchés. Chaque champ est contrôlé à la frontière :
- le GHSA et le CVE avec `fullmatch`. Le format CVE est importé de `cisa_kev.py` (`CVE_ID`) pour
  ne pas l'écrire deux fois ;
- la gravité dans un ensemble fermé ;
- l'URL sous `https://github.com/advisories/` ;
- les dates avec fuseau, par `parse_github_date`, qui sert pour les deux champs de date.

Une alerte décrit une plage de versions vulnérables par entrée de `vulnerabilities`. Le même
paquet peut donc y apparaître deux fois : `parse_package_names` garde chaque nom une seule fois,
dans l'ordre.

`Advisory` n'a **aucun champ pour `credits`**, les logins GitHub des personnes qui ont trouvé ou
corrigé la faille. C'est une donnée personnelle, inutile à la veille (minimisation). Elle reste
dans le brut, et le registre des traitements le dit désormais.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Périmètre | **Paquets des dépôts suivis** ; les projets de Sabine relèvent de Dependabot (décidé par Sabine) | Tout `pip` : 43 alertes par semaine, recoupe Dependabot. Tous les écosystèmes : plus de 180 par semaine. `actions` : couvert par Dependabot. `pnpm` : pas utilisé. `uv` : dépôt « sous le coude » |
| Paquets | **Ceux publiés par le dépôt suivi et maintenus**, vérifiés sur PyPI et npm | `langchain-community`, `langchain-experimental` : dépôts archivés. `langchain-classic` : compatibilité v0, non utilisée (décidé par Sabine) |
| Où déclarer les paquets | **À côté de chaque dépôt**, dans `tracked_repositories.py` | Une liste de paquets séparée : deux listes à tenir d'accord |
| Filtre | **Dans la requête** (`affects=`), exception consignée dans l'ADR | Brut de tout l'écosystème, filtre à la lecture : plus de 100 alertes npm par semaine, donc pagination obligatoire |
| Date suivie | **Date de revue** (`reviewed`, `github_reviewed_at`), après la revue de code | Date de publication : perte silencieuse des alertes relues tard. Date de mise à jour (`updated`) : ramène une alerte à chaque modification |
| Sources | **Une par écosystème** : une requête porte un seul `ecosystem` | Une par paquet : 7 requêtes au lieu de 2, sans gain |
| Logique incrémentale | **Copiée de `github_releases_source.py`**, pas factorisée | Une fonction commune : c'est la deuxième occurrence, et `code.md` factorise à la troisième |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_packages_are_grouped_by_ecosystem_in_the_order_of_the_repositories` | Le regroupement par écosystème garde l'ordre |
| `test_each_ecosystem_of_the_tracked_repositories_is_a_source_of_kb_collect` | `pip` et `npm` sont des sources de `kb collect` |
| `test_a_first_collection_asks_for_the_reviewed_advisories_of_the_packages` | La requête exacte : `type`, `ecosystem`, `affects`, `per_page` |
| `test_a_later_collection_asks_for_advisories_reviewed_from_the_day_before_the_last_one` | Filtre sur la revue, avec un jour de marge, et plus sur la publication |
| `test_an_advisory_published_before_the_last_collection_but_reviewed_after_is_new` | Le scénario de perte décrit plus haut ne se produit plus |
| `test_a_page_without_any_new_advisory_returns_nothing`, `test_an_empty_first_collection_returns_nothing` | Rien de neuf, rien d'écrit |
| `test_a_full_page_of_new_advisories_warns…`, `test_no_warning_when…` | L'avertissement sort quand il le faut, et seulement à ce moment-là |
| `test_the_credited_people_are_not_kept` | `Advisory` n'a pas de champ pour les crédits |
| `test_an_invalid_advisory_is_refused_with_its_position` (8 cas) | GHSA, CVE, gravité, résumé, URL, dates, nom de paquet : chaque champ invalide est refusé |
| `uv run pytest` : 92 tests verts | Les releases de #10 fonctionnent toujours avec la nouvelle liste |
| Vrai `kb collect` (avant la correction de date) : 7 sources `ok`, 55 alertes `pip` et 28 `npm` lues sans erreur ; second passage : aucun brut de plus | Le lecteur accepte de vraies alertes ; l'incrémental fonctionne |
| Vrai `kb collect` après la correction, deux passages : 7 sources `ok` puis 7 `ok` sans brut de plus (le second envoie le vrai filtre `reviewed=>=…`) | La requête corrigée est acceptée par l'API ; l'incrémental fonctionne |
| `/security-review` en sous-agent sans contexte | Aucune faille rapportée |
| `/code-review` en sous-agent sans contexte | Un constat (la date suivie), vérifié sur l'API et corrigé avec l'accord de Sabine |

## Ce que tu dois pouvoir défendre

1. **Pourquoi K-B ne surveille-t-il pas les dépendances de tes projets ?** Dependabot le fait
   mieux : il lit `uv.lock`, voit les dépendances indirectes et propose la correction. Le faire
   dans K-B demanderait aussi un jeton avec des droits de lecture sur ces alertes, contre le
   moindre privilège (journal ADR, 2026-10-02).
2. **Pourquoi filtrer dans la requête, alors que la règle est « brut intact » ?** Parce que le
   brut de tout npm dépasse une page par semaine. C'est une exception décidée et tracée, comme
   pour arXiv (`github_advisories_source.py:39`).
3. **Pourquoi la date de revue ?** Parce qu'on ne demande que les alertes relues. Une alerte
   relue après la collecte suivante serait perdue avec la date de publication. Le cas a été
   observé sur l'API (`github_advisories_source.py:45`).
4. **Où sont les données personnelles ?** Dans `credits`, dans le brut seulement. `Advisory` ne
   les lit pas, et le registre des traitements les déclare.
5. **Si `langchain` publie un nouveau paquet (une intégration) ?** Il n'est pas suivi tant
   qu'on ne l'ajoute pas à `tracked_repositories.py`. C'est la limite assumée d'une liste tenue à
   la main.

## Zones non vérifiées

- **L'alphabet des GHSA** (`23456789cfghjmpqrvwx`) n'a pas été vérifié dans une documentation.
  Il est tiré du format observé, et les 83 alertes réelles collectées (55 `pip`, 28 `npm`) le
  respectent. Une alerte au format différent ferait échouer la lecture du brut, donc l'écriture
  de toute la source : l'échec serait visible, pas silencieux.
- **La gravité `unknown`** est acceptée sans l'avoir vue dans une réponse réelle.
- **L'ordre des résultats** reste celui de l'API, par date de publication. Avec une page pleine,
  les alertes manquantes seraient les plus anciennement publiées, pas forcément les moins
  récemment relues. Sans effet tant que l'avertissement ne sort pas.

## Ce qui reste

- **Les dépôts les plus étoilés** : seconde moitié de #11, à concevoir (sens de « plus étoilés »,
  `topic`).
- **Une alerte modifiée après sa revue** (gravité changée, retrait) n'est pas recollectée.
  Limite assumée, consignée dans l'ADR.
- **Le passage des `Advisory` à l'item commun** et à la base, avec la fusion (CVE en commun avec
  CISA KEV : le dédoublonnage par CVE est prévu dans `specs-collecte.md`).
- **Le résumé (`summary`)** est un texte libre écrit par un tiers. Le jour où un agent lira les
  items, ce texte sera une donnée, jamais une instruction (remarque de la revue de sécurité).
