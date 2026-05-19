"""影響因素分析頁：各因素對刑期的影響量化。"""
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np


def factor_impact_fig(df: pd.DataFrame) -> go.Figure:
    """Compare median sentence by presence/absence of each factor."""
    valid = df[df["effective_months"].notna()]

    factors = {
        "累犯": "is_repeat_offender",
        "致死": "caused_death",
        "重傷": "caused_serious_injury",
        "傷人": "caused_injury",
        "肇事": "caused_accident",
        "認罪": "guilty_plea",
        "緩刑": "sentence_suspended",
        "尿液陽性": "urine_positive",
    }

    rows = []
    baseline = valid["effective_months"].median()
    for label, col in factors.items():
        if col not in valid.columns:
            continue
        grp_yes = valid[valid[col] == True]["effective_months"]
        grp_no = valid[valid[col] == False]["effective_months"]
        if len(grp_yes) > 0 and len(grp_no) > 0:
            rows.append({
                "因素": label,
                "有（中位數）": grp_yes.median(),
                "無（中位數）": grp_no.median(),
                "差值": grp_yes.median() - grp_no.median(),
                "樣本數（有）": len(grp_yes),
            })

    if not rows:
        fig = go.Figure()
        fig.update_layout(title="資料不足")
        return fig

    factor_df = pd.DataFrame(rows).sort_values("差值", ascending=True)

    fig = go.Figure()
    colors = ["#F44336" if v > 0 else "#4CAF50" for v in factor_df["差值"]]
    fig.add_trace(go.Bar(
        x=factor_df["差值"],
        y=factor_df["因素"],
        orientation="h",
        marker_color=colors,
        text=[f"{v:+.1f}月" for v in factor_df["差值"]],
        textposition="outside",
    ))
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    fig.update_layout(
        title="各因素對刑期的影響（相較無該因素之差值）",
        xaxis_title="刑期差值（月，正值=較重）",
        yaxis_title="",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        height=450,
    )
    return fig


def drug_class_comparison(df: pd.DataFrame) -> go.Figure:
    valid = df[df["effective_months"].notna() & df["drug_class_label"].notna()]

    fig = px.box(
        valid,
        x="drug_class_label",
        y="effective_months",
        color="severity",
        labels={
            "drug_class_label": "毒品級別",
            "effective_months": "刑期（月）",
            "severity": "肇事嚴重程度",
        },
        title="毒品級別 × 肇事嚴重程度 刑期分佈",
        category_orders={"drug_class_label": ["第一級", "第二級", "第三級", "第四級"]},
        color_discrete_map={
            "無肇事": "#4CAF50",
            "肇事": "#FF9800",
            "傷人": "#F44336",
            "重傷": "#9C27B0",
            "致死": "#212121",
        },
    )
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
    )
    return fig


def repeat_offender_fig(df: pd.DataFrame) -> go.Figure:
    """Compare sentencing distribution for repeat vs first-time offenders."""
    valid = df[df["effective_months"].notna()]
    valid = valid.copy()
    valid["累犯"] = valid["is_repeat_offender"].map({True: "累犯", False: "初犯"})

    fig = px.violin(
        valid,
        x="累犯",
        y="effective_months",
        box=True,
        points=False,
        color="累犯",
        labels={"effective_months": "刑期（月）", "累犯": ""},
        title="初犯 vs 累犯 刑期分佈",
        color_discrete_map={"初犯": "#4CAF50", "累犯": "#F44336"},
    )
    fig.update_layout(
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
    )
    return fig


def layout(df: pd.DataFrame) -> html.Div:
    return html.Div([
        dbc.Row([
            dbc.Col(dcc.Graph(figure=factor_impact_fig(df)), width=6),
            dbc.Col(dcc.Graph(figure=repeat_offender_fig(df)), width=6),
        ], className="mb-4"),
        dbc.Row([
            dbc.Col(dcc.Graph(figure=drug_class_comparison(df)), width=12),
        ]),
    ])
