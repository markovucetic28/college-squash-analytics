"""Evaluate genuinely prospective production/shadow snapshots only."""
from pathlib import Path
import json, math, os, sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from college_squash.database import connect_database
from college_squash.shadow_evaluation import prospective_evaluation


def metrics(rows,column):
    if not rows:return {"matches":0,"accuracy":None,"log_loss":None,"brier":None,"ece":None}
    y=np.array([row["actual"] for row in rows]);p=np.clip([row[column] for row in rows],1e-12,1-1e-12)
    bins=np.minimum((p*10).astype(int),9);ece=sum((bins==i).mean()*abs(p[bins==i].mean()-y[bins==i].mean()) for i in set(bins))
    return {"matches":len(rows),"accuracy":float(((p>=.5)==y).mean()),"log_loss":float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),"brier":float(np.mean((p-y)**2)),"ece":float(ece)}


def comparison(rows):return {name:metrics(rows,name) for name in ["production","shadow"]}


def main():
    path=Path(os.environ.get("COLLEGE_SQUASH_DB",ROOT/"data/college_squash.db"));connection=connect_database(path);data=prospective_evaluation(connection);connection.close()
    individual=data["individual_rows"];teams=data["team_rows"]
    report={"authoritative_rule":"latest snapshot generated strictly before scheduled match time; no post-result snapshot","checkpoints":{"individual":[100,250,500,1000],"team":[25,50,100,250]},"current_samples":{"individual":len(individual),"team":len(teams)},"individual":{"overall":comparison(individual),"close":{f"under_{threshold:.2f}":comparison([row for row in individual if row.get("rating_gap") is not None and row["rating_gap"]<threshold]) for threshold in [.30,.20,.10]},"gender":{gender:comparison([row for row in individual if row["gender"]==gender]) for gender in ["men","women"]}},"team":{"overall":comparison(teams),"gender":{gender:comparison([row for row in teams if row["gender"]==gender]) for gender in ["men","women"]},"mode":{mode:comparison([row for row in teams if row["mode"]==mode]) for mode in ["verified","projected","preseason"]},"lineup_confidence":{label:comparison([row for row in teams if lower<=row["lineup_confidence"]<upper]) for label,lower,upper in [("low",0,.5),("medium",.5,.75),("high",.75,1.01)]}}}
    output=ROOT/"data/processed/shadow_evaluation";output.mkdir(parents=True,exist_ok=True);(output/"latest.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=="__main__":main()
