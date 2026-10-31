# Jetons GitHub de K-B

K-B lit GitHub avec deux jetons, de la même sorte, du même compte :

- **`KB_GITHUB_TOKEN`, la collecte** (releases, alertes de sécurité, dépôts les plus étoilés et les
  plus forkés), qui ne lit que des données publiques. Sans jeton, l'API accepte 60 requêtes par
  heure ; avec un jeton, 5 000 : cette limite vaut pour les releases et les alertes. Les deux tops
  appellent la recherche, qui a son propre quota, à part ([specs-collecte.md](specs-collecte.md),
  « Limites »). Facultatif.
- **`KB_AI_GITHUB_TOKEN`, les comptes rendus des tendances** (#367) : l'API IA lit la fiche de
  chaque candidat, `GET /repos/{owner}/{repo}`, 70 requêtes au plus par compte rendu
  ([tendances.md](tendances.md), « GitHub »). **Obligatoire** : sans lui, `kb serve-ai` ne démarre
  pas, jamais en anonyme ; un jeton *classic* (`ghp_…`) est refusé.

Deux jetons plutôt qu'un : chaque service ne reçoit que le sien (l'API IA ne lit pas les variables
de la collecte), et l'un se révoque sans arrêter l'autre. La limite de 5 000 requêtes par heure est
celle du **compte**, partagée par ses jetons : la collecte et les comptes rendus la consomment
ensemble ([Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) :
les requêtes d'un jeton personnel comptent dans la limite de l'utilisateur).

## Pourquoi un jeton *fine-grained*

GitHub propose deux sortes de jetons personnels.

| | *classic* | *fine-grained* |
|---|---|---|
| Droits | des *scopes* larges : `repo` ouvre tous les dépôts privés, en lecture et en écriture | plus de 50 permissions séparées, chacune à « aucun accès », « lecture » ou « lecture et écriture » |
| Dépôts visés | tous ceux auxquels le compte a accès | un propriétaire, puis tous ses dépôts, une liste, ou les dépôts publics seulement |

Chaque jeton de K-B est un *fine-grained* limité aux **dépôts publics**, **sans aucune permission** :
c'est le moindre privilège. Les endpoints utilisés n'en demandent aucune sur des données
publiques. S'il fuite, il ne lit aucun dépôt privé et n'écrit nulle part.

## Créer un jeton

Les mêmes étapes pour les deux jetons ; seul le nom change.

1. Avatar → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
2. **Token name** : `K-B collecte (lecture seule)` pour la collecte, `K-B API IA (lecture seule)`
   pour les comptes rendus des tendances.
3. **Expiration** : 90 jours. Une durée courte limite les dégâts d'une fuite ; à l'échéance, on en
   génère un nouveau.
4. **Resource owner** : son propre compte.
5. **Repository access** : **Public repositories**.
6. **Permissions** : n'en ajouter aucune.
7. **Generate token**, puis copier le jeton. Il ne s'affiche qu'une fois.

## Le ranger

Dans le `.env` à la racine du dépôt, ignoré par git :

```
KB_GITHUB_TOKEN=<le jeton de la collecte>
KB_AI_GITHUB_TOKEN=<le jeton de l'API IA>
```

Aucun des deux ne s'appelle `GITHUB_TOKEN` : la CLI `gh` lit cette variable en priorité sur la connexion de
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

Pour le jeton de l'API IA, la même commande en remplaçant `KB_GITHUB_TOKEN` par
`KB_AI_GITHUB_TOKEN` ; puis `kb serve-ai`, qui le vérifie au démarrage (absent, *classic*, ou un
caractère hors `[A-Za-z0-9_]` : code 2, la variable nommée, jamais le jeton) :

```
KB_DATA_DIR=~/.knowledge_base uv run --env-file .env kb serve-ai
```

Sa sortie d'erreur dit `GitHub token of the trend reports loaded`, sans la valeur ; Ctrl-C l'arrête.
Un jeton expiré ou révoqué ne se voit qu'au premier compte rendu : 502 `github_unauthorized`.

## Sources (consultées le 2026-09-30)

- [Managing your personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [Introducing fine-grained personal access tokens](https://github.blog/security/application-security/introducing-fine-grained-personal-access-tokens-for-github/)
- [Permissions required for fine-grained personal access tokens](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens)
- [Rate limits for the REST API](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
