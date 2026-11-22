# Écrire le bouton « Retour au fil de veille » une seule fois

- **Date** : 2026-11-22
- **Branche** : `refactor/web-back-to-feed-button`, commit `b139aeba`, sur `origin/main` à `7232d421`
- **Issue** : #681
- **Série** : suite de [Tenir le site sans défilement horizontal à texte 200 %](2026-11-21-tenir-le-site-a-texte-200-pour-cent.md)
  (#599), dont la revue a relevé la copie, et d'[Aligner le fil sur ses maquettes](2026-11-11-aligner-le-fil-sur-ses-maquettes.md),
  qui a créé la macro `external_link`
- **Fichiers principaux** :
  - `src/k_b/web/templates/links.html` : la macro `back_to_feed_button` ;
  - `src/k_b/web/templates/404.html`, `500.html` et `error.html` : son appel ;
  - `tests/web/test_templates.py` : le test qui la tient.

## Le pourquoi

Les trois pages d'erreur du site (404, 500, et `error.html`, qui sert les autres codes, dont 405) ouvrent leurs
actions par le même bouton : « ← Retour au fil de veille ». Il était écrit trois fois, à l'identique. Depuis #599, son
balisage est fin : un `span` qui fait du libellé un seul élément du bouton, une flèche cachée aux lecteurs d'écran, une
espace insécable qui la tient à son mot. Changer ce bouton demandait donc trois éditions à la main, et en oublier une
cassait une page sans que les deux autres le montrent.

`.claude/rules/code.md` (« Duplication ») demande de factoriser à la troisième occurrence. Le rendu ne change pas :
c'est une refactorisation.

## Le comment

### 1. Une macro sans paramètre

`src/k_b/web/templates/links.html:12-14` :

```jinja
{%- macro back_to_feed_button() -%}
<a class="button" href="/"><span><span class="arrow-start" aria-hidden="true">←&nbsp;</span>Retour au fil de veille</span></a>
{%- endmacro -%}
```

Le corps de la macro est la ligne recopiée, mot pour mot. Les trois pages écrivaient la même adresse et le même
libellé : la macro n'a donc aucun paramètre. Les tirets de `{%-` et `-%}` retirent les retours à la ligne autour du
corps, si bien que l'appel rend exactement la ligne `<a …>`, sans blanc en plus. `external_link`, la macro des liens
vers un autre site, est écrite de la même façon, juste au-dessus.

Avec `autoescape=True` (`src/k_b/web/rendering.py:24`), une macro rend du balisage marqué comme sûr : `{{ … }}` ne
l'échappe pas une seconde fois. Il n'y faut donc ni `|safe` ni `Markup`, que `tests/web/test_templates.py` interdit
dans tout gabarit.

### 2. L'import avant `{% extends %}`

`src/k_b/web/templates/404.html:1-2` :

```jinja
{%- from "links.html" import back_to_feed_button -%}
{% extends "base.html" %}
```

Cette forme est celle de `item.html`, qui importe déjà `external_link`. Le `-%}` final compte : Jinja écrit dans la page
tout ce qui précède `{% extends %}`. Sans lui, le retour à la ligne de l'import arriverait avant `<!DOCTYPE html>`.
Essayé dans cette session sur un gabarit minimal : `'\n<!DOCTYPE html>…'` sans le tiret, `'<!DOCTYPE html>…'` avec.
Un test l'aurait vu : `test_a_page_is_an_html_document_in_french` (`tests/web/test_accessibility.py:189`) vérifie que
chaque page commence par `<!DOCTYPE html>`.

### 3. L'appel dans chaque page

`src/k_b/web/templates/404.html:12` :

```jinja
{{ back_to_feed_button() }}
```

Il remplace la ligne recopiée, à la même place, dans `404.html:12`, `500.html:25` et `error.html:11`. Le bouton
secondaire de chaque page (« Voir les tendances », « Réessayer ») reste écrit dans sa page : chacun n'existe qu'une fois.

### 4. Le test qui tient la factorisation

`tests/web/test_templates.py:68-83` lit le source des gabarits, pas les pages rendues :

```python
    assert writers == ["links.html"]
    assert callers == ["404.html", "500.html", "error.html"]
```

`writers` est la liste des gabarits qui contiennent le libellé « Retour au fil de veille » ; `callers`, ceux qui
contiennent `{{ back_to_feed_button() }}`. L'appel est cherché avec ses accolades : sans elles, `links.html` serait
compté parmi les appelants, par sa ligne `macro back_to_feed_button()`. Le test suit le modèle de
`test_a_link_to_another_site_is_written_by_its_macro_only`, juste au-dessus, qui tient `external_link` de la même façon.

Une nouvelle copie du libellé dans un gabarit fait échouer la première assertion. Une page d'erreur qui cesse d'appeler
la macro fait échouer la seconde.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Une macro dans `links.html` | Le plan de #681, accepté : la forme d'`external_link`, que ce fichier porte déjà | Un `{% include %}` d'un fichier d'une ligne : un fichier de plus pour une ligne, et une autre forme que celle des liens. Un bloc de `base.html` : le bouton n'est pas sur toutes les pages, et un bloc se redéfinit, il ne se partage pas |
| Aucun paramètre | Les trois appels écrivaient la même adresse et le même libellé (`code.md`, « Simplicité » : pas de paramètre pour plus tard) | `href` et `label` en paramètres : aucun appel n'en donnerait d'autres |
| Le test lit le source des gabarits | La duplication est dans le source : le rendu était déjà identique, et `test_the_arrow_of_a_button_stays_on_the_line_of_its_word` le vérifiait | Un test sur les pages rendues : il passait aussi avant la factorisation, il ne pouvait pas être rouge |
| `web/errors.py:30` hors de la macro | La page de secours est du HTML brut, écrite sans gabarit par conception : c'est elle qui s'affiche quand le gabarit de la page 500 échoue. Décidé par l'orchestrateur en second le 22/11 | La faire passer par la macro : elle dépendrait alors des gabarits qu'elle doit remplacer |
| Le lien « ← Retour au fil » du détail (`item.html:6`) hors de la macro | Hors du périmètre de l'issue : c'est un lien `.back-link` avec un autre libellé, pas un bouton | L'écrire par la même macro avec des paramètres : deux formes différentes dans une même macro |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_button_back_to_the_feed_is_written_by_its_macro_only`, rouge avant la macro : `['404.html', … 'error.html'] == ['links.html']` | Le test voyait les trois copies : il échouait pour la bonne raison |
| Le même test, vert après | Le libellé n'est plus écrit que dans `links.html`, et les trois pages appellent la macro |
| Les 24 pages rendues par `fetch_every_page` (`tests/web/test_accessibility.py:150`), écrites avant et après, puis `diff -r` : 0 différence | Le rendu de chaque page est inchangé, octet pour octet, et pas seulement celui des trois pages d'erreur. L'heure et l'identifiant de la demande de la page 500 sont masqués des deux côtés. Deux rendus avant le changement ne différaient pas : la comparaison est stable |
| `uv run pytest --cov --cov-report=term-missing:skip-covered`, la commande du job `tests` : 5 709 réussis, 365 écartés (`e2e`, `postgresql`), couverture 98,55 % pour un seuil de 96 % | Les tests existants des pages, dont celui des flèches et celui de la page 404, passent sans changement |
| `uv run ruff check --no-cache`, `uv run ruff format --check`, `uv run mypy --strict` | Contrôles du dépôt verts |
| Les jobs `audit`, `tests-postgresql`, `tests-data` et `digests-reference` de `ci.yml`, rejoués sur le Mac : aucune vulnérabilité connue (pip-audit 2.10.1, 109 paquets) ; 350 tests sur `postgres:18.6`, l'image de la CI par son digest, sous Docker ; 1 365 tests ; les trois seuils tenus | GitHub Actions est sans budget jusqu'au déploiement, et la PR est fusionnée sans CI : ces jobs n'ont pas d'autre lancement |
| Recherche des caractères Cc et Cf, et des espaces avant « : » ou « ; » dans les lignes ajoutées | Aucun |
| `/code-review` (niveau high) sur `origin/main...HEAD` : aucun bug ; le relecteur a rendu les trois pages d'erreur avec les gabarits de `origin/main` et de `HEAD`, sans différence | Une seconde comparaison du rendu, faite à part, confirme la première. De ses deux remarques mineures, l'une est corrigée (le commentaire de la macro nommait « chaque page d'erreur », alors que la page 403 n'a pas ce bouton) ; l'autre, la copie de la page de secours que le test ne voit pas, est écartée, cette page étant hors de #681 |

## Ce que tu dois pouvoir défendre

1. **Pourquoi factoriser un bouton qui marchait ?** Parce que trois copies d'un balisage fin divergent à la première
   modification. La règle du dépôt dit de factoriser à la troisième occurrence (`code.md`, « Duplication »), et c'est
   la troisième. Rien d'autre ne change : 0 différence sur les 24 pages rendues.
2. **Si `links.html` casse, la page 500 casse-t-elle ?** Son gabarit échoue, oui, mais le gestionnaire rattrape toute
   erreur du gabarit et sert la page de secours écrite sans gabarit (`src/k_b/web/errors.py:83-85`). C'est pour cela
   que cette page reste hors de la macro. Les pages du fil, du détail, des sources et des tendances dépendaient déjà de
   `links.html`.
3. **Pourquoi la page 403 n'appelle-t-elle pas la macro ?** Elle n'a pas ce bouton : son seul bouton déconnecte le
   compte refusé (`403.html:12`), car le fil de veille lui est fermé.
4. **Pourquoi pas de `|safe` pour rendre le HTML de la macro ?** Une macro rend du balisage marqué comme sûr quand
   l'échappement automatique est actif. `|safe` est d'ailleurs interdit dans tout gabarit (`tests/web/test_templates.py`,
   `FORBIDDEN`).
5. **Que se passe-t-il si quelqu'un recopie le libellé dans une nouvelle page ?** `writers` ne vaut plus
   `["links.html"]` : le test échoue et la CI refuse la PR.

## Zones non vérifiées

- Les pages n'ont pas été rouvertes dans un navigateur. Le HTML rendu étant identique octet pour octet, et la feuille
  de style inchangée, l'affichage ne peut pas différer.
- Pas de passage par l'export en ligne ni par un lecteur d'écran : rien de ce qu'ils lisent n'a changé.
- Les tests PostgreSQL ont tourné sur l'image de la CI en aarch64, l'architecture du Mac ; la CI la tire en amd64.
- Les jobs `image-build`, `build` et `bicep-build` n'ont pas été rejoués. `infra/`, le `Dockerfile` et
  `.dockerignore` ne changent pas, et `mkdocs.yml` lit `documentation/`, où rien ne change. L'image emporte les
  gabarits comme avant, `links.html` compris.

## Ce qui reste

- **La page de secours** de `web/errors.py:30` garde son lien « Retour au fil de veille » en HTML brut, par conception.
- **Le lien « ← Retour au fil » du détail** (`item.html:6`, `.back-link`) garde son balisage, hors du périmètre de #681.
