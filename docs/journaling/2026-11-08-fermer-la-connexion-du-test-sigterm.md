# Fermer la connexion laissée ouverte par le test SIGTERM de `kb migrate-database`

- Date : 2026-11-08
- Branche : `test/close-sigterm-connection`
- Issue : #470
- Fichier : `tests/commands/test_sigterm.py`

## Le pourquoi

En mesurant la couverture pour #465, `uv run pytest --cov` affichait un avertissement : `ResourceWarning:
unclosed database`. Une connexion SQLite n'était jamais fermée. L'avertissement était rapporté sous un
test de `kb smoke-test`, d'où le titre de #470. La piste A a tracé la vraie source avec `tracemalloc` :
un test SIGTERM de `kb migrate-database`. Python ne signale une connexion oubliée qu'au moment où le
ramasse-miettes la libère, c'est-à-dire souvent pendant un autre test.

## Le comment

### La fonction de remplacement ne rendait jamais la connexion

```python
    def connect_then_stop(database_path):
        connection = connect_sqlite(database_path)
        try:
            signal.raise_signal(signal.SIGTERM)
        except StoppedBySigtermError:
            # The stop comes before the connection is handed back: no caller can close it.
            connection.close()
            raise
        return connection
```
(`tests/commands/test_sigterm.py`, `test_a_sigterm_during_kb_migrate_database_leaves_no_base_and_exits_with_its_code`)

Le test remplace l'ouverture de la base par une fonction qui ouvre la connexion, puis envoie SIGTERM au
processus. Le gestionnaire de `kb` transforme ce signal en `StoppedBySigtermError`, une `SystemExit`
(`commands/sigterm.py`). L'exception part avant le `return` : aucun appelant ne reçoit la connexion,
donc aucun ne peut la fermer. Désormais, le test la ferme lui-même au passage de l'exception, puis
relance l'exception. Le reste du test ne change pas : `kb` sort avec son code d'arrêt, et la base est
retirée.

## Choix faits et options écartées

| Choix | Pourquoi | Écarté |
|---|---|---|
| Corriger le test, pas `src/` | la fuite vient de la fonction de remplacement ; en vrai, un SIGTERM à cet instant termine le processus | toucher `database/creation.py` : rien n'y fuit |
| `except StoppedBySigtermError` puis `raise` | ne ferme la connexion que si le signal arrête bien `kb` | `finally` (annoncé dans le plan) : si le signal n'arrêtait rien, il rendrait une connexion déjà fermée |
| La connexion reste ouverte au moment du signal | c'est le cas réel que le test imite | la fermer avant le signal : le test ne verrait plus le même état |

## Preuve

| Commande | Ce que ça démontre |
|---|---|
| Avant : le test seul, sous `-W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning`, code 1 (`unclosed database`) | la fuite est là, et ce test la porte |
| Après : la même commande, code 0 ; tout `tests/commands` sous les mêmes options, 246 tests passés | la fuite a disparu, et c'était la seule de ce dossier |
| `uv run pytest --cov` : 4 061 tests, couverture 98,42 %, sans le « 1 warning » d'avant | plus aucun avertissement dans la suite |

## Ce que tu dois pouvoir défendre

1. **Pourquoi l'avertissement nommait-il un autre test ?** Python ne le signale qu'au moment où il
   libère la connexion, souvent pendant le test suivant ; `tracemalloc` donne l'endroit où elle a été
   ouverte.
2. **Pourquoi pas de correction dans `src/` ?** Le code réel reçoit la connexion et la ferme. Seule la
   fonction du test levait l'exception avant de la rendre.

## Zones non vérifiées

Aucune.

## Ce qui reste

- Faire échouer la suite sur un `ResourceWarning` (`filterwarnings` dans `pyproject.toml`) empêcherait
  une rechute. Ce n'est pas fait : il faudrait ton accord sur `pyproject.toml`, et un avertissement
  qui tombe au hasard du ramasse-miettes ferait échouer un test sans rapport.
