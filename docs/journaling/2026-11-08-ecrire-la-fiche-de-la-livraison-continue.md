# Écrire la fiche de la livraison continue, avec le test de la livraison

- Date : 2026-11-08
- Branche : `docs/continuous-delivery-sheet`
- Issue : #509
- Fichiers principaux : `documentation/livraison_continue_pour_docu.md` (neuf), `documentation/tests_pour_docu.md`
  (typographie, choix 30)
- Série : la note [2026-11-06-deployer-une-version-taguee-par-oidc.md](2026-11-06-deployer-une-version-taguee-par-oidc.md)
  explique le code de la chaîne (#415) ; celle-ci en fait une fiche, vérifiée contre `main` et contre GitHub.

## Le pourquoi

Le référentiel demande, pour la chaîne de livraison continue, une documentation de son installation et de son test,
une documentation pour qui la déclenche, et une documentation de la procédure : outils, configurations, exécution,
débug (C13, C19). Jusqu'ici, le test de la livraison n'était écrit que dans une note datée, et les étapes se lisaient
entre `infra/README.md` et le README. Décision de Sabine du 08/11 : chaque documentation demandée devient une fiche
neuve de `documentation/`, écrite d'après le code, sans toucher à `docs/`.

## Le comment

### La chaîne, lue dans le workflow et non dans les notes

`.github/workflows/deploy.yml:69-72` :

```yaml
  deploy:
    needs: check
    runs-on: ubuntu-latest
    environment: production
```

Tout part de ces deux jobs. `check` tourne sans droit sur Azure ; `deploy` ne tourne qu'après lui, dans
l'environnement `production`, le seul dont `id-kb-deploy` accepte les jetons. La fiche décrit chaque étape par son
nom exact dans le workflow, et par la ligne qu'elle écrit (`documentation/livraison_continue_pour_docu.md:75-85`) :
c'est ce que la personne qui livre lit dans `gh run watch`.

### Ce qui a déjà changé quand une étape échoue

`.github/workflows/deploy.yml:143-144` :

```bash
            az containerapp job update -n "$job" -g "$RG" --container-name kb --image "$DEPLOYED_IMAGE" -o none
            execution=$(az containerapp job start -n "$job" -g "$RG" --query name -o tsv)
```

`run_job` met le job à l'image du tag **avant** de le lancer. Donc, dès l'étape de migration,
`caj-kb-migrate-database` est à la nouvelle image, même si la migration échoue. Le premier jet du tableau « Quand une
livraison échoue » l'oubliait ; la relecture l'a trouvé (`livraison_continue_pour_docu.md:278`). C'est la partie
« débug » : rien ne revient tout seul, il faut savoir ce qui est déjà en ligne pour choisir entre revenir au tag
précédent et livrer une version corrigée.

### Le test de la chaîne : vu ou simulé

`documentation/livraison_continue_pour_docu.md:216` et `:221` (extraits) :

```text
| un tag sur la tête d'une branche | … | vu le 2026-11-06, exécution 42289900589: …
| un tag supprimé puis recréé sur un autre commit | … | non essayé; la lecture du label et du « not found » l'est …
```

Chaque refus attendu dit d'où vient sa preuve : une exécution réelle de GitHub, relue par `gh run view --log`, ou un
essai de la session de #415 consigné dans sa note, avec de faux `az` et `gh`. Un refus qu'aucun essai ne montre est
écrit « non essayé ». La livraison témoin `v0.1.0` (exécution 42429577646) donne ensuite la ligne de résultat de chaque
étape de `deploy`, avec son heure, toutes relues dans le journal de l'exécution.

### Le choix 30 : aucune espace avant « : » et « ; » dans `documentation/`

Règle de Sabine du 08/11 : dans les fiches de `documentation/`, aucune espace avant « : » ni « ; », hors code et hors
textes d'interface ; elle vaut aussi pour les citations du référentiel (l'en-tête de C19). La correction s'est faite
par un script, sur le texte hors blocs de code et hors code en ligne, et non à la main : 93 occurrences dans
`tests_pour_docu.md`, et toutes celles de la fiche neuve. Le même commit retire de `tests_pour_docu.md:95` un renvoi à
`MEMORY.md`, la mémoire des sessions, qui n'est pas une documentation : la fiche dit le fait elle-même.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Les commandes de création (rulesets, environnement, secrets) renvoient à `infra/README.md` (plan validé par Sabine) | une seule copie des commandes ; la fiche donne l'ordre, le rôle de chaque pièce et les commandes de vérification | les recopier : deux copies finiraient par diverger |
| La CI n'est décrite que comme condition de `check` (plan) | son détail est la fiche de l'intégration continue (#508) | la décrire ici : deux fiches pour la même chose |
| La visibilité du dépôt n'est pas écrite (correction de Sabine au plan) | c'est un état du moment, pas un fait du code | l'écrire dans les limites |
| Les limites datées du 2026-11-08, lues par `gh api` (plan) | l'environnement `production` peut changer sans commit | les présenter comme définitives |
| L'en-tête de C19 sans espace avant « : » (Sabine, 08/11) | sa règle vaut pour les citations du référentiel ; seuls les textes d'interface gardent leur typographie | le mot pour mot avec l'espace (la proposition de la session) |
| Les 13 constats de la relecture, puis les 3 de la seconde, triés par time-knight (délégation de Sabine du 15/10) | 14 corrigés, 2 écartés (l'en-tête, déjà tranché par Sabine ; un commentaire dans un bloc de code, hors de la règle) | — |

## Preuve

| Sortie observée | Ce que ça démontre |
|---|---|
| `gh run view 42429577646 --log` : `v0.1.0: sha256:37c6d42b…`, `caj-kb-migrate-database: Succeeded`, `the latest revision of each app is ready at v0.1.0 …`, `caj-kb-smoke-test: Succeeded` | chaque étape de `deploy` a tourné sur Azure, dans l'ordre de la fiche |
| `gh run view 42289900589 --log` : `v0.0.1 is not on main: 80d1327e…`, `deploy` `skipped` | le refus d'un tag hors de `main`, vu sur une exécution réelle |
| `gh api …/environments/production` : une règle `branch_policy`, `can_admins_bypass: true` ; `…/deployment-branch-policies` : `["v*.*.*","tag"]` | la limite « aucune validation humaine » et la règle des tags, lues le 08/11 |
| `gh api …/rulesets` : « tags v » (contournement `actor_id 5`) et « tags v immuables » (aucun), `active` | le verrou des tags décrit par la fiche |
| Script de normalisation appliqué à la version de `main` de `tests_pour_docu.md`, puis `diff` avec la branche : seule la ligne 95 diffère | le commit `de23533` ne change que les espaces et le renvoi à `MEMORY.md` |
| Hors blocs de code, `grep -cE "[^ ] [:;]( |$)"` → 0 dans les deux fiches ; aucun caractère `Cc` ou `Cf` ; les 5 liens relatifs ouvrent un fichier ; `git diff --stat origin/main -- README.md` vide, et dans `docs/` seule cette note est ajoutée | les contrôles du plan |
| Deux relectures par des sous-agents neufs, en lecture seule (13 puis 3 constats) | chaque fait revérifié contre `b412323` et GitHub |

## Ce que tu dois pouvoir défendre

1. **Comment sais-tu que chaque étape a été testée ?** Par la livraison `v0.1.0` : son journal donne la ligne de
   résultat de chaque étape, avec son heure (`livraison_continue_pour_docu.md:228-257`). Les refus, eux, sont dits
   « vu », « simulé » ou « non essayé », un par un.
2. **Que fait une personne dont la livraison échoue ?** Elle lit l'étape en échec (`gh run view <id> --log-failed`),
   regarde dans le tableau ce qui est déjà en ligne, puis revient au tag précédent ou livre une version corrigée
   (`livraison_continue_pour_docu.md:259-280`).
3. **Pourquoi la fiche renvoie-t-elle à `infra/README.md` pour installer ?** Pour ne garder qu'une copie des
   commandes. La fiche garde l'ordre, ce que fait chaque pièce, et les commandes qui vérifient l'installation.
4. **Qui peut déclencher une livraison ?** Une administratrice du dépôt, seule à pouvoir créer un tag `v*`, et aucune
   validation humaine ne suit encore (limites, lues le 08/11).

## Zones non vérifiées

- `az identity federated-credential list` n'a pas été lancé pour cette fiche (aucun accès Azure de la session) : le
  sujet attendu vient du Bicep, et la connexion OIDC de `v0.1.0` l'a utilisé.
- Les refus simulés (format du tag, CI, révisions, `run_job`) ne sont prouvés que par les essais de la session de
  #415, consignés dans sa note : aucun n'a été rejoué ici.
- Le ruleset « tags v » n'a jamais été essayé par un compte qui n'est pas administrateur.

## Ce qui reste

- L'étape d'`infra/README.md` qui fait de Sabine la validatrice de chaque livraison n'est pas appliquée : la fiche le
  dit dans ses limites, et sera à reprendre quand elle le sera.
- Le commentaire de `deploy.yml:79-80` ne nomme pas `jq` parmi les sorties des commandes `az` : un défaut du code, hors
  de cette mission, que time-knight fait porter par une issue.
- Les jobs `caj-kb-daily-routine` et `caj-kb-digest-watch` ne sont pas livrés par la chaîne : à ajouter à la fiche quand
  ils entreront dans `infra/` et `deployment.json`.
