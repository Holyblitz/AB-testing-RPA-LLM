# rules_triage_csv.py
import re, csv, json, time
from pathlib import Path

CSV_PATH = Path("data/messages.csv")
N_MAX = 50
OUT = Path("results_email/results_rules.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

SPAM_PATTERNS = [
    r"\bviagra\b", r"\bcasino\b", r"\blottery\b", r"\bwin\s+\$?\d",
    r"\bfree\b", r"\bbulk\s+email\b", r"\bunsubscribe\b",
    r"\bcredit\b", r"\bmortgage\b", r"\bguaranteed\b", r"\bsex\b",
    r"\bwork\s+from\s+home\b", r"\bmake\s+\$?\d+(\,\d{3})?\b",
]

def classify_rules(text: str) -> str:
    t = text.lower()
    for p in SPAM_PATTERNS:
        if re.search(p, t): 
            return "spam"
    return "other"

def run():
    with CSV_PATH.open("r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= N_MAX: break
            subject = row.get("subject","") or ""
            message = row.get("message","") or ""
            label_num = row.get("label")
            gt = "spam" if str(label_num) == "1" else "other"

            text = f"Subject: {subject}\n\n{message}"
            t0 = time.time()
            pred = classify_rules(text)
            rec = {
                "id": f"row_{i:04d}",
                "variant": "A_RULES",
                "latency_s": round(time.time()-t0, 3),
                "success": True,
                "error": "",
                "gt": gt,
                "pred": {"label": pred}
            }
            OUT.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False)+"\n")
            print(f"[RULES] row_{i:04d} -> {pred} (gt={gt})")

if __name__ == "__main__":
    run()

