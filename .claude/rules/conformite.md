<!-- consignes/conformite.md v2026-10-16 — source : time-knight. Ne pas modifier ici sans la reporter. -->
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
| OWASP Top 10 for LLM Applications | 2026 (août 2026 ; remplace 2025) | 2026-10-15 | https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/ | tout appel à un LLM : consigne, données envoyées, sortie, coût |
| OWASP Top 10 for Agentic Applications | 2026 (publiée le 09/12/2025) | 2026-10-15 | https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/ | tout agent qui choisit ses actions ou ses outils (aucun au POC du 25/10) |
| RGPD, sous-traitance et transferts (art. 28, 30, chap. V) ; fiche CNIL « registre » | règlement 2016/679 ; pages CNIL en ligne | 2026-10-16 | https://www.cnil.fr/fr/reglement-europeen-protection-donnees/chapitre4 ; https://www.cnil.fr/fr/RGPD-le-registre-des-activites-de-traitement | tout envoi de données à un fournisseur : modèle (LLM), hébergement |

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

**RGPD : sous-traitance et transferts**
- Un fournisseur qui reçoit des données pour le compte de l'utilisatrice (modèle, hébergement) est un sous-traitant :
  son contrat (DPA) est lu à la source **avant le premier envoi** (art. 28.3), et il est nommé au registre parmi les
  destinataires (art. 30.1.d).
- Lieu de traitement choisi et écrit (zone UE quand le fournisseur l'offre) ; un transfert hors UE est inscrit au
  registre avec sa garantie (chap. V).
- Un changement de fournisseur, de compte ou d'abonnement : relire le contrat et mettre le registre à jour avant.

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

**OWASP Top 10 for LLM Applications (2026)**
(Publiée le 03/08/2026 selon la page officielle ; LLM01 et LLM03 confirmés par OWASP ; les autres intitulés
viennent de sources secondaires concordantes, à revérifier dans le PDF officiel.)
- LLM01 *Prompt Injection* : le texte d'une source est une donnée, jamais une consigne ; la consigne est
  une constante ; la sortie est revalidée par le code (schéma, listes fermées) avant tout usage.
- LLM02 *Sensitive Information Disclosure* : n'envoyer au modèle que ce qui sert ; données personnelles
  retirées ou masquées avant l'envoi ; ni texte envoyé ni sortie dans les journaux.
- LLM03 *Excessive Agency* : aucun outil confié au modèle sans besoin écrit ; s'il en faut, le Top 10
  for Agentic Applications s'applique.
- LLM04 *Supply Chain* : fournisseur et modèle choisis par décision écrite ; dépendances épinglées et
  auditées.
- LLM06 *Unbounded Consumption* : borner par demande le nombre d'appels, les jetons de sortie et les
  délais.
- LLM07 *Misinformation* : chaque affirmation d'une sortie se rattache à sa source et se vérifie.
- LLM10 *Improper Output Handling* : la sortie est une entrée non fiable ; liens et balises refusés
  avant tout rendu.
- LLM05, LLM08, LLM09 : à relire à la source dès qu'un besoin les touche (entraînement, contexte caché,
  recherche vectorielle).

**OWASP Top 10 for Agentic Applications (2026)** — ASI01 à ASI10 confirmés sur la page officielle ; avant le
premier agent, relire le guide en entier.
- ASI01 *Agent Goal Hijack* : un contenu lu par l'agent ne change jamais son objectif.
- ASI02 *Tool Misuse* : outils au plus juste, paramètres validés par le code.
- ASI03 *Identity & Privilege Abuse* : l'agent agit avec ses propres droits, minimaux.

## Fraîcheur

Avant un travail qui touche un domaine de la table : si « Vérifiée le » date de plus de 30 jours,
ou qu'une nouvelle version est annoncée, revérifier à la source officielle et signaler l'écart à
Sabine. Ne pas modifier ce fichier dans le dépôt : time-knight le tient.

## Enrichir

Un domaine sans référentiel dans la table (premier appel à un LLM, première interface,
hébergement, licence d'une source…) : le **signaler** dans le `Statut` de la mission ou à Sabine,
et appliquer en attendant la source officielle vérifiée sur le moment. time-knight vérifie la
version en vigueur, ajoute la ligne, et la mission suivante recopie ce fichier.
