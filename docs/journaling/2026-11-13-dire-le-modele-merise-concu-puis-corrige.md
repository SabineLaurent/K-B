# Dire que le MCD et le MLD ont été conçus, puis corrigés selon le besoin

- Date : 2026-11-13
- Branche : `docs/mcd-design-wording`
- Issue : #613
- Fichiers : `docs/stockage.md` (« MCD et MLD »), `docs/merise/mcd-k-b_20261020.drawio` et son image
  `docs/merise/mcd-k-b_20261020.svg` (le cartouche)
- Commits : `5a48cd2` (la phrase), puis cette note. Les autres commits de la liste injectée sont ceux de
  `main` avant la branche : ils ne sont pas de cette PR.
- Série : [redessiner le modèle Merise](2026-10-20-redessiner-le-modele-merise-depuis-le-schema.md) (#211),
  [dire pourquoi un SGBD relationnel convient](2026-11-12-dire-pourquoi-un-sgbd-relationnel.md) (#600).

## Le pourquoi

`docs/stockage.md` et le cartouche du MCD disaient le MCD et le MLD « tirés de `schema.sql` » : le
modèle aurait été déduit de la base codée. Ce n'est pas la démarche suivie. La démarche Merise va du
MCD au MLD, puis au MPD : le premier commit de la base, `43f71f2` (2026-10-02, « design the items
database with Merise »), écrit le MCD et le MLD en Mermaid avec le MPD, `schema.sql`. Les modèles ont
ensuite été dessinés avec draw.io (`54aac46`, 2026-10-08), puis corrigés quand ils n'étaient plus en
phase avec le besoin, la dernière fois le 2026-10-20 (#211 : le modèle du 12/10 n'avait ni clip, ni
étiquette, ni entrée Zotero). La phrase dit maintenant cela, aux mots de Sabine.

## Le comment

### La phrase de `docs/stockage.md`

`docs/stockage.md:327-329` :

```markdown
[`mld-k-b_20261020.drawio`](merise/mld-k-b_20261020.drawio). Ils ont été conçus d'abord, puis
corrigés quand ils n'étaient plus en phase avec le besoin ; dernière correction le 2026-10-20
(#211). Leurs images, exportées en SVG : [`mcd-k-b_20261020.svg`](merise/mcd-k-b_20261020.svg) et
```

Seul « tirés de `schema.sql` le 2026-10-20 » disparaît. La phrase qui suit dans la section reste :
chaque élément du MCD renvoie à ses lignes de `schema.sql`, et le MLD se déduit du MCD par les règles
de passage. Les renvois disent où le modèle est codé ; ils ne disent pas d'où il vient.

### Le cartouche du MCD

`docs/merise/mcd-k-b_20261020.drawio:10`, l'attribut `value` de la cellule `title` (du HTML échappé) :

```text
&lt;b&gt;Le MCD et le MLD ont été conçus d&#39;abord, puis corrigés quand ils n&#39;étaient plus en phase avec le besoin ; dernière correction le 2026-10-20 (#211).&lt;/b&gt; Chaque entité, propriété et association renvoie à ses lignes de &lt;code&gt;src/k_b/database/schema.sql&lt;/code&gt; (le MPD) à origin/main d540499 (« l. ») ;
```

Le commit `d540499` passe de la première phrase à la seconde : il dit à quelle version de `schema.sql`
renvoient les « l. ». Sans lui, un numéro de ligne ne se vérifie plus, `schema.sql` ayant changé
depuis. Le cartouche du MLD (« Déduit du MCD … ») ne disait pas « tiré de `schema.sql` » : il reste
tel quel.

### Les trois copies de la phrase dans le SVG

`docs/merise/mcd-k-b_20261020.svg` tient sur une ligne, `svg:1`. draw.io y écrit la phrase trois
fois :

1. en HTML, dans un `<foreignObject>` : c'est ce qu'affiche un navigateur ;
2. en texte de repli, `<text>` et ses lignes `<tspan>`, coupées par draw.io à la largeur du cadre :
   pour un lecteur qui ne sait pas afficher un `<foreignObject>` ;
3. dans l'attribut `content=`, une copie du diagramme pour le rouvrir dans draw.io : un `<mxfile>`
   échappé dont le `<diagram>` contient le XML encodé pour une URL, compressé (*deflate* brut), puis
   en base64.

Le script du scratchpad remplace la phrase dans les trois, et dans le `.drawio`. Il exige une seule
occurrence de l'ancienne phrase à chaque endroit, sinon il s'arrête. Il recoupe les lignes de repli à
la longueur de la plus longue ligne de l'export du 2026-10-20 (276 caractères), sans couper devant
« » », « ; », « : » ni après « « ». Il décompresse la copie, y remplace la phrase avec l'apostrophe de
cette copie (`'` dans la copie, `&#39;` dans le `.drawio`), puis la recompresse.

## Choix faits et options écartées

- **Retenu : l'édition par script.** Le diff se limite au cartouche, et le reste de l'image est
  l'export de Sabine du 2026-10-20 (`1c22f35`). Accord de tn-orchestrateur.
- **Écarté : le réexport par la CLI de draw.io 32.6.10.** Essayé à blanc sur le `.drawio` inchangé, il
  ne redonne pas le SVG actuel : 1 738 lignes de diff, `color-scheme: light dark` au lieu de `light`,
  des couleurs adaptatives au mode sombre, une hauteur de 3110 au lieu de 3109. Il changerait le
  rendu de l'image en mode sombre, hors du périmètre de #613.
- **Écarté : un export par Sabine.** Possible, mais il lui coûte du temps pour une phrase.
- **Imposé par la consigne de Sabine :** le texte, et les renvois aux lignes de `schema.sql` gardés.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `grep -on "[a-zé]*tir[ée]s\?\b"` sur `docs/stockage.md` et sur le `.drawio` et le `.svg` du MCD : seulement « retiré » et « retire » (`stockage.md:415`, `:434`, `mcd-k-b_20261020.drawio:664`), sans rapport | Plus aucun « tiré de `schema.sql` » pour le MCD et le MLD dans ces fichiers |
| Copie de `content=` décompressée, comparée au `.drawio` modifié : 431 nœuds, mêmes attributs, sauf `dx` (décalage de la vue, déjà différent avant) | La copie qui rouvre l'image dans draw.io dit la même chose que le `.drawio` |
| Diff normalisé (`content=` vidé) contre `origin/main` (`690a63f`) : 8 lignes changées dans le SVG, 2 dans le `.drawio`, toutes du cartouche | Rien d'autre n'a bougé |
| `xml.etree.ElementTree.fromstring` sur les deux fichiers | Les deux restent du XML valide |
| Capture du cartouche dans Chrome sans interface, avant et après | La phrase tient en 3 lignes dans le cadre de 190 px, comme avant |
| Recherche des caractères `Cc` et `Cf` dans les trois fichiers : 0 | Aucun caractère invisible ajouté |

## Ce que tu dois pouvoir défendre

- **« #211 dit "redessinés depuis `schema.sql`" : le modèle n'est-il pas tiré du code ? »** Le
  modèle a été conçu le 2026-10-02 par la démarche Merise (`43f71f2`). #211 l'a corrigé quand il
  n'était plus en phase avec le besoin : clips, étiquettes et entrées Zotero étaient codés, absents du
  modèle du 12/10. L'issue est un écrit daté ; la doc vivante dit la démarche.
- **« Pourquoi garder les renvois aux lignes de `schema.sql` ? »** Ils relient chaque élément du
  modèle à son code, au commit `d540499` : on vérifie qu'un élément conçu est bien codé, et où.
- **« Pourquoi ne pas avoir réexporté l'image ? »** Le réexport par la version installée de draw.io
  change le rendu en mode sombre de toute l'image : hors du sujet de la PR.
- **« Comment sait-on que l'image se rouvre juste dans draw.io ? »** La copie compressée a été
  décompressée et comparée au `.drawio`, nœud par nœud.

## Zones non vérifiées

- L'ordre « MCD avant MPD » le 2026-10-02 n'est pas observable dans git : le MCD, le MLD et
  `schema.sql` entrent dans le même commit, `43f71f2`. Il vient de Sabine et du message de ce commit.
- Le SVG n'a pas été rouvert dans draw.io ; seule la décompression de sa copie a été vérifiée.
- Le texte de repli n'a été vu dans aucun lecteur qui ne sait pas afficher un `<foreignObject>` : sa
  coupe en caractères est une approximation de celle de draw.io, en pixels.

## Ce qui reste

- Les écrits datés qui disent le modèle redessiné « depuis le schéma » (issue #211, note
  [du 2026-10-20](2026-10-20-redessiner-le-modele-merise-depuis-le-schema.md)) restent tels quels :
  ils racontent ce qui a été fait ce jour-là.
