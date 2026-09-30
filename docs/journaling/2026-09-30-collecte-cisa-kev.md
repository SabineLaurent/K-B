# Collecter le catalogue CISA KEV : télécharger tout, trier à la lecture

- **Date** : 2026-09-30
- **Branche** : `feat/cisa-kev`
- **Issue** : #23 (dépend de #9)
- **Fichiers principaux** : `src/k_b/cisa_kev_source.py`, `src/k_b/cisa_kev.py`,
  `src/k_b/collect.py`, `src/k_b/raw_store.py`
- **Note précédente** : [La commande `kb collect`](2026-09-30-commande-kb-collect.md), qui avait
  renvoyé à #23 le timeout, le User-Agent, l'ETag/304 et la date de publication.

## Le pourquoi

La CISA (agence américaine de cybersécurité) publie la liste des vulnérabilités **activement
exploitées** : le catalogue KEV, un CSV public, sans clé. K-B veut savoir lesquelles touchent
l'outillage suivi, en les croisant plus tard avec les alertes GitHub (#11). C'est aussi la source
de type « fichier de données » exigée par la certification.

Cette PR branche la **première vraie source** sur le squelette `kb collect` de #9. Elle fait
deux choses distinctes :

1. **collecter** : télécharger le catalogue et le déposer, intact, dans
   `raw/automation/cisa_kev/` ;
2. **lire** : sortir de ce brut un item par vulnérabilité ajoutée depuis la dernière collecte.

Elle corrige aussi deux limites relevées par la note de #9 : un fichier d'état illisible, et le
message « no source registered ».

## Le comment

### 1. Une source = un objet qui renvoie des octets, ou rien

