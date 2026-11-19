# La documentation de K-B

K-B est <q>une bibliothèque de veille tech qui se range toute seule</q>: un pipeline collecte chaque jour l'actualité
tech de plusieurs sources et la range en items datés dans une base, que deux API servent. Le produit est décrit dans
le [README du dépôt](https://github.com/SabineLaurent/K-B/blob/main/README.md). Ce site rassemble ses
fiches de documentation, une par sujet. Chacune dit, sous son titre, la compétence de la certification qu'elle sert.

## Les fiches

- [L'accessibilité de cette documentation](accessibilite_pour_docu.md): les recommandations suivies, leurs règles et
    ce qui n'est pas vérifié.
- [L'installation et l'environnement de développement](installation_pour_docu.md)
- [L'architecture de l'application](architecture_pour_docu.md)
- [Les maquettes du site et le parcours de l'opératrice](maquettes_et_parcours_pour_docu.md)
- [L'agrégation, l'import et la base](import_et_base_pour_docu.md)
- [L'API IA](api_ia_pour_docu.md)
- [Le service d'IA: le déploiement du modèle](service_ia_pour_docu.md)
- [Le monitorage du modèle et de l'application](monitoring_pour_docu.md)
- [Les tests](tests_pour_docu.md)
- [L'intégration continue](integration_continue_pour_docu.md)
- [La livraison continue](livraison_continue_pour_docu.md)

## Lire une fiche

Chaque page a sa « Table des matières », et le champ « Rechercher » cherche dans toutes les fiches. Un
renvoi `fichier:ligne` vise le code du dépôt, au commit ou à la date que la fiche nomme dans son introduction. Un lien vers un
fichier hors de ces fiches mène à sa page sur GitHub, sur la branche `main`.
