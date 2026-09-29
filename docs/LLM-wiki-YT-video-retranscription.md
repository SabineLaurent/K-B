# LLM Wiki: Karpathy's approach to persistent AI knowledge bases

Wed, 23 Sept 26

## Context: Why RAG Falls Short

- RAG (Retrieval Augmented Generation) re-reads raw files from scratch on every query
- No knowledge accumulates between sessions
- Three core weaknesses:
  - Cross-document synthesis done on the fly, often incomplete
  - Contradictions between sources go unresolved
  - No durable summary: knowledge stays scattered in original files

## Karpathy’s LLM Wiki Concept

- Proposed by Andrej Karpathy (OpenAI co-founder, ex-Tesla AI lead) in April 2025
  - Published as a short GitHub gist, not a product
  - Gathered thousands of stars within days
- Core inversion: instead of re-searching raw files, the model writes and maintains a wiki
  - Each new source is read, integrated, and then set aside
  - The synthesized wiki page becomes the primary artifact, not the original file
- Karpathy’s own analogy: “Obsidian is the editor. The LLM is the programmer. The wiki is the code.”

## How the Wiki Is Structured

- Three layers:
  1. Raw sources (documents, PDFs, notes you provide)
  2. The wiki itself: Markdown pages derived and maintained by the model
  3. A rules file: instructions for naming pages, linking them, handling contradictions
- When a new source is added, the model:
  - Updates existing relevant pages
  - Creates new pages for new concepts
  - Links everything together
  - Flags contradictions explicitly on the relevant page

## Practical Use and Accessibility

- In practice: paste Karpathy’s pattern into a code-capable agent (e.g. a terminal assistant), point it at a source folder, let it build the wiki page by page
- You read and correct the result in any standard Markdown editor (e.g. Obsidian)
- Main barrier: setup requires command-line comfort
  - Karpathy himself acknowledged this: the people who need it most often lack the technical ease to set it up
  - More accessible tools are emerging that offer the same approach without the terminal

## Limits and When to Use RAG Instead

- Wiki is a model rewrite, not the source: misunderstandings propagate to linked pages
  - Must keep originals and re-check when in doubt
- Maintenance cost: each new source triggers a full read-and-update cycle, heavier than RAG indexing
- LLM Wiki suits: long-lived knowledge bases built over time
- RAG still wins for: quick, one-off questions on a small set of documents

---

## Le thème : créer un « LLM Wiki »

**Quoi ?** Une base de connaissances en pages Markdown reliées entre elles, que l’IA rédige et met à jour à mesure que tu ajoutes des documents. L’objectif est de conserver une synthèse durable, plutôt que de repartir des fichiers bruts à chaque question comme dans le fonctionnement RAG décrit dans la retranscription.

**Comment, étape par étape :**

1.  **Rassembler les sources** : notes, PDF, articles ou autres documents à organiser. Conserver les originaux pour pouvoir vérifier le wiki ensuite.
2.  **Préparer un dossier de wiki** : les connaissances synthétisées y seront écrites sous forme de pages Markdown.
3.  **Définir des règles d’entretien** : prévoir comment nommer les pages, créer des liens et signaler les contradictions entre sources.
4.  **Confier les sources à un agent capable de lire et d’écrire des fichiers** : dans l’approche présentée, on lui fournit le motif proposé par Karpathy et on le dirige vers les dossiers de sources et de notes. Il construit alors le wiki page par page.
5.  **Faire évoluer le wiki** : à chaque nouvelle source, l’agent met à jour les pages concernées, en crée si nécessaire, établit des liens et note les contradictions sur les pages pertinentes.
6.  **Relire et corriger** : ouvrir les pages dans un éditeur Markdown, vérifier les synthèses et revenir aux documents originaux en cas de doute. Une erreur de compréhension peut se propager aux pages liées.

**Quand l’utiliser ?** Pour une base documentaire appelée à grandir dans le temps. Pour une question ponctuelle sur quelques documents, la retranscription présente le RAG comme une solution plus simple.

---

Voici une version plus détaillée du **quoi** et du **comment**, en distinguant ce que décrit la retranscription des choix pratiques que tu pourrais faire.

## 1\. Comprendre ce que l’on construit

Un **LLM Wiki** est un ensemble de pages de connaissances, au format Markdown, que le modèle rédige, relie et entretient à partir de documents. Contrairement au fonctionnement RAG décrit dans la vidéo, il conserve une synthèse entre les sessions : à la prochaine source, il enrichit les pages existantes au lieu de reconstruire sa compréhension uniquement au moment d’une question.

Le montage présenté comporte **trois couches** : les sources originales, le wiki dérivé de ces sources et un fichier de règles qui indique au modèle comment entretenir ce wiki.

## 2\. Préparer les sources

Rassemble les notes, PDF et articles que tu veux intégrer. **Garde les originaux** : une page du wiki est une réécriture par le modèle, pas la source elle-même. Si une synthèse paraît douteuse, il faut pouvoir revenir au document de départ.

*Organisation possible* — c’est une suggestion pratique, pas une structure imposée dans la retranscription :

    projet/
    ├── sources/       # documents originaux
    ├── wiki/          # pages Markdown produites et entretenues
    └── regles.md      # consignes d’entretien du wiki
    

## 3\. Définir les règles du wiki

La retranscription propose un fichier qui précise notamment **comment nommer les pages, les relier et traiter les contradictions**. C’est ce cadre qui doit aider le modèle à garder un ensemble cohérent au fil des ajouts.

Pour rendre ce cadre utilisable, tu pourrais lui demander, par exemple :

-   une page par concept ou sujet clairement identifié ;
-   des liens vers les pages connexes ;
-   une indication des sources utilisées sur chaque page ;
-   une section « Points à vérifier » lorsqu’une source est ambiguë ;
-   la mention explicite de deux versions contradictoires, plutôt qu’un choix silencieux entre elles.

Ces cinq conventions sont des **propositions de mise en œuvre**. La retranscription ne fournit pas de modèle de fichier de règles prêt à copier.

## 4\. Construire une première version

Dans la méthode décrite, on donne le motif de Karpathy et les dossiers de sources à **un agent capable de lire et d’écrire des fichiers**, par exemple un assistant utilisé dans un terminal. L’agent lit les sources et fabrique le wiki page par page ; on peut ensuite ouvrir et corriger les pages dans un éditeur de notes Markdown comme Obsidian.

Concrètement, pour une première tentative, je te suggère de commencer avec **un petit ensemble de documents sur un même thème**. Cela rend la relecture des pages produites plus facile avant d’élargir la base.

## 5\. Ajouter des documents sans repartir de zéro

À chaque nouvelle source, le travail attendu du modèle est de :

1.  lire cette source ;
2.  mettre à jour les pages concernées ;
3.  créer une page si un nouveau concept apparaît ;
4.  relier les pages pertinentes ;
5.  inscrire les contradictions sur la page concernée.

C’est le cœur de l’approche : **le wiki devient l’artefact que l’on entretient**, tandis que les documents originaux restent disponibles pour vérification.

## 6\. Contrôler le résultat

Après chaque ajout, relis surtout les pages modifiées et les liens créés. Vérifie que la synthèse ne déforme pas les sources et que les désaccords entre documents sont visibles. La vidéo souligne qu’une mauvaise compréhension peut entrer dans le wiki puis se propager aux pages liées.

**Le compromis à retenir :** cette maintenance demande davantage de travail qu’une simple indexation RAG. La retranscription présente donc le LLM Wiki comme adapté à une base de connaissances que l’on fait vivre longtemps, et le RAG comme plus simple pour une question ponctuelle sur quelques documents.

---