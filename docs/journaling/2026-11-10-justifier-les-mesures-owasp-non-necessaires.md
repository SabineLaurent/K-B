# Justifier les mesures OWASP dont K-B n'a pas besoin, et corriger l'autoévaluation

- **Date** : 2026-11-10
- **Branche** : `docs/owasp-justifications`
- **Issue** : #500
- **Fichiers** : `docs/fiches-veille.md` et `docs/specs-api.md`, sections « Sécurité : OWASP API
  Security Top 10 (2023) »
- **Série** : [2026-11-05-bornes-owasp-des-deux-api.md](2026-11-05-bornes-owasp-des-deux-api.md),
  [2026-11-08-justifier-les-ecarts-voulus-de-l-api-ia.md](2026-11-08-justifier-les-ecarts-voulus-de-l-api-ia.md)

La liste injectée des commits remonte au-delà de la branche : les commits plus anciens que `d53eb8f`
viennent de #540 (PR #546), déjà fusionnée dans `main`, comme les fichiers de code de la liste.
Cette note ne couvre que `d53eb8f`, `e8954c6` et `9b2009f`, qui ne touchent que les deux fiches.

## Le pourquoi

La certification lit l'autoévaluation strictement. Pour chacune des 10 entrées, et sur les deux API,
il faut soit une mesure tenue, avec sa preuve, soit un texte qui **démontre** que la mesure n'est pas
nécessaire dans le contexte de K-B. Accepter un risque ne suffit pas : c'est alors une mesure
nécessaire non intégrée, donc « non tenue ». L'autoévaluation disait « à justifier (#500) » à
plusieurs endroits. Elle gardait aussi des phrases écrites avant la mise en ligne (« à revoir au
déploiement »), et des renvois `fichier:ligne` décalés depuis.

## Le comment

### Une légende qui sépare « pas nécessaire » de « pas fait »

La légende distingue maintenant trois états d'une entrée (`docs/fiches-veille.md:854-856`) :

```
entrée est tenue quand toutes ses mesures applicables le sont ; elle est un écart voulu, justifié
quand ses mesures applicables sont tenues ou justifiées, au moins une justifiée ; elle est non
tenue dès qu'une mesure l'est.
```

« Non tenue » veut dire « nécessaire, non intégrée ». C'est le cas d'API4 (#501), d'API8 (#496 à
#499) et d'API10 (#522). Elles ne sont pas maquillées en écarts justifiés.

### Une justification = un argument, une limite, une réduction du risque

Chaque écart justifié suit le même patron. L'argument s'appuie sur un fait du dépôt ou une source
lue le jour même. La limite dit ce qui rendrait la mesure nécessaire. « Pour réduire le risque » dit
comment garder la limite loin (règle du 10/11). Exemple, le TLS mutuel (`docs/fiches-veille.md:959-963`) :

```
    **Limite** : une entrée externe, une route HTTP de l'environnement qui viserait l'app, ou un
    client hors de l'environnement.
    **Pour réduire le risque** : relire à chaque version `external`, `allowInsecure` et les routes de
    l'environnement, par les commandes d'API8 (« TLS, même pour une API interne »), en lecture
```

Le fait central de presque toutes les justifications est l'**entrée interne** des deux API
(`infra/modules/api-container-app.bicep:74-80`). Seules les pièces de l'environnement les
atteignent. À ce commit, la seule à appeler l'API IA est `caj-kb-smoke-test`, sur `/health` et sans
clé (`infra/deployment.json`). Le TLS mutuel, la chaîne Envoy → uvicorn et les protections externes
visent tous un client tiers, et K-B n'en a aucun.

### Le pire cas de la dépense, recalculé

Le débit (20 demandes par 24 h et par route) vit dans la mémoire de la réplique. Avec
`minReplicas: 0`, la réplique s'arrête 300 s après la dernière requête (défaut d'ACA), et la
suivante repart d'un compte à zéro (`docs/fiches-veille.md:1104-1107`) :

```
  zéro. Au pire, 20 demandes par route et par réveil, et jusqu'à 288 réveils par jour
  (86 400 s / 300 s) : 5 760 demandes par route, si chacune était instantanée. La borne qui reste est
  le quota du déploiement, 140 000 jetons par minute (`README.md`, « Budget ») : 201 600 000 jetons
  par jour, au plus environ 121 $ par jour au prix de sortie. Ce pire cas demande une clé et une
```

