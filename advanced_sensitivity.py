#!/usr/bin/env python3
"""Supplemental repeated-measures, ordinal, and CEI sensitivity analyses.
Run AFTER final_statistical_analysis.py; never selects weights based on significance.
"""
import argparse, json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.miscmodels.ordinal_model import OrderedModel
from statsmodels.stats.multitest import multipletests
from scipy.special import expit
TERMS=['medium','context','high','medium:context','order_centered']
FORM='medium * context + high + order_centered'

def cluster_fit(d,y):
    return smf.ols(f'{y} ~ {FORM}',d).fit(cov_type='cluster',cov_kwds={'groups':d.participant_id},use_t=True)

def bootstrap(d,y,reps,seed):
    rng=np.random.default_rng(seed); ids=d.participant_id.unique(); groups={pid:g for pid,g in d.groupby('participant_id')}; arr=[]
    for k in range(reps):
        sampled=rng.choice(ids,len(ids),replace=True)
        sample=pd.concat([groups[pid] for pid in sampled],ignore_index=True)
        try:arr.append(smf.ols(f'{y} ~ {FORM}',sample).fit().params.reindex(TERMS).to_numpy())
        except Exception:continue
    a=np.array(arr)
    return {t:(float(np.quantile(a[:,j],.025)),float(np.quantile(a[:,j],.975)),len(a)) for j,t in enumerate(TERMS)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--results-dir',default='results/final_statistics');ap.add_argument('--output-dir',default=None);ap.add_argument('--bootstrap-reps',type=int,default=1000);ap.add_argument('--seed',type=int,default=20261015);a=ap.parse_args()
    src=Path(a.results_dir);out=Path(a.output_dir or a.results_dir);out.mkdir(parents=True,exist_ok=True)
    d=pd.read_csv(src/'sessions_with_engagement_scores.csv');q=pd.read_csv(src/'questionnaire_condition_scores.csv')
    if d.participant_id.nunique()<8:raise ValueError('Insufficient participant clusters')
    # Participant-cluster robust model; inference uses participant rather than conversation as independent unit.
    # GEE Gaussian exchangeable is a population-average repeated-measures cross-check.
    import statsmodels.api as sm
    from statsmodels.genmod.cov_struct import Exchangeable
    diagnostics=[]
    for name,formula in [('random_intercept','engagement_score ~ '+FORM),('model_random_slope','engagement_score ~ '+FORM)]:
        re='1' if name=='random_intercept' else '1+medium'
        for opt in ['lbfgs','powell']:
            try:
                with warnings.catch_warnings(record=True) as ww:
                    warnings.simplefilter('always')
                    fit=smf.mixedlm(formula,d,groups=d.participant_id,re_formula=re).fit(reml=False,method=opt,maxiter=700,disp=False)
                diagnostics.append({'model':name,'optimizer':opt,'converged':bool(fit.converged),'log_likelihood':float(fit.llf),'aic':float(fit.aic),'random_covariance':str(fit.cov_re.values.tolist()),'warnings':' | '.join(str(w.message) for w in ww)})
            except Exception as e:diagnostics.append({'model':name,'optimizer':opt,'converged':False,'warnings':str(e)})
    pd.DataFrame(diagnostics).to_csv(out/'random_effects_diagnostics.csv',index=False)
    gee=smf.gee('engagement_score ~ '+FORM,groups='participant_id',data=d,family=sm.families.Gaussian(),cov_struct=Exchangeable()).fit()
    ci=gee.conf_int();pd.DataFrame([{'term':t,'estimate':gee.params[t],'ci95_low':ci.loc[t,0],'ci95_high':ci.loc[t,1],'p_asymptotic':gee.pvalues[t],'method':'Gaussian GEE exchangeable; asymptotic sandwich, 24 clusters'} for t in TERMS]).to_csv(out/'gee_cei_sensitivity.csv',index=False)
    # Predeclared alternatives, including components: avoid selecting formula by resulting p-values.
    d['cei_original']=d.engagement_score
    d['cei_equal']=(d.semantic_continuity+d.user_participation+d.user_initiative)/3
    d['cei_semantic_heavy']=.5*d.semantic_continuity+.25*d.user_participation+.25*d.user_initiative
    d['cei_behavior_heavy']=.25*d.semantic_continuity+.4*d.user_participation+.35*d.user_initiative
    outcomes=['cei_original','cei_equal','cei_semantic_heavy','cei_behavior_heavy','semantic_continuity','user_participation','user_initiative']
    rows=[]
    for idx,y in enumerate(outcomes):
        m=cluster_fit(d,y);ci=m.conf_int();bs=bootstrap(d,y,a.bootstrap_reps,a.seed+idx)
        for t in TERMS:
            lo,hi,n=bs[t]
            rows.append({'outcome':y,'term':t,'estimate':m.params[t],'cluster_t_p':m.pvalues[t],'cluster_t_ci_low':ci.loc[t,0],'cluster_t_ci_high':ci.loc[t,1],'bootstrap_ci_low':lo,'bootstrap_ci_high':hi,'bootstrap_successful':n})
    pd.DataFrame(rows).to_csv(out/'cei_weight_component_sensitivity.csv',index=False)
    # Ordinal GEE: repeated 1-5 ratings; cumulative logit with clustered participants.
    # statsmodels OrdinalGEE uses binary indicators for cumulative categories internally.
    from statsmodels.genmod.generalized_estimating_equations import OrdinalGEE
    outcomes_q=['perceived_engagement','overall_satisfaction','naturalness','willingness_continue']
    qr=[]; failures=[]
    for y in outcomes_q:
        sub=q.dropna(subset=[y,'medium','context','high','order_centered']).copy()
        try:
            import patsy
            X=patsy.dmatrix('0 + medium + context + high + medium:context + order_centered',sub,return_type='dataframe')
            # Fit ordinal GEE with robust clustered covariance.
            model=OrdinalGEE(sub[y].astype(int).to_numpy(),X,groups=sub.participant_id.to_numpy())
            fit=model.fit(maxiter=200)
            # exog includes threshold parameters added internally; slopes are final columns.
            param_names=list(fit.model.exog_names)
            ci=fit.conf_int()
            for j,t in enumerate(param_names):
                if t not in ['medium','context','high','medium:context','order_centered']:continue
                qr.append({'outcome':y,'term':t,'log_odds':float(fit.params.iloc[j]),'odds_ratio':float(np.exp(fit.params.iloc[j])),'ci95_low_or':float(np.exp(ci.iloc[j,0])),'ci95_high_or':float(np.exp(ci.iloc[j,1])),'p_raw':float(fit.pvalues.iloc[j]),'method':'Ordinal GEE cumulative logit, participant-cluster robust','n_participants':sub.participant_id.nunique(),'n_ratings':len(sub)})
        except Exception as e:failures.append({'outcome':y,'error':repr(e)})
    qr=pd.DataFrame(qr)
    if not qr.empty:
        # Holm correction separately for the prespecified secondary outcomes and their 4 condition effects.
        qr['p_holm_secondary']=np.nan
        mask=qr.outcome!='perceived_engagement'
        if mask.any():qr.loc[mask,'p_holm_secondary']=multipletests(qr.loc[mask,'p_raw'],method='holm')[1]
        qr.to_csv(out/'ordinal_gee_questionnaire.csv',index=False)
    pd.DataFrame(failures,columns=['outcome','error']).to_csv(out/'ordinal_gee_failures.csv',index=False)
    (out/'ADVANCED_METHODS_README.txt').write_text('Primary CEI: participant random-intercept plus model-size random-slope MixedLM (1+medium | participant) in final_statistical_analysis.py; random-intercept-only MixedLM is sensitivity, subject to convergence/boundary checks. Gaussian GEE is a population-averaged repeated-measures sensitivity model; with 24 clusters its sandwich p-values may be optimistic. Ordinal GEE fits cumulative logits for participant-clustered 1-5 questionnaire ratings, but is not an ordinal mixed-effects model. Proportional odds and small-cluster inference need consideration. Holm correction is applied to secondary outcome condition-effect family; primary perceived engagement is reported separately. CEI alternative weights are fixed in advance of this sensitivity analysis and MUST NOT be selected based on p-values. No causal interpretation of CEI-questionnaire association.\n',encoding='utf-8')
    print('Advanced sensitivity complete:',len(d),'conversations;',len(q),'ratings;',len(qr),'ordinal coefficients;',len(failures),'ordinal failures')
if __name__=='__main__':main()
