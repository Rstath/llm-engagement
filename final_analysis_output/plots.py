#!/usr/bin/env python3
"""
Expected inputs (filenames may include browser suffixes such as "(1)"):
  - final_session_metrics.csv
  - participant_condition_means.csv
  - personalization_effects.csv
  - statistical_tests.csv
  - descriptives.csv
  - big5_correlations.csv

Outputs:
  01_model_size_paired.png/.pdf
  02_personality_context_paired.png/.pdf
  03_topic_interest_paired.png/.pdf
  04_agreeableness_personalization.png/.pdf
  05_engagement_components.png/.pdf
  figure_captions_and_statistics.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ----------------------------- configuration -----------------------------

DISPLAY_DPI = 300
FIGSIZE_PAIRED = (6.4, 5.0)
FIGSIZE_SCATTER = (6.4, 5.0)
FIGSIZE_COMPONENTS = (7.4, 5.0)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10.5,
    "axes.titlesize": 12.5,
    "axes.labelsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9.5,
    "figure.titlesize": 13,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "savefig.bbox": "tight",
})


# ----------------------------- file helpers ------------------------------

def normalized_stem(path: Path) -> str:
    """Remove browser duplicate suffixes: file(1).csv -> file."""
    return re.sub(r"\s*\(\d+\)$", "", path.stem).lower()


def find_csv(folder: Path, expected_stem: str, required: bool = True) -> Path | None:
    matches = [
        p for p in folder.glob("*.csv")
        if normalized_stem(p) == expected_stem.lower()
    ]
    if not matches:
        if required:
            raise FileNotFoundError(
                f"Could not find {expected_stem}.csv in {folder.resolve()}"
            )
        return None

    # Prefer unsuffixed file, otherwise newest.
    exact = [p for p in matches if p.stem.lower() == expected_stem.lower()]
    return exact[0] if exact else max(matches, key=lambda p: p.stat().st_mtime)


def read_csv(folder: Path, stem: str, required: bool = True) -> pd.DataFrame | None:
    p = find_csv(folder, stem, required)
    return pd.read_csv(p) if p is not None else None


def require_columns(df: pd.DataFrame, columns: list[str], source: str):
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"{source} is missing required columns: {', '.join(missing)}\n"
            f"Available columns: {', '.join(map(str, df.columns))}"
        )


def choose_col(df: pd.DataFrame, candidates: list[str], source: str) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(
        f"Could not identify required column in {source}. "
        f"Tried: {candidates}. Available: {list(df.columns)}"
    )


def save_figure(fig, out_dir: Path, stem: str):
    png = out_dir / f"{stem}.png"
    pdf = out_dir / f"{stem}.pdf"
    fig.savefig(png, dpi=DISPLAY_DPI)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def clean_group_value(x) -> str:
    s = str(x).strip().lower()
    aliases = {
        "0": "no context", "false": "no context", "no": "no context",
        "1": "context", "true": "context", "yes": "context",
        "medium": "medium", "small": "small",
        "high": "high", "low": "low",
    }
    return aliases.get(s, s)


# --------------------------- statistics helpers --------------------------

def bootstrap_mean_ci(values, n_boot=10000, seed=20260921):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(n_boot, len(values)), replace=True)
    means = samples.mean(axis=1)
    return tuple(np.quantile(means, [0.025, 0.975]))


def spearman_simple(x, y):
    """Spearman rho using pandas ranks; p is read from analysis output if available."""
    x = pd.Series(x).rank(method="average")
    y = pd.Series(y).rank(method="average")
    return float(x.corr(y))


def format_p(p):
    if pd.isna(p):
        return "n/a"
    p = float(p)
    return "< .001" if p < .001 else f"= {p:.3f}".replace("0.", ".")


def find_test_row(tests: pd.DataFrame | None, keywords: list[str]):
    if tests is None or tests.empty:
        return None
    text_cols = [
        c for c in tests.columns
        if tests[c].dtype == "object" or pd.api.types.is_string_dtype(tests[c])
    ]
    for _, row in tests.iterrows():
        blob = " ".join(str(row[c]).lower() for c in text_cols)
        if all(k.lower() in blob for k in keywords):
            return row
    return None


def row_numeric(row, candidates):
    if row is None:
        return np.nan
    for c in candidates:
        if c in row.index:
            try:
                return float(row[c])
            except Exception:
                pass
    return np.nan


# ----------------------------- data shaping ------------------------------

def paired_from_metrics(metrics, participant_col, factor_col, score_col, left, right):
    tmp = metrics[[participant_col, factor_col, score_col]].copy()
    tmp[factor_col] = tmp[factor_col].map(clean_group_value)
    grouped = (
        tmp.groupby([participant_col, factor_col], as_index=False)[score_col]
        .mean()
    )
    wide = grouped.pivot(index=participant_col, columns=factor_col, values=score_col)
    if left not in wide.columns or right not in wide.columns:
        raise ValueError(
            f"Could not construct paired comparison {left!r} vs {right!r}. "
            f"Found factor values: {list(wide.columns)}"
        )
    return wide[[left, right]].dropna()


# ------------------------------- plotting -------------------------------

def paired_plot(wide, left, right, left_label, right_label, title, ylabel,
                test_row, out_dir, filename, caption_label):
    fig, ax = plt.subplots(figsize=FIGSIZE_PAIRED)

    x = np.array([0, 1])
    for _, row in wide.iterrows():
        ax.plot(x, [row[left], row[right]], marker="o", linewidth=0.9, alpha=0.45)

    means = np.array([wide[left].mean(), wide[right].mean()])
    sems = np.array([
        wide[left].std(ddof=1) / np.sqrt(len(wide)),
        wide[right].std(ddof=1) / np.sqrt(len(wide)),
    ])
    ax.errorbar(
        x, means, yerr=sems, marker="o", linewidth=2.8,
        capsize=4, label="Mean ± SE"
    )

    diffs = wide[right] - wide[left]
    ci_lo, ci_hi = bootstrap_mean_ci(diffs)

    p = row_numeric(test_row, ["p", "p_value", "pvalue"])
    w = row_numeric(test_row, ["statistic", "W", "w"])
    effect = row_numeric(
        test_row,
        ["rank_biserial", "rank_biserial_r", "effect", "effect_size"]
    )

    ax.set_xticks(x, [left_label, right_label])
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.20)
    ax.legend(frameon=False)

    annotation = (
        f"n = {len(wide)} paired participants\n"
        f"Mean Δ ({right_label} − {left_label}) = {diffs.mean():.4f}\n"
        f"Bootstrap 95% CI [{ci_lo:.4f}, {ci_hi:.4f}]"
    )
    if np.isfinite(p):
        annotation += f"\nWilcoxon p {format_p(p)}"
    ax.text(
        0.02, 0.98, annotation,
        transform=ax.transAxes, va="top", ha="left",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.85, edgecolor="0.8")
    )

    fig.tight_layout()
    save_figure(fig, out_dir, filename)

    stat_parts = [
        f"{caption_label}. Participant-level paired engagement scores.",
        f"{right_label} M={wide[right].mean():.4f}; {left_label} M={wide[left].mean():.4f}.",
        f"Paired mean difference ({right_label} − {left_label})={diffs.mean():.4f}, "
        f"bootstrap 95% CI [{ci_lo:.4f}, {ci_hi:.4f}].",
    ]
    if np.isfinite(w):
        stat_parts.append(f"Wilcoxon W={w:.3f}.")
    if np.isfinite(p):
        stat_parts.append(f"p {format_p(p)}.")
    if np.isfinite(effect):
        stat_parts.append(f"Rank-biserial effect={effect:.3f}.")
    stat_parts.append(
        "Thin lines represent individual participants; the heavier line represents the group mean ± SE."
    )
    return " ".join(stat_parts)


def personalization_plot(personal, big5, out_dir):
    # Resolve participant and delta columns.
    pid_p = choose_col(
        personal,
        ["participant_id", "participant", "participant_code", "code"],
        "personalization_effects.csv"
    )
    delta_col = choose_col(
        personal,
        ["personalization_delta", "delta_engagement", "context_minus_no_context",
         "personalization_effect", "delta"],
        "personalization_effects.csv"
    )

    # Agreeableness may already be included in personalization_effects.
    agree_candidates = ["Agreeableness", "agreeableness", "big5_agreeableness"]
    agree_col = next((c for c in agree_candidates if c in personal.columns), None)

    if agree_col is not None:
        plot_df = personal[[pid_p, agree_col, delta_col]].dropna().copy()
    else:
        if big5 is None:
            raise ValueError(
                "Agreeableness is not in personalization_effects.csv and "
                "big5_correlations.csv cannot supply participant-level scores. "
                "Use a personalization_effects.csv containing Agreeableness."
            )
        raise ValueError(
            "personalization_effects.csv must contain participant-level Agreeableness "
            "scores for Figure 4."
        )

    x = plot_df[agree_col].astype(float).to_numpy()
    y = plot_df[delta_col].astype(float).to_numpy()
    rho = spearman_simple(x, y)

    # Read the final Spearman p-value if available.
    p = np.nan
    if big5 is not None and not big5.empty:
        trait_col = next(
            (c for c in ["trait", "Trait", "big5_trait"] if c in big5.columns),
            None
        )
        if trait_col:
            row = big5[
                big5[trait_col].astype(str).str.lower().eq("agreeableness")
            ]
            if not row.empty:
                pcol = next((c for c in ["p", "p_value", "pvalue"] if c in row.columns), None)
                if pcol:
                    p = float(row.iloc[0][pcol])

    fig, ax = plt.subplots(figsize=FIGSIZE_SCATTER)
    ax.scatter(x, y, s=45, alpha=0.80)
    ax.axhline(0, linestyle="--", linewidth=1.1, alpha=0.75)

    # Linear trend is visual guidance only; inference remains Spearman.
    if len(plot_df) >= 2 and np.unique(x).size >= 2:
        slope, intercept = np.polyfit(x, y, 1)
        xx = np.linspace(np.min(x), np.max(x), 100)
        ax.plot(xx, slope * xx + intercept, linewidth=1.6, alpha=0.75)

    ax.set_xlabel("Agreeableness score")
    ax.set_ylabel("Personalization effect\n(Context − No context engagement)")
    ax.set_title("Agreeableness and personalization benefit")
    ax.grid(alpha=0.18)

    text = f"n = {len(plot_df)}\nSpearman ρ = {rho:.3f}"
    if np.isfinite(p):
        text += f"\np {format_p(p)}"
    ax.text(
        0.02, 0.98, text,
        transform=ax.transAxes, va="top", ha="left",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.85, edgecolor="0.8")
    )

    fig.tight_layout()
    save_figure(fig, out_dir, "04_agreeableness_personalization")

    caption = (
        "Figure 4. Exploratory relationship between Agreeableness and the participant-level "
        "personalization effect (mean engagement with personality context minus mean engagement "
        f"without context), n={len(plot_df)}, Spearman ρ={rho:.3f}"
    )
    if np.isfinite(p):
        caption += f", p {format_p(p)}"
    caption += (
        ". Positive values indicate greater engagement under personality-aware context. "
        "The fitted line is descriptive; inference is based on Spearman rank correlation."
    )
    return caption


def components_plot(metrics, out_dir):
    candidates = [
        ("coherence", "Coherence"),
        ("windowed_coherence", "Windowed\ncoherence"),
        ("topic_consistency", "Topic\nconsistency"),
        ("novelty", "Novelty"),
        ("question_rate", "Question\nrate"),
    ]
    available = [(c, label) for c, label in candidates if c in metrics.columns]
    if len(available) < 3:
        raise ValueError(
            "final_session_metrics.csv does not contain enough component columns. "
            f"Available columns: {list(metrics.columns)}"
        )

    cols = [c for c, _ in available]
    labels = [label for _, label in available]
    means = metrics[cols].mean()
    ses = metrics[cols].std(ddof=1) / np.sqrt(len(metrics))

    fig, ax = plt.subplots(figsize=FIGSIZE_COMPONENTS)
    x = np.arange(len(cols))
    ax.bar(x, means.values, yerr=ses.values, capsize=4, alpha=0.82)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Mean score")
    ax.set_title("Embedding-derived conversation metrics")
    ax.set_ylim(0, 1)
    ax.grid(axis="y", alpha=0.20)

    for i, value in enumerate(means.values):
        ax.text(i, value + 0.025, f"{value:.3f}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    save_figure(fig, out_dir, "05_engagement_components")

    summary = "; ".join(f"{label.replace(chr(10), ' ')} M={means[c]:.3f}"
                        for c, label in available)
    return (
        "Figure 5. Descriptive means of the embedding-derived conversation components "
        f"across {len(metrics)} conversations: {summary}. Error bars represent SE. "
        "Turn balance is intentionally omitted because it is invariant (1.000) and therefore "
        "does not discriminate between conversations. These semantic measures are operational "
        "embedding-based proxies rather than direct human engagement measures."
    )


# --------------------------------- main ----------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate five final thesis figures.")
    parser.add_argument(
        "input_dir", nargs="?", default=".",
        help="Folder containing final analysis CSV files (default: current folder)."
    )
    parser.add_argument(
        "--output-dir", default="thesis_figures",
        help="Output folder for PNG/PDF figures and caption summary."
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = read_csv(input_dir, "final_session_metrics")
    tests = read_csv(input_dir, "statistical_tests", required=False)
    personal = read_csv(input_dir, "personalization_effects")
    big5 = read_csv(input_dir, "big5_correlations", required=False)

    participant_col = choose_col(
        metrics,
        ["participant_id", "participant", "participant_code", "code"],
        "final_session_metrics.csv"
    )
    score_col = choose_col(
        metrics,
        ["engagement_score", "engagement", "primary_engagement"],
        "final_session_metrics.csv"
    )

    model_col = choose_col(
        metrics, ["model_size", "model", "llm_size"], "final_session_metrics.csv"
    )
    context_col = choose_col(
        metrics,
        ["personality_context_enabled", "context", "context_flag", "personality_context"],
        "final_session_metrics.csv"
    )
    interest_col = choose_col(
        metrics,
        ["topic_preference", "topic_interest", "interest", "interest_level"],
        "final_session_metrics.csv"
    )

    # 1. Model size
    model = paired_from_metrics(
        metrics, participant_col, model_col, score_col, "small", "medium"
    )
    model_test = find_test_row(tests, ["medium", "small"])
    if model_test is None:
        model_test = find_test_row(tests, ["model"])
    captions = []
    captions.append(paired_plot(
        model, "small", "medium", "Small", "Medium",
        "Participant-level engagement by LLM size",
        "Engagement score", model_test, out_dir,
        "01_model_size_paired", "Figure 1"
    ))

    # 2. Context
    context = paired_from_metrics(
        metrics, participant_col, context_col, score_col, "no context", "context"
    )
    context_test = find_test_row(tests, ["context", "no context"])
    if context_test is None:
        context_test = find_test_row(tests, ["context"])
    captions.append(paired_plot(
        context, "no context", "context", "No context", "Context",
        "Participant-level engagement by personality context",
        "Engagement score", context_test, out_dir,
        "02_personality_context_paired", "Figure 2"
    ))

    # 3. Topic interest
    interest = paired_from_metrics(
        metrics, participant_col, interest_col, score_col, "low", "high"
    )
    interest_test = find_test_row(tests, ["high", "low"])
    if interest_test is None:
        interest_test = find_test_row(tests, ["interest"])
    captions.append(paired_plot(
        interest, "low", "high", "Low interest", "High interest",
        "Participant-level engagement by topic interest",
        "Engagement score", interest_test, out_dir,
        "03_topic_interest_paired", "Figure 3"
    ))

    # 4. Agreeableness x personalization benefit
    captions.append(personalization_plot(personal, big5, out_dir))

    # 5. Component means
    captions.append(components_plot(metrics, out_dir))

    summary_path = out_dir / "figure_captions_and_statistics.txt"
    header = (
        "THESIS FIGURE CAPTIONS AND STATISTICAL SUMMARIES\n"
        "================================================\n\n"
        "Primary analysis unit: participant for paired inferential comparisons.\n"
        "Conversation rows are used descriptively for embedding-derived component summaries.\n"
        "Embedding model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2\n\n"
    )
    summary_path.write_text(
        header + "\n\n".join(captions) + "\n",
        encoding="utf-8"
    )

    print(f"Created thesis figures in: {out_dir.resolve()}")
    for stem in [
        "01_model_size_paired",
        "02_personality_context_paired",
        "03_topic_interest_paired",
        "04_agreeableness_personalization",
        "05_engagement_components",
    ]:
        print(f"  {stem}.png")
        print(f"  {stem}.pdf")
    print(f"  {summary_path.name}")


if __name__ == "__main__":
    main()
