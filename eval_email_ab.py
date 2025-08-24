# eval_email_ab.py
import json
from pathlib import Path
from statistics import median

LABELS = ["spam","other"]

def load_jsonl(p: Path):
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8", errors="ignore").splitlines()]

def metrics(recs):
    n=len(recs)
    lat=[r["latency_s"] for r in recs] if n else []
    succ=[int(r["success"]) for r in recs] if n else []
    mean = sum(lat)/n if n else 0.0
    med  = median(lat) if n else 0.0
    ok   = sum(succ)/n if n else 0.0
    return n, mean, med, ok

def eval_cls(recs):
    y_true=[]; y_pred=[]
    for r in recs:
        gt = r.get("gt")
        pr = r.get("pred",{}).get("label")
        if gt in LABELS and pr in LABELS:
            y_true.append(gt); y_pred.append(pr)
    n=len(y_true)
    if n==0: return 0.0, 0.0
    acc = sum(int(a==b) for a,b in zip(y_true,y_pred))/n
    # macro F1 binaire
    from collections import Counter
    conf = {lab:{lab2:0 for lab2 in LABELS} for lab in LABELS}
    for t,p in zip(y_true,y_pred):
        conf[t][p]+=1
    f1s=[]
    for lab in LABELS:
        tp = conf[lab][lab]
        fp = sum(conf[x][lab] for x in LABELS if x!=lab)
        fn = sum(conf[lab][x] for x in LABELS if x!=lab)
        prec = tp/(tp+fp) if (tp+fp) else 0.0
        rec  = tp/(tp+fn) if (tp+fn) else 0.0
        f1   = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
        f1s.append(f1)
    macro_f1 = sum(f1s)/len(f1s)
    return acc, macro_f1

def show(name, recs):
    n, mean, med, ok = metrics(recs)
    acc, mf1 = eval_cls(recs)
    print(f"\n== {name} ==\n"
          f"n={n} | latence moyenne={mean:.3f}s | médiane={med:.3f}s | succès={ok:.1%}\n"
          f"Accuracy={acc:.1%} | Macro-F1={mf1:.3f}")

# ajoute en bas dans main()
def main():
    A = load_jsonl(Path("results_email/results_rules.jsonl"))
    B = load_jsonl(Path("results_email/results_llm.jsonl"))
    C = load_jsonl(Path("results_email/results_hybrid.jsonl"))
    show("A_RULES", A)
    show("B_LLM", B)
    show("C_HYBRID", C)


if __name__ == "__main__":
    main()


