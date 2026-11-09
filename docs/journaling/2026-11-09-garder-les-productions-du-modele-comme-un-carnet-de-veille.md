# Garder les productions du modèle comme un carnet de veille

- **Date** : 2026-11-09
- **Branche** : `docs/model-productions-retention`
- **Issue** : #530 (l'issue « Plus tard » qui l'accompagne : #531)
- **Fichiers** : `docs/registre-traitements.md` (fiche 1, « Durée de conservation » ; procédure de tri,
  étape 9), `.claude/rules/conformite.md` (ligne 14)
- **Série** : [la purge de la base et du brut](2026-11-04-purger-la-base-et-le-brut-hors-de-l-etl.md), qui
  tient les durées de la base et du brut ; cette note-ci traite de ce que la purge ne touche pas.

## Le pourquoi

Le registre des traitements disait seulement des comptes rendus du modèle qu'ils n'étaient « jamais purgés
par K-B ». Il ne disait ni combien de temps ils sont gardés, ni qui les supprime, ni où ils se trouvent.
Le 09/11, Sabine a tranché : les productions du modèle sont gardées sans limite, comme un carnet de veille,
et supprimées à la main. Ces productions sont les comptes rendus de veille par sujet, le compte rendu des
tendances, et plus tard les fiches de lecture et les pages du wiki. Le livrable E4 (éco-conception,
RGESN 5.8) cite le registre : la règle doit y être écrite, avec sa justification RGPD. Une durée sans
chiffre est permise, à condition d'en donner le critère (RGPD art. 13.2.a, déjà cité par le registre).

La PR copie aussi la règle de conformité de time-knight, qui corrige la date du RGESN.

## Le comment

### 1. La règle, dans la fiche 1

`docs/registre-traitements.md:58`, rubrique « Durée de conservation » :