Le débit ne borne donc pas la dépense : seul le quota du modèle la borne. `budget-kb` ne la voit pas,
car la ressource du modèle n'a pas l'étiquette `project=k-b`. D'où la mesure non tenue, et #501.

### L'API de données suit les mêmes arguments, avec ses propres faits

Un renvoi seul ne suffisait pas (relecture, constat 2). Par exemple, un débit de 120 listes par
minute ne borne pas les connexions. L'API de données a donc sa propre puce API4
(`docs/specs-api.md:502`) : aucun processus lancé (`grep` vide sur `data_api` et `database`),
`uvicorn.run` sans `workers` (`commands/serve_data_command.py:45`). Sa dépense est tenue : l'app et
le serveur PostgreSQL sont étiquetés, et donc comptés par `budget-kb`. Son API8 passe à « non
tenue » : le durcissement, la revue et l'évaluation sont communs aux deux API.

## Choix faits et options écartées

- **API10 « non tenue »**, plutôt que « tenue » au motif que le jeton est mort : c'est le plan validé
  par Sabine (#522 encore ouverte à 16:05Z). La portée d'un jeton qui n'existe pas encore ne se
  prouve pas.
- **API9 « données de production hors production » : tenue.** La machine sert les mêmes données
  avec le même code, une clé par client et les mêmes limites. Décision : Sabine et time-knight
  (l'option écartée, laisser la phrase périmée à une autre issue, aurait gardé un état faux).
- **Citations en phrases entières**, recopiées des pages enregistrées le 2026-11-10 (tranché par
  time-knight) : une citation coupée tomberait à la lecture stricte.
- **Pas de prix d'API Management ni de Front Door dans API9** : l'argument tient sans eux (aucun
  trafic du dehors), et ces prix n'ont pas été relevés aujourd'hui.

## Preuve

| Vérification | Ce que ça démontre |
|---|---|
| `grep -nE "^\| API(2\|4\|6\|8\|9\|10) " docs/fiches-veille.md` | chaque ligne du tableau suit l'état de ses mesures (critère de #500) |
| `sed -n '116,119p;149,152p' infra/modules/api-container-app.bicep` | les deux renvois corrigés montrent les ressources et `minReplicas`/`maxReplicas` |
| deux relectures par un sous-agent neuf (high), sur `d53eb8f` puis sur le delta | 15 constats, tous corrigés sur décision de time-knight ; renvois et citations vérifiés |
| contrôle des catégories Unicode `Cc`/`Cf` | aucun caractère invisible dans les deux fichiers |

## Ce que tu dois pouvoir défendre

1. **« Pourquoi ne pas limiter les essais de clé ? »** Une clé de 256 bits (192 au minimum contrôlé)
   rend la recherche exhaustive impraticable, et en ligne seule une pièce de K-B peut essayer
   (`docs/fiches-veille.md`, API2, « Anti-force brute »).
2. **« Pourquoi pas de WAF ni d'API Management ? »** OWASP les demande pour chaque version exposée,
   celle de production comprise. Ils filtrent le trafic du dehors, et aucun n'atteint l'API IA, qui a
   une seule révision derrière une entrée interne (API9).
3. **« Votre limite de débit borne-t-elle la dépense ? »** Non, pas en ligne : le compte repart à
   chaque réveil. La borne est le quota, environ 121 $ par jour au pire, et l'alerte manque (#501).
4. **« Qu'est-ce qui ferait tomber vos justifications ? »** Une entrée externe. Chaque limite le dit,
   et la relecture à chaque version (#497) le surveille.

## Zones non vérifiées

- L'état en ligne : la version déployée (`v0.1.0` ou `v0.1.1`, avec les mêmes uvicorn et h11), les
  routes de l'environnement (relues le 2026-11-08, pas aujourd'hui), « l'environnement ne sert que
  K-B ».
- Les relevés de Sabine (ressource du modèle sans étiquette, quota de 140 000 jetons par minute).
- Le renvoi du référentiel de la certification à l'édition 2019 : repris de l'ordre de mission.
- Rien n'a été essayé contre l'environnement : la chaîne Envoy → uvicorn reste non essayée, et
  justifiée comme telle.

## Ce qui reste

- API4, la dépense du modèle : #501 (alerte sur les jetons, étiquette de la ressource du modèle).
- API8 : #496 (construction du Bicep exigée), #497 (relecture à chaque version), #498 (scan de
  l'image), #499 (sondes sans clé).
- API10 : #522 (jeton OTLP de production, sur la seule pile), puis la portée relevée par Sabine.
