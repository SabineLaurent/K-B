# Écrire les pages des données du site pour E1

- **Date** : 2026-11-22
- **Branche** : `docs/e1-data-pages`
- **Issue** : #685 (issues ouvertes en marge : #686, #687)
- **Fichiers principaux** : `documentation/collecte.md`, `documentation/requetes.md`,
  `documentation/modele-de-donnees.md`, `documentation/donnees-personnelles.md`, `documentation/api-donnees.md`,
  `documentation/images/m*d-k-b_20261107*.png`, `docs/merise/*_20261107.drawio`,
  `mkdocs.yml`, `documentation/accessibilite_pour_docu.md`
- **Note précédente de la série** :
  [Placer les logigrammes dans la page des données](2026-11-21-placer-les-logigrammes-dans-la-page-des-donnees.md)

La liste des fichiers que l'outil de la note a calculée compte aussi des commits déjà sur `main` (#658, #662, #664,
#665, #670, #679) : elle part d'une base plus ancienne. Cette PR n'a qu'un commit, `3e5494b0`, au-dessus de
`origin/main` `39cb5eb9` ; la note ne couvre que lui.

## Le pourquoi

Le dossier d'E1 affirme que la documentation de ce qu'il présente est versionnée dans `documentation/` et publiée sur
le site de K-B. Le relevé de cohérence d'E1 montrait que quatre critères n'y avaient aucune page : leur documentation
n'existait que dans `docs/`, un dossier de travail que le site ne publie pas.

- C1, les spécifications techniques de la collecte ;
- C2, la documentation des requêtes d'extraction ;
- C4, le modèle Merise, le registre des traitements et les procédures de tri ;
- C5, l'API de données (l'API IA avait déjà sa page).

Cette PR écrit cinq pages, une par sujet, dans la partie « 2. Les données » du site. Chacune reprend le fond de
`docs/`, le contrôle contre le code de `main`, et porte elle-même ce que son critère demande. `docs/` reste le
détail ; le site est ce que lit le jury.

## Le comment

### 1. Le menu suit le chemin des données

`mkdocs.yml:17-23` :

```yaml
      - 2. Les données:
          - collecte.md
          - requetes.md
          - import_et_base_pour_docu.md
          - modele-de-donnees.md
          - donnees-personnelles.md
          - api-donnees.md
```

L'ordre est celui du flux : la collecte, ses requêtes, l'import dans la base, le modèle de cette base, les données
personnelles qu'elle porte, puis l'API qui la sert. La page de l'import, qui existait, reste à sa place dans ce
chemin. Les noms sont courts, sans le suffixe `_pour_docu` des pages plus anciennes (décision du 2026-11-21).

Le menu gagne six lignes : tous les renvois `mkdocs.yml:N` des autres pages, au-delà de la ligne 16, ont été
recalés de six (`documentation/accessibilite_pour_docu.md`, `documentation/integration_continue_pour_docu.md`).

### 2. Chaque page porte son critère, puis ses faits

Chaque page ouvre sur l'encadré « Compétences de la certification », le texte du critère mot pour mot, puis dit le
commit de `main` qu'elle décrit (`39cb5eb9`). Ses sections suivent les mots du critère. Pour C1, par exemple, la
page a une section par élément : « Les technologies et outils », « Les services externes », « Les exigences de
programmation », « L'accessibilité des sources » (disponibilité, accès), et le périmètre jusqu'au « jeu de données
brutes ». Elle finit par « Vérifier cette fiche » : les commandes, en lecture seule, qui prouvent ses faits.

Chaque fait porte son renvoi `fichier:ligne`. Deux contrôles l'ont tenu, des scripts gardés hors du dépôt : l'un
vérifie que chaque renvoi vise un fichier et des lignes qui existent (0 problème sur les cinq pages), l'autre les
règles du texte (aucune espace avant « : » ni « ; », aucun caractère invisible, les listes en retrait de quatre
espaces).

### 3. Une limite s'écrit comme un choix, puis sa vérification

`documentation/collecte.md:288-293` :

```markdown
**arXiv.** La collecte d'arXiv demande toute sa fenêtre en une seule page, de 2 000 papiers au plus
(`etl/sources/arxiv.py:53`, `:107`). Elle collecte tout ou rien: si arXiv annonce plus de papiers que la page n'en
rend, la source refuse la page, n'écrit rien et garde sa date de dernière collecte (`:77-81`, test
`test_a_page_that_does_not_hold_every_result_is_refused`). Au rythme mesuré (551 papiers du 2026-05-01 au
2026-10-21, `docs/2026-10-21-collecte-reelle.md:179`), il faudrait plus d'un an et demi sans collecte pour atteindre
2 000 papiers.
```

