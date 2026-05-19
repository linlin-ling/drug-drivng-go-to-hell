"""Descriptive statistics and temporal trend analysis of drug-driving sentences."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


def descriptive_stats(df: pd.DataFrame) -> dict:
    """Overall and by-group descriptive statistics."""
    results = {}

    valid = df[df["effective_months"].notna()]

    # Overall
    m = valid["effective_months"]
    results["overall"] = {
        "count": int(len(valid)),
        "acquitted_count": int(df["acquitted"].sum()),
        "suspended_count": int(df["sentence_suspended"].sum()),
        "suspended_rate": float(df["sentence_suspended"].mean()),
        "mean": float(m.mean()),
        "median": float(m.median()),
        "std": float(m.std()),
        "min": float(m.min()),
        "max": float(m.max()),
        "q1": float(m.quantile(0.25)),
        "q3": float(m.quantile(0.75)),
    }

    # By drug class
    by_class = {}
    for cls, grp in valid.groupby("drug_class", dropna=True):
        m = grp["effective_months"]
        by_class[str(int(cls))] = {
            "count": int(len(grp)),
            "median": float(m.median()),
            "mean": float(m.mean()),
            "q1": float(m.quantile(0.25)),
            "q3": float(m.quantile(0.75)),
            "suspended_rate": float(grp["sentence_suspended"].mean()),
        }
    results["by_drug_class"] = by_class

    # By year
    by_year = {}
    for yr, grp in valid.groupby("year", dropna=True):
        m = grp["effective_months"]
        by_year[str(int(yr))] = {
            "count": int(len(grp)),
            "median": float(m.median()),
            "mean": float(m.mean()),
            "suspended_rate": float(grp["sentence_suspended"].mean()),
        }
    results["by_year"] = by_year

    # By severity
    by_severity = {}
    for sev, grp in valid.groupby("severity", dropna=True):
        m = grp["effective_months"]
        by_severity[sev] = {
            "count": int(len(grp)),
            "median": float(m.median()),
            "mean": float(m.mean()),
            "suspended_rate": float(grp["sentence_suspended"].mean()),
        }
    results["by_severity"] = by_severity

    return results


def temporal_trend(df: pd.DataFrame) -> dict:
    """Year-over-year trend with Mann-Kendall trend test."""
    valid = df[df["effective_months"].notna() & df["year"].notna()]
    yearly = (
        valid.groupby("year")["effective_months"]
        .agg(["median", "mean", "count", "std"])
        .reset_index()
    )
    yearly["suspended_rate"] = (
        df[df["year"].notna()]
        .groupby("year")["sentence_suspended"]
        .mean()
        .values[:len(yearly)]
    )

    # Mann-Kendall trend test (monotonic)
    medians = yearly["median"].values
    if len(medians) >= 4:
        tau, p_value = stats.kendalltau(range(len(medians)), medians)
    else:
        tau, p_value = float("nan"), float("nan")

    return {
        "yearly": yearly.to_dict(orient="records"),
        "mann_kendall_tau": float(tau),
        "mann_kendall_p": float(p_value),
        "trend": "上升" if tau > 0 and p_value < 0.05 else (
            "下降" if tau < 0 and p_value < 0.05 else "無顯著趨勢"
        ),
    }


def suspension_rate_analysis(df: pd.DataFrame) -> dict:
    """Analyze suspended sentence (緩刑) rates by various dimensions."""
    results = {}

    # Overall rate
    results["overall_rate"] = float(df["sentence_suspended"].mean())

    # By drug class
    results["by_drug_class"] = (
        df.groupby("drug_class", dropna=True)["sentence_suspended"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "rate"})
        .reset_index()
        .to_dict(orient="records")
    )

    # By severity
    results["by_severity"] = (
        df.groupby("severity")["sentence_suspended"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "rate"})
        .reset_index()
        .to_dict(orient="records")
    )

    # By guilty plea
    results["by_guilty_plea"] = (
        df.groupby("guilty_plea")["sentence_suspended"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "rate"})
        .reset_index()
        .to_dict(orient="records")
    )

    return results


def run_analysis(df: pd.DataFrame, out_dir: str = "data/processed") -> dict:
    """Run all analyses and save stats.json."""
    stats_data = {
        "descriptive": descriptive_stats(df),
        "temporal": temporal_trend(df),
        "suspension": suspension_rate_analysis(df),
    }

    out_path = Path(out_dir) / "stats.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(stats_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"統計分析完成，輸出至 {out_path}")
    return stats_data
