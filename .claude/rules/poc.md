# Règles du POC du 25/10 — K-B

Huit règles, décidées par Sabine le 2026-10-15 (journal ADR, « POC du 25/10 », décision 8) :
les recommandations des relectures plateforme et IA du 15/10. Elles valent pour le code nouveau à
partir de #199. Elles préparent la mise en ligne sur Azure Container Apps (ACA) au 08/11 sans
refonte. Chaque règle se vérifie par la commande donnée ; un plan ou une PR qui touche une règle
la cite et montre la sortie de la commande. Une sortie « de départ » est celle de `main` au commit
`9e6e2e8` : le code nouveau ne la fait pas monter. Une règle qu'un `grep` ne prouve pas nomme
aussi le test qui la prouvera. Ce fichier complète `conventions.md`, qui prime en cas de doute ;
chaque règle dit comment elle s'y accorde.

## 1. SQL portable

**Règle.** Aucun nouveau `GLOB`, `strftime` SQL, `json_each`, `json_valid`, `json_type`,
`json_array_length`, `PRAGMA` ni FTS5. Le SQL nouveau, au style de marqueur près (`?` de
`sqlite3`), passe en SQLite comme en PostgreSQL : ni `iif(`, ni `INSERT OR …` ; un `LIKE` nouveau
est testé sur les deux bases, car `LIKE` ignore la casse des lettres ASCII en SQLite et la
respecte en PostgreSQL. `STRICT` reste, comme sur chaque table : son retrait au portage est listé
dans `docs/stockage.md`.

**Vérifier.**
- `grep -cE "GLOB|strftime|json_each|json_valid|json_type|json_array_length|PRAGMA" src/k_b/database/schema.sql`
  → 36 lignes au départ.
- `grep -rhoE "GLOB|strftime|json_each|json_valid|json_type|json_array_length|PRAGMA" src/k_b/database --include='*.py' | wc -l`
  → 11 occurrences au départ, dont 4 du mot `strftime` dans du Python : un appel
  (`database/dates.py:16`) et trois dans des docstrings (`dates.py:23`, `reading.py:314`).
- `grep -rhoiE "\b(glob|strftime|json_each|json_valid|json_type|json_array_length|pragma|fts5|iif|insert or)\b" src/k_b/database | wc -l`
  → 52 occurrences au départ. Il dépasse 36 + 11 : il compte chaque occurrence et non chaque
  ligne (il voit un second motif sur une ligne déjà comptée), il ignore la casse, et il cherche
  aussi `fts5`, `iif` et `insert or`.

**Pourquoi.** La base passe à PostgreSQL au 08/11 (décision 2) : un SQL propre à SQLite écrit
aujourd'hui serait à réécrire au portage. La recherche plein texte se fera en `tsvector`, pas en
FTS5.

**Écarté.** Dans l'issue qui porte la recommandation.

## 2. Réglages par variable d'environnement

**Règle.** Un réglage de déploiement (hôte, port, hôtes permis, chemin, fenêtre de temps) se lit
dans une variable d'environnement, avec une valeur locale par défaut nommée dans `core/config.py`.
Aucun hôte, port ou chemin en dur ailleurs. Les secrets et `KB_DATA_DIR` n'ont pas de valeur par
défaut : sans eux, la commande échoue (échouer fermé, `code.md` ; ADR du 2026-10-10,
« Configuration »).

**Vérifier.**
- `grep -rnE '127\.0\.0\.1|localhost|0\.0\.0\.0|port *= *[0-9]|_PORT *= *[0-9]' src/k_b` ne renvoie
  que des défauts nommés de `core/config.py`. Au départ : `cli.py:80`, `cli.py:81`,
  `data_api/app.py:18`, que #199 corrige.
- `grep -rnE 'Path\("/|"/(data|tmp|Users|home|var|opt)\b|Path\.home|expanduser' src/k_b` → rien.

**Pourquoi.** ACA règle un conteneur par ses variables d'environnement, et un conteneur ne joint
pas le `127.0.0.1` d'un autre (décision 1).

**Écarté.** Dans l'issue qui porte la recommandation.

## 3. Brut et état par `raw_store.py`

