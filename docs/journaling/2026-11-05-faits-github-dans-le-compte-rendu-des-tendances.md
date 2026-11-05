# Les faits GitHub dans le compte rendu des tendances

- **Date** : 2026-11-05
- **Branche** : `feat/trend-report-github-facts`
- **Issue** : aucune propre ; part du contrat de `docs/tendances.md` que #369 ne citait pas
- **Fichiers principaux** : `src/k_b/post/trend_report_client.py`, `src/k_b/post/trend_report_sheets.py`, `src/k_b/items.py`

## Le pourquoi

L'API IA lit sur GitHub la fiche de chaque candidat et la rend à `kb`, mais `kb` ne la lisait pas :
le fichier du coffre donnait un critère et un sujet, rien sur le dépôt. Le premier essai réel du 05/11
a montré le manque : impossible de juger un choix du modèle en lisant le fichier. Le contrat disait
pourtant « le code rend les faits ». Cette PR écrit ces faits, sans appel de plus à GitHub ni au modèle.

## Le comment

### 1. La réponse est une entrée non fiable, relue par un schéma fermé

`kb` tient la réponse de l'API IA pour non fiable. Les faits passent donc par un modèle Pydantic dont
les bornes sont celles de la lecture sur GitHub :

```python
class RepositoryFacts(AiApiModel):
    license: SpdxId | None
    created_at: UtcDatetime
    language: GithubLanguage | None
```
(`src/k_b/post/trend_report_client.py:84`, extrait)

`UtcDatetime` convertit en UTC à la frontière : une date hors des bornes devient une réponse refusée,
pas une trace brute au moment d'écrire.

### 2. Une borne vit à un seul endroit

`Caution`, `SpdxId`, `GithubTopic` et `GithubLanguage` sont dans `k_b/items.py`, déjà partagé par `post`
et `ai_api`. `github_client.py` et `kb` lisent ainsi les mêmes motifs :

```python
type Caution = Literal["created_recently", "no_license"]
CAUTIONS: tuple[Caution, ...] = get_args(Caution.__value__)
```
(`src/k_b/items.py:223-224`)

### 3. Des faits qui se contredisent sont refusés

Le fichier s'écrit une seule fois : mieux vaut refuser que garder une contradiction.

```python
if (facts.license is None) != ("no_license" in facts.cautions):
    raise_invalid(response.request_id, f"{place}.facts.cautions", "not_the_license")
```
(`src/k_b/post/trend_report_client.py:294-295`)

Les faits d'un choisi doivent aussi être ceux de sa ligne du tableau (`not_those_of_the_table`). Un
choisi est toujours un candidat lu : une ligne sans faits le contredit aussi.

### 4. Le langage et la licence ne font ni lien ni champ

La ligne d'un choisi omet ce que GitHub ne donne pas :

```python
language = neutralize_digest_text(facts.language or "")
if language:
    parts.append(language)
```
(`src/k_b/post/trend_report_sheets.py:246-248`)

`neutralize_digest_text` échappe la syntaxe Markdown, les autoliens (`www.`) et les champs de Dataview
(`::`). Tester le résultat, et non l'entrée, écarte un langage fait d'espaces.

### 5. Une licence non reconnue n'est pas une licence absente

GitHub rend `NOASSERTION` pour une licence qu'il ne reconnaît pas, et `github_client.py` le traduit en
licence nulle. D'où le libellé :

```python
"no_license": "aucune licence reconnue par GitHub",
```
(`src/k_b/post/trend_report_sheets.py:98`)

### 6. D'où vient chaque nombre

