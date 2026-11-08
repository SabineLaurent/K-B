# Relire API8 et API10 de l'auto-évaluation OWASP après la mise en ligne

- Date : 2026-11-08
- Branche : `docs/owasp-api8-api10-online`
- Issue : #454
- Fichiers : `docs/fiches-veille.md` (l'API IA), `docs/specs-api.md` (l'API de données)
- Série : l'auto-évaluation écrite le 2026-11-05 (#161) ; la mise en ligne (#414, #415, #421).

## Le pourquoi

L'auto-évaluation OWASP de l'API IA date du 05/11. Plusieurs de ses mesures étaient renvoyées « au
déploiement », qui a eu lieu depuis : `v0.1.0` tourne sur Azure Container Apps. #454 demande de relire
chaque point d'API8 (Security Misconfiguration) et d'API10 (Unsafe Consumption of APIs) contre
`infra/` et contre l'état en ligne, puis de donner à chacun son état et sa preuve. Le TLS d'API8 vaut
aussi pour l'API de données : ta règle du 05/11 veut qu'une règle OWASP commune aux deux API se traite
pour les deux dans la même PR.

## Le comment

### Une preuve par point : un fichier, ou une commande en lecture seule

```
- Les deux API n'ont qu'une entrée interne, en HTTPS (`external: false`, `allowInsecure: false`,
  `infra/modules/api-container-app.bicep:74-80`)
```
(`docs/fiches-veille.md`, API8, « TLS, même pour une API interne »)

Chaque fait renvoie au fichier qui le pose dans `infra/`, puis à ce qu'Azure dit en ligne. Le fichier
dit ce qui doit être, et la commande `az` montre ce qui est vraiment en ligne. Il faut les deux :
`deploy.yml` change l'image hors du Bicep, et le socle s'applique à la main.

### Les commandes, sans identifiant

```sh
az containerapp env show -n <environnement> -g <groupe> \
  --query "{encryption: properties.peerTrafficConfiguration.encryption.enabled, mtls: properties.peerAuthentication.mtls.enabled}"
```

K-B va devenir public. Les commandes nomment donc l'app, mais remplacent le groupe et l'environnement
par `<groupe>` et `<environnement>`, et le domaine par `<defaultDomain>`. Chaque `--query` ne lit
que les champs qui prouvent le point : pour les variables, `KB_DATA_API_URL` et
`KB_DATA_API_ALLOWED_HOSTS` seules. Qui rejoue la commande ne voit aucune autre variable.

### Ce qu'aucune commande ne prouve depuis le Mac

L'entrée interne n'est joignable que de l'environnement. La version de TLS (« always use TLS 1.2 or
1.3 ») et la manière dont Envoy traite une requête ambiguë ne s'essaient donc pas depuis le Mac. La
première vient de la documentation d'ACA, lue le 08/11. La seconde est écrite « non essayée », avec
l'essai qui la tiendrait.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté |
|---|---|---|
| TLS « tenue en ligne », par la relecture datée | la définition de « Tenue » admet un essai daté | refuser `http` en production dans le code : un comportement nouveau, dans `src/`, hors de #454 |
| « Traitement uniforme dans la chaîne de serveurs » passe de *s.o.* à non tenue | Envoy est devant uvicorn depuis la mise en ligne | le garder *s.o.* : faux depuis #414 |
| API10 tenue, malgré la réserve Grafana du tableau des fournisseurs | la réserve porte sur la portée du jeton de K-B, pas sur la consommation des réponses d'un fournisseur (tri de time-knight) | API10 non tenue, et un compte de 5 sur 10 |
| `specs-api.md` : la ligne API8 et « API8, TLS » seulement | ta règle du 05/11 : une règle commune, une PR pour les deux | relire toute l'auto-évaluation de l'API de données : hors de #454 |

## Preuve

| Commande ou lecture | Ce que ça démontre |
|---|---|
| `az containerapp show` pour les deux apps : `external` false, `allowInsecure` false, `transport` Http | les deux API ne sont joignables que de l'environnement, en HTTPS |
| `az containerapp env show` : `encryption` true, `mtls` false | le trafic entre apps est chiffré |
| `az containerapp env http-route-config list` : `[]` | aucune route ne sert les API au-dehors, la seule exception de la documentation |
| les deux variables en ligne : `https://ca-kb-data-api.internal.<defaultDomain>` et ce nom seul permis | l'API IA appelle l'API de données en `https` |
| `uv.lock` de `v0.1.0` : uvicorn 0.54.0, h11 0.16.0 | les versions citées sont celles de l'image en ligne |

## Ce que tu dois pouvoir défendre

1. **Pourquoi API10 passe-t-elle à « tenue » ?** Sa seule mesure non tenue était le TLS vers l'API de
   données. En ligne, cet appel passe en `https`, avec le chiffrement entre apps.
2. **Pourquoi API8 reste-t-elle « non tenue » ?** Il manque la revue périodique de la configuration en
   ligne (une seule relecture, celle-ci), une évaluation automatisée de sa sécurité (le test de fumée
   ne vérifie que la réponse) et un essai de la chaîne Envoy → uvicorn.
3. **Le code peut-il appeler l'API de données en `http` en ligne ?** Oui, si l'URL posée l'était : le
   code accepte `http` pour la machine (`data_api_settings.py:18`). En ligne, c'est le Bicep qui pose
   l'URL en `https` (`infra/main.bicep:223`). C'est écrit comme une limite.
4. **Pourquoi pas de mTLS ?** Ce qu'il ajoute au chiffrement entre apps n'est pas documenté
   (commentaire de `infra/modules/container-apps-environment.bicep:32`).

## Zones non vérifiées

- La version de TLS de l'entrée interne et le comportement d'Envoy devant une requête ambiguë : la
  documentation seule pour la première, rien pour le second.

## Ce qui reste

- Refuser `http` vers l'API de données hors du poste local : une issue S, que time-knight te
  propose.
- Les « au déploiement » d'API9 et la définition datée du 05/11, hors de #454.