D'abord le choix (une page, tout ou rien), son code et son test, puis la mesure qui le situe. Les deux limites
écrites (arXiv, l'échantillon de GH Archive, `documentation/collecte.md:337-343`) ont été soumises au tri avant
d'être écrites. Toutes les autres limites trouvées pendant la rédaction (débit en mémoire de l'API, bornes de temps
cumulées en PostgreSQL, passages « non vérifiés » du registre…) sont restées hors des pages.

La phrase de GH Archive a été retouchée en route : elle disait « jamais un nombre d'étoiles gagnées », ce qui était
faux pour le site, dont la page des tendances affiche ces comptes (`web/trends.py:132-133`,
`web/templates/trends.html:27`). Elle dit maintenant que le compte rendu en tire des rangs, et que le site les
montre en les disant tirés d'un échantillon.

### 4. Les schémas Merise deviennent des images, à jour de `main`

`documentation/modele-de-donnees.md:85-87` :

```markdown
![MCD de K-B, vue d'ensemble, décrit en texte dans la section « La vue d'ensemble »](images/mcd-k-b_20261107_vue-ensemble.png)

[Le MCD de K-B, vue d'ensemble, en taille réelle (image de 2 012 × 647 pixels)](images/mcd-k-b_20261107_vue-ensemble.png)
```

Un texte de remplacement court qui nomme la section de sa description détaillée, puis un lien vers l'image en
taille réelle : c'est la forme des logigrammes de #679 (règle 4.4 de la notice d'AcceDe Web). Le texte qui suit
l'image en donne le contenu : les 18 entités, les 15 associations avec leurs cardinalités, les 19 relations du MLD et
leurs colonnes.

Les images sont celles des schémas du 2026-11-07, dont les flèches et la disposition ont été revues, et le MLD repris
le 2026-11-12 : `docs/merise/*_20261107.drawio`, copiés tels quels, sans retouche. Avant l'export, ils ont été
comparés aux schémas du 2026-10-20 et aux deux scripts de la base : même modèle, mêmes 19 relations, mêmes colonnes,
mêmes 21 clés étrangères, et aucun écart avec la base. Ils ne portent ni renvoi au code ni cartouche : la page donne
elle-même les lignes de `database/schema.sql`, et les règles que le code tient, dans « Ce que le code tient ». Les
schémas du 2026-10-20 restent dans `docs/merise/`, tels qu'ils étaient, comme historique.

### 5. La déclaration d'accessibilité compte ce qui a été vérifié

