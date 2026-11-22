# Grouper les milliers de la même façon sur tout le site

- **Date** : 2026-11-22
- **Branche** : `fix/web-thousands-grouping`
- **Issue** : #614
- **Fichiers principaux** : `src/k_b/web/french_dates.py`, `src/k_b/web/feed.py`, `src/k_b/web/trends.py`,
  `src/k_b/web/item_detail.py`, `src/k_b/web/templates/feed.html`
- **Série** : la fonction est née avec le tableau des tendances,
  [2026-11-14-afficher-les-tendances-sur-le-site.md](2026-11-14-afficher-les-tendances-sur-le-site.md).

La note couvre les deux commits de la branche, `b7c239a8` (le code et ses tests) et `376c8150` (le tri des
revues). Les autres commits et fichiers listés par l'outil viennent de `main`, déjà fusionnés : ils ne font pas
partie de cette PR.

## Le pourquoi

Le site écrivait les nombres de deux façons. Le tableau des tendances groupait les milliers par une espace fine
insécable : « 1 087 étoiles ». Le fil ne les groupait pas : « 12345 items depuis le … ». La revue de code de #596 l'a
relevé, et #614 demande une seule fonction pour tout le site, employée partout où un nombre peut atteindre 1 000.

Le rôle de ce code est la présentation : il ne change aucune donnée, aucune requête à l'API de données, aucun
lien. Il ne change que le texte que la personne lit.

## Le comment

### Une seule fonction, à côté de `write_day`

```python
# src/k_b/web/french_dates.py:9
THOUSANDS_SEPARATOR = chr(0x202F)
```

```python
# src/k_b/web/french_dates.py:38-39
def write_count(count: int) -> str:
    return f"{count:,}".replace(",", THOUSANDS_SEPARATOR)
```

- `f"{count:,}"` est l'option « , » du mini-langage de format de Python : elle insère une virgule toutes les trois
  chiffres, **sans lire la locale de la machine**. C'est voulu : la machine qui sert le site (un conteneur Linux sur
  Azure) n'est pas forcément en français.
- `.replace(",", …)` met à la place l'espace fine insécable U+202F, celle du français.
- `chr(0x202F)` et pas un `" "` dans la source : un outil d'édition a déjà transformé un tel échappement en
  caractère invisible dans ce dépôt (`MEMORY.md`, « Échappements `\u` et `\x` »).

La fonction a quitté `trends.py`, où elle était née, pour `french_dates.py`, le module qui écrit déjà les dates du
site en français (`write_day`, `write_moment`). Son docstring de module dit maintenant « The dates and the numbers
of the site ».

### Le fil : le total, la longueur d'une recherche refusée, les pages

```python
# src/k_b/web/feed.py:400
    items = "1 item" if total == 1 else f"{write_count(total)} items"
```

C'est la ligne des résultats (Opquast 13) : « 12 345 items depuis le 10 novembre 2026 … ».

```python
# src/k_b/web/feed.py:285-286
            f"La recherche fait {write_count(len(q))} caractères:"
            f" {DATA_API_MAX_SEARCH_LENGTH} au plus.",
```

Le paramètre `q` n'est pas borné avant ce message : une adresse écrite à la main peut envoyer 1 500 caractères, et le
message dirait sinon « 1500 ». Le message ne cite que la **longueur** de la recherche, jamais son texte.

### Les numéros de page, par une valeur déjà écrite

```python
# src/k_b/web/feed.py:370-371
    page_text = write_count(page)
    pages_text = write_count(pages)
```

`FeedListing` porte maintenant `page_text` et `pages_text` (`feed.py:192` et `:194`), que le gabarit affiche
(`feed.html:73` et `:94`) ; `pages` reste un entier, car le gabarit s'en sert pour un test (`listing.pages > 1`).
Les numéros de page n'atteignent jamais 1 000 : `PAGE_NUMBER` accepte 3 chiffres au plus et `MAX_PAGE` vaut 501
(`feed.py:80` et `:82`). Ils passent quand même par la fonction, parce que l'issue le demande : un nombre du site
s'écrit d'une seule façon, et rien ne dépend d'une borne qui pourrait changer.

### Le rang d'un article de newsletter

```python
# src/k_b/web/item_detail.py:217
                LinePart(f"n° {write_count(detail.rank)}"),
```

Le titre de la page du détail l'écrit de même (`item_detail.py:179`). Le rang n'a pas de borne haute : le client de
l'API de données n'impose que `ge=1`. Ce point a été ajouté au tri des revues : le relecteur accessibilité l'a
relevé (A2), et le Second a tranché qu'il entre dans le périmètre de #614.

## Choix faits et options écartées

- **Le module : `french_dates.py`**, retenu par le Second le 19/11 (plan, « Décisions demandées », 4), comme le
  proposait l'issue. Écarté : un module `french_numbers.py`, qui aurait porté une fonction d'une ligne. Le nom
  `french_dates` ne dit plus tout ce que le module contient : la revue de code l'a relevé (CR4) et le choix a été
  gardé.
- **Les numéros de page par une valeur déjà écrite** dans `FeedListing`. Écarté : un filtre Jinja2 enregistré dans
  `rendering.py`, qui aurait changé la configuration des gabarits pour trois nombres.
- **`write_results_line` garde sa signature** (des entiers) et écrit elle-même la page et le nombre de pages. Écarté :
  lui passer `page_text` et `pages_text`, ce qui aurait changé ses tests existants pour deux appels de moins
  (revue, CR2).
- **Les constantes 200 (`DATA_API_MAX_SEARCH_LENGTH`) et 20 (`FEED_PAGE_SIZE`) restent écrites telles quelles** : ce
  sont des réglages sous 1 000, hors des endroits que le plan nommait (revue, CR3, laissé par le Second).
