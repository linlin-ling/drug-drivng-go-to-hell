"""法官分析頁：法官量刑 violin plot + 異常法官排行。"""
from __future__ import annotations
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd


MIN_CASES = 15


def judge_violin(df: pd.DataFrame, selected_court: str | None = None) -> go.Figure:
    valid = df[df["effective_months"].notna() & df["judge"].notna() & df["court"].notna()]

    if selected_court and selected_court != "全部":
        valid = valid[valid["court"] == selected_court]

    # Filter judges with enough cases
    counts = valid["judge"].value_counts()
    valid = valid[valid["judge"].isin(counts[counts >= MIN_CASES].index)]

    if valid.empty:
        fig = go.Figure()
        fig.update_layout(title="資料不足（每位法官需至少15筆案件）")
        return fig

    order = (
        valid.groupby("judge")["effective_months"]
        .median()
        .sort_values(ascending=False)
        .index.tolist()
    )

    fig = px.violin(
        valid,
        x="judge",
        y="effective_months",
        category_orders={"judge": order},
        box=True,
        points=False,
        labels={"judge": "法官", "effective_months": "刑期（月）"},
        title=f"法官量刑分佈{f'（{selected_court}）' if selected_court and selected_court != '全部' else '（全部法院）'}",
        color_discrete_sequence=["#5C85D6"],
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        height=500,
    )
    return fig


def anomaly_table(df: pd.DataFrame) -> dash_table.DataTable:
    valid = df[df["effective_months"].notna() & df["judge"].notna() & df["court"].notna()]

    judge_stats = (
        valid.groupby(["court", "judge"])
        .agg(
            case_count=("effective_months", "count"),
            median_months=("effective_months", "median"),
            suspended_rate=("sentence_suspended", "mean"),
        )
        .reset_index()
    )
    judge_stats = judge_stats[judge_stats["case_count"] >= MIN_CASES]

    # Compute deviation from court median
    court_medians = valid.groupby("court")["effective_months"].median()
    judge_stats["court_median"] = judge_stats["court"].map(court_medians)
    judge_stats["deviation"] = judge_stats["median_months"] - judge_stats["court_median"]
    judge_stats["suspended_pct"] = (judge_stats["suspended_rate"] * 100).round(1)

    judge_stats = judge_stats.sort_values("deviation", key=abs, ascending=False)

    rows = judge_stats.head(50).to_dict("records")
    for row in rows:
        row["median_months"] = round(row["median_months"], 1)
        row["court_median"] = round(row["court_median"], 1)
        row["deviation"] = round(row["deviation"], 1)

    return dash_table.DataTable(
        data=rows,
        columns=[
            {"name": "法院", "id": "court"},
            {"name": "法官", "id": "judge"},
            {"name": "案件數", "id": "case_count"},
            {"name": "刑期中位數（月）", "id": "median_months"},
            {"name": "法院中位數（月）", "id": "court_median"},
            {"name": "偏差（月）", "id": "deviation"},
            {"name": "緩刑率（%）", "id": "suspended_pct"},
        ],
        style_data_conditional=[
            {
                "if": {"filter_query": "{deviation} > 6", "column_id": "deviation"},
                "backgroundColor": "#FFCDD2",
                "color": "black",
            },
            {
                "if": {"filter_query": "{deviation} < -6", "column_id": "deviation"},
                "backgroundColor": "#C8E6C9",
                "color": "black",
            },
        ],
        style_header={"backgroundColor": "#37474F", "color": "white", "fontWeight": "bold"},
        style_cell={"fontFamily": "Noto Sans TC, sans-serif", "fontSize": "13px"},
        page_size=20,
        sort_action="native",
        filter_action="native",
    )


def layout(df: pd.DataFrame) -> html.Div:
    courts = ["全部"] + sorted(df["court"].dropna().unique().tolist())

    return html.Div([
        dbc.Row([
            dbc.Col([
                html.Label("選擇法院：", className="fw-bold"),
                dbc.Select(
                    id="judge-court-select",
                    options=[{"label": c, "value": c} for c in courts],
                    value="全部",
                ),
            ], width=4),
        ], className="mb-3"),
        dbc.Row([
            dbc.Col(dcc.Graph(id="judge-violin-fig"), width=12),
        ], className="mb-4"),
        html.H5("法官量刑偏差排行（偏差 > 6月 者標紅；偏差 < -6月 者標綠）", className="mb-2"),
        anomaly_table(df),
    ])
