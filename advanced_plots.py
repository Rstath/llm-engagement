#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd,numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
ap=argparse.ArgumentParser();ap.add_argument('--results-dir',default='results/final_statistics');ap.add_argument('--output-dir',default='results/plots');a=ap.parse_args();src=Path(a.results_dir);out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
labels={'medium':'Medium vs small','context':'Personality context (small)','high':'High vs low interest','medium:context':'Model × context','order_centered':'Conversation order'}
def save(fig,name):
 fig.tight_layout();fig.savefig(out/(name+'.png'),dpi=220,bbox_inches='tight');fig.savefig(out/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
d=pd.read_csv(src/'cei_weight_component_sensitivity.csv');subset=d[d.term.isin(['medium','context','high','medium:context'])];outcomes=['cei_original','cei_equal','cei_semantic_heavy','cei_behavior_heavy'];fig,ax=plt.subplots(figsize=(10,6));y=0;yt=[];yl=[]
for o in outcomes:
 for term in ['medium','context','high','medium:context']:
  z=subset[(subset.outcome==o)&(subset.term==term)].iloc[0];ax.plot([z.bootstrap_ci_low,z.bootstrap_ci_high],[y,y],color='#39866f',lw=2);ax.plot(z.estimate,y,'o',color='#276d98');yt.append(y);yl.append(o.replace('cei_','').replace('_',' ')+' — '+labels[term]);y+=1
 y+=.65
ax.set_yticks(yt,yl,fontsize=8);ax.invert_yaxis();ax.axvline(0,ls='--',color='gray');ax.set_xlabel('Adjusted CEI difference and participant-cluster bootstrap 95% interval');ax.set_title('CEI weighting sensitivity — prespecified alternatives');save(fig,'09_cei_weight_sensitivity')
q=pd.read_csv(src/'ordinal_gee_questionnaire.csv');q=q[(q.outcome=='perceived_engagement') & q.term.isin(['medium','context','high','medium:context'])];fig,ax=plt.subplots(figsize=(8,4));y=np.arange(len(q));ax.errorbar(q.odds_ratio,y,xerr=[q.odds_ratio-q.ci95_low_or,q.ci95_high_or-q.odds_ratio],fmt='o',capsize=4,color='#286a9c');ax.axvline(1,ls='--',color='gray');ax.set_yticks(y,[labels[t] for t in q.term]);ax.invert_yaxis();ax.set_xlabel('Cumulative odds ratio (95% CI; participant-cluster robust)');ax.set_title('Perceived engagement: ordinal GEE');save(fig,'10_ordinal_perceived_engagement')
g=pd.read_csv(src/'gee_cei_sensitivity.csv');e=pd.read_csv(src/'model_estimates.csv');e=e[e.method=='MixedLM'];fig,ax=plt.subplots(figsize=(8,4.5));terms=['medium','context','high','medium:context'];
for i,t in enumerate(terms):
 for df,shift,color,name in [(e,-.11,'#286a9c','MixedLM'),(g,.11,'#bc8139','Gaussian GEE')]:
  z=df[df.term==t].iloc[0];ax.errorbar(z.estimate,i+shift,xerr=[[z.estimate-z.ci95_low],[z.ci95_high-z.estimate]],fmt='o',capsize=3,color=color,label=name if i==0 else None)
ax.set_yticks(range(len(terms)),[labels[t] for t in terms]);ax.invert_yaxis();ax.axvline(0,ls='--',color='gray');ax.legend();ax.set_xlabel('Adjusted CEI difference, model-based 95% CI');ax.set_title('MixedLM vs repeated-measures GEE');save(fig,'11_mixedlm_vs_gee')
print('Generated 3 advanced plots in',out)
