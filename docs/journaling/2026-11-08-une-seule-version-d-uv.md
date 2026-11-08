# Une seule version d'uv : 0.13.6 dans la borne, l'image, la CI et le Mac

- **Date** : 2026-11-08
- **Branche** : `chore/uv-0-13`
- **Issue** : #485
- **Fichiers principaux** : `pyproject.toml`, `Dockerfile`, `.github/workflows/ci.yml`,
  `.github/dependabot.yml`, `README.md`, `docs/ADR/journal-decisions-projet.md`

## Le pourquoi

uv joue deux rôles dans K-B : il installe les dépendances depuis `uv.lock`, et il construit K-B
lui-même, par son propre backend de construction, `uv_build`. Le 08/11, trois versions d'uv
cohabitaient :

- la CI prenait la dernière publiée, 0.13.7, faute de version fixée, et le disait dans ses 5 jobs
  (« Could not determine uv version from uv.toml or pyproject.toml. Falling back to latest. ») ;
- l'image construisait K-B avec uv 0.11.33 (`Dockerfile`) ;
- le Mac tournait sous uv 0.11.13.

La CI avertissait aussi, dans chaque job, que la borne de `pyproject.toml`
(`uv_build>=0.11.13,<0.12.0`) « does not contain the current uv version 0.13.7 » (exécution
42475069049). La CI ne testait donc pas K-B avec l'uv qui construit l'image mise en ligne.

Sabine a choisi de monter uv partout plutôt que de fixer la CI sur 0.11 (« ça me paraît plus
pérenne »). Le travail aligne la même version, 0.13.6, aux quatre endroits.

## Le comment

### 1. La borne du backend de construction

`pyproject.toml:30` :

```toml
requires = ["uv_build>=0.13.6,<0.14.0"]
```

`build-system.requires` dit quel outil construit le paquet K-B (son wheel), quand `uv sync`
l'installe dans l'environnement ou quand l'image le construit. uv compare sa propre version à cette
plage et avertit quand elle en sort : c'était l'avertissement de la CI. La borne haute `<0.14.0`
s'arrête avant la version mineure suivante : avant 1.0, une version mineure d'uv peut changer le
comportement du backend.

### 2. L'image uv du `Dockerfile`, épinglée par son tag et son digest

`Dockerfile:5-7` :

```dockerfile
# uv builds K-B with its own build backend: its version stays in the range of build-system.requires
# of pyproject.toml (uv_build>=0.13.6,<0.14.0), and is the version setup-uv installs in ci.yml.
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv
```

L'étape `uv` ne sert qu'à copier le binaire d'uv dans l'étape de construction. Le tag `0.13.6` se
lit, mais il peut être déplacé sur le registre ; le digest `sha256:…` désigne un contenu exact, que
personne ne peut changer. Docker tire le digest : le tag reste pour l'humain et pour Dependabot. Le
digest a été relu sur ghcr.io le 08/11 (en-tête `docker-content-digest` du manifeste de `0.13.6`) : il
est identique.

### 3. La version fixée dans les 5 jobs de la CI

`.github/workflows/ci.yml:18-20` (même ligne `version:` aux lignes 33, 45, 57 et 89) :

```yaml
      - uses: astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3
        with:
          version: "0.13.6" # the uv of the Dockerfile, in the uv_build range of pyproject.toml
```

L'action `setup-uv` installe uv sur le runner. Sans `version:`, elle cherche une version dans un
`uv.toml` ou dans `[tool.uv] required-version` du `pyproject.toml`, n'en trouve pas dans K-B, et prend
la dernière publiée. Avec `version:`, chaque job installe exactement 0.13.6, la version de l'image.
Les jobs `audit`, `tests`, `lint`, `types` et `tests-postgresql` lancent tous `uv sync --locked` : il
faut l'épingler dans chacun.

### 4. Dependabot ne met à jour que le `Dockerfile`

`.github/dependabot.yml:22-28` :

```yaml
    # Python stays at the 3.13 of .python-version; uv in the uv_build range of pyproject.toml. A patch
    # update of astral-sh/uv changes the version of setup-uv in the 5 jobs of ci.yml too, by hand.
    ignore:
      - dependency-name: "python"
        update-types: ["version-update:semver-minor", "version-update:semver-major"]
      - dependency-name: "astral-sh/uv"
        update-types: ["version-update:semver-minor", "version-update:semver-major"]
```

Dependabot suit les images du `Dockerfile` : pour `astral-sh/uv`, il ne proposera que les correctifs
(0.13.7, 0.13.8…) et les nouveaux digests, jamais 0.14, qui sortirait de la borne. Il ne lit pas la
ligne `version:` de `ci.yml`, qui n'est pas une image. Le commentaire, et une phrase du README
(`README.md:735-736`), disent donc de changer la CI à la main dans la même PR.

### 5. La décision écrite

