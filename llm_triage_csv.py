# llm_triage_csv.py
import csv, json, time, sys, multiprocessing
from pathlib import Path
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_PATH = Path("data/messages.csv")
N_MAX = 50
OUT = Path("results_email/results_llm.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

MODEL = "mistral"
OLLAMA_URL = "http://localhost:11434/api/generate"

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
            "num_predict": 40,
            "num_thread": multiprocessing.cpu_count(),
            "num_ctx": 1024,
        },
        "stream": False,
        "keep_alive": "5m"
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=(10, 35))
    if r.status_code != 200:
        raise RuntimeError(f"Ollama {r.status_code}: {r.text}")
    return r.json()["response"]

def run():
    with CSV_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= N_MAX: break
            subject = row.get("subject","") or ""
            message = row.get("message","") or ""
            label_num = row.get("label")
            gt = "spam" if str(label_num) == "1" else "other"

            # texte court pour CPU : sujet + début de message
            text = (f"Subject: {subject}\n\n{message}")[:4000]
            t0 = time.time()
            success, err, pred_label = True, "", "other"
            try:
                raw = call_ollama(MODEL, PROMPT_TMPL.format(email=text))
                try:
                    data = json.loads(raw)           # format:"json" -> déjà du JSON
                except Exception:
                    import re
                    m = re.search(r"\{.*\}", raw, flags=re.S)
                    data = json.loads(m.group(0)) if m else {"label":"other"}
                lab = str(data.get("label","other")).strip().lower()
                pred_label = "spam" if lab == "spam" else "other"
            except Exception as e:
                success, err = False, repr(e)

            rec = {
                "id": f"row_{i:04d}",
                "variant": "B_LLM",
                "latency_s": round(time.time()-t0, 3),
                "success": success,
                "error": err,
                "gt": gt,
                "pred": {"label": pred_label}
            }
            OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False)+"\n")
            print(f"[LLM] row_{i:04d} -> {pred_label} (gt={gt}) err={err}")

if __name__ == "__main__":
    # petit pré-chauffage recommandé
    try:
        requests.post(OLLAMA_URL, json={
            "model": MODEL, "prompt": "{}", "format":"json", "stream": False
        }, timeout=(5,10))
    except Exception:
        pass
    run()


