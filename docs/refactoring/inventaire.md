# Inventaire avant refactorisation de l'ETL

Relevé du 2026-10-22, branche `refactoring/etl`, commit `51bb7ea`. Aucun fichier du dépôt n'a
été modifié pour l'écrire. Il sert de point de départ à la cible annoncée par Sabine :

```
etl/extract/     lit les sources, ne transforme rien
etl/transform/   fonctions pures, données -> données
etl/load/        écrit dans la cible
etl/pipeline.py  orchestre extract -> transform -> load, rien d'autre
post/digest/     résumés, agrégats pour humains
post/render/     rapports, affichage
```

Règles de la cible : `etl` n'importe jamais `post` ; `extract`, `transform` et `load` ne
s'importent pas entre eux, seul `pipeline` les relie.

Le relevé est factuel : il dit ce que les fichiers contiennent, pas ce qu'il faut en faire. Le
rattachement d'une fonction à un stage (partie 3) est une proposition, pas une décision.

## 1. Arborescence des fichiers suivis par git

347 fichiers suivis, dont 178 `.py` (36 773 lignes au total).

```
|-- .claude/
|   |-- rules/
|   |   |-- code.md
|   |   |-- conformite.md
|   |   |-- conventions.md
|   |   |-- methode.md
|   |   |-- outillage.md
|   |   `-- poc.md
|   |-- skills/
|   |   `-- fastapi
|   `-- settings.json
|-- .github/
|   `-- workflows/
|       `-- ci.yml
|-- docs/
|   |-- ADR/
|   |   `-- journal-decisions-projet.md
|   |-- api/
|   |   |-- openapi-donnees.json
|   |   `-- openapi-ia.json
|   |-- journaling/
|   |   |-- 2026-09-30-collecte-cisa-kev.md
|   |   |-- 2026-09-30-commande-kb-collect.md
|   |   |-- 2026-10-02-collecte-alertes-github.md
|   |   |-- 2026-10-02-collecte-arxiv.md
|   |   |-- 2026-10-02-collecte-depots-etoiles.md
|   |   |-- 2026-10-02-collecte-releases-github.md
|   |   |-- 2026-10-04-collecte-tldr-pages-brutes.md
|   |   |-- 2026-10-04-telechargement-commun.md
|   |   |-- 2026-10-05-creer-la-base.md
|   |   |-- 2026-10-05-fusionner-les-items.md
|   |   |-- 2026-10-05-importer-les-items-dans-la-base.md
|   |   |-- 2026-10-05-lire-cisa-et-releases-avant-ecriture.md
|   |   |-- 2026-10-05-lire-le-brut-en-items-communs.md
|   |   |-- 2026-10-05-resume-collecte-etat-non-ecrit.md
|   |   |-- 2026-10-06-lire-un-dossier-de-pages-brutes.md
|   |   |-- 2026-10-06-ranger-les-conversions.md
|   |   |-- 2026-10-06-releases-autonomes.md
|   |   |-- 2026-10-06-renommer-le-contrat-des-sources.md
|   |   |-- 2026-10-06-un-module-par-source.md
|   |   |-- 2026-10-06-une-seule-liste-des-sources.md
|   |   |-- 2026-10-07-clarifier-le-modele-de-la-base.md
|   |   |-- 2026-10-10-depot-suivi-release-et-alerte-github.md
|   |   |-- 2026-10-10-dossiers-du-brut-et-etat-de-collecte.md
|   |   |-- 2026-10-10-item-minimal-publication-et-vulnerabilite.md
|   |   |-- 2026-10-10-longueurs-maximales-et-controle-des-check.md
|   |   |-- 2026-10-10-nommer-le-flux-arxiv.md
|   |   |-- 2026-10-10-sortir-le-code-du-init-de-database.md
|   |   |-- 2026-10-10-tables-de-reference-et-mode-acquisition.md
|   |   |-- 2026-10-11-extraire-la-bibliotheque-zotero.md
|   |   |-- 2026-10-11-reperer-les-depots-qui-montent-gh-archive.md
|   |   |-- 2026-10-12-importer-seulement-les-bruts-nouveaux.md
|   |   |-- 2026-10-12-laisser-la-base-dedoublonner-les-items.md
|   |   |-- 2026-10-12-lecture-articles-tldr.md
|   |   |-- 2026-10-13-lire-l-extrait-zotero-vers-la-base.md
|   |   |-- 2026-10-13-mettre-les-depots-qui-montent-en-base.md
|   |   |-- 2026-10-13-ranger-le-parcours-dans-etl.md
|   |   |-- 2026-10-13-types-communs-dans-items.md
|   |   |-- 2026-10-14-journaux-horodates-et-fichier-de-journal.md
|   |   |-- 2026-10-14-lire-les-items-en-lecture-seule.md
|   |   |-- 2026-10-14-servir-la-liste-par-une-api-locale.md
|   |   |-- 2026-10-14-sql-d-ecriture-dans-database-writers.md
|   |   |-- 2026-10-15-appeler-le-modele-et-son-remplacement.md
|   |   |-- 2026-10-15-lire-la-veille-par-l-api-de-donnees.md
|   |   |-- 2026-10-15-reglages-serve-et-health.md
|   |   |-- 2026-10-15-servir-le-detail-et-les-tendances.md
|   |   |-- 2026-10-15-specifier-les-fiches-de-veille.md
|   |   |-- 2026-10-16-brancher-gemini-en-repli.md
|   |   |-- 2026-10-16-ecarter-une-entree-invalide-d-une-source.md
|   |   |-- 2026-10-16-ecrire-par-un-temporaire-cache.md
|   |   |-- 2026-10-16-journaliser-un-rejet-sans-la-valeur-recue.md
|   |   |-- 2026-10-16-rejeter-l-item-que-la-base-refuse.md
|   |   |-- 2026-10-17-brancher-gpt-6-luna-sur-foundry.md
|   |   |-- 2026-10-17-classer-les-items-et-rediger-les-fiches.md
|   |   |-- 2026-10-17-collecter-les-clips-du-coffre-obsidian.md
|   |   |-- 2026-10-17-lancer-la-ci-sur-main-en-jobs-nommes.md
|   |   |-- 2026-10-18-aligner-la-spec-de-collecte-sur-le-code.md
|   |   |-- 2026-10-18-choisir-les-sources-collectees.md
|   |   |-- 2026-10-18-marquer-le-retrait-et-ranger-les-tests-d-architecture.md
|   |   |-- 2026-10-18-nommer-les-codes-de-sortie-de-kb.md
|   |   |-- 2026-10-18-ranger-l-api-ia-par-role.md
|   |   |-- 2026-10-18-ranger-la-ligne-de-commande.md
|   |   |-- 2026-10-18-rassembler-le-choix-des-ecrivains.md
|   |   |-- 2026-10-18-rassembler-les-routeurs-de-l-api-de-donnees.md
|   |   |-- 2026-10-19-annoncer-les-sources-et-le-jeton-github.md
|   |   |-- 2026-10-19-collecter-le-top-des-depots-forkes.md
|   |   |-- 2026-10-19-ecrire-les-fiches-des-tops.md
|   |   |-- 2026-10-19-garder-les-tags-des-clips.md
|   |   |-- 2026-10-19-ne-garder-que-le-dernier-brut-des-catalogues-d-etat.md
|   |   |-- 2026-10-19-presenter-le-projet-dans-le-readme.md
|   |   |-- 2026-10-19-reecrire-un-clip-dont-le-contenu-a-change.md
|   |   |-- 2026-10-19-renommer-la-liaison-des-tags.md
|   |   |-- 2026-10-20-consigner-les-decisions-de-cadrage.md
|   |   |-- 2026-10-20-redessiner-le-modele-merise-depuis-le-schema.md
|   |   |-- 2026-10-20-refuser-une-page-tldr-qui-n-est-pas-l-edition.md
|   |   |-- 2026-10-20-sortir-le-juge-du-contrat-des-fiches.md
|   |   |-- 2026-10-21-ecrire-les-fiches-de-veille-dans-le-coffre.md
|   |   |-- 2026-10-21-rapport-et-variables-des-tests-de-bout-en-bout.md
|   |   |-- 2026-10-21-refuser-un-lien-ou-une-balise-dans-une-fiche.md
|   |   |-- 2026-10-21-roder-la-collecte-sur-donnees-reelles.md
|   |   `-- 2026-10-21-servir-les-fiches-par-l-api-ia.md
|   |-- merise/
|   |   |-- mcd-k-b.drawio
|   |   |-- mcd-k-b_20261012.drawio
|   |   |-- mcd-k-b_20261020.drawio
|   |   |-- mcd-k-b_20261020.svg
|   |   |-- mcd-k-b_20261020_vue-ensemble.drawio
|   |   |-- mcd-k-b_20261020_vue-ensemble.svg
|   |   |-- mld-k-b.drawio
|   |   |-- mld-k-b_20261012.drawio
|   |   |-- mld-k-b_20261020.drawio
|   |   |-- mld-k-b_20261020.svg
|   |   `-- positions-mcd.md
|   |-- veille/
|   |   |-- 2026-09-23-fiches-existant/
|   |   |   |-- Astro-Han_karpathy-llm-wiki.md
|   |   |   |-- Encod3d-Sec_ClaudeBrain.md
|   |   |   |-- JanYork_llm-wiki-cli.md
|   |   |   |-- OrangeproAI_orangepro-mcp.md
|   |   |   |-- Tencent_WeKnora.md
|   |   |   |-- XBlueSky_cortexes.md
|   |   |   |-- akitaonrails_ai-memory.md
|   |   |   |-- brief09_assistant-veille-tech.md
|   |   |   |-- frankchu91_mindbase.md
|   |   |   |-- gist_rohitg00_llm-wiki-v2.md
|   |   |   |-- gowtham0992_link.md
|   |   |   |-- j-wang_knowledge-agent-template.md
|   |   |   |-- jp-lorenc1o_Eva-brain.md
|   |   |   |-- notfounnd_marc-server.md
|   |   |   |-- skyllwt_AutoSci.md
|   |   |   |-- suwonleee_llmwiki.md
|   |   |   `-- toolboxmd_karpathy-wiki.md
|   |   |-- 2026-09-23-veille-existant.md
|   |   |-- LLM-wiki-YT-video-retranscription.md
|   |   `-- article-DataCamp-llm-wiki-points-cl\303\251s.md
|   |-- 2026-10-04-flux-donnees.md
|   |-- 2026-10-06-plan-etl.md
|   |-- 2026-10-06-revue-architecture.md
|   |-- 2026-10-07-clarification-modele.md
|   |-- 2026-10-11-gh-archive-evenements-par-heure.csv
|   |-- 2026-10-11-revue-homogeneite.md
|   |-- 2026-10-16-express-mvc-et-fastapi.md
|   |-- 2026-10-21-collecte-reelle.md
|   |-- bigquery.md
|   |-- fiches-veille.md
|   |-- jeton-github.md
|   |-- registre-traitements.md
|   |-- requetes-extraction.md
|   |-- sources-detaillees.md
|   |-- sources.md
|   |-- specs-api.md
|   |-- specs-collecte.md
|   `-- stockage.md
|-- src/
|   `-- k_b/
|       |-- ai_api/
|       |   |-- connectors/
|       |   |   |-- __init__.py
|       |   |   |-- data_api_client.py
|       |   |   |-- data_api_settings.py
|       |   |   |-- llm_client.py
|       |   |   |-- llm_replay.py
|       |   |   `-- llm_settings.py
|       |   |-- routers/
|       |   |   |-- __init__.py
|       |   |   `-- digest_router.py
|       |   |-- schemas/
|       |   |   |-- __init__.py
|       |   |   `-- digest_schema.py
|       |   |-- stages/
|       |   |   |-- __init__.py
|       |   |   |-- classification.py
|       |   |   `-- writing.py
|       |   |-- __init__.py
|       |   |-- api_router.py
|       |   |-- app.py
|       |   |-- deadline.py
|       |   |-- dependencies.py
|       |   |-- digests.py
|       |   |-- errors.py
|       |   |-- metrics.py
|       |   |-- settings.py
|       |   `-- watch_items.py
|       |-- commands/
|       |   |-- __init__.py
|       |   |-- collect_command.py
|       |   |-- create_db_command.py
|       |   |-- digest_command.py
|       |   |-- environment.py
|       |   |-- exit_codes.py
|       |   |-- import_command.py
|       |   |-- openapi_command.py
|       |   |-- run_log.py
|       |   |-- serve_ai_command.py
|       |   |-- serve_command.py
|       |   |-- sigterm.py
|       |   `-- write_tops_command.py
|       |-- core/
|       |   |-- __init__.py
|       |   |-- api_access.py
|       |   |-- api_errors.py
|       |   |-- api_health.py
|       |   |-- api_keys.py
|       |   |-- api_request_log.py
|       |   |-- api_settings.py
|       |   |-- config.py
|       |   |-- outbound.py
|       |   `-- quoting.py
|       |-- data_api/
|       |   |-- routers/
|       |   |   |-- __init__.py
|       |   |   |-- item_router.py
|       |   |   `-- trend_router.py
|       |   |-- schemas/
|       |   |   |-- __init__.py
|       |   |   |-- item_schema.py
|       |   |   `-- trend_schema.py
|       |   |-- __init__.py
|       |   |-- api_router.py
|       |   |-- app.py
|       |   |-- dependencies.py
|       |   |-- errors.py
|       |   `-- settings.py
|       |-- database/
|       |   |-- writers/
|       |   |   |-- __init__.py
|       |   |   |-- advisory_writer.py
|       |   |   |-- catalog.py
|       |   |   |-- clip_writer.py
|       |   |   |-- discard.py
|       |   |   |-- newsletter_article_writer.py
|       |   |   |-- paper_writer.py
|       |   |   |-- release_writer.py
|       |   |   |-- shared_rows.py
|       |   |   |-- trend_writer.py
|       |   |   |-- vulnerability_writer.py
|       |   |   `-- zotero_entry_writer.py
|       |   |-- __init__.py
|       |   |-- connection.py
|       |   |-- creation.py
|       |   |-- dates.py
|       |   |-- reading.py
|       |   |-- savepoint.py
|       |   |-- schema.sql
|       |   |-- seed_sources.sql
|       |   `-- writing.py
|       |-- etl/
|       |   |-- sources/
|       |   |   |-- __init__.py
|       |   |   |-- arxiv.py
|       |   |   |-- cisa_kev.py
|       |   |   |-- clipping.py
|       |   |   |-- gh_archive.py
|       |   |   |-- github_advisories.py
|       |   |   |-- github_api.py
|       |   |   |-- github_most_forked.py
|       |   |   |-- github_most_starred.py
|       |   |   |-- github_releases.py
|       |   |   |-- tldr.py
|       |   |   |-- tracked_repositories.py
|       |   |   `-- zotero.py
|       |   |-- __init__.py
|       |   |-- ai_api_client.py
|       |   |-- collected_sources.py
|       |   |-- digest_sheets.py
|       |   |-- extract.py
|       |   |-- http_download.py
|       |   |-- import_log.py
|       |   |-- load.py
|       |   |-- normalize.py
|       |   |-- raw_purge.py
|       |   |-- raw_store.py
|       |   |-- source_contract.py
|       |   |-- source_kinds.py
|       |   |-- top_sheets.py
|       |   |-- transform.py
|       |   |-- user_agent.py
|       |   `-- vault_files.py
|       |-- __init__.py
|       |-- cli.py
|       `-- items.py
|-- tests/
|   |-- ai_api/
|   |   |-- test_ai_api_openapi.py
|   |   |-- test_data_api_client.py
|   |   |-- test_data_api_settings.py
|   |   |-- test_deadline.py
|   |   |-- test_digest_router.py
|   |   |-- test_digests.py
|   |   |-- test_llm_client.py
|   |   |-- test_llm_replay.py
|   |   |-- test_llm_settings.py
|   |   |-- test_serve_ai.py
|   |   |-- test_stages.py
|   |   `-- test_watch_items.py
|   |-- architecture/
|   |   |-- module_imports.py
|   |   |-- test_apis.py
|   |   |-- test_import_reading.py
|   |   |-- test_layers.py
|   |   `-- test_packages.py
|   |-- data_api/
|   |   |-- conftest.py
|   |   |-- test_api_errors.py
|   |   |-- test_api_keys.py
|   |   |-- test_health.py
|   |   |-- test_item_router.py
|   |   |-- test_openapi.py
|   |   |-- test_request_log.py
|   |   |-- test_serve.py
|   |   `-- test_trend_router.py
|   |-- database/
|   |   |-- test_connection.py
|   |   |-- test_reading.py
|   |   |-- test_savepoint.py
|   |   `-- test_writers.py
|   |-- e2e/
|   |   `-- test_real_sources.py
|   |-- etl/
|   |   |-- sources/
|   |   |   |-- test_arxiv.py
|   |   |   |-- test_cisa_kev.py
|   |   |   |-- test_clipping.py
|   |   |   |-- test_gh_archive.py
|   |   |   |-- test_github_advisories.py
|   |   |   |-- test_github_api.py
|   |   |   |-- test_github_most_forked.py
|   |   |   |-- test_github_most_starred.py
|   |   |   |-- test_github_releases.py
|   |   |   |-- test_tldr.py
|   |   |   |-- test_tracked_repositories.py
|   |   |   `-- test_zotero.py
|   |   |-- test_ai_api_client.py
|   |   |-- test_digest_sheets.py
|   |   |-- test_extract.py
|   |   |-- test_http_download.py
|   |   |-- test_import_log.py
|   |   |-- test_load.py
|   |   |-- test_load_clips.py
|   |   |-- test_load_zotero.py
|   |   |-- test_normalize.py
|   |   |-- test_raw_purge.py
|   |   |-- test_raw_store.py
|   |   |-- test_source_contract.py
|   |   |-- test_source_kinds.py
|   |   |-- test_top_sheets.py
|   |   |-- test_transform.py
|   |   `-- test_vault_files.py
|   |-- fixtures/
|   |   |-- clipping/
|   |   |   |-- article_with_author.md
|   |   |   |-- page_with_a_rule_in_its_text.md
|   |   |   `-- page_without_author_or_date.md
|   |   |-- arxiv_extract.xml
|   |   |-- cisa_kev_extract.csv
|   |   |-- gh_archive_extract.json
|   |   |-- github_advisories_extract.json
|   |   |-- github_most_forked_extract.json
|   |   |-- github_most_starred_extract.json
|   |   |-- github_releases_extract.json
|   |   |-- items_database.sql
|   |   |-- tldr_ai_extract.html
|   |   |-- tldr_ai_landing_extract.html
|   |   |-- tldr_ai_trapped_extract.html
|   |   |-- tldr_dev_extract.html
|   |   `-- zotero_extract.sql
|   |-- conftest.py
|   |-- test_cli.py
|   |-- test_database.py
|   |-- test_e2e_selection.py
|   |-- test_items.py
|   |-- test_outbound.py
|   |-- test_package.py
|   |-- test_quoting.py
|   `-- test_schema.py
|-- .env.e2e_test.example
|-- .env.example
|-- .gitignore
|-- .python-version
|-- CLAUDE.md
|-- LICENSE
|-- MEMORY.md
|-- README.md
|-- pyproject.toml
`-- uv.lock
```

## 2. Les `.py` par nombre de lignes, du plus long au plus court

178 fichiers. Le nombre de lignes est celui de `wc -l` (lignes physiques, docstrings et lignes
vides comprises).

```
  2011  tests/test_cli.py
  1983  tests/etl/test_load.py
  1254  tests/test_schema.py
   955  tests/ai_api/test_digests.py
   879  tests/ai_api/test_llm_client.py
   846  tests/test_items.py
   793  tests/etl/sources/test_zotero.py
   712  tests/etl/sources/test_gh_archive.py
   688  tests/ai_api/test_data_api_client.py
   671  tests/etl/sources/test_clipping.py
   659  tests/etl/test_transform.py
   648  tests/ai_api/test_digest_router.py
   596  tests/etl/test_top_sheets.py
   596  tests/etl/sources/test_tldr.py
   572  tests/etl/test_load_zotero.py
   563  tests/etl/test_load_clips.py
   559  tests/database/test_reading.py
   546  src/k_b/items.py
   525  tests/etl/test_digest_sheets.py
   494  tests/etl/test_ai_api_client.py
   493  src/k_b/database/reading.py
   489  src/k_b/ai_api/connectors/llm_client.py
   463  src/k_b/etl/sources/zotero.py
   430  src/k_b/etl/load.py
   426  src/k_b/etl/sources/gh_archive.py
   423  tests/etl/test_extract.py
   397  src/k_b/etl/sources/clipping.py
   371  tests/data_api/test_serve.py
   365  tests/data_api/test_item_router.py
   363  tests/etl/test_raw_store.py
   354  src/k_b/ai_api/connectors/data_api_client.py
   353  tests/etl/sources/test_arxiv.py
   351  tests/etl/sources/test_github_releases.py
   351  tests/ai_api/test_serve_ai.py
   350  tests/ai_api/test_stages.py
   329  tests/e2e/test_real_sources.py
   328  src/k_b/ai_api/digests.py
   325  src/k_b/etl/sources/tldr.py
   299  src/k_b/etl/ai_api_client.py
   297  tests/etl/sources/test_github_advisories.py
   291  tests/etl/sources/test_cisa_kev.py
   290  tests/test_e2e_selection.py
   237  src/k_b/etl/sources/arxiv.py
   237  src/k_b/ai_api/stages/classification.py
   231  src/k_b/core/config.py
   227  src/k_b/etl/top_sheets.py
   225  tests/architecture/test_apis.py
   219  src/k_b/etl/transform.py
   218  tests/ai_api/test_llm_settings.py
   217  src/k_b/etl/sources/cisa_kev.py
   217  src/k_b/ai_api/stages/writing.py
   212  tests/etl/sources/test_github_most_forked.py
   209  src/k_b/database/writers/clip_writer.py
   207  src/k_b/etl/digest_sheets.py
   207  src/k_b/database/writers/zotero_entry_writer.py
   205  tests/ai_api/test_watch_items.py
   202  src/k_b/etl/sources/github_advisories.py
   202  src/k_b/etl/raw_store.py
   198  src/k_b/ai_api/watch_items.py
   195  tests/etl/sources/test_github_most_starred.py
   191  src/k_b/etl/sources/github_releases.py
   166  tests/database/test_savepoint.py
   162  tests/conftest.py
   149  src/k_b/cli.py
   148  src/k_b/ai_api/connectors/llm_replay.py
   147  tests/etl/test_raw_purge.py
   147  tests/data_api/test_request_log.py
   147  src/k_b/etl/sources/github_most_starred.py
   146  tests/etl/test_http_download.py
   146  src/k_b/ai_api/routers/digest_router.py
   145  src/k_b/core/api_errors.py
   144  tests/data_api/test_api_keys.py
   143  tests/architecture/test_layers.py
   142  tests/etl/test_vault_files.py
   135  tests/data_api/test_api_errors.py
   134  src/k_b/ai_api/connectors/llm_settings.py
   131  src/k_b/commands/digest_command.py
   126  src/k_b/etl/sources/github_most_forked.py
   124  src/k_b/database/writers/vulnerability_writer.py
   124  src/k_b/data_api/schemas/item_schema.py
   123  src/k_b/etl/source_contract.py
   121  src/k_b/etl/collected_sources.py
   120  src/k_b/data_api/routers/item_router.py
   119  tests/data_api/test_openapi.py
   117  tests/data_api/test_trend_router.py
   116  src/k_b/etl/vault_files.py
   115  tests/ai_api/test_ai_api_openapi.py
   114  tests/architecture/test_import_reading.py
   114  tests/architecture/module_imports.py
   114  src/k_b/ai_api/metrics.py
   113  src/k_b/commands/collect_command.py
   108  src/k_b/etl/source_kinds.py
   106  src/k_b/commands/import_command.py
    99  src/k_b/etl/extract.py
    98  tests/ai_api/test_data_api_settings.py
    97  tests/ai_api/test_llm_replay.py
    94  src/k_b/commands/run_log.py
    92  tests/etl/test_source_contract.py
    90  src/k_b/database/writers/release_writer.py
    89  tests/etl/test_source_kinds.py
    89  src/k_b/etl/import_log.py
    87  src/k_b/core/api_request_log.py
    81  tests/test_quoting.py
    81  src/k_b/database/writers/trend_writer.py
    81  src/k_b/ai_api/schemas/digest_schema.py
    78  tests/database/test_writers.py
    78  src/k_b/commands/serve_ai_command.py
    78  src/k_b/commands/openapi_command.py
    76  src/k_b/database/writing.py
    75  src/k_b/database/savepoint.py
    74  tests/etl/sources/test_github_api.py
    74  src/k_b/etl/http_download.py
    73  src/k_b/data_api/settings.py
    73  src/k_b/core/api_keys.py
    72  src/k_b/database/writers/catalog.py
    71  src/k_b/commands/write_tops_command.py
    68  src/k_b/database/writers/newsletter_article_writer.py
    67  src/k_b/database/writers/shared_rows.py
    65  src/k_b/database/writers/advisory_writer.py
    61  src/k_b/core/quoting.py
    61  src/k_b/ai_api/connectors/data_api_settings.py
    60  src/k_b/ai_api/app.py
    59  src/k_b/database/writers/paper_writer.py
    59  src/k_b/ai_api/settings.py
    58  src/k_b/commands/exit_codes.py
    57  src/k_b/ai_api/errors.py
    57  src/k_b/ai_api/deadline.py
    56  tests/test_database.py
    56  src/k_b/data_api/app.py
    54  tests/database/test_connection.py
    54  src/k_b/core/outbound.py
    53  tests/ai_api/test_deadline.py
    53  src/k_b/data_api/routers/trend_router.py
    51  src/k_b/data_api/errors.py
    50  tests/test_outbound.py
    50  src/k_b/commands/sigterm.py
    48  tests/etl/test_normalize.py
    48  src/k_b/core/api_access.py
    47  src/k_b/etl/sources/tracked_repositories.py
    45  src/k_b/commands/environment.py
    44  tests/data_api/conftest.py
    41  src/k_b/database/connection.py
    41  src/k_b/commands/serve_command.py
    39  src/k_b/etl/raw_purge.py
    37  tests/architecture/test_packages.py
    36  src/k_b/database/creation.py
    36  src/k_b/ai_api/dependencies.py
    33  src/k_b/etl/sources/github_api.py
    32  src/k_b/etl/normalize.py
    31  src/k_b/core/api_settings.py
    30  tests/etl/sources/test_tracked_repositories.py
    26  src/k_b/commands/create_db_command.py
    25  src/k_b/database/dates.py
    22  tests/data_api/test_health.py
    22  src/k_b/data_api/dependencies.py
    19  src/k_b/data_api/schemas/trend_schema.py
    18  src/k_b/database/writers/discard.py
    15  src/k_b/core/api_health.py
    10  tests/etl/test_import_log.py
    10  src/k_b/data_api/api_router.py
     9  src/k_b/ai_api/api_router.py
     5  tests/test_package.py
     5  src/k_b/etl/user_agent.py
     0  src/k_b/etl/sources/__init__.py
     0  src/k_b/etl/__init__.py
     0  src/k_b/database/writers/__init__.py
     0  src/k_b/database/__init__.py
     0  src/k_b/data_api/schemas/__init__.py
     0  src/k_b/data_api/routers/__init__.py
     0  src/k_b/data_api/__init__.py
     0  src/k_b/core/__init__.py
     0  src/k_b/commands/__init__.py
     0  src/k_b/ai_api/stages/__init__.py
     0  src/k_b/ai_api/schemas/__init__.py
     0  src/k_b/ai_api/routers/__init__.py
     0  src/k_b/ai_api/connectors/__init__.py
     0  src/k_b/ai_api/__init__.py
     0  src/k_b/__init__.py
