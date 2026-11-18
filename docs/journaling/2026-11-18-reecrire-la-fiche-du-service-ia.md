# Réécrire la fiche du service d'IA en phrases courtes (essai)

- **Date** : 2026-11-18
- **Branche** : `docs/readable-ai-service-sheet`
- **Issue** : #648
- **Fichier** : `documentation/service_ia_pour_docu.md` (490 lignes sur `main`, 674 après)
- **Série** : suit [la mise en forme des fiches restantes](2026-11-18-mettre-en-forme-les-fiches-restantes.md), qui a
  rendu les fiches accessibles sans toucher à leur style.

## Le pourquoi

La fiche du service d'IA est une preuve pour le jury : elle dit ce qu'est le déploiement de `gpt-6.1-sol`, qui y
accède, comment il s'installe, se teste, et ce qu'il reçoit. Sur `main`, elle est exacte mais dense. Une phrase y
porte souvent trois faits reliés par des deux-points et des points-virgules. Des termes comme « déploiement »,
« identité managée » ou « point d'arrêt » y sont employés sans être définis. Les renvois `fichier:ligne`
coupent le texte. Cet essai teste une autre forme sur une seule fiche, sans changer ses faits, pour que Sabine
juge si elle se lit mieux avant de l'étendre.

## Le comment

### Une idée par phrase, chaque terme défini à sa première apparition

Sur `main`, l'introduction tenait en une phrase à deux-points et parenthèse :

```
Cette fiche documente le service d'IA de K-B: le déploiement du modèle `gpt-6.1-sol` dans Microsoft Foundry
(anciennement Azure AI Foundry), fait à la main dans le portail, hors du code de K-B.
```

Elle devient (`documentation/service_ia_pour_docu.md:7-11`) :

```
Cette fiche documente le service d'intelligence artificielle (IA) de K-B. Ce service est le déploiement d'un modèle
de langage, `gpt-6.1-sol`, dans Microsoft Foundry. Un déploiement est la mise à disposition d'un modèle par une
plateforme. Microsoft Foundry, anciennement Azure AI Foundry, est la plateforme de Microsoft qui héberge des modèles
```

