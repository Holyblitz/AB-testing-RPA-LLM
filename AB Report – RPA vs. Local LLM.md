# A/B Report – RPA vs. Local LLM

Author: Romain • Period: August 2025 • Context: Comparative evaluation on a local machine (limited CPU/RAM) for realistic automation tasks.

1) ## Executive Summary

    Main finding: For simple and deterministic automation, **RPA/Rules is significantly superior** to a local LLM (latency, robustness, success rate).

    LLM's contribution: Useful as a **decision-making** engine (selecting from candidates, normalization, semantic arbitration), but weak in raw, unbounded extraction.

    **Recommended pattern: Rules/RPA → LLM (selection/normalization) → RPA (validation/formatting).**

2) ## Objectives & Hypotheses

    H1 (Structured Extraction): RPA > LLM in success and latency for fields identifiable by selectors/regex.

    H2 (Free Text): Simple Rules ≈ LLM, hybrid (RPA + LLM for ambiguous cases) > each separately.

    H3 (Semantic Decision): LLM performs well if the choice is constrained (list of candidates) and it's asked to select an index rather than generating freely.

3) ## Environment & Settings

    Hardware: Personal PC, CPU-only, limited RAM (approx. 3GB free during tests).

    LLM (Ollama): llama3.2:1b (chosen for memory constraints in the last test); initial tests with mistral were not possible for the third test (OOM errors). Typical parameters: num_ctx 512–1024, num_predict 60–80, temperature 0. We had to switch to a lighter model, Llama2.

    RPA: Playwright (headless Chromium), minimal wait (title), non-blocking retrieval, short timeouts, limited retries.

    Data:

        Web (WTTJ): Job offer pages (extracting {title, company, location, salary, skills}).
    
        Emails (messages.csv a Kaggle dataset): First 50, sorted into {billing, support, sales, spam...} with rules vs. LLM vs. hybrid.
    
        Invoices (FATURA v2): JSON annotations → "pseudo-OCR" text (50 items).

    Validity Note: Some GT (Ground Truth) **data was pre-aggregated by heuristics** (risk of leakage). A manual_gt subset was started to verify trends.

4) ## A/B Protocol

    Runner A (RPA/Rules): CSS selectors + regex + fast heuristics, no generation.

    Runner B (Free LLM): Strict JSON prompt, direct extraction from text, without candidates.

    Runner C (Selector LLM): The pipeline generates candidates (e.g., 5-10 vendor, invoice_no, date, amount), and the LLM returns indices.

    Metrics: Latency (average/median), success rate (run OK), accuracy/exact-match per field, macro-F1 (emails).

5) ## Results (Summary)

### 5.1 Web Scraping (WTTJ) – Offer Extraction

    A_RPA: n = 45 | success 95.6% | avg. lat. 5.98s | median 1.88s
    
    B_LLM: n = 54 | success 20.4% | avg. lat. 45.60s | median 60.74s

Conclusion: **RPA is far superior** (DOM + selectors > generation); LLM suffers from parsing/time and DOM variations.

### 5.2 Email Triage (50)

    A_RPA: lat. 0.00s | Accuracy 96% | Macro-F1 0.823
    
    B_LLM: lat. 23.39s (med. 23.28s) | Accuracy 88% | Macro-F1 0.468 | success 66%
    
    C_HYBRID: lat. 1.71s (med. 0.00s) | Accuracy 98% | Macro-F1 0.895 | success 100%

Conclusion: The hybrid approach dominates (rules for the bulk of the flow, LLM for ambiguous/exception cases).

### 5.3 Extraction on Invoices (50, "Floating" FATURA text)

B (Free LLM) vs C (Selector LLM) vs A (Rules) — exact-match per field:

    A_RULES_INV: 100% on {invoice_no, date, vendor, total, currency}; lat. ~ 0s
    (⚠️ strong suspicion of leakage between GT heuristics and rules; see limitations)
    
    B_LLM_INV: invoice_no 50%, date 94%, vendor 0%, total 4%, currency 76%, global exact 0%; med. lat. 4.10s
    
    C_LLM_SELECT: invoice_no 4%, date 100%, vendor 92%, total 0%, currency 8%, global exact 0%; med. lat. 5.28s

Conclusion: **The free LLM degrades vendor/total; the selector LLM strongly corrects vendor and stabilizes date**, but remains weak on total/currency as long as candidates aren't scored by context ("total/ttc/amount due" vs. "subtotal/tax/ht").

6) ## Analysis & Learnings

    Simple (Deterministic) Automation: RPA/Rules >> LLM (latency, success, cost).

    Free Text: Well-designed rules cover the essentials; LLM is useful as a backup for semantic arbitration.

    Decision-Making: The LLM excels if the output space is constrained (index selection, short reformulation); it is fragile in unconstrained generative mode.

    Field Quality: RPA can "fill" a lot but with noise if rules are naive (e.g., vendor capturing "Bill to"). This highlights the importance of validations and regex unit tests.

7) ## Limitations & Threats to Validity

    Partially heuristic GT (FATURA) → possible leakage favoring RPA.

    Hardware constraint (1B LLM on CPU): Conservative result for LLM; a vision+OCR model or a quantized 7B GPU model could change absolute performance (but not the trend for simple extraction).

    Data: WTTJ (anti-bot, hydration), synthetic email dataset, generic invoices; results are transposable but not universal.

8) ## Practical Recommendations

    Architectural Pattern: Rules → **LLM (selector) → Rules (validation).**

    When to choose RPA alone: Stable DOM, clear rules, critical SLAs, costs.

    When to add the LLM: Ambiguous fields, multi-language normalization, disambiguation (vendor, email intents), semantic scoring.

    RPA Hygiene: Stopword lists (Bill to/Ship to/Subtotal/Tax/VAT/HT/Shipping...), currency inherited from the total line, format normalization.

9) ## Work Performed (Trace)

    Scripts: rpa_runner.py, llm_runner.py, eval_ab.py, rules_triage.py, llm_triage.py, eval_email_ab.py, fatura_prep_text[_v2].py, invoices_rules.py, invoices_llm.py, invoices_llm_select.py, eval_invoice_ab.py, annotate_invoices_gt.py.

    Key Patches:

        LLM → lightweight models (llama3.2:1b) + strict JSON prompts.
    
        RPA → minimal wait (title), tolerant selectors, short timeouts, retries.
    
        Selector (C) → decision by indices, candidates generated by rules.

10) ## Next Steps 

    Harden C (invoices): Scoring total/currency candidates by context (total|ttc|amount due, exclude subtotal|tax|vat|tva|ht|shipping).

    Manual GT: 20-50 items to remove all ambiguity.

    Figures: Bar plots for median latency & exact-match (A/B/C) for the report.

11) ## Conclusion

    Simple Automation: Choose RPA/Rules.

    LLM's Value: Decision-making and normalization where rules become brittle.

    Winning Combo: Hybrid — that's where the LLM shines without sacrificing latency/robustness.