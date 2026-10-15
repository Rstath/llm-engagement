import argparse, warnings
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

def main():
 p=argparse.ArgumentParser();p.add_argument('--results-dir',default='results/final_statistics');p.add_argument('--output-dir',default=None);a=p.parse_args();src=Path(a.results_dir);out=Path(a.output_dir or a.results_dir);out.mkdir(parents=True,exist_ok=True)
 d=pd.read_csv(src/'sessions_with_engagement_scores.csv');q=pd.read_csv(src/'questionnaire_condition_scores.csv')
 f='engagement_score ~ medium * context + high + order_centered'
 fits=[]; rows=[]
 for name,re in [('random_intercept','1'),('random_slope_medium','1+medium')]:
  for optimizer in ['lbfgs','powell']:
   try:
    with warnings.catch_warnings(record=True) as ws:
     warnings.simplefilter('always');m=smf.mixedlm(f,d,groups=d.participant_id,re_formula=re).fit(reml=False,method=optimizer,maxiter=800,disp=False)
    fits.append(dict(model=name,optimizer=optimizer,converged=m.converged,aic=m.aic,bic=m.bic,loglik=m.llf,random_covariance=str(m.cov_re.values.tolist()),warnings=' | '.join(str(w.message) for w in ws)))
    if optimizer=='lbfgs':
     for term in ['medium','context','high','medium:context','order_centered']:
      ci=m.conf_int().loc[term];rows.append(dict(model=name,term=term,estimate=m.params[term],ci_low=ci.iloc[0],ci_high=ci.iloc[1],p_asymptotic=m.pvalues[term]))
   except Exception as e:fits.append(dict(model=name,optimizer=optimizer,converged=False,warnings=str(e)))
 pd.DataFrame(fits).to_csv(out/'FINAL_random_effects_comparison.csv',index=False);pd.DataFrame(rows).to_csv(out/'FINAL_mixedlm_effects.csv',index=False)
 # Diagnostic for common slopes across cumulative rating thresholds: binary logits separately per cutoff.
 # This is an empirical check, not a formal proof of proportional odds or a small-cluster-corrected test.
 terms=['medium','context','high','medium:context','order_centered'];cutrows=[]
 y=q.perceived_engagement.astype(int)
 for cutoff in [1,2,3,4]:
  x=q.copy();x['above']=(y>cutoff).astype(int)
  if x.above.nunique()<2:continue
  try:
   fit=smf.gee('above ~ medium * context + high + order_centered',groups='participant_id',data=x,family=sm.families.Binomial(),cov_struct=sm.cov_struct.Exchangeable()).fit()
   for term in terms:
    ci=fit.conf_int().loc[term];cutrows.append(dict(cutoff=cutoff,term=term,log_odds=fit.params[term],ci_low=ci.iloc[0],ci_high=ci.iloc[1],p=fit.pvalues[term],n_above=int(x.above.sum())))
  except Exception as e:cutrows.append(dict(cutoff=cutoff,term='ERROR',error=str(e)))
 pd.DataFrame(cutrows).to_csv(out/'FINAL_proportional_odds_threshold_diagnostics.csv',index=False)
 # Main hypothesis family: four effects in CEI + four effects in subjective engagement, Holm across all eight.
 cei=pd.DataFrame(rows);cei=cei[cei.model=='random_slope_medium']
 ords=pd.read_csv(src/'ordinal_gee_questionnaire.csv');ords=ords[ords.outcome=='perceived_engagement']
 hypotheses=['medium','high','context','medium:context'];h=[]
 for t in hypotheses:
  r=cei[cei.term==t];
  if len(r):h.append(dict(outcome='CEI',term=t,p_raw=float(r.iloc[0].p_asymptotic),method='primary random-intercept + medium random-slope MixedLM; asymptotic'))
  r=ords[ords.term==t];
  if len(r):h.append(dict(outcome='perceived_engagement',term=t,p_raw=float(r.iloc[0].p_raw),method='ordinal GEE; asymptotic'))
 if len(h)==8:
  h=pd.DataFrame(h);h['p_holm_eight']=multipletests(h.p_raw,method='holm')[1];h.to_csv(out/'FINAL_primary_hypotheses_holm.csv',index=False)
 lines=['FINAL STATISTICAL DECISIONS','',f'Dataset: {d.participant_id.nunique()} participants, {len(d)} conversations; {q.participant_id.nunique()} questionnaire participants, {len(q)} ratings.','', '1. PRIMARY CEI MODEL: participant random intercept plus random slope for model size (medium), ML fit, fixed effects medium*context + high + order_centered. Random intercept only is a sensitivity comparator. Selection is based on design and AIC, not significance of individual effects. Inspect FINAL_random_effects_comparison.csv for boundary warnings and optimizer agreement.','', '2. ORDINAL PERCEIVED ENGAGEMENT: cumulative-logit ordinal GEE clustered by participant, with threshold-specific binary GEE estimates as a proportional-odds diagnostic. This is NOT a formal assumption validation. Materially varying cutoff-specific slopes, sparse cutoffs or poor fit require a partial proportional-odds / multinomial sensitivity model or a qualified interpretation. With 24 clusters asymptotic standard errors remain approximate.','', '3. MULTIPLICITY: define 4 experimental contrasts (model size, high vs low topic, context at small model, model-by-context) for BOTH primary outcomes CEI and perceived engagement: 8 primary tests, Holm-adjusted together at familywise alpha=.05. Order is a nuisance adjustment. Secondary questionnaire outcomes form a separate exploratory family with Holm correction; trait analyses and CEI weighting variants are exploratory sensitivity, not extra confirmatory tests.','', 'WARNING: if this primary family is defined after seeing results, call it a retrospective multiplicity sensitivity analysis, NOT preregistration.','', 'No test demonstrates the absence of a personality effect. No choice of model cures possible measurement validity, missingness, confounding or small sample limitations.']
 (out/'FINAL_STATISTICAL_DECISIONS.txt').write_text('\n'.join(lines),encoding='utf-8')
 print('\n'.join(lines[:9]));print('Files saved to',out)
if __name__=='__main__':main()
