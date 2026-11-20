# Scanner l'image de K-B dans la CI, et en faire un contrôle exigé de `main`

- **Date** : 2026-11-14
- **Branche** : `ci/scan-image`, commits `b110816` et `d05927e`, puis `1b67dbd` (fusion de `main` à `57ff235`)
- **Issue** : #498
- **Série** : suite de [Construire le Bicep sur toute PR](2026-11-13-construire-le-bicep-sur-toute-pr.md) (#496),
  l'autre mesure d'API8 tenue par un contrôle exigé ; la mesure vient de l'auto-évaluation OWASP de l'API IA (#454,
  #500).
- **Fichiers principaux** : `.github/workflows/image.yml`, `documentation/integration_continue_pour_docu.md`,
  `docs/fiches-veille.md` (API8), `docs/specs-api.md`, `README.md`, `docs/ADR/journal-decisions-projet.md`.

La liste des commits donnée à la note compte aussi ceux de `main` jusqu'à `57ff235` (#560, #596, #559, #496, #606…) :
ils sont entrés par d'autres PR, qui ont leur note. `1b67dbd` ne fait que fusionner `main` dans la branche ; seul le
journal ADR y a eu un conflit, deux entrées du 14/11 ajoutées au même endroit, gardées toutes les deux. Cette note
couvre `b110816` et `d05927e`, puis, le 18/11, le digest de la base monté (`b38fd16`) et l'installation de zlib1g
(section 6).

## Le pourquoi

La CI cherchait déjà les vulnérabilités connues des paquets Python de K-B : le job `audit` passe `uv.lock` à
pip-audit. Mais l'image qui part en ligne contient bien plus que `uv.lock` : les paquets Debian de l'image de base
`python:3.13-slim-trixie`, CPython lui-même, et `pip`, que l'image de base installe. Rien ne les vérifiait.
L'auto-évaluation OWASP de l'API IA comptait ce manque dans la mesure « évaluation automatisée et continue » d'API8
(Security Misconfiguration), non tenue. Sabine a décidé le 08/11 de la tenir, par un outil de CI nouveau.

Ce travail ajoute un scanner d'image à `image-build`, le rend bloquant pour toute PR (`image-build` devient exigé par
le ruleset de `main`, le geste de Sabine juste avant la fusion), et écrit quoi faire quand il bloque. Il ne tient pas
toute la mesure : les sondes après déploiement restent à #499. Il passe en revanche le « durcissement répétable »
d'API8 à « tenue », grâce au constat que #496 attendait.

## Le comment

### 1. Un binaire téléchargé, vérifié avant d'être exécuté

```yaml
      - name: Installs Grype v0.121.3
        run: |
          curl -fsSL -o "$RUNNER_TEMP/grype.tar.gz" \
            https://github.com/anchore/grype/releases/download/v0.121.3/grype_0.121.3_linux_amd64.tar.gz
          echo "e9da18cc1429e786722e32161288103600efffd8e483c90761f90485bd1bec85  $RUNNER_TEMP/grype.tar.gz" | sha256sum -c
          tar -xzf "$RUNNER_TEMP/grype.tar.gz" -C "$RUNNER_TEMP" grype
```

`.github/workflows/image.yml:67-72`. Le job télécharge l'archive de la release de Grype, puis `sha256sum -c` compare
son empreinte à celle écrite dans le workflow. Si elles diffèrent, la commande rend un code non nul, et le shell du
runner (`bash -e`) arrête l'étape : l'archive n'est jamais décompressée, Grype jamais lancé. L'empreinte a été lue le
18/11 à deux endroits : le `digest` de l'asset dans l'API des releases de GitHub, et le fichier
`grype_0.121.3_checksums.txt` de la même release. Elles concordent.

C'est le même principe qu'`infra.yml` pour Bicep : on ne fait pas confiance à « la dernière version », ni à une URL
seule. Une release réécrite après coup (ce qui est arrivé à Trivy le 19/03/2026) changerait l'empreinte, et le job
échouerait au lieu d'exécuter un binaire piégé. `tar` n'extrait que le fichier `grype`, dans le dossier temporaire du
runner.

### 2. Le scan et son seuil

```yaml
      - name: Has no high or critical vulnerability that has a fix
        env:
          GRYPE_CHECK_FOR_APP_UPDATE: "false"
        run: |
          "$RUNNER_TEMP/grype" docker:k-b:ci --only-fixed --fail-on high
```

`.github/workflows/image.yml:78-82`. `docker:k-b:ci` dit à Grype de lire l'image que le job a construite plus haut,
dans le démon Docker du runner. Il en lit le système de fichiers final et y reconnaît les paquets Debian, les paquets
Python installés (sous `/app/.venv`, et ceux de l'image de base sous `/usr/local/lib/python3.13`, dont `pip`) et le
binaire de CPython.

Le seuil se lit en deux temps. `--only-fixed` écarte d'abord les vulnérabilités sans correctif publié. `--fail-on
high` fait ensuite échouer la commande s'il reste une vulnérabilité de sévérité haute ou plus, donc haute ou
critique. La doc d'Anchore le dit : le contrôle de `--fail-on` tourne après le filtrage. Le comportement a été validé
par Sabine avec le plan le 13/11. La raison donnée par le plan : la CI ne refuse que ce qu'une PR peut corriger.

Grype télécharge sa base de vulnérabilités à chaque exécution, et la refuse si elle a été construite il y a plus de
5 jours (`db.max-allowed-built-age`, 120 h par défaut, lu dans la référence des réglages le 14/11). Une base trop
vieille ne laisse donc pas passer une image en silence. `GRYPE_CHECK_FOR_APP_UPDATE: "false"` coupe seulement
l'appel qui cherche une version plus récente de Grype : la version est épinglée.

### 3. En dernière étape du job

Le scan est la dernière étape d'`image-build`, après `kb --help` et `kb create-db`
(`.github/workflows/image.yml:60-82`). Le plan le plaçait juste après la construction. La revue de code a montré
qu'un scan rouge, placé là, arrêtait le job avant les contrôles de l'image (utilisateur non root, fichiers plantés,
refus de démarrer sans `KB_DATA_DIR`). On ne savait plus si la nouvelle image démarrait. En dernier, un scan rouge
fait toujours échouer le job, et les autres contrôles ont déjà rendu leur résultat. Time-knight a tranché cet écart au
plan le 14/11.

### 4. Un contrôle exigé, et quoi faire quand il bloque

Exigé par le ruleset, `image-build` bloque la fusion de toute PR tant qu'une vulnérabilité haute ou critique corrigée
est dans l'image. Une vulnérabilité publiée un matin rend donc rouges toutes les PR, comme `audit` le 13/11 (#606).
C'est le prix du contrôle. La doc de la CI donne la marche à suivre, dans cet ordre
(`documentation/integration_continue_pour_docu.md:433-471`) :

1. un paquet Python de l'environnement virtuel : `audit` échoue aussi, on monte le paquet dans `uv.lock` ;
2. un paquet Debian, CPython ou un paquet Python de l'image de base, quand l'image `python` amont a déjà le
   correctif : on monte à la main le digest des deux `FROM` du `Dockerfile`, sans attendre la PR de Dependabot ;
3. un paquet Debian dont le correctif est dans `trixie-security` mais pas encore dans l'image amont : on l'installe
   dans l'étape finale du `Dockerfile`, à la version corrigée écrite en entier, avec une issue qui retire le bloc
   (ajoutée le 18/11, section 6) ;
4. sinon : une entrée dans `.grype.yaml`, décidée par Sabine, avec sa raison, sa date et l'issue qui la retire.

```yaml
ignore:
  - vulnerability: CVE-AAAA-NNNNN
    package:
      name: <paquet>
    reason: "<pourquoi l'accepter>, décidé par Sabine le AAAA-MM-JJ, retiré par #<issue>"
```

Grype lit `.grype.yaml` dans le dossier où il tourne : la racine du dépôt cloné par le job. Le fichier n'existe pas
aujourd'hui. Il ne naît qu'avec une première entrée, parce qu'une vulnérabilité acceptée est une règle non tenue, et
`conformite.md` veut qu'elle le soit par décision écrite, jamais par oubli. `.dockerignore`, qui refuse tout sauf
quatre chemins, le tient hors de l'image.

### 5. Ce que devient l'auto-évaluation d'API8

Deux mesures d'API8 changent dans `docs/fiches-veille.md` :

- **« Durcissement répétable »** (l. 1291) passe à « tenue ». #496 avait rendu `bicep-build` exigé ; il restait à le
  voir vert sur une PR qui ne touche pas `infra/`. La PR #625 (piste A, 30 fichiers, aucun sous `infra/`) l'a reçu,
  vert, le 14/11 à 16:53 UTC (exécution 43618055085). Le constat est posté sur #496. Le plan attendait la PR d'API10 ;
  celle de #625 est venue plus tôt, avec la même preuve (accord de time-knight).
- **« Évaluation automatisée »** (l. 1337) reste « non tenue, en partie » : le scan y est décrit, mais les sondes après
  déploiement viennent avec #499. Les exécutions du scan, rouge sur l'essai et vert sur l'image de #643, n'y ont été
  citées qu'une fois qu'elles existaient (`1f2abbf`) : l'auto-évaluation ne s'écrit jamais d'avance.

### 6. Le premier scan rouge : zlib1g, installé à sa version corrigée

Le 18/11, le scan de la PR a été rouge sur l'image du jour : zlib1g `1:1.3.dfsg+really1.3.1-1+b1`, la bibliothèque
de compression de Debian, porte CVE-2026-85091 (haute). Debian l'a corrigée le 07/11 (DSA-6613-1), mais dans son archive
de sécurité seulement, `trixie-security` : l'image `python` du jour, au digest `e48f59c…` monté à la main (étape 2),
ne l'a pas (exécution 44279945350). Sabine a choisi d'installer la version corrigée dans l'image
(`Dockerfile:52-54`) :

```dockerfile
RUN apt-get update \
    && apt-get install --yes --no-install-recommends zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 \
    && rm -rf /var/lib/apt/lists/*
```

`apt-get update` lit les index des sources de l'image de base. `apt-get install` remplace la zlib1g installée par la
version écrite. Grype lit les paquets dans la base de `dpkg`, qui nomme alors la version corrigée. Les index sont
retirés après coup : ils ne servent plus et alourdiraient l'image. Le bloc est placé juste avant `USER 10001:10001`,
parce qu'installer un paquet demande root. Il est placé après `ENV` pour qu'aucun des renvois `Dockerfile:<ligne>`
antérieurs au bloc ne bouge, ni maintenant ni au retrait. Ceux qui citent le bloc lui-même partent avec lui (#647).

La version est écrite en entier : l'image reste celle de son `Dockerfile`, pas celle du jour de sa construction.
C'est pourquoi `apt-get upgrade` reste écarté. Le revers : l'index de `trixie-security`, lu le 18/11, ne porte
qu'une version de zlib1g ; quand une `+deb13u2` remplacera la `+deb13u1`, la construction échouera. Le bloc est provisoire : #647 le retire dès
qu'un digest de l'image de base porte le correctif.

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| L'outil | Grype (Anchore, Apache 2.0) : un binaire, sans compte, qui voit CPython | Trivy : vecteur de l'attaque du 19/03/2026 (76 tags de `trivy-action` sur 77 réécrits, un binaire v0.69.4 piégé), et il ne voit pas le CPython de l'image ; Docker Scout : un compte Docker |
| La forme | le binaire de la release, vérifié par son SHA256, comme Bicep | `anchore/scan-action` : une action de plus, du code de plus à croire |
| La version | v0.121.3 (09/11), la dernière publiée depuis 7 jours au moins, l'attente que se donne Dependabot ; v0.121.2 au code du 14/11, montée le 18/11 (tranché par time-knight) | v0.122.0 (16/11), 2 jours le 18/11 ; elle corrige un avis moyen du SDK OpenTelemetry pour Go que Grype embarque ; le job ne règle aucune variable `OTEL_*`, son effet sur le scan est supposé nul, non vérifié |
| Ce qui est scanné | tout ce que Grype voit : l'image est ce qui part en ligne (plan, point 4) | les seuls paquets Debian : `pip` et CPython échapperaient au scan |
| Le seuil | haute ou critique, avec correctif (l'issue, validé avec le plan) | sans `--only-fixed` : une vulnérabilité que personne ne peut corriger bloquerait toutes les PR |
| La place | en dernière étape (revue de code, tranché par time-knight) | juste après la construction (le plan) : un scan rouge cachait les autres contrôles |
| Exigé ou non | exigé par le ruleset (plan, point 6, validé par Sabine le 13/11) | non exigé : un scan rouge laisserait fusionner et ne bloquerait qu'au déploiement |
| Quand il bloque | digest de l'image de base monté à la main, sinon `.grype.yaml` décidé par Sabine | `apt-get upgrade` dans le `Dockerfile` : l'image dépendrait du jour de sa construction, plus du digest épinglé |
| zlib1g, le 18/11 | installé dans l'image à la version corrigée, écrite en entier, et retiré par #647 (décision de Sabine sur la recommandation de time-knight : le correctif existe et l'image en ligne porte la faille) | une entrée de `.grype.yaml` : elle accepte un risque qu'on peut corriger ; attendre l'image amont : toutes les PR restent rouges d'ici là |
| Les téléchargements | sans nouvelle tentative ni cache (revue de code, écarté par time-knight) | un cache de la base : une action de plus ; une relance est un clic, déjà écrite dans la doc |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `grep -n "grype" .github/workflows/image.yml` → rien, exit 1, le 14/11 avant le code | le critère rouge : aucun scan avant #498 |
| `gh api repos/anchore/grype/releases/tags/v0.121.3` → digest `sha256:e9da18cc…ec85`, égal à la ligne de `grype_0.121.3_checksums.txt`, le 18/11 | l'empreinte écrite dans `image.yml:71` est celle de la release |
| `gh pr checks 625` → `bicep-build pass 20s`, exécution 43618055085, le 14/11 à 16:53 UTC | le « durcissement répétable » est tenu (#496) |
| `uv run pytest` → 5582 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts ; `yamllint` sur `image.yml` sans erreur | la branche ne casse rien ; le workflow est un YAML valide |
| `/security-review` (sous-agent neuf, lecture seule) → aucun constat ≥ 8/10 | pas d'injection (aucun `${{ github.event.* }}` dans un `run:`), `pull_request` et non `pull_request_target`, `contents: read`, échec fermé |
| l'essai jetable #644, les deux `FROM` sur `python:3.13.0-slim-bookworm` (décembre 2024) : `image-build` rouge, exécution 44275262249, le 18/11 | le scan refuse bien une vulnérabilité haute ou critique corrigée |
| l'exécution 44279945350 sur b38fd169, le 18/11 : `zlib1g 1:1.3.dfsg+really1.3.1-1+b1`, corrigé en `1:1.3.dfsg+really1.3.1-1+deb13u1`, CVE-2026-85091 `High` ; `image-build` rouge | l'image du jour, au digest monté, porte la faille ; la version installée est `+b1`, une recompilation de Debian |
| l'exécution 44347407723 sur ccb672fc, le 18/11 à 16:27 UTC : apt prend zlib1g `1:1.3.dfsg+really1.3.1-1+deb13u1` dans `trixie-security` (« 1 upgraded, 0 newly installed »), puis le scan est vert ; restent 7 vulnérabilités de CPython, moyennes ou moindres | les sources d'APT de l'image comptent `trixie-security`, le bloc n'installe que zlib1g, et l'image passe le seuil |

## Ce que tu dois pouvoir défendre

- **Pourquoi un scan de l'image, alors qu'`audit` existe ?** `audit` lit `uv.lock`. L'image contient aussi les paquets
  Debian, CPython et `pip` de l'image de base, qu'aucun contrôle ne voyait (`.github/workflows/image.yml:73-77`).
- **Que se passe-t-il si quelqu'un remplace le binaire de Grype sur GitHub ?** L'empreinte change, `sha256sum -c`
  échoue, le job s'arrête avant d'exécuter quoi que ce soit (`image.yml:71`).
- **Pourquoi ne pas bloquer aussi les vulnérabilités sans correctif ?** Aucune PR ne peut les corriger : elles
  bloqueraient toutes les PR sans issue. Elles restent un risque, écrit comme limite (« Le scan ne voit pas tout »).
- **L'image en ligne est-elle scannée ?** Pas au moment du tag : `deploy.yml` reconstruit l'image depuis le même
  commit, mêmes digests et même `uv.lock`, sans la rescanner (l. 102-117). Une vulnérabilité publiée entre le dernier
  scan et le tag passe. C'est écrit comme limite, et #626 porte le scan dans `deploy.yml`. Ce défaut existait déjà
  avant #498.
- **Et si une PR ajoute un `.grype.yaml` qui ignore tout ?** Le scan passerait. Mais qui peut ajouter ce fichier peut
  aussi modifier `image.yml`. Le fichier se voit dans le diff, et chaque entrée est une décision de Sabine. La revue de
  sécurité a jugé ce point sous le seuil.

## Zones non vérifiées

- **Le code de sortie exact de `--fail-on`** : l'aide de la CLI dit 2, la description du réglage dit 1. Le workflow ne
  dépend que d'un code non nul.
- **Les types que Grype donne** (`deb`, `python`, `binary` pour CPython) viennent de sa documentation et de son code
  lus par Context7, pas d'une exécution sur notre image.
- **`docker buildx imagetools inspect`**, cité dans la marche à suivre pour lire le digest du jour, et
  **`dpkg-query -W zlib1g`**, cité dans la limite pour savoir quand #647 s'applique, n'ont pas été lancés (le démon
  Docker du Mac ne tournait pas) : l'image avec le bloc de zlib1g n'a été construite que par la CI.
- **La vérification que Grype fait lui-même de sa base téléchargée** n'a pas été lue.

## Ce qui reste

- **Le geste de Sabine, après la fusion de #643** (le 18/11, sans lui) : `image-build` au ruleset de `main`, et sa
  lecture citée. Lu le 18/11 après la fusion, le ruleset exige encore six contrôles, sans `image-build`.
- **La montée à Grype v0.122.0** après le 23/11 à 20:41 UTC, par une PR.
- **#647** : retirer l'installation de zlib1g quand l'image de base porte le correctif.
- **#626** : le même scan dans `deploy.yml`, avant la mise en ligne.
- **#499** : les sondes sans clé après déploiement, qui tiendront le reste de l'« évaluation automatisée ».
- **#497** : la revue périodique de la configuration en ligne, le dernier morceau d'API8.
