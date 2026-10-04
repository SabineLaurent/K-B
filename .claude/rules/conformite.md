<!-- consignes/conformite.md v2026-10-04 — source : time-knight. Ne pas modifier ici sans la reporter. -->
# Conformité — référentiels en vigueur

Ce que le code des projets applique en sécurité, données, accessibilité et écoconception, dans la
version **en vigueur**. Complète `code.md`, qui dit comment coder ; ce fichier dit selon quelle norme.

## Référentiels

| Référentiel | Version en vigueur | Vérifiée le | Source officielle | S'applique à |
|---|---|---|---|---|
| OWASP API Security Top 10 | 2023 | 2026-10-04 | https://api-security.owasp.org/ | toute API exposée |
| RGPD, fiche CNIL « intérêt légitime : collecte par moissonnage » | fiche en ligne | 2026-10-04 | https://www.cnil.fr/fr/focus-interet-legitime-collecte-par-moissonnage | collecte, scraping, base, purge |
| RGAA | 4.1.2 (WCAG 2.1 AA) ; RGAA 5 (WCAG 2.2) annoncé fin 2026 | 2026-10-04 | https://accessibilite.numerique.gouv.fr/ | interfaces, documentation publiée |
| RGESN | v2, 28/05/2024 | 2026-10-04 | https://ecoresponsable.numerique.gouv.fr/publications/referentiel-general-ecoconception/ | collecte, stockage, hébergement, IA |

## Ce que chacun impose ici

**OWASP API Security Top 10 (2023)**
- API1 : contrôler l'autorisation sur **chaque objet** demandé, pas seulement sur la route.
- API2 : authentification par jeton ; un test prouve qu'un appel sans jeton est refusé.
- API3 et API5 : ne renvoyer que les champs et les fonctions que l'appelant a le droit de voir.
- API4 : limiter la consommation (débit, taille de page, délai).
- API10 : une réponse d'API tierce est une entrée non fiable (vaut aussi pour la collecte).

**RGPD et CNIL (moissonnage)**
- Critères de collecte écrits **avant** de collecter ; supprimer dès la collecte ce qui ne sert pas.
- Exclure une source qui s'oppose à la collecte (`robots.txt`, CAPTCHA, conditions d'utilisation) ;
  le vérifier avant de coder une source.
- Ne pas croiser des données par identifiant personnel ; supprimer sans délai une donnée sensible
  collectée par accident.
- Chaque donnée personnelle (auteur, identifiant…) figure au registre des traitements, avec sa
  durée ; la purge est **codée et testée**, pas seulement décrite.

**RGAA 4.1.2**
- Toute interface vise WCAG 2.1 AA ; un contrôle d'accessibilité en apporte la preuve.
- Documentation publiée : titres hiérarchisés, tableaux avec en-têtes, images et schémas décrits
  par un texte.

**RGESN v2**
- 1.6 : minimiser les données collectées au-delà du RGPD, et leur durée de conservation, **même
  non personnelles**.
- 3.1 : éviter une technologie gourmande (apprentissage automatique notamment) sauf à retenir la
  solution la plus sobre et à le documenter.
- Collecte incrémentale : ne pas retélécharger ce qui est déjà là ; limiter le volume lu par requête.

## Fraîcheur

Avant un travail qui touche un domaine de la table : si « Vérifiée le » date de plus de 30 jours,
ou qu'une nouvelle version est annoncée, revérifier à la source officielle et signaler l'écart à
Sabine. Ne pas modifier ce fichier dans le dépôt : time-knight le tient.

## Enrichir

Un domaine sans référentiel dans la table (premier appel à un LLM, première interface,
hébergement, licence d'une source…) : le **signaler** dans le `Statut` de la mission ou à Sabine,
et appliquer en attendant la source officielle vérifiée sur le moment. time-knight vérifie la
version en vigueur, ajoute la ligne, et la mission suivante recopie ce fichier.
