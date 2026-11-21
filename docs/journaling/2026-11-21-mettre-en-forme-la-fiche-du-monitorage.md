# Mettre en forme la fiche du monitorage, et y relever le réimport et la production

- Date : 2026-11-21
- Branche : `docs/monitoring-sheet-accede-format`
- Issues : #669 (la mise en forme), #621 (le réimport et une série de la production), #167 (sa part pour cette fiche)
- Fichiers principaux : `documentation/monitoring_pour_docu.md`, `documentation/accessibilite_pour_docu.md`,
  `tests/test_grafana_files.py`, `documentation/integration_continue_pour_docu.md` (une ligne)
- Série : [mettre en forme les fiches restantes](2026-11-18-mettre-en-forme-les-fiches-restantes.md) (#646), et
  [restituer les métriques du modèle et alerter](2026-11-08-restituer-les-metriques-du-modele-et-alerter.md) (#164)

Les commits de cette PR sont `a0238062` et `d46188c6`, plus celui de cette note, sur `main` à `54ba488c`. Les autres
commits de la liste fournie à la note sont déjà sur `main` (#662, #665, #664) et ont leurs propres notes.

## Le pourquoi

La fiche du monitorage était la seule page du site de la documentation hors de la vérification selon la notice
d'accessibilité éditoriale d'AcceDe Web. La fiche de l'accessibilité le disait, en limite. Ses listes étaient en
retrait de deux ou trois espaces, ce que Python-Markdown rend mal. Elle avait trois renvois de position (« ci-dessus »,
« plus bas ») et des citations sans balise `q`. Sans elle, le critère « documentation dans un format accessible »
d'E3 ne reposait, pour cette fiche, que sur le passage de WAVE du 19/11.

La fiche disait aussi deux choses fausses au 21/11 :
- les trois noms de la durée d'une demande étaient dits « pas encore relevés » ;
- la pile devait encore être réimportée (« À réimporter »).

Sabine a réimporté le 18/11, et la production envoie ses mesures. La relecture a trouvé d'autres passages dépassés,
de même nature. Le job des fiches de veille, `caj-kb-digest-watch`, était dit absent d'`infra/`, sous un « [WIP #423] »
que le jury aurait lu. Le site `ca-kb-web` manquait parmi ce qui écrit dans `log-kb`.

## Le comment

### Les compétences dans un encadré, en blocs de citation

```markdown
!!! note "Compétences de la certification"

    > Rédaction de la documentation utilisateur, pour l'utilisation du monitorage.

    — C11
```

`documentation/monitoring_pour_docu.md:3-16`. C'est la forme des dix autres fiches. L'intitulé du référentiel est une
citation : un `blockquote`, et non un « » tapé (règle 6.1 de la notice, RGAA 9.4). Sa source, le code de la
compétence, vient après le bloc et non dedans. L'encadré vient de l'extension `admonition` (`mkdocs.yml`).

### Le tri des guillemets, paire par paire

Sur les 40 paires de « » de la fiche, 8 sont devenues des citations : les trois intitulés en blocs, et cinq `q`. Ce
sont les deux mots de la grille de Sabine, le sujet d'un e-mail de Grafana, un message d'`az`, et une phrase
d'`infra/README.md`.

```markdown
grille de Sabine du 2026-10-15: <q>100 % de schémas valides après une nouvelle tentative</q>
```

`documentation/monitoring_pour_docu.md:43`. Ces mots sont dans le journal ADR, mot pour mot (vérifié). Quatre autres
paires sont devenues des liens nommés, à la place des renvois de position. Les 28 de la première mise en forme
entourent un titre, un libellé d'interface (« NORMAL ») ou un mot dont on parle (« non trouvés ») : ce ne sont pas des
citations. Les sections du réimport et de la production en ajoutent six, de mêmes sortes, et le « Installer »
de l'ancien « À réimporter » devient un lien : 33 paires en tout.

### Les libellés anglais de Grafana

```markdown
1. **Le tableau**: <span lang="en">**Dashboards**, **New**, **Import**, **Upload dashboard JSON file**</span>, le
    fichier `observability/grafana/dashboard.json`.
```

`documentation/monitoring_pour_docu.md:91-92`. Un `span` couvre tout un chemin de menu : Python-Markdown lit le gras à
l'intérieur d'une balise en ligne, ce que le HTML construit montre (`<span lang="en"><strong>Dashboards</strong>,…`).
Le retrait de quatre espaces rattache la suite de la ligne, et la liste imbriquée de l'étape 2, à son point.

### Le réimport et la production, prouvés par une lecture datée

Le relevé de la production du 2026-11-19 tient à deux sources. Un export PDF du tableau donne les valeurs ; il ne
montre pas l'environnement choisi. La lecture de Sabine dans Explore, le 2026-11-21, le donne. Ce jour-là,
`k_b_llm_calls_total` n'a que des séries `production`, et leurs appels par étape (4, 1, 9 et 5) sont ceux de l'export.

```markdown
| `KbModelLowFidelity` | < 95 % (provisoire) | 99,4 % | NORMAL |
```

`documentation/monitoring_pour_docu.md:201`. Une première lecture semblait montrer des séries sans environnement. La
légende « Auto » de Grafana masque les étiquettes communes à toutes les séries (documentation de Grafana v13.3.0, par
Context7). La légende « Verbose » a montré `deployment_environment_name="production"`. L'étiquette vient d'un
attribut de ressource, `deployment.environment.name` (`src/k_b/ai_api/connectors/metrics_export.py:227`), que Grafana
Cloud promeut d'office en étiquette.

### Le test : trois noms passent dans l'ensemble des noms vus

```python
NAMES_SEEN_IN_GRAFANA = {
    ...
    "k_b_request_duration_seconds_bucket",
    "k_b_request_duration_seconds_count",
    "k_b_request_duration_seconds_sum",
}
```

`tests/test_grafana_files.py:26-55`, et l'assertion `:202`, `read_emitted_names() == NAMES_SEEN_IN_GRAFANA`. Le test
compare les noms que K-B émet, convertis comme Grafana Cloud le fait, à ceux que Grafana a montrés. Tant que les trois
noms n'étaient pas lus, ils vivaient dans un ensemble à part, `NAMES_NOT_SEEN_IN_GRAFANA_YET`. La lecture du 21/11 les
fait entrer dans l'ensemble vu, et l'ensemble à part disparaît. Le commentaire date chaque lecture.

### Des renvois à deux commits, chacun nommé

La section des journaux est écrite d'après `main` au commit `33fa59c`. Ce qui y est ajouté le 21/11 (le site, le job
des fiches de veille) l'est d'après `54ba488c`, et chaque renvoi nouveau le dit :

```markdown
le site, `ca-kb-web`
(au commit `54ba488c`: `infra/main.bicep:79`, `:349-354`), et les quatre jobs:
```

`documentation/monitoring_pour_docu.md:390-391`. Le tampon de la section le dit aussi. Les anciens renvois restent
justes à leur commit : `infra/README.md:310`, par exemple, est la ligne citée à `33fa59c`, et non sur `main`.

## Choix faits et options écartées

- **La mise en forme avant #620 et #621**, et non après comme le disait la fiche de l'accessibilité. Choix du Second :
  #620 attend une séance de Sabine dans Grafana. Écarté : attendre, ce qui bloquait la partie 6 de C11.
- **« Dessous » gardé** pour décrire la place d'une courbe dans le tableau de Grafana. Un premier passage l'avait
  changé en « Puis ». La relecture a montré que « Puis » changeait l'information : les courbes forment la rangée
  suivante, elles ne suivent pas chacune son panneau. Un mot qui décrit une interface et nomme l'élément n'est pas un
  renvoi de position de la fiche (règle 6.3).
- **Les renvois de code laissés en code** (`docs/fiches-veille.md`), un seul fichier devenu un lien (l'essai
  d'accessibilité de Grafana Cloud, `docs/accessibilité_pour_docu.md`), pour ne pas le confondre avec la fiche du
  site. Les autres fiches mêlent les deux formes.
- **« Explore » sans balise anglaise** : un nom de fonction de Grafana, comme dans la fiche des tests.
- **Jamais « première série de la production »** : le dernier commentaire de #522 relève des séries de la production
  dès le 2026-11-11. La section s'appelle « Relevé de la production du 2026-11-19 ».
- **Deux limites retirées, et non reformulées** : l'export de la production (#522 est fermée, la production est
  relevée) et le job des fiches de veille (déclaré dans `infra/`). Ce ne sont plus des limites.
- **Le site ajouté au tableau des journaux** : `kb serve-web` écrit par le même journal que les deux API. Il a le même
  logger, son propre fichier par `LOG_FILE_PATH_BY_COMMAND` (`src/k_b/cli.py:72-76`), et le même `log_request`
  (`src/k_b/web/app.py:64`). Tri du Second : une ligne de plus, sans issue à part.
- **Le label `E3` non posé sur #669** : l'outil a refusé la création avec lui, et le `MEMORY.md` de K-B réserve les
  labels de livrable à time-knight.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run --locked --only-group docs mkdocs build --strict` : aucun avertissement | les six ancres nouvelles et les liens se résolvent |
| le contrôle du HTML construit (script hors du dépôt) : 0 constat sur la fiche, hors « au-dessus de 0 % », des seuils | un titre de niveau 1, aucun saut, des tableaux à `th`, aucun lien vague, aucune ressource externe, aucun `br` ni `title` |
| `grep -cE "ci-dessus\|plus bas\|ci-dessous" documentation/monitoring_pour_docu.md` → 0 | les renvois de position sont partis |
| la comparaison mot à mot de la fiche, de `main` à `a0238062`, balises retirées | la mise en forme n'a changé aucun fait |
| `uv run pytest` : 5664 passed ; `tests/test_grafana_files.py` : 17 passed | les noms émis sont les 25 noms vus |
| `uv run ruff check --no-cache .`, `ruff format --check .`, `mypy --strict src` : verts | les contrôles du dépôt |
| la lecture de Sabine dans Explore, le 2026-11-21 entre 02:27 et 02:38 UTC | les trois noms de la durée existent, en production, le 19/11 |
| aucune espace avant « : » ni « ; » dans `documentation/`, aucun caractère Cc ni Cf | la règle de typographie de Sabine |

## Ce que tu dois pouvoir défendre

1. **Pourquoi certains « » restent-ils ?** Ils entourent un titre, un libellé d'interface ou un mot dont on parle, pas
   les mots d'une source. La règle est dans la fiche de l'accessibilité, « Des citations déclarées », et chaque paire
   a été triée.
2. **Comment savez-vous que l'export du 19/11 est celui de la production ?** L'export ne le montre pas. Explore, sur la
   même journée, ne trouve que des séries `production`, et leurs appels par étape sont ceux de l'export
   (`documentation/monitoring_pour_docu.md:209-218`).
3. **Le test a changé : que prouve-t-il maintenant ?** Que chaque nom que K-B émet a été vu dans Grafana. Il échouerait
   sur un instrument nouveau tant que son nom n'est pas lu et ajouté (`tests/test_grafana_files.py:201-202`).
4. **Pourquoi deux commits de référence dans une même section ?** La section a été écrite et relue à `33fa59c`. Ce qui
   s'ajoute le 21/11 est vérifié à `54ba488c`, et le dit à chaque renvoi : un renvoi doit se relire au commit qu'il
   nomme.
5. **Le site est-il vraiment dans `log-kb` ?** Oui : `ca-kb-web` est créé dans l'environnement `cae-kb`
   (`infra/main.bicep:349-354`), dont le paramètre de diagnostic envoie la sortie des conteneurs à `log-kb`.

## Zones non vérifiées

- Le rendu au lecteur d'écran : non essayé (limite déjà écrite dans la fiche de l'accessibilité).
- Le passage WAVE et Tab de Sabine sur la fiche construite : à faire avant la fusion, écrit dans la PR.
- Le sujet de l'e-mail de Grafana et le message d'`az`, recopiés en `q` : leurs sources ne sont pas dans le dépôt,
  leur mot pour mot n'est pas revérifié.
- Les renvois `fichier:ligne` antérieurs à la PR (`src/…`, `README.md`, `docs/registre-traitements.md`) : non relus,
  sauf les deux ajoutés.
- L'export PDF du 19/11 : lu par le Second, pas par cette session.

## Ce qui reste

- #620 : l'étape qui branche l'export des mesures, sur la branche de la piste C, à rebaser après cette fusion et à
  écrire selon la même notice.
- #589 : l'essai d'accessibilité du tableau de Grafana (`docs/accessibilité_pour_docu.md`, à venir).
- La note datée du 18/11 (`docs/journaling/2026-11-18-passer-k-b-a-gpt-6-1-sol.md:141`) cite encore
  `NAMES_NOT_SEEN_IN_GRAFANA_YET` : une note dit l'état de son jour, elle reste telle quelle.
