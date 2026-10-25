# Chiffrer le coût mensuel de chaque option de la mise en ligne

- **Date** : 2026-10-25
- **Branche** : `docs/hosting-cost`
- **Issue** : #333 (demande 76 de la revue de la certification du 2026-10-24)
- **Fichier** : `README.md`, section « Budget » (l. 118-139)

## Le pourquoi

Jusqu'ici, le tableau « Budget » disait de la mise en ligne du 08/11 : « non chiffrée à ce jour ».
Il reste une décision ouverte, « La base au temps 3 » : SQLite et Blob, ou PostgreSQL (journal ADR,
« Décisions encore ouvertes »). Pour la prendre, il faut connaître le prix de chaque option. La
PR le donne sans trancher, pour la région choisie pour le modèle, France Central. Chaque prix est
daté et sourcé.

## Le comment

### Séparer ce qui est commun de ce qui distingue les options

Le tableau a trois lignes au lieu d'une : une pour les coûts communs, puis une pour le surcoût de
chaque option (`README.md:125-127`) :

```
| Mise en ligne du 08/11 : coûts communs aux deux options (France Central, prix publics en dollars relevés le 2026-10-25, mois de 730 h) | **8,96 $ par mois** sans l'offre gratuite …
| Mise en ligne, option SQLite et Blob | **0,02 $ par mois** de plus : …
| Mise en ligne, option PostgreSQL | **18,13 $ par mois** de plus : …
```

Le job, les deux API, le brut, le registre d'images et les journaux sont les mêmes dans les deux
options. Seul l'endroit de la base change. Écrire la différence à part montre ce que la décision
coûte vraiment : 0,02 $ ou 18,13 $ par mois, en plus des coûts communs.

### D'où viennent les prix : l'API des prix de détail

Le jour de la PR, les pages de prix d'Azure n'affichaient pas leurs chiffres : la page de Container
Apps lue par WebFetch montrait « $- per second ». Les prix viennent donc de l'API officielle des
prix de détail de Microsoft, filtrée sur France Central (`README.md:134`) :

```
- Prix de France Central : [API des prix de détail d'Azure](…) (Microsoft Learn), requête
  `https://prices.azure.com/api/retail/prices` filtrée par `armRegionName eq 'francecentral'` et par `serviceName` (…)
