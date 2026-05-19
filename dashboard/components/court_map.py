"""地區分析頁：各法院量刑箱型圖 + 縣市熱力圖。"""
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html
import dash_bootstrap_components as dbc
import pandas as pd


def court_boxplot(df: pd.DataFrame, metric: str = "effective_months") -> go.Figure:
    valid = df[df[metric].notna() & df["court"].notna()].copy()

    # Keep only courts with >= 10 cases
    counts = valid["court"].value_counts()
    valid = valid[valid["court"].isin(counts[counts >= 10].index)]

    # Sort courts by median sentence
    order = (
        valid.groupby("court")[metric]
        .median()
        .sort_values(ascending=False)
        .index.tolist()
    )

    fig = px.box(
        valid,
        x="court",
        y=metric,
        category_orders={"court": order},
        labels={"court": "法院", metric: "刑期（月）"},
        title="各法院刑期分佈（箱型圖）",
        color="court",
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig.update_layout(
        showlegend=False,
        xaxis_tickangle=-45,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        height=500,
    )
    return fig


def region_heatmap(df: pd.DataFrame) -> go.Figure:
    valid = df[df["effective_months"].notna() & df["region"].notna()]
    region_stats = (
        valid.groupby("region")
        .agg(
            median_months=("effective_months", "median"),
            count=("effective_months", "count"),
            suspended_rate=("sentence_suspended", "mean"),
        )
        .reset_index()
    )
    region_stats["suspended_pct"] = region_stats["suspended_rate"] * 100

    fig = px.bar(
        region_stats.sort_values("median_months", ascending=False),
        x="region",
        y="median_months",
        color="suspended_pct",
        text="count",
        labels={
            "region": "縣市/地區",
            "median_months": "中位刑期（月）",
            "suspended_pct": "緩刑率（%）",
            "count": "案件數",
        },
        title="各地區中位刑期與緩刑率",
        color_continuous_scale="RdYlGn_r",
    )
    fig.update_traces(texttemplate="%{text}件", textposition="outside")
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        coloraxis_colorbar=dict(title="緩刑率(%)"),
        height=450,
    )
    return fig


def court_drug_heatmap(df: pd.DataFrame) -> go.Figure:
    """法院 × 毒品級別 的緩刑率熱力圖。"""
    valid = df[df["court"].notna() & df["drug_class_label"].notna()]
    counts = valid["court"].value_counts()
    valid = valid[valid["court"].isin(counts[counts >= 10].index)]

    pivot = (
        valid.groupby(["court", "drug_class_label"])["sentence_suspended"]
        .mean()
        .unstack(fill_value=None)
    )

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values * 100,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale="RdYlGn_r",
        zmin=0, zmax=100,
        text=[[f"{v:.0f}%" if v is not None and not pd.isna(v) else "N/A"
               for v in row] for row in pivot.values * 100],
        texttemplate="%{text}",
        colorbar=dict(title="緩刑率(%)"),
    ))
    fig.update_layout(
        title="法院 × 毒品級別 緩刑率（%）",
        xaxis_title="毒品級別",
        yaxis_title="法院",
        font_family="Noto Sans TC, sans-serif",
        height=max(400, len(pivot) * 25),
    )
    return fig


def layout(df: pd.DataFrame) -> html.Div:
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=court_boxplot(df)), width=8),
            dbc.Col(dcc.Graph(figure=region_heatmap(df)), width=4),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=court_drug_heatmap(df)), width=12),
        ]),
    ])
