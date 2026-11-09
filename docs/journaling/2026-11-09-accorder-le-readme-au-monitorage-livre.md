# Accorder le README au monitorage livré

- Date : 2026-11-09
- Branche : `docs/readme-monitoring`
- Issue : #526
- Fichier principal : `README.md` (trois passages)

La note couvre le seul commit de la branche, 2ef5637. Les autres commits et fichiers que liste l'outil
(`documentation/`, `src/k_b/ai_api/`, `tests/`…) sont ceux de #502, #507 et #518, déjà sur `main` : ils ne sont pas
de cette PR (`git diff --stat origin/main..HEAD` ne donne que `README.md`).

## Le pourquoi

Le README annonçait encore que la restitution des métriques du modèle et l'alerte sur seuil « viendra avec #164 ».
Or le tableau de bord et les trois alertes sont dans le dépôt (`observability/grafana/`), et leur fiche,
`documentation/monitoring_pour_docu.md`, relève qu'elles ont été déclenchées dans le bac à sable le 08/11. Un lecteur
qui ouvre le README d'abord croyait le monitorage à venir. Au passage, la ligne `KB_DATABASE_URL` du tableau des
variables oubliait deux des commandes qui la lisent.

## Le comment

### Ce que le monitorage fait, dans le périmètre

`README.md:80-86` dit maintenant ce qui existe : un tableau de bord, trois alertes sur seuil envoyées par e-mail,
les deux fichiers versionnés, et un renvoi à la fiche du monitorage pour l'installation, la lecture et le relevé.

```markdown
  JSON de la sortie standard et en OpenTelemetry vers Grafana Cloud, en région UE. Un tableau de
  bord les montre à jour et dans le temps, et trois alertes sur seuil partent par e-mail : sorties
  invalides, fidélité basse, coût au-dessus du budget. Le tableau et les alertes sont versionnés
```

Les trois alertes sont nommées par ce qu'elles surveillent, comme dans le tableau de la fiche
(`documentation/monitoring_pour_docu.md`, « Ce que le monitorage suit » : `KbModelInvalidOutputs`,
`KbModelLowFidelity`, `KbModelCostOverBudget`). Le README ne redéfinit pas la fidélité : la fiche du monitorage la
porte, et un seul texte la tient.

### Où on en est : livré, puis ce qui reste

`README.md:192-196` sépare ce qui est fait de ce qui reste dans #164 :

```markdown
tableau de bord et leurs trois alertes sur seuil sont livrés (#164), et les trois alertes ont été
déclenchées dans un bac à sable le 08/11. Restent, dans #164, le réimport du tableau et de la règle
de fidélité, changés depuis, et l'essai d'accessibilité ; puis, au deuxième temps, l'image étant
```

Les deux restes viennent de la fiche du monitorage : « À réimporter » (le tableau et la règle de fidélité ont changé
après le relevé) et le critère de #164 sur l'essai d'accessibilité. La fin de la phrase (#200, #202) n'est pas
touchée.

### Qui lit `KB_DATABASE_URL`

Une seule fonction lit la variable, `read_database_location_or_refusal` (`src/k_b/database/location.py:109-115`).
Quatre commandes l'appellent : `kb create-db`, `kb import`, `kb serve-data` et `kb migrate-database`
(`src/k_b/commands/migrate_database_command.py:26`). `kb daily-routine` ne l'appelle pas lui-même : il lance
`kb import` dans le même processus, par une étape de sa routine.

```python
    RoutineStep(
        "kb import",
        lambda settings: run_import(settings.data_dir, settings.environ),
```

(`src/k_b/commands/daily_routine_command.py:54-56`.) D'où la formule de `README.md:223` : « `kb import` (et
`kb daily-routine`, qui le lance) ».

## Choix faits et options écartées

- **Nommer `kb daily-routine` entre parenthèses**, après `kb import` (écart au plan de la mission, validé par Sabine
  le 09/11). Écarté : ne nommer que `kb migrate-database`, comme le demandait la mission. Un lecteur qui règle le job
  de la routine aurait cru qu'il n'en a pas besoin.
- **Renvoyer à la fiche du monitorage plutôt que décrire le tableau dans le README** : la fiche tient l'installation,
  les seuils et le relevé ; les recopier ferait deux textes à tenir d'accord.
- **Ne pas écrire que ce qui reste de #164 est « en pause »** : c'est une organisation de travail, pas un fait du
  produit.

## Preuve

| Commande ou sortie | Ce que ça démontre |
|---|---|
| `grep -c "viendr.* avec #164" README.md` → `0` | la phrase du futur a disparu |
| `grep -rn "read_database_location" src/k_b` → `create_db_command.py:29`, `import_command.py:57`, `migrate_database_command.py:26`, `serve_data_command.py:35` | les quatre lecteurs directs de la variable |
| `ls observability/grafana/` → `alert-rules.yaml`, `dashboard.json` | les deux fichiers nommés existent |
| contrôle `Cc`/`Cf` sur `README.md` → aucun caractère | pas de contrôle invisible |

## Ce que tu dois pouvoir défendre

- **« Le monitorage est-il fini ? »** Le tableau et les trois alertes sont livrés et ont été déclenchées dans le bac à
  sable le 08/11 ; restent le réimport de la version modifiée et l'essai d'accessibilité (`README.md:192-196`).
- **« Pourquoi `kb daily-routine` lit-elle la base sans appeler la fonction ? »** Elle enchaîne les commandes dans
  son processus (`commands/job_routine.py`), dont `kb import` (`daily_routine_command.py:54-56`).
- **« Où se lit le détail des alertes ? »** Dans `documentation/monitoring_pour_docu.md`, à laquelle le README
  renvoie (`README.md:86`).

## Zones non vérifiées

- Que la pile Grafana en ligne porte aujourd'hui la dernière version du tableau : la fiche dit le contraire
  (« À réimporter ») ; le README le dit comme un reste de #164.
- La première phrase de la puce de `README.md:80` (les mesures, la ligne JSON de la sortie standard, l'export en
  OpenTelemetry) n'est pas revérifiée ici : elle n'a pas changé.

## Ce qui reste

- #164 : le réimport des deux fichiers et l'essai d'accessibilité.
