"""總覽頁：KPI 卡片 + 整體刑期分佈 + 年份趨勢。"""
import plotly.graph_objects as go
import plotly.express as px
from dash import dcc, html
import dash_bootstrap_components as dbc
import pandas as pd


def kpi_card(title: str, value: str, subtitle: str = "", color: str = "primary") -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.H6(title, className="card-subtitle text-muted mb-1", style={"fontSize": "0.85rem"}),
            html.H3(value, className=f"card-title text-{color} mb-1"),
            html.Small(subtitle, className="text-muted"),
        ]),
        className="text-center shadow-sm h-100",
    )


def make_kpis(df: pd.DataFrame) -> list:
    total = len(df)
    valid = df[df["effective_months"].notna()]
    median_m = valid["effective_months"].median() if len(valid) > 0 else 0
    suspended_rate = df["sentence_suspended"].mean() * 100
    acquitted_rate = df["acquitted"].mean() * 100
    max_m = valid["effective_months"].max() if len(valid) > 0 else 0
    min_m = valid["effective_months"].min() if len(valid) > 0 else 0

    return dbc.Row([
        dbc.Col(kpi_card("總案件數", f"{total:,}", "件", "primary"), width=2),
        dbc.Col(kpi_card("刑期中位數", f"{median_m:.1f}", "月", "info"), width=2),
        dbc.Col(kpi_card("緩刑率", f"{suspended_rate:.1f}%", "比率", "warning"), width=2),
        dbc.Col(kpi_card("無罪率", f"{acquitted_rate:.1f}%", "比率", "success"), width=2),
        dbc.Col(kpi_card("最高刑期", f"{max_m:.0f}", "月", "danger"), width=2),
        dbc.Col(kpi_card("最低刑期", f"{min_m:.0f}", "月", "secondary"), width=2),
    ], className="mb-4 g-3")


def sentence_distribution_fig(df: pd.DataFrame) -> go.Figure:
    valid = df[df["effective_months"].notna() & ~df["sentence_suspended"]]
    fig = px.histogram(
        valid,
        x="effective_months",
        nbins=60,
        color="drug_class_label",
        barmode="overlay",
        opacity=0.75,
        labels={
            "effective_months": "刑期（月）",
            "drug_class_label": "毒品級別",
            "count": "案件數",
        },
        title="毒駕刑期分佈（不含緩刑案件）",
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        xaxis_title="刑期（月）",
        yaxis_title="案件數",
        legend_title="毒品級別",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
    )
    fig.add_vline(
        x=valid["effective_months"].median(),
        line_dash="dash",
        line_color="red",
        annotation_text=f"中位數 {valid['effective_months'].median():.1f}月",
    )
    return fig


def yearly_trend_fig(df: pd.DataFrame) -> go.Figure:
    valid = df[df["effective_months"].notna() & df["year"].notna()]
    yearly = valid.groupby("year").agg(
        median_months=("effective_months", "median"),
        count=("effective_months", "count"),
    ).reset_index()
    yearly["suspended_rate"] = (
        df[df["year"].notna()].groupby("year")["sentence_suspended"].mean().values[:len(yearly)]
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=yearly["year"], y=yearly["median_months"],
        mode="lines+markers",
        name="中位刑期（月）",
        line=dict(color="#2196F3", width=2),
        marker=dict(size=8),
        yaxis="y1",
    ))
    fig.add_trace(go.Bar(
        x=yearly["year"], y=yearly["count"],
        name="案件數",
        marker_color="rgba(200,200,200,0.5)",
        yaxis="y2",
    ))
    fig.add_trace(go.Scatter(
        x=yearly["year"], y=yearly["suspended_rate"] * 100,
        mode="lines+markers",
        name="緩刑率（%）",
        line=dict(color="#FF9800", width=2, dash="dot"),
        marker=dict(size=6),
        yaxis="y1",
    ))

    fig.update_layout(
        title="年度趨勢：刑期、案件數與緩刑率",
        xaxis=dict(title="年份", dtick=1),
        yaxis=dict(title="月 / 百分比", side="left"),
        yaxis2=dict(title="案件數", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
    )
    return fig


def layout(df: pd.DataFrame) -> html.Div:
    return html.Div([
        make_kpis(df),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=sentence_distribution_fig(df)), width=7),
            dbc.Col(dcc.Graph(figure=yearly_trend_fig(df)), width=5),
        ], className="mb-4"),
    ])
