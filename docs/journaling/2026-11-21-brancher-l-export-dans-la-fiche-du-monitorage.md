# Brancher l'export dans la fiche du monitorage

- Date : 2026-11-21
- Branche : `docs/monitoring-export-step`
- Issue : #620 (et le reste de #621, l'expiration du jeton de la production)
- Fichier : `documentation/monitoring_pour_docu.md`
- Série : [la mise en forme de la fiche (#669)](2026-11-21-mettre-en-forme-la-fiche-du-monitorage.md), [la relecture
  d'API10 depuis le jeton de la production (#611)](2026-11-20-relire-api10-depuis-le-jeton-de-production.md)

## Le pourquoi

La fiche du monitorage sert au jury de preuve pour C11 et C20 : la procédure d'installation et de configuration de
l'outillage du monitorage. Sa section « Installer » partait d'une pile Grafana Cloud qui reçoit déjà les mesures : le
branchement de l'export, lui, n'était écrit que dans `docs/fiches-veille.md` et dans `.env.example`. Un lecteur qui
suivait la fiche ne pouvait pas installer la chaîne d'un bout à l'autre. L'étape « Brancher l'export » comble cet
écart : de la pile vide jusqu'aux séries vues dans Explore, puis l'import du tableau et des règles.

Le jeton de la production expire : la fiche dit quand, et qui Grafana prévient avant, sous « Maintenir ».

## Le comment

### Une étape, six parties, avant « Installer »

La section est placée entre « Lire le tableau » et « Installer », car l'import du tableau suppose une pile qui reçoit
déjà les mesures. « Installer » part d'elle par un lien nommé (`documentation/monitoring_pour_docu.md:180`) :

```markdown
Sur la pile qui reçoit les mesures ([Brancher l'export](#brancher-lexport)), par l'interface, sans jeton ni outil à
installer.
```

Les six parties suivent l'ordre d'une installation : la pile, l'adresse et l'identifiant, le jeton, l'en-tête, les
variables, la vérification. Chaque libellé de l'interface de Grafana Cloud est en anglais, dans un
`<span lang="en">`, comme le reste de la fiche (notice d'AcceDe Web), pour qu'un lecteur d'écran le lise en anglais.

### Le jeton : une politique de la pile, trois droits d'écriture

`documentation/monitoring_pour_docu.md:105-113` crée la politique depuis le Grafana de la pile, et non depuis le
portail de l'organisation :

```markdown
3. **Le jeton**: dans le Grafana de la pile, <span lang="en">**Administration**, **Users and access**, **Cloud access
    policies**, **Create access policy**</span>. Une politique créée là ne vaut que pour cette pile.
```

Une politique créée là a le *realm* de la pile : ses jetons ne valent que pour elle (page « Access policies » de
Grafana, citée dans les sources). Les trois droits, `metrics:write`, `logs:write` et `traces:write`, sont ceux de
`.env.example:164` : le jeton ne fait qu'écrire, K-B ne relit rien de ce qu'il envoie. C'est le moindre privilège de
`code.md`.

### L'en-tête : un jeton qui ne passe ni par l'écran ni par l'historique

`documentation/monitoring_pour_docu.md:122-128` :

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
  puis le jeton quand `Jeton:` s'affiche (`documentation/monitoring_pour_docu.md:117-120`).

### Les variables, en local et en ligne

En local, `.env.e2e_test` (modèle `.env.e2e_test.example:25-30`). En ligne, l'en-tête est le secret `kb-otlp-headers`
du coffre (`infra/main.bicep:209`), l'adresse le paramètre `otlpEndpoint` de la seconde passe (`infra/main.bicep:28-29`,
`:333`), et l'environnement est écrit dans le gabarit (`infra/main.bicep:323`). La fiche cite ensuite cinq réglages
que `kb serve-ai` refuse au démarrage, « par exemple » : la liste complète est dans le code cité
(`metrics_export.py:99-151`, `:169-188`, `:198-213` ; `src/k_b/core/outbound.py:19-39`).

### La vérification : le test, puis Explore

`documentation/monitoring_pour_docu.md:165-168` :

```markdown
    Un jeton refusé fait échouer le test (`tests/e2e/test_real_export.py:119`). Le test vérifie que chaque envoi est
    accepté; l'arrivée des séries se vérifie dans Explore, car le SDK d'OpenTelemetry
```

Le test exige que chaque export rende `SUCCESS` (`tests/e2e/test_real_export.py:119`). Mais le SDK compte aussi une
réponse 3xx, une redirection, comme un succès (`tests/e2e/test_real_export.py:7-8`) : seul Explore prouve que les
séries sont arrivées. Le test n'envoie que les mesures (`:96-97`) : les traces se lisent dans Tempo après une demande
à `kb serve-ai`.

### L'expiration du jeton de la production

`documentation/monitoring_pour_docu.md:225-230` : 90 jours depuis le 2026-11-11, jusqu'au 2027-02-09 (#522). Le
destinataire des e-mails d'avant expiration est cité mot pour mot de Grafana, en `<q lang="en">` : pour une politique
de pile, « the admins of the corresponding stack ». La case qui les active est cochée, lue par Sabine le 2026-11-20
(`docs/fiches-veille.md:1690-1691`).

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

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Les 20 renvois `fichier:ligne` de la section, relus sur `main` au commit `36c1e02d` | Chaque phrase dit ce que la ligne citée contient |
| `uv run --locked --only-group docs mkdocs build --strict` : sortie 0 | Aucun lien ni ancre cassé |
| Le HTML construit : une liste ordonnée de six étapes, les deux blocs de code dans leur étape, les ancres `#brancher-lexport`, `#limites`, `#sources` présentes | La section se lit comme une suite d'étapes, au clavier comme au lecteur d'écran |
| Contrôle du HTML de la déclaration d'accessibilité sur la section : `lang="fr"`, un seul `h1`, aucun saut de niveau, aucun lien nommé par une adresse, « ici » ou « plus haut » | La section tient la vérification d'AcceDe du 2026-11-21 |
| Aucune espace avant « : » ou « ; » hors code, aucun caractère `Cc` ou `Cf` | Les règles de typographie du dépôt |
| Collage simulé dans un pseudo-terminal (`pty.fork()` de Python), faux jeton, sous bash 3.2 et zsh 5.9, collage protégé actif ou non, bloc avec et sans son dernier retour à la ligne : huit cas, suivis comme la fiche le dit | Dans les huit cas, ni écho, ni jeton dans l'historique, ni jeton lancé comme commande, et l'en-tête attendu ; sans accolades sous bash 3.2, ou le jeton collé avant `Jeton:` sous zsh, le jeton s'affiche et entre dans l'historique |
| Relecture neuve du commit `079a2827`, puis relecture du delta `558e0f8a` | Les constats, triés, sont dans la PR |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas le jeton de la tuile OpenTelemetry ?** Ses droits ne se choisissent pas à l'étape où on le
   génère ; celui de la politique ne porte que les trois droits d'écriture, sur cette pile seule
   (`documentation/monitoring_pour_docu.md:105-113`).
2. **Le jeton peut-il fuiter pendant l'installation ?** Ni à l'écran (`read -s`), ni dans l'historique, ni dans la
   liste des processus (`printf` interne), même collé d'un coup sous zsh : l'invite `Jeton:` dit quand le coller. Il
   reste dans le presse-papiers, que l'étape vide, et dans l'historique de Spotlight s'il est activé, que l'étape
   efface (`:130-133`).
3. **Le test passe : les mesures sont-elles arrivées ?** Pas forcément : une redirection compte comme un succès pour
   le SDK. La preuve est la série vue dans Explore (`:165-171`).
4. **Que se passe-t-il le 2027-02-09 ?** Le jeton expire, l'export reçoit des 401 (`Failed to export 'metrics' batch
   code: 401` dans le journal). Grafana écrit avant aux administratrices de la pile ; la rotation est la procédure
   « Pour refaire un seul secret » d'`infra/README.md` (`:222-230`).
5. **Pourquoi `prod-eu-west-2` est-il en Allemagne ?** La page des adresses des régions de Grafana Cloud range ce
   nom sous AWS, Allemagne ; le registre le lit sur l'hôte de l'adresse OTLP (`docs/registre-traitements.md:128`).

## Zones non vérifiées

- Les chemins de l'interface dans la pile de Sabine : ils viennent de la documentation de Grafana du jour. Sabine les
  parcourt avant que la PR quitte le brouillon.
- La date d'expiration exacte du jeton : 2027-02-09 est le calcul de 90 jours depuis le 2026-11-11. Sabine la lit sur
  la page « Cloud access policies » pendant son parcours.
- Les lignes « Metrics » et « Logs » du champ « Scopes » : la documentation nomme la ligne « Traces » ; les deux
  autres suivent le même modèle, à voir dans l'interface.
- Le collage de l'en-tête dans un vrai Terminal ou iTerm2, et avec les fichiers `~/.zshrc` ou `~/.bashrc` de Sabine :
  le terminal était simulé, sans configuration. Un greffon comme `bracketed-paste-magic` peut changer le collage.

## Ce qui reste

- Le parcours de l'interface par Sabine, puis la PR sort du brouillon.
- La branche `docs/monitoring-export-and-reimport` est supprimée après la fusion.