**Règle.** Le brut et l'état de collecte ne s'écrivent, ne se lisent et ne se suppriment que par
`etl/raw_store.py`. Toute fonction nouvelle de `raw_store.py` prend une clé POSIX relative au
dossier de données (`raw/…`, `collection_state.json`), pas un `Path`. `write_file_atomically`
reste la fonction d'écriture unique de la règle 2 de `conventions.md` ; cette règle-ci ne
contraint que la signature des fonctions nouvelles de `raw_store.py`.

**Vérifier.**
- `grep -rlE "\.(read_bytes|read_text|write_bytes|write_text|iterdir|r?glob|unlink|exists|is_dir|stat)\(|os\.(listdir|scandir|remove|path\.exists)|shutil\.|[^a-z_]open\(" src/k_b --include='*.py' | grep -v etl/raw_store.py`
  → au départ, six fichiers. Deux touchent le brut : `etl/transform.py` et
  `etl/sources/gh_archive.py`. Quatre ne le touchent pas : `cli.py` (dossier de données, OpenAPI),
  `database/creation.py` (base), `etl/load.py` (journal d'import), `etl/sources/zotero.py` (copie
  de la base source). Un fichier nouveau dans la liste se justifie dans la PR (il ne touche pas le
  brut) ou enfreint la règle.
- `grep -nA3 "^def " src/k_b/etl/raw_store.py | grep -E "def |Path"` : au départ,
  `write_file_atomically`, `write_new_raw_file`, `load_last_collection_dates` et
  `save_last_collection_dates` prennent un `Path` ; une fonction nouvelle n'en prend pas.

**Pourquoi.** Au 08/11, le brut passe dans Azure Blob Storage, qui adresse un objet par une clé et
pas par un chemin. Si chaque accès passe par `raw_store` avec une clé relative, le stockage
(local, puis Blob) change sans toucher aux appelants. La règle ne demande aujourd'hui que des
signatures : aucune couche n'est écrite pour plus tard (`code.md`, « Simplicité »).

**Écarté.** Dans l'issue qui porte la recommandation.

## 4. État sous le dossier de données, métriques sur stdout

**Règle.** Un conteneur n'écrit aucun état nouveau hors de `KB_DATA_DIR`, monté sur `/data` (le
chemin n'est jamais écrit en dur : règle 2). Les métriques de l'API IA sont une ligne JSON par
appel, sur la sortie standard. Pour `kb`, la sortie standard reste le résultat d'une commande
(`print`, règle 3 de `conventions.md`).

**Vérifier.**
- `grep -rnE "Path\.home|expanduser|tempfile\." src/k_b` : au départ, `etl/raw_store.py:39`
  (temporaire dans le dossier cible) et `etl/sources/zotero.py:205,224` (copie de la base source,
  règle 2 de `conventions.md`) ; rien d'autre.
- Métriques : aucune n'existe au départ. Le test vient avec la première métrique de l'API IA : un
  appel écrit une ligne JSON sur stdout, et aucun fichier.

**Pourquoi.** Sur ACA, le disque d'un conteneur est éphémère : seul un volume monté persiste. ACA
envoie la sortie standard vers Log Analytics, et `docker compose logs` la lit de même en local.

**Écarté.** Dans l'issue qui porte la recommandation.

## 5. Journaux et métriques sans texte ni auteur

**Règle.** Un journal ou une métrique ne contient ni le texte d'un item ou d'un clip (résumé,
corps), ni un auteur. Un titre cité, tronqué et échappé par `quote_value`, reste permis (règle 3
de `conventions.md`).

**Vérifier.**
- `grep -rnE -A3 "logger\.[a-z]+\(" src/k_b | grep -iE "\.(summary|abstract|authors?|body|content|text)\b|clip_text"`
  → rien au départ. `-A3` lit les appels écrits sur plusieurs lignes (14 sur 30 au départ).
