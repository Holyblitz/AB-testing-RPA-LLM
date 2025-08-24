# annotate_invoices_gt.py — GT manuelle avec suggestions rapides
import json, re
from pathlib import Path

IN = Path("data/fatura_subset/items.jsonl")
OUT = Path("data/fatura_subset/manual_gt.jsonl")
N = 20

CUR_PAT = r"(€|eur|euro|\$|usd|£|gbp)"
AMT_PAT = r"(?<!\w)(\d{1,3}(?:[ .,\u00A0]\d{3})*(?:[.,]\d{2})?)(?!\w)"
DATE_PATS = [
    r"\b(\d{4}-\d{2}-\d{2})\b",            # 2024-06-12
    r"\b(\d{2}/\d{2}/\d{4})\b",            # 12/06/2024
    r"\b(\d{2}-\d{2}-\d{4})\b",            # 12-06-2024
    r"\b(\d{1,2}\s+[A-Za-zéûôîà]+\.?\s+\d{2,4})\b",  # 12 juin 2024 / 12 June 2024
]

def suggest(text: str):
    # invoice number
    m_inv = re.search(r"(?:invoice|facture|inv)[^\n]{0,20}(?:no|n[°o]|#|num(?:éro)?)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/\.]{2,})",
                      text, flags=re.I)
    invoice_no = m_inv.group(1) if m_inv else ""

    # date
    date = ""
    for pat in DATE_PATS:
        m = re.search(pat, text, flags=re.I)
        if m: date = m.group(1); break

    # total & currency (prend le plus grand montant)
    best = (0.0, "", "")
    for m in re.finditer(AMT_PAT, text):
        seg = m.group(0)
        cur = ""
        mcur = re.search(CUR_PAT, seg, flags=re.I)
        if mcur:
            cur = mcur.group(1).upper().replace("€","EUR").replace("$","USD").replace("£","GBP")
        # normalise
        val = seg
        if val.count(",")==1 and val.count(".")==0:
            val = val.replace(" ","").replace("\u00A0","").replace(".","").replace(",",".")
        else:
            val = val.replace(" ","").replace("\u00A0","").replace(",","")
        try:
            f = float(val)
            if f > best[0]: best = (f, f"{f:.2f}", cur)
        except:
            pass
    total, currency = best[1], best[2]

    # vendor: une des premières lignes non chiffrées
    vendor = ""
    for line in text.splitlines()[:15]:
        line = line.strip()
        if len(line) >= 5 and not re.search(AMT_PAT, line):
            vendor = line; break

    return {"invoice_no": invoice_no, "date": date, "vendor": vendor, "total": total, "currency": currency}

def ask(label, default=""):
    val = input(f"{label} [{default}]: ").strip()
    return val if val else default

def main():
    OUT.write_text("", encoding="utf-8")
    rows = [json.loads(l) for l in IN.read_text(encoding="utf-8").splitlines()]
    for i, obj in enumerate(rows[:N], 1):
        text = obj.get("text","")
        print("\n" + "="*60)
        print(f"{i}/{N}  id={obj['id']}")
        print("-"*60)
        print((text[:1200] + ("..." if len(text) > 1200 else "")))

        # suggestions à partir du texte
        sug = suggest(text)
        gt_old = obj.get("gt", {})  # si tu veux garder la valeur existante comme base
        # priorité aux suggestions; si vides, on met l'ancienne GT
        defv = lambda k: sug.get(k) or gt_old.get(k,"")

        inv = ask("invoice_no", defv("invoice_no"))
        dat = ask("date",       defv("date"))
        ven = ask("vendor",     defv("vendor"))
        tot = ask("total",      defv("total"))
        cur = ask("currency",   defv("currency"))

        OUT.open("a", encoding="utf-8").write(json.dumps(
            {"id": obj["id"], "gt": {"invoice_no":inv,"date":dat,"vendor":ven,"total":tot,"currency":cur}},
            ensure_ascii=False
        ) + "\n")
    print(f"✅ GT manuelle écrite: {OUT}\nAstuce: Entrée = accepter la suggestion.")
if __name__ == "__main__":
    main()
