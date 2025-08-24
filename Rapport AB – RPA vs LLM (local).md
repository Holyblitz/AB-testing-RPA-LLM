# Rapport A/B – RPA vs LLM (local)

**Auteur :** Romain • **Période :** août 2025 • **Contexte :** évaluation comparative sur machine locale (CPU/RAM limitée) pour des tâches d’automatisation réalistes.

---

## 1) Résumé exécutif

* **Constat principal :** pour l’automatisation **simple et déterministe**, le **RPA/Rules** est **nettement supérieur** au LLM local (latence, robustesse, taux de succès).
* **Apport du LLM :** utile comme **moteur de décision** (sélection parmi des candidats, normalisation, arbitrage sémantique), mais **faible** en extraction brute non bornée.
* **Patron recommandé :** **Rules/RPA → LLM (sélection/normalisation) → RPA (validation/formatage)**.

---

## 2) Objectifs & hypothèses

* **H1 (extraction structurée) :** RPA > LLM en succès et latence sur des champs identifiables par sélecteurs/regex.
* **H2 (texte libre) :** Règles simples ≈ LLM, **hybride** (RPA + LLM pour cas ambigus) > chacun séparément.
* **H3 (décision sémantique) :** LLM performant si on **borne** le choix (liste de candidats) et qu’on lui demande de **choisir l’index** plutôt que de générer librement.

---

## 3) Environnement & réglages

* **Matériel :** PC perso, CPU-only, RAM limitée (≈ 3 Go libres pendant les eessais).
* **LLM (Ollama) :** `llama3.2:1b` (choisi pour la contrainte mémoire dans le dernier test) ; tests initiaux avec `mistral`puis impossibles pour le troisième.(erreurs OOM). Paramètres typiques : `num_ctx 512–1024`, `num_predict 60–80`, `temperature 0`. Nous avons du prendre un modèle plus leger LLama2
* **RPA :** Playwright (Chromium headless), attente minimale (titre), récupération non bloquante, timeouts courts, retries limités.
* **Données :**

  * **Web (WTTJ)** : pages d’offres d’emploi (extraction {title, company, location, salary, skills}).
  * **Emails (messages.csv un dataset kaggle)** : 50 premiers, tri en {billing, support, sales, spam…} avec règles vs LLM vs hybride.
  * **Factures (FATURA v2)** : annotations JSON → « pseudo-OCR » texte (50 items).

> **Note validité** : certaines GT ont été **pré-agrégées par heuristiques** (risque de fuite). Un sous-ensemble **manual\_gt** a été amorcé pour vérifier les tendances.

---

## 4) Protocole A/B

* **Runner A (RPA/Rules)** : sélecteurs CSS + regex + heuristiques rapides, aucune génération.
* **Runner B (LLM libre)** : prompt JSON strict, extraction directe depuis le texte, sans candidats.
* **Runner C (LLM sélecteur)** : le pipeline génère des **candidats** (p. ex. 5–10 `vendor`, `invoice_no`, `date`, `amount`), et le LLM **renvoie des indices**.
* **Mesures** : latence (moyenne/médiane), taux de succès (run OK), accuracy/exact-match par champ, macro-F1 (emails).

---

## 5) Résultats (synthèse)

### 5.1 Web scraping (WTTJ) – extraction d’offres

* **A\_RPA** : *n* = 45 | **succès 95,6 %** | lat. moyenne **5,98 s** | médiane **1,88 s**
* **B\_LLM** : *n* = 54 | **succès 20,4 %** | lat. moyenne **45,60 s** | médiane **60,74 s**

**Conclusion :** RPA très supérieur (DOM + sélecteurs > génération) ; LLM souffre du parsing/temps et des variations DOM.

### 5.2 Triage d’emails (50)

* **A\_RPA** : lat. **0,00 s** | **Accuracy 96 %** | **Macro-F1 0,823**
* **B\_LLM** : lat. **23,39 s** (méd. 23,28 s) | **Accuracy 88 %** | **Macro-F1 0,468** | succès 66 %
* **C\_HYBRID** : lat. **1,71 s** (méd. 0,00 s) | **Accuracy 98 %** | **Macro-F1 0,895** | succès 100 %

**Conclusion :** l’**hybride** domine (règles pour le gros du flux, LLM pour cas ambigus/exceptions).

