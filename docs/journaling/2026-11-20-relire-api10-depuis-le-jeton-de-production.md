# Relire API10 de l'auto-évaluation OWASP depuis le jeton de production

- Date : 2026-11-20
- Branche : `docs/api10-otlp-token-scope`
- Issue : #611
- Fichiers : `docs/fiches-veille.md` (auto-évaluation de l'API IA), `docs/registre-traitements.md` (fiche Grafana)
- Série : [relecture d'API8 et d'API10 après la mise en ligne](2026-11-08-relire-api8-et-api10-apres-la-mise-en-ligne.md)
  (#454) ; le jeton de production refait par #522.

## Le pourquoi

API10 (*Unsafe Consumption of APIs*) demande d'évaluer la sécurité de chaque fournisseur que l'API IA appelle :
le modèle, l'API de données, GitHub et l'export OTLP vers Grafana Cloud. Une seule mesure restait ouverte, la portée
du jeton de Grafana Cloud : le passage à l'offre gratuite du 08/11 avait supprimé les politiques d'accès, et le
jeton de production ne valait plus rien. #522 a créé le 2026-11-11 une politique `kb-production` depuis la pile de
K-B, et son jeton. #611 relit l'entrée depuis ce jeton, avec une lecture datée de Sabine dans Grafana, et fait passer
API10 à « Tenue » : l'auto-évaluation compte 6 entrées tenues sur 10.

## Le comment

### Une politique créée depuis la pile ne vaut que pour la pile

La documentation de Grafana, relue le 2026-11-20, dit deux choses qui font la preuve. Le *realm* d'une politique
est posé d'office quand on la crée depuis l'administration d'une pile, et un *realm* de pile limite ses jetons à
cette pile. La page « Cloud access policies » d'une pile « only displays access policies with a stack realm for that
stack » : y voir `kb-production` prouve son *realm*. C'est ce que Sabine a lu :

```text
Lu par Sabine le 2026-11-20 sur la page « Cloud access policies » de la pile, qui n'affiche que les
politiques de *realm* pile : `kb-production` active, *realm* `prod-eu-west-2` (pile), droits d'écriture
des métriques, des journaux et des traces seuls, aucun droit de lecture ni de suppression, 0 sélecteur,
0 plage d'adresses ; un seul jeton, `kb-production-2027-01`, non expiré, utilisé la veille.
```

(`docs/fiches-veille.md:1655`, ligne Grafana du tableau des fournisseurs.) Le moindre privilège tient en trois
points : écrire seulement (K-B ne relit rien de ce qu'il envoie), sur une seule pile, avec une date d'expiration.

### Le compte de l'auto-évaluation

```text
| API10 Unsafe Consumption of APIs | **Tenue** | — |

Le compte : 6 entrées tenues sur 10 (API1, API3, API5, API6, API7, API10). Les 4 autres : 2 écarts
```

(`docs/fiches-veille.md:1037-1039`.) API10 quitte les « non tenues » : il en reste 2, API4 (#501) et API8 (#497,
#499). Le compte se réécrit en entier, pas seulement le chiffre, parce que la phrase énumère chaque entrée.

### Le risque qui reste : l'expiration du jeton

```text
Le jeton expire vers le 2027-02-09 : sa rotation se fait avant, avec nos droits (administratrice de la
pile, Owner du groupe de ressources), comme le 2026-11-11 : un jeton neuf de la même politique, puis le
secret `kb-otlp-headers` refait par « Pour refaire un seul secret » d'`infra/README.md`, et la révision
active de `ca-kb-ai-api` redémarrée. Grafana prévient les administrateurs de la pile par courriel
avant l'échéance (case « Enable token expiration emails » cochée, lue par Sabine le 2026-11-20).
```

(`docs/fiches-veille.md:1664-1669`.) Un jeton expiré coupe l'export des mesures sans rien casser d'autre : l'API IA
continue de servir. La rotation est faisable avec nos droits, et prouvée : c'est exactement ce que #522 a fait le
2026-11-11. Le courriel d'avertissement est actif par défaut, et Sabine a vu la case cochée.

### Le registre suit

`docs/registre-traitements.md:131`, ligne « Sécurité » de la fiche Grafana, nommait encore la politique du 27/10,
supprimée depuis, avec une portée « à vérifier ». Elle dit maintenant la politique en vigueur, sa portée et la
lecture de Sabine, et nomme la seconde politique de la pile, `kb-sandbox`, par laquelle le bac à sable envoie.

## Choix faits et options écartées

- **La preuve de la portée : une lecture de Sabine dans la page de la pile, plutôt qu'une lecture du jeton.**
  Aucune session ne lit un jeton (règle du dépôt). La page de la pile suffit, puisqu'elle n'affiche que les
  politiques de *realm* pile (documentation de Grafana). Écartée : l'API des politiques d'accès de Grafana, qui
  demanderait un jeton de plus, aux droits de lecture des politiques.
- **Les deux pages de Grafana citées à leur chemin en vigueur** (`platform/security-and-account-management/…`),
  donné par Context7 et la recherche du jour, au lieu de l'ancien chemin.
- **« Enforce token expiration » non écrit** (tranché par time-knight, sous la délégation de Sabine du 15/10) : la
  mesure d'API10 est la portée et l'expiration de notre jeton, déjà prouvées ; l'imposition par l'organisation ne
  vaut que pour des jetons créés par d'autres administrateurs.
- **`documentation/monitoring_pour_docu.md:374` laissée telle quelle** (tranché par time-knight) : la phrase est
  réécrite par #621, sur une autre branche ; la changer ici ferait un conflit sur la même ligne.

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `grep -n "^| API10" docs/fiches-veille.md` : `Non tenue` à `origin/main`, `**Tenue**` sur la branche | La ligne du tableau change |
| `grep -c "Le compte : 6 entrées tenues sur 10 (API1, API3, API5, API6, API7, API10)" docs/fiches-veille.md` → 1 | Le compte est à jour (critère de fin de la mission) |
| `grep -n "ne vaut plus rien\|d'ici #522" docs/fiches-veille.md` et `grep -n "KB logs metrics traces write" docs/registre-traitements.md` : une ligne chacun à `origin/main`, vides sur la branche | L'ancien état n'est plus écrit |
| Lecture de Sabine du 2026-11-20, page « Cloud access policies » de la pile | *Realm* pile, trois droits d'écriture, aucun sélecteur ni plage, un jeton non expiré |
| Lecture de Sabine du 2026-11-20, « Org Settings → Settings » | Courriels d'expiration actifs |
| #522, commentaires du 2026-11-11 et du 2026-11-12 | Politique et jeton créés, secret refait, mesures de la production reçues |
| `uv run mkdocs build --strict`, `uv run pytest` | La doc se construit, rien d'autre ne bouge |

## Ce que tu dois pouvoir défendre

- **Comment sais-tu que le jeton ne vaut que pour la pile de K-B ?** La politique a été créée depuis la pile, ce qui
  pose son *realm* sur la pile, et la page de la pile, qui n'affiche que les politiques de *realm* pile, la montre
  (`docs/fiches-veille.md:1655`, documentation de Grafana citée dans « Sources de l'auto-évaluation »).
- **Que se passe-t-il quand le jeton expire ?** L'export des mesures vers Grafana s'arrête ; l'API IA continue de
  servir. Grafana prévient avant, par courriel ; la rotation suit la procédure de #522 (`docs/fiches-veille.md:1664-1669`).
- **Qu'est-ce qu'un attaquant ferait de ce jeton ?** Écrire des mesures, des journaux ou des traces dans la seule
  pile de K-B : il ne lit rien et ne supprime rien, aucun droit de lecture ni de suppression n'est coché.
- **Pourquoi « Tenue » et pas « Écart voulu » ?** Toutes les mesures d'API10 sont appliquées, la portée du jeton
  comprise ; rien n'est écarté.

## Zones non vérifiées

- **La date exacte d'expiration** : la page de Grafana affiche « in 3 months » ; le 2027-02-09 vient de la durée de
  90 jours choisie à la création, le 2026-11-11 (#522).

## Ce qui reste

- API4 (#501) et API8 (#497, et le constat en ligne de #499) : les deux entrées encore non tenues.
- La rotation du jeton, avant le 2027-02-09 : son échéance est rappelée dans `MEMORY.md` (« Jeton OTLP de la
  production »), lu par chaque session, à côté de celle du secret client du site.
