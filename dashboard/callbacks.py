"""All Dash callbacks for interactivity."""
import pandas as pd
from dash import Input, Output, State, callback
from dash.exceptions import PreventUpdate

from dashboard.components import (
    overview, court_map, judge_view, trends, case_explorer, factors, appeal_chain
)


def register_callbacks(app, df: pd.DataFrame) -> None:
    """Register all callbacks with the Dash app instance."""

    # ── Tab routing ───────────────────────────────────────────────────────────

    @app.callback(
        Output("tab-content", "children"),
        Input("main-tabs", "active_tab"),
    )
    def render_tab(active_tab: str):
        if active_tab == "overview":
            return overview.layout(df)
        if active_tab == "court-map":
            return court_map.layout(df)
        if active_tab == "judge-view":
            return judge_view.layout(df)
        if active_tab == "trends":
            return trends.layout(df)
        if active_tab == "case-explorer":
            return case_explorer.layout(df)
        if active_tab == "factors":
            return factors.layout(df)
        if active_tab == "appeal-chain":
            return appeal_chain.layout(df)
        return "請選擇頁籤"

    # ── Judge page: violin updates when court changes ─────────────────────────

    @app.callback(
        Output("judge-violin-fig", "figure"),
        Input("judge-court-select", "value"),
        prevent_initial_call=True,
    )
    def update_judge_violin(selected_court: str):
        return judge_view.judge_violin(df, selected_court)

    # ── Case explorer: filter table ───────────────────────────────────────────

    @app.callback(
        Output("case-table", "data"),
        Output("explorer-count", "children"),
        Input("explorer-court", "value"),
        Input("explorer-years", "value"),
        Input("explorer-drug", "value"),
        Input("explorer-sentence", "value"),
        Input("explorer-flags", "value"),
        prevent_initial_call=False,
    )
    def filter_cases(court, years, drug, sentence_range, flags):
        filtered = df.copy()

        if court and court != "全部":
            filtered = filtered[filtered["court"] == court]

        if years:
            filtered = filtered[filtered["year"].between(years[0], years[1])]

        if drug and drug != "全部":
            filtered = filtered[filtered["drug_class_label"] == drug]

        if sentence_range:
            filtered = filtered[
                filtered["effective_months"].between(sentence_range[0], sentence_range[1])
                | filtered["effective_months"].isna()
            ]

        if flags:
            if "suspended" in flags:
                filtered = filtered[filtered["sentence_suspended"] == True]
            if "repeat" in flags:
                filtered = filtered[filtered["is_repeat_offender"] == True]
            if "accident" in flags:
                filtered = filtered[filtered["caused_accident"] == True]

        display_cols = [
            "case_no", "court", "judge", "year", "drug_class_label",
            "drug_substance", "effective_months", "sentence_suspended",
            "is_repeat_offender", "severity", "guilty_plea",
        ]
        display = filtered[[c for c in display_cols if c in filtered.columns]].copy()

        for col in ["sentence_suspended", "is_repeat_offender", "guilty_plea"]:
            if col in display.columns:
                display[col] = display[col].map({True: "是", False: "否"})

        if "effective_months" in display.columns:
            display["effective_months"] = display["effective_months"].round(1)
        if "year" in display.columns:
            display["year"] = display["year"].astype("Int64")

        count_text = f"共找到 {len(filtered):,} 筆符合條件的案件"
        return display.fillna("").to_dict("records"), count_text
