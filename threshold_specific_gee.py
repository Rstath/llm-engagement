#!/usr/bin/env python3
"""Threshold-specific participant-clustered logistic GEE sensitivity for ordinal engagement.
Does not assume proportional odds. Uses cutoffs 2,3,4; cutoff 1 is near-degenerate.
Threshold-specific ORs are not a replacement for ordinal probabilities.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.genmod.cov_struct import Exchangeable, Independence

TERMS=['medium','context','high','medium:context','order_centered']

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--results-dir',default='results/final_statistics');ap.add_argument('--output-dir',default=None);a=ap.parse_args()
 root=Path(a.results_dir);out=Path(a.output_dir or root);out.mkdir(parents=True,exist_ok=True)
 q=pd.read_csv(root/'questionnaire_condition_scores.csv')
 q=q.dropna(subset=['perceived_engagement','medium','context','high','order_centered','participant_id']).copy()
 q['rating']=q.perceived_engagement.astype(int)
 if not q.rating.between(1,5).all():raise ValueError('Ratings outside 1-5')
 counts=q.rating.value_counts().sort_index();counts.rename_axis('rating').reset_index(name='n').to_csv(out/'FINAL_threshold_rating_distribution.csv',index=False)
 rows=[]; warnings=[]
 for cutoff in [1,2,3,4]:
  x=q.copy();x['above']=(x.rating>cutoff).astype(int)
  n_yes=int(x.above.sum());n_no=len(x)-n_yes
  if min(n_yes,n_no)<10:
   warnings.append(f'Cutoff {cutoff} excluded from interpretation: {n_yes} above, {n_no} at/below (sparse outcome).')
   continue
  for cov in [Exchangeable(),Independence()]:
   label=type(cov).__name__
   try:
    fit=smf.gee('above ~ medium * context + high + order_centered',groups='participant_id',data=x,family=sm.families.Binomial(),cov_struct=cov).fit(maxiter=200)
    for t in TERMS:
     ci=fit.conf_int().loc[t]
     rows.append(dict(cutoff=cutoff,working_correlation=label,term=t,log_odds=float(fit.params[t]),odds_ratio=float(np.exp(fit.params[t])),or_ci_low=float(np.exp(ci.iloc[0])),or_ci_high=float(np.exp(ci.iloc[1])),p_asymptotic=float(fit.pvalues[t]),n_above=n_yes,n_below_or_equal=n_no,n_participants=q.participant_id.nunique(),converged=bool(fit.converged)))
   except Exception as exc:warnings.append(f'Cutoff {cutoff}, {label}: {exc}')
 result=pd.DataFrame(rows);result.to_csv(out/'FINAL_threshold_specific_gee.csv',index=False)
 # Joint heterogeneity check: stack threshold binary responses and include all threshold-by-covariate interactions.
 # Cluster at participant, NOT at participant-threshold. The common slope is the reference threshold's slope.
 stacked=pd.concat([q.assign(cutoff=str(c),above=(q.rating>c).astype(int)) for c in [2,3,4]],ignore_index=True)
 formula='above ~ C(cutoff) * (medium + context + high + medium:context + order_centered)'
 try:
  fit=smf.gee(formula,groups='participant_id',data=stacked,family=sm.families.Binomial(),cov_struct=Independence()).fit(maxiter=250)
  names=list(fit.params.index);wald=[]
  for t in ['medium','high','context','medium:context','order_centered']:
   related=[n for n in names if 'C(cutoff)' in n and n.split(']:',1)[-1] == t]
   if not related:continue
   R=np.zeros((len(related),len(names)))
   for i,n in enumerate(related):R[i,names.index(n)]=1
   test=fit.wald_test(R,scalar=True)
   wald.append(dict(term=t,df=len(related),wald_chi2=float(test.statistic),p_asymptotic=float(test.pvalue),n_participants=q.participant_id.nunique(),method='Participant-cluster robust stacked threshold logistic GEE; working independence'))
  pd.DataFrame(wald).to_csv(out/'FINAL_threshold_slope_heterogeneity.csv',index=False)
 except Exception as exc:warnings.append('Stacked heterogeneity model failed: '+str(exc))
 lines=['THRESHOLD-SPECIFIC PERCEIVED ENGAGEMENT SENSITIVITY','',f'Participants: {q.participant_id.nunique()}; ratings: {len(q)}; ratings by category: {counts.to_dict()}.',
 'Binary outcomes: P(rating > 2), P(rating > 3), P(rating > 4). Cutoff 1 is omitted if sparse.',
 'Separate participant-clustered binomial GEEs with exchangeable and independence working correlation.',
 'Stacked participant-clustered GEE with threshold-by-covariate interactions tests slope heterogeneity (asymptotic Wald).',
 'These analyses RELAX proportional odds, but threshold-specific odds ratios are NOT equivalent to a single common ordinal odds ratio.',
 'Only 24 participant clusters: sandwich confidence intervals and Wald p-values are approximate and can be anti-conservative.',
 'This is a post-hoc sensitivity analysis, not an additional primary hypothesis family. Do not use threshold p-values to choose cutoffs.',
 'If a threshold-specific confidence interval crosses 1, report uncertainty at that threshold rather than claim universal significance.',
 'Original CEI random-intercept MixedLM is superseded as PRIMARY by participant random-intercept + model-size random-slope MixedLM; original intercept model is sensitivity.',
 'Eight primary tests (4 contrasts x CEI and perceived engagement) use retrospective Holm correction; threshold tests are diagnostic only.']
 if warnings:lines+=['','Warnings:']+warnings
 (out/'FINAL_THRESHOLD_INTERPRETATION.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print('Threshold sensitivity complete:',len(q),'ratings,',q.participant_id.nunique(),'participants; output',out)
 print(result[(result.working_correlation=='Exchangeable') & (result.term.isin(['medium','high']))][['cutoff','term','odds_ratio','or_ci_low','or_ci_high','p_asymptotic']].to_string(index=False))
if __name__=='__main__':main()
