#!/usr/bin/env python3
"""Final offline analysis for the LLM Engagement Study.

Input: CSVs downloaded from Researcher > Exports.
Required: assignments_design.csv, conversation_turns.csv, participants_progress.csv
Output: final_session_metrics.csv, participant_condition_means.csv,
        personalization_effects.csv, statistical_tests.csv, big5_correlations.csv,
        descriptives.csv, analysis_metadata.txt

Semantic metrics are embedding-based proxies, not direct measures of human engagement.
"""
import argparse, json, math, re
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon, spearmanr
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
WINDOW = 3

def qflag(s):
    s=str(s or '').lower().strip(); qs=('what','why','how','when','where','which','who','would you','do you','did you','are you','can you')
    return ('?' in s) or any(s.startswith(q+' ') for q in qs)
def tokens(s): return max(1, round(len(str(s or '').split())*1.3))
def sim01(a,b): return float((np.dot(a,b)+1.0)/2.0)  # normalized embeddings

def bootstrap_ci(x, reps=5000, seed=1059667):
    x=np.asarray(x,float); x=x[np.isfinite(x)]
    if len(x)==0:return (np.nan,np.nan)
    rng=np.random.default_rng(seed); means=np.array([rng.choice(x,len(x),replace=True).mean() for _ in range(reps)])
    return tuple(np.quantile(means,[.025,.975]))

def rb_effect(d):
    d=np.asarray(d,float); d=d[np.isfinite(d) & (d!=0)]
    if not len(d): return 0.0
    ranks=pd.Series(np.abs(d)).rank(method='average').to_numpy(); pos=ranks[d>0].sum(); neg=ranks[d<0].sum()
    return float((pos-neg)/(pos+neg)) if pos+neg else 0.0

