# fatura_prep_text_v2.py — subset robuste (50 items non vides)
import json, re, random
from pathlib import Path

ANN_ROOT = Path("data/fatura/invoices_dataset_final/Annotations")
CAND_DIRS = [
    ANN_ROOT / "Original_Format",
    ANN_ROOT / "layoutlm_HF_format",
    ANN_ROOT / "COCO_compatible_format",
]

OUT_DIR = Path("data/fatura_subset"); OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "items.jsonl"
N = 50

CUR_PAT = r"(€|eur|euro|\$|usd|£|gbp)"
AMT_PAT = r"(?<!\w)(\d{1,3}(?:[ .,\u00A0]\d{3})*(?:[.,]\d{2})?)(?!\w)"
DATE_PATS = [
    r"\b(\d{4}-\d{2}-\d{2})\b",
    r"\b(\d{2}/\d{2}/\d{4})\b",
    r"\b(\d{2}-\d{2}-\d{4})\b",
    r"\b(\d{1,2}\s+[A-Za-zéûôîà]+\.?\s+\d{2,4})\b",
]

def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None

def collect_strings(obj, bucket):
    """Collecte récursive de chaînes plausibles."""
    if isinstance(obj, str):
        s = obj.strip()
        if not s: return
        # on évite les très longues chaînes (base64, etc.)
        if len(s) > 2000: return
        # on évite manifestement des chemins/URLs
        if re.match(r"^[A-Za-z]:\\|^/?(home|usr|var|tmp)|^https?://", s): return
        # du vrai texte : contient lettres/chiffres/ponctuation
        if re.search(r"[A-Za-z0-9]", s):
            bucket.append(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_strings(v, bucket)
    elif isinstance(obj, list):
        for it in obj:
            collect_strings(it, bucket)

def build_fulltext(strings):
    # nettoie, déduplique (conservant l'ordre approx), et assemble
    clean = []
    seen = set()
    for s in strings:
        s2 = re.sub(r"[ \t]+", " ", s)
        s2 = re.sub(r"\n{3,}", "\n\n", s2).strip()
        if not s2: continue
        k = s2.lower()
        if k in seen: continue
        seen.add(k)
        clean.append(s2)
    # on préfère découper en lignes courtes
    lines=[]
    for s in clean:
        for ln in s.splitlines():
            ln = ln.strip()
            if ln:
                lines.append(ln)
    # garde un texte raisonnable
    text = "\n".join(lines)
    return text[:8000]

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

def pick_vendor(lines):
    for ln in lines[:15]:
        if len(ln) >= 5 and not re.search(AMT_PAT, ln):
            return ln
    return ""

def pick_total(lines):
    best = (0.0, "", "")
    for ln in lines:
        for m in re.finditer(AMT_PAT, ln):
            seg = m.group(0)
            val, cur = norm_amt(seg)
            if val:
                try:
                    f = float(val)
                    if f > best[0]:
                        best = (f, f"{f:.2f}", cur)
                except: pass
    return best[1], best[2]

def pick_invoice_no(text):
    m = re.search(r"(?:invoice|facture|inv)[^\n]{0,20}(?:no|n[°o]|#|num(?:éro)?)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-\/\.]{2,})",
                  text, flags=re.I)
    return m.group(1) if m else ""

def pick_date(text, lines):
    # 1) pattern explicite
    for pat in DATE_PATS:
        m = re.search(pat, text, flags=re.I)
        if m: return m.group(1)
    # 2) fallback : cherche "date" proche
    m = re.search(r"date\s*[:\-]?\s*(.+)", text, flags=re.I)
    if m:
        seg = m.group(1).split("\n")[0]
        for pat in DATE_PATS:
            m2 = re.search(pat, seg, flags=re.I)
            if m2: return m2.group(1)
    return ""

def iter_json_files():
    all_jsons=[]
    for d in CAND_DIRS:
        if d.exists():
            all_jsons.extend(d.rglob("*.json"))
    random.seed(42)
    random.shuffle(all_jsons)
    return all_jsons

def main():
    OUT.write_text("", encoding="utf-8")
    picked = 0
    skipped = 0
    for jp in iter_json_files():
        if picked >= N: break
        data = load_json(jp)
        if data is None:
            continue
        strings=[]
        collect_strings(data, strings)
        full = build_fulltext(strings)
        if not full or len(full.splitlines()) < 5:
            skipped += 1
            continue
        lines = full.splitlines()
        vendor = pick_vendor(lines)
        total, currency = pick_total(lines)
        invno = pick_invoice_no(full)
        date  = pick_date(full, lines)
        rec = {
            "id": str(jp.relative_to(ANN_ROOT.parent.parent)),  # depuis invoices_dataset_final/...
            "text": full,
            "gt": {
                "invoice_no": invno,
                "date": date,
                "vendor": vendor,
                "total": total,
                "currency": currency,
            }
        }
        OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
        picked += 1
        if picked % 10 == 0:
            print(f"... {picked} items écrits (skipped {skipped})")
    print(f"✅ Subset écrit: {OUT} | {picked} items (skipped {skipped})")

if __name__ == "__main__":
    main()

