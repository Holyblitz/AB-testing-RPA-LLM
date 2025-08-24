# hybrid_triage_csv.py — règles rapides + LLM sur cas suspects
import csv, json, time, re, sys, multiprocessing
from pathlib import Path
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = Path("data/messages.csv")
N_MAX = 50
OUT = Path("results_email/results_hybrid.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

MODEL = "mistral"
OLLAMA_URL = "http://localhost:11434/api/generate"

# --- règles (mêmes patterns que rules_triage_csv.py, score = nb de hits)
SPAM_PATTERNS = [
    r"\bviagra\b", r"\bcasino\b", r"\blottery\b", r"\bwin\s+\$?\d",
    r"\bfree\b", r"\bunsubscribe\b", r"\bcredit\b", r"\bmortgage\b",
    r"\bguaranteed\b", r"\bsex\b", r"\bwork\s+from\s+home\b",
    r"\bmake\s+\$?\d+(\,\d{3})?\b",
]

def sniff_columns(fieldnames):
    f = [c.lower() for c in fieldnames]
    def pick(keys):
        for k in keys:
            for i,name in enumerate(f):
                if k in name: return fieldnames[i]
        return None
    subj = pick(["subject","sujet"])
    msg  = pick(["message","body","texte","content"])
    lab  = pick(["label","spam"])
    if not (subj and msg and lab):
        raise ValueError(f"Colonnes attendues ~ subject/message/label, trouvées: {fieldnames}")
    return subj, msg, lab

def rule_score(text: str) -> int:
    t = text.lower()
    score = 0
    for p in SPAM_PATTERNS:
        if re.search(p, t):
            score += 1
    return score

def rule_label(text: str) -> str:
    return "spam" if rule_score(text) > 0 else "other"

SYSTEM = (
    "You are an email spam classifier. Output ONLY valid JSON with this exact schema:\n"
    "{\"label\":\"spam_or_other\"}\n"
    "Allowed labels: spam, other."
)
PROMPT_TMPL = (
    "Classify this email as 'spam' or 'other'.\n"
    "Email:\n----\n{email}\n----\n"
    "Return ONLY the JSON."
)

def call_ollama(model: str, prompt: str):
    payload = {
        "model": model,
        "prompt": prompt,
        "system": SYSTEM,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_predict": 25,
            "num_thread": multiprocessing.cpu_count(),
            "num_ctx": 768,
        },
        "stream": False,
        "keep_alive": "5m"
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=(10, 30))
    if r.status_code != 200:
        raise RuntimeError(f"Ollama {r.status_code}: {r.text}")
    return r.json()["response"]

def run():
    rows = []
    with CSV_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        subj_col, msg_col, lab_col = sniff_columns(reader.fieldnames)
        for i, row in enumerate(reader):
            if i >= N_MAX: break
            subject = row.get(subj_col, "") or ""
            message = row.get(msg_col, "") or ""
            gt = "spam" if str(row.get(lab_col, "")).strip() in {"1","spam","true","yes"} else "other"
            text = f"Subject: {subject}\n\n{message}"
            rows.append({"id": f"row_{i:04d}", "text": text, "gt": gt})

    # 1) Passage règles pour tout le monde
    for r in rows:
        t0 = time.time()
        r["rule_label"] = rule_label(r["text"])
        r["rule_score"] = rule_score(r["text"])
        r["rule_latency"] = round(time.time()-t0, 3)

    # 2) Sélectionne les K plus suspects pour LLM (ceux avec score > 0)
    suspects = [r for r in rows if r["rule_score"] > 0]
    # si trop, on coupe aux top_k (par score décroissant)
    suspects.sort(key=lambda x: -x["rule_score"])
    TOP_K = min(len(suspects), max(10, N_MAX//2))  # ex: 25 max sur 50
    suspects = suspects[:TOP_K]

    # 3) Appel LLM uniquement sur ces suspects (texte tronqué)
    for r in suspects:
        t0 = time.time(); success=True; err=""; pred="other"
        try:
            short = r["text"][:1500]
            raw = call_ollama(MODEL, PROMPT_TMPL.format(email=short))
            try:
                data = json.loads(raw)
            except Exception:
                m = re.search(r"\{.*\}", raw, flags=re.S)
                data = json.loads(m.group(0)) if m else {"label":"other"}
            lab = str(data.get("label","other")).strip().lower()
            pred = "spam" if lab == "spam" else "other"
        except Exception as e:
            success=False; err=repr(e)
        r["llm_label"] = pred
        r["llm_success"] = success
        r["llm_error"] = err
        r["llm_latency"] = round(time.time()-t0, 3)

    # 4) Fusion des décisions : LLM override sur suspects, sinon règles
    for r in rows:
        final = r.get("llm_label") if r in suspects else r["rule_label"]
        lat   = r.get("llm_latency", 0.0) + r["rule_latency"]
        success = True if (r not in suspects or r.get("llm_success", False)) else False
        err = "" if success else r.get("llm_error","")

        rec = {
            "id": r["id"],
            "variant": "C_HYBRID",
            "latency_s": round(lat, 3),
            "success": success,
            "error": err,
            "gt": r["gt"],
            "pred": {"label": final}
        }
        OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False)+"\n")
        print(f"[HYBRID] {r['id']} -> {final} (gt={r['gt']}) score={r['rule_score']} llm={'yes' if r in suspects else 'no'}")

if __name__ == "__main__":
    # pré-chauffage
    try:
        requests.post(OLLAMA_URL, json={"model": MODEL, "prompt": "{}", "format":"json", "stream": False}, timeout=(5,10))
    except Exception:
        pass
    run()