### 5.3 Extraction sur factures (50, texte « flottant » FATURA)

**B (LLM libre)** vs **C (LLM sélecteur)** vs **A (Rules)** — exact-match par champ :

* **A\_RULES\_INV** : **100 %** sur {invoice\_no, date, vendor, total, currency} ; lat. \~ **0 s**
  *(⚠️ forte suspicion de fuite entre heuristiques GT et règles ; voir limites)*
* **B\_LLM\_INV** : invoice\_no **50 %**, date **94 %**, vendor **0 %**, total **4 %**, currency **76 %**, exact global **0 %** ; lat. méd. **4,10 s**
* **C\_LLM\_SELECT** : invoice\_no **4 %**, date **100 %**, vendor **92 %**, total **0 %**, currency **8 %**, exact global **0 %** ; lat. méd. **5,28 s**

**Conclusion :** le LLM **libre** dégrade vendor/total ; le LLM **sélecteur** **corrige fortement `vendor`** et **stabilise `date`**, mais reste faible sur `total/currency` tant que les candidats ne sont pas scorés par contexte ("total/ttc/amount due" vs "subtotal/tax/ht").

---

## 6) Analyse & enseignements

* **Automatisation simple (déterministe)** : **RPA/Rules >> LLM** (latence, succès, coût).
* **Texte libre** : règles bien conçues couvrent l’essentiel ; **LLM utile en appoint** pour arbitrages sémantiques.
* **Décision** : le LLM excelle si on **borne** l’espace de sortie (sélection d’indices, reformulation courte) ; il est fragile en mode génératif non contraint.
* **Qualité des champs** : RPA peut « remplir » beaucoup mais avec  du**bruit** si les règles sont naïves (p. ex. `vendor` capturant "Bill to"). D’où l’intérêt des **validations** et **tests unitaires regex**.

---

## 7) Limites & menaces à la validité

1. **GT partiellement heuristique** (FATURA) → possible **fuite** en faveur de Rpa.
2. **Contrainte matérielle** (LLM 1B en CPU) : résultat conservateur pour LLM ; un modèle vision+OCR ou un 7B quantisé GPU pourrait changer les perfs absolues (pas la tendance sur extraction simple).
3. **Données** : WTTJ (anti-bot, hydratation), emails dataset synthétique, factures génériques ; résultats transposables mais non universels.

---

## 8) Recommandations pratiques

* **Pattern d’archi** : *Rules → LLM (sélecteur) → Rules (validation)*.
* **Quand choisir RPA seul** : DOM stable, règles claires, SLA critiques, coûts.
* **Quand ajouter le LLM** : champs ambigus, normalisation multi-langue, désambiguisation (`vendor`, intents emails), scoring sémantique.
* **Hygiène RPA** : listes de stopwords (Bill to/Ship to/Subtotal/Tax/HT/TVA…), devise héritée de la ligne du `total`, normalisation des formats.

---

## 9) Travail effectué (trace)

* **Scripts** : `rpa_runner.py`, `llm_runner.py`, `eval_ab.py`, `rules_triage.py`, `llm_triage.py`, `eval_email_ab.py`, `fatura_prep_text[_v2].py`, `invoices_rules.py`, `invoices_llm.py`, `invoices_llm_select.py`, `eval_invoice_ab.py`, `annotate_invoices_gt.py`.
* **Patches clés** :

  * LLM → modèles légers (`llama3.2:1b`) + prompts JSON stricts.
  * RPA → attente minimale (titre), selectors tolerant, timeouts courts, retries.
  * Sélecteur (C) → décision par **indices**, candidates générés par règles.

---

## 10) Prochaines étapes 

* **Durcir C (factures)** : scoring des candidats `total/currency` par contexte (`total|ttc|amount due`, exclure `subtotal|tax|vat|tva|ht|shipping`).
* **GT manuelle** : 20–50 items pour lever toute ambiguïté.
* **Figures** : barplots latence médiane & exact-match (A/B/C) pour le rapport.

---

## 11) Conclusion

* **Automatisation simple** : choisissez **RPA/Rules**.
* **Valeur du LLM** : **prise de décision** et **normalisation** quand les règles deviennent fragiles.
* **Combo gagnant** : **Hybride** — c’est là que LLM brille sans pénaliser latence/robustesse.