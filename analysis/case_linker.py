"""Build cross-instance appeal chains from parsed judgment data."""
import pandas as pd


def build_appeal_chains(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add linkage columns to df:
      - lower_jid: jid of the 一審 judgment this record appeals from (for 二審+ records)
      - higher_jid: jid of the appeal judgment filed against this record (for 一審 records)
      - chain_id: shared identifier for all judgments in the same case chain
      - sentence_delta_months: prison_months minus lower court's prison_months (for appeal records)
    """
    df = df.copy()
    df["lower_jid"] = None
    df["higher_jid"] = None
    df["chain_id"] = None
    df["sentence_delta_months"] = None

    # Build lookup: (normalized_court, normalized_case_no) → row index
    lookup = {}
    for idx, row in df.iterrows():
        court = str(row.get("court") or "")
        case_no = str(row.get("case_no") or "")
        if court and case_no:
            lookup[(court, case_no)] = idx

    # Match appeal records to their originals
    for idx, row in df.iterrows():
        orig_court = str(row.get("original_court_ref") or "")
        orig_case_no = str(row.get("original_case_no_ref") or "")
        if not orig_court or not orig_case_no:
            continue
        orig_idx = lookup.get((orig_court, orig_case_no))
        if orig_idx is not None:
            df.at[idx, "lower_jid"] = df.at[orig_idx, "jid"]
            df.at[orig_idx, "higher_jid"] = df.at[idx, "jid"]
            # Sentence delta
            lower_months = df.at[orig_idx, "effective_months"]
            upper_months = df.at[idx, "effective_months"]
            if pd.notna(lower_months) and pd.notna(upper_months):
                df.at[idx, "sentence_delta_months"] = upper_months - lower_months

    # Build chain_id: walk from the lowest instance upward
    chain_counter = [0]

    def assign_chain(idx, chain_id):
        df.at[idx, "chain_id"] = chain_id
        higher = df.at[idx, "higher_jid"]
        if higher:
            # find the row for higher_jid
            matches = df.index[df["jid"] == higher].tolist()
            if matches:
                assign_chain(matches[0], chain_id)

    for idx, row in df.iterrows():
        if pd.isna(row.get("lower_jid")) or row.get("lower_jid") is None:
            # This is a root (no lower court linked)
            if pd.notna(row.get("higher_jid")) and row.get("higher_jid") is not None:
                # Only assign chain if there's at least one linked record
                chain_counter[0] += 1
                assign_chain(idx, chain_counter[0])

    return df


def get_chain_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per chain_id with: 一審刑期, 二審刑期, 上訴結果, delta."""
    chains = df[df["chain_id"].notna()].copy()
    if chains.empty:
        return pd.DataFrame()

    rows = []
    for chain_id, grp in chains.groupby("chain_id"):
        first = grp[grp["case_instance"] == "一審"]
        second = grp[grp["case_instance"] == "二審"]
        row = {
            "chain_id": chain_id,
            "first_jid": first["jid"].values[0] if len(first) else None,
            "first_court": first["court"].values[0] if len(first) else None,
            "first_months": first["effective_months"].values[0] if len(first) else None,
            "second_jid": second["jid"].values[0] if len(second) else None,
            "second_court": second["court"].values[0] if len(second) else None,
            "second_months": second["effective_months"].values[0] if len(second) else None,
            "appeal_outcome": second["appeal_outcome"].values[0] if len(second) else None,
            "sentence_delta": second["sentence_delta_months"].values[0] if len(second) else None,
            "drug_class": first["drug_class"].values[0] if len(first) else None,
            "year": first["year"].values[0] if len(first) else None,
        }
        rows.append(row)
    return pd.DataFrame(rows)
