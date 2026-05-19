"""
Court-level and judge-level sentencing disparity analysis.
Uses Kruskal-Wallis H-test to detect statistically significant differences.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


MIN_CASES_PER_COURT = 10
MIN_CASES_PER_JUDGE = 15


def court_disparity(df: pd.DataFrame) -> dict:
    """Compute sentencing statistics per court and test for disparity."""
    valid = df[df["effective_months"].notna() & df["court"].notna()]

    court_stats = (
        valid.groupby("court")["effective_months"]
        .agg(
            count="count",
            median="median",
            mean="mean",
            std="std",
            q1=lambda x: x.quantile(0.25),
            q3=lambda x: x.quantile(0.75),
        )
        .reset_index()
    )
    court_stats["suspended_rate"] = (
        df[df["court"].notna()]
        .groupby("court")["sentence_suspended"]
        .mean()
        .reset_index()["sentence_suspended"]
        .values[:len(court_stats)]
    )

    # Filter courts with enough cases
    enough = court_stats[court_stats["count"] >= MIN_CASES_PER_COURT]

    # Kruskal-Wallis across courts
    groups = [
        valid[valid["court"] == c]["effective_months"].values
        for c in enough["court"]
        if len(valid[valid["court"] == c]) >= MIN_CASES_PER_COURT
    ]
    h_stat, p_value = (float("nan"), float("nan"))
    if len(groups) >= 2:
        h_stat, p_value = stats.kruskal(*groups)

    # Coefficient of variation (CV) for disparity magnitude
    median_vals = enough["median"].values
    cv = float(np.std(median_vals) / np.mean(median_vals)) if len(median_vals) > 0 else float("nan")

    return {
        "court_stats": court_stats.to_dict(orient="records"),
        "kruskal_h": float(h_stat),
        "kruskal_p": float(p_value),
        "significant": bool(p_value < 0.05) if not np.isnan(p_value) else False,
        "cv_median": cv,
    }


def region_disparity(df: pd.DataFrame) -> dict:
    """Court-of-region level statistics for choropleth map."""
    valid = df[df["effective_months"].notna() & df["region"].notna()]

    region_stats = (
        valid.groupby("region")["effective_months"]
        .agg(count="count", median="median", mean="mean")
        .reset_index()
    )
    region_stats["suspended_rate"] = (
        df[df["region"].notna()]
        .groupby("region")["sentence_suspended"]
        .mean()
        .values[:len(region_stats)]
    )

    return {"region_stats": region_stats.to_dict(orient="records")}


def judge_disparity(df: pd.DataFrame) -> dict:
    """Identify judges with anomalous sentencing patterns."""
    valid = df[df["effective_months"].notna() & df["judge"].notna() & df["court"].notna()]

    judge_stats = (
        valid.groupby(["court", "judge"])["effective_months"]
        .agg(count="count", median="median", mean="mean", std="std")
        .reset_index()
    )

    # Only judges with enough cases
    judge_stats = judge_stats[judge_stats["count"] >= MIN_CASES_PER_JUDGE]

    # Flag judges whose median is > 1.5 IQR from their court's distribution
    anomalies = []
    for court, court_grp in judge_stats.groupby("court"):
        if len(court_grp) < 3:
            continue
        court_median = court_grp["median"].median()
        iqr = court_grp["median"].quantile(0.75) - court_grp["median"].quantile(0.25)
        for _, row in court_grp.iterrows():
            if abs(row["median"] - court_median) > 1.5 * iqr:
                anomalies.append({
                    "court": court,
                    "judge": row["judge"],
                    "median_months": float(row["median"]),
                    "court_median": float(court_median),
                    "deviation": float(row["median"] - court_median),
                    "count": int(row["count"]),
                })

    return {
        "judge_stats": judge_stats.to_dict(orient="records"),
        "anomalies": sorted(anomalies, key=lambda x: abs(x["deviation"]), reverse=True),
    }


def extreme_cases(df: pd.DataFrame, top_n: int = 20) -> dict:
    """Find cases with extreme sentences relative to similar cases."""
    valid = df[df["effective_months"].notna() & ~df["sentence_suspended"]].copy()

    # Group by drug_class + severity for peer comparison
    def peer_stats(grp):
        grp = grp.copy()
        grp["peer_median"] = grp["effective_months"].median()
        grp["deviation_from_peer"] = grp["effective_months"] - grp["peer_median"]
        return grp

    valid = valid.groupby(["drug_class", "severity"], group_keys=False).apply(peer_stats)

    display_cols = [c for c in
        ["jid", "court", "judge", "year", "drug_class", "drug_class_label",
         "severity", "effective_months", "peer_median", "deviation_from_peer"]
        if c in valid.columns]

    harshest = (
        valid.nlargest(top_n, "deviation_from_peer")[display_cols]
        .to_dict(orient="records")
    )
    lenient = (
        valid.nsmallest(top_n, "deviation_from_peer")[display_cols]
        .to_dict(orient="records")
    )

    return {"harshest": harshest, "most_lenient": lenient}


def run_disparity_analysis(df: pd.DataFrame, out_dir: str = "data/processed") -> dict:
    """Run all disparity analyses and save disparity.json."""
    results = {
        "court": court_disparity(df),
        "region": region_disparity(df),
        "judge": judge_disparity(df),
        "extreme_cases": extreme_cases(df),
    }

    out_path = Path(out_dir) / "disparity.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"落差分析完成，輸出至 {out_path}")
    return results
