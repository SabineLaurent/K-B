# Brancher l'export dans la fiche du monitorage

- Date : 2026-11-21
- Branche : `docs/monitoring-export-step`
- Issue : #620 (et le reste de #621, l'expiration du jeton de la production)
- Fichier : `documentation/monitorage.md`
- Série : [la mise en forme de la fiche (#669)](2026-11-21-mettre-en-forme-la-fiche-du-monitorage.md), [la relecture
  d'API10 depuis le jeton de la production (#611)](2026-11-20-relire-api10-depuis-le-jeton-de-production.md)

## Le pourquoi

La fiche du monitorage sert au jury de preuve pour C11 et C20 : la procédure d'installation et de configuration de
l'outillage du monitorage. Sa section « Installer » partait d'une pile Grafana Cloud qui reçoit déjà les mesures : le
branchement de l'export, lui, n'était écrit que dans `docs/fiches-veille.md` et dans `.env.example`. Un lecteur qui
suivait la fiche ne pouvait pas installer la chaîne d'un bout à l'autre. L'étape « Brancher l'export » comble cet
écart : de la pile vide jusqu'aux séries vues dans Explore, puis l'import du tableau et des règles.

Un jeton expire : la fiche dit, sous « Maintenir », où se choisit sa date d'expiration, comment un jeton expiré se
repère, et qui Grafana prévient avant.

Le 2026-11-22, avant la sortie du brouillon, trois demandes s'ajoutent (décisions de Sabine) :

- **L'encadré des compétences porte, mot pour mot, les huit phrases du référentiel** qui demandent une documentation du
  monitorage (C11 et C20, l'accessibilité comprise), et une liste rattache chacune aux sections qui y répondent
  (`documentation/monitorage.md:42-59`). Le jury lit la fiche critère par critère.
- **La fiche décrit la procédure et l'état, pas l'histoire** : dans les sections touchées, plus aucune date de
  réalisation, de relecture ou de relevé, ni le nom d'une personne : la tête, « Ce que le monitorage suit »,
  « Brancher l'export », « Installer », « Maintenir », « Journaux de l'application » et « Sources ». Une date reste
  quand la mesure en dépend : la version d'un outil, la fenêtre d'un relevé, l'heure d'une ligne de journal citée.
  Chaque seuil cite sa ligne du journal des décisions ; la tête de la fiche nomme le seul commit que visent ses renvois.
- **Les deux alertes d'Azure entrent dans la liste des seuils** (C20 : <q>la documentation liste les métriques et les
  seuils et valeurs d'alerte pour chaque métrique à risque</q>) : `budget-kb` et `alert-kb-model-tokens`, avec leurs
  chiffres lus dans le code (`documentation/monitorage.md:94-102`).
- **La section « Les arguments du choix des outils »** (C20 : <q>La documentation explicite les arguments en faveur des
  choix techniques pour l'outillage du monitorage de l'application</q>), rédigée côté time-knight et posée telle
  quelle, avec sa phrase dans l'encadré et sa puce dans la liste (`documentation/monitorage.md:104-171`).

Le parcours de l'interface par Sabine est remplacé, par sa décision, par la vérification de chaque libellé et de chaque
chemin dans la documentation officielle de Grafana Cloud.

## Le comment

### Une étape, six parties, avant « Installer »

La section est placée entre « Lire le tableau » et « Installer », car l'import du tableau suppose une pile qui reçoit
déjà les mesures. « Installer » part d'elle par un lien nommé (`documentation/monitorage.md:309`) :

```markdown
Sur la pile qui reçoit les mesures ([Brancher l'export](#brancher-lexport)), par l'interface, sans jeton ni outil à
installer.
```

Les six parties suivent l'ordre d'une installation : la pile, l'adresse et l'identifiant, le jeton, l'en-tête, les
variables, la vérification. Chaque libellé de l'interface de Grafana Cloud est en anglais, dans un
`<span lang="en">`, comme le reste de la fiche (notice d'AcceDe Web), pour qu'un lecteur d'écran le lise en anglais.

### Le jeton : une politique de la pile, trois droits d'écriture

`documentation/monitorage.md:226-238` crée la politique depuis le Grafana de la pile, et non depuis le
portail de l'organisation :

```markdown
    date (moindre privilège). Dans le Grafana de la pile, <span lang="en">**Administration**, **Users and access**,
    **Cloud access policies**, **Create access policy**</span>. Une politique créée là ne vaut que pour cette pile.
```

Chaque étape s'ouvre sur ce qu'elle produit et à quoi elle sert, puis dit comment faire (consigne de Sabine du
2026-11-22 : une fiche pédagogique). Pour le jeton : il prouve que l'envoi vient de K-B, et ses droits sont bornés à
l'écriture, sur une seule pile, jusqu'à une date.

Une politique créée là a le *realm* de la pile : ses jetons ne valent que pour elle (page « Access policies » de
Grafana, citée dans les sources). Les trois droits, `metrics:write`, `logs:write` et `traces:write`, sont ceux de
`.env.example:164` : le jeton ne fait qu'écrire, K-B ne relit rien de ce qu'il envoie. C'est le moindre privilège de
`code.md`.

### L'en-tête : un jeton qui ne passe ni par l'écran ni par l'historique

`documentation/monitorage.md:249-255` :

```sh
{
    printf 'Jeton: '; read -rs TOKEN; echo
    printf 'Authorization=Basic%%20%s' "$(printf '%s:%s' '<instance>' "$TOKEN" | base64 | tr -d '\n')" | pbcopy
    unset TOKEN
}
```

- `read -rs` lit le jeton sans l'afficher (`-s`) et sans interpréter les barres obliques inverses (`-r`).
- `printf` est une commande interne du shell : le jeton n'apparaît pas dans la liste des processus.
- `%%20` donne `%20` en sortie de `printf` : c'est l'espace de `Basic `, encodé comme le format des en-têtes OTLP
  le demande (`.env.example:161-163`) ; K-B décode chaque valeur (`src/k_b/ai_api/connectors/metrics_export.py:198-213`).
- `tr -d '\n'` retire le retour à la ligne que `base64` ajoute : il rendrait l'en-tête invalide.
- `pbcopy` met l'en-tête dans le presse-papiers ; `unset` efface la variable.
- Les accolades : sans elles, un bloc collé d'un coup dans un bash sans collage protégé (bash 3.2 de macOS) fait lire
  à `read` la ligne `printf` comme jeton. Le vrai jeton, collé ensuite à l'invite, s'afficherait et entrerait dans
  l'historique. Avec elles, le shell lit tout le groupe avant de le lancer, et `read` attend bien le jeton.
- L'invite `Jeton:` : zsh, le shell par défaut de macOS, active le collage protégé (*bracketed paste*). Le bloc collé
  y reste sur la ligne de commande jusqu'à Entrée ; un jeton collé à ce moment rejoindrait la ligne de commande,
  affiché et gardé dans l'historique. L'invite dit quand coller le jeton : seulement une fois `Jeton:` affiché, donc
  une fois `read` en attente. La fiche le dit en clair : coller le bloc, Entrée s'il reste sur la ligne de commande,
  puis le jeton quand `Jeton:` s'affiche (`documentation/monitorage.md:244-247`).

### Les variables, en local et en ligne

En local, `.env.e2e_test` (modèle `.env.e2e_test.example:25-30`). En ligne, l'en-tête est le secret `kb-otlp-headers`
du coffre (`infra/main.bicep:209`), l'adresse le paramètre `otlpEndpoint` de la seconde passe (`infra/main.bicep:28-29`,
`:333`), et l'environnement est écrit dans le gabarit (`infra/main.bicep:323`). La fiche cite ensuite cinq réglages
que `kb serve-ai` refuse au démarrage, « par exemple » : la liste complète est dans le code cité
(`metrics_export.py:99-151`, `:169-188`, `:198-213` ; `src/k_b/core/outbound.py:19-39`).

### La vérification : le test, puis Explore

`documentation/monitorage.md:295-298` :

```markdown
    Un jeton refusé fait échouer le test (`tests/e2e/test_real_export.py:119`). Le test vérifie que chaque envoi est
    accepté; l'arrivée des séries se vérifie dans Explore, car le SDK d'OpenTelemetry
```

Le test exige que chaque export rende `SUCCESS` (`tests/e2e/test_real_export.py:119`). Mais le SDK compte aussi une
réponse 3xx, une redirection, comme un succès (`tests/e2e/test_real_export.py:7-8`) : seul Explore prouve que les
séries sont arrivées. Le test n'envoie que les mesures (`:96-97`) : les traces se lisent dans Tempo après une demande
à `kb serve-ai`.

### L'expiration d'un jeton

`documentation/monitorage.md:351-366` donne la règle, et non une date : la date d'expiration est celle choisie dans le
champ « Expiration date » de la boîte « Create new token » (vide, le jeton n'expire pas), et un jeton expiré est
marqué « Expired » sur la page « Access Policies » du portail. Le destinataire des e-mails d'avant expiration est cité
mot pour mot de Grafana, en `<q lang="en">` : pour une politique de pile, « the admins of the corresponding stack ».
Ces e-mails partent par défaut ; la case « Enable token expiration emails », page « Settings » des « Org Settings »,
les coupe. Tout cela vient des deux pages de Grafana sur les politiques d'accès, citées dans les sources.

Le temps qui reste à un jeton s'affiche sur la page « Cloud access policies » de la pile : c'est le relevé de #664
(`docs/journaling/2026-11-20-relire-api10-depuis-le-jeton-de-production.md:24-29`, `:109-110`, « in 3 months »).
Pour la production, la fiche donne la durée du jeton, 90 jours choisie à sa création (#522), et non une date :
« 2027-02-09 » était un calcul, jamais lu dans Grafana.

### Les alertes d'Azure dans la liste des seuils

`documentation/monitorage.md:94-102` : `budget-kb`, 40 € par mois sur les coûts étiquetés `project=k-b`, un e-mail à
50 % et 100 % du réel et à 100 % de la prévision (`infra/modules/budget.bicep:11-12`, `:20-22`, `:27-58`) ;
`alert-kb-model-tokens`, `TotalTokens` au-dessus de 400 000 sur 24 h glissantes, évaluée toutes les 15 minutes
(`infra/modules/model-token-alert.bicep:41-42`, `:52-55` ; `infra/main.bicep:176`). Toutes deux écrivent à l'adresse
de `budgetContactEmail` (`infra/main.bicep:161`, `:181`). Ni le job `caj-kb-digest-watch`, qui n'est pas une
alerte, ni les alertes d'erreurs de #553, qui ne sont pas déployées.

## Choix faits et options écartées

- **Une branche neuve depuis `main`**, plutôt qu'un rebase de `docs/monitoring-export-and-reimport` (écrite le
  2026-11-14) : #669 a remis en forme toute la fiche, et chaque commit aurait été en conflit pour un seul texte. Le
  texte a été réécrit selon la notice, et chaque renvoi relu sur `main`.
- **Le jeton créé dans une politique de la pile**, plutôt que par le bouton de la tuile OpenTelemetry : la tuile
  génère un jeton dont les droits ne sont pas choisis ici ; Grafana écrit « Don't click Generate now on the
  OpenTelemetry card » quand une politique existe.
- **L'en-tête construit dans le terminal**, plutôt que copié depuis la tuile : le jeton ne s'affiche pas, et la
  commande montre ce que l'en-tête contient.
- **Les accolades et l'invite `Jeton:`**, plutôt qu'une consigne « taper la ligne `read` seule » : le bloc se colle
  d'un coup, dans bash comme dans zsh, et l'invite dit quand coller le jeton. Les accolades seules ne suffisaient pas
  sous zsh : la relecture du delta l'a montré par un essai.
- **« Par exemple »** devant les réglages refusés, plutôt que la liste complète : la fiche montre les refus qu'un
  installateur rencontre, et renvoie au code pour le reste.
- **Les libellés d'Apple en français** : le Mac de Sabine est en français ; la page d'aide citée est la page fr-fr.
- **Une source par recherche web** : Context7 n'était pas connecté le 2026-11-21. Chaque page a été lue le jour même.
- **Les libellés vérifiés dans la documentation officielle de Grafana Cloud**, plutôt que parcourus par Sabine dans sa
  pile (décision de Sabine du 2026-11-22). Un libellé absent de la documentation est écrit de façon générique : le
  questionnaire de l'inscription, que la documentation ne décrit pas, n'est pas dans la fiche ; seul
  « Add Stack » l'est.
- **La règle de l'expiration, plutôt qu'une date** : la date du jeton de la production n'a jamais été lue dans
  Grafana ; la fiche dit où elle se choisit et comment un jeton expiré se repère.
- **Les sources des seuils par la ligne du journal des décisions**, sans nom ni date, plutôt que par le titre de
  l'entrée.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Les 20 renvois `fichier:ligne` de la section, relus sur `main` au commit `36c1e02d`, puis de nouveau le 2026-11-22 sur `9658225a` après la fusion de `main` (trois renvois vers `docs/fiches-veille.md` décalés de 10 à 13 lignes, corrigés) | Chaque phrase dit ce que la ligne citée contient |
| Les 97 renvois `fichier:ligne` de toute la fiche comparés, ligne à ligne, entre le dernier commit de `main` qui touche la fiche (`96ec90ef`) et `a1a01efd` : deux renvois décalés, d'un même fichier, `docs/registre-traitements.md:199` et `:293`, qui visaient déjà une ligne vide en `96ec90ef`, corrigés en `:234` et `:328` | La tête de la fiche peut nommer un seul commit, `a1a01efd` |
| Chaque libellé et chemin de Grafana Cloud de la fiche retrouvé dans une page officielle : création d'une pile, envoi en OTLP, création d'une politique et d'un jeton, politiques d'accès, analyse des séries dans Explore, sources de données, éditeur de requêtes d'Explore, politique des traces | Les libellés de la fiche sont ceux de Grafana |
| Les chiffres des deux alertes d'Azure lus dans `infra/modules/budget.bicep`, `infra/modules/model-token-alert.bicep` et `infra/main.bicep` | La liste des seuils ne dit que ce que le code pose |
| Le HTML construit : 7 citations dans l'encadré, chaque ancre de la liste de l'encadré présente, 7 tableaux, tous à en-têtes `th` | L'encadré et sa liste se lisent, au clavier comme au lecteur d'écran |
| `uv run --locked --only-group docs mkdocs build --strict` : sortie 0 | Aucun lien ni ancre cassé |
| Le HTML construit : une liste ordonnée de six étapes, les deux blocs de code dans leur étape, les ancres `#brancher-lexport`, `#limites`, `#sources` présentes | La section se lit comme une suite d'étapes, au clavier comme au lecteur d'écran |
| Contrôle du HTML de la déclaration d'accessibilité sur la section : `lang="fr"`, un seul `h1`, aucun saut de niveau, aucun lien nommé par une adresse, « ici » ou « plus haut » | La section tient la vérification d'AcceDe du 2026-11-21 |
| Aucune espace avant « : » ou « ; » hors code, aucun caractère `Cc` ou `Cf` | Les règles de typographie du dépôt |
| Collage simulé dans un pseudo-terminal (`pty.fork()` de Python), faux jeton, sous bash 3.2 et zsh 5.9, collage protégé actif ou non, bloc avec et sans son dernier retour à la ligne : huit cas, suivis comme la fiche le dit | Dans les huit cas, ni écho, ni jeton dans l'historique, ni jeton lancé comme commande, et l'en-tête attendu ; sans accolades sous bash 3.2, ou le jeton collé avant `Jeton:` sous zsh, le jeton s'affiche et entre dans l'historique |
| Relecture neuve du commit `079a2827`, puis relecture du delta `558e0f8a` | Les constats, triés, sont dans la PR |
| Relecture du delta `eac9d1ee..3410b2cf` (`/code-review`, niveau `high`) : 10 constats, 9 corrigés, 1 écarté (les dates de lecture des sources, que la règle de Sabine retire de la fiche), tranchés par time-knight sous la délégation de Sabine du 15/10 | Le tri est dans la PR |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas le jeton de la tuile OpenTelemetry ?** Ses droits ne se choisissent pas à l'étape où on le
   génère ; celui de la politique ne porte que les trois droits d'écriture, sur cette pile seule
   (`documentation/monitorage.md:226-238`).
2. **Le jeton peut-il fuiter pendant l'installation ?** Ni à l'écran (`read -s`), ni dans l'historique, ni dans la
   liste des processus (`printf` interne), même collé d'un coup sous zsh : l'invite `Jeton:` dit quand le coller. Il
   reste dans le presse-papiers, que l'étape vide, et dans l'historique de Spotlight s'il est activé, que l'étape
   efface (`:257-260`).
3. **Le test passe : les mesures sont-elles arrivées ?** Pas forcément : une redirection compte comme un succès pour
   le SDK. La preuve est la série vue dans Explore (`:298-301`).
4. **Que se passe-t-il quand le jeton expire ?** L'export reçoit des 401 (`Failed to export 'metrics' batch
   code: 401` dans le journal). Grafana écrit avant aux administrateurs de la pile ; la rotation est la procédure
   « Pour refaire un seul secret » d'`infra/README.md` (`documentation/monitorage.md:351-366`).
5. **Quelles alertes surveillent la dépense ?** Dans Grafana, `KbModelCostOverBudget` sur le coût estimé ; dans Azure,
   `budget-kb` sur les coûts réels et prévus du mois, et `alert-kb-model-tokens` sur les jetons de la ressource du
   modèle (`:94-102`).
6. **Pourquoi `prod-eu-west-2` est-il en Allemagne ?** La page des adresses des régions de Grafana Cloud range ce
   nom sous AWS, Allemagne ; le registre le lit sur l'hôte de l'adresse OTLP (`docs/registre-traitements.md:128`).

## Zones non vérifiées

- Les chemins de l'interface dans la pile de Sabine : ils viennent de la documentation officielle de Grafana Cloud,
  non d'un parcours à l'écran (décision de Sabine du 2026-11-22).
- La date d'expiration du jeton de la production : jamais lue dans Grafana, elle n'est pas écrite.
- L'endroit de l'interface où s'affiche le temps qui reste à un jeton : la documentation ne le nomme pas ; la fiche
  le prend du relevé de #664, la page « Cloud access policies » de la pile.
- Les libellés des lignes du champ « Scopes » : la documentation ne nomme que la ligne « Traces » ; la fiche écrit
  les trois lignes de façon générique (les mesures, les journaux, les traces) avec leurs droits.
- Le collage de l'en-tête dans un vrai Terminal ou iTerm2, et avec les fichiers `~/.zshrc` ou `~/.bashrc` de Sabine :
  le terminal était simulé, sans configuration. Un greffon comme `bracketed-paste-magic` peut changer le collage.

## Ce qui reste

- La relecture du delta, puis la PR sort du brouillon et part sur l'accord de Sabine.
- La branche `docs/monitoring-export-and-reimport` est supprimée après la fusion.
