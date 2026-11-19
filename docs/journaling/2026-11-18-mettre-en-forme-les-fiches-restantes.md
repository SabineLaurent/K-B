# Mettre en forme les fiches restantes, et déclarer les citations

- Date : 2026-11-18
- Branche : `docs/accessible-sheets-part-2`
- Issues : #167 (part « documentation »), #623 (en partie)
- Fichiers principaux : `documentation/stylesheets/extra.css`, les fiches de `documentation/` sauf le monitorage,
  `documentation/accessibilite_pour_docu.md`
- Série : [publier les fiches en site accessible](2026-11-18-publier-les-fiches-en-site-accessible.md) (la PR A,
  #637)

Les commits de cette PR vont de `24ef3bc6` à `39ff1b9e`, sur `main` à `fd956430`. Les commits plus anciens de la
liste fournie à la note (#637, #636) ont leurs propres notes.

## Le pourquoi

La PR A a fait des fiches un site, et en a mis quatre en forme. Six restaient : tests, livraison continue, import et
base, API IA, architecture, installation. Leurs listes étaient mal rendues, leurs schémas et leurs tableaux sans phrase
d'annonce, et plusieurs passages décrivaient un état que `main` avait dépassé (#623). La règle 6.1 de la notice
éditoriale d'AcceDe Web, « Déclarer les citations en ligne et les blocs de citations », était écrite « non tenue » dans
toutes les fiches. Enfin, la relecture du 11/11 avait relevé, dans l'architecture et l'installation, des
renvois glissés, un état en ligne faux et des cellules surchargées.

## Le comment

### Une citation en ligne est un `q`, et la feuille de style dessine ses guillemets

```css
.md-typeset q {
  quotes: "« " " »";
}
```

`documentation/stylesheets/extra.css:14-16`. Un `<q>` déclare la citation au lecteur d'écran (RGAA 9.4). Le navigateur
dessine lui-même ses guillemets : sans cette règle, il prendrait ceux de la langue héritée (valeur `auto`, page MDN de
`quotes`, lue le 2026-11-18). La règle fixe les guillemets français, avec l'espace U+0020 des « » tapés
ailleurs : le rendu est le même, vu dans Chrome sans interface. Une citation s'écrit donc sans guillemets tapés,
sinon ils seraient doublés :

```html
mais <q lang="en">Pull request authors cannot approve their own pull requests</q>: avec une seule
```

`documentation/integration_continue_pour_docu.md:429`. `lang="en"` remplace le `<span lang="en">` qui l'entourait.

### Le tri des guillemets : citation ou pas

Une citation, ce sont les mots d'une source recopiés : une phrase de Microsoft Learn, un message du portail, la
phrase d'une page. Le titre cité d'une section ou d'un document, un mot dont on parle et un libellé d'interface ne
sont pas des citations : ils gardent leurs « ». Le tri s'est fait paire par paire. Sur les 291 paires de `main`, 26
sont devenues des `<q>`, dont 19 dans la fiche du service d'IA, qui cite le plus Microsoft. La règle est écrite dans
la fiche d'accessibilité (« Des citations déclarées »).

### L'intitulé du référentiel en bloc de citation

```markdown
> Rédaction de la documentation technique.

— C17
```

`documentation/architecture_pour_docu.md:3-5`. L'intitulé est une citation du référentiel. Sa source, le code de la
compétence, va après le bloc et non dedans : un `blockquote` ne porte que la citation. La convention de Sabine
(intitulé, puis code) est gardée.

### La forme des six fiches

Ce sont les règles de la PR A : listes en retrait de quatre espaces, un seul titre de niveau 1, une phrase avant
chaque tableau et chaque schéma, `accTitle` et `accDescr` dans chacun des huit schémas, liens qui nomment leur
cible, aucun « plus haut » ni « ci-dessous ». Deux pièges de Python-Markdown sont apparus :

- une ligne qui commence par `#162 (` devient un titre de niveau 1 : la fiche du monitorage avait ainsi deux titres
  de niveau 1 (corrigé en repliant la ligne) ;
- une liste numérotée qui commence à 0 s'affiche à partir de 1. Dans la fiche de l'import, les étapes « 0. à 9. »
  s'affichaient « 1. à 10. », et « l'étape 3 » ne visait plus la bonne. Le point 0 est devenu un paragraphe,
  « **Avant la première étape, la base et l'instant.** » (`documentation/import_et_base_pour_docu.md:271`).

### Un seul tampon pour l'architecture et l'API IA

L'architecture mêlait six commits de référence ; l'API IA en mêlait deux. Les deux fiches disent maintenant
« d'après `main` au commit `fd956430` », et chacun de leurs renvois `fichier:ligne` a été repointé sur ce commit :
291 pour l'architecture, 145 pour l'API IA. Un script (hors du dépôt) cherche le bloc cité à l'ancien commit dans le
fichier du nouveau. Ce qu'il ne retrouve pas se relit à la main. L'import garde son tampon `94e3f4e` : ses 231 renvois
y sont justes. Les tests et la livraison prolongent le leur pour les seuls passages remis à jour.

## Choix faits et options écartées

- **Des guillemets dessinés par la feuille de style.** Écarté : garder les « » tapés autour d'un `q` dont on
  retire les guillemets (`content: none`). Sans feuille de style, les guillemets seraient doublés.
- **Lue sur GitHub, une citation garde son `q`** (`gh api markdown`), mais pas la feuille de style du site : les
  guillemets y seraient ceux de l'anglais. C'est écrit en limite ; le format de remise est le site.
- **Le bloc de citation pour l'intitulé du référentiel**, plutôt qu'un `q` : il est seul sur sa ligne, en tête de
  fiche.
- **Les quatre routes du client `WEB` hors du tableau** des deux API (relecture n° 1) : la cellule « Routes » portait
  huit routes et onze renvois, le défaut que visait le constat 10 de la relecture du 11/11.
- **Écarts acceptés par time-knight** : l'architecture décrit la lecture du conteneur `watch` par l'API de données
  (#559, #560), code de `fd956430` qu'elle omettait ; le constat d'échec du test de l'export (#495, fermée) est résumé
  en une phrase datée ; la liste de l'import commence à 1.
- **Le registre et deux spécifications**, à la demande de time-knight : le site ne montre pas encore les comptes
  rendus de veille (`docs/registre-traitements.md`, lignes « Destinataires » et « Site privé »), et une échéance
  passée est remplacée par « plus tard » dans le registre, `infra/README.md` et `docs/tendances.md`.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run --locked --only-group docs mkdocs build --strict` : aucun avertissement | aucun lien ni ancre cassés |
| le contrôle du HTML construit : 0 constat sur les dix pages mises en forme | un titre de niveau 1, aucun saut, des tableaux à `th`, aucun lien vague, aucune ressource externe |
| dans le HTML : 26 `q`, un `blockquote` ou plus par fiche, aucun `q` qui contienne un « tapé | la règle 6.1 est tenue, sans guillemets doublés |
| capture de Chrome sans interface de la page d'accueil et de la fiche d'accessibilité | un `q` s'affiche « comme ceci », comme les « » tapés ; le bloc de citation est lisible |
| `gh pr checks 637` : `deploy` à `skipping`, neuf autres à `pass` | une PR reçoit dix contrôles |
| aucune espace avant « : » ni « ; » dans `documentation/`, aucun caractère Cc ni Cf | la règle de typographie de Sabine |

## Ce que tu dois pouvoir défendre

1. **Pourquoi `<q>` et pas des guillemets ?** Un lecteur d'écran ne sait pas qu'un passage entre « » est une
   citation ; le `q` le déclare (RGAA 9.4, notice d'AcceDe Web 6.1). Les guillemets restent visibles, dessinés par
   la feuille de style (`extra.css:14-16`).
2. **Pourquoi certains « » restent-ils ?** Ils n'entourent pas une citation : un titre de section, un mot dont on
   parle, un libellé d'interface. La règle est écrite dans la fiche d'accessibilité, et chaque paire a été triée.
3. **Comment savez-vous que les renvois de l'architecture sont justes ?** Chacun a été repointé sur `fd956430`, puis
   la relecture neuve n° 1 en a relu environ 110 en détail ; deux renvois mal rattachés ont été trouvés et corrigés.
4. **Pourquoi l'import garde-t-il un ancien commit ?** Ses renvois sont justes à `94e3f4e`, et le code de l'import n'a
   pas changé ce qu'il décrit ; un tampon ne fige pas une fiche, il dit à quel code elle se lit.

## Zones non vérifiées

- Le rendu au lecteur d'écran (VoiceOver) : non essayé.
- Les guillemets d'un `q` lu sur GitHub : déduits de la propriété `quotes`, non vus.
- L'état en ligne (le modèle que l'API IA appelle, les ressources déclarées dans le Bicep) : non relu, aucune commande
  `az`.
- Le test de bout en bout de l'export n'a pas été relancé depuis le 2026-11-09.

## Ce qui reste

- La fiche du monitorage (forme, citations, trois renvois de position), après les PR de #620 et #621.
- #623 se ferme par la dernière fusionnée de cette PR et de celle de #620 et #621, qui porte le passage du
  monitorage.
- #641 : ne plus faire dépendre le build de `Docs` d'une version de Mermaid qui bouge.
- La publication sur Pages, après la mise en public du dépôt.
