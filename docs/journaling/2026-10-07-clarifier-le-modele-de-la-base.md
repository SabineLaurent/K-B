# Clarifier le modèle de la base : des sources au MLD

- **Date** : 2026-10-07
- **Branche** : `docs/clarify-data-model`
- **Issue** : aucune propre (mission « clarifier ce que K-B doit faire ») ; touche #105, #84, #57
- **Fichier principal** : `docs/2026-10-07-clarification-modele.md`
- **Série** : fait suite à [2026-10-05-creer-la-base.md](2026-10-05-creer-la-base.md), qui
  expliquait le schéma actuel (`src/k_b/database/schema.sql`) ; cette note explique ce qui le
  remplace.

## Le pourquoi

Le 06/10, « laisser la base dédoublonner les items » (#105) bloquait sur une question de modèle :
comment interdire un même CVE deux fois dans une même source, alors que le CVE vit dans une table
et la source dans une autre ? En creusant, d'autres questions sont apparues : ce que les sources
donnent vraiment, ce que Sabine demandera à K-B, ce qu'est un « item ». La séance n'a rien codé :
elle a relevé les faits (sur une première vraie collecte, lancée source par source), noté les
parcours et décidé un nouveau modèle. Le code et la doc de stockage suivront dans des issues à
part.

## Le comment

### 1. Une donnée brute contient des items

Le schéma actuel appelle `collection` un fichier brut, sans le relier à sa source. Le mot faisait
penser au lancement de `kb collect`, qui touche plusieurs sources ; d'où l'idée, écartée, d'une
association plusieurs-à-plusieurs. Le modèle décidé (`docs/2026-10-07-clarification-modele.md:146-150`) :

```
- **SOURCE ─0,n─ (FOURNIR) ─1,1─ DONNÉE BRUTE ─1,n─ (CONTENIR) ─1,1─ ITEM.** Une donnée brute
  est un fichier de `raw/` : le `.xml` d'arXiv, le `.csv` de CISA, un `.html` de TLDR (une
  édition, un jour). Un item est une entrée de ce fichier : une `<entry>`, une ligne, un
  `<article>`.
```

Une donnée brute appartient à une seule source (1,1) : c'est un fichier d'un dossier de source.
La table de liaison « source × lancement » qu'avait imaginée Sabine, c'est exactement ce fichier.
Une sous-catégorie de source (les éditions `tldr_ai`, `tldr_infosec`) devient l'attribut `flux`
de la donnée brute (`:151`), qui vaut le nom du dossier brut : pas de table, pas de nouvelle
source.

### 2. Catalogue d'état contre flux de nouveautés

Toutes les sources relisent une partie de ce qu'elles ont déjà (marges d'arXiv, des alertes, de
TLDR) ; deux téléchargent tout : CISA KEV et le top 100 GitHub. CISA n'est pas un flux : c'est un
**catalogue d'état**, dont les lignes sont modifiées sur place (`:156-169`) :

```
  - une ligne connue garde son identité (`item_id`, CVE) ; tout le reste, titre compris, est
    remplacé par la dernière version si le contenu diffère, et `revised_at` prend la date de la
    collecte qui a constaté le changement ; une ligne identique ne change rien ;
  - une ligne connue absente du catalogue est marquée retirée : `withdrawn_at` prend la date de la
```

`revised_at` rend un changement visible à « quoi de neuf » (P1) : sans elle, une faille ajoutée
en 2023 qui devient exploitée par un rançongiciel garderait sa vieille `dateAdded`. `withdrawn_at`
évite qu'une disparition passe sous silence. L'historique n'est pas en base : le brut garde chaque
catalogue. La règle « premier vu ou dernier vu » (D6 de la revue) se règle donc par nature de
source, pas une fois pour toutes.

### 3. Des référentiels épais, chacun avec la source qui fait foi

Un référentiel est une chose de référence, avec un identifiant officiel, dont le contenu vient de
la source qui fait autorité :

- **PAPER** : arXiv, éditeur des papiers. Zotero, prévu en v0, pointera vers le même papier.
- **CVE** : CISA KEV. Dans la liste CVE, l'autorité est le programme CVE et ses CNA ; la NVD
  enrichit (CVSS, CWE). Mais le périmètre de K-B est celui des failles **exploitées de façon
  avérée**, dont KEV est la liste officielle. Le record d'un CVE a été regardé
  (`CVE-2026-69086`) : un conteneur `cna` et un conteneur `CISA-ADP` qui porte une évaluation SSVC
  (`"Exploitation": "none"`) ; la liste CVE (3,9 Go décompressée) n'est pas collectée.