> Les productions du modèle (…) sont gardées sans limite, comme un carnet de veille que l'utilisatrice
> tiendrait à la main, et supprimées à la main par elle (décision de Sabine du 2026-11-09, #530).

L'étape 9 de la procédure de tri (`docs/registre-traitements.md:218`) la reprend en une phrase et renvoie
à la fiche 1 : la règle n'est écrite en détail qu'à un seul endroit.

La phrase des 99 ans (« C'est un critère et non un chiffre (…) décision de Sabine du 2026-10-19 ») retrouve
sa place, juste après les fiches des tops. Elle a été écrite pour les tops (`4bb57c7`, « the retention of
the tops »), avant que les comptes rendus n'existent. Ceux-ci avaient été glissés entre les deux.

### 2. Où sont les productions, aujourd'hui et demain

Aujourd'hui, elles sont dans le coffre du Mac. Le code qui les publierait existe déjà (#413), mais
l'infrastructure n'a pas encore le conteneur `watch` :

```bicep
// container of the smoke test alone; #420 adds the containers of the exchanges and their protections.
```
(`infra/modules/exchange-storage.bicep:2`)

Elles ne seront en ligne qu'avec #420 (le partage `job-data` et le conteneur `watch`) et le job qui les
écrit, `caj-kb-digest-watch` (#423). Elles existeront alors en trois copies : le coffre de travail des jobs
(un dossier de `job-data`), `watch` et le coffre du Mac. C'est pourquoi le registre écrit cette partie au
futur.

### 3. La limite de la suppression à la main

La publication n'envoie que ce que le conteneur n'a pas, et ne remplace jamais rien :

```python
container_client.upload_blob(sheet_name, content, overwrite=False)
```
(`src/k_b/jobs/watch_publication.py:146` ; la docstring du module, lignes 1 à 3, le dit aussi :
« each sheet the container lacks is sent to it (…) never replacing a blob »)

Deux conséquences, écrites comme limite au registre :
- une fiche supprimée de `watch` y revient tant qu'elle reste dans le coffre de travail ;
- une fiche corrigée pour un effacement (étape 5) ne remplace jamais celle déjà publiée.

S'y ajoute ce que prévoit #420 :
- Sabine n'aura que la lecture sur `watch` ;
- un blob supprimé restera récupérable 30 jours ;
- ses versions resteront tant que personne ne les efface, et personne n'aura le droit `deleteBlobVersion`.

La règle « supprimées à la main » reste celle de Sabine. Le registre dit où elle ne tiendra pas encore, et
renvoie à #531.

### 4. La justification RGPD

Le registre dit que les données personnelles des productions sont publiques et réduites à ce qui nomme la
source citée.

**Un login GitHub vient du titre d'une release**, qui commence par le nom du dépôt :

```python
title=f"{release.repository} {release.name or release.tag_name}",
```
(`src/k_b/etl/sources/github/releases.py:182`)

Ce titre est écrit tel quel dans un compte rendu, avec l'URL de la release
(`src/k_b/post/digest_sheets.py:137-141`). Le compte rendu des tendances écrit de même le nom `owner/repo`
de chaque dépôt (`src/k_b/post/trend_report_sheets.py:277`).

**Il n'y a aucun nom d'auteur de papier.** La mission le supposait, mais le code le contredit : l'API IA ne
lit pas les auteurs.

```python
    """An answer of the data API: the fields read are typed, the others ignored, the authors
    among them."""
```
(`src/k_b/ai_api/connectors/data_api_client.py:72-73`)

**La limite, enfin.** Seuls les `@login` des notes d'une release sont masqués avant le modèle :

```python
LOGIN_FIELDS_BY_KIND: dict[WatchKind, tuple[str, ...]] = {"release": ("body",)}
```
(`src/k_b/ai_api/watch_items.py:94`)

Un nom ou une adresse mail écrits en texte libre peuvent donc être recopiés par un compte rendu, de veille
comme des tendances. Les tendances masquent les adresses mail, mais avec des limites (`docs/tendances.md:519`).

### 5. La copie de `conformite.md`

`.claude/rules/conformite.md` est tenu par time-knight. Le fichier est remplacé par sa copie
(`8ed8d23`), qui corrige une seule ligne : `v2, 28/05/2024` devient `v2 (version 2024), 17/05/2024`, la
date du communiqué de l'Arcep.

## Choix faits et options écartées

| Choix | Retenu | Écarté, et pourquoi |
|---|---|---|
| Données personnelles citées | Logins, et la limite du nom ou du mail (décision de Sabine, sur l'écart signalé) | Les « noms d'auteurs de papiers » de la mission : faux aujourd'hui (`data_api_client.py:72-73`). Les fiches de lecture, quand elles viendront, mettront le registre à jour dans leur propre PR. |
| Limite de la suppression à la main | Écrite au registre, au futur, avec renvoi à #531 (choix 67 de Sabine) | La taire : le registre aurait promis une suppression que `watch` ne permettra pas. Changer la règle : c'est la décision de Sabine. |
| Condition de la mise en ligne | « #420 et `caj-kb-digest-watch` (#423) » | #420 seule : elle crée le stockage, aucun job. #330 : il ne planifie que `caj-kb-daily-routine` (accepté par time-knight). |
| Renvois au code | Le module, sans numéro de ligne | `fichier:ligne` : le registre n'en cite aucun ailleurs, et un numéro vieillit. Les lignes sont dans la PR et dans cette note. |
| Phrase des 99 ans | Rattachée aux fiches des tops | La laisser après les comptes rendus : elle leur attribuerait une décision du 19/10 qui ne les visait pas. |

## Preuve

| Sortie observée | Ce que ça démontre |
|---|---|
| `diff .claude/rules/conformite.md /Users/sabine/REPO_GIT/time-knight/consignes/conformite.md` : aucune sortie ; `git diff -U0` : `@@ -14 +14 @@` | La copie est exacte, et seule la ligne 14 change. |
| `grep -c "carnet de veille" docs/registre-traitements.md` → `2` | La règle est écrite, dans la fiche 1 et à l'étape 9. |
| Nombre de `|` des deux lignes changées : 3 et 6, comme sur `origin/main` ; 319 lignes | Les tableaux ne sont pas cassés. |
| Contrôle Unicode : aucun caractère `Cc` ou `Cf` ; ponctuation : 0 écart | Aucun caractère invisible, ponctuation française tenue. |
| Relecture par un sous-agent neuf (high) : 8 constats ; C4, C5, C6 et C8 tranchés par time-knight, C1 à C3 par Sabine, C7 hors du plan | Chaque fait nouveau a été vérifié contre le code de `origin/main`. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi garder sans limite, alors que le RGPD demande une durée ?** Le RGPD admet un critère à la
   place d'un chiffre (art. 13.2.a). Ici, le critère est que la production est gardée tant que
   l'utilisatrice la garde, comme un carnet. La finalité est une archive de veille personnelle, et les
   données sont publiques et minimes (`docs/registre-traitements.md:58`).
2. **Que contient un compte rendu, en données personnelles ?** Des logins GitHub, dans un titre de release
   (`releases.py:182`) ou dans `owner/repo` (`trend_report_sheets.py:277`). Aucun auteur de papier
   (`data_api_client.py:72-73`). Un nom ou un mail recopiés d'un texte libre restent possibles : c'est la
   limite écrite.
3. **Une personne demande l'effacement : que faire ?** L'étape 5 s'applique aussi à ces fichiers.
   Aujourd'hui, il suffit de modifier les fiches du coffre. Une fois #420 en place, `watch` ne suivra pas,
   faute de droit, et une fiche corrigée n'y sera jamais republiée (`watch_publication.py:146`). C'est ce
   que porte #531.
4. **Pourquoi dire « aujourd'hui sur le Mac », alors que le code de publication existe ?** Parce que
   l'infrastructure n'a pas encore de conteneur `watch` (`infra/modules/exchange-storage.bicep:2`), et
   qu'aucun job qui publie n'est déployé (`infra/deployment.json:3`).

## Zones non vérifiées

- Les droits sur `watch`, la suppression réversible et les versions viennent du plan de #420, pas d'un
  Bicep : rien n'est encore écrit dans `infra/`.
- La place du coffre de travail sur `job-data` (`KB_VAULT_DIR=/data/vault`) vient du plan de #330. Aucun
  Bicep ne la fixe encore.
- Sous `KB_TRACE_CONTENT=anomalies` ou `all`, la sortie du modèle part aussi chez Grafana. La ligne
  « Destinataires » le dit déjà, et ce réglage n'est pas posé : la PR n'y touche pas.

## Ce qui reste

- #531 (plus tard) : un index en base des productions et une suppression synchronisée aux trois endroits,
  puis une durée d'archivage par sorte.
- Les fiches des tops partent aussi dans `watch` (`src/k_b/commands/job_transfers.py:79`), mais ce ne sont
  pas des productions du modèle. Elles sont laissées hors de cette PR.
- Les fiches de lecture et le wiki diront leurs données personnelles dans la PR qui les créera.

Les autres commits et fichiers que liste l'outil de la note viennent des PR déjà fusionnées (#521 à
#529) : ils ne sont pas de cette branche (`git diff origin/main --stat` : deux fichiers).
