# label_emails.py
# Usage: python3 label_emails.py
from pathlib import Path
import re, sys

LABELS = ["invoice","job","support","sales","newsletter","spam","other"]
IN_DIR = Path("data/emails")

def read_preview(p: Path, n=20):
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
        lines = [l for l in txt.splitlines() if l.strip()]
        return "\n".join(lines[:n])
    except Exception as e:
        return f"<error: {e}>"

def relabel(p: Path, new_label: str):
    name = p.name
    m = re.match(r"([a-zA-Z]+)__", name)
    if m:
        rest = name[len(m.group(1))+2:]
    else:
        rest = name
    new_name = f"{new_label}__{rest}"
    p.rename(p.with_name(new_name))
    return new_name

def main():
    files = sorted(IN_DIR.glob("*.txt"))
    print(f"{len(files)} files.")
    for p in files:
        print("\n" + "="*60)
        print(p.name)
        print("-"*60)
        print(read_preview(p))
        print("-"*60)
        print("Labels:", ", ".join(LABELS))
        choice = input("Label? [invoice/job/support/sales/newsletter/spam/other] (enter to keep): ").strip().lower()
        if choice and choice in LABELS:
            newn = relabel(p, choice)
            print(f"→ {newn}")
        else:
            print("→ unchanged")
    print("✅ labeling done.")

if __name__ == "__main__":
    main()

