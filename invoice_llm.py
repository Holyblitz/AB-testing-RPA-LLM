# invoices_llm.py
import json, time, sys, multiprocessing, re
from pathlib import Path
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

IN = Path("data/fatura_subset/items.jsonl")
OUT = Path("results_invoice/llm.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

MODEL = "llama3.2:1b"
URL = "http://localhost:11434/api/generate"

SYSTEM = (
    "You extract key fields from invoices. Output ONLY valid JSON:\n"
    "{\"invoice_no\":\"str\",\"date\":\"str\",\"vendor\":\"str\",\"total\":\"str\",\"currency\":\"str\"}\n"
    "If unknown, use empty string. Keep numbers canonical (e.g., 1234.56)."
)
PROMPT = "Invoice text:\n----\n{doc}\n----\nReturn ONLY the JSON."

def call_ollama(prompt):
    payload = {
        "model": MODEL, "prompt": prompt, "system": SYSTEM, "format":"json",
        "options": {"temperature":0, "num_predict": 80, "num_ctx": 1024,
                    "num_thread": multiprocessing.cpu_count()},
        "stream": False, "keep_alive": "5m"
    }
    r = requests.post(URL, json=payload, timeout=(10,35))
    if r.status_code!=200: raise RuntimeError(f"Ollama {r.status_code}: {r.text}")
    return r.json()["response"]

def force_json(s):
    try: return json.loads(s)
    except: m = re.search(r"\{.*\}", s, flags=re.S); return json.loads(m.group(0)) if m else {}

def main():
    OUT.write_text("", encoding="utf-8")
    for line in IN.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        doc = obj["text"][:6000]
        t0 = time.time(); success=True; err=""; pred={}
        try:
            raw = call_ollama(PROMPT.format(doc=doc))
            data = force_json(raw)
            pred = {
                "invoice_no": data.get("invoice_no","") or "",
                "date": data.get("date","") or "",
                "vendor": data.get("vendor","") or "",
                "total": data.get("total","") or "",
                "currency": data.get("currency","") or "",
            }
        except Exception as e:
            success=False; err=repr(e); pred={"invoice_no":"","date":"","vendor":"","total":"","currency":""}
        rec = {
            "id": obj["id"], "variant":"B_LLM_INV",
            "latency_s": round(time.time()-t0,3), "success": success, "error": err, "pred": pred
        }
        OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False)+"\n")
        print(f"[LLM] {obj['id']} -> {pred} err={err}")
    print(f"✅ Résultats: {OUT}")

if __name__ == "__main__":
    try: requests.post(URL, json={"model":MODEL,"prompt":"{}","format":"json","stream":False}, timeout=(5,10))
    except: pass
    main()