- **NEWSLETTER_ARTICLE** : TLDR fait foi pour **son** résumé. Sa clé est (édition, date, rang),
  pas l'URL : deux éditions peuvent résumer le même article (`:213-216`).

### 4. La spécialisation : ITEM minimal, sous-types à clé partagée (option D)

C'est la généralisation / spécialisation de Merise 2 (1992) : « un papier *est un* item ». ITEM
porte ce qui est commun ; chaque sous-type porte son contenu (`:217-224`) :

```
- **Option D : ITEM minimal, clé partagée.** ITEM ne porte que `item_id`, la donnée brute de sa
  version actuelle et `kind` (`paper`, `vulnerability`, `newsletter_article`). Chaque sous-type
  (PAPER, CVE, NEWSLETTER_ARTICLE) a pour clé primaire `item_id`, qui est aussi sa clé étrangère
  vers ITEM (règle 4 du MLD de `docs/stockage.md`).
```

Une table de sous-type est une table ordinaire dont la clé primaire **est** la clé de l'item :
relation 1 pour 1, pas de ligne sans parent. Le schéma actuel le faisait déjà pour une partie
(`src/k_b/database/schema.sql:86-89`) :

```sql
CREATE TABLE vulnerability (
    item_id INTEGER PRIMARY KEY REFERENCES item (item_id) ON DELETE CASCADE,
    cve     TEXT CHECK (cve GLOB 'CVE-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]*')
) STRICT;
```

La différence : ici le contenu restait dans ITEM et le CVE n'était pas unique (`:84-85`) ; dans D,
tout le contenu passe au sous-type et `cve_id` y est unique. Le dédoublonnage de #105 est alors
porté par les clés naturelles (`arxiv_id`, `cve_id`, édition + date + rang). Notre spécialisation
est une **partition** : chaque item est dans exactement un sous-type (exclusion X et totalité T).
L'exclusion se garantit en base par une clé étrangère composée (`item_id`, `kind`) ; la totalité,
par l'import, qui écrit l'item et son sous-type dans la même transaction.

### 5. Les auteurs, un attribut de PAPER

`:208-212` : les auteurs sont un tableau JSON dans PAPER, sans table `author` ni table de
liaison. Aucun parcours ne cherche par auteur ; la valeur est une mention d'affichage que la base
ne découpe jamais. Le modèle n'a donc plus aucune table de liaison (`:225`).

### 6. Les parcours v0 : recherche, filtres, classements

Sans LLM en v0, K-B n'a pas de questions en langage naturel : un champ de recherche, des filtres
(période, type, source) et trois classements (`:26-29`). Chaque parcours dit ce qu'il demande à
la base, et une colonne dit s'il lui faudrait un LLM (`non par mots-clés, oui par le sens` pour
une recherche par sujet).

## Choix faits et options écartées

| Décision | Retenu | Écarté, et pourquoi |
|---|---|---|
| Nom de l'entité « fichier brut » | DONNÉE BRUTE | COLLECTE : évoque le lancement |
| Lancement de `kb collect` | pas d'entité pour l'instant | LANCEMENT + DÉCLENCHER : aucun parcours v0 ne s'en sert ; viendra avec la surveillance des exécutions |
| Sous-catégorie de source | attribut `flux` | une source par édition (GitHub en aurait une douzaine) ; entité FLUX (aucun attribut propre) |
| CISA KEV | catalogue d'état : dernière version, `revised_at`, `withdrawn_at` | premier vu : perdrait les changements silencieux ; suppression : ferait disparaître sans trace |
| Lien entre items décrivant la même chose | référentiels typés | SUJET générique : nom gênant, et type incertain pour les liens TLDR |
| Épaisseur des référentiels | épais, une source fait foi | minces : l'item garderait le contenu, d'où un doublon de rôle |
| Liste CVE | non collectée | hors du périmètre (failles non exploitées), 3,9 Go |
| Traduction en tables | D : ITEM minimal, clé partagée | B : clés étrangères facultatives dans ITEM (doublon de rôle) ; C : pas de table ITEM, vue `UNION` (une table de liaison par type pour les notes) |
| Auteurs | attribut JSON de PAPER | `author` + `paper_author` : aucun parcours ; texte séparé par des virgules : un nom peut contenir une virgule |
| Usage de la v0 | recherche + filtres + classements | une liste de questions : les tops et les filtres ne sont pas des questions |

