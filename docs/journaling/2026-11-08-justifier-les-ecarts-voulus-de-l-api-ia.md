# Justifier les deux écarts voulus de l'autoévaluation OWASP de l'API IA

- **Date** : 2026-11-08
- **Branche** : `docs/owasp-ai-api-wanted-gaps`
- **Issue** : #480
- **Fichiers** : `docs/fiches-veille.md` (section « Sécurité : OWASP API Security Top 10 (2023) »),
  `docs/outils-de-suivi.md` (trois renvois)
- **Série** : [2026-11-05-bornes-owasp-des-deux-api.md](2026-11-05-bornes-owasp-des-deux-api.md),
  [2026-11-08-relire-api8-et-api10-apres-la-mise-en-ligne.md](2026-11-08-relire-api8-et-api10-apres-la-mise-en-ligne.md)

Les commits plus anciens que `7c2b2fa` dans la liste de la branche viennent de #494, déjà fusionnée
dans `main`. Cette note ne les couvre pas.

## Le pourquoi

Le tableau de l'autoévaluation OWASP de l'API IA marquait API2 et API9 « Non tenue ». Pourtant,
leur écart est voulu : une décision de Sabine du 2026-11-05, justifiée plus bas, dans chaque
entrée. À lire le tableau seul, on croyait à un manque. La revue d'E3 du 08/11 juge C9.3 partiel
(« Les recommandations du top 10 OWASP sont intégrées quand nécessaires ») : un écart doit donc
dire pourquoi la mesure n'est pas nécessaire. La PR ne change ni le code ni l'état réel des
mesures. Elle aligne le tableau et le compte sur ce que les entrées disent déjà.

## Le comment

### Un état de plus, défini dans la légende

`docs/fiches-veille.md:832-834` :

```
elle se tiendra ; *s.o.* : sans objet pour cette API ; « écart voulu, justifié » dit une mesure
non appliquée par décision, dont la justification est écrite sous son entrée ; un écart voulu dans
une mesure tenue (« Pour lever l'écart ») la laisse tenue.
```

