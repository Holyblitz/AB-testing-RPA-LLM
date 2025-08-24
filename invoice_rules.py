# invoices_rules.py
import json, re, time
from pathlib import Path

IN = Path("data/fatura_subset/items.jsonl")
OUT = Path("results_invoice/rules.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

CUR_PAT = r"(€|eur|euro|\$|usd|£|gbp)"
AMT_PAT = r"(?<!\w)(\d{1,3}(?:[ .,\u00A0]\d{3})*(?:[.,]\d{2})?)(?!\w)"
DATE_PATS = [
    r"\b(\d{4}-\d{2}-\d{2})\b",
    r"\b(\d{2}/\d{2}/\d{4})\b",
    r"\b(\d{2}-\d{2}-\d{4})\b",
    r"\b(\d{1,2}\s+[A-Za-zéûôîà]+\.?\s+\d{2,4})\b",
]

def norm_amt(s):
    s = s.replace("\u00A0"," ").strip()
    cur = ""
    mcur = re.search(CUR_PAT, s, flags=re.I)
    if mcur: cur = mcur.group(1).upper().replace("€","EUR").replace("$","USD").replace("£","GBP")
    mam = re.search(AMT_PAT, s)
    if not mam: return "", cur
    raw = mam.group(1)
    if raw.count(",")==1 and raw.count(".")==0:
        val = raw.replace(" ","").replace("\u00A0","").replace(".","").replace(",",".")
    else:
        val = raw.replace(" ","").replace("\u00A0","").replace(",","")
    return val, cur

def extract_rules(text):
    # invoice_no
    m = re.search(r"(?:invoice|facture|inv)[^\n]{0,20}(?:no|n[°o]|#|num(?:éro)?)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/\.]{2,})", text, flags=re.I)
    invno = m.group(1) if m else ""
    # date
    date = ""
    for pat in DATE_PATS:
        m = re.search(pat, text, flags=re.I)
        if m: date = m.group(1); break
    # total + currency (prend le plus grand dans le doc)
    best = (0.0, "", "")
    for m in re.finditer(AMT_PAT, text):
        seg = m.group(0)
        val, cur = norm_amt(seg)
        if val:
            try:
                f = float(val)
                if f > best[0]:
                    best = (f, val, cur)
            except: pass
    total = best[1]; currency = best[2]
    # vendor: première ligne du doc (header) raisonnable
    vendor = ""
    for line in text.splitlines()[:15]:
        line = line.strip()
        if len(line) >= 5 and not re.search(AMT_PAT, line):
            vendor = line
            break
    return {"invoice_no": invno, "date": date, "vendor": vendor, "total": total, "currency": currency}

def main():
    OUT.write_text("", encoding="utf-8")
    for line in IN.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        t0 = time.time()
        pred = extract_rules(obj["text"])
        rec = {
            "id": obj["id"], "variant":"A_RULES_INV",
            "latency_s": round(time.time()-t0,3), "success": True, "error":"", "pred": pred
        }
        OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False)+"\n")
        print(f"[RULES] {obj['id']} -> {pred}")
    print(f"✅ Résultats: {OUT}")

if __name__ == "__main__":
    main()