Imposés par les consignes du dépôt : K-B déterministe (un référentiel épais ne choisit pas entre
deux textes : d'où une seule source qui fait foi) ; RGPD et RGESN 1.6 (minimiser : pas
d'historique en base, pas de liste CVE).

## Preuve

| Observé (commande lancée pendant la séance) | Ce que ça démontre |
|---|---|
| `collect_one.py <source>` → `errors_by_source={'<source>': None}` pour `cisa_kev`, `github_advisories_pip`, `github_releases_anthropics_claude_code`, `github_most_starred`, `arxiv`, `tldr_ai` | la première vraie collecte fonctionne ; l'annexe cite de vrais bruts |
| catalogue CISA : 1 734 lignes, triées par `dateAdded` décroissant, 0 rupture, 0 CVE en double | une modification ne crée pas de ligne : catalogue d'état |
| pages TLDR : 80 articles hors sponsor ; liens vers `arxiv.org` (2), `github.com` (2) | un résumé TLDR peut viser un papier ou un dépôt : d'où la clé (édition, date, rang) et le lien facultatif vers PAPER |
| record `CVE-2026-69086` : conteneurs `cna` et `adp` (`CISA-ADP`, SSVC `Exploitation: none`) | ce qu'apporterait la liste CVE si le périmètre s'élargissait |
| `temp/mld-k-b.drawio` : XML valide, trois pages (D, B, C) | le MLD existe ; rendu non vérifié dans draw.io |

## Ce que tu dois pouvoir défendre

1. **Pourquoi des sous-types plutôt qu'une table ITEM avec toutes les colonnes ?** Une table unique
   aurait des colonnes vides selon le type (le CVE pour un papier, les auteurs pour une faille) et
   mélangerait des dépendances différentes. Les sous-types gardent chaque fait dans sa table ;
   ITEM reste le point d'entrée commun pour la recherche, P1 et les notes (règle 4 du MLD de
   `docs/stockage.md:134`).
2. **Les auteurs en JSON, ce n'est pas contraire à la 1re forme normale ?** Une valeur est
   atomique si la base ne la décompose pas. Ici, aucune requête ne découpe la liste : c'est une
   mention d'affichage. Le jour où un parcours cherche par auteur, on crée `author` et
   `paper_author` en relisant le brut (`:208-212`).
3. **Que se passe-t-il quand CISA modifie une ligne ?** La ligne est reconnue par son CVE, son
   contenu est remplacé, `revised_at` prend la date de la collecte : P1 la montre comme nouvelle
   (`:163-165`).
4. **Pourquoi CISA fait-il foi sur les CVE alors que l'autorité est le programme CVE ?** Le
   périmètre de K-B est celui des failles exploitées de façon avérée ; pour ce périmètre, la liste
   officielle est KEV. Élargir le périmètre ajouterait la liste CVE comme source, sans changer la
   structure.
5. **Comment la base empêche-t-elle un même CVE deux fois ?** `cve_id` est unique dans le
   sous-type CVE : la base refuse le doublon, quel que soit le code d'import (#105).

## Zones non vérifiées

- L'atomicité « selon l'usage » est attribuée à C. J. Date de mémoire, sans source lue.
- La date de Merise (fin des années 1970) est de mémoire ; celle de Merise 2 (1992) vient d'une
  source secondaire.
- La clé étrangère composée (`item_id`, `kind`) suppose `UNIQUE (item_id, kind)` sur ITEM, car
  SQLite exige que la cible d'une clé étrangère soit unique ; non écrit ni testé.
- `CHECK (json_valid(authors))` dans une table `STRICT` : non essayé dans la version de SQLite du
  projet.
- Les critères d'entrée au catalogue KEV viennent de sources secondaires, pas de la page de CISA.
- Les valeurs possibles de SSVC `Exploitation`, et si un CVE de KEV y est marqué autrement : un
  seul record vu.
- Qu'une ligne puisse disparaître du catalogue KEV n'a pas été vérifié : `withdrawn_at` couvre le
  cas sans savoir s'il arrive.
- Le fichier draw.io n'a pas été ouvert dans draw.io.

## Ce qui reste

- Les points 4 (lien avec les notes) et 5 (modèle complet : index plein texte, GitHub, Zotero,
  clips) de la mission ; GitHub a été mis de côté volontairement.
- Les ADR des décisions (`/adr-ls`), le second passage de vérification par un sous-agent, la PR.
- Les issues que ces décisions modifient ou font naître (#105 en premier, #84, #57, registre des
  traitements, `stockage.md`, lecteur CISA en catalogue d'état), à lister dans le document puis à
  découper dans une session à part.