`README.md:726-728` décrit maintenant la version fixée dans les cinq jobs, la même que le
`Dockerfile`, et la commande du Mac (`uv self update 0.13.6`). Le journal ADR porte la révision sur
l'entrée de l'image (#200) : « **Révisée le 2026-11-08** : uv 0.13.6 (`uv_build>=0.13.6,<0.14.0`), la
même version dans l'image, dans la CI […] et sur le Mac ; décision de Sabine : monter uv plutôt que
fixer la CI sur 0.11 (#485) » (`docs/ADR/journal-decisions-projet.md:5379-5382`).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Sens de l'alignement | Monter tout en 0.13 : décision de Sabine, plus durable. | Fixer la CI sur 0.11 : on garderait une version qui vieillit, et l'écart reviendrait à la prochaine mise à jour. |
| Version | 0.13.6, publiée le 2026-10-27, la plus récente publiée depuis au moins 7 jours (règle de l'issue, comme le délai de Dependabot). | 0.13.7, publiée le 2026-11-03 : 5 jours, sous les 7 exigés. Une version très récente peut être retirée ou corrigée en urgence. |
| Borne basse de `uv_build` | `>=0.13.6` : borne du plan validé par Sabine ; elle contient la version essayée. | `>=0.13.0`, que donnent les notes d'uv (constat 6 de la revue) : écarté par tn-orchestrateur, sans gain pour K-B. |
| Où écrire la version pour la CI | `version: "0.13.6"` dans les 5 jobs : le plan validé. | `[tool.uv] required-version` dans `pyproject.toml` (constat 2) : une seule source pour la CI et le Mac, mais un écart au plan, une nouvelle retouche de `pyproject.toml`, et uv refuserait de tourner sur le Mac tant qu'il n'est pas en 0.13.6. Écarté par tn-orchestrateur, gardé comme suite possible. |
| Où ranger la décision dans l'ADR | Une révision datée de l'entrée de l'image (#200), consigne de tn-orchestrateur. | Une entrée neuve : la décision change une décision existante, elle ne la remplace pas. |
| Mise en ligne | Aucun tag : la nouvelle image ne part en ligne que sur demande de Sabine (règle du dépôt). | Un tag après la fusion. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `gh release view 0.13.6 -R astral-sh/uv` : `2026-10-27T00:47:49Z` ; `0.13.7` : `2026-11-03T02:45:04Z` | 0.13.6 respecte le délai de 7 jours, 0.13.7 non. |
| `uvx --from uv==0.13.6 uv lock --check` : « Resolved 96 packages », code 0, `uv.lock` inchangé (relancé le 08/11 sur la branche rebasée) | `uv.lock` n'a pas à changer sous 0.13.6. |
| Digest du manifeste de `ghcr.io/astral-sh/uv:0.13.6` = `sha256:af22a52f…9986d0` | Le digest du `Dockerfile` est celui du registre. |
| `uv sync --locked` puis la suite sous 0.13.6 : 4061 passed, couverture 98,42 % (sur `b580372`, avant le rebase, qui n'a apporté que des docs) | K-B s'installe et passe ses tests sous 0.13.6, sans l'avertissement de borne. |
| CI de la PR (à venir) : aucun « Falling back to latest », aucun « does not contain the current uv version », `image-build` vert | La CI installe 0.13.6, et l'image se construit avec. |
| `uv --version` sur le Mac après `uv self update 0.13.6` (à venir, écrit dans l'ADR) | Le Mac a la même version. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi fixer la version d'uv ?** Pour que la CI teste K-B avec l'outil qui construit l'image mise
   en ligne. Avant, la CI prenait la dernière version publiée : le résultat d'un même commit pouvait
   changer d'un jour à l'autre (`ci.yml:20`, `Dockerfile:7`).
2. **Pourquoi pas la toute dernière, 0.13.7 ?** Une version doit être publiée depuis au moins 7 jours.
   C'est une protection de la chaîne d'approvisionnement : une version défectueuse ou compromise est en
   général retirée dans ce délai. Dependabot applique le même délai aux actions.
3. **Que se passe-t-il quand Dependabot propose uv 0.13.8 ?** Sa PR ne change que le `Dockerfile`. Il
   faut changer à la main les 5 `version:` de `ci.yml` dans la même PR. Rien ne le vérifie encore : c'est
   la limite de ce travail (`dependabot.yml:22-23`, « Ce qui reste »).
4. **Pourquoi un digest en plus du tag ?** Un tag peut être déplacé vers une autre image, pas un digest.
   Le digest a été relu sur le registre (`Dockerfile:7`).
5. **Pourquoi la borne haute `<0.14.0` ?** uv n'est pas encore en 1.0 : une version mineure peut changer
   le backend `uv_build`. La borne évite qu'uv construise K-B avec une version non essayée
   (`pyproject.toml:30`).

## Zones non vérifiées

- **L'image n'a pas été construite sur le Mac** : Docker n'y tournait pas. La preuve viendra du job
  `image-build` de la CI de la PR.
- **Les notes de version d'uv de 0.12 et 0.13** ont été lues par la session précédente, pas relues ici.
  Ses conclusions, dont deux revérifiées le 08/11 : Python 3.15 par défaut, sans effet (K-B est fixé par
  `.python-version` à 3.13, relu) ; archives `.tar.bz2` refusées, sans effet (`uv.lock` n'en contient
  aucune, relu) ; `--require-hashes` désormais respecté par `uv pip`, sans effet (l'audit passe par
  pip-audit, `ci.yml:25`).
- **La lecture de `required-version` par `setup-uv`** vient du message de son journal, pas d'un essai.
- **La CI de la PR et la mise à jour du Mac** sont à venir au moment d'écrire cette note.

## Ce qui reste

- **Sabine** lance `uv self update 0.13.6` sur le Mac ; sa version est écrite, datée, dans l'ADR.
- **Une seule source pour la version d'uv** (`[tool.uv] required-version` dans `pyproject.toml`, à la
  place des 5 `version:`), et un pas de CI qui compare l'étiquette `FROM ghcr.io/astral-sh/uv:<x>` du
  `Dockerfile` à la version de la CI (XS) : proposés à Sabine comme suite, avec l'effet de bord sur le
  Mac (uv refuse de tourner avec une autre version).
- **La mise en ligne** de l'image construite avec uv 0.13.6 : seulement par un tag, sur demande de
  Sabine.
