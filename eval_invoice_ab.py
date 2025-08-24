# eval_invoice_ab.py — évalue A (règles), B (LLM libre) et C (LLM sélecteur)
import os, json, re, datetime
from pathlib import Path
from statistics import median

# Ground truth : par défaut items.jsonl ; override possible avec env GT=path
GT_PATH = Path(os.getenv("GT", "data/fatura_subset/items.jsonl"))
A_PATH  = Path("results_invoice/rules.jsonl")        # A_RULES_INV
B_PATH  = Path("results_invoice/llm.jsonl")          # B_LLM_INV
C_PATH  = Path("results_invoice/llm_select.jsonl")   # C_LLM_SELECT

def load_jsonl(p: Path):
    if not p.exists(): return []
    txt = p.read_text(encoding="utf-8", errors="ignore").strip()
    if not txt: return []
    return [json.loads(l) for l in txt.splitlines()]

def to_map(rows):  # map id -> row
    return {r["id"]: r for r in rows if "id" in r}

def norm_invno(s: str) -> str:
    return re.sub(r"[\s]", "", (s or "")).upper()

def parse_date_any(s: str) -> str:
    s = (s or "").strip()
    if not s: return ""
    fmts = ["%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%d %B %Y","%d %b %Y"]
    for f in fmts:
        try:
            return datetime.datetime.strptime(s, f).date().isoformat()
        except Exception:
            pass
    m = re.search(r"(\d{1,2})\s+([A-Za-zéûôîà]+)\s+(\d{2,4})", s)
    if m:
        d, mo, y = m.groups()
        months = {
            "janvier":"01","février":"02","fevrier":"02","mars":"03","avril":"04","mai":"05","juin":"06","juillet":"07",
            "août":"08","aout":"08","septembre":"09","octobre":"10","novembre":"11","décembre":"12","decembre":"12",
            "january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07",
            "august":"08","september":"09","october":"10","november":"11","december":"12"
        }
        mo2 = months.get(mo.lower())
        if mo2:
            y = ("20"+y) if len(y)==2 else y
            try:
                return datetime.date(int(y), int(mo2), int(d)).isoformat()
            except Exception:
                pass
    return ""

def norm_amt(s: str) -> str:
    s = (s or "").replace("\u00A0"," ").strip()
    if not s: return ""
    if s.count(",")==1 and s.count(".")==0:
        val = s.replace(" ","").replace(".","").replace(",",".")
    else:
        val = s.replace(" ","").replace(",","")
    try:
        return f"{float(val):.2f}"
    except Exception:
        m = re.search(r"\d+(?:\.\d+)?", val)
        return m.group(0) if m else ""

def norm_cur(s: str) -> str:
    s=(s or "").upper()
    return {"€":"EUR","EUR":"EUR","$":"USD","USD":"USD","£":"GBP","GBP":"GBP"}.get(s, s)

FIELDS = ["invoice_no","date","vendor","total","currency"]

def compare(pred: dict, gt: dict) -> dict:
    return {
        "invoice_no": norm_invno(pred.get("invoice_no","")) == norm_invno(gt.get("invoice_no","")),
        "date":       parse_date_any(pred.get("date",""))    == parse_date_any(gt.get("date","")),
        "vendor":     (pred.get("vendor","").strip().lower() == gt.get("vendor","").strip().lower()),
        "total":      norm_amt(pred.get("total",""))         == norm_amt(gt.get("total","")),
        "currency":   norm_cur(pred.get("currency",""))      == norm_cur(gt.get("currency","")),
    }

def metrics(rows, gtmap):
    lat=[r.get("latency_s",0.0) for r in rows if r.get("success", True)]
    mean = sum(lat)/len(lat) if lat else 0.0
    med  = median(lat) if lat else 0.0
    per_field = {f:0 for f in FIELDS}; n=0; all_ok=0
    for r in rows:
        gid = r["id"]; pred = r.get("pred", {})
        gt = gtmap.get(gid, {}).get("gt", {})
        if not gt: continue
        res = compare(pred, gt)
        for f,v in res.items(): per_field[f]+= int(v)
        all_ok += int(all(res.values()))
        n += 1
    if n==0: return n, mean, med, per_field, 0.0
    for f in per_field: per_field[f] = per_field[f]/n
    return n, mean, med, per_field, all_ok/n

def show(name, rows, gt):
    if not rows:
        print(f"\n== {name} ==\n(absent ou vide)")
        return
    n, mean, med, per_field, exact = metrics(rows, gt)
    print(f"\n== {name} ==\n"
          f"n={n} | latence moyenne={mean:.3f}s | médiane={med:.3f}s\n"
          + "\n".join([f"- {k}: {v:.2%}" for k,v in per_field.items()]) +
          f"\n→ Exact-match (tous champs): {exact:.2%}")

def main():
    print(f"GT utilisée : {GT_PATH}")
    gt_map = to_map(load_jsonl(GT_PATH))
    rules  = load_jsonl(A_PATH)
    llm    = load_jsonl(B_PATH)
    select = load_jsonl(C_PATH)
    show("A_RULES_INV", rules, gt_map)
    show("B_LLM_INV",   llm,   gt_map)
    show("C_LLM_SELECT",select,gt_map)

if __name__ == "__main__":
    main()