Le contrat `Source` (défini dans #9) gagne un cas : `None` veut dire « rien n'a changé ».

```python
# src/k_b/collect.py:59-61
    raw_content = source.fetch(last_collected_at)
    if raw_content is None:
        return
```

Quand une source renvoie `None`, aucun fichier brut n'est écrit. La source compte pourtant comme
**réussie** : sa date de dernière collecte avance. Ce n'est pas une panne, c'est une réponse
« rien de neuf ». Sans ce cas, il faudrait soit réécrire un fichier identique (1 Mo pour rien),
soit traiter le 304 comme une erreur (et la commande sortirait en échec tous les jours calmes).

### 2. Un téléchargement HTTP borné de tous les côtés

```python
# src/k_b/cisa_kev_source.py:24-32
        headers = {"User-Agent": USER_AGENT}
        if last_collected_at is not None:
            headers["If-Modified-Since"] = format_datetime(last_collected_at, usegmt=True)
        request = Request(CATALOG_URL, headers=headers)
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                if not response.url.startswith(TRUSTED_URL_PREFIX):
                    raise ValueError(f"catalog redirected outside {TRUSTED_URL_PREFIX}, refused")
                catalog = response.read(MAX_CATALOG_BYTES + 1)
```

Chaque ligne pose une limite (défense en profondeur, `.claude/rules/code.md`) :

- **User-Agent** `K-B (+url du dépôt)` : le serveur sait qui l'appelle et comment le joindre.
- **`timeout=30`** : sans délai, un serveur muet bloquerait `kb collect` indéfiniment.
- **`If-Modified-Since`** : « envoie le fichier seulement s'il a changé depuis cette date ».
  `format_datetime(..., usegmt=True)` produit le format HTTP exigé
  (`Wed, 30 Sep 2026 10:00:00 GMT`). S'il n'a pas changé, le serveur répond **304**.
- **URL finale** : `urlopen` suit les redirections, y compris vers du HTTP en clair. On vérifie
  que la réponse vient bien de `https://www.cisa.gov/` (le `/` final empêche
  `www.cisa.gov.example.com` de passer).
- **Taille** : on lit au plus `MAX_CATALOG_BYTES + 1` octets. Si on obtient ce `+1`, c'est que le
  fichier dépasse la limite : il est refusé (`cisa_kev_source.py:38-39`). On ne charge jamais en
  mémoire un fichier arbitrairement gros.

Le 304 arrive par une exception : urllib traite toute réponse hors 2xx comme une `HTTPError`.

```python
# src/k_b/cisa_kev_source.py:33-37
        except HTTPError as error:
            if error.code == HTTP_NOT_MODIFIED:
                error.close()
                return None
            raise
```

Seul le 304 est transformé en `None`. Toute autre erreur (503, 404…) remonte, et la boucle de
collecte l'isole comme une panne de cette source. `error.close()` libère la connexion que porte
l'exception.

### 3. La lecture : un module pur, qui valide à la frontière

`cisa_kev.py` ne fait **aucun** appel réseau ni fichier : il reçoit des octets, rend des objets.
C'est la séparation métier / entrées-sorties de `code.md`, et c'est ce qui permet de le tester sur
un extrait enregistré.

```python
# src/k_b/cisa_kev.py:39-44
    rows = csv.DictReader(io.StringIO(raw_catalog.decode("utf-8-sig"), newline=""))
    columns = rows.fieldnames or []
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing_columns:
        raise ValueError(f"catalog without the columns {', '.join(missing_columns)}")
    vulnerabilities = [parse_vulnerability(row, rows.line_num) for row in rows]
```

- `utf-8-sig` : comme `utf-8`, mais retire un éventuel BOM (marque d'ordre des octets) en tête.
  Sans ça, la première colonne s'appellerait `﻿cveID` et le catalogue serait refusé. Le vrai
  CSV n'en a pas aujourd'hui (vérifié : il commence par les octets `cve`).
- `newline=""` : ce que la documentation de `csv` demande, pour qu'un champ entre guillemets
  garde ses retours à la ligne.
- Colonnes manquantes → refus du fichier entier. **Échouer fermé** : si la CISA change son
  format, on le voit tout de suite au lieu de produire des items faux.

Chaque ligne passe ensuite par `parse_vulnerability` (`cisa_kev.py:51-68`), qui refuse une ligne
trop courte (`DictReader` remplit alors les champs manquants par `None`), un identifiant qui
n'a pas la forme `CVE-AAAA-NNNN…`, ou une `dateAdded` qui n'est pas une date ISO. Le message
donne le numéro de ligne. Le résultat est un `Vulnerability` figé (`frozen=True`), un type fermé
plutôt qu'un `dict` où n'importe quelle clé passerait.

### 4. Le filtre par date, avec un jour de marge

```python
# src/k_b/cisa_kev.py:45-48
    if last_collected_at is None:
        return vulnerabilities
    since = last_collected_at.date() - timedelta(days=1)
    return [vulnerability for vulnerability in vulnerabilities if vulnerability.date_added >= since]
```

Première collecte (`None`) : tout le catalogue. Ensuite : les lignes dont `dateAdded` est au plus
un jour avant le jour (UTC) de la dernière collecte. La raison du jour de marge est en section
suivante.

### 5. Le fichier d'état : échouer proprement, même quand on ne peut pas le lire

```python
# src/k_b/raw_store.py:39-46
    try:
        state_content = state_path.read_bytes()
    except OSError as error:
        raise InvalidCollectionStateError(
            f"{state_path} cannot be read: {error.strerror}"
        ) from error
    try:
        stored_dates = json.loads(state_content.decode("utf-8"))
```

Deux familles d'erreur, deux blocs :

- **lecture impossible** (droits, disque) : `OSError`, message du système (« Permission
  denied ») ;
- **contenu invalide** (pas de l'UTF-8, JSON cassé, date sans fuseau) : `ValueError`, déjà traité
  dans #9. `UnicodeDecodeError` est une sous-classe de `ValueError`, d'où le décodage placé
  **dans** le second bloc.

Les deux deviennent `InvalidCollectionStateError`, que `cli.py` attrape : code de sortie 2 et une
ligne claire, jamais une trace Python.

Enfin, le message « no source registered » est supprimé de `cli.py` : maintenant qu'une source
est enregistrée, c'était du code mort, et c'est lui qui s'imprimait avant le message d'erreur.

## Choix faits et options écartées

| Retenu | Écarté | Pourquoi |
|---|---|---|
| **Brut complet, intact ; filtre à la lecture.** Voir [le journal des décisions](../ADR/journal-decisions-projet.md). | Filtrer à l'écriture (ne stocker que les nouvelles lignes). | Décision de Sabine : pouvoir rejouer le traitement sur le brut. Coût : ~1 Mo par collecte où le catalogue a changé. |
| **`If-Modified-Since`** avec la date de dernière collecte. | **ETag / `If-None-Match`**. | Testé contre le vrai serveur : `If-None-Match` avec l'ETag qu'il venait de renvoyer → **200** (ignoré) ; `If-Modified-Since` → **304**. En plus, `If-Modified-Since` réutilise la date déjà stockée : rien à ajouter au fichier d'état. |
| **`dateAdded` comparé tel quel, avec un jour de marge.** | Convertir à l'heure de Washington. | `dateAdded` est un **jour sans fuseau**, pas un instant. Supposer qu'il est en heure de l'Est serait une hypothèse non vérifiée. Avec la marge, une collecte à 02:00 UTC le 30 garde les lignes datées du 29, quel que soit le fuseau réel. |
| Doublons laissés passer (marge d'un jour). | Dédoublonner ici, ou comparer les `cveID` avec le brut précédent. | Retirer les doublons est le rôle de l'étape de fusion (README). Le diff par `cveID` sortirait du critère de l'issue (`dateAdded`). |
| `urllib` (bibliothèque standard). | `httpx`, `requests`. | Aucune dépendance à ajouter pour un seul GET ; `pyproject.toml` ne se modifie pas sans demande explicite (consigne). |
| Deux modules : `cisa_kev_source.py` (réseau) et `cisa_kev.py` (lecture). | Un seul module. | Séparation métier / entrées-sorties imposée par `code.md` ; la lecture se teste sans réseau. |
| Limite de 10 Mo. | Pas de limite ; limite serrée (2 Mo). | ~10× la taille actuelle (1 037 519 octets le 30/09) : assez de marge pour la croissance, assez bas pour refuser un fichier aberrant. |
| Le 304 compte comme une réussite. | Le compter comme une erreur. | « Rien de neuf » est le cas normal ; sinon `kb collect` échouerait les jours calmes. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| `test_the_first_collection_reads_the_whole_catalog` | Sans collecte précédente, les 4 lignes de l'extrait sortent. |
| `test_only_vulnerabilities_added_since_the_day_before_the_last_collection_are_read` | Le filtre `dateAdded` écarte la ligne de 2020. |
| `test_a_vulnerability_dated_the_day_before_a_collection_run_after_midnight_utc_is_kept` | La marge d'un jour garde une ligne datée de la veille. |
| `test_a_catalog_without_the_expected_columns_is_refused`, `test_a_malformed_row_is_refused`, `test_a_row_with_missing_fields_is_refused` | Échec fermé, avec le numéro de ligne. |
| `test_a_catalog_starting_with_a_byte_order_mark_is_read` | Un BOM ne casse pas la lecture. |
| `test_the_request_names_k_b_and_has_a_timeout`, `test_a_later_collection_asks_only_…` | User-Agent, timeout, `If-Modified-Since` au bon format. |
| `test_an_unmodified_catalog_returns_nothing`, `test_a_source_with_nothing_new_writes_no_raw_file_but_succeeds` | 304 → `None` → aucun fichier, source réussie, date avancée. |
| `test_a_catalog_larger_than_the_limit_is_refused`, `test_a_redirection_away_from_https_cisa_gov_is_refused` | Taille et origine bornées. |
| `test_collect_fails_closed_…_unreadable_state`, `test_a_collection_state_that_is_not_utf8_is_refused` | Fichier d'état illisible ou non UTF-8 → message clair, code 2. |
| `test_collect_prints_nothing_but_the_error_on_a_corrupted_state` | Plus de « no source registered » avant l'erreur. |
| `uv run pytest` : **39 passed** | Tout le dépôt passe. |
| `kb collect` réel, deux fois de suite, sur un dossier jetable | 1ʳᵉ : `cisa_kev: ok`, un CSV de 1 037 519 octets ; 2ᵉ : `cisa_kev: ok`, **aucun nouveau fichier** (le 304 réel). Relu : 1 729 vulnérabilités. |

Tous les tests tournent **sans réseau** : `urlopen` est remplacé par un faux
(`tests/test_cisa_kev_source.py`), et la lecture se teste sur
`tests/fixtures/cisa_kev_extract.csv`, 5 lignes copiées **telles quelles** du vrai CSV (en-tête,
3 lignes récentes, la plus ancienne).

## Ce que tu dois pouvoir défendre

1. **Pourquoi stocker 1 Mo à chaque fois au lieu des seules nouveautés ?** Pour pouvoir rejouer :
   si le filtre change ou a un bug, on le relance sur le brut. Et on ne stocke que quand le
   catalogue a changé (304 sinon). → `collect.py:59-61`, journal ADR.
2. **Que se passe-t-il si la CISA change le format du CSV ?** La lecture refuse le fichier entier,
   avec la liste des colonnes manquantes ou le numéro de la ligne fautive ; aucun item faux
   n'est produit. Le brut, lui, est déjà stocké : on corrige le lecteur et on rejoue.
   → `cisa_kev.py:40-43`, `51-60`.
3. **Pourquoi pas l'ETag, plus précis qu'une date ?** Parce que ce serveur l'ignore (testé), et
   que `If-Modified-Since` fonctionne sans rien stocker de plus.
4. **Pourquoi « un jour de marge », et qu'est-ce que ça coûte ?** `dateAdded` n'a pas de fuseau :
   sans marge, une ligne datée de la veille, publiée après une collecte faite tôt en UTC, serait
   perdue. Le coût : des doublons, retirés à la fusion. → `cisa_kev.py:47`.
5. **Où est la sécurité ?** URL fixe en HTTPS ; redirection hors de `https://www.cisa.gov/`
   refusée ; timeout ; taille plafonnée ; le contenu ne décide d'aucun chemin de fichier ;
   chaque champ validé avant de devenir un `Vulnerability` ; pas d'`eval` ni de `shell`.
   → `cisa_kev_source.py:24-39`, `cisa_kev.py:51-60`.

## Zones non vérifiées

- **Redirection** : la vérification de `response.url` n'est testée qu'avec un faux `urlopen`.
  Je n'ai pas observé une vraie redirection ; que `response.url` donne l'URL finale après
  redirection est le comportement documenté d'urllib, pas un comportement vu ici.
- **`response.read(n)`** : je suppose qu'il lit jusqu'à `n` octets ou la fin du fichier, et non
  moins. C'est le comportement de `http.client`, mais un envoi fragmenté n'a pas été testé.
- **`date.fromisoformat`** accepte aussi d'autres formes ISO (`20260929`) : acceptées, non
  testées.
- **Test des droits** : sauté si les tests tournent en `root` (root lit tout). En CI (GitHub
  Actions, utilisateur non root), il tourne.

## Ce qui reste

- **Texte libre non borné** (point 7 de la revue de sécurité) : `vendor_project`, `product`,
  `vulnerability_name`, `short_description` sont gardés tels quels, sans limite de longueur. Un
  champ contenant du HTML, un lien `javascript:` ou une consigne de type injection de prompt
  serait rendu tel quel. À traiter **à l'affichage**, dans le gabarit des fiches de veille :
  échapper au point d'usage, et borner la longueur.
- **Brancher la lecture** : `read_new_vulnerabilities` n'est encore appelé par aucune commande.
  C'est l'étape de fusion qui l'appellera, et qui retirera les doublons dus au jour de marge.
- **Croisement avec les alertes GitHub** : #11.
