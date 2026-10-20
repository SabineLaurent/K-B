# Sortir le LLM juge du contrat des fiches

- **Date** : 2026-10-20
- **Branche** : `docs/digest-spec-without-judge`
- **Issue** : #277
- **Fichiers principaux** : `docs/fiches-veille.md`, `docs/registre-traitements.md`, `README.md`,
  `src/k_b/ai_api/digests.py`
- **Commits** : ceux de la branche sur `main` (`git log origin/main..HEAD`) : la spec et le
  README, le registre, les commentaires du code, puis les corrections de la revue et cette note.
  La liste de commits fournie au début de la note contenait aussi l'historique de `main`, et la
  liste des fichiers venait d'un `main` local en retard : seuls les quatre fichiers ci-dessus
  changent (`git diff --stat origin/main...HEAD`).
- **Série** : suit [Consigner les décisions de cadrage du 20/10](2026-10-20-consigner-les-decisions-de-cadrage.md)
  (#275), qui a écrit la décision appliquée ici.

## Le pourquoi

Le 20/10, tu as décidé que le LLM juge sort du contrat des fiches : « on voit plus tard » (journal
ADR, 2026-10-20, « Squelette E1 E3 : cadrage du 20/10 », décision 2). Le juge était un second
modèle qui devait relire chaque affirmation gardée par la fidélité et retirer celles que ses
items n'appuient pas. Il n'a jamais été codé : #223 (le code) et #224 (l'étalonnage) restent
ouvertes, hors du squelette.

La spec `docs/fiches-veille.md` est le contrat de l'API IA, écrit avant le code. Elle décrivait
pourtant un parcours, une réponse et des métriques avec le juge, que le produit n'a pas : c'est
la contradiction relevée par le rapport du *product owner*. Ce travail aligne la spec, le registre
des traitements, le README et deux commentaires du code sur ce que fait le produit. Aucun
comportement ne change : c'est une PR de documentation, plus deux commentaires de code.

## Le comment

### 1. Ce que le code fait déjà : le constat de départ

Avant d'écrire, chaque mention du juge a été relue face au code de `main`. Le code ne connaît
que deux étapes :

```python
type Stage = Literal["classify", "write"]
```
(`src/k_b/ai_api/digests.py:46`)

et sept contrôles refusés, sans `claim_id`, la valeur que le juge devait ajouter
(`src/k_b/ai_api/connectors/llm_client.py:54-62`). Aucun `claims_judged_removed`, aucune variable
`KB_LLM_JUDGE_MODEL`. Chaque réécriture de la spec suit donc le code : `stage` vaut `classify` ou
`write` dans les métriques, et `write` seul dans `failed_subjects`, car un classement en échec fait
échouer toute la demande.

### 2. Retirer la section « Juge », garder ce qui n'en dépendait pas

La section « Juge » faisait environ 345 lignes (entrée, sortie, contrôle 8, échecs, réglage, coût,
limites, révision, étalonnage). Elle est retirée en entier, sauf deux morceaux qui ne parlaient
pas du juge :

- « Ce que la spec ne couvre pas » devient une section de premier niveau, avec ses trois puces
  sans juge (complétude par un modèle, français et style, lint périodique) ;
- une limite de la rédaction, cachée dans les limites du juge, passe dans « Réponse » :

```markdown
**Limite** : le `text` d'une affirmation peut recopier une adresse mail d'un item (section
« Entrée du modèle » : une adresse mail n'est pas masquée) ; elle revient dans la
réponse, car le contrôle 6 ne la refuse pas.
```
(`docs/fiches-veille.md:444-446`)

Le retrait s'est fait par un script qui vérifiait d'abord les bornes de la section (le titre
`## Juge`, puis `## Métriques`) et que chaque puce gardée était bien recopiée du bloc retiré. Un
retrait de 345 lignes ne se relit pas à l'œil.

### 3. La seule phrase qui parle encore du juge

Le critère de #277 demande qu'il ne reste qu'une ligne avec « juge » : celle qui dit que le juge
est hors du contrat, et où lire son contrat retiré.

```markdown
- La **vérification du sens** de chaque affirmation, que la fidélité ne fait pas (« Ce qu'elle ne
  vérifie pas »), est hors du contrat depuis le 2026-10-20 (journal ADR, « Squelette E1 E3 :
  cadrage du 20/10 », décision 2). Le contrat retiré du LLM juge : section « Juge » de
  `git show 4bb57c7:docs/fiches-veille.md` ; son code (#223) et son étalonnage (#224) restent
```
(`docs/fiches-veille.md:563-566`)

La puce part du **besoin** (vérifier le sens) et non du juge, car la section dit « rien n'est
décidé ici ». Le commit `4bb57c7` est le dernier de `main` qui touche le fichier : le contrat y est
entier. On écrit `git show 4bb57c7:<fichier>` pour qu'on lise le fichier tel qu'il était, et pas
le diff de ce commit, qui parle d'autre chose (`kb write-tops`).

### 4. Ce que la fidélité ne vérifie pas : une limite, plus un renvoi

La spec confiait au juge le sens de la phrase, le nombre non déclaré et la traduction. Sans juge,
ce manque revient (l'ADR le dit : « Conséquence »). Il est donc écrit comme une limite :

```markdown
  faible. **Limite** : le sens de la phrase, le nombre non déclaré et la traduction ne sont
  vérifiés par aucune étape (section « Ce que la spec ne couvre pas ») ; la fidélité reste sans
  modèle.
```
(`docs/fiches-veille.md:535-537`)

### 5. Les nombres qui découlaient du juge

Le juge ajoutait un appel par sujet. Sans lui, au plafond : 6 classements ou plus et 8 rédactions,
soit environ 14 appels et 28 tentatives (`docs/fiches-veille.md:161-166`), et le pire cas de
l'échéance devient « 14 appels de 210 s » (l. 136). La mesure de #158 (98 s), faite avec le juge,
reste telle quelle, avec une phrase qui dit ce qu'elle comptait :

```markdown
  section « HTTP ») ; 200 s gardent 40 s pour le dernier appel en cours et la réponse. Cette
  mesure comptait un appel de plus par sujet, la vérification du sens, sortie du contrat le
  2026-10-20 (section « Ce que la spec ne couvre pas » ; `core/config.py`). Options
```
(`docs/fiches-veille.md:130-132`)

Le commentaire de `src/k_b/core/config.py:181` (« the judge included ») reste, comme le demande
le critère : il décrit une mesure faite avec le juge.

### 6. Le registre, le README et le code

- Registre, « Destinataires » (l. 52) et « Destinataire » (l. 81) : plus rien n'est envoyé au juge.
  La l. 81 garde l'engagement qui y était écrit pour le juge, et qui couvre maintenant le
  rédacteur : « Le registre est mis à jour avant tout envoi de données réelles à un autre
  déploiement. »
- `README.md:124` renvoyait à « Coût », une sous-section du juge : il renvoie à « Lecture
  plafonnée », qui donne les appels d'une demande.
- `src/k_b/ai_api/digests.py` : la docstring n'annonce plus le juge, et le commentaire des
  `facts` dit « Kept for the checks of #207; never in the answer. » (l. 80).

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| Retirer la section entière ; le contrat reste lisible par `git show 4bb57c7` | Le critère de #277 ; une spec dit ce que fait le produit (ADR, décision 2) | Garder le juge dans le contrat sans le coder : l'option écartée par l'ADR |
| Garder `stage` dans `failed_subjects`, avec la seule valeur `write` | La doc décrit le code (`FailedSubject.stage`, `digests.py:109`) ; tranché par time-knight, délégation de Sabine du 15/10 | Retirer le champ : changerait la réponse, hors de #277 (signalé dans la PR) |
| Préciser les 98 s par « un appel de plus par sujet, la vérification du sens » | Sans elle, la mesure se lit comme celle de la chaîne sans juge (constat de la revue) | Écrire « juge compris » : une seconde ligne au `grep` du critère |
| « 14 appels de 210 s », la forme de `main` | Tranché par time-knight : pas de « au moins » sans ligne qui le fonde | « 14 appels ou plus de 210 s » : se lit « 14 appels, ou plus de 210 s » |
| Garder dans le registre la mise à jour avant un autre déploiement | Seul engagement écrit avant un changement de déploiement ; le rédacteur garde un repli (tranché par time-knight) | Le retirer avec le juge : un changement de déploiement ne serait plus précédé de rien |
| Ne pas garder les mesures de #158 de « Coût » (médianes, jetons d'une rédaction) | Rien ne les cite ; elles restent lisibles en `4bb57c7` (tranché par time-knight) | Les déplacer : un paragraphe sans lecteur |
| Suivre la mission : revue, note et `pytest` une fois | La mission prime ; le critère dit que ces étapes « ne s'appliquent pas », il ne les interdit pas | Les sauter : 345 lignes retirées sans autre relecture |

## Preuve

| Commande ou sortie observée | Ce qu'elle démontre |
|---|---|
| `grep -ciE "juge\|judge" docs/fiches-veille.md` → 1 | Une seule ligne parle encore du juge (critère, puce 1) |
| `grep -nE "jug[ée]\|claim_id\|verdict\|#22[234]\|\b(22\|44) appels\|phase 3" docs/fiches-veille.md` → l. 565-566 | Les formes que le premier `grep` ne voit pas (« jugé », `claim_id`, #223) ne restent que dans la puce gardée |
| `grep -n -A4 "Ce qu'elle ne vérifie pas"` | La limite reste écrite, sans renvoi au juge (puce 2) |
| `grep -c KB_LLM_JUDGE_MODEL docs/registre-traitements.md` → 0 ; seule la l. 85 contient « juge » (« qu'il juge potentiellement abusif », pas le LLM juge) | Le registre n'envoie plus rien au juge (puce 3) |
| `grep -rniE judge src/k_b` → `config.py:181` seule | Les commentaires sont accordés, la mesure gardée (puce 4) |
| `gh issue view 223` et `224` → `OPEN` | #223 et #224 restent ouvertes (puce 5) |
| `uv run pytest -q` → 1956 passed ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` verts | Les deux commentaires changés ne cassent rien |

## Ce que tu dois pouvoir défendre

1. **Pourquoi retirer le contrat plutôt que le marquer « non codé » ?** Une spec qui décrit des
   champs de réponse et des métriques absents ment au lecteur et à qui code #156 : c'est la
   contradiction relevée par le *product owner*, et l'option écartée par l'ADR (décision 2). Le
   contrat n'est pas perdu : `git show 4bb57c7:docs/fiches-veille.md` (`fiches-veille.md:565-566`).
2. **Sans juge, qu'est-ce qui garantit qu'une fiche dit vrai ?** Rien, pour le sens : la fidélité
   vérifie que chaque fait déclaré existe dans l'item cité, pas que la phrase dit vrai. C'est écrit
   comme une limite (`fiches-veille.md:535-537`). Une phrase fausse appuyée sur des faits vrais
   passe ; c'est aussi écrit dans « Injection d'instructions ».
3. **Pourquoi `stage` reste-t-il, s'il n'a qu'une valeur ?** Parce que le code l'a
   (`FailedSubject.stage`, `digests.py:109`) et que la doc décrit le code. Le retirer change la
   réponse : c'est un travail de code, signalé dans la PR.
4. **Le registre change-t-il ce qui part chez Microsoft ?** Non : l'API IA n'appelle pas le juge
   (`Stage`, `digests.py:46`), donc ce que le code envoie ne change pas ; le registre cesse
   d'annoncer un second envoi que le code ne fait pas. L'engagement de mettre le registre à jour
   avant un autre déploiement est gardé (`registre-traitements.md:81`).
5. **Pourquoi la mesure de 98 s n'est-elle pas refaite ?** Elle reste au-dessus de la chaîne réelle
   (un appel de moins par sujet), donc la marge sous les 240 s de l'ingress tient ; la refaire
   demanderait un essai réel, hors de cette PR de doc.

## Zones non vérifiées

- La chaîne sans juge n'a pas été mesurée : on sait seulement qu'elle est plus courte que 98 s.
- L'essai de #158 a appelé le juge (sa mesure de 98 s le compte, `core/config.py:181`) : ce qu'il
  a envoyé alors n'est pas relu ici ; ce travail ne touche que ce que le code envoie aujourd'hui.
- Le repli du rédacteur (gpt-5.6-luna, ADR du 16/10) n'est nommé nulle part dans le registre, ni
  sur `main` ni ici : manque antérieur à #277, relevé par la relecture du constat 1 et signalé dans
  la PR.

## Ce qui reste

- Le juge codé (#223) et son étalonnage (#224) : hors du squelette, « on voit plus tard ». Leurs
  corps d'issue renvoient encore à la section « Juge » de `main`, retirée ici : signalé dans la
  PR.
- La spec décrit encore des étapes non codées (fidélité #207, contrôle 6 #206, route et métriques
  #156) : c'est le contrat qui reste, hors de #277.
- `.claude/rules/poc.md` parle encore du « POC en conteneurs » : à modifier par toi (`.claude/`).
