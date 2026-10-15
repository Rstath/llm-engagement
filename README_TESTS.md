# Tests & final thesis analysis README

## Structure
- `local_final_analysis.py`: offline Sentence-Transformer metrics; writes `final_analysis_output/`.
- `final_statistical_analysis.py`: primary CEI MixedLM and core sensitivity outputs.
- `advanced_sensitivity.py`: GEE, ordinal questionnaires, CEI weights and component sensitivity.
- `final_decisions_audit.py`: primary random-effects comparison, diagnostics and Holm correction.
- `threshold_specific_gee.py`: threshold-specific repeated-measures questionnaire analysis.
- `plots.py` and `advanced_plots.py`: figures in `results/plots/`.
- Root CSVs: original exports and inputs. `results/final_statistics/`: **selected** final result tables. `final_analysis_output/`: offline embedding results.

## Setup
```powershell
pip install -r local_analysis_requirements.txt
pip install numpy pandas scipy statsmodels patsy matplotlib
```
The first offline embedding run may download `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` and require internet.

## Run in order — ONE COMMAND PER LINE
```powershell
python local_final_analysis.py . --output-dir final_analysis_output
python final_statistical_analysis.py --turns conversation_turns.csv --sessions final_analysis_output/final_session_metrics.csv --participants participants_progress.csv --questionnaires condition_questionnaires.csv --output-dir results/final_statistics --bootstrap-reps 1000 --bootstrap-seed 20261015
python advanced_sensitivity.py --results-dir results/final_statistics --bootstrap-reps 1000 --seed 20261015
python final_decisions_audit.py --results-dir results/final_statistics
python threshold_specific_gee.py --results-dir results/final_statistics
python plots.py --results-dir results/final_statistics --output-dir results/plots
python advanced_plots.py --results-dir results/final_statistics --output-dir results/plots
```

## Statistical reporting decisions
- **Primary CEI model:** participant random intercept **plus random slope for model size**, with fixed effects `medium * context + high + order_centered` (ML estimation). Random-intercept MixedLM and Gaussian GEE are sensitivity checks. Boundary warnings must be reported.
- **Primary subjective outcome:** perceived engagement (ordinal 1–5) using participant-clustered cumulative-logit ordinal GEE. Threshold-specific binary GEE checks sensitivity to proportional-odds assumptions; do not claim the assumption is proven.
- **Primary testing family:** 4 contrasts (model size, high topic interest, context at small-model reference, model × context) × 2 outcomes = **8 tests**, with **retrospective Holm adjustment**. Secondary questionnaire outcomes receive separate Holm correction; interpret as exploratory.
- **CEI:** researcher-defined 40% semantic continuity, 35% user participation, 25% initiative. Alternative weights and component models test robustness, not validation. The CEI is an exploratory behavioral proxy, not a validated subjective engagement scale.
- **Design:** 24 participants contribute repeated observations; 384 conversations are not 384 independent participants. Participant-cluster bootstrap and leave-one-participant-out are supporting analyses. The bootstrap refits OLS, not MixedLM.

## Selected output tables
- `FINAL_primary_hypotheses_holm.csv`: corrected primary inference.
- `FINAL_random_effects_comparison.csv`, `FINAL_mixedlm_effects.csv`: mixed-effects selection and coefficients.
- `FINAL_threshold_specific_gee.csv`, `FINAL_threshold_slope_heterogeneity.csv`: ordinal threshold sensitivity.
- `cei_weight_component_sensitivity.csv`: CEI component and weighting robustness.
- `ordinal_gee_questionnaire.csv`: ordinal questionnaire models.
- `model_estimates.csv`, `model_diagnostics.csv`, `cluster_bootstrap_summary.csv`: main diagnostics and sensitivities.

The package intentionally omits redundant intermediate logs, preliminary server metrics, cached Python files and duplicate README documents. Running the scripts will regenerate some intermediate outputs; these are not required to remain under version control.
