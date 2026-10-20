# Redessiner le modèle Merise depuis le schéma de la base

- **Date** : 2026-10-20
- **Branche** : `docs/merise-20261020`
- **Issue** : #211
- **Fichiers principaux** : `docs/merise/mcd-k-b_20261020.drawio`, `docs/merise/mld-k-b_20261020.drawio`,
  `docs/stockage.md` (« MCD et MLD »), `docs/merise/positions-mcd.md`
- **Série** : suit [la clarification du modèle de la base](2026-10-07-clarifier-le-modele-de-la-base.md)
  (option D : ITEM minimal, sous-types et tables de référence).

Les commits de cette PR sont les cinq premiers de la liste injectée (`f996829` à `2482546`). Les autres
commits listés, et les fichiers de code, de tests et de règles du résumé, viennent de `main` (PR #250 à
#273). Ils ne sont pas de cette branche, et la note ne les couvre pas.

## Le pourquoi

Le 20/10, l'expert du bloc 1 a refusé la case Merise (C4, « modèles conceptuels et physiques »). Il
reprochait trois choses : un modèle en retard sur le schéma, des attributs liste, et un `stockage.md` qui
renvoyait aux versions du 08/10. Le MCD du 12/10 n'avait ni clip, ni tag, ni entrée Zotero, et il donnait
encore pour « prévus » des objets déjà codés.

Ce travail redessine le MCD depuis la seule source qui fait foi : `src/k_b/database/schema.sql`, le MPD,
lu comme un fichier. Le MLD se déduit ensuite du MCD par les règles de passage de Merise (décision de
Sabine du 20/10). Les deux modèles sont des instantanés datés, et les anciens ne sont pas touchés.
`stockage.md` désigne les nouveaux fichiers et justifie les deux endroits où le MPD s'écarte du MLD.

Les trois niveaux, à savoir dire à l'oral :

- **MCD** : ce que K-B sait du monde, sans technique ;
- **MLD** : les tables et les clés qui en découlent par des règles ;
- **MPD** : le script SQL réel, qui peut s'écarter du MLD pour une raison écrite.

## Le comment

### 1. Chaque élément dessiné renvoie à sa ligne de `schema.sql`

Chaque entité du MCD porte `schema.sql:<lignes>` sous son nom, et chaque propriété et chaque association
porte « l. <n> ». Exemple : la propriété « mode d'acquisition » de Source renvoie à cette ligne :

```sql
    acquisition_mode TEXT NOT NULL CHECK (acquisition_mode IN ('watch', 'library', 'wiki'))
```
`src/k_b/database/schema.sql:23`

C'est une propriété de Source, pas une entité, comme le demande le critère de #211. Les quatre
identifiants qui n'ont pas de colonne en base (codes de Classement, Auteur, Paquet suivi et Paquet touché)
sont marqués « absent du MPD ». Ce renvoi rend le modèle vérifiable ligne à ligne, et c'est ce que le
contrôle de la section « Preuve » vérifie.

### 2. L'héritage : Item et ses sous-entités (spécialisation X, sans T)

Item est l'entité générique. Version publiée, Clip de page web, Alerte GitHub, Article de newsletter et
Entrée Zotero sont ses sous-entités et héritent de son identifiant (« code item (hérité d'Item) »). Au
MPD, l'exclusion est tenue par la base :

```sql
    -- The target of the (item_id, kind) foreign key of each subtype: an item has one subtype.
    UNIQUE (id, kind)
```
`src/k_b/database/schema.sql:48-49`

```sql
    kind                  TEXT NOT NULL CHECK (kind = 'release'),
    ...
    FOREIGN KEY (item_id, kind) REFERENCES item (id, kind)
```
`src/k_b/database/schema.sql:176, 191`

Un item n'a qu'une valeur de `kind`, et une ligne `release` exige `kind = 'release'` et une clé
`(item_id, kind)` qui existe dans `item`. Un item ne peut donc pas avoir deux sous-types : c'est le **X**
(exclusion). Il n'y a pas de **T** (totalité) : un item `paper` ou `vulnerability` n'a pas de sous-entité,
il passe par les tables de référence (sous-section 3).

Au MCD, `kind` n'est pas une propriété d'Item, parce que le type se déduit de la structure : la
sous-entité, ou bien DÉCRIRE ou RECENSER. Il est noté sur la spécialisation : « discriminant : type
d'item ». `kind` est la façon dont le MPD matérialise ce discriminant.

**Identifiant ou discriminant** (décision de Sabine du 20/10). Dans sa formation DWWM, Sabine a appris
à appeler « discriminant » la propriété soulignée qui identifie chaque occurrence d'une entité (« code
question »). Le MCD de K-B l'appelle **identifiant**, le mot de Merise : « Identifiants : le mécanisme
d'héritage s'applique aussi à l'identifiant du sur-type qui est aussi l'identifiant du sous-type »
(Espinasse, voir les sources). Le MCD de K-B a une spécialisation, et dans ce contexte « discriminant »
désigne autre chose : l'attribut qui dit à quelle sous-entité appartient une occurrence. Un cours de
Merise 2 le décrit comme « un attribut permettant de différencier les occurrences » quand la
spécialisation tient dans une seule relation (Nomad Education). Le nom « discriminator column » vient
du monde objet-relationnel (JPA, Oracle). Garder « discriminant » pour l'identifiant aurait donné deux
sens au même mot sur un seul schéma. À l'oral : « l'identifiant, ce que ma formation appelait
discriminant ».

Ce que la base ne tient pas : qu'un item de type `release` ait vraiment sa ligne `release`. C'est le code
qui le tient : un seul écrivain par type écrit les deux ensemble (`src/k_b/database/writing.py:58-66`,
`WRITER_BY_KIND`). La légende du MCD le dit.

### 3. Les tables de référence en (0,1)–(0,1) : DÉCRIRE et RECENSER

Une publication existe dès qu'une source la cite, et arXiv n'est pas forcément passé. Une vulnérabilité
existe dès qu'une alerte GitHub cite son CVE, même hors du catalogue CISA KEV. Le lien vers l'item est
donc facultatif des deux côtés :

```sql
    item_id      INTEGER UNIQUE REFERENCES item (id),
```
`src/k_b/database/schema.sql:59`

`UNIQUE` donne « au plus un » côté item, et l'absence de `NOT NULL` donne « zéro possible » côté
publication : d'où DÉCRIRE (0,1)–(0,1). Un `CHECK` (l. 71-75) impose que les colonnes arXiv soient
remplies si et seulement si `item_id` l'est. RECENSER suit la même forme (l. 134, 148-154). Que l'item
visé soit de type `paper` (ou `vulnerability`) est tenu par le code
(`src/k_b/database/writers/paper_writer.py:37-41`), pas par la base : la légende le dit.

### 4. Le MLD se déduit du MCD par les règles de passage

Le titre du MLD donne les règles appliquées :

- une entité donne une table, avec la clé primaire `id` ;
- (0,N) ou (1,N)–(1,1) donne une clé étrangère obligatoire du côté (1,1) ;
- (0,1)–(0,N) donne une clé étrangère facultative du côté (0,1) ;
- (0,1)–(0,1) donne une clé étrangère `UNIQUE` facultative ;
- (0,N)–(1,N) donne une table de liaison `<a>_has_<b>` à clé composée (`item_has_tag`) ;
- une sous-entité prend pour clé primaire `item_id`.

Le MLD a donc 19 tables : les 15 de `schema.sql`, plus `ranking`, `author`, `tracked_package` et
`affected_package`, notées « absente du MPD » sur fond bleu. Chaque écart avec le MPD est écrit en gris
dans la table qu'il concerne. Exemple : pour `release`, « MPD : + id (l. 174), PK ; item_id UNIQUE
(l. 175) ; + kind (l. 176) et FK (item_id, kind) (l. 191) ». Chaque flèche part de la ligne de la clé
étrangère et vise la clé primaire. Chacune a sa propre voie, pour que deux flèches ne partagent jamais un
segment (constats 2 à 5 de la revue).

### 5. Première dénormalisation du MPD : le classement dans `trend` (2FN)

```sql
-- window of 3 days, the 30 first by stars and the 30 first by forks together. One row per window
-- and per repository, produced by a raw result of gh_archive. News feed, by window: the first
-- ranking seen of a window is kept whole, so every row of a window has the same raw_data_id.
```
`src/k_b/database/schema.sql:104-106`

La clé naturelle de `trend` est `(window_end, repository_id)` (l. 121). Or `raw_data_id` ne dépend que de
`window_end` : toutes les lignes d'une fenêtre ont la même donnée brute. Une colonne qui dépend d'une
**partie** de la clé, c'est une violation de la **2FN**. Le MCD le dessine comme Merise le demande :
une entité Classement (fin de la fenêtre), produite par une donnée brute et qui compte des tendances. Le
MPD garde `trend` seule. La règle est tenue par l'écriture :

```sql
WHERE NOT EXISTS (
    SELECT 1 FROM trend WHERE window_end = :window_end AND raw_data_id <> :raw_data_id
)
```
`src/k_b/database/writers/trend_writer.py:24-26`

Une ligne n'est écrite que si aucune autre donnée brute n'a déjà apporté sa fenêtre. La raison est écrite
dans `docs/stockage.md:233-239`.

### 6. Seconde dénormalisation du MPD : les trois listes JSON (1FN)

Le critère de #211 interdit tout attribut liste au MCD. Les auteurs, les paquets suivis et les paquets
touchés y deviennent donc des entités : Auteur, Paquet suivi et Paquet touché, chacune reliée à son
porteur en 1,1. Au MPD, ce sont des listes JSON dans une colonne :

```sql
    -- The names, in arXiv's order.
    authors      TEXT
        CHECK (json_valid(authors) AND json_type(authors) = 'array'
            AND json_array_length(authors) > 0)
```
`src/k_b/database/schema.sql:62-65`

Une valeur non atomique, c'est une violation de la **1FN**. La raison, liste par liste, est écrite dans
`docs/stockage.md:240-249` : une liste n'est jamais cherchée ni filtrée en base, et elle s'écrit entière.
Les auteurs et les paquets touchés sont relus entiers et servis en liste par l'API
(`src/k_b/database/reading.py:406, 432`). Les paquets suivis sont une copie de la liste du code, jamais
relue en base (constat 1 de la revue).

Ne pas confondre les deux dénormalisations à l'oral : la **1FN** porte sur la forme d'une valeur (une
liste) ; la **2FN** porte sur la dépendance d'une colonne envers la clé.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Source : `schema.sql` lu comme un fichier | décision de Sabine du 20/10 : la seule source qui fait foi | une base créée et lue (règle du 12/10, révisée) ; la mémoire ou les anciens schémas |
| Le MLD se déduit du MCD | décision de Sabine du 20/10 : c'est la démarche Merise | un MLD recopié de `schema.sql` (c'était le plan v1 : le MLD aurait gardé les listes JSON) |
| Une entité par liste, jamais partagée | un nom n'identifie pas une personne ; relier deux publications par un auteur croiserait des données par un identifiant personnel (`.claude/rules/conformite.md`, RGPD) | **Auteur partagé** entre publications ; **Paquet partagé** : l'écosystème d'une alerte n'est pas une colonne d'`advisory` (`schema.sql:198-219`), et un nom de paquet seul n'identifie pas un paquet |
| Classement au MCD | 2FN (sous-section 5) ; décision de Sabine | une simple ligne de légende (l'expert peut relever la 2FN) |
| « code <entité> » souligné pour toutes les entités, avec un `UNIQUE (publication_id, rank)` au MLD | convention de Sabine (son dossier DWWM), une seule règle ; décision de time-knight | l'identification relative (clé composée `(publication_id, rank)`), que la convention n'utilise pas ; constat 6 de la revue, gardé tel quel |
| `kind` n'est pas une propriété d'Item ; il est noté « discriminant : type d'item » sur la spécialisation | il se déduit de la spécialisation et de DÉCRIRE ou RECENSER ; décision de Sabine pour la mention | le garder comme propriété (redondant) ; une spécialisation XT à 7 sous-entités, dont deux sans propriété |
| « Identifiant » pour la propriété soulignée | le mot de Merise ; « discriminant » est réservé aux sous-types (décision de Sabine du 20/10, constat 9) | « Discriminant », le mot de la formation DWWM : un même mot aurait eu deux sens sur le schéma |
| Surlignage sur Entrée Zotero, Étiquette sur Item | une règle : le commentaire de `schema.sql` fait foi (l. 78, 331), la clé étrangère à défaut | Surlignage sur Item (fidèle à la clé étrangère, mais dirait qu'une version publiée peut avoir un surlignage) |
| Noms français au MCD (Étiquette, Clip de page web, Version publiée), noms de `schema.sql` au MLD | conventions de Sabine ; la correspondance se lit d'un modèle à l'autre | un mot anglais entre parenthèses au MCD |
| `tag_name` devient « nom de version », `name` devient « titre » | évite un conflit avec l'entité Étiquette et deux « nom » dans une même entité | « balise Git » (une balise est HTML en français) |
| Accents gardés sur les capitales (DÉCRIRE) | orthographe française ; décision de time-knight | les capitales sans accent du dossier oQuiz |

## Preuve

| Commande ou sortie observée | Ce que ça démontre |
|---|---|
| Script de vérification (scratchpad, hors du dépôt) : « MLD: 19 tables, 108 rows; MPD: 15 tables, 104 columns … no problem found » | chaque colonne des 15 tables du MPD est dans le MLD ou dans une note d'écart ; chaque ligne citée au MLD contient le nom attendu ; chaque élément du MCD cite des lignes qui existent |
| Le même script sur un `schema.sql` où deux colonnes sont renommées exprès : 3 problèmes trouvés | le contrôle n'est pas vide : il attrape une erreur |
| Boucle `grep -c` sur chaque table et chaque nom de colonne de `schema.sql` dans le MLD : `missing=0` | la vérification par commande que demande la mission |
| Contrôle géométrique (scratchpad) : 0 chevauchement, 0 trait à travers une forme, 0 croisement, 0 segment superposé, sur les deux modèles | aucune flèche ambiguë ; ce contrôle a été renforcé après la revue, qui avait trouvé 4 superpositions qu'il ne voyait pas |
| Calcul des 15 positions sujet / complément sur les coordonnées du `.drawio` | la table de `positions-mcd.md` dit vrai |
| `/code-review high` : 10 constats, triés par time-knight ; 1 à 9 corrigés, sauf le 6 (gardé) ; le 9 tranché par Sabine | la revue a eu lieu et ses suites sont tracées dans la PR |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi votre MPD n'est-il pas en 3FN alors que votre MLD l'est ? »** Deux dénormalisations
   voulues et écrites. Pour `trend` (2FN), un classement n'a pas d'autre attribut que sa donnée brute, et
   la règle est tenue par l'écriture (`trend_writer.py:24-26`). Pour les listes JSON (1FN), elles ne sont
   jamais cherchées ni filtrées en base et s'écrivent entières (`docs/stockage.md:233-249`).
2. **« Comment garantissez-vous qu'un item n'a qu'un sous-type ? »** Par la base : clé étrangère
   `(item_id, kind) → item (id, kind)` et `CHECK kind = '…'` (`schema.sql:49, 176, 191`). Ce que la base
   ne garantit pas, qu'un item `release` ait sa ligne, est tenu par l'écrivain unique de chaque type
   (`writing.py:58-66`).
3. **« Pourquoi DÉCRIRE est-elle en (0,1) des deux côtés ? »** Une publication peut exister sans item
   arXiv (citée par une entrée Zotero), et un item arXiv décrit au plus une publication :
   `item_id UNIQUE`, facultatif (`schema.sql:59`).
4. **« Votre Auteur n'est-il pas un doublon quand un chercheur signe deux articles ? »** Non. Un auteur
   est une place dans la liste d'une publication, pas une personne. K-B ne relie pas deux publications par
   un nom (RGPD : pas de croisement par identifiant personnel). L'unicité du rang dans une publication est
   tenue par `UNIQUE (publication_id, rank)` au MLD.
5. **« Où est la clé de Classement dans votre base ? »** Nulle part : la table est absente du MPD.
   `trend.window_end` et `trend.raw_data_id` en tiennent lieu, et le MLD le note en gris dans `ranking` et
   dans `trend`.

## Zones non vérifiées

- **Le rendu visuel n'a pas été vu.** Les `.drawio` sont générés par un script, et draw.io n'est pas
  installé en ligne de commande. Le contrôle géométrique travaille sur les coordonnées, pas sur l'image :
  la taille des textes, les lignes qui débordent d'une cellule et la lisibilité des petites mentions
  « l. » restent à voir dans draw.io. Sabine exporte l'image, et c'est à ce moment que cela se vérifie.
- **Les scripts de génération et de vérification ne sont pas dans le dépôt** (scratchpad de la session) :
  un tiers ne peut pas relancer le contrôle géométrique. Le contrôle `grep -c` est, lui, rejouable.
- **Le sens de « discriminant » pour les sous-types** : aucune des sources lues n'est un cours Merise en
  français qui emploie le mot lui-même. Nomad Education décrit l'attribut sans le nommer, et le mot vient
  des sources objet-relationnel (JPA). L'usage est donc établi par recoupement, pas par une source de
  référence Merise.
- La phrase « servies en liste par l'API » est vérifiée dans `reading.py:406, 432`, mais pas jusqu'aux
  routes de l'API.

## Ce qui reste

- L'image exportée du modèle, à mettre dans `docs/merise/` : c'est Sabine qui l'exporte depuis draw.io,
  avant la fusion.
- Signalés, hors de cette PR :
  - `docs/stockage.md:216-217` dit que les classements n'entrent pas dans la base, ce que `trend`
    contredit ;
  - `docs/2026-10-07-clarification-modele.md:234` renvoie à l'ancien `mld-k-b.drawio` pour la liste des
    `kind` ;
  - `highlight_id` (`schema.sql:84`) est la seule clé primaire qui ne s'appelle pas `id` ;
  - la clé étrangère de `highlight` vise `item`, alors que le commentaire de `schema.sql` parle d'une
    entrée Zotero ;
  - `tracked_repository.packages` n'a pas de maximum ;
  - la mission compte 14 tables, et `schema.sql` en a 15.
- Aucune issue pour aligner la base sur le MLD : la dénormalisation est voulue (décision de Sabine du
  20/10).

## Sources (consultées le 2026-10-20)

- Bernard Espinasse, « Modélisation conceptuelle des données : compléments » (MCD2 - Merise), Université
  d'Aix-Marseille :
  <https://pageperso.lis-lab.fr/bernard.espinasse/wp-content/uploads/2021/12/6-MCD2-Merise-4p.pdf>
  (héritage de l'identifiant du sur-type par le sous-type).
- Nomad Education, « Merise 2 : la spécialisation d'entités » :
  <https://www.nomadeducation.fr/revisions/licence-informatique-1re-annee-lb2efe85/merise-2-la-specialisation-dentites-cy595931>
  (« un attribut permettant de différencier les occurrences » ; les relations spécialisées héritent de la
  clé primaire de la relation générique).
- Oracle, The Java EE 6 Tutorial, « Entity Inheritance Mapping Strategies » :
  <https://docs.oracle.com/cd/E19226-01/820-7627/bnbqr/index.html> (la colonne discriminante d'une
  hiérarchie tenue dans une seule table).