Le fichier écrit désormais un total d'étoiles, qui vient de GitHub, sous une phrase sur l'échantillon de
GH Archive. Celle-ci parle donc des rangs, et dit d'où viennent les dates et les totaux
(`src/k_b/post/trend_report_sheets.py:75-79`). Les étoiles gagnées restent absentes du fichier.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Tous les faits sous les choisis, trois colonnes au tableau | Validé par Sabine : on juge la pertinence sur les choisis, et les 29 lignes restent lisibles | Tous les faits au tableau (trop large) ; une section à part (chercher chaque dépôt ailleurs) |
| 20 topics au plus | La limite déjà appliquée au modèle | Les 100 que GitHub peut rendre |
| Refuser une contradiction | Module « checked against itself », fichier écrit une fois | Écrire et laisser le lecteur voir |
| `neutralize_digest_text` | Un texte n'a pas à faire de lien | `neutralize_text`, qui laisse `www.` et `::` actifs ; prévu au départ, corrigé après revue |
| Types dans `k_b/items.py` | Règle du dépôt : une connaissance à un seul endroit | Une copie tenue égale par un test |
| Séparateur « ; » non échappé dans le langage | GitHub donne un nom de la liste fermée de Linguist | Exclure `;` du motif : un refus arrêterait tout le compte rendu pour un risque non montré |
| Pas de contrôle de `created_at` contre la date du jour | Confiance déjà accordée à l'API IA, sans effet sur la structure du fichier | Un contrôle de plus sans cas réel |

## Preuve

| Test ou sortie | Ce que ça démontre |
|---|---|
| `test_a_report_gives_its_period_its_limit_and_a_row_per_repository` | Le tableau complet, octet par octet, avec et sans faits |
| `test_the_repositories_chosen_are_listed_with_their_criteria_and_subjects` | La ligne de faits sous chaque choisi |
| `test_the_language_of_a_repository_chosen_makes_neither_link_nor_field`, `test_a_license_makes_no_link` | Ni lien, ni champ, ni balise |
| `test_the_day_of_creation_is_the_one_in_utc` | Le jour écrit est celui d'UTC |
| `test_facts_out_of_the_schema_are_refused_never_quoted` | Les bornes tiennent, valeur jamais citée |
| `test_facts_that_contradict_themselves_are_refused`, `test_the_facts_of_a_repository_chosen_are_those_of_the_table`, `test_a_repository_chosen_has_facts_in_the_table_when_it_is_there` | Les contradictions sont refusées |
| Revue de sécurité par un sous-agent : 30 valeurs hostiles passées dans le vrai schéma et le vrai rendu | Aucune vulnérabilité retenue |

## Ce que tu dois pouvoir défendre

- **Pourquoi relire ce que notre propre API envoie ?** Une réponse est une entrée : un défaut ou une
  compromission de l'API ne doit pas écrire n'importe quoi dans le coffre (`trend_report_client.py:84`).
- **Un propriétaire peut-il écrire ce qu'il veut dans le langage ?** Il peut le choisir par
  `.gitattributes`, mais dans la liste fermée de Linguist ; le langage reste une indication, pas une
  preuve. Les topics sont, eux, de vrais mots du propriétaire, bornés par un motif.
- **« Aucune licence reconnue », pourquoi pas « pas de licence » ?** GitHub répond aussi « aucune » pour
  une licence qu'il ne reconnaît pas : affirmer l'absence serait faux (`trend_report_sheets.py:98`).
- **Que devient un dépôt sans fiche ?** Au-delà de 60 candidats, sa ligne du tableau affiche `—`
  (`trend_report_sheets.py:338`) ; il ne peut pas être choisi.
- **Le total d'étoiles prouve-t-il la popularité ?** Non : il est lu sur GitHub, sans dire comment les
  étoiles ont été obtenues. Il informe, le choix reste à juger.

## Zones non vérifiées

- Aucun essai réel avec la phrase ni les faits : le fichier du 05/11 n'est pas réécrit.
- Le rendu n'a pas été vu dans Obsidian : la revue de sécurité a lu les octets produits.
- La liste fermée du langage vient du code public de Linguist et d'un petit échantillon ; un dépôt avec
  un `linguist-language` inconnu n'a pas été essayé sur github.com.
- `is_in_order_once` suppose que `find_cautions` garde l'ordre de `Caution` : tenu par deux assertions de
  tests, pas par une dérivation.

## Ce qui reste

- #369 : les textes du modèle, et le plan doit tenir compte de ces faits.
- #370 : revoir les seuils, trace Grafana, compte rendu d'essai.
