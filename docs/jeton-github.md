# Jeton GitHub de K-B

La collecte GitHub (releases, alertes de sécurité, dépôts les plus étoilés) ne lit que des données
publiques. Sans jeton, l'API accepte 60 requêtes par heure ; avec un jeton, 5 000. Le jeton ne
sert qu'à cela.

## Pourquoi un jeton *fine-grained*

GitHub propose deux sortes de jetons personnels.

| | *classic* | *fine-grained* |
|---|---|---|
| Droits | des *scopes* larges : `repo` ouvre tous les dépôts privés, en lecture et en écriture | plus de 50 permissions séparées, chacune à « aucun accès », « lecture » ou « lecture et écriture » |
| Dépôts visés | tous ceux auxquels le compte a accès | un propriétaire, puis tous ses dépôts, une liste, ou les dépôts publics seulement |

Le jeton de K-B est un *fine-grained* limité aux **dépôts publics**, **sans aucune permission** :
c'est le moindre privilège. Les endpoints utilisés n'en demandent aucune sur des données
publiques. S'il fuite, il ne lit aucun dépôt privé et n'écrit nulle part.

## Créer le jeton

1. Avatar → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
2. **Token name** : `K-B collecte (lecture seule)`.
3. **Expiration** : 90 jours. Une durée courte limite les dégâts d'une fuite ; à l'échéance, on en
   génère un nouveau.
4. **Resource owner** : son propre compte.
5. **Repository access** : **Public repositories**.
6. **Permissions** : n'en ajouter aucune.
7. **Generate token**, puis copier le jeton. Il ne s'affiche qu'une fois.

## Le ranger

Dans le `.env` à la racine du dépôt, ignoré par git :

```
KB_GITHUB_TOKEN=<le jeton>
```

Le nom n'est pas `GITHUB_TOKEN` : la CLI `gh` lit cette variable en priorité sur la connexion de
l'utilisateur, et ce jeton sans permission bloquerait alors les PR et les issues.

## Vérifier qu'il est pris en compte

Depuis la racine du dépôt :

```
uv run --env-file .env python -c "import os,json,urllib.request as u; t=os.environ.get('KB_GITHUB_TOKEN',''); print('présente' if t else 'ABSENTE'); r=u.Request('https://api.github.com/rate_limit',headers={'Authorization':'Bearer '+t}); c=json.load(u.urlopen(r))['resources']['core']; print('quota :', c['limit'], '— restant :', c['remaining'])"
```

La commande n'affiche jamais le jeton, seulement :

- `présente` ou `ABSENTE` : la variable est lue, ou non ;
- `quota : 5000` : le jeton est pris en compte (`60` : il ne l'est pas) ;
- `restant` : les requêtes encore disponibles dans l'heure. L'appel à `/rate_limit` ne les
  décompte pas.

Un jeton expiré ou révoqué fait échouer la commande avec `HTTP Error 401`.

## Sources (consultées le 2026-09-30)

- [Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [Introducing fine-grained personal access tokens](https://github.blog/security/application-security/introducing-fine-grained-personal-access-tokens-for-github/)
- [Permissions required for fine-grained personal access tokens](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens)
- [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
