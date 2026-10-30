# Le contrat du compte rendu des tendances, et sa conformité

- **Date** : 2026-10-30
- **Branche** : `docs/trend-report-contract`
- **Issue** : #364 (incrément 1 sur 7 ; le code est #365 à #370)
- **Fichiers** : `docs/tendances.md` (nouveau), `docs/ADR/journal-decisions-projet.md`,
  `docs/registre-traitements.md`, `docs/specs-collecte.md`, `docs/bigquery.md`, `MEMORY.md`

## Le pourquoi

GH Archive remplit la table `trend` à chaque collecte (les dépôts qui gagnent le plus d'étoiles
sur 3 jours), mais rien ne la rend lisible. Sabine veut un compte rendu deux fois par semaine dans
le coffre, où le modèle choisit au plus 5 dépôts qui ressortent et dit pourquoi. La conception a été
faite par time-knight le 29/10 et approuvée par Sabine ; le code sera écrit par time-knight, dans un
autre worktree.

Cette PR ne contient aucun code. Elle écrit ce qui doit exister **avant** le code :
- le **contrat** (`docs/tendances.md`), pour que #365 à #370 se codent sans le plan de time-knight,
  qui n'est pas dans K-B ;
- le **registre des traitements**, parce que `conformite.md` demande de l'écrire avant le premier
  envoi de données au modèle ;
- la **conclusion sur les conditions de GitHub**, parce que `conformite.md` demande de vérifier
  qu'une source ne s'oppose pas à la collecte avant de la coder ;
- la **limite de GH Archive**, parce que le compte rendu ne doit pas présenter un échantillon comme
  un total.

## Le comment

### 1. Un post-traitement qui ne garde rien

```
C'est du **post-traitement**, pas de l'ETL : rien de ce qui est lu sur GitHub n'est gardé, ni dans
le brut ni dans la base.
```
`docs/tendances.md:13`

C'est la phrase qui commande le reste. Le compte rendu lit la base (`trend`, par l'API de données),
lit GitHub, appelle le modèle et écrit un fichier dans le coffre, mais il n'écrit ni brut ni ligne de
base. Conséquences : pas de nouvelle source dans l'ETL, pas de nouvelle durée de conservation, et le
registre peut dire « rien gardé chez K-B ». Le seul état est le registre des comptes rendus
(`trend_reports.json`), tenu par `kb` et pas par l'API IA, qui reste sans état (règle 7 de `poc.md`).

### 2. Le registre des comptes rendus, et les arrêts avant la demande

```
| Registre illisible | Arrêt avant toute demande, code 2 (`ExitCode.NOT_STARTED`) |
```
`docs/tendances.md:69`

La période d'un compte rendu part de la dernière fenêtre du précédent. Sabine a voulu que le code
garde ce point de départ (« Je préfèrerais que le code garde un registre », 29/10, 19:33) plutôt
que de relire le dernier fichier du coffre : le coffre reste un lieu où K-B écrit sans lire. Un
registre illisible arrête tout avant la demande : on ne devine pas une période. C'est le même motif
que `collection_state.json`, avec la même fonction d'écriture atomique.

### 3. Des critères calculés par le code, avant le modèle

```
- **Durable** : dans le top 30 de deux fenêtres **sans jour commun**, lues sur la période et les 2
```
`docs/tendances.md:98`

Le modèle ne calcule rien. Le code calcule le rang et trois critères (durable, nouveau, en
accélération) ; le modèle choisit parmi des candidats déjà qualifiés, et le code revérifie que
chaque critère annoncé est un critère calculé. Les fenêtres glissent d'un jour et durent 3 jours :
deux fenêtres qui finissent à D et D+2 partagent un jour, d'où « sans jour commun » (D et D+3).
Écrire ces définitions exactement dans le contrat permet d'en faire des tests (section « Ce qui le
prouve »).

### 4. Deux niveaux de refus de la sortie du modèle

```
| `ref` faux, lien, image, balise (`MARKUP`, `ai_api/stages/writing.py:75`), accent grave, `~~~`, motif de commande | refuse la sortie entière du dépôt |
```
`docs/tendances.md:192`

Une sortie qui contient un lien ou une commande peut venir d'une injection dans un README : on ne
garde rien de ce dépôt. Une sortie qui n'a qu'un défaut de fond (un fait introuvable, une borne
dépassée) ne perd que ce texte, et le fichier le dit. C'est la même séparation que pour les fiches
de veille (`docs/fiches-veille.md`, « Contrôles »).

### 5. Les conditions de GitHub, avec leur risque restant

```
  - **Risque restant, dit tel quel** : l'AUP §7 n'autorise que la recherche (informations publiques
```
`docs/specs-collecte.md:193`

La conclusion (décision de Sabine du 30/10) est écrite avec la source « API GitHub », parce qu'elle
vaut pour toute la collecte GitHub, pas seulement pour les tendances. Elle ne cache pas la zone
grise : l'AUP §7 n'autorise à la lettre que la recherche et l'archivage. Sabine a accepté ce risque
en le nommant, et l'usage retenu est le plus proche : la recherche, minimisée.

### 6. La limite de GH Archive, sans réécrire le passé

```
- **Limite mesurée le 2026-10-29 : environ 1 % des étoiles** (mesures de time-knight, lues le
```
`docs/specs-collecte.md:682`

