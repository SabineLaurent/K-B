# Annoncer l'erreur d'un champ par un mot, et refuser une date sans donner de format

- Date : 2026-11-22
- Branche : `fix/web-field-error-messages`
- Issues : #590 (le message d'un champ en couleurs forcées), #617 (le message d'une date refusée)
- Fichiers principaux : `src/k_b/web/templates/feed.html`, `src/k_b/web/templates/trends.html`,
  `src/k_b/web/feed.py`, `src/k_b/web/trends.py`, `docs/site-web.md`, et leurs tests dans `tests/web/`
- Série : [servir le fil de veille](2026-11-11-servir-le-fil-de-veille.md) (les messages des champs) et
  [afficher les tendances sur le site](2026-11-14-afficher-les-tendances-sur-le-site.md) (le message d'un jour
  refusé, que cette PR partage avec le fil)

Les commits de cette PR sont `8bdd1b6d` (le code et ses tests), `af54fd64` (les revues triées), `84212273`
(la fusion d'`origin/main` 39cb5eb9, sans conflit), cette note (`f77195f7`) et la précision du journal des
décisions (`6e277769`). Les autres commits de l'historique de la branche sont ceux de
`main` qu'apporte cette fusion (#658, #662, #664, #665, #670, #679) : ils ont leur propre note.

## Le pourquoi

Le site de K-B a deux formulaires : les filtres du fil (« Quoi de neuf ») et le jour des tendances. Un champ refusé
rend la page en 422, avec un message sous le champ et, sur le fil, un résumé « Filtre à corriger » en tête du
formulaire. Deux défauts restaient, relevés par les relectures d'accessibilité du site.

- **#590 : le message ne se distinguait du libellé que par sa couleur.** Le libellé est en encre `#1C1E21`, le
  message en brique `#7C2D12`, tous deux en demi-gras. Entre eux, le rapport n'est que de 1,78:1 : la couleur seule
  porte l'information « ceci est une erreur » (RGAA 3.1, WCAG 1.4.1). En couleurs forcées (le mode de contraste
  élevé de Windows), le navigateur remplace les couleurs du site par celles que la personne a choisies : libellé et
  message deviennent de la même couleur, et rien ne dit plus que le second est une erreur (RGAA 11.10, WCAG 3.3.1).
- **#617 : le message d'une date refusée donnait un format que le champ ne montre pas.** Le message disait « un
  jour attendu, sous la forme AAAA-MM-JJ ». Or un champ `<input type="date">` affiche le jour à la façon du
  navigateur (`10/10/2026` dans Chrome en français) : la personne ne tape jamais `AAAA-MM-JJ`, et le site ne sait
  pas quel format son navigateur lui montre. L'aide était donc fausse pour elle (Opquast 2025, règle 80 : un
  message d'erreur aide à corriger).

## Le comment

### 1. Un mot en tête du message, écrit dans le gabarit

Le message de chaque champ du fil est rendu par une macro Jinja2, `field_error` :

```jinja
{%- if field in error_by_field %}
<p id="{{ field }}-error" class="field-error">Erreur. {{ error_by_field[field] }}</p>
{%- endif -%}
```

(`src/k_b/web/templates/feed.html:5-7`). « Erreur. » est du texte : il reste lisible dans tous les modes de
couleur, et un lecteur d'écran le lit, puisque le message est lié au champ par `aria-describedby`. Le mot est posé
dans le gabarit, pas dans les constantes de `feed.py` : les mêmes messages servent aussi au résumé, où le mot
serait de trop (section 2). Les tendances ont leur propre gabarit, avec le même mot
(`src/k_b/web/templates/trends.html:14`).

La feuille de style n'a pas changé : `.field-error` garde sa couleur et son demi-gras
(`src/k_b/web/static/site.css:464-468`). Le mot s'ajoute à la couleur ; il ne la remplace pas.

### 2. Le résumé garde les messages sans le mot

Le résumé « Filtre à corriger » liste un lien par champ refusé :

```jinja
<h2>Filtre à corriger</h2>
<ul>
{% for error in errors %}
<li><a href="#{{ error.field }}">{{ error.message }}</a></li>
```

(`src/k_b/web/templates/feed.html:23-26`). Son titre dit déjà qu'il s'agit d'erreurs : « Erreur. » répété devant
chaque lien ne dirait rien de plus. C'est pourquoi le mot vit dans la macro du champ et `error.message` reste le
texte seul. Un test vérifie que chaque lien du résumé porte exactement le message de son champ, mot retiré
(section « Preuve »).

### 3. Une seule fonction pour le message d'un jour refusé