`documentation/accessibilite_pour_docu.md:159` ouvre la vérification selon la notice d'AcceDe Web : dix-sept pages
désormais, dont les cinq nouvelles vérifiées le 2026-11-22. Le contrôle a lu le HTML construit par
`mkdocs build --strict` : un seul titre de niveau 1 par page, aucun saut de niveau, aucun `br` hors des schémas,
aucun lien à `title` ni à `target`, un texte de remplacement sur chaque image, des en-têtes à chaque tableau. Les
comptes de la déclaration suivent, après la fusion de `main` (#678) : huit images, onze schémas Mermaid sur sept
fiches.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Où écrire | Cinq pages dans `documentation/`, qui renvoient à `docs/` pour le détail | Publier `docs/` tel quel : ce sont des notes de travail, avec des décisions orales, des passages « à vérifier » et des renvois périmés |
| Le fond | Repris de `docs/`, contrôlé contre le code ; le code fait foi en cas d'écart | Recopier `docs/` : trois documents avaient des renvois ou des faits périmés (`docs/specs-api.md`, `docs/stockage.md`, `docs/registre-traitements.md`) |
| L'OpenAPI | Cité et décrit dans la page de l'API, jamais recopié | Le recopier : deux copies d'un contrat qui dériveraient ; la version du dépôt est tenue égale au code par un test |
| L'échelle des PNG | 1 : le texte des schémas à sa taille d'origine, 131 à 294 Ko | 2, comme #679 : deux fois plus de pixels et de poids, sans information de plus (RGESN, poids des pages) |
| La source des images | Le `.drawio` reste dans `docs/merise/`, le PNG seul entre dans `documentation/images/` | Copier le `.drawio` à côté du PNG, comme #679 : deux sources du même schéma |
| Les schémas montrés | Ceux du 2026-11-07, aux flèches et à la disposition revues, copiés tels quels ; ceux du 2026-10-20 restent comme historique | Retoucher ceux du 2026-10-20 (renvois recalés, purge dite codée), essayé puis écarté : ils sont moins récents, et leur disposition n'a pas été revue |
| Les traitements terminés du registre | Une ligne datée chacun, avec un renvoi au registre | Les omettre : le critère veut l'ensemble des traitements ; les détailler : leur trace contient des décisions orales |
| La rédaction | Cinq rédacteurs en parallèle, puis une relecture de chaque page contre le code, puis une relecture neuve | Une seule rédaction en série : plus de six heures pour cinq pages |

Choix imposés par les consignes du dépôt : « en local » et « en ligne », jamais la visibilité du dépôt ni l'origine
d'un abonnement ; aucune espace avant « : » ni « ; » dans `documentation/`, citations du référentiel comprises ;
une limite nouvelle passe au tri avant d'être écrite.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `NO_MKDOCS_2_WARNING=1 uv run --locked --only-group docs mkdocs build --strict` : aucun avertissement | Chaque page est au menu, chaque lien et chaque ancre existe |
| `uv run pytest -q` : 5 664 passed, 365 deselected | La PR ne casse rien du code |
| Script des renvois : 0 problème sur les cinq pages | Chaque `fichier:ligne` vise un fichier et des lignes qui existent |
| Script du texte : 0 espace avant « : » ou « ; », 0 caractère Cc ou Cf | Règles de typographie du site tenues |
| HTML construit des cinq pages : un `h1`, aucun saut de titre, 0 `br`, 0 `title`, 0 `target`, 3 images avec `alt` | Règles 1 à 4 de la notice d'AcceDe Web tenues |
| Morceaux des PNG : `IHDR`, `IDAT`, `IEND` seulement | Les images ne portent aucune métadonnée |
| Les commandes « Vérifier cette fiche » de chaque page, lancées par ses rédacteurs puis relues | Les faits de chaque page se reprouvent depuis le dépôt |

## Ce que tu dois pouvoir défendre

1. **Pourquoi des pages nouvelles, alors que `docs/` documente déjà tout ?** Le dossier dit que la documentation est
    publiée sur le site ; `docs/` n'y est pas. Et `docs/` est un dossier de travail : décisions orales, passages
    « à vérifier », renvois que le code a dépassés. Chaque page reprend le fond, le vérifie contre le code, et y
    renvoie pour le détail.
2. **Comment sais-tu que les pages disent vrai ?** Chaque fait porte un renvoi `fichier:ligne`, contrôlé par script ;
    un échantillon de faits a été relu contre le code à la relecture, puis par une relecture neuve ; chaque page finit
    par les commandes qui reprouvent ses faits.
3. **Ton MLD a 19 relations, ta base 15 tables : lequel est faux ?** Aucun. Quatre relations du MLD, `ranking`,
    `author`, `tracked_package` et `affected_package`, sont écrites autrement dans le MPD par une décision du
    2026-10-20 : trois listes JSON (hors 1FN) et deux colonnes de `trend` (hors 2FN). La note du MLD le dit, et
    la page détaille chaque écart (`documentation/modele-de-donnees.md`, « Ce que le MPD écrit autrement que le MLD »).
4. **Où sont les procédures de tri, et lesquelles sont automatiques ?** Le tableau des 11 étapes de
    `documentation/donnees-personnelles.md`, « Les procédures de tri » : la colonne « Automatisée », la fréquence et
    le code de chaque étape ; `kb purge` les enchaîne chaque jour en ligne, dans `kb daily-routine`.
5. **Qui peut appeler l'API de données, et comment change-t-on une clé ?** Une clé par client, en `Bearer`, comparée
    à temps constant ; les routes de `watch` réservées au client `WEB` ; une clé n'expire pas (choix du 2026-10-14)
    et se change par une nouvelle version du secret, puis le redémarrage des apps qui la lisent
    (`documentation/api-donnees.md`, « Authentification et autorisation », « Expiration et changement d'une clé »).

## Zones non vérifiées

- Les mesures citées (plan d'exécution et temps de la requête Zotero du 2026-11-03, `dry_run` de BigQuery du
    2026-10-11, part des étoiles vues par GH Archive du 2026-10-29) sont reprises de `docs/`, avec leur date : elles
    n'ont pas été rejouées, il faudrait la vraie base Zotero ou des requêtes BigQuery.
- Les tests marqués `postgresql` (comparaison des deux schémas, schéma PostgreSQL, lecture de l'API sur PostgreSQL)
    n'ont pas tourné : pas de serveur PostgreSQL pendant la rédaction. Le job `tests-postgresql` de la CI les lance.
- Les faits du registre qui n'ont pas de code à l'appui (région de Grafana Cloud, durée de son offre, relevé du
    dépôt du 2026-11-06, conditions de Microsoft) sont repris tels que le registre les date.
- Le rendu des pages dans un navigateur, WAVE et le parcours à la touche Tab : faits par Sabine sur l'aperçu,
    avant la fusion.

## Ce qui reste

- #686 : tenir par la base trois règles que seul le code tient aujourd'hui.
- #687 : remettre à jour trois renvois de `docs/stockage.md`.
- Les écarts trouvés entre `docs/` et le code (renvois de `docs/specs-api.md`, la fiche 2 du registre sur Zotero et
    les clips en ligne, CISA KEV dans `docs/specs-collecte.md`) restent dans `docs/` : la PR ne change pas `docs/`,
    sauf les schémas Merise.
