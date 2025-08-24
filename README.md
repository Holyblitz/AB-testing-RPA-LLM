# AB-testing-RPA-LLM

README (checklist)

objectifs & protocole (A/B/C)

env local (Ollama + modèle léger, Playwright install chromium)

étapes pour reproduire 

limites & menaces à la validité

pas de redistribution des datasets → liens officiels (WTTJ à scraper soi-même, FATURA2 via Zenodo, dataset kaggle de mails)

licence (MIT simple)

2) Post LinkedIn 

RPA vs LLM (local) : ce que montrent nos tests A/B
Contexte : machine locale (CPU/RAM limitée), 3 tâches réalistes.
Résultats (très courts)
• Web (WTTJ) – extraction : RPA > LLM (95,6% vs 20,4%, latence ~1,9s vs 60,7s)
• Emails (50) – tri : Hybride Règles+LLM = 98% (règles 96%, LLM 88%)
• Factures (50) – texte flottant : RPA très fort sur extraction simple ; LLM utile comme sélecteur (arbitrage sémantique) mais faible en extraction brute
Conclusion : pour l’automatisation déterministe → RPA/Rules. Le LLM apporte de la valeur en prise de décision quand on borne les choix (candidats) ou pour normaliser. Le meilleur compromis est souvent Hybride (Rules → LLM sélecteur → Rules).
Rapport & scripts (GitHub) en commentaire.
(Contexte, limites et détails dans le README.)

---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

A/B Testing – RPA vs LLM (Local)

Author: Romain
Period: August 2025
Scope: On a local machine (CPU, limited RAM), we compare classic automation (RPA/Rules) vs a local LLM (via Ollama), plus a hybrid approach, on three realistic tasks.

TL;DR (Executive Summary)

For simple, deterministic automation, RPA/Rules clearly beat a local LLM on latency, robustness, and cost.

LLMs shine when they are bounded (choosing among candidates) and used for semantic decisions or normalization—not as raw extractors.

Best pattern: Rules/RPA → LLM (selector/normalizer) → Rules (validation).

Experiments & Key Results
1) Web extraction (WTTJ job pages)

Fields: {title, company, location, salary, skills}

A_RPA: success ≈ 95.6%, median latency ≈ 1.9 s

B_LLM: success ≈ 20.4%, median latency ≈ 60.7 s

Takeaway: DOM + selectors (RPA) >> free-form generation (LLM) for structured web extraction.

2) Email triage (first 50 emails)

A_RULES: Accuracy 96%, Macro-F1 0.823, median latency ~0 s

B_LLM: Accuracy 88%, Macro-F1 0.468, median latency ~23 s

C_HYBRID (Rules+LLM): Accuracy 98%, Macro-F1 0.895, median latency ~1.7 s

Takeaway: A simple hybrid (rules do most; LLM handles ambiguous cases) outperforms either alone.

3) Invoice field extraction (FATURA v2, 50 “pseudo-OCR” texts)

A_RULES_INV: 100% per field (likely label-leak in this subset—see Limitations).

B_LLM_INV (free extraction): Strong on date, weak on vendor/total.

C_LLM_SELECT (choose among candidates): vendor 92%, date 100%, but total/currency still low until candidate scoring is improved (prefer “total/ttc/amount due”, exclude “subtotal/tax/ht”).

Takeaway: LLM as decision maker works—if you constrain outputs to select indices from good candidates built by rules.