Le sigle IA est développé, « déploiement » est défini avant d'être employé, et la parenthèse devient une phrase.
La même règle vaut dans toute la fiche (variable d'environnement, en-tête HTTP, identité managée, conteneur, rejeu).

### Une cause écrite, et sourcée quand le dépôt ne la donne pas

Sur `main`, le cache de la consigne tenait en une ligne : « sans point d'arrêt, qui n'écrit aucun cache ». Le
lecteur ne savait ni ce qu'est un point d'arrêt, ni pourquoi son absence coupe le cache. La fiche le dit
maintenant (`documentation/service_ia_pour_docu.md:474-477`) :

```
caching</span> » de Microsoft Learn définit ce terme. Un point d'arrêt marque la fin du début de demande que le
cache peut réutiliser: <q lang="en">mark the end of a reusable prompt prefix</q>. En mode explicite, seuls les
points d'arrêt posés dans la demande servent au cache. L'API IA n'en pose aucun, donc ce réglage n'écrit aucun
```

La définition vient de la page « Prompt caching » de Microsoft Learn, ajoutée aux « Sources » (`:662-663`). Le
« donc » ne relie que deux faits prouvés : la page (le mode explicite n'écrit qu'aux points d'arrêt) et le code
(l'API IA n'en pose aucun, `ai_api/connectors/llm_client.py:412-417`).

### Les renvois sortis du texte, réunis dans « Vérifier cette fiche »

Le texte courant ne cite plus de `fichier:ligne`. Chaque fait tiré du dépôt a sa ligne dans un tableau à trois
colonnes, placé avant « Sources » (`documentation/service_ia_pour_docu.md:566-578`) :

```
## Vérifier cette fiche

Le tableau suivant donne, pour chaque fait de la fiche tiré du dépôt, le fichier qui le prouve ou la source qui le
dit. Le code cité est celui de `main` au commit `cc3d8eaf` (2026-11-18). Les chemins du code de K-B (`ai_api/…`,
```

Le tampon « au commit `cc3d8eaf` » y a migré depuis l'introduction : il date les renvois, et ils sont tous là. La
colonne « Section » rattache chaque fait à la section qui l'affirme. Le tableau est annoncé par une phrase, comme
le veut la forme accessible des fiches.

### Ce qui ne bouge pas

Les titres de section, les quatre blocs de code et le schéma Mermaid sont identiques à `main`. Une seule section
est nouvelle, « Vérifier cette fiche ». Les commandes `az` du bloc de « L'installation » gardent leurs commentaires.

## Choix faits et options écartées

- **Renvois réunis dans un tableau, plutôt que laissés en fin de phrase** : la lecture suivie n'est plus coupée,
  et le jury garde la preuve de chaque fait. Écarté : des notes de bas de page, que le site MkDocs n'active pas
  aujourd'hui (aucune extension `footnotes` dans `mkdocs.yml`), et qui auraient ajouté un réglage.
- **Définir les termes dans le texte, plutôt que dans un glossaire** : le lecteur trouve la définition là où il
  bute. Écarté : un glossaire, une page de plus à tenir et un aller-retour à chaque terme.
- **Sourcer la définition du point d'arrêt** : la première version la donnait sans source ; time-knight a demandé
  une source. Microsoft Learn la donne, lue par Context7 et par une recherche web le 2026-11-18.
- **Lignes longues gardées** : `documentation/` n'a pas de règle de longueur de ligne, et le rendu n'en dépend pas.
- **Forme seule, aucun fait changé** : imposé par la décision de Sabine sur l'essai. Le fait nouveau trouvé en
  route (le cache de la consigne peut contenir des items) n'est pas écrit : il va dans « Left out of the plan ».

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `uv run --locked --only-group docs mkdocs build --strict` : code de sortie 0, aucun avertissement de MkDocs | liens, ancres et menu valides |
| Comparaison des blocs entre trois accents graves, `main` et branche : identiques (4 blocs) | aucune commande changée |
| Comparaison des titres : seul `## Vérifier cette fiche` est nouveau | le plan de la fiche est gardé |
| Recherche d'une espace avant « : » ou « ; » hors code : 0 | règle typographique de Sabine tenue |
| Recherche des caractères `Cc` et `Cf` hors tabulation et retour à la ligne : aucun | aucun caractère invisible |
| Deux relectures neuves (opus, effort high), la seconde sur le delta : constats appliqués | chaque fait et chaque renvoi comparé aux deux versions |
| Lecture de la page servie en local par Sabine | l'avis de la lectrice visée |

## Ce que tu dois pouvoir défendre

1. **Un fait a-t-il changé ?** Non. Les blocs de code et les titres sont identiques. Chaque phrase réécrite a été
   comparée à l'originale par deux relectures neuves. Les seuls ajouts sont des définitions et une source.
2. **Pourquoi la fiche est-elle plus longue (490 → 674 lignes) ?** Les définitions, une phrase par idée, et le
   tableau « Vérifier cette fiche », environ 60 lignes. La longueur sert la lecture, pas l'ajout de faits.
3. **Comment le jury vérifie-t-il un fait ?** Par la ligne du tableau qui le porte, au commit `cc3d8eaf` :
   `documentation/service_ia_pour_docu.md:566-569`.
4. **Pourquoi dire que le cache est coupé ?** Parce que le code n'envoie aucun point d'arrêt
   (`ai_api/connectors/llm_client.py:412-417`), et que la page de Microsoft dit qu'en mode explicite seuls ces
   points servent au cache (`documentation/service_ia_pour_docu.md:474-477`). La mesure du 2026-10-17 sur
   `gpt-6-luna` le confirme : `cache_write_tokens` à 0 sur 20 réponses.

## Zones non vérifiées

- La coupure du cache sur `gpt-6.1-sol` n'a pas été mesurée : la fiche le dit déjà, et le client ne suit pas ce
  champ.
- La date `ms.date` de la page « Prompt caching » n'a pas été relevée : écrit dans « Sources ».
- La lecture au lecteur d'écran n'a pas été faite.
- L'effet de la forme sur un lecteur autre que Sabine n'est pas mesuré.

## Ce qui reste

- Étendre la forme aux autres fiches : décision de Sabine, après cet essai.
- Le thème du site de la doc (un seul menu, une barre de navigation, la charte du back office), remarqué par
  Sabine pendant la lecture : son issue et sa PR à part.
- Le fait nouveau sur le cache de la consigne qui peut contenir des items : hors de l'essai, laissé de côté.