def paired_test(df, factor, a, b, label):
    p=df.groupby(['participant_id',factor])['engagement_score'].mean().unstack()
    if a not in p or b not in p:return {'comparison':label,'n':0,'W':np.nan,'p':np.nan,'rank_biserial':np.nan,'mean_difference':np.nan}
    z=p[[a,b]].dropna(); d=z[a]-z[b]
    if len(z)==0:return {'comparison':label,'n':0,'W':np.nan,'p':np.nan,'rank_biserial':np.nan,'mean_difference':np.nan}
    if np.allclose(d,0): W,pv=0.0,1.0
    else: W,pv=wilcoxon(z[a],z[b],zero_method='wilcox',alternative='two-sided')
    lo,hi=bootstrap_ci(d)
    return {'comparison':label,'n':len(z),'W':W,'p':pv,'rank_biserial':rb_effect(d),'mean_difference':d.mean(),'difference_ci95_low':lo,'difference_ci95_high':hi}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('export_dir'); ap.add_argument('--output-dir',default='final_analysis_output'); args=ap.parse_args()
    d=Path(args.export_dir); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    A=pd.read_csv(d/'assignments_design.csv'); T=pd.read_csv(d/'conversation_turns.csv'); P=pd.read_csv(d/'participants_progress.csv')
    A=A[A['status'].astype(str).str.lower().eq('complete')].copy(); T=T[T['session_id'].isin(A.session_id)].copy()
    model=SentenceTransformer(MODEL)
    rows=[]
    for _,a in A.sort_values(['participant_id','conversation_order']).iterrows():
        tt=T[T.session_id==a.session_id].sort_values('turn_index'); texts=[str(a.topic_prompt)]+tt.text.fillna('').astype(str).tolist()
        if len(texts)<2: continue
        V=model.encode(texts,normalize_embeddings=True,show_progress_bar=False); topic=V[0]; tv=V[1:]
        prev=[]; win=[]; tops=[]; nov=[]
        for i,v in enumerate(tv):
            tops.append(sim01(v,topic))
            if i:
                ps=sim01(v,tv[i-1]); prev.append(ps); nov.append(1-ps)
                c=np.mean(tv[max(0,i-WINDOW):i],axis=0); c=c/(np.linalg.norm(c) or 1); win.append(sim01(v,c))
        humans=tt[tt.speaker.astype(str).str.lower().eq('human')]; agents=tt[tt.speaker.astype(str).str.lower().eq('agent')]
        ht=sum(tokens(x) for x in humans.text); at=sum(tokens(x) for x in agents.text)
        coh=np.mean(prev) if prev else np.nan; wc=np.mean(win) if win else np.nan; tc=np.mean(tops) if tops else np.nan; novelty=np.mean(nov) if nov else np.nan
        tb=min(len(humans),len(agents))/max(1,max(len(humans),len(agents))); tokb=min(ht,at)/max(1,max(ht,at)); qr=np.mean([qflag(x) for x in tt.text])
        # Primary thesis composite specified for the study. Novelty is the semantic distance proxy available in the stored design.
        engagement=.25*coh+.20*wc+.20*tc+.15*novelty+.10*tb+.10*qr
        # Sensitivity analysis removes the non-discriminating turn-balance component and renormalizes remaining weights to sum to 1.
        sens=(.25*coh+.20*wc+.20*tc+.15*novelty+.10*qr)/.90
        rows.append(dict(session_id=a.session_id,participant_id=a.participant_id,conversation_order=a.conversation_order,latin_square_sequence=a.latin_square_sequence,condition_code=a.condition_code,condition_order=a.condition_order,conversation_within_condition=a.conversation_within_condition,topic_id=a.topic_id,variation_id=a.variation_id,topic_preference=a.topic_preference,model_size=a.model_size,model_name=a.model_name,personality_context_enabled=int(a.personality_context_enabled),coherence=coh,windowed_coherence=wc,topic_consistency=tc,novelty=novelty,turn_balance=tb,token_balance=tokb,question_rate=qr,engagement_score=engagement,engagement_sensitivity_no_turn_balance=sens))
    S=pd.DataFrame(rows); S.to_csv(out/'final_session_metrics.csv',index=False)
    metrics=['engagement_score','coherence','windowed_coherence','topic_consistency','novelty','turn_balance','token_balance','question_rate','engagement_sensitivity_no_turn_balance']
    desc=[]
    for m in metrics:
        x=S[m].dropna(); lo,hi=bootstrap_ci(x); desc.append(dict(metric=m,n=len(x),mean=x.mean(),median=x.median(),sd=x.std(ddof=1),ci95_low=lo,ci95_high=hi,min=x.min(),max=x.max()))
    pd.DataFrame(desc).to_csv(out/'descriptives.csv',index=False)
    tests=[paired_test(S,'model_size','medium','small','Medium vs small engagement'),paired_test(S,'personality_context_enabled',1,0,'Context vs no context engagement'),paired_test(S,'topic_preference','high','low','High vs low topic-interest engagement')]
    pd.DataFrame(tests).to_csv(out/'statistical_tests.csv',index=False)
    pcm=S.groupby(['participant_id','model_size','personality_context_enabled','topic_preference'],as_index=False)[metrics].mean(); pcm.to_csv(out/'participant_condition_means.csv',index=False)
    ctx=S.groupby(['participant_id','personality_context_enabled'])['engagement_score'].mean().unstack();
    if 1 in ctx and 0 in ctx: delta=(ctx[1]-ctx[0]).rename('personalization_delta').reset_index()
    else: delta=pd.DataFrame(columns=['participant_id','personalization_delta'])
    # Big Five + personalization effect
    big=[]
    for _,r in P.iterrows():
        try: scores=json.loads(r.get('big5_scores_json') or '{}')
        except Exception: scores={}
        item={'participant_id':r.participant_id}; item.update(scores); big.append(item)
    B=pd.DataFrame(big); D=delta.merge(B,on='participant_id',how='left'); D.to_csv(out/'personalization_effects.csv',index=False)
    cor=[]
    for trait in ['Extraversion','Agreeableness','Conscientiousness','Neuroticism','Openness']:
        if trait not in D: continue
        z=D[[trait,'personalization_delta']].dropna(); rho,pv=spearmanr(z[trait],z.personalization_delta) if len(z)>=3 else (np.nan,np.nan)
        cor.append(dict(trait=trait,outcome='personalization_delta',n=len(z),spearman_rho=rho,p=pv))
    pd.DataFrame(cor).to_csv(out/'big5_correlations.csv',index=False)
    (out/'analysis_metadata.txt').write_text(f'''Embedding model: {MODEL}\nWindow size: {WINDOW}\nCosine similarities transformed from [-1,1] to [0,1].\nSemantic measures are embedding-based operational proxies, not direct human engagement measures.\nPrimary tests use participant-level paired means (Wilcoxon signed-rank). Conversation rows are not treated as independent participants.\nBig Five analyses use Spearman correlations and are exploratory.\nIndividual-topic effects should be treated as exploratory because topic IDs are not equally represented within participants.\nPrimary composite: .25 coherence + .20 windowed coherence + .20 topic consistency + .15 novelty + .10 turn balance + .10 question rate.\nSensitivity composite removes turn balance and renormalizes the remaining weights by dividing by .90.\n''')
    print(f'Wrote final analysis to {out.resolve()}')
if __name__=='__main__': main()
