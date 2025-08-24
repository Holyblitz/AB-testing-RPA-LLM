# eval_ab.py
import json, statistics as stats, csv, re
from pathlib import Path

def load_jsonl(p):
    out=[]
    for line in Path(p).read_text(encoding="utf-8").splitlines():
        out.append(json.loads(line))
    return out

def norm(s): 
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

def load_gt(p="data/gt.csv"):
    if not Path(p).exists(): return {}
    gt={}
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rid=row["id"]
            gt[rid]={
                "title":row.get("title",""),
                "company":row.get("company",""),
                "location":row.get("location",""),
                "salary":row.get("salary",""),
                "skills":[s.strip() for s in (row.get("skills","").split("|") if row.get("skills") else [])]
            }
    return gt

def exact_match(pred, gt):
    keys=["title","company","location","salary"]
    em = {k: int(norm(pred.get(k,""))==norm(gt.get(k,""))) for k in keys}
    # F1 micro simple pour skills
    ps=set([norm(x) for x in pred.get("skills",[]) if x])
    gs=set([norm(x) for x in gt.get("skills",[]) if x])
    tp=len(ps & gs); fp=len(ps-gs); fn=len(gs-ps)
    prec= tp/(tp+fp) if (tp+fp) else 0.0
    rec = tp/(tp+fn) if (tp+fn) else 0.0
    f1  = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    return em, f1

def summarize(recs, name, gt):
    n=len(recs)
    lat=[r["latency_s"] for r in recs]
    succ=[int(r["success"]) for r in recs]
    print(f"\n== {name} ==")
    print(f"n={n} | latence moyenne={sum(lat)/n:.3f}s | médiane={stats.median(lat):.3f}s | succès={sum(succ)/n:.1%}")
    if gt:
        em_all = {"title":[], "company":[], "location":[], "salary":[]}; f1s=[]
        for r in recs:
            gid=r["id"]; 
            if gid not in gt: continue
            em,f1 = exact_match(r["pred"], gt[gid])
            for k,v in em.items(): em_all[k].append(v)
            f1s.append(f1)
        if f1s:
            print("Exactitude : " + " | ".join([f"{k}={sum(v)/len(v):.1%}" for k,v in em_all.items()]))
            print(f"Skills F1 moyen = {sum(f1s)/len(f1s):.3f}")

def main():
    A=load_jsonl("results/results_rpa.jsonl")
    B=load_jsonl("results/results_llm.jsonl")
    gt=load_gt()
    summarize(A, "A_RPA", gt)
    summarize(B, "B_LLM", gt)

if __name__=="__main__":
    main()

