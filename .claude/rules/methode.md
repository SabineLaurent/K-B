<!-- consignes/methode.md v2026-09-30 — source : time-knight. Ne pas modifier ici sans la reporter. -->
# Méthode de travail

Le cycle de toute PR de code. Ce qui est propre au dépôt (board, taille des PR, briques en cycle
complet) reste dans son `CLAUDE.md` et prime.

## Démarrer

- Quand Sabine tape « go » : lire `MISSION.md` et l'exécuter. Il prime sur la procédure de reprise.
- Sans mission : `git status` et la branche, puis le dernier commentaire de l'issue en cours.

## Le cycle d'une PR de code

1. **Conception** : 10 lignes au plus dans l'issue — ce qu'on fait, ce qu'on ne fait pas, les
   options et le choix. Sabine valide avant le code.
2. **Branche** `<type>/<sujet>` depuis `main` à jour (types des commits : `feat`, `fix`, `docs`…).
3. **Tests d'abord** : le test qui échoue, puis le code qui le fait passer.
4. **Contrôles du dépôt verts** (tests, et lint, format, typage s'ils existent).
5. **Revue** dans un sous-agent sans contexte : `/code-review`, plus `/security-review` si la PR
   touche une entrée externe. Constats **rapportés, pas corrigés** ; corrections sur accord de
   Sabine.
6. **Note pédagogique** : `/note-pedago-ls` via l'outil Skill ; la note entre dans la PR.
7. **Décision structurante** (qui engage la suite du projet) : `/adr-ls` via l'outil Skill.
8. **PR** vers `main` : un seul sujet, `Closes #n` par issue, compte rendu de revue en commentaire.
9. **Sabine fusionne.** Claude ne fusionne jamais.

Une PR de documentation ou de configuration seule saute les étapes 3, 5 et 6.

## Actions que l'outil peut refuser

Push, suppression de branche distante, modification de `CLAUDE.md` ou de `.claude/` : en cas de
refus, s'arrêter et le dire, ne pas contourner. Sabine lance la commande avec `!`.

## Finir une session

Committer le travail en cours sur sa branche ; laisser sur l'issue un commentaire « point
d'arrêt » (branche, fait, état des tests, prochaine étape, question en attente) ; mettre à jour la
ligne `Statut :` de `MISSION.md`.
