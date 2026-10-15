#!/usr/bin/env python3
"""Defense-ready plots from final_statistical_analysis.py output."""
import argparse
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt

def save(fig,out,name):
 fig.tight_layout();fig.savefig(out/(name+'.png'),dpi=240,bbox_inches='tight');fig.savefig(out/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--results-dir',default='results/final_statistics');ap.add_argument('--output-dir',default='results/thesis_plots');a=ap.parse_args()
 src=Path(a.results_dir);out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
 d=pd.read_csv(src/'sessions_with_engagement_scores.csv');est=pd.read_csv(src/'model_estimates.csv');paired=pd.read_csv(src/'participant_paired_differences.csv');pred=pd.read_csv(src/'interaction_predictions.csv')
 primary='MixedLM' if 'MixedLM' in set(est.method) else 'Cluster-robust OLS (sensitivity; not MixedLM)'
 e=est[(est.method==primary)&(est.term!='order_centered')].copy()
 labels={'medium':'Medium vs small','context':'Context (small model)','high':'High vs low topic interest','medium:context':'Model × context interaction'}
 fig,ax=plt.subplots(figsize=(9,4.7));y=np.arange(len(e));v=e.estimate.to_numpy();ax.errorbar(v,y,xerr=[v-e.ci95_low.to_numpy(),e.ci95_high.to_numpy()-v],fmt='o',capsize=5,color='#286a9c');ax.axvline(0,color='0.5',ls='--');ax.set_yticks(y,[labels.get(x,x) for x in e.term]);ax.invert_yaxis();ax.set_xlabel('Adjusted CEI difference (95% confidence interval)');ax.set_title('Adjusted experimental effects — '+primary);save(fig,out,'01_adjusted_effects')
 fig,ax=plt.subplots(figsize=(8,5));names=list(paired.comparison.unique());
 for i,name in enumerate(names):
  x=paired.loc[paired.comparison==name,'difference'].to_numpy();ax.scatter(x,np.full(len(x),i)+np.linspace(-.14,.14,len(x)),s=19,alpha=.55);ax.plot([np.mean(x)],[i],marker='D',markersize=9,color='black')
 ax.axvline(0,color='0.5',ls='--');ax.set_yticks(range(len(names)),names);ax.invert_yaxis();ax.set_xlabel('Within-participant CEI difference');ax.set_title('Participant differences (diamonds = mean)');save(fig,out,'02_participant_differences')
 fig,ax=plt.subplots(figsize=(7,4.8));
 for model,color in [('small','#286a9c'),('medium','#d18b36')]:
  q=pred[pred.model_size==model].sort_values('context');ax.plot(q.context,q.predicted_CEI,marker='o',label=model.capitalize(),color=color,lw=2)
 ax.set_xticks([0,1],['Disabled','Enabled']);ax.set_ylabel('Model-adjusted CEI (topic interest averaged)');ax.set_xlabel('Personality context');ax.set_title('Model size × personality context');ax.legend();save(fig,out,'03_model_context_interaction')
 fig,axes=plt.subplots(1,3,figsize=(12,4.4));factors=[('model_size','small','medium','Model size'),('personality_context_enabled',0,1,'Personality context'),('topic_preference','low','high','Topic interest')]
 for ax,(col,lo,hi,title) in zip(axes,factors):
  g=d.groupby(['participant_id',col]).engagement_score.mean().unstack().dropna(subset=[lo,hi]);means=[g[lo].mean(),g[hi].mean()];sems=[g[lo].sem(),g[hi].sem()]
  ax.bar([0,1],means,color=['#8aadc6','#d3a66c'],width=.6);ax.errorbar([0,1],means,yerr=[1.96*x for x in sems],fmt='none',ecolor='black',capsize=4);ax.set_xticks([0,1],[str(lo),str(hi)]);ax.set_title(f'{title} (n={len(g)})');ax.set_ylim(0,1)
 axes[0].set_ylabel('Mean participant CEI (±1.96 SE; descriptive)');fig.suptitle('Descriptive means — not adjusted model estimates');save(fig,out,'04_descriptive_bars')
 # Primary MixedLM intervals compared with cluster-bootstrap OLS sensitivity intervals.
 bs=src/'cluster_bootstrap_summary.csv'
 if bs.exists():
  b=pd.read_csv(bs); terms=['medium','context','high','medium:context']; labs=[labels[t] for t in terms]
  mm=est[(est.method==primary)&est.term.isin(terms)].set_index('term')
  bb=b.set_index('term'); fig,ax=plt.subplots(figsize=(10,5.2))
  for i,t in enumerate(terms):
   if t in mm.index:
    r=mm.loc[t];ax.errorbar(r.estimate,i-.13,xerr=[[r.estimate-r.ci95_low],[r.ci95_high-r.estimate]],fmt='o',capsize=4,color='#286a9c',label='MixedLM 95% CI' if i==0 else None)
   if t in bb.index:
    r=bb.loc[t];ax.errorbar(r.full_sample_estimate,i+.13,xerr=[[r.full_sample_estimate-r.ci95_low],[r.ci95_high-r.full_sample_estimate]],fmt='s',capsize=4,color='#c07d36',label='OLS cluster bootstrap 95% CI' if i==0 else None)
  ax.axvline(0,color='0.5',ls='--');ax.set_yticks(range(len(terms)),labs);ax.invert_yaxis();ax.set_xlabel('Adjusted CEI difference');ax.set_title('Primary model and participant-cluster bootstrap sensitivity');ax.legend();save(fig,out,'05_mixedlm_vs_bootstrap')
 loo=src/'leave_one_participant_out.csv'
 if loo.exists():
  l=pd.read_csv(loo); fig,axes=plt.subplots(1,2,figsize=(12,6),sharey=True)
  for ax,t in zip(axes,['medium','high']):
   z=l[l.term==t].sort_values('leave_one_out_estimate');ids=z.omitted_participant_id.astype(str).tolist();yy=np.arange(len(z))
   ax.scatter(z.leave_one_out_estimate,yy,s=25,color='#286a9c');ax.axvline(z.full_sample_estimate.iloc[0],ls='--',color='#c07d36',label='Full sample');ax.set_yticks(yy,[f'P{i+1:02d}' for i in range(len(z))]);ax.set_title(labels[t]);ax.set_xlabel('CEI coefficient after omission');ax.legend()
  fig.suptitle('Leave-one-participant-out influence (participant IDs anonymized)');save(fig,out,'06_participant_influence')
 qp=src/'questionnaire_condition_scores.csv'
 if qp.exists():
  q=pd.read_csv(qp); fig,axes=plt.subplots(1,2,figsize=(11,4.5))
  for ax,col,title in zip(axes,['engagement','overall_satisfaction'],['Perceived engagement','Overall satisfaction']):
   x=q.groupby(['participant_id','model_size'])[col].mean().unstack().dropna()
   if len(x):
    for _,r in x.iterrows():ax.plot([0,1],[r['small'],r['medium']],alpha=.22,color='#7f8995',lw=1)
    ax.scatter([0,1],[x.small.mean(),x.medium.mean()],color='#286a9c',s=70,zorder=4)
   ax.set_xticks([0,1],['Small','Medium']);ax.set_ylim(1,5);ax.set_ylabel('Participant rating (1–5)');ax.set_title(title)
  fig.suptitle('Questionnaire ratings by model size (paired participant means)');save(fig,out,'07_questionnaire_ratings')
  fig,ax=plt.subplots(figsize=(7,5));ax.scatter(q.mean_CEI,q.engagement,alpha=.45,s=26)
  ax.set_xlabel('Mean CEI within condition');ax.set_ylabel('Perceived engagement rating (1–5)');ax.set_title('Behavioral CEI versus participant-reported engagement');save(fig,out,'08_cei_vs_perceived_engagement')

 print('Saved plots to',out,'using',primary)
if __name__=='__main__':main()
