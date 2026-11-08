# Accessibilité de Grafana Cloud: l'essai de Sabine

« Les enjeux d'accessibilité, pour toutes les parties prenantes du projet, sont pris en compte lors de la sélection de l'outil de restitution. » — C11

Les résultats de l'essai d'accessibilité de Grafana Cloud, l'outil de restitution choisi (`docs/outils-de-suivi.md`).
La grille, ses critères WCAG 2.1 AA (RGAA 4.1.2), ce qui est bloquant et les outils de l'essai sont dans
`docs/outils-de-suivi.md`, section « Accessibilité ». Les lecteurs du tableau et de l'alerte, et leurs outils
d'assistance, sont dans `documentation/monitoring_pour_docu.md`, section « Qui lit le tableau et l'alerte ».

**Ce qui est essayé**: Explore; le tableau de bord « K-B, modèle: qualité, coût, alertes » (`observability/grafana/dashboard.json`),
environnement `sandbox`; la liste des règles d'alerte du dossier K-B, avec les trois alertes déclenchées par le bac à
sable le 2026-11-08; l'e-mail d'une alerte.

**Essai**: à venir, par Sabine. Navigateur: à relever le jour de l'essai.

| n° | Étape (grille de `docs/outils-de-suivi.md`) | Résultat | Bloquant |
|---|---|---|---|
| 1 | contrôles automatiques (FastPass) | à venir | à venir |
| 2 | clavier seul: ouvrir le tableau de bord, changer la période | à venir | à venir |
| 3 | clavier seul: lire le panneau en tableau (Inspect > Data) | à venir | à venir |
| 4 | clavier seul: ouvrir une règle d'alerte depuis la liste | à venir | à venir |
| 5 | clavier: sortir de chaque menu ou fenêtre ouvert | à venir | à venir |
| 6 | focus visible tout au long du parcours | à venir | à venir |
| 7 | lecteur d'écran: nom et rôle des commandes | à venir | à venir |
| 8 | lecteur d'écran: valeur d'un panneau, résultat d'une requête | à venir | à venir |
| 9 | lecteur d'écran: règles d'alerte et leur état | à venir | à venir |
| 10 | couleur seule (émulation du daltonisme) | à venir | à venir |
| 11 | contrastes du texte, des axes, de la légende | à venir | à venir |
| 12 | zoom à 200 % | à venir | à venir |
| 13 | zoom à 400 % | à venir | à venir |

## Ce que le tableau fait déjà pour l'accessibilité

Tenu par `tests/test_grafana_files.py`: aucune valeur, aucune cellule ni aucun seuil n'est porté par la couleur; un
état est écrit en toutes lettres; un seuil est une ligne de tirets nommée dans la légende. Un mode d'emploi en tête du
tableau dit comment lire chaque panneau en tableau (**Inspect**, **Data**). L'e-mail d'une alerte écrit son état
(« Firing »).

Constaté le 2026-11-08, à vérifier par l'essai: les chiffres des panneaux d'état sont plus petits que ceux d'un
panneau à une seule valeur, Grafana réduisant la taille pour faire tenir le texte de l'état.
