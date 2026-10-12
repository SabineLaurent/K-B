# Lire les articles des pages TLDR brutes

- **Date** : 2026-10-12
- **Branche** : `feat/tldr-articles`
- **Issue** : #57
- **Fichiers principaux** : `src/k_b/sources/tldr.py`, `src/k_b/items.py`,
  `src/k_b/import_items.py`, `src/k_b/database/schema.sql`, `tests/sources/test_tldr.py`,
  `tests/test_import_items.py`, `docs/specs-collecte.md`
- **Dans la même série** : [lire un dossier de pages brutes](2026-10-06-lire-un-dossier-de-pages-brutes.md)
  (#101), qui a préparé la lecture page par page ; [laisser la base dédoublonner les
  items](2026-10-12-laisser-la-base-dedoublonner-les-items.md) (#105), dont cette PR applique la
  règle du flux de nouveautés ; [importer seulement les bruts
  nouveaux](2026-10-12-importer-seulement-les-bruts-nouveaux.md) (#106), dont elle réutilise le
  registre et le journal.

## 1. Le pourquoi

Depuis #13, `kb collect` range les pages d'édition de tldr.tech telles quelles, une par jour et
par édition suivie (`ai`, `infosec`, `dev`). Rien ne les lisait : à l'import, leur dossier était
sauté « faute de lecteur ». Une page d'édition est pourtant la source la plus lisible de la
veille : une quinzaine d'articles choisis, chacun avec un titre, un lien et un résumé de
quelques lignes.

Cette PR écrit le lecteur qui manquait : un item par article, rangé dans une table à lui,
`newsletter_article`. Elle applique à TLDR la règle déjà posée pour les releases et les alertes
GitHub : un article déjà en base garde la version que sa première collecte a apportée.

## 2. Le comment

### 2.1 Une page devient une liste d'entrées

Le lecteur reçoit les octets de la page et rend une entrée par balise `<article>` :

```python
# src/k_b/sources/tldr.py:147
soup = BeautifulSoup(page.decode("utf-8"), "html.parser")
```

```python
# src/k_b/sources/tldr.py:156-160
articles = [
    article
    for rank, entry in enumerate(entries, start=1)
    if not is_left_out(article := read_article(entry, edition_date, rank))
]
```

- `page.decode("utf-8")` : K-B décode lui-même. Si on lui donne des octets, BeautifulSoup
  devine l'encodage ; K-B ne devine pas (consigne « K-B est déterministe »). Une page qui n'est
  pas de l'UTF-8 lève `UnicodeDecodeError`, qui est une `ValueError` : la page est rejetée.
- `"html.parser"` : l'analyseur HTML de la bibliothèque standard de Python. BeautifulSoup n'est
  que la couche qui permet d'écrire `entry.select_one("a.font-bold")`.
- `enumerate(entries, start=1)` donne le **rang** : la position de l'entrée parmi tous les
  `<article>` de la page. Il est calculé avant le filtre : une entrée écartée « consomme » son
  rang.

Dans chaque `<article>`, le titre est le texte de `a.font-bold`, le lien son `href`, le résumé
le texte de `div.newsletter-html` (`read_article`, `tldr.py:190`). `read_text` (`tldr.py:203`)
rend le texte de l'élément, ses morceaux (paragraphes, liens) séparés par une espace et chaque
suite de blancs réduite à une espace.

### 2.2 Ce qui est écarté, ce qui est refusé

Trois issues possibles pour une entrée, qu'il ne faut pas confondre :

| Cas | Ce qui se passe | Trace |
|---|---|---|
| titre avec « (Sponsor) », ou lien d'une offre d'emploi de TLDR | écartée par le lecteur | aucune : ce n'est pas une erreur |
| entrée sans titre, sans lien `https`, sans résumé, trop longue | refusée par l'`Item` | un rejet au journal d'import, les autres entrées sont lues |
| page qui n'est pas une édition lisible | refusée entière par le lecteur | un rejet au journal d'import, la page n'est pas inscrite au registre |

```python
# src/k_b/sources/tldr.py:209-212
def is_left_out(article: TldrArticle) -> bool:
    return SPONSOR_MARK in article.title or article.link.startswith(
        TLDR_JOB_OFFER_URL_PREFIX
    )
```

Le lecteur ne valide pas l'entrée : il la rend « telle que lue », même vide. C'est l'`Item`
Pydantic, construit par `convert_article`, qui la refuse. Pourquoi ce partage : dans le contrat
de lecture (`raw_items.py`), une exception du lecteur rejette **la page entière**, alors qu'une
`ValidationError` de la conversion ne rejette que **l'entrée**. Valider dans le lecteur aurait
fait tomber quinze articles pour un lien manquant.

La page entière n'est refusée que dans cinq états : pas de l'UTF-8, pas de `h1`, premier `h1`
qui n'est pas « TLDR <titre> <date> », un `<article>` dans un autre (2.7), et celui-ci :

```python
# src/k_b/sources/tldr.py:161-167
if not any(
    article.title and article.link and article.summary for article in articles
):
    raise ValueError(
        "no article with a title, a link and a summary among "
        f"{len(entries)} article elements"
    )
```

Si tldr.tech renomme la classe `font-bold`, toutes les entrées perdent leur titre. Sans ce
contrôle, chacune serait refusée une à une, la page serait inscrite au registre comme lue, et
plus jamais rouverte. Avec lui, la page reste « à relire » : elle sera importée dès que le
lecteur sera corrigé, sans reconstruire la base.

### 2.3 De l'entrée à l'item : édition, date, rang

```python
# src/k_b/sources/tldr.py:220
edition = find_stream(raw_file_path).removeprefix(FOLDER_PREFIX).removeprefix("_")
```

- **L'édition** vient du nom du dossier brut : `tldr_ai` → `ai`. Un dossier `tldr` seul donne
  une édition vide, que l'item refuse.
- **La date** vient du premier `h1` de la page (`TLDR AI 2026-10-08`, `read_edition_date`,
  `tldr.py:171`), écrite à minuit UTC dans `published_at`, comme la date d'ajout de CISA.
- **Le rang** vient de la page (2.1).
- L'identifiant de l'item, `ai/2026-10-08#3`, réunit les trois. C'est lui que le journal
  d'import cite.

Le lien subit une seule retouche ici :

```python
# src/k_b/sources/tldr.py:228
url=article.link.replace("&amp;", "&"),
```

Certains liens sont échappés deux fois dans la page (`&amp;amp;utm_source=…`). Une fois le HTML
lu, il reste `&amp;utm_source=…` : le paramètre s'appellerait `amp;utm_source` et ne serait pas
reconnu comme un `utm_*`. Le retrait des `utm_*` lui-même n'est pas dans ce fichier : c'est
`normalize_item` (`merge.py`) qui le fait pour tous les items, à l'étape suivante.

### 2.4 L'item refuse avant la base

Deux types nouveaux dans `items.py`, écrits pour que l'item refuse tout ce que la base ou la
normalisation refuserait plus tard :

```python
# src/k_b/items.py:68-70
NewsletterEdition = Annotated[
    str, StringConstraints(pattern=f"^{EDITION_SLUG.pattern}$")
]
```

Le motif est **ancré** (`^…$`) et donné **en texte**. Pydantic cherche un motif non ancré
n'importe où dans la valeur : `AI ai` passerait. Et un motif compilé par Python accepte un
retour à la ligne final : `ai\n` passerait. La base, elle, refuse les deux
(`CHECK (edition <> '' AND edition NOT GLOB '*[^a-z]*')`, `schema.sql:206`). Comme la base n'a
pas de `SAVEPOINT` par item, une valeur que l'item laisse passer et que la base refuse arrête
tout l'import.

```python
# src/k_b/items.py:45-52
    try:
        host = urlsplit(url).hostname
    except ValueError:
        # The error of urlsplit quotes the host as written: only the state is kept.
        raise ValueError(f"url cannot be split: {len(url)} characters") from None
    if not host:
        raise ValueError(f"url without a host: {len(url)} characters")
    return url
```

Même idée pour l'URL (`check_url_can_be_normalized`, `items.py:40`). Deux liens passaient le
motif `^https://\S+$` puis arrêtaient tout l'import, hors de tout rattrapage :

- `https://[x` : `urlsplit` lève dans `merge.py` (constat de la relecture du plan) ;
- `https://?utm_source=tldrai` : une fois ses `utm_*` retirés il reste `https://`, que la
  seconde validation de `normalize_item` refuse (constat des deux revues de la PR).

Le message ne recopie pas le texte d'erreur de `urlsplit`, qui cite l'hôte entier tel
qu'écrit : il dit l'état et la longueur (règle 3 des conventions). `HttpsUrl` sert à toutes
les sources : le contrôle vaut pour toutes.

Le rang, lui, est borné des deux côtés (`items.py:185`, `Field(ge=1, le=MAX_INT64)`) : SQLite
ne tient pas un entier au-delà de 64 bits.

### 2.5 La table et sa clé

```sql
-- src/k_b/database/schema.sql:222-223
    UNIQUE (edition, edition_date, rank),
    FOREIGN KEY (item_id, kind) REFERENCES item (id, kind)
```

- La **clé naturelle** est (édition, date, rang). L'URL n'en fait pas partie et n'est pas
  unique : deux éditions peuvent résumer le même article, et on veut garder les deux résumés.
- La **clé étrangère composée** (`item_id`, `kind`) est celle de tous les sous-types : elle
  interdit qu'un article pointe vers un item d'une autre sorte.
- `publication_id` (le papier cité) existe et reste vide : décision de Sabine.

### 2.6 L'écriture : premier vu, premier gardé

```sql
-- src/k_b/import_items.py:129-136
INSERT INTO item (kind, raw_data_id)
SELECT 'newsletter_article', :raw_data_id WHERE NOT EXISTS (
    SELECT 1 FROM newsletter_article
    WHERE edition = :edition AND edition_date = :edition_date AND rank = :rank
)
RETURNING id
```

L'item n'est créé que si aucun article n'a déjà cette clé. Si la requête ne rend rien, l'article
est connu : `write_newsletter_article` (`import_items.py:527`) rend un écart `already_seen`,
daté de la collecte de la version gardée, que le journal d'import écrit. Rien n'est modifié en
base. C'est la règle du flux de nouveautés de #105, écrite une troisième fois (releases,
alertes, articles).

Ce cas n'est pas rare : la collecte retélécharge chaque jour la page du jour de la dernière
collecte, parce que son édition a pu paraître après. Une même page d'édition arrive donc
normalement dans deux collectes.

### 2.7 Une limite de ressources : les articles imbriqués

```python
# src/k_b/sources/tldr.py:153-154
if soup.select_one("article article") is not None:
    raise ValueError("article element inside an article element")
```

Constat de la revue de sécurité. Chaque `<article>` est une entrée, et chaque entrée est
fouillée en entier pour y trouver son titre et son résumé. Une page faite d'`<article>` les uns
dans les autres est donc fouillée autant de fois qu'elle a d'articles : 18 s pour 50 Ko, 74 s
pour 100 Ko (mesures du relecteur), et la page, refusée à la fin, serait relue à chaque
import. Avec ce contrôle, la même page de 1 Mo est refusée en 0,35 s (mesuré). Aucune des 315
entrées collectées n'est imbriquée.

## 3. Choix faits et options écartées

Les six décisions de Sabine sont au journal ADR du 2026-10-12, « Collecte : articles TLDR »,
avec leurs options écartées : la clé et l'absence d'empreinte, le rang qui compte tout,
`publication_id` vide, BeautifulSoup, les offres d'emploi, `HttpsUrl`. Les choix ci-dessous sont
ceux de la session, validés avec le plan.

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Qui refuse une entrée invalide | l'`Item`, par `convert_article` : seul chemin de rejet du contrat, et aucun `logger.warning` dans la source (règle 1 des conventions) | le lecteur, comme `feat/tldr` : une exception y rejette toute la page |
| D'où vient la date | du `h1` : c'est ce que la page dit d'elle-même | du nom du fichier : c'est ce que K-B a demandé, pas ce qu'il a reçu |
| Titre d'édition du `h1` | non comparé au dossier | le comparer, comme `feat/tldr` : il faudrait une table « ai → AI, infosec → Information Security », alors que la collecte demande déjà l'URL de l'édition sans accepter de redirection |
| Résumé | texte simple, morceaux séparés par une espace, comme `feat/tldr` | le Markdown de brief09 (son module de nettoyage n'est pas repris) ; les morceaux collés, d'abord retenu puis corrigé après la revue de code : deux paragraphes donnaient « …ends.Next… ». Sur les 272 articles gardés, les deux lectures donnent le même texte |
| Retrait des `utm_*` | par `merge.py`, pour tout item | une fonction propre à TLDR, comme `feat/tldr` et brief09 : la même règle écrite deux fois |
| Encodage | UTF-8 décodé par K-B | laisser BeautifulSoup deviner |
| « (Sponsor) » | cherché dans tout le titre, comme brief09 et `feat/tldr` | seulement en fin de titre : une marque suivie d'un autre texte laisserait entrer une publicité |
| Les trois écrivains du flux de nouveautés | laissés côte à côte | les factoriser ici : le déplacement du SQL (#135) est le moment |
| SQL de l'écrivain | dans `import_items.py`, avec les autres | dans `database/` (règle 5) : écart temporaire, imposé par la mission, que #135 rattrape |
| `KindWithoutTableError` | gardée, comme garde qui échoue fermé | la retirer : une sorte ajoutée sans écrivain finirait en `KeyError` |
| Borne des entiers | `MAX_INT64` défini une fois dans `items.py`, `gh_archive.py` l'importe (règle 4) | une seconde constante à côté de celle de `gh_archive.py` |
| `soupsieve` | verrouillé en 2.10 dans `uv.lock` (décision de Sabine) | la 3.0.3 choisie par `uv`, publiée le jour même |
| Fixtures | deux extraits de pages collectées, résumés coupés à leur première phrase | la fixture de `feat/tldr`, dont les résumés étaient remplacés et un paramètre ajouté à la main (consigne : une fixture part d'un exemple collecté) |

Repris de l'existant : de brief09, un item par `<article>`, les sélecteurs `a.font-bold` et
`div.newsletter-html`, le filtre « (Sponsor) », BeautifulSoup ; de `feat/tldr`, la forme de
`read_articles`, le contrôle du `h1`, le double échappement défait, les cas de ses tests.

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_one_article_per_entry_without_the_sponsored_one_that_its_rank_counts` | sur un extrait de page collectée (5 entrées), 3 articles sortent avec les rangs 2, 3, 4 : le sponsor (1) et l'offre d'emploi (5) sont écartés et comptés |
| `test_a_job_offer_of_tldr_is_left_out_by_its_link_not_by_its_title` | l'offre est reconnue par son lien : donné à un vrai article, ce lien le fait écarter |
| `test_a_link_escaped_twice_in_the_page_loses_its_tracking_parameters` | le lien collecté `…?gift=…&amp;utm_source=tldrdev` entre en base sans `utm_source`, avec `gift` |
| `test_a_page_that_is_not_a_readable_edition_is_refused_whole` (9 cas) | les états de page illisible, chacun avec son message, dont les articles imbriqués |
| `test_the_paragraphs_of_a_summary_are_read_apart` | deux paragraphes d'un résumé restent séparés par une espace |
| `test_the_title_found_is_quoted_escaped_and_cut_in_the_refusal` | un `h1` long, avec un caractère de contrôle, est cité échappé et coupé à 100 caractères |
| `test_an_entry_refused_is_rejected_and_the_others_of_its_page_are_read` | une entrée sans résumé donne un rejet, les deux autres articles sont lus |
| `test_an_invalid_newsletter_article_is_refused` et `test_an_edition_that_is_not_a_slug_is_refused` | les mêmes éditions (`""`, `AI`, `a1`, `ai\n`…) sont refusées par l'item et par la base |
| `test_a_link_that_cannot_be_split_is_refused`, `test_a_link_without_a_host_is_refused` | `https://[x` et `https://?utm_source=tldrai` sont refusés par l'item, au lieu d'arrêter l'import |
| `test_a_link_that_cannot_be_split_is_not_copied_whole_into_the_refusal` | un hôte de 3 000 lettres avec une séquence d'échappement n'est pas recopié dans le motif du rejet |
| `test_an_article_seen_again_keeps_its_first_collection_and_is_logged_already_seen` | **le test du critère** : la même page dans une collecte suivante, titre et résumé modifiés ; la base est inchangée, l'écart est au journal avec `already_seen` et la date de la première collecte |
| `test_the_same_article_summarized_by_two_editions_is_kept_twice` | la même URL sous deux éditions fait deux lignes |
| `test_a_value_each_check_forbids_is_refused` (9 cas nouveaux) | chaque `CHECK` de la table refuse sa valeur |
| `kb create-db` puis `kb import` deux fois sur une copie des 18 pages collectées | 272 articles (127 `ai`, 70 `dev`, 75 `infosec`), 0 rejet, aucun `utm_*`, aucune offre, aucun sponsor ; le second import ne lit rien |
| filtre « (Sponsor) » retiré à la main | 11 tests échouent |
| filtre des offres d'emploi retiré à la main | 7 tests échouent |
| `WHERE NOT EXISTS` retiré à la main | le test du critère échoue (`IntegrityError` sur la clé unique) |
| `uv run pytest`, `ruff check`, `ruff format --check`, `mypy --strict` | 718 tests passent, aucun constat |
| `pip-audit` sur `uv.lock`, avec la commande de la CI | « No known vulnerabilities found » |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi la clé n'est-elle pas l'URL ?** Parce que deux éditions résument le même
   article, chacune avec son résumé, et que TLDR fait foi pour le résumé, pas pour l'article.
   Sur les 18 pages collectées, 10 URL reviennent sous deux clés, toujours avec deux résumés
   différents. (`schema.sql:222`, ADR du 2026-10-07 et du 2026-10-12.)
2. **Que se passe-t-il si tldr.tech change sa page ?** Si une classe est renommée, plus aucun
   article n'est complet : la page est refusée entière, n'est pas inscrite, et sera relue
   (`tldr.py:161`). Si la page d'un jour est retouchée entre deux collectes, la première
   version vue reste, et un article dont le rang a bougé peut être écarté à tort ou entrer deux
   fois : c'est la limite écrite de la clé (`docs/specs-collecte.md`, étape 4).
3. **Où est la sécurité, face à une page écrite par un tiers ?** La page est une donnée, jamais
   une instruction. Chaque valeur passe par un type fermé avant la base (`items.py` : lien
   `https` seulement, donc ni `javascript:` ni `http:` ; longueurs bornées ; édition en lettres
   minuscules). Le SQL est à paramètres liés (`import_items.py:129-180`). Un `h1` cité dans un
   message est échappé et coupé (`tldr.py:176-179`). Une page d'articles imbriqués est refusée
   avant d'être fouillée (`tldr.py:153`). Le lecteur ne fait aucun appel réseau : il ne suit
   pas les liens. Reste un écart connu, pour toutes les sources : un caractère de contrôle
   passe l'item et est rangé tel quel (section 7).
4. **Pourquoi BeautifulSoup alors que le projet limite ses dépendances ?** Décision de Sabine :
   réemployer ce qui marche dans brief09 et `feat/tldr`. La dépendance est contenue :
   l'analyseur reste celui de la bibliothèque standard, `lxml` n'est pas ajouté, `soupsieve`
   est verrouillé sur une version de 18 jours et non sur celle du jour, et la CI audite
   `uv.lock` avec `pip-audit`.
5. **Pourquoi le rang compte-t-il les sponsors ?** Pour qu'il se vérifie à l'œil sur la page
   brute, et qu'un changement de filtre ne renumérote rien : les offres d'emploi ont été
   écartées en cours de PR sans décaler un seul rang (`tldr.py:126-127`).

## 6. Zones non vérifiées

- **Le comportement de tldr.tech après publication** : aucune page n'est collectée deux fois
  dans le brut. On ne sait pas si une page d'édition est retouchée, ni à quelle fréquence.
- **La page d'accueil** : aucune n'est dans le brut (la collecte refuse cette redirection). Les
  pages refusées des tests sont l'extrait collecté, son `h1` remplacé.
- **`ParserRejectedMarkup`** : le cas où `html.parser` rejette une page n'a pas été provoqué
  avec une vraie page ; le test le simule.
- **Une page hostile de grande taille** : mesurée par la revue de sécurité pour trois formes
  (articles imbriqués, refusés depuis ; 55 000 articles côte à côte, 0,6 s ; 209 000 `<div>`
  imbriqués, 0,8 s et 161 Mo). D'autres formes n'ont pas été cherchées, ni un autre système que
  macOS, ni une autre version de Python que la 3.13.
- **`&amp;` → `&`** : un lien qui contiendrait légitimement le texte `&amp;` serait modifié.
  Aucun cas observé ; non cherché au-delà des 315 entrées.
- **Le code de `beautifulsoup4` 4.15.0 et de `soupsieve` 2.10** n'a pas été lu ; `pip-audit`
  et OSV ne leur connaissent aucune alerte.
- **Les revues** n'ont pas relu les corrections faites après elles (C1 à C7) : pas de second
  `/code-review`, par décision (issue de taille S).

## 7. Ce qui reste

- **Remplir `publication_id`** quand le lien est `https://arxiv.org/abs/<id>` : signalé, sans
  issue (journal ADR, « Décisions encore ouvertes »).
- **Les liens `links.tldrnewsletter.com`** (3 sur le brut) restent des redirections : trouver
  l'adresse de l'article demanderait un appel réseau.
- **Une offre d'emploi publiée ailleurs** que sur le site d'offres de TLDR entrerait comme
  article.
- **Un caractère de contrôle** (NUL, séquence d'échappement, inversion du sens du texte) passe
  l'item et est rangé dans le titre, le résumé ou l'URL, pour toutes les sources : le type
  « texte sans NUL » de la règle 4 n'existe pas encore. Sans issue.
- **Un `h1` sans nom d'édition** (« TLDR <date> ») serait refusé : à vérifier quand une édition
  est ajoutée.
- **Citer, échapper, couper une valeur** est écrit trois fois (`tldr.py`, `gh_archive.py`,
  `zotero.py`) : à factoriser avec le rangement. Sans issue.
- **Le SQL de l'écrivain** rejoindra `src/k_b/database/` avec les autres (#135).
- **Le MCD et le MLD** du 2026-10-12 n'ont pas la table `newsletter_article`.
- **La base locale est à reconstruire** après la fusion : supprimer la base, `kb create-db`,
  `kb import`.
