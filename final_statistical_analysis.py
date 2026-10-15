#!/usr/bin/env python3
"""Transparent, exploratory repeated-measures analysis of the study CEI.
Do not mix synthetic/development records with genuine study participants.
"""
import argparse, json, re, warnings, shutil
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import wilcoxon

FACTORS=[('model_size','medium','small','Medium minus small'),('personality_context_enabled',1,0,'Context minus no context'),('topic_preference','high','low','High minus low interest')]
TERMS=['medium','context','high','medium:context','order_centered']

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--turns',default='conversation_turns.csv');ap.add_argument('--sessions',default='final_session_metrics.csv');ap.add_argument('--participants',default='participants_progress.csv')
 ap.add_argument('--bootstrap-reps',type=int,default=1000,help='Participant-cluster bootstrap resamples for cluster-robust OLS sensitivity')
 ap.add_argument('--bootstrap-seed',type=int,default=20261015)
 ap.add_argument('--questionnaires',default='condition_questionnaires.csv',help='Condition-level ratings export');ap.add_argument('--output-dir',default='results/final_statistics');ap.add_argument('--verified-real-ids',default=None,help='Optional CSV allowlist of participant IDs')
 a=ap.parse_args();out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
 # Remove only known obsolete outputs from earlier script versions, not user files.
 legacy=['MODEL_DIAGNOSTICS_INTERPRETATION.txt','METHODS_AND_INTERPRETATION.txt','paired_t_tests.csv','paired_assumption_checks.csv','five_traits_exploratory.csv','figure_paired_effects.png','figure_paired_effects.pdf','figure_paired_qq.png','figure_paired_qq.pdf','figure_topic_interest.png','figure_topic_interest.pdf']
 for filename in legacy:
  (out/filename).unlink(missing_ok=True)

 d=pd.read_csv(a.sessions);turns=pd.read_csv(a.turns);p=pd.read_csv(a.participants);verified=pd.read_csv(a.verified_real_ids) if a.verified_real_ids else None
 required=['session_id','participant_id','coherence','windowed_coherence','topic_consistency','model_size','personality_context_enabled','topic_preference','conversation_order']
 for name,df,cols in [('sessions',d,required),('turns',turns,['session_id','speaker','text']),('participants',p,['participant_id'])]:
  missing=set(cols)-set(df.columns)
  if missing:raise ValueError(f'{name} missing columns: {sorted(missing)}')
 if verified is not None and 'participant_id' not in verified:raise ValueError('Verified IDs file needs participant_id column')
 if verified is not None and verified.participant_id.duplicated().any():raise ValueError('Duplicate verified participant IDs')
 if d.session_id.duplicated().any():raise ValueError('Duplicate session IDs')
 if verified is not None:d=d[d.participant_id.isin(verified.participant_id)].copy()
 if d.empty:raise ValueError('No sessions to analyze')
 if not d.participant_id.isin(p.participant_id).all():raise ValueError('Some session participants are missing from participants_progress.csv')
 if d[required].isna().any().any():raise ValueError('Missing required session fields')
 if not d.model_size.isin(['medium','small']).all() or not d.topic_preference.isin(['high','low']).all():raise ValueError('Unexpected factor levels')
 context=pd.to_numeric(d.personality_context_enabled,errors='raise')
 if not context.isin([0,1]).all():raise ValueError('Context must be 0 or 1')
 h=turns[turns.speaker.astype(str).str.lower().str.strip().isin(['human','user','participant'])].copy()
 if h.empty:raise ValueError('No participant-authored turns')
 pattern=re.compile(r'\b(because|however|although|but|also|actually|for example|for instance|i think|i feel|i prefer|i would|in my opinion|personally|my experience)\b',re.I)
 def initiative(s):
  s=str(s);return int('?' in s or bool(re.match(r'^\s*(what|why|how|when|where|which|who|would you|do you|did you|are you|can you)\b',s,re.I)) or bool(pattern.search(s)))
 h['words']=h.text.fillna('').astype(str).map(lambda s:len(re.findall(r"\b[\w']+\b",s)))
 h['initiative']=h.text.fillna('').astype(str).map(initiative)
 beh=h.groupby('session_id').agg(mean_user_words=('words','mean'),user_initiative=('initiative','mean'),user_turn_count=('words','size')).reset_index()
 d=d.drop(columns=['mean_user_words','user_initiative','user_turn_count'],errors='ignore').merge(beh,on='session_id',validate='one_to_one',how='left')
 if d[['mean_user_words','user_initiative']].isna().any().any():raise ValueError('Missing human turns for scored sessions')
 d['user_participation']=1-np.exp(-d.mean_user_words/12)
 d['semantic_continuity']=d[['coherence','windowed_coherence','topic_consistency']].mean(axis=1)
 d['engagement_score']=.40*d.semantic_continuity+.35*d.user_participation+.25*d.user_initiative
 if not d.engagement_score.between(0,1).all():raise ValueError('CEI outside 0..1')
 d['medium']=(d.model_size=='medium').astype(int);d['context']=pd.to_numeric(d.personality_context_enabled).astype(int)
 d['high']=(d.topic_preference=='high').astype(int);d['order_centered']=pd.to_numeric(d.conversation_order)-pd.to_numeric(d.conversation_order).mean()
 d.to_csv(out/'sessions_with_engagement_scores.csv',index=False)
 formula='engagement_score ~ medium * context + high + order_centered'
 attempts=[];fit=None;method=None
 for optimizer in ['lbfgs','bfgs','powell','nm']:
  try:
   with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    candidate=smf.mixedlm(formula,d,groups=d.participant_id,re_formula='1+medium').fit(reml=False,method=optimizer,maxiter=1500,disp=False)
   rv=float(candidate.cov_re.iloc[0,0]);good=bool(candidate.converged and np.isfinite(candidate.params).all() and np.isfinite(candidate.cov_re.to_numpy()).all() and rv>=0)
   attempts.append({'optimizer':optimizer,'converged':good,'random_intercept_variance':rv,'random_slope_medium_variance':float(candidate.cov_re.loc['medium','medium']),'warnings':' | '.join(str(w.message) for w in caught)})
   if good and rv>1e-8:fit=candidate;method='MixedLM';break
  except Exception as e:attempts.append({'optimizer':optimizer,'converged':False,'warnings':str(e)})
 pd.DataFrame(attempts).to_csv(out/'mixedlm_fit_attempts.csv',index=False)
 rows=[]
 if fit is not None:
  ci=fit.conf_int()
  for term in TERMS:rows.append({'method':method,'term':term,'estimate':fit.params[term],'ci95_low':ci.loc[term,0],'ci95_high':ci.loc[term,1],'p':fit.pvalues[term]})
  resid=np.asarray(fit.resid);fitted=np.asarray(fit.fittedvalues)
  variance=float(fit.cov_re.iloc[0,0]);icc=np.nan # random slope makes a single constant ICC inappropriate
 else:
  resid=np.array([]);fitted=np.array([]);variance=np.nan;icc=np.nan
 ols=smf.ols(formula,d).fit(cov_type='cluster',cov_kwds={'groups':d.participant_id},use_t=True)
 ci=ols.conf_int()
 for term in TERMS:rows.append({'method':'Cluster-robust OLS (sensitivity; not MixedLM)','term':term,'estimate':ols.params[term],'ci95_low':ci.loc[term,0],'ci95_high':ci.loc[term,1],'p':ols.pvalues[term]})
 # Resample entire participants (not conversations) for a cluster bootstrap.
 # This is an OLS sensitivity analysis, NOT a bootstrap of the MixedLM estimator.
 # Use percentile intervals; with only 24 clusters, interpret coverage cautiously.
 if a.bootstrap_reps < 100:raise ValueError('--bootstrap-reps must be >=100')
 rng=np.random.default_rng(a.bootstrap_seed)
 ids=d.participant_id.unique()
 participant_data={pid:d[d.participant_id==pid] for pid in ids}
 boot=[];failures=0
 for b in range(a.bootstrap_reps):
  sampled=rng.choice(ids,size=len(ids),replace=True)
  db=pd.concat([participant_data[pid] for pid in sampled],ignore_index=True)
  try:
   model=smf.ols(formula,db).fit()
   if all(np.isfinite(model.params.get(t,np.nan)) for t in TERMS):
    boot.append({'replicate':b,**{t:float(model.params[t]) for t in TERMS}})
   else:failures+=1
  except (ValueError,np.linalg.LinAlgError):failures+=1
 boot_df=pd.DataFrame(boot)
 boot_df.to_csv(out/'cluster_bootstrap_replicates.csv',index=False)
 boot_summary=[]
 for t in TERMS:
  vals=boot_df[t].to_numpy() if t in boot_df else np.array([])
  boot_summary.append({'method':'Participant-cluster bootstrap of OLS (sensitivity)',
   'term':t,'full_sample_estimate':float(ols.params[t]),
   'ci95_low':float(np.percentile(vals,2.5)) if len(vals) else np.nan,
   'ci95_high':float(np.percentile(vals,97.5)) if len(vals) else np.nan,
   'bootstrap_se':float(np.std(vals,ddof=1)) if len(vals)>1 else np.nan,
   'successful_replicates':len(vals),'requested_replicates':a.bootstrap_reps,
   'failed_replicates':failures,'seed':a.bootstrap_seed})
 pd.DataFrame(boot_summary).to_csv(out/'cluster_bootstrap_summary.csv',index=False)
 # Leave-one-participant-out influence check for the SAME OLS estimator.
 # Compare coefficients to full-sample estimates; do not interpret these as independent tests.
 loo=[]
 for pid in ids:
  sub=d[d.participant_id!=pid]
  lm=smf.ols(formula,sub).fit()
  for t in TERMS:
   estimate=float(lm.params.get(t,np.nan))
   delta=estimate-float(ols.params[t])
   loo.append({'omitted_participant_id':pid,'term':t,
    'full_sample_estimate':float(ols.params[t]),'leave_one_out_estimate':estimate,
    'change_on_removal':delta,'absolute_change':abs(delta),
    'remaining_participants':sub.participant_id.nunique()})
 loo_df=pd.DataFrame(loo)
 loo_df.to_csv(out/'leave_one_participant_out.csv',index=False)
 loo_df.sort_values('absolute_change',ascending=False).groupby('term',sort=False).head(3).to_csv(out/'most_influential_participants.csv',index=False)
 pd.DataFrame(rows).to_csv(out/'model_estimates.csv',index=False)
 pd.DataFrame([{'n_participants':d.participant_id.nunique(),'n_conversations':len(d),'mixedlm_success':fit is not None,'random_intercept_variance':variance,'icc':icc,'formula':formula,'primary_random_effects':'participant random intercept + model-size random slope (1+medium)'}]).to_csv(out/'model_diagnostics.csv',index=False)
 contrasts=[];paired=[]
 for col,pos,neg,label in FACTORS:
  z=d.groupby(['participant_id',col]).engagement_score.mean().unstack().dropna(subset=[pos,neg]);diff=z[pos]-z[neg]
  for pid,value in diff.items():paired.append({'participant_id':pid,'comparison':label,'difference':value,'lower_mean':z.loc[pid,neg],'upper_mean':z.loc[pid,pos]})
  try:wp=float(wilcoxon(diff).pvalue) if len(diff)>=6 and (diff!=0).any() else np.nan
  except ValueError:wp=np.nan
  contrasts.append({'comparison':label,'n_participants':len(diff),'mean_difference':diff.mean(),'median_difference':diff.median(),'wilcoxon_p_exploratory':wp})
 pd.DataFrame(contrasts).to_csv(out/'paired_descriptives.csv',index=False);pd.DataFrame(paired).to_csv(out/'participant_paired_differences.csv',index=False)
 # Model-based interaction predictions; fixed-effects only, at centered order=0.
 predictions=[]
 if fit is not None:
  params=fit.params
  source='MixedLM'
 else:params=ols.params;source='Cluster-robust OLS sensitivity'
 for m in [0,1]:
  for c in [0,1]:
   predictions.append({'model_size':'medium' if m else 'small','context':c,'predicted_CEI':params['Intercept']+m*params['medium']+c*params['context']+m*c*params['medium:context']+0.5*params['high'],'source':source})
 pd.DataFrame(predictions).to_csv(out/'interaction_predictions.csv',index=False)
 (out/'METHODS_AND_LIMITATIONS.txt').write_text(f'''CEI = .40*semantic continuity + .35*user participation + .25*user initiative. This is a post-hoc, unvalidated behavioral proxy, NOT a validated subjective engagement scale. Report as exploratory unless weights and hypothesis were prospectively fixed.\n\nParticipants included: {d.participant_id.nunique()}; conversations: {len(d)}. Participant authenticity is researcher-confirmed, not independently verifiable by the script. Optional allowlist applied: {verified is not None}.\n\nPrimary specification: {formula} with participant random intercept AND model-size random slope (1+medium | participant). Random-intercept-only MixedLM and Gaussian GEE are sensitivity analyses. Both random-effects models may show covariance boundary warnings. MixedLM successful: {fit is not None}. A failed or boundary fit is NOT evidence of independent observations. Cluster-robust OLS is explicitly a sensitivity/fallback, not a mixed-effects result.\n\nThe context coefficient is the effect for the SMALL model; medium:context tests whether context effect differs by model. For medium model context effect, sum context and medium:context; use covariance for its CI.\n\nBootstrap sensitivity: {a.bootstrap_reps} participant-cluster resamples, seed={a.bootstrap_seed}, successful={len(boot)}, failed={failures}. The bootstrap and leave-one-participant-out analyses refit OLS, NOT MixedLM. Compare their estimates with the cluster-robust OLS rows in model_estimates.csv; do not label their intervals as MixedLM intervals. Percentile intervals may have imperfect coverage with only 24 participants. Large leave-one-out changes signal sensitivity, not grounds for excluding participants.\n\nQuestionnaire ratings must be analyzed separately using an appropriate ordinal or repeated-measures model; no questionnaire results are claimed here. Missingness, convergence, residual diagnostics and participant balance must be discussed. Do not infer population effects from synthetic participants.\n\nRelevant references: Baayen, Davidson & Bates (2008); Bates et al. (2015), lme4; Dragicevic (2016), Fair Statistical Communication in HCI; Kay, Nelson & Hekler (CHI 2016); O'Brien, Cairns & Hall (2018), User Engagement Scale.\n''',encoding='utf-8')
 # Consolidated diagnostics: warnings are retained, not suppressed from reporting.
 fit_attempts=pd.DataFrame(attempts)
 fit_warnings=' | '.join(fit_attempts.warnings.fillna('').astype(str).tolist())
 diagnostics={
 'participants':int(d.participant_id.nunique()),'conversations':int(len(d)),
 'model_formula':formula,'primary_random_effects':'(1+medium | participant)','mixedlm_converged':bool(fit is not None),
 'random_intercept_variance':variance,'icc':icc,
 'mixedlm_attempt_warnings':fit_warnings,
 'bootstrap_requested':int(a.bootstrap_reps),'bootstrap_successful':len(boot),'bootstrap_failed':failures,
 'cluster_robust_ols_role':'sensitivity only',
 'questionnaire_role':'separate participant-reported outcomes; 1-5 ordinal ratings',
 'caution':'Boundary/singular covariance warnings require caution even if optimizer converges; CEI is unvalidated and exploratory.'}
 (out/'MODEL_DIAGNOSTICS_REPORT.txt').write_text('\n'.join(f'{k}: {v}' for k,v in diagnostics.items())+'\n',encoding='utf-8')
 # Condition questionnaire ratings: one observation per participant × condition.
 qpath=Path(a.questionnaires)
 if qpath.is_file():
  q=pd.read_csv(qpath)
  need={'participant_id','condition_code','answers_json'}
  if not need.issubset(q.columns):raise ValueError(f'Questionnaires missing {need-set(q.columns)}')
  q=q[q.participant_id.isin(d.participant_id)].copy()
  if q.duplicated(['participant_id','condition_code']).any():
   raise ValueError('Duplicate participant × condition questionnaires; resolve before analysis')
  parsed=q.answers_json.map(json.loads)
  keys=['engagement','naturalness','responsiveness','coherence','topic_consistency','willingness_continue','overall_satisfaction']
  for key in keys:q[key]=pd.to_numeric(parsed.map(lambda x:x.get(key)),errors='coerce')
  q['model_size']=parsed.map(lambda x:x.get('model_size'))
  q['topic_interest']=parsed.map(lambda x:x.get('topic_interest'))
  q['personality_context_enabled']=parsed.map(lambda x:x.get('personality_context_enabled'))
  q['condition_order']=pd.to_numeric(q.condition_order,errors='coerce')
  for key in keys:
   if not q[key].dropna().between(1,5).all():raise ValueError(f'Invalid rating values in {key}')
  q['medium']=(q.model_size=='medium').astype(int)
  q['context']=q.personality_context_enabled.astype(int)
  q['high']=(q.topic_interest=='high').astype(int)
  q['order_centered']=q.condition_order-q.condition_order.mean()
  q['perceived_engagement']=q.engagement
  # Align the CEI average to the same participant-condition unit as the questionnaire.
  condition_cei=d.groupby(['participant_id','condition_code'],as_index=False).agg(mean_CEI=('engagement_score','mean'),n_conversations=('session_id','size'))
  q=q.merge(condition_cei,on=['participant_id','condition_code'],how='left',validate='one_to_one')
  if q.mean_CEI.isna().any():raise ValueError('Questionnaire conditions do not match scored sessions')
  q.to_csv(out/'questionnaire_condition_scores.csv',index=False)
  qrows=[]
  # Cluster-robust linear model is a transparent sensitivity model for ordinal ratings;
  # ordinal cumulative models with participant clustering should be considered for confirmation.
  for outcome in ['perceived_engagement','overall_satisfaction','naturalness','willingness_continue']:
   sub=q.dropna(subset=[outcome]).copy()
   if sub.participant_id.nunique()<6:continue
   qm=smf.ols(f'{outcome} ~ medium * context + high + order_centered',sub).fit(cov_type='cluster',cov_kwds={'groups':sub.participant_id},use_t=True)
   ciq=qm.conf_int()
   for term in TERMS:
    qrows.append({'outcome':outcome,'method':'Cluster-robust linear model (ordinal rating sensitivity)', 'term':term,'estimate':float(qm.params[term]),'ci95_low':float(ciq.loc[term,0]),'ci95_high':float(ciq.loc[term,1]),'p':float(qm.pvalues[term]),'participants':sub.participant_id.nunique(),'condition_ratings':len(sub)})
  pd.DataFrame(qrows).to_csv(out/'questionnaire_model_estimates.csv',index=False)
  assoc=[]
  from scipy.stats import spearmanr
  for outcome in ['perceived_engagement','overall_satisfaction','naturalness','willingness_continue']:
   sub=q.dropna(subset=[outcome,'mean_CEI'])
   rho,pval=spearmanr(sub.mean_CEI,sub[outcome])
   # Within-participant centered association, to reduce between-person response-style confounding.
   x=sub.mean_CEI-sub.groupby('participant_id').mean_CEI.transform('mean')
   y=sub[outcome]-sub.groupby('participant_id')[outcome].transform('mean')
   within=float(np.corrcoef(x,y)[0,1]) if x.std()>0 and y.std()>0 else np.nan
   assoc.append({'outcome':outcome,'spearman_rho_pooled':rho,'pooled_p_exploratory_not_cluster_adjusted':pval,'within_participant_centered_correlation':within,'n_condition_ratings':len(sub)})
  pd.DataFrame(assoc).to_csv(out/'questionnaire_CEI_associations.csv',index=False)
  (out/'QUESTIONNAIRE_INTERPRETATION.txt').write_text('Questionnaires are 1–5 ordinal participant-reported ratings collected once per condition (8 per participant), not once per conversation. Cluster-robust linear regression is a transparent sensitivity analysis; it is not an ordinal mixed-effects model. Pooled Spearman p-values ignore clustering and MUST NOT be used for confirmatory inference. Within-person centered correlation is descriptive. Report questionnaire results separately from CEI.\n',encoding='utf-8')
 else:
  print('WARNING: questionnaire file not found; questionnaire analysis skipped:',qpath)

 print('Completed:',len(d),'conversations from',d.participant_id.nunique(),'participants; MixedLM success:',fit is not None)
if __name__=='__main__':main()