```

Lecture : les 17 premiers fichiers de la liste sont des tests (`tests/test_cli.py` 2 011,
`tests/etl/test_load.py` 1 983, `tests/test_schema.py` 1 254…) : 24 122 lignes sous `tests/`
pour 12 651 sous `src/`. Côté code, la tête de liste est
`src/k_b/items.py` (546), `src/k_b/database/reading.py` (493),
`src/k_b/ai_api/connectors/llm_client.py` (489), `src/k_b/etl/sources/zotero.py` (463) et
`src/k_b/etl/load.py` (430).

Les 28 modules de `src/k_b/etl/` (les deux `__init__.py` vides exclus), par taille :

| Module | Lignes | Ce qu'il fait aujourd'hui |
|---|---|---|
| `sources/zotero.py` | 463 | extract + transform (sa docstring dit « (E) … then … (T) ») |
| `load.py` | 430 | load + orchestration de la transaction et du journal |
| `sources/gh_archive.py` | 426 | extract + transform (requête BigQuery, puis conversion) |
| `sources/clipping.py` | 397 | extract + transform |
| `sources/tldr.py` | 325 | extract + transform |
| `ai_api_client.py` | 299 | **post** : client HTTP de l'API IA, pour `kb digest` |
| `sources/arxiv.py` | 237 | extract + transform |
| `top_sheets.py` | 227 | **post/render** : fiches `.md` des tops |
| `transform.py` | 219 | transform (lecture du brut en items, rejets) |
| `sources/cisa_kev.py` | 217 | extract + transform |
| `digest_sheets.py` | 207 | **post/digest** + **post/render** : fiches de veille |
| `sources/github_advisories.py` | 202 | extract + transform |
| `raw_store.py` | 202 | extract/load : écriture atomique du brut et de l'état |
| `sources/github_releases.py` | 191 | extract + transform |
| `sources/github_most_starred.py` | 147 | extract + transform |
| `sources/github_most_forked.py` | 126 | extract + transform |
| `source_contract.py` | 123 | vocabulaire : le contrat E et T que chaque source remplit |
| `collected_sources.py` | 121 | pipeline : les sources que `kb collect` fait tourner |
| `vault_files.py` | 116 | **post/render** : écriture dans le coffre Obsidian |
| `source_kinds.py` | 108 | vocabulaire : nature d'une source (règles de doublon) |
| `extract.py` | 99 | pipeline : `collect_all_sources` |
| `import_log.py` | 89 | load : journal d'import |
| `http_download.py` | 74 | extract : téléchargement commun |
| `sources/tracked_repositories.py` | 47 | vocabulaire : les dépôts suivis |
| `raw_purge.py` | 39 | purge du brut (ni E, ni T, ni L) |
| `sources/github_api.py` | 33 | extract : un GET sur l'API REST GitHub |
| `normalize.py` | 32 | transform |
| `user_agent.py` | 5 | extract (en-tête HTTP) |

Quatre modules de `etl/` relèvent déjà de `post/` dans la cible : `ai_api_client.py`,
`top_sheets.py`, `digest_sheets.py` et `vault_files.py`.

## 3. Le module le plus long, fonction par fonction

Le plus long `.py` suivi est `tests/test_cli.py` (2 011 lignes) : rattacher ses fonctions à un
stage n'a pas de sens. Le relevé porte donc sur le plus long module de code,
`src/k_b/items.py` (546 lignes) — et, parce que celui-ci est le vocabulaire commun et ne dit
presque rien des stages, sur les deux plus longs modules de `etl/`, qui sont les cibles réelles
de la refactorisation : `etl/sources/zotero.py` (463) et `etl/load.py` (430).

### 3.1 `src/k_b/items.py` — 546 lignes

Module de vocabulaire : types partagés, modèles Pydantic `Item`, `Highlight`, `TrendRow`, et
leurs validateurs. 200 lignes environ sont des constantes et des tables (`REQUIRED_FIELDS_BY_KIND`,
`MAX_LENGTH_BY_KIND`…), pas des fonctions.

| Fonction | Lignes | Appelle | Stage |
|---|---|---|---|
| `check_url_can_be_normalized` | 85-97 (13) | `urlsplit`, `len`, `ValueError` | transform (validation) |
| `check_text_can_be_stored` | 104-112 (9) | `UNSTORABLE_CHARACTER.search`, `len` | transform |
| `normalize_tag` | 115-118 (4) | `lower`, `strip`, `removeprefix` | transform |
| `check_tag_length` | 121-128 (8) | `len` | transform |
| `check_tag_is_normalized` | 131-136 (6) | `normalize_tag`, `len` | transform |
| `convert_to_utc` | 139-145 (7) | `moment.astimezone` | transform |
| `at_midnight_utc` | 148-151 (4) | `datetime.combine`, `time` | transform |
| `parse_aware_datetime` | 154-167 (14) | `datetime.fromisoformat`, `quote_value`, `isinstance` | transform (lit une date venue de la base) |
| `Highlight.check_text_or_comment` | 353-356 (4) | `model_validator` | transform |
| `Item.check_the_fields_of_its_kind` | 407-417 (11) | `check_source`, `check_required_fields`, `check_fields_of_other_kinds`, `check_cve`, `check_lengths`, `check_url_scheme`, `check_source_item_id`, `check_tag_count`, `check_tags_once` | transform (chef d'orchestre des neuf contrôles) |
| `check_source` | 420-423 (4) | `SOURCE_BY_KIND.get` | transform |
| `check_required_fields` | 426-437 (12) | `REQUIRED_FIELDS_BY_KIND.get`, `getattr` | transform |
| `check_fields_of_other_kinds` | 440-449 (10) | `FIELDS_OF_ONE_KIND.items`, `getattr` | transform |
| `check_cve` | 452-454 (3) | — | transform |
| `check_url_scheme` | 457-465 (9) | `item.url.startswith`, `len` | transform |
| `check_source_item_id` | 468-478 (11) | `SOURCE_ITEM_ID_BY_KIND.get`, `re.fullmatch`, `int` | transform |
| `check_tag_count` | 481-485 (5) | `len` | transform |
| `check_tags_once` | 488-493 (6) | `set`, `len` | transform |
| `check_lengths` | 496-501 (6) | `list_texts_too_long`, `list_lists_too_long` | transform |
| `list_texts_too_long` | 504-512 (9) | `getattr`, `MAX_LENGTH_BY_KIND.get` | transform |
| `list_lists_too_long` | 515-528 (14) | `getattr`, `MAX_COUNT_BY_KIND.get`, `MAX_ELEMENT_LENGTH_BY_KIND.get`, `max`, `map` | transform |

**Aucune fonction mixte.** Les 21 fonctions sont pures (données -> données, ou lever une erreur)
et n'appellent rien d'extérieur sauf `quote_value` (`core/quoting.py`). Au sens de la cible, le
module entier est du `transform` ; mais la règle 5 de `conventions.md` en fait le vocabulaire
commun à toutes les couches, importable par chacune. Si `items.py` partait dans `etl/transform/`,
`database/`, `data_api/` et `ai_api/` importeraient `etl` — ce que la cible interdit. **`items.py`
n'est pas un candidat au déplacement** : sa longueur vient de ses tables de constantes, pas d'un
mélange d'étapes.

### 3.2 `src/k_b/etl/sources/zotero.py` — 463 lignes, le plus long module de `etl/`

Sa propre docstring annonce le mélange : « extract the documents of the user's library and their
highlights (E), then read an extract into Zotero entries (T) ».

| Fonction | Lignes | Appelle | Stage |
|---|---|---|---|
| `ZoteroSource.__init__` | 199-201 (3) | — | — |
| `ZoteroSource.fetch` | 203-237 (35) | `remove_left_copies`, `copy_library`, `extract_documents`, `read_each_entry`, `check_not_empty`, `check_not_all_invalid`, `self.store.read_latest`, `json.dumps`, `logger.info` | **mixte** : extract (copie, requête) + transform (`read_each_entry`, contrôles de validité) + écriture du brut |
| `remove_left_copies` | 240-258 (19) | `glob`, `path.lstat`, `shutil.rmtree`, `os.getuid`, `stat.S_ISDIR`, `tempfile.gettempdir` | extract (ménage d'avant-collecte) |
| `read_file_states` | 261-269 (9) | `read_file_state` | extract |
| `read_file_state` | 272-274 (3) | `path.stat` | extract |
| `copy_library` | 277-297 (21) | `read_file_states`, `shutil.copyfile`, `contextlib.suppress` | extract |
| `extract_documents` | 300-319 (20) | `check_integrity`, `sqlite3.connect`, `connection.execute`, `json.loads`, `describe_query_error` | extract (lecture seule de la base source) |
| `check_integrity` | 322-334 (13) | `connection.execute` | extract |
| `describe_query_error` | 337-347 (11) | `MESSAGE_ABOUT_THE_QUERY.fullmatch`, `getattr` | extract (message d'erreur) |
| `mark_as_utc` | 350-355 (6) | `ZOTERO_DATE.fullmatch` | transform |
| `read_arxiv_id` | 358-367 (10) | `ARXIV_REFERENCE.fullmatch`, `reference.group` | transform |
| `read_documents` | 402-411 (10) | `EntryReading`, `json.loads` | transform |
| `check_document` | 414-420 (7) | `ZoteroDocument.model_validate`, `without_values` | transform |
| `convert_document` | 423-458 (36) | `ZoteroDocument.model_validate`, `Item`, `Highlight`, `without_values` | transform |

Une seule fonction est mixte, mais c'est la porte d'entrée : `fetch` enchaîne extract, transform
et écriture du brut. Le reste se coupe net : 8 fonctions d'extract (96 lignes), 5 de transform
(69 lignes), plus les modèles Pydantic `ZoteroDocument` et `ZoteroHighlight` (25 lignes) qui vont
avec le transform. Les 12 autres sources suivent le même dessin (un `fetch` au contrat de
`source_contract.py`, puis des fonctions de conversion) : la coupure E/T est la même pour toutes.

### 3.3 `src/k_b/etl/load.py` — 430 lignes

| Fonction | Lignes | Appelle | Stage |
|---|---|---|---|
| `read_imported_paths` | 86-93 (8) | `check_database_exists`, `connect_database`, `read_raw_file_paths` | load (lecture du registre) |
| `import_items` | 107-143 (37) | `connect_database`, `write_tracked_repositories`, `write_files`, `commit_with_log`, `connection.rollback` | **pipeline** : ouvre la transaction, enchaîne les étapes, rend le résumé |
| `write_files` | 146-169 (24) | `join_writings`, `write_file`, `list_files_in_collection_order` | load |
| `join_writings` | 172-184 (13) | `sum` | transform (agrégation pure de `FileWriting`) |
| `write_file` | 187-194 (8) | `write_items_file`, `write_trend_file` | load (aiguillage) |
| `commit_with_log` | 197-232 (36) | `check_log_absent`, `write_import_log`, `connection.commit`, `log_path.unlink`, `quote_value` | **mixte** : écrit le journal (fichier) et commite la base, et défait le journal si le commit échoue |
| `list_files_in_collection_order` | 235-246 (12) | `sorted` | transform (tri pur) |
| `reject_untracked_releases` | 249-274 (26) | `reject`, `lower` | transform (filtre pur, rend les gardés et les rejets) |
| `write_items_file` | 277-310 (34) | `reject_untracked_releases`, `register_raw_file`, `normalize_item`, `write_item_in_savepoint`, `mark_withdrawn_vulnerabilities`, `mark_withdrawn_zotero_rows` | **mixte** : transform (`reject_untracked_releases`, `normalize_item`) puis load |
| `write_item_in_savepoint` | 313-330 (18) | `write_in_savepoint`, `write_item`, `reject`, `quote_value` | load |
| `register_raw_file` | 333-341 (9) | `write_raw_data`, `find_stream` | load |
| `write_trend_file` | 344-382 (39) | `write_in_savepoint`, `register_raw_file`, `write_trend_rows`, `reject`, `TrendDiscard` | load |
| `mark_withdrawn_vulnerabilities` | 385-407 (23) | `mark_withdrawn_vulnerabilities_not_in` | load |
| `mark_withdrawn_zotero_rows` | 410-424 (15) | `mark_withdrawn_zotero_rows_not_in` | load |
| `check_log_absent` | 427-430 (4) | `log_path.exists` | load |

Trois fonctions mixtes, et elles tiennent le cœur du module :

- `import_items` est l'orchestrateur — dans la cible, c'est `pipeline.py`, pas `load/` ;
- `write_items_file` applique le filtre des releases non suivies et `normalize_item` au milieu
  de l'écriture : deux étapes de transform coincées dans le load ;
- `commit_with_log` mêle deux cibles d'écriture (un fichier `.jsonl` et la base) dans une seule
  fonction, parce que l'ordre entre les deux porte une règle (le journal avant le commit).

Trois fonctions sont pures et pourraient partir dans `transform/` : `join_writings`,
`list_files_in_collection_order`, `reject_untracked_releases` (63 lignes).

## 4. Ce qui n'est pas dans ce relevé

- Les imports entre modules (qui importe qui) : non relevés ici. `tests/architecture/test_layers.py`
  et `tests/architecture/module_imports.py` les lisent déjà et seront le filet de la
  refactorisation.
- Les fonctions des 14 autres modules de `etl/` et des 12 autres sources : non détaillées.
- Le rattachement des modules de `commands/`, `data_api/`, `ai_api/` et `database/` : hors
  périmètre de la cible annoncée.