Le 11/10, K-B avait lu une baisse comme des tables BigQuery appauvries (`docs/bigquery.md`), en ne
vérifiant que l'existence et la taille des fichiers horaires. Le 29/10, time-knight a compté le
fichier de 12 h UTC de deux jours : BigQuery est **cohérent avec** les fichiers, c'est ce que GH
Archive reçoit qui a chuté. La note du 11/10 n'est pas réécrite : elle reçoit un renvoi
(`docs/bigquery.md:146-149`), pour qu'on voie ce qu'on savait à chaque date.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté |
|---|---|---|
| Un contrat complet dans `docs/tendances.md` (définitions, états, cas de test) | Le plan de time-knight n'est pas dans K-B ; le relecteur a demandé que le contrat suffise à coder | Un contrat qui renvoie au plan (illisible par un tiers) |
| Les conditions de GitHub dans `specs-collecte.md` | C'est là que K-B consigne l'accès et la conformité de chaque source (le `robots.txt` de tldr.tech y est) | Dans `tendances.md` (la conclusion vaut pour toute la collecte) |
| « Cohérent avec », pas « fidèle » | La mesure ne compte qu'une heure sur deux jours (précision de time-knight) | « Fidèle » (affirme plus que mesuré) |
| Le contenu des appels des tendances tracé sous `KB_TRACE_CONTENT`, comme les fiches | Décision de Sabine du 30/10 (~16:12Z) : le plan disait « jamais tracé », ce qui revenait sur sa décision D1 du 27/10 sans qu'elle l'ait vu comme tel ; signalé par la session, soumis par time-knight | Une exception pour les tendances (« jamais tracé ») |
| Les décisions de Sabine reprises dans une seule entrée ADR, avec leurs heures | Une entrée par sujet, comme les entrées voisines du journal | Une entrée par décision (13 entrées pour un sujet) |
| `docs/jeton-github.md` et `.env.example` laissés à #367 | Mission : ils vont avec le code qui introduit le second jeton | Les écrire ici (doc d'un réglage qui n'existe pas encore) |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run pytest` : 2782 passed, 11 deselected | Aucun code touché ne casse (aucun `.py` dans le diff) |
| `uv run ruff check --no-cache`, `ruff format --check`, `mypy --strict` : verts | Idem |
| Script de contrôle : aucun caractère `Cc`/`Cf` hors tabulation, saut de ligne, U+200D | Pas de caractère invisible écrit par l'outil (consigne de `MEMORY.md`) |
| Script de contrôle : chaque lien relatif `.md` ajouté pointe vers un fichier existant | Les renvois du contrat et du registre ne sont pas cassés |
| Identifiants cités (`DIGEST_SUBJECTS`, `MIN_SECONDS_FOR_LLM_REQUEST`, `write_new_sheet`, `MARKUP`…) cherchés dans `src/` | Ils existent au commit `8898095` |

## Ce que tu dois pouvoir défendre

1. **Pourquoi pas lire la période dans le dernier compte rendu du coffre ?** Le coffre est le lieu
   où K-B écrit, jamais où il lit (journal ADR, « Coffre : organisation ») ; un fichier renommé ou
   déplacé par toi fausserait la période. Le registre est un fichier de `KB_DATA_DIR`
   (`docs/tendances.md`, « Registre des comptes rendus »).
2. **Envoyer un README au modèle, est-ce permis par GitHub ?** Ce n'est pas de l'entraînement (D.9
   des Terms ne vise que l'entraînement d'un système d'IA commercial) ; le risque restant est l'AUP
   §7, nommé et accepté (`docs/specs-collecte.md`, « Conditions d'utilisation »).
3. **Où sont les données personnelles ?** Le login du propriétaire dans `owner/repo`, et un nom
   possible dans un texte libre. Les `@login` deviennent `@user`, les adresses `[email]` ; rien n'est
   gardé chez K-B ; les traces ne portent que des `ref` (`docs/registre-traitements.md`, « Envoi des
   dépôts au modèle du compte rendu des tendances »).
4. **Que vaut un compte de GH Archive ?** Environ 1 % des étoiles, mesuré le 29/10 : un échantillon.
   Le compte rendu le dit et ne départage pas des rangs proches (`docs/tendances.md`, « Limite de GH
   Archive »).
5. **Que se passe-t-il si le modèle choisit mal ?** Le code revérifie ; après une relance, le fichier
   est quand même écrit, en compte rendu factuel « choix non fait », et la période avance
   (`docs/tendances.md`, « Défenses et échecs »).

## Zones non vérifiées

- Les **références `fichier:ligne`** du contrat viennent du plan de time-knight (vérifiées par lui au
  commit `8898095`) ; ici, seuls les identifiants ont été cherchés, pas chaque numéro de ligne.
- Les **conditions de GitHub** et les **mesures de GH Archive** n'ont pas été relues ni refaites dans
  cette session : elles sont reprises de la mission et des messages de time-knight (lues les 29 et
  30/10).
- La **correspondance entre cas d'échec GitHub et états nommés** (`github_unavailable` pour un 5xx
  après relance, `github_timeout`, `github_invalid_response`) est déduite des noms du plan, qui ne
  les associait pas un à un ; à confirmer au code de #367.
- Les titres des deux pages de la limite de GH Archive n'ont pas été lus : elles sont citées par leur
  URL seule.

## Ce qui reste

- Le code : #365 (déplacements vers `core`), #366 (compte rendu factuel), #367 (fiche GitHub, second
  jeton, `docs/jeton-github.md`, `.env.example`), #368 (choix), #369 (rédaction), #370 (essai réel,
  seuils), par time-knight.
- Une ligne des conditions de GitHub dans `.claude/rules/conformite.md` : time-knight tient ce
  fichier.
