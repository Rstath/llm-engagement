# Final offline analysis (recommended)

The Render dashboard is intentionally lightweight and labels its stored metrics **preliminary**. Do not use the server hash-based semantic metrics as the final thesis results.

## 1. Export from Researcher
Download at minimum:
- `participants_progress.csv`
- `assignments_design.csv`
- `conversation_turns.csv`

Also download the other CSVs as a complete backup.

## 2. Install locally
`pip install -r local_analysis_requirements.txt`

## 3. Run
Put the exported CSVs in one folder, e.g. `exports`, then:
`python local_final_analysis.py exports --output-dir final_analysis_output`

The first run downloads `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` and requires internet access. Later runs use the local model cache.

## Outputs
- `final_session_metrics.csv`: final semantic and composite metrics per conversation
- `participant_condition_means.csv`: participant-level condition means
- `statistical_tests.csv`: paired Wilcoxon tests, effect sizes, mean differences and bootstrap 95% CIs
- `personalization_effects.csv`: each participant's Context Yes − Context No engagement delta plus Big Five scores
- `big5_correlations.csv`: Spearman correlations between Big Five and personalization benefit
- `descriptives.csv`: descriptive statistics and bootstrap CIs
- `analysis_metadata.txt`: methods/version record for thesis reproducibility

## Interpretation
Sentence-Transformer cosine measures are **embedding-based operational proxies** for coherence/topic consistency/novelty, not direct measurements of subjective engagement. Questionnaire outcomes should be analyzed separately and compared with these automated proxies.

The primary composite is retained as specified. Because turn balance may be constant at 1.0, the script additionally reports a sensitivity composite without turn balance; this does not replace the primary outcome.
