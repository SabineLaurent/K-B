# Placer les logigrammes de la collecte et de l'import dans la page des données

- Date : 2026-11-21
- Branche : `docs/data-logic-diagrams`
- Issue : #675
- Fichiers principaux : `documentation/import_et_base_pour_docu.md`, `documentation/accessibilite_pour_docu.md`,
  `documentation/images/logigramme-collecte_20261121.{drawio,png}`,
  `documentation/images/logigramme-import-lire_20261121.{drawio,png}`,
  `documentation/images/logigramme-import-ecrire_20261121.{drawio,png}`
- Série : [écrire la fiche de l'import et de la base](2026-11-11-ecrire-la-fiche-de-l-import-et-de-la-base.md), et
  [mettre en forme la fiche du monitorage](2026-11-21-mettre-en-forme-la-fiche-du-monitorage.md) (la vérification
  selon la notice d'AcceDe Web)

Les commits de cette PR sont `fca956fa` et `c4beb569`, plus celui de cette note, sur `main` à `36c1e02d`. Les autres
commits de la liste fournie à la note sont déjà sur `main` (#670, #662, #665, #664) et ont leurs propres notes.

## Le pourquoi

Le critère C3 demande de documenter <q>les enchaînements logiques de l'algorithme</q>. Les trois logigrammes de l'oral
blanc les dessinent : `kb collect`, puis `kb import` en deux parties, lire et transformer, puis écrire en base. Ils
décrivent le commit figé d'E1 (`d28137e`), et Sabine a décidé le 21/11 de les garder tels quels pour E1, et de mettre
dans la documentation leur version à jour de `main`.

Une relecture neuve du 21/11, contre `origin/main` 36c1e02, avait trouvé deux écarts avec `main` et quatre cas que
les dessins ne montrent pas. La relecture de cette PR, par un second sous-agent neuf, en a trouvé treize de plus, que
time-knight a tous fait corriger. Ce travail corrige les dessins, écrit dans le texte ce qu'ils ne montrent pas, et
donne à la collecte la description pas à pas que la page n'avait pas.

## Le comment

### Les corrections du dessin, tirées du code

La première : l'échec d'une source part au journal de fonctionnement, par `logger.error`, pas au journal d'import de
`journals/`, que `kb collect` n'écrit pas.

```python
        except Exception as error:
            ...
            logger.error(
                "collection failed for source %r: %s",
```
(`src/k_b/etl/extract.py:71-76`). La case du dessin dit donc « noté au journal de fonctionnement », le mot de la page
et de la règle 3 de `conventions.md`.

La seconde : la question « Base désignée et présente ? » ne vaut que pour SQLite.

```python
def check_database_exists(location: DatabaseLocation) -> None:
    """Connecting to a missing file would create an empty base; the server of a PostgreSQL base
    answers for it at the first query."""
    if isinstance(location, Path) and not location.is_file():
```
(`src/k_b/database/location.py:167-170`). Une base PostgreSQL absente ou injoignable répond par une erreur du moteur à
la première requête, que `run_import` rend en code 1 (`src/k_b/commands/import_command.py:54-56`). La question devient
« Réglage de la base valide, fichier SQLite présent ? », sa fin « code 2 : réglage refusé ou fichier SQLite absent »,
et une note du dessin dit le code 1 de toute autre erreur, dont une base PostgreSQL absente ou injoignable.

Les autres corrections viennent de la relecture de la PR, chacune vérifiée dans le code :
- **l'écriture du journal et la validation peuvent échouer**, après la question « Journal de cette seconde déjà
  là ? » : aucun journal n'est gardé, et la commande sort en 1 (`src/k_b/etl/load.py:139-146`). Une question
  « Journal écrit et transaction validée ? » les suit, avec sa fin « code 1 : aucun journal gardé ». La fin ne dit
  pas « rien en base » : un COMMIT qui échoue lève une erreur du moteur, que la base ait gardé ou annulé la
  transaction (commentaire de `src/k_b/etl/load.py:140-141`). Le texte dit ce qui reste vrai dans les deux cas :
  l'import tient en une seule transaction, l'inscription des fichiers au registre comprise, et le prochain import
  relit chaque fichier que la base n'a pas inscrit (`src/k_b/etl/load.py:76-79`, `src/k_b/etl/raw_reading.py:107-113`) ;
- **les deux boucles posent leur question d'abord** : « Reste-t-il un fichier ? » et « Reste-t-il un item ? ». Un
  import sans fichier, ou un fichier sans item, est un cas normal : le bilan de la page en donne un, `0 raw read`.
  Le dessin à « prendre le suivant » d'abord l'envoyait à un fichier qui n'existe pas ;
- **le verrou des écrivains** n'est pris à cette étape que sur PostgreSQL ; SQLite le prend à la première écriture
  (`src/k_b/database/engine.py:43-47`) ;
- **un retrait** demande au moins une entrée et aucun rejet (`src/k_b/etl/withdrawals.py:24`, `:41`) ;
- **une source est interrogée avec sa date si elle s'en sert** : Zotero et les deux classements GitHub ne s'en
  servent pas, et sont relus à chaque collecte (`src/k_b/etl/sources/zotero.py:205-206`) ;
- la légende violette dit « Journal et validation », la seule case qu'elle colore ; la note rouge pointillée de la
  lecture a son entrée de légende, « Note ».

### Les sources `.drawio` à côté des PNG

Chaque logigramme est un `.drawio` corrigé par un script Python sur son XML (le libellé et la taille de quelques
cases), puis exporté par draw.io 32.6.10 en ligne de commande, à l'échelle 2 :
`draw.io -x -f png -s 2 -b 10 -o <nom>.png <nom>.drawio`. Le dépôt garde déjà ses sources draw.io
(`docs/merise/*.drawio`) : la source reste à côté de l'image, pour que la prochaine mise à jour parte d'elle. Le nom de
la page de chaque `.drawio` dit le commit qu'il suit : `kb collect (main 36c1e02)`
(`documentation/images/logigramme-collecte_20261121.drawio:2`).

### L'image donne la vue d'ensemble, le texte le détail

Les dessins font de 904 à 1 318 unités de large, en police de 11 à 14 ; la colonne du site en fait 688 pixels. À
cette largeur, le texte de la collecte et de l'écriture rendrait autour de 6 pixels. Chaque image est donc suivie d'un
lien texte vers son fichier en taille réelle, puis de sa description en texte :

```markdown
![Logigramme de kb collect, la préparation puis la collecte de chaque source, décrit en texte dans la section « La collecte, pas à pas »](images/logigramme-collecte_20261121.png)

[Le logigramme de `kb collect` en taille réelle (image de 2 673 × 1 075 pixels)](images/logigramme-collecte_20261121.png)
```
(`documentation/import_et_base_pour_docu.md:232-234`). Le texte de remplacement est court et nomme la section qui le
décrit (règle 4.4 de la notice d'AcceDe Web) ; l'image n'est pas dans le lien, qui a son propre intitulé (règles 3.1
et 4.3).

### La collecte, pas à pas

La page ne décrivait `kb collect` que dans sa vue d'ensemble. La section « La commande qui précède l'import :
`kb collect` » lui donne la même forme que l'import : la commande, le logigramme, une liste numérotée en sept étapes,
chacune avec son renvoi, et le tableau des codes de sortie (`documentation/import_et_base_pour_docu.md:212-276`). Les
codes communs à toutes les commandes, lus dans `cli.py`, y entrent : 2 pour un réglage de `kb` ou un fichier du journal
de fonctionnement refusé (`src/k_b/cli.py:113-117`, `:232-240`), 1 pour une exception que la commande ne traite pas
(`src/k_b/cli.py:261-265`), 130 et 143 pour un signal (`src/k_b/cli.py:252-260`).

### Ce que l'import dit en texte

Trois cas restent hors des dessins de l'import, et la page les donne : la page illisible, rejetée entière et relue au
prochain import (étape 3, déjà écrite) ; les classements GitHub, qui n'ont pas de lecteur (étape 2, déjà écrite) ;
la fenêtre de tendances déjà en base, écartée et écrite au journal d'import (étape 7, ajoutée, `etl/file_writing.py:87-91`).
L'étape 7 dit aussi l'item écarté (`database/writers/discard.py:8-10`) et la condition d'un retrait : au moins une
entrée et aucun rejet (`etl/withdrawals.py:24`, `:41`).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Lisibilité à 688 pixels | l'image à la largeur de la colonne, un lien vers sa taille réelle, la description en texte (tri du Second, 21/11) | un cadre qui défile en deux dimensions (une règle CSS de plus, une lecture plus lourde); redessiner en portrait (de 45 min à 1 h par dessin, hors budget) |
| Le mot de l'échec d'une source | « journal de fonctionnement », le mot de la page et de `conventions.md` | « log », proposé par la relecture : un mot anglais, à baliser `lang="en"` dans le texte |
| Le code 1 de PostgreSQL | une note dans le cadre du dessin, « Toute autre erreur, dont une base PostgreSQL absente ou injoignable : fin, code 1, rien en base », et le texte (étape 1, tableau des codes) | une case et une flèche de plus depuis la lecture du registre : la case n'a pas la place d'une sortie, et l'erreur peut venir d'ailleurs (disque, seconde validation d'un item) |
| « Écarté » dans l'écriture | libellé gardé, le texte dit le journal d'import | « Écarté, écrit au journal d'import » : la case est bornée par le trait pointillé qui la suit, et la relecture le donnait comme facultatif |
| Le nom des fichiers | `logigramme-<commande>_20261121`, comme les planches de #619 et les sources de `docs/merise/` | le nom de l'oral blanc (`-paysage`) : il dit la mise en page, pas le contenu |
| Le nom de la page | `import_et_base_pour_docu.md` gardé (consigne du Second) | `donnees.md` : il vient avec la PR du README, qui fusionne en dernier |
| Les deux boucles de l'écriture | la question d'abord, « Reste-t-il un fichier ? », « Reste-t-il un item ? » (tri de time-knight) | « prendre le suivant » d'abord, comme à l'oral blanc : faux pour un import sans fichier ou un fichier sans item |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `mkdocs build --strict` : vert, aucun avertissement | les trois images et les trois liens se résolvent |
| contrôle AcceDe Web du HTML construit (`import_et_base_pour_docu`, `accessibilite_pour_docu`) : `lang`, un `h1`, aucun saut de niveau, chaque tableau avec ses `th`, aucune image dans un lien, aucun lien sans intitulé | les deux pages tiennent la notice avec leurs images |
| les trois PNG relus à l'œil après l'export, une découpe de la case de l'échec | les libellés corrigés tiennent dans leurs cases |
| aucun bloc `tEXt` dans les PNG ; aucun `agent`, `etag` ni `modified` dans les `.drawio` | rien de personnel dans les fichiers publiés |
| aucun caractère `Cc` ni `Cf`, aucune espace avant « : » ni « ; » dans les deux fiches | les règles du dépôt pour `documentation/` |
| `uv run pytest` : 5664 passed, 365 deselected | la PR ne touche pas au code |
| relecture par un sous-agent neuf, en lecture seule, des dessins et du texte contre le code : 13 constats, tous corrigés sur le tri de time-knight | chaque fait vérifié par un second lecteur |
| relecture courte du delta par un autre sous-agent neuf : aucun trait faux ni manquant, aucun oui/non inversé ; 6 petits constats, corrigés sur le tri de time-knight | les dessins redessinés et les cases changées tiennent contre le code |

## Ce que tu dois pouvoir défendre

1. **Pourquoi deux représentations de l'import, le schéma Mermaid et les logigrammes ?** Le schéma Mermaid donne les
   neuf étapes en une colonne ; les logigrammes donnent chaque question, chaque branche et chaque fin avec son code.
   Le texte de la section décrit les deux (`documentation/import_et_base_pour_docu.md:311-409`).
2. **Que fait `kb import` si la base PostgreSQL est éteinte ?** Rien n'est lu ni écrit : la lecture du registre
   échoue à la première requête, et la commande sort en 1 (`src/k_b/commands/import_command.py:54-56`).
3. **Une source en panne bloque-t-elle la collecte ?** Non : l'erreur est rattrapée par source, notée au journal de
   fonctionnement, la source garde sa date et les autres continuent ; la commande sort en 4 si une autre a réussi
   (`src/k_b/etl/extract.py:71-81`, `src/k_b/commands/collect_command.py:115-124`).
4. **Comment une lectrice qui ne voit pas l'image suit-elle le logigramme ?** Le texte de remplacement nomme la
   section qui le décrit, et la liste numérotée en donne chaque case, avec son renvoi au code.
5. **Pourquoi garder le `.drawio` dans le dépôt ?** C'est la source : une image se régénère d'elle par une commande,
   et un écart avec le code se corrige dans un seul fichier.

## Zones non vérifiées

- Le rendu des trois images dans un navigateur : le HTML construit et les PNG sont vérifiés, la page servie ne l'est
  pas.
- Ce qu'un lecteur d'écran dit des trois images et de leurs liens.
- Les `.drawio` copiés avec le site : MkDocs copie tout fichier de `documentation/`, et les trois sources sont servies
  à côté de leurs images, sans lien vers elles.

## Ce qui reste

- Le renommage de la page en `donnees.md`, avec la PR du README.
- Le site, quand #619 fusionne : la déclaration d'accessibilité réunit les deux planches de la fiche des maquettes et
  ces trois logigrammes ; la PR qui fusionne en second recompte les images et les pages.