« Tenue », « non tenue » et *s.o.* étaient définis ; le nouvel état ne l'était pas. Il prend deux
sens dans la même section : une mesure laissée de côté (API2, anti-force brute), et un écart à
l'intérieur d'une mesure tenue (le 415 d'API8, `TrustedHostMiddleware`). La deuxième phrase les
sépare, sur le constat 7 de la relecture.

### Les cases renvoient à leur justification par son titre

`docs/fiches-veille.md:850`, API2 : « justifié sous API2, « Anti-force brute, plus strict que la
limite de débit » (clé de 32 caractères au moins, contrôlée au démarrage) ». Le titre est cité en
entier : une recherche exacte le retrouve. La clé est décrite par ce que le code vérifie, et rien
de plus (`src/k_b/core/config.py:221-222`) :

```python
MIN_API_KEY_LENGTH = 32
API_KEY_CHARACTERS = re.compile(r"[A-Za-z0-9_-]+")
```

Le premier jet disait « 192 bits au moins ». Or 32 caractères sur 64 symboles donnent 192 bits
seulement si la clé est tirée au hasard, et le code ne contrôle pas ce tirage (constat 2).

### API9 : l'écart n'existe qu'en local

`docs/fiches-veille.md:1231-1233` dit que l'API IA en ligne est déployée en `production`
(`infra/main.bicep:216`). Le code ne sert `/docs` que pour la valeur `sandbox` exacte
(`src/k_b/core/api_settings.py:41-43`) :

```python
def is_sandbox(environ: Mapping[str, str]) -> bool:
    """Whether KB_DEPLOYMENT_ENVIRONMENT is sandbox, written as is."""
    return environ.get(DEPLOYMENT_ENVIRONMENT_VARIABLE) == "sandbox"
```

Une valeur oubliée ou mal écrite ferme donc la documentation (échouer fermé). La phrase dit
« non relu en ligne » : elle vient du Bicep et du test, pas d'un `az containerapp show`
(constat 1).

### Ce qui reste reste nommé

Chacune des deux entrées garde une mesure que la PR ne justifie pas : la protection externe d'API9
(`:1239`) et le TLS mutuel d'API2 (`:918-923`). Leur case dit « non tenue » ou « non appliqué »,
« à justifier (#500) », et le compte le répète (`:860-862`). Ces deux formulations sont de Sabine :
la première au plan, la seconde au constat 5. Écrire « justifiée par #500 » aurait affirmé ce
qu'aucune PR fusionnée n'a encore écrit.

### Les renvois décalés

La légende, le compte et API9 ajoutent 6 lignes. Or `docs/outils-de-suivi.md:43` et `:66` citent
`fiches-veille.md` par numéro de ligne. Ils passent de 1434-1436 à 1440-1442, de 1545-1547 à
1551-1553 et de 1547-1549 à 1553-1555. Les notes datées de `docs/journaling/` gardent les leurs :
elles décrivent leur propre commit (décision de Sabine).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Forme du renvoi | Le titre de la mesure entre guillemets, comme ailleurs dans le document | Un lien `#ancre` : le document n'en a aucun, et un titre renommé le casse |
| API9 et sa protection externe | « Écart voulu, justifié », la mesure restante nommée « à justifier (#500) » (Sabine, plan) | Garder « Non tenue » : le critère de #480 tombait ; écrire ici la justification de 28-7 : c'est le périmètre de #500 |
| TLS mutuel d'API2 | Nommé comme celui d'API9 (Sabine, constat 5) | Le laisser hors du tableau, comme au plan initial : API2 aurait gardé une mesure non appliquée que ni sa case ni le compte ne nomment |
| Le corps d'API9, « à décider au déploiement » (`:1239-1240`) | Laissé tel quel (time-knight, constat 6) | Le corriger : c'est 28-7, le périmètre de #500 |
| Renvois de `outils-de-suivi.md` | Recalés dans la PR (Sabine) | Les laisser : ils auraient visé un autre texte |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `grep -nE "^\| API(2\|9) " docs/fiches-veille.md` → `:850` et `:857`, « Écart voulu, justifié » | Le premier point du critère de #480 |
| `sed -n '202p;216p' infra/main.bicep` → `name: 'ca-kb-ai-api'`, `KB_DEPLOYMENT_ENVIRONMENT: 'production'` | Le fait cité pour API9, tel que le Bicep le déclare |
| `uv run pytest tests/ai_api/test_serve_ai.py -k documentation_is_served_in_the_sandbox_only` → 6 passed | `/docs` et `/openapi.json` rendent 404 hors de `sandbox` |
| `diff` des `sed -n` entre `origin/main` et la branche, pour les trois renvois | Les renvois recalés visent le même texte qu'avant |
| Script Python sur les deux fichiers : aucun caractère `Cc` ni `Cf` | Pas de caractère invisible |
| Relecture par un sous-agent neuf, en lecture seule : 9 constats ; 6 corrigés (1, 2, 3, 5, 7, 8), 3 écartés (4, 6, 9) | Le texte relu contre le code et le reste de la section |

## Ce que tu dois pouvoir défendre

1. **« Écart voulu, justifié », n'est-ce pas un « non tenue » rebaptisé ?** Non. La mesure n'est
   pas appliquée, mais par une décision datée, et la justification est écrite sous l'entrée. Pour
   API2 : une clé de 32 caractères rend la recherche exhaustive impraticable, et une limite des 401
   par adresse couperait `kb digest` en local. Voir API2, « Anti-force brute, plus strict que la
   limite de débit ».
2. **Pourquoi « 32 caractères » et pas « 192 bits » ?** Le code contrôle la longueur et l'alphabet
   (`core/config.py:221-222`), pas le hasard. 192 bits est le maximum d'une clé de 32 caractères,
   atteint seulement si elle est tirée au hasard. La commande du `README.md`,
   `secrets.token_urlsafe(32)`, tire 32 octets, soit 256 bits sur 43 caractères.
3. **Et si quelqu'un lance l'API en ligne en `sandbox` ?** Il faudrait changer `infra/main.bicep:216`
   et redéployer. Une valeur mal écrite (`Sandbox`, vide) ferme `/docs`, et le test le vérifie.
4. **API9 est « justifié » alors qu'une mesure n'est pas tenue : pourquoi ?** La case le dit
   elle-même : « protection externe : non tenue, à justifier (#500) ». Ce choix de Sabine garde
   l'état transitoire visible jusqu'à #500.

## Zones non vérifiées

- La valeur de `KB_DEPLOYMENT_ENVIRONMENT` sur `ca-kb-ai-api` en ligne, et le 404 de `/docs` en
  ligne : tirés du Bicep et du test, sans aucune commande `az` (la mission l'interdit). Le texte
  écrit « non relu en ligne ».
- Le rendu Markdown du tableau sur GitHub : les lignes sont bien formées, mais je ne les ai pas
  vues rendues.

## Ce qui reste

- #500 : justifier la protection externe d'API9 et le TLS mutuel d'API2, mettre à jour leurs cases
  et le compte, corriger le corps d'API9. Ses renvois par ligne sont à relire à son rebase : cette
  PR les décale de +2 jusqu'au compte (`:858` d'`origin/main`), de +4 jusqu'au corps d'API9
  (`:1226`), et de +6 après.
- API4 et API8 restent « non tenue » : #496 à #499 et #501.
