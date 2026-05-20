"""Load, clean, and normalize parsed judgment data into a pandas DataFrame."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROCESSED_JSON = Path("data/processed/judgments.json")
PROCESSED_CSV = Path("data/processed/judgments.csv")

# Court name → region mapping (Taiwan's 22 district courts + branches)
COURT_REGION_MAP = {
    "臺灣臺北地方法院": "臺北",
    "臺灣士林地方法院": "臺北",
    "臺灣新北地方法院": "新北",
    "臺灣桃園地方法院": "桃園",
    "臺灣新竹地方法院": "新竹",
    "臺灣苗栗地方法院": "苗栗",
    "臺灣臺中地方法院": "臺中",
    "臺灣彰化地方法院": "彰化",
    "臺灣南投地方法院": "南投",
    "臺灣雲林地方法院": "雲林",
    "臺灣嘉義地方法院": "嘉義",
    "臺灣臺南地方法院": "臺南",
    "臺灣高雄地方法院": "高雄",
    "臺灣橋頭地方法院": "高雄",
    "臺灣屏東地方法院": "屏東",
    "臺灣臺東地方法院": "臺東",
    "臺灣花蓮地方法院": "花蓮",
    "臺灣宜蘭地方法院": "宜蘭",
    "臺灣基隆地方法院": "基隆",
    "臺灣澎湖地方法院": "澎湖",
    "福建金門地方法院": "金門",
    "福建連江地方法院": "連江",
}

DRUG_CLASS_LABELS = {1: "第一級", 2: "第二級", 3: "第三級", 4: "第四級"}


def load_and_clean(json_path: str | Path = PROCESSED_JSON) -> pd.DataFrame:
    """Load parsed JSON and return a cleaned DataFrame."""
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    df = pd.DataFrame(data)

    if df.empty:
        return df

    # ── Date parsing ──────────────────────────────────────────────────────────
    df["judgment_date"] = pd.to_datetime(df["judgment_date"], errors="coerce")
    df["year"] = df["judgment_date"].dt.year.fillna(df["year_ce"]).astype("Int64")
    df["month"] = df["judgment_date"].dt.month.astype("Int64")

    # ── Prison months: cap extreme outliers (> 240 months = 20 years) ────────
    if "prison_months" in df.columns:
        df["prison_months"] = pd.to_numeric(df["prison_months"], errors="coerce")
        df.loc[df["prison_months"] > 240, "prison_months"] = np.nan

    # ── Effective sentence: prison or detention_days as months ───────────────
    df["effective_months"] = df["prison_months"].astype(float).copy()
    if "detention_days" in df.columns:
        det_days = pd.to_numeric(df["detention_days"], errors="coerce")
        det_mask = df["prison_months"].isna() & det_days.notna()
        if det_mask.any():
            df.loc[det_mask, "effective_months"] = det_days[det_mask] / 30.0

    # ── Drug class labels ─────────────────────────────────────────────────────
    df["drug_class"] = pd.to_numeric(df["drug_class"], errors="coerce").astype("Int64")
    df["drug_class_label"] = df["drug_class"].map(DRUG_CLASS_LABELS)

    # ── Boolean columns ───────────────────────────────────────────────────────
    bool_cols = [
        "sentence_suspended", "acquitted", "is_repeat_offender",
        "caused_accident", "caused_death", "caused_injury",
        "caused_serious_injury", "guilty_plea", "urine_positive",
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(bool)

    # ── Court region ──────────────────────────────────────────────────────────
    df["region"] = df["court"].map(COURT_REGION_MAP)
    df["region"] = df["region"].fillna("其他")

    # ── Severity label ────────────────────────────────────────────────────────
    def severity(row) -> str:
        if row["caused_death"]:
            return "致死"
        if row["caused_serious_injury"]:
            return "重傷"
        if row["caused_injury"]:
            return "傷人"
        if row["caused_accident"]:
            return "肇事"
        return "無肇事"

    df["severity"] = df.apply(severity, axis=1)

    # ── Court level and instance (from parser fields) ─────────────────────────
    for col in ["court_level", "case_instance", "case_type_word",
                "original_court_ref", "original_case_no_ref",
                "appeal_outcome", "appealed_by"]:
        if col not in df.columns:
            df[col] = None

    # ── Drug-driving filter: use is_drug_driving_case flag if available ────────
    if "is_drug_driving_case" in df.columns:
        n_excl = (~df["is_drug_driving_case"].fillna(True)).sum()
        if n_excl > 0:
            print(f"  [filter] 排除 {n_excl} 筆非毒駕案件", file=sys.stderr)
        df = df[df["is_drug_driving_case"].fillna(True)].copy()

    # ── Filter: keep only cases with valid sentencing info ────────────────────
    valid_mask = (
        df["effective_months"].notna() | df["acquitted"]
    ) & df["year"].between(2016, 2026)

    df_clean = df[valid_mask].copy()

    # ── Build appeal chains ───────────────────────────────────────────────────
    from analysis.case_linker import build_appeal_chains
    df_clean = build_appeal_chains(df_clean)

    return df_clean


def save_csv(df: pd.DataFrame, path: str | Path = PROCESSED_CSV) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"已儲存 {len(df)} 筆資料至 {path}")


def load_csv(path: str | Path = PROCESSED_CSV) -> pd.DataFrame:
    """Load the processed CSV; fallback to JSON if CSV not found."""
    p = Path(path)
    if p.exists():
        df = pd.read_csv(p, encoding="utf-8-sig", low_memory=False)
        df["judgment_date"] = pd.to_datetime(df["judgment_date"], errors="coerce")
        for col in ["drug_class", "year", "month"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # Keep these as strings (not forced numeric)
        for col in ["chain_id", "case_instance", "case_type_word",
                    "original_court_ref", "original_case_no_ref",
                    "appeal_outcome", "appealed_by", "lower_jid", "higher_jid"]:
            if col in df.columns:
                df[col] = df[col].where(df[col].notna(), None)
        bool_cols = [
            "sentence_suspended", "acquitted", "is_repeat_offender",
            "caused_accident", "caused_death", "caused_injury",
            "caused_serious_injury", "guilty_plea", "urine_positive",
        ]
        for col in bool_cols:
            if col in df.columns:
                df[col] = df[col].fillna(False).astype(bool)
        return df

    json_path = Path("data/processed/judgments.json")
    if json_path.exists():
        return load_and_clean(json_path)

    raise FileNotFoundError(
        "找不到處理後的資料。請先執行 `python main.py parse` 和 `python main.py analyze`。"
    )
