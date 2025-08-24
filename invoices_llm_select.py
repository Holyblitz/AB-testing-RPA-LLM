# invoices_llm_select.py — LLM choisit parmi des candidats extraits par règles
import json, re, time, sys, multiprocessing
from pathlib import Path
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

IN  = Path("data/fatura_subset/items.jsonl")
OUT = Path("results_invoice/llm_select.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

MODEL = "llama3.2:1b"  # léger & rapide en CPU
URL   = "http://localhost:11434/api/generate"

CUR_PAT = r"(€|eur|euro|\$|usd|£|gbp)"
AMT_PAT = r"(?<!\w)(\d{1,3}(?:[ .,\u00A0]\d{3})*(?:[.,]\d{2})?)(?!\w)"
DATE_PATS = [
    r"\b(\d{4}-\d{2}-\d{2})\b",
    r"\b(\d{2}/\d{2}/\d{4})\b",
    r"\b(\d{2}-\d{2}-\d{4})\b",
    r"\b(\d{1,2}\s+[A-Za-zéûôîà]+\.?\s+\d{2,4})\b",
]

def norm_amt_val(s):
    s = s.replace("\u00A0"," ").strip()
    if s.count(",")==1 and s.count(".")==0:
        s = s.replace(" ","").replace(".","").replace(",",".")
    else:
        s = s.replace(" ","").replace(",","")
    try:
        return float(s)
    except:
        m = re.search(r"\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else None

def extract_candidates(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 1) vendor candidates: lignes d’en-tête non numériques
    vendor_cands = []
    for ln in lines[:20]:
        if len(ln) >= 5 and not re.search(AMT_PAT, ln):
            vendor_cands.append(ln)
    vendor_cands = vendor_cands[:10] or [""]

    # 2) invoice_no candidates
    invoice_cands = []
    # proches d’un mot-clé
    for m in re.finditer(r"(?:invoice|facture|inv)[^\n]{0,25}(?:no|n[°o]|#|num(?:éro)?)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/\.]{2,})", text, flags=re.I):
        invoice_cands.append(m.group(1))
    # tokens plausibles (fallback)
    if len(invoice_cands) < 3:
        toks = re.findall(r"\b[A-Z0-9][A-Z0-9\-\/\.]{2,}\b", " ".join(lines[:30]))
        invoice_cands += [t for t in toks if len(t) <= 20]
    # dédupliquer
    seen=set(); invoice_cands = [t for t in invoice_cands if not (t in seen or seen.add(t))]
    invoice_cands = invoice_cands[:8] or [""]

    # 3) date candidates
    date_cands=[]
    for pat in DATE_PATS:
        for m in re.finditer(pat, text, flags=re.I):
            date_cands.append(m.group(1))
    seen=set(); date_cands = [d for d in date_cands if not (d in seen or seen.add(d))]
    date_cands = date_cands[:8] or [""]

    # 4) amounts (value + currency + context line)
    amt_cands = []
    for i, ln in enumerate(lines[:200]):
        # cherche devise dans la ligne
        mcur = re.search(CUR_PAT, ln, flags=re.I)
        cur = ""
        if mcur:
            cur = mcur.group(1).upper().replace("€","EUR").replace("$","USD").replace("£","GBP")
        for m in re.finditer(AMT_PAT, ln):
            val_raw = m.group(1)
            val = norm_amt_val(val_raw)
            if val is not None:
                amt_cands.append((val, cur, ln))
    # garde top 8 montants plus grands (souvent le total)
    amt_cands.sort(key=lambda x: -x[0])
    # dédup par (val,cur) approx
    uniq=[]; seen=set()
    for v, c, ln in amt_cands:
        key = (round(v,2), c)
        if key in seen: continue
        seen.add(key)
        uniq.append((v,c,ln))
        if len(uniq)>=8: break
    amt_cands = uniq or [(0.0,"","")]

    return vendor_cands, invoice_cands, date_cands, amt_cands

SYSTEM = (
    "You must choose the correct fields of an invoice by selecting indices from candidate lists.\n"
    "Return ONLY valid JSON with this schema:\n"
    "{\"vendor_idx\":int, \"invoice_idx\":int, \"date_idx\":int, \"amount_idx\":int, \"currency\":\"\"}\n"
    "- Indices are 0-based. Use -1 if none applies.\n"
    "- currency must be one of: \"\", \"EUR\", \"USD\", \"GBP\".\n"
    "- Prefer the grand total (Amount Due / Total TTC) over subtotals or line items."
)

PROMPT_TMPL = (
    "Pick the best indices from the candidate lists below.\n\n"
    "VENDORS:\n{vendors}\n\n"
    "INVOICE_NUMBERS:\n{invoices}\n\n"
    "DATES:\n{dates}\n\n"
    "AMOUNTS (value ~ currency ~ context line):\n{amounts}\n\n"
    "Return ONLY the JSON."
)

def call_ollama(prompt):
    payload = {
        "model": MODEL, "prompt": prompt, "system": SYSTEM, "format":"json",
        "options": {"temperature":0, "num_predict": 50, "num_ctx": 768,
                    "num_thread": multiprocessing.cpu_count()},
        "stream": False, "keep_alive": "5m"
    }
    r = requests.post(URL, json=payload, timeout=(10, 35))
    if r.status_code != 200:
        raise RuntimeError(f"Ollama {r.status_code}: {r.text}")
    return r.json()["response"]

def force_json(s):
    try: return json.loads(s)
    except: 
        m = re.search(r"\{.*\}", s, flags=re.S)
        return json.loads(m.group(0)) if m else {}

def run():
    OUT.write_text("", encoding="utf-8")
    for line in IN.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line); text = obj["text"]
        vendor_cands, inv_cands, date_cands, amt_cands = extract_candidates(text)

        def fmt_list(lst): 
            return "\n".join([f"[{i}] {x}" for i,x in enumerate(lst)])
        def fmt_amts(lst):
            return "\n".join([f"[{i}] {v:.2f} ~ {c or ''} ~ {ln[:120]}" for i,(v,c,ln) in enumerate(lst)])

        prompt = PROMPT_TMPL.format(
            vendors = fmt_list(vendor_cands),
            invoices= fmt_list(inv_cands),
            dates   = fmt_list(date_cands),
            amounts = fmt_amts(amt_cands),
        )
        t0=time.time(); success=True; err=""; pred={}

        try:
            raw = call_ollama(prompt)
            data = force_json(raw)
            v_idx = int(data.get("vendor_idx",-1))
            i_idx = int(data.get("invoice_idx",-1))
            d_idx = int(data.get("date_idx",-1))
            a_idx = int(data.get("amount_idx",-1))
            cur   = (data.get("currency","") or "").upper()
        except Exception as e:
            success=False; err=repr(e)
            v_idx=i_idx=d_idx=a_idx=-1; cur=""

        # map vers valeurs finales
        vendor = vendor_cands[v_idx] if 0 <= v_idx < len(vendor_cands) else ""
        invoice_no = inv_cands[i_idx] if 0 <= i_idx < len(inv_cands) else ""
        date = date_cands[d_idx] if 0 <= d_idx < len(date_cands) else ""
        if 0 <= a_idx < len(amt_cands):
            total_val, total_cur, _ = amt_cands[a_idx]
            total = f"{total_val:.2f}"
            currency = cur or total_cur
        else:
            total=""; currency=cur

        rec = {
            "id": obj["id"], "variant":"C_LLM_SELECT",
            "latency_s": round(time.time()-t0,3), "success": success, "error": err,
            "pred": {"invoice_no": invoice_no, "date": date, "vendor": vendor, "total": total, "currency": currency}
        }
        OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False)+"\n")
        print(f"[LLM_SELECT] {obj['id']} -> {rec['pred']} err={err}")

if __name__ == "__main__":
    # chauffe
    try: requests.post(URL, json={"model":MODEL,"prompt":"{}","format":"json","stream":False}, timeout=(5,10))
    except: pass
    run()