Le fil (la date de début, `start`) et les tendances (le dernier jour de la fenêtre, `window_end`) lisent un jour
par la même fonction, `read_written_day`, qui applique `WrittenDay`, le type des routes de l'API de données
(`src/k_b/web/feed.py:265-271`). Ils partagent maintenant aussi le message du refus :

```python
def write_day_refusal(field_in_messages: str, value: str) -> str:
    if DAY_FORM.fullmatch(value):
        return (
            f"{field_in_messages} invalide: {value} n’existe pas."
            " Choisissez un jour qui existe."
        )
    if LONG_YEAR_DAY.fullmatch(value):
        return f"{field_in_messages} invalide: l’année a plus de 4 chiffres."
    return f"{field_in_messages} invalide: choisissez un jour dans le champ."
```

(`src/k_b/web/feed.py:274-287`, docstring et commentaire retirés de l'extrait). Chaque page donne le nom de son
champ : `START_IN_MESSAGES = "Date de début"` (`feed.py:97`), `WINDOW_END_IN_MESSAGES = "Date"` (`trends.py:32`).
La fonction était `write_refusal`, dans `trends.py` ; elle est déplacée dans `feed.py`, que `trends.py` importait
déjà (`trends.py:12-17`). Le sens de la dépendance ne change pas.

### 4. Trois phrases, et une valeur nommée seulement si elle a la forme d'un jour

`write_day_refusal` n'est appelée qu'après un refus de `WrittenDay` (`feed.py:260-261`, `trends.py:88-93`). Trois
cas :

- **La valeur a la forme d'un jour** (`DAY_FORM`, `[0-9]{4}-[0-9]{2}-[0-9]{2}`, `src/k_b/items.py:69`) : elle a
  quatre chiffres, deux, deux, et `WrittenDay` l'a pourtant refusée. C'est donc un jour qui n'existe pas
  (`2026-02-30`, `2026-13-01`). Le message le nomme, puisque le champ `type=date` ne peut pas le réafficher
  (sa valeur est un jour valide ou rien, WHATWG ; Opquast 81).
- **Une année de 5 ou 6 chiffres** (`LONG_YEAR_DAY`, `[0-9]{5,6}-[0-9]{2}-[0-9]{2}`, `feed.py:88`) : « … invalide:
  l’année a plus de 4 chiffres. », sans la valeur. C'est le seul refus que Chrome envoie (section 5) ; HTML s'arrête
  à l'année 275760, d'où 6 chiffres au plus. Troisième phrase décidée par Sabine le 2026-11-22 (constat CR1).
- **Toute autre valeur** (`07/10/2026`, `2026-1-7`, `2026666-01-01`, un caractère de contrôle) : une phrase vraie
  dans tous les cas, sans la valeur et sans format.

Nommer seulement une valeur de cette forme est une mesure de sécurité autant qu'une aide : une valeur qui a passé
`DAY_FORM` fait 10 caractères, chiffres ASCII et tirets. Un lien piégé (`?start=<un texte>`) ne peut donc jamais
faire écrire au site un texte de son choix. Jinja2 échappe de toute façon chaque valeur (`autoescape=True`,
`src/k_b/web/rendering.py:21-24`) ; ce filtre est une seconde défense.

`DAY_FORM` est la constante d'`items.py`, déjà utilisée par `check_day_form` (`items.py:133-138`) : les tendances
avaient leur propre copie du motif, `DAY_SHAPE`, retirée. Un motif qui sert à plus d'un module s'écrit une fois,
dans `items.py` (règle 4 de `.claude/rules/conventions.md`). C'est un écart au plan, qui prévoyait de garder
`DAY_SHAPE` ; time-knight l'a accepté le 21/11.

### 5. Ce qu'un vrai navigateur envoie

Le 21/11, des frappes réelles au clavier dans Chrome 157 (par le protocole de débogage, `wip/590/typed-in-chrome.txt`,
hors du dépôt) ont montré ce que le champ laisse partir :

- `30/02/2026` : bloqué par le navigateur (`badInput`, « Veuillez saisir une valeur valide… ») ; rien n'est envoyé.
- une année de 5 ou 6 chiffres (`20266`, `202666`) : acceptée et envoyée, `window_end=20266-01-01`.

Le seul refus qu'un vrai navigateur envoie au site est donc l'année de plus de 4 chiffres. Elle reçoit sa phrase,
« … invalide: l’année a plus de 4 chiffres. » (section 4). La phrase « n’existe pas » ne sert qu'à une adresse
modifiée à la main, ou à un navigateur sans calendrier.

Le journal des décisions disait le contraire : son entrée du 2026-11-14 sur le jour des tendances (#596) écrivait
que le sélecteur de date n'envoie qu'un jour valide, et qu'une valeur refusée ne vient que d'une adresse écrite à
la main. Le texte d'une décision ne se réécrit pas : une ligne « **Précisée le 2026-11-22** » y ajoute le fait
mesuré, comme les « Révisée le » du journal (tri de time-knight du 22/11).

## Choix faits et options écartées

| Choix | Retenu, et pourquoi | Écarté, et pourquoi |
|---|---|---|
| Distinguer le message en couleurs forcées | Un mot en tête, « Erreur. » : du texte, lisible dans tous les modes. Choix de Sabine du 21/11. | Une règle `@media (forced-colors: active)` : elle ne vaut que dans ce mode, et laisse le défaut de RGAA 3.1 (la couleur seule) dans le mode normal. |
| La forme du mot | « Erreur. » (choix de Sabine, 21/11) | « Erreur: » : deux deux-points de suite (« Erreur: Date de début invalide: … »), et une majuscule après le premier. |
| Où écrire le mot | Dans les gabarits (choix de Sabine, 21/11) | Dans les constantes de `feed.py` : le résumé, sous son titre « Filtre à corriger », l'aurait répété devant chaque lien. |
| Le mot dans deux gabarits | Gardé en deux copies, `feed.html` et `trends.html` : chacune est tenue par un test (`test_accessibility.py`). Constat CR5 de la revue, laissé par time-knight. | Une macro commune : `code.md` factorise à la troisième occurrence, pas à la deuxième. |
| Le texte du message d'une date | Les deux phrases proposées et validées par Sabine (21/11), et une troisième pour l'année de 5 ou 6 chiffres, que Chrome envoie (Sabine, 22/11, constat CR1) | « avec son année en 4 chiffres » : faux pour `2026-02-30` ou `2026-1-7`, dont l'année a 4 chiffres. « JJ/MM/AAAA » : faux dans un autre navigateur, et faux pour l'adresse. |
| Où vit la fonction | `feed.py`, que `trends.py` importe déjà (décision de Sabine) | Garder une fonction par page : elles divergeaient déjà, le fil n'ayant qu'une phrase fixe, sans la valeur. |
| Un second contrôle dans `write_day_refusal` | Aucun : la docstring dit qu'elle prend une valeur que `WrittenDay` a refusée (constat CR4, corrigé ainsi) | Relire le jour dans la fonction : chaque appelant le lit déjà par `read_written_day`, juste avant. |
| `max="9999-12-31"` sur les champs | Non ajouté (constat CR2, laissé) | Vérifié dans Chrome : avec `max`, `20266` devient `0266-01-01`, envoyé sans erreur. Un jour faux, en silence, est pire qu'un refus. |
| Le libellé « Date » des tendances | Gardé : il existait sur `main`, et le plan validé dit « Date de début » ou « Date » (CR6, laissé) | « Fenêtre se terminant le invalide » : une phrase qui ne se lit pas. |

## Preuve

| Test ou sortie observée | Ce que ça démontre |
|---|---|
| 25 échecs montrés avant le code (session du 21/11), puis `uv run pytest` : 5670 passed sur `84212273` | Les tests lisaient l'ancien texte ; le code nouveau les fait passer, sans casser le reste. |
| `test_the_message_of_each_field_refused_opens_with_a_word_that_says_an_error` (`tests/web/test_accessibility.py:523`), sur le fil refusé et les tendances refusées | Chaque message sous un champ commence par « Erreur. », sur les deux pages. |
| `test_the_summary_says_the_message_of_each_field_without_its_word` (`test_accessibility.py:534`) | Le résumé a un lien par champ refusé (`q`, `kinds`, `start`), chacun avec le message de son champ, sans le mot. |
| `FEED_REFUSED` avec `&start=2026-02-30` (`test_accessibility.py:33`, constat A4) | Les contrôles d'accessibilité du fil refusé passent aussi par `write_day_refusal`. |
| `test_date_checked_without_a_valid_day_is_refused_on_the_start_field` (`tests/web/test_feed.py:181`) | Chaque valeur refusée de la date de début reçoit sa phrase : manquante, pas un jour (`07/10/2026`, `2026-1-7`, `2026666-01-01`), une année de 5 ou 6 chiffres (`20266-01-01`, `202666-01-01`), jour qui n'existe pas (`2026-02-30`, nommé). |
| `test_a_year_of_5_or_6_digits_is_said_in_its_message` (`tests/web/test_trends.py:98`) ; rouge montré avant le correctif de CR1 (6 échecs, 21/11), puis `uv run pytest` : 5675 passed sur `251a33cc` | La troisième phrase, sans la valeur, sur les tendances. |
| `test_a_value_that_is_not_a_day_is_refused_on_its_field` et `test_a_value_of_the_form_of_a_day_that_does_not_exist_is_named_in_its_message` (`tests/web/test_trends.py:74`, `:82`) | Les mêmes phrases sur les tendances, avec « Date » ; huit valeurs qui ne sont pas un jour, dont l'année à 7 chiffres. |
| `test_a_start_of_a_year_of_5_digits_is_refused_without_a_format_the_field_does_not_show` (`tests/web/test_feed_page.py:241`) | Page entière : 422, aucun appel à l'API, ni `AAAA-MM-JJ` ni `20266` dans la page. |
| Chrome 157, couleurs forcées émulées, 390 px (`wip/590/forced-colors-390.json`, captures `wip/590/shots/`, hors du dépôt) | En couleurs forcées, libellés et messages sont tous `rgb(255, 255, 255)` en 600 : seul « Erreur. » les distingue. Sans émulation (`normal-390.json`), message `rgb(124, 45, 18)` et libellé `rgb(28, 30, 33)`, 1,78:1. |
| Chrome 157, frappes réelles (`wip/590/typed-in-chrome.txt`) | `30/02/2026` bloqué par le navigateur ; une année de 5 ou 6 chiffres envoyée. |
| `/security-review` : aucun constat ; `ruff check --no-cache`, `ruff format --check`, `mypy --strict` (198 fichiers) verts ; aucun caractère `Cc` ni `Cf` | Les contrôles du dépôt. |

## Ce que tu dois pouvoir défendre

1. **Pourquoi un mot plutôt qu'une règle CSS pour les couleurs forcées ?** Une règle `forced-colors` ne corrige
   que ce mode, et laisse en mode normal la couleur seule séparer le message du libellé (1,78:1). Le mot est du
   texte : il se lit partout, au lecteur d'écran compris (RGAA 3.1 et 11.10 ; `feed.html:5-7`).
2. **Pourquoi le résumé n'a-t-il pas le mot ?** Son titre, « Filtre à corriger », dit déjà que ce sont des
   erreurs ; le mot serait répété à chaque lien. C'est pour cela qu'il est écrit dans la macro du champ, et non dans
   les messages (`feed.html:23-26`).
3. **Un lien piégé peut-il faire afficher un texte au site ?** Non : seule une valeur de la forme d'un jour
   (`DAY_FORM`, 10 caractères, chiffres ASCII et tirets) est nommée dans le message ; toute autre valeur reçoit une
   phrase fixe. Jinja2 échappe en plus chaque valeur (`feed.py:274-287`, `items.py:69`).
4. **Pourquoi ne pas écrire le format attendu, puisque l'adresse attend `AAAA-MM-JJ` ?** Parce que la personne ne
   tape jamais dans l'adresse : elle tape dans le champ, qui montre le jour à la façon de son navigateur. Donner
   `AAAA-MM-JJ`, c'est lui demander un format qu'elle ne voit pas (Opquast 80).
5. **Que voit la personne qui tape une année à 5 chiffres ?** « Erreur. Date de début invalide: l’année a plus de 4
   chiffres. » La phrase dit la cause (WCAG 3.3.3), sans la valeur et sans format (`feed.py:285-286`).

## Zones non vérifiées

- **Un vrai lecteur d'écran** n'a pas été passé : que « Erreur. » soit lu avant le message, puis « invalide » une
  seconde fois, est déduit du HTML (le message est lié au champ par `aria-describedby`), pas entendu. Le constat A6
  de la relecture (« invalide » entendu deux fois) a été laissé : c'est le patron courant, celui de GOV.UK.
- **Les couleurs forcées réelles de Windows** : la preuve est l'émulation de Chrome (`forced-colors: active`), pas
  un poste Windows en contraste élevé.
- **Les autres navigateurs** : seul Chrome 157 a été essayé au clavier. Firefox et Safari peuvent laisser passer
  d'autres valeurs du champ ; elles recevraient l'une des trois phrases, vraies dans tous les cas.
- **Les maquettes du 09/11** n'ont pas pu être relues par le relecteur d'accessibilité (`read_artifact` a répondu
  « not found ») : leur accord avec le mot ajouté n'est pas vérifié.

## Ce qui reste

- **A5** : les groupes « Sortes » et « Depuis » (des `fieldset`) n'ont pas d'`aria-invalid`, l'attribut étant
  déprécié sur le rôle `group` en ARIA 1.2 ; hors de ces deux issues.
- **A7** : la déclaration d'accessibilité du site (`accessibilite.html`) ne dit pas que les messages du fil ont
  été vérifiés ; hors de ces deux issues, laissé par time-knight.
- À 390 px, le message du fil coupe la valeur au tiret (« 2026-02- / 30 ») ; laissé par time-knight, hors des deux
  issues, le message restant lisible.
