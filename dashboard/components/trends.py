"""年份趨勢頁：年度刑期趨勢 + 毒品種類分拆。"""
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html
import dash_bootstrap_components as dbc
import pandas as pd


def yearly_by_drug_fig(df: pd.DataFrame) -> go.Figure:
    valid = df[
        df["effective_months"].notna()
        & df["year"].notna()
        & df["drug_class_label"].notna()
    ]

    yearly = (
        valid.groupby(["year", "drug_class_label"])["effective_months"]
        .median()
        .reset_index()
        .rename(columns={"effective_months": "median_months"})
    )

    fig = px.line(
        yearly,
        x="year",
        y="median_months",
        color="drug_class_label",
        markers=True,
        labels={
            "year": "年份",
            "median_months": "中位刑期（月）",
            "drug_class_label": "毒品級別",
        },
        title="各毒品級別年度刑期趨勢",
        color_discrete_sequence=px.colors.qualitative.Set1,
    )
    fig.update_layout(
        xaxis=dict(dtick=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def drug_volume_fig(df: pd.DataFrame) -> go.Figure:
    valid = df[df["year"].notna() & df["drug_class_label"].notna()]
    counts = (
        valid.groupby(["year", "drug_class_label"])
        .size()
        .reset_index(name="count")
    )

    fig = px.bar(
        counts,
        x="year",
        y="count",
        color="drug_class_label",
        barmode="stack",
        labels={
            "year": "年份",
            "count": "案件數",
            "drug_class_label": "毒品級別",
        },
        title="各年度毒駕案件數（依毒品級別）",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        xaxis=dict(dtick=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def suspension_trend_fig(df: pd.DataFrame) -> go.Figure:
    valid = df[df["year"].notna()]
    yearly = (
        valid.groupby("year")["sentence_suspended"]
        .agg(["mean", "count"])
        .reset_index()
    )
    yearly["rate_pct"] = yearly["mean"] * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=yearly["year"], y=yearly["rate_pct"],
        mode="lines+markers",
        name="緩刑率（%）",
        line=dict(color="#FF9800", width=2),
        fill="tozeroy",
        fillcolor="rgba(255,152,0,0.1)",
    ))
    fig.update_layout(
        title="各年度緩刑率趨勢",
        xaxis=dict(title="年份", dtick=1),
        yaxis=dict(title="緩刑率（%）", range=[0, 100]),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
    )
    return fig


def severity_trend_fig(df: pd.DataFrame) -> go.Figure:
    """肇事嚴重程度隨年份的分佈變化。"""
    valid = df[df["year"].notna() & df["severity"].notna()]
    counts = (
        valid.groupby(["year", "severity"])
        .size()
        .reset_index(name="count")
    )
    totals = counts.groupby("year")["count"].transform("sum")
    counts["pct"] = counts["count"] / totals * 100

    fig = px.area(
        counts,
        x="year",
        y="pct",
        color="severity",
        labels={"year": "年份", "pct": "比率（%）", "severity": "肇事嚴重程度"},
        title="各年度肇事嚴重程度分佈",
        color_discrete_map={
            "無肇事": "#4CAF50",
            "肇事": "#FF9800",
            "傷人": "#F44336",
            "重傷": "#9C27B0",
            "致死": "#212121",
        },
    )
    fig.update_layout(
        xaxis=dict(dtick=1),
        yaxis=dict(range=[0, 100]),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
    )
    return fig


def layout(df: pd.DataFrame) -> html.Div:
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=yearly_by_drug_fig(df)), width=6),
            dbc.Col(dcc.Graph(figure=drug_volume_fig(df)), width=6),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=suspension_trend_fig(df)), width=6),
            dbc.Col(dcc.Graph(figure=severity_trend_fig(df)), width=6),
        ]),
    ])