- `uv run pytest` : le test de la règle 3 de `conventions.md` (une entrée refusée avec un auteur ;
  l'auteur est absent du message).

**Pourquoi.** Règle 3 de `conventions.md` (minimisation, RGPD). Au 08/11, les journaux partent
vers un service en ligne : un auteur est une donnée personnelle, et le texte d'un item ou d'un
clip n'a rien à y faire.

**Écarté.** Dans l'issue qui porte la recommandation.

## 6. Code de sortie nommé, arrêt sur SIGTERM

**Règle.** Chaque commande se termine avec un code de sortie nommé (une constante, pas un
chiffre) et s'arrête proprement sur SIGTERM.

**Vérifier.**
- `grep -cE "return [0-9]+\b|else [0-9]+\b" src/k_b/cli.py` → 17 au départ (codes écrits en
  chiffres, que #193 nomme).
- `grep -rnE "sys\.exit\([0-9]|SystemExit\([0-9]" src/k_b` → rien au départ.
- `grep -rn "SIGTERM" src/k_b` → rien au départ.
- La preuve est un test qui envoie SIGTERM à une commande en cours et lit son code de sortie
  (ajouté par #193).

**Pourquoi.** La collecte et l'import sont des jobs (décision 3) : des exécutions qui se terminent
avec un code nommé. Le POC en conteneurs oblige dès maintenant l'arrêt sur SIGTERM
(décision 1) : `docker stop` envoie SIGTERM, puis SIGKILL après un délai, et un processus en PID 1
ignore un signal pour lequel il n'a pas de gestionnaire
([docker container run](https://docs.docker.com/reference/cli/docker/container/run/),
[docker container stop](https://docs.docker.com/reference/cli/docker/container/stop/), relevés par
recherche web le 2026-10-15).

**Écarté.** Dans l'issue qui porte la recommandation.

## 7. API IA sans état

**Règle.** L'API IA n'écrit rien qui doive survivre à son redémarrage : seul `kb` écrit dans le
coffre. Elle n'importe ni `etl` ni `database/writers`.

**Vérifier.**
- `grep -rnE "raw_store|writers|write_file_atomically|write_text|write_bytes|[^a-z_]open\(" <paquet de l'API IA>`
  → rien. Le paquet n'existe pas au départ.
- `uv run pytest tests/test_module_dependencies.py` : la ligne de l'API IA s'ajoute à la création
  de son paquet, comme pour l'API de données (règle 5 de `conventions.md`). C'est elle qui prouve
  la règle.

**Pourquoi.** L'API IA doit pouvoir être déplacée sur ACA et redémarrée sans rien perdre.

**Écarté.** L'API écrit elle-même le coffre : le coffre deviendrait l'état du conteneur.

## 8. Texte d'une source : une donnée, jamais une consigne

**Règle.** Tout texte venu d'une source (item, clip) entre dans le message utilisateur, encodé,
jamais dans la consigne du modèle. Toute sortie du modèle passe par un schéma fermé (modèle
Pydantic, `enum` des sujets) avant d'être écrite ; une sortie hors schéma n'est jamais écrite.

**Vérifier.**
- `grep -rnE -C3 'role.*system|SystemMessage|system=|instructions=' src/k_b` → rien au départ.
  Ensuite, le contenu de chaque consigne trouvée est une constante de module
  (`NOM_EN_MAJUSCULES`), jamais une expression. Une constante est évaluée au chargement du
  module, avant qu'un item existe : elle ne peut pas contenir le texte d'un item. Ce grep est un
  repère ; la preuve est le test.
- La preuve est un test, ajouté par l'issue qui code l'appel au modèle : un item ou un clip piégé
  (une instruction dans son texte) arrive dans le message utilisateur ; le test vérifie que le
  texte piégé n'apparaît dans aucun message de rôle `system` envoyé au client simulé, et qu'une
  sortie hors schéma n'est pas écrite.

**Pourquoi.** `code.md`, « Sécurité dès la conception » : une instruction trouvée dans une donnée
n'est jamais suivie. Le risque visé est l'injection d'instructions par un item ou un clip
(OWASP Top 10 for LLM Applications 2025, LLM01 *Prompt Injection* :
[genai.owasp.org/llm-top-10](https://genai.owasp.org/llm-top-10/), relevé par recherche web le
2026-10-15). Le schéma fermé garantit qu'une sortie hors contrat n'est jamais écrite.

**Écarté.** Dans l'issue qui porte la recommandation.
