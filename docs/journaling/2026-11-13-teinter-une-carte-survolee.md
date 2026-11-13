# Teinter une carte du fil survolée

- **Date** : 2026-11-13
- **Branche** : `fix/card-hover`, commit `483f204`, partie d'`origin/main` à `eef28b2` (#607)
- **Issue** : #605
- **Série** : suite d'[Aligner le fil sur ses maquettes](2026-11-11-aligner-le-fil-sur-ses-maquettes.md) (#587)
  et d'[Afficher le détail d'un item](2026-11-12-afficher-le-detail-d-un-item.md) (#564)
- **Fichiers principaux** : `src/k_b/web/static/site.css`, `tests/web/test_stylesheet.py`.

La liste des commits donnée à la note compte aussi ceux de #564 (`e5ce50b` à `02e5b6d`) : ils sont entrés dans
`main` par la fusion de #601 (`5bbe3ce`), et la note du 12/11 les couvre.

## Le pourquoi

La maquette du fil sur ordinateur, version (c) du 09/11, montre sa première carte survolée, sur un fond teinté ; sa
légende dit « la première carte est survolée ». Sur `main`, une carte ne changeait pas au survol : seuls ses liens
changeaient de couleur. Sabine a décidé le 12/11 que le site suit la maquette, et la démo vidéo de l'oral montre le
fil en ligne. La teinte dit à l'opératrice quelle carte est sous sa souris. Au clavier, elle dit dans quelle carte
est le lien qui a le focus.

## Le comment

### 1. Une couleur de plus dans la charte

```css
    /* A card under the pointer (Maquettes-fil.dc.html, version (c)). */
    --color-card-hover: #E6F0F1;
```

`src/k_b/web/static/site.css:43-44`. La teinte est une propriété personnalisée de `:root`, comme les autres
couleurs. Le test des contrastes (`CUSTOM_PROPERTY`, `tests/web/test_stylesheet.py:11`) ne lit que ces propriétés :
une couleur écrite en dur dans une règle lui échapperait.

### 2. Le survol et le focus dans la même règle

```css
    &:hover,
    &:focus-within {
      background: var(--color-card-hover);
    }
```

`src/k_b/web/static/site.css:616-619`, imbriquée dans `.card`, comme le `&:hover` de `.card-title a` et de
`.card-link`. Deux états, un seul fond :
- `:hover` : la carte est sous le pointeur ;
- `:focus-within` : un élément de la carte, ici le lien du titre ou le lien vers la source, a le focus.

Sans le second, l'indice ne serait donné qu'à la souris. L'anneau de focus (`:focus-visible`, `site.css:54-55`)
reste la marque du lien lui-même ; la teinte montre sa carte.

### 3. Les contrastes sur la teinte

```python
    ("--color-ink", "--color-card-hover", 4.5),
    ("--color-slate", "--color-card-hover", 4.5),
    ("--color-teal", "--color-card-hover", 4.5),
    ("--color-teal-deep", "--color-card-hover", 4.5),
```

`tests/web/test_stylesheet.py:39-42`. Ce sont les quatre couleurs de texte d'une carte :
- l'encre : la sorte et son cadre ;
- l'ardoise : la date, les identifiants et les liens visités ;
- le bleu canard : les liens ;
- le bleu canard foncé : un lien survolé.

Le test calcule la luminance relative de WCAG 2.1 et exige 4,5:1 (critère 1.4.3). Il mesure 14,4:1, 7,11:1, 6,39:1
et 9,43:1. La pastille « Exploitée (KEV) » garde son propre fond, sans changement. L'anneau de focus en bleu
canard, un composant, n'exige que 3:1 (1.4.11) : 6,39:1 le couvre.

## Choix faits et options écartées

- **`:focus-within`, retenu**, pour que le clavier ait le même indice que la souris. Écarté :
  - le survol seul, qui laisse le clavier sans indice ;
  - `:has(:focus-visible)`, qui ne teinterait pas la carte après un clic. Cette option est écartée sans
    vérification de sa prise en charge par les navigateurs : `:focus-within` suffit au besoin, et il est plus
    simple.
- **La teinte de la maquette, sans retouche** : #E6F0F1 tient les quatre contrastes, rien n'obligeait à
  l'assombrir.
- **Pas de transition** : la maquette n'en montre pas, et une animation demanderait de respecter
  `prefers-reduced-motion`.
- **Ni ADR ni relecteur** : l'issue est de taille XS et suit la maquette sans s'en écarter. time-knight lit le
  diff (consigne de tn-orchestrateur).

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_a_card_takes_the_tint_of_its_mockup_under_the_pointer_or_the_focus`, rouge avant le CSS (le bloc `&:hover, &:focus-within` manquait), vert après | la règle existe dans `.card` et vaut #E6F0F1 |
| `test_each_pair_of_the_chart_has_its_contrast`, quatre paires rouges avant (`KeyError` sur `--color-card-hover`), vertes après | chaque texte d'une carte tient 4,5:1 sur la teinte |
| Capture de la maquette, `Maquettage - 3) Maquettes du fil de veille@2x.png` : #E6F0F1 sur 141 099 pixels, sur un échantillon d'un pixel sur quatre ; la boîte de la teinte couvre la première carte de la version (c) | la teinte est celle de la maquette, lue sur l'image |
| Chrome sans interface, 1280 px, CDP : `Input.dispatchMouseEvent` sur la première carte | fond `rgb(230, 240, 241)` sur elle seule, `:hover` vrai, retour au blanc quand la souris s'en va |
| Même page, Tab jusqu'au titre de la deuxième carte (19 appuis) | fond `rgb(230, 240, 241)` sur la deuxième carte seule, `:focus-visible` vrai, anneau visible sur la teinte |
| `uv run pytest` : 5124 passed ; ruff `--no-cache`, format, `mypy --strict` verts | rien d'autre n'a bougé |

## Ce que tu dois pouvoir défendre

- **Pourquoi aussi au focus ?** Aucun critère ne l'exige : le focus visible (WCAG 2.4.7) est déjà tenu par
  l'anneau. C'est un choix d'égalité : ce que la souris montre, le clavier le montre aussi. La teinte situe le
  lien qui a le focus dans sa carte (`site.css:617`).
- **La teinte gêne-t-elle la lecture ?** Non : quatre contrastes mesurés par un test, le plus faible à 6,39:1, au-dessus
  des 4,5:1 exigés (`test_stylesheet.py:39-42`).
- **Pourquoi une variable et pas `#E6F0F1` dans la règle ?** Le test des contrastes ne lit que les propriétés de
  `:root`. Une couleur en dur échapperait à la preuve (`site.css:44`).
- **Et si Windows force ses couleurs ?** Le navigateur remplace alors les fonds, et la teinte disparaît. Il reste
  l'anneau de focus et le soulignement des liens : la teinte n'est qu'un indice de plus, jamais la seule marque
  d'un état.

## Zones non vérifiées

- **Les couleurs forcées de Windows** : la disparition de la teinte vient du comportement documenté du mode, mais
  elle n'a pas été observée.
- **Un écran tactile** : un toucher hors d'un lien peut laisser `:hover` sur la carte jusqu'au toucher suivant.
  Pas essayé.
- **Après un clic** sur « Lire l'article d'origine », le lien garde le focus : au retour de l'onglet, la carte
  reste teintée tant que le focus ne la quitte pas. Comportement voulu par le choix de `:focus-within`, mais pas
  montré à Sabine.

## Ce qui reste

Rien pour #605. La teinte part en ligne avec le prochain tag, que seule Sabine décide.