- **Les années ne sont jamais groupées** : « 2026 » et pas « 2 026 ». `write_day` écrit l'année par `day.year`, qui ne
  passe pas par `write_count`.
- **L'espace fine insécable U+202F**, déjà choisie par #596 pour les tendances : elle ne se coupe jamais en fin de
  ligne. Le relecteur accessibilité l'a vérifié dans le fichier Unicode `LineBreak.txt` : U+202F y est de classe
  `GL`, comme une colle.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Rouge avant le code : 5 échecs dans `test_feed.py` et `test_feed_page.py`, `ImportError` de `write_count` dans `test_trends.py` | Les tests vérifiaient bien le changement : ils échouaient sur l'ancien code |
| Rouge avant le code : `'… n° 1234'.endswith(', n° 1 234')` faux | Le test du rang échouait avant sa correction |
| `test_a_count_is_grouped_by_thousands_with_a_narrow_no_break_space` (`tests/web/test_trends.py:126`) : 0, 999, 1 000, 1 500, 1 234 567 | La fonction déplacée groupe dès 1 000, pas avant |
| `test_the_line_of_the_results_groups_the_thousands_of_the_total` (`tests/web/test_feed.py:317`) : 999, 1 000, 12 345 | Le total de la ligne des résultats est groupé |
| `test_the_length_of_a_search_refused_groups_its_thousands` (`tests/web/test_feed.py:112`) : 999, 1 000, 1 500 | La longueur d'une recherche refusée est groupée |
| `test_the_feed_groups_the_thousands_of_its_total` (`tests/web/test_feed_page.py:333`) | La page rendue contient « 12 345 items depuis le », le caractère brut et pas une entité |
| `test_the_rank_of_a_newsletter_article_groups_its_thousands` (`tests/web/test_item_detail.py:234`) | Le rang est groupé dans le titre et sous la sorte |
| Les tests existants « Page 2 sur 3 » et « Page 1 sur 501 » (`test_feed_page.py`) | Le gabarit lit bien `page_text` et `pages_text` ; un nom de champ absent ferait échouer la page (`StrictUndefined`, `rendering.py:25`), vérifié par un essai |
| `ruff check --no-cache`, `ruff format --check`, `mypy --strict` (198 fichiers), `uv run pytest` (5673 passés), aucun caractère `Cc` ou `Cf` | Les contrôles du dépôt passent |

## Ce que tu dois pouvoir défendre

1. **Pourquoi ne pas utiliser `locale` ou `format(…, "n")` ?** Ils dépendent de la locale de la machine. Le conteneur
   sur Azure n'est pas forcément en `fr_FR`, et changer la locale d'un processus touche tout le processus. Ici, le site
   écrit lui-même ses nombres, comme ses dates (`french_dates.py:38-39`).
2. **Pourquoi grouper les numéros de page, s'ils ne dépassent jamais 501 ?** Parce que l'issue demande une seule
   façon d'écrire les nombres. Si `MAX_PAGE` change un jour, rien d'autre n'est à modifier (`feed.py:370-371`).
3. **Un attaquant peut-il injecter du texte par ces nombres ?** Non. Chaque valeur vient d'un entier : `len(q)`, le
   numéro de page lu par une expression régulière, le total et le rang validés par Pydantic en mode strict.
   `write_count` ne rend que des chiffres ASCII et U+202F. Le gabarit échappe tout (`autoescape=True`). La revue de
   sécurité n'a rien trouvé.
4. **Pourquoi U+202F et pas une espace ordinaire ou U+00A0 ?** Une espace ordinaire peut couper « 12 » et « 345 » sur
   deux lignes, ce qui gêne la lecture à 320 px ou à 200 % (WCAG 1.4.10). U+202F, l'espace fine insécable, est
   insécable et c'est le séparateur de milliers du français ; #596 l'avait déjà choisie pour les tendances.
5. **Quelles règles de qualité sont en jeu ?** Aucune règle Opquast 2025 ne parle des milliers (relu à la source le
   2026-11-22). Celles que ce code touche : 13 (la ligne des résultats donne le nombre de résultats, de pages et de
   résultats par page), 14 (aucun caractère détourné pour une mise en forme : U+202F est un séparateur, pas un
   artifice), 80 et 82 (la raison d'un rejet est dite, dans la langue du formulaire).

## Zones non vérifiées

- **La lecture de U+202F par les lecteurs d'écran n'a pas été essayée** (constat A1 du relecteur accessibilité).
  D'après le code de NVDA 2025 (normalisation NFKC) et d'eSpeak NG, « 12 345 » serait lu comme un seul nombre. Pour
  OneCore (la voix par défaut de NVDA sous Windows), JAWS et VoiceOver, le comportement est inconnu. Un essai à la
  main est proposé à Sabine.
- **Le séparateur de milliers du français dans CLDR** (U+202F) : c'est le relecteur accessibilité qui l'a lu dans
  `common/main/fr.xml`, pas moi.
- **Les maquettes** : le relecteur n'a pas pu lire le canevas des maquettes. Ce que les maquettes écrivent pour un
  nombre de 1 000 ou plus n'a pas été comparé.

## Ce qui reste

- L'essai à la main avec un lecteur d'écran (A1), sans urgence : il ira dans la PR s'il est fait.
- Hors du périmètre de #614, par l'issue elle-même : les nombres que `kb` écrit dans le coffre et les journaux.
- La note du 2026-11-14 renvoie encore à `trends.py:115-116` pour `write_count` : c'est une note datée, qui décrit
  l'état de son jour, et elle n'est pas réécrite (revue, CR6).
