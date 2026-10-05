# Fusionner les items en un seul jeu

- **Date** : 2026-10-05
- **Branche** : `feat/merge-items`
- **Issue** : #80, sous-issue de l'épic #20 « Fusion et base »
- **Fichiers principaux** : `src/k_b/merge.py`, `docs/specs-collecte.md` (étape 3)
- **Dans la même série** : [lire le brut en items communs](2026-10-05-lire-le-brut-en-items-communs.md) (#79), qui produit les items fusionnés ici.

## 1. Le pourquoi

Le brut contient le même élément plusieurs fois, pour trois raisons :

- les fenêtres de collecte se recouvrent (arXiv relit 7 jours, TLDR relit le jour de la dernière
  collecte) ;
- certaines sources sont des instantanés complets : le catalogue CISA entier, ou le classement
  des dépôts les plus étoilés, à chaque collecte ;
- deux sources donnent parfois la même URL, ou une même source donne une même CVE sous deux
  identifiants (deux alertes GitHub).

La base refuse ces doublons, avec des contraintes `UNIQUE` sur l'URL et sur le couple source et
identifiant. Il faut donc les retirer avant l'import, et dire lesquels ont été retirés, et
pourquoi. La CVE n'est pas un doublon d'une source à l'autre : une entrée CISA et une alerte
GitHub de même CVE restent deux items, reliés par leur CVE. Le schéma perd son unicité sur
`cve` avec #81.

Cette PR fait l'étape 3 de `docs/specs-collecte.md`, la fusion. Elle reçoit les items lus par
#79 et rend un seul jeu, plus la liste des items écartés, chacun avec le nom de sa règle. Elle
n'écrit rien : le journal des écartés et l'insertion en base relèvent de #82.

## 2. Le comment

### 2.1 Garder le premier vu, grâce à trois index

```python
    for item in map(normalize_item, items):
        position = position_by_source_id.get((item.source_code, item.source_item_id))
        ...
        if item.url in position_by_url:
            discards.append(Discard("same_url", item, kept[position_by_url[item.url]].url))
            continue
```
`src/k_b/merge.py:42-55`

`merge_items` parcourt les items une seule fois. Elle tient trois dictionnaires : identifiant,
URL, et CVE **par source** (le couple source et CVE), chacun associé à la position de l'item gardé dans la liste `kept`. Pour chaque
nouvel item, elle regarde ces index **dans l'ordre du tableau de la spec** : identifiant, puis
URL, puis CVE. Le premier qui correspond décide de la règle. Quand c'est l'identifiant, une
révision arXiv plus récente donne `arxiv_revision` (2.2), et tout autre cas `same_source_id`.

La règle générale est de garder le premier vu. Les items arrivent dans l'ordre des collectes
(`read_raw_items` les trie par `collected_at`). Le premier vu est donc celui de la collecte qui
a apporté l'élément, et c'est à elle que la base le rattachera (table `collection`).

Chaque recherche dans un dictionnaire prend un temps constant. La fusion est donc linéaire en
nombre d'items, alors qu'une comparaison de chaque paire d'items serait quadratique.

### 2.2 La révision arXiv remplace l'item à sa place

```python
            if is_newer_revision(item, previous):
                kept[position] = item
                position_by_url[item.url] = position
                discards.append(Discard("arxiv_revision", previous, item.url))
```
`src/k_b/merge.py:46-49`

C'est la seule exception au « premier vu ». Quand un papier arXiv revient avec une date de
révision (`revised_at`) plus récente, la nouvelle version remplace l'ancienne **à la même
position**, ce qui garde l'ordre du jeu. Ici, c'est l'ancienne version qui est tracée comme
écartée. La spec le demandait : « une révision (arXiv `v2`) met à jour l'item existant au lieu
d'être ignorée ».

L'identifiant arXiv est déjà sans version (#79). Une `v2` a donc le même `source_item_id` que
la `v1`, et passe par l'index des identifiants.

### 2.3 Normaliser avant de comparer, et valider de nouveau

```python
def normalize_item(item: Item) -> Item:
    fields = item.model_dump()
    fields["url"] = remove_tracking_parameters(item.url)
    ...
    # Validated again: the normalized item must pass the same checks as the item read.
    return Item(**fields)
```
`src/k_b/merge.py:68-76`

Chaque item est normalisé avant les comparaisons : les paramètres `utm_*` sont retirés de
l'URL, et les dates sont ramenées en UTC. Deux URL qui ne diffèrent que par leurs paramètres de
suivi deviennent donc égales.

On reconstruit l'item avec `Item(**fields)`, plutôt qu'avec `model_copy(update=...)`, qui ne
valide pas. Le résultat repasse ainsi les mêmes contrôles que l'item lu : `https://`, dates
avec fuseau, mode strict. C'est la défense en profondeur de `code.md`, puisque l'URL vient
d'une source non fiable et que la fonction la modifie.

### 2.4 Retirer `utm_*` sans réécrire le reste

```python
    query = "&".join(
        parameter
        for parameter in parts.query.split("&")
        if parameter and not parameter.startswith(TRACKING_PARAMETER_PREFIX)
    )
```
`src/k_b/merge.py:82-86`

La requête est découpée sur `&`, comme du texte. Pour savoir ce qu'on retire, il suffit de
regarder si un paramètre commence par `utm_`. Les autres paramètres restent **tels qu'écrits**,
dans leur ordre. Si on était passé par `parse_qsl` puis `urlencode`, l'URL aurait été
réencodée : des espaces écrits `%20` deviendraient `+`, par exemple. L'URL stockée ne serait
alors plus celle que la source a donnée.

## 3. Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Quel doublon garder | **Le premier vu** : sa collecte l'a apporté, et la base le rattache à elle. | Le dernier vu : il aurait changé de collecte à chaque nouvelle collecte, par exemple pour CISA, téléchargé en entier chaque jour. |
| Même CVE chez CISA et GitHub | **Deux items, reliés par leur CVE** (décision de Sabine, 2026-10-05) : on rattache, on ne dédoublonne pas. `stockage.md` prévoit la CVE pour le « croisement avec CISA ». `same_cve` ne vaut qu'au sein d'une même source. | Un seul item, le premier vu (option a, d'abord retenue le même jour) : l'information « activement exploitée » de CISA pouvait disparaître de la base si l'alerte GitHub arrivait avant. Garder les deux avec la CVE sur le premier seulement (option b) : le lien entre eux serait perdu. |
| Retrait de `utm_*` | **Découpage du texte de la requête**, le reste n'est pas touché. | `parse_qsl` et `urlencode` : ils réencodent l'URL. |
| Copie de l'item normalisé | **`Item(**model_dump())`** : il est validé de nouveau. | `model_copy(update=...)` : il ne valide pas les champs modifiés. |
| Résultat | **Une fonction pure** qui rend les items gardés et les écartés (`MergeResult`). | Écrire le journal ici : cela mêlerait le métier et les entrées/sorties (`code.md`, séparation des responsabilités). |

## 4. Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_distinct_items_are_all_kept_in_order` | Des items différents sont tous gardés, dans leur ordre, sans aucun écarté. |
| `test_utm_parameters_are_removed_and_the_others_kept_in_order` | `utm_source` et `utm_medium` sont retirés, `id=7&page=2` et le fragment `#part` restent, dans leur ordre. |
| `test_a_query_made_only_of_utm_parameters_disappears` | Une requête faite seulement de `utm_*` disparaît, le `?` aussi. |
| `test_dates_are_brought_to_utc` | Une date à +02:00 est ramenée au même instant en UTC. |
| `test_the_same_source_item_seen_again_is_discarded_and_the_first_collection_kept` | Règle `same_source_id` : la seconde collecte est écartée, avec l'URL de l'item gardé. |
| `test_the_same_url_from_another_source_is_discarded` | Règle `same_url`, y compris quand l'URL n'est égale qu'une fois les `utm_*` retirés. |
| `test_the_same_cve_from_another_source_is_kept_as_a_second_item` | Une entrée CISA et une alerte GitHub de même CVE restent deux items, sans aucun écarté. |
| `test_the_same_cve_within_one_source_is_discarded_and_the_first_seen_kept` | Règle `same_cve` : deux alertes GitHub de même CVE, la seconde est écartée avec l'URL de la première. |
| `test_items_without_cve_are_not_duplicates_of_each_other` | Une CVE absente ne fait pas de doublon. |
| `test_a_newer_arxiv_revision_replaces_the_kept_paper_in_place` | Règle `arxiv_revision` : la v2 prend la place de la v1, et la v1 est tracée comme écartée. |
| `test_an_arxiv_paper_seen_again_without_revision_keeps_the_first_collection` | Le même papier sans révision plus récente suit `same_source_id`. |
| `uv run pytest` | 221 tests passent. |

## 5. Ce que tu dois pouvoir défendre

1. **Pourquoi garder le premier et pas le dernier ?** La base rattache chaque item à la
   collecte qui l'a apporté. Garder le dernier ferait changer de collecte, chaque jour, les
   éléments que CISA ou le classement GitHub renvoient à chaque fois (`merge.py:33-34`).
2. **Une alerte GitHub et une entrée CISA de même CVE, est-ce un doublon ?** Non : ce sont deux
   informations différentes, un paquet vulnérable et une faille activement exploitée. Les deux
   items restent, et la CVE les relie, pour le croisement prévu par `stockage.md`. `same_cve`
   ne s'applique qu'au sein d'une même source (`merge.py:39-40`, `57-60`).
3. **Pourquoi l'ordre des règles compte-t-il ?** Un item peut correspondre à plusieurs règles.
   Il est tracé avec la première qui correspond, dans l'ordre identifiant, URL, CVE, comme dans
   le tableau de la spec. Un même papier arXiv revu **sans** révision plus récente est donc
   tracé `same_source_id`, même si son URL est aussi déjà connue. Avec une révision plus
   récente, c'est `arxiv_revision`, un sous-cas de la correspondance par identifiant
   (`merge.py:43-51`).
4. **Où est la sécurité ?** La fusion modifie l'URL, une donnée non fiable. L'item modifié
   repasse la validation complète d'`Item` (`merge.py:75-76`). La fonction ne fait aucune
   entrée ni sortie.
5. **Pourquoi ne pas réencoder la requête ?** Pour stocker l'URL telle que la source l'a
   donnée, moins les paramètres de suivi (`merge.py:79-87`).

## 6. Zones non vérifiées

- **L'ordre des items est supposé.** `merge_items` compte sur l'ordre des collectes, que
  `read_raw_items` donne. Elle ne le vérifie pas elle-même : appelée sur une liste dans un autre
  ordre, elle garderait un autre « premier ».
- **Variantes de `utm_` non traitées** : `UTM_source` en majuscules, ou `utm%5Fsource` encodé, ne
  sont pas retirés. Je n'ai pas vérifié si TLDR en produit. Ce sera à regarder sur les pages
  réelles, avec #57.
- **Aller-retour `urlsplit` / `urlunsplit`.** Je ne l'ai testé que sur les URL des tests. Une URL
  qui finit par un `?` vide le perd, par exemple. Je n'ai pas vérifié tous les cas limites.
- **Une révision arXiv ne passe pas par les règles d'URL et de CVE par source.** C'est sans effet
  aujourd'hui, puisque l'URL d'un papier est construite à partir de son identifiant sans
  version, mais ce n'est pas testé.
- Aucun brut réel n'a été fusionné : uniquement des items construits dans les tests.

## 7. Ce qui reste

- L'écriture du journal des écartés et l'insertion en base : #82.
- La création de la base : #81, et le test du schéma : #67.
- La lecture de TLDR (#57), qui apportera les premières URL avec `utm_*` réelles.