```

Sabine a accepté cette source le 2026-10-25, à condition de citer sa page Microsoft Learn. Chaque
compteur lu a un tarif et une date d'effet. Par exemple : `Standard vCPU Active Usage` à 0,000024 $
la seconde (depuis 2022-06-01), `B1MS` à 0,019 $ de l'heure (depuis 2021-12-01), `Hot LRS Data
Stored` à 0,0192 $ par Go et par mois (depuis 2017-09-01). Les prix sont en dollars, la devise de
base de l'API.

### Le calcul : des secondes de vCPU et de mémoire

Container Apps facture à la seconde, selon les vCPU et la mémoire alloués. Une réplique active est
facturée au tarif actif, une réplique au repos au tarif de repos. Un job est facturé au tarif actif,
du début à la fin de chaque exécution, d'après la page officielle. Pour le job, sur un mois de
730 h, soit 30,4 jours :

- 30,4 exécutions de 900 s, à 0,5 vCPU : 13 688 vCPU-secondes à 0,000024 $, soit 0,33 $ ;
- les mêmes 27 375 s à 1 Gio : 27 375 Gio-secondes à 0,000003 $, soit 0,08 $ ;
- total : 0,41 $.

Les deux API sont calculées de la même façon, dans deux hypothèses. Dans la première, chaque API
tombe à zéro réplique au repos et reste active 1 h par jour : 3,29 $ pour les deux. Dans la
seconde, chaque API garde une réplique jour et nuit, au tarif de repos : 23,65 $ pour les deux.

### L'offre gratuite vaut par abonnement

Chaque mois, l'offre gratuite donne 180 000 vCPU-secondes, 360 000 Gio-secondes et 2 millions de
requêtes, « per subscription per month » (page officielle de Container Apps). À zéro réplique, le
job et les deux API restent en dessous : 123 188 vCPU-secondes et 246 375 Gio-secondes. Leur coût
tombe donc à 0 $. L'abonnement de la mise en ligne n'est pas connu : le registre des traitements le
dit pour le modèle, sur l'abonnement de l'organisme. Le README donne donc les deux chiffres :
8,96 $ sans l'offre et 5,26 $ avec elle.

### Les deux options de la base

- **SQLite et Blob** : la base est un fichier, produit par le job et rangé dans Blob, au prix du
  brut : 1 Go, soit 0,02 $. Le README écrit l'hypothèse que `kb serve-data` la lit au démarrage,
  parce que la façon de la lire n'est pas décidée.
- **PostgreSQL** : le plus petit serveur flexible, Burstable B1ms, coûte 0,019 $ × 730 h, soit
  13,87 $. Le stockage minimal est de 32 Gio (page « Compute options », Microsoft Learn), à
  0,133 $, soit 4,26 $. Total : 18,13 $.

## Choix faits et options écartées

| Choix retenu | Pourquoi | Écarté, et pourquoi |
|---|---|---|
| L'API des prix comme source | Les pages de prix n'affichaient pas leurs chiffres ; l'API est publiée par Microsoft, sans authentification, et son filtre isole France Central (accepté par Sabine) | Les agrégateurs tiers (Bytebase, blogs) : non officiels, et leurs chiffres ne concordent pas entre eux |
| Les dollars | La devise de base de l'API | L'euro : l'API le donne « pour référence » seulement |
| Un mois de 730 h | La convention des prix horaires d'Azure | 30 jours : un écart de 1,4 % |
| Deux variantes pour les API (zéro réplique ou une gardée) | Le choix n'est pas fait, et il multiplie le coût des API par sept | Une seule variante : elle cacherait le poste qui pèse le plus |
| Avec et sans l'offre gratuite | L'abonnement n'est pas connu | Toujours l'offre déduite : faux si l'abonnement l'a déjà consommée |
| ACR Basic chiffré, GHCR nommé | Aucune décision n'est consignée sur le registre d'images ; ACR est le registre d'Azure, GHCR est gratuit pour un paquet public, et le dépôt devient public | Choisir l'un des deux : c'est une décision, hors de la demande |
| Ne pas trancher la base | La demande 76 donne le coût ; la décision reste à Sabine (MISSION.md, « Ne pas déborder ») | — |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| Réponse de `prices.azure.com/api/retail/prices` filtrée sur `francecentral` (2026-10-25) | Les tarifs unitaires cités, avec leur date d'effet |
| Page « Azure Container Apps pricing », lue par WebFetch le 2026-10-25 | L'offre gratuite par abonnement ; les jobs facturés au tarif actif ; le compteur de gestion à 0,125 $ de l'heure (« Environment Management Hour » dans l'API) qui ne vaut que pour le plan Dedicated, un point de terminaison privé et la maintenance planifiée |
| Page « Compute options in Azure Database for PostgreSQL » (Microsoft Learn, 2026-07-08) | Le stockage de 32 Gio au moins ; la mise en garde sur le niveau Burstable |
| Calcul en Python dans la session (730 h, tarifs ci-dessus) | Les totaux : 0,41 ; 3,29 ; 23,65 ; 0,19 ; 5,07 ; 18,13 $ |
| `uv run pytest` : 2596 réussis ; `ruff`, `ruff format`, `mypy --strict` verts | La PR ne casse rien (elle ne touche que le README) |

## Ce que tu dois pouvoir défendre

- **Pourquoi ces durées et ces tailles ?** Ce sont des hypothèses, écrites comme telles dans le
  README : aucune exécution en ligne n'a été mesurée. Le coût varie en proportion. Si le job prend
  1 h au lieu de 15 min, il passe de 0,41 $ à environ 1,64 $ (`README.md:125`).
- **Pourquoi la variante à une réplique coûte-t-elle autant ?** Une réplique gardée est facturée
  2 628 000 secondes par mois, même au repos. Le tarif de repos est huit fois plus bas que le tarif
  actif pour les vCPU, mais la durée l'emporte.
- **PostgreSQL vaut-il 18 $ de plus ?** Le chiffre ne le dit pas : il donne le prix, la décision
  reste « La base au temps 3 ». Microsoft déconseille aussi le niveau Burstable pour la production
  (`README.md:127`). Un niveau au-dessus coûterait plus cher, et il n'est pas chiffré.
- **Les prix sont-ils à jour ?** Ils ont été lus le 2026-10-25, et chaque compteur porte sa date
  d'effet. Un prix qui change après cette date n'est pas suivi (`README.md:132`).
- **Où est le coût du modèle ?** Sur sa ligne, « Modèle des fiches » (`README.md:124`), à part :
  l'abonnement de l'organisme ne montre pas sa facturation.

## Zones non vérifiées

- Le volume du brut (10 Go) et celui de la base (1 Go) sont supposés : le dossier de données du Mac
  n'a pas été mesuré.
- La façon dont l'offre gratuite se répartit entre tarif actif et tarif de repos n'est pas lue à
  la source. Les 27,70 $ de la variante à une réplique sont donc approchés.
- Les 5 Go gratuits de Log Analytics viennent du palier de l'API (le prix commence à 5 Go). Leur
  portée, « par compte de facturation », n'est donnée que par des réponses de Microsoft Q&A, pas
  par la page officielle.
- Le transfert de données entre services d'une même région n'est pas chiffré, et sa gratuité
  n'est pas vérifiée.
- Les 10 Go compris dans ACR Basic viennent d'un exemple de la page Microsoft Learn « service
  tiers », relevé par la recherche, page non ouverte.
- La gratuité de GHCR est écrite « currently free » par GitHub, sans engagement de durée.

## Ce qui reste

- Mesurer la durée réelle du job et le volume du brut une fois en ligne (#330, le job du 08/11),
  puis recalculer.
- Trancher « La base au temps 3 », puis le registre d'images : décisions de Sabine.
- La ligne « Temps » du même tableau (« estimation en heures ») contredit la règle du 2026-10-20
  (une taille, sans heures). Elle est signalée, pas corrigée : hors de la demande 76.
