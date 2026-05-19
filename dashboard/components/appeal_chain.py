"""審級分析頁：上訴結果分析、量刑變化、案件鏈表格。"""
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd

from analysis.case_linker import get_chain_summary


def kpi_card(title: str, value: str, subtitle: str = "", color: str = "primary") -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.H6(title, className="card-subtitle text-muted mb-1", style={"fontSize": "0.85rem"}),
            html.H3(value, className=f"card-title text-{color} mb-1"),
            html.Small(subtitle, className="text-muted"),
        ]),
        className="text-center shadow-sm h-100",
    )


def _no_data_message() -> html.Div:
    return html.Div(
        dbc.Alert(
            [
                html.I(className="me-2"),
                html.Strong("尚無連結的審級資料"),
                html.Br(),
                html.Small(
                    "目前的資料集中尚未找到可跨審級連結的判決。"
                    "當一審和二審判決均存在且 original_court_ref / original_case_no_ref 欄位"
                    "能互相對應時，此分析才會顯示資料。",
                    className="text-muted",
                ),
            ],
            color="secondary",
            className="mt-4 text-center",
        ),
        className="py-4",
    )


def make_kpis(chains: pd.DataFrame) -> dbc.Row:
    total_chains = len(chains)
    upheld = chains[chains["appeal_outcome"] == "上訴駁回"]
    overturn = chains[chains["appeal_outcome"] == "撤銷改判"]
    remand = chains[chains["appeal_outcome"] == "撤銷發回"]

    upheld_rate = len(upheld) / total_chains * 100 if total_chains else 0
    overturn_rate = len(overturn) / total_chains * 100 if total_chains else 0

    delta_values = overturn["sentence_delta"].dropna()
    avg_delta = delta_values.mean() if len(delta_values) > 0 else 0
    delta_sign = "+" if avg_delta > 0 else ""

    return dbc.Row([
        dbc.Col(kpi_card("連結案件鏈數", f"{total_chains:,}", "條", "primary"), width=3),
        dbc.Col(kpi_card("上訴駁回率", f"{upheld_rate:.1f}%", "維持原判", "info"), width=3),
        dbc.Col(kpi_card("撤銷改判率", f"{overturn_rate:.1f}%", "改變刑期", "warning"), width=3),
        dbc.Col(
            kpi_card(
                "撤銷改判平均變化",
                f"{delta_sign}{avg_delta:.1f}",
                "月（正=加重）",
                "danger" if avg_delta > 0 else "success",
            ),
            width=3,
        ),
    ], className="mb-4 g-3")


def outcome_pie_fig(chains: pd.DataFrame) -> go.Figure:
    counts = chains["appeal_outcome"].value_counts().reset_index()
    counts.columns = ["appeal_outcome", "count"]
    counts["appeal_outcome"] = counts["appeal_outcome"].fillna("未知")

    color_map = {
        "上訴駁回": "#5B9BD5",
        "撤銷改判": "#ED7D31",
        "撤銷發回": "#A9D18E",
        "未知": "#BFBFBF",
    }
    colors = [color_map.get(o, "#BFBFBF") for o in counts["appeal_outcome"]]

    fig = go.Figure(go.Pie(
        labels=counts["appeal_outcome"],
        values=counts["count"],
        hole=0.45,
        marker=dict(colors=colors),
        textinfo="label+percent",
        hovertemplate="%{label}: %{value} 件 (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title="上訴結果分佈",
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        legend=dict(orientation="h", yanchor="bottom", y=-0.15),
        margin=dict(t=50, b=60),
    )
    return fig


def outcome_by_appellant_fig(chains: pd.DataFrame, df_full: pd.DataFrame) -> go.Figure:
    """Bar chart of appeal outcomes broken down by who appealed."""
    # Merge appealed_by from the 二審 records
    second = df_full[df_full["case_instance"] == "二審"][
        ["jid", "appealed_by", "appeal_outcome"]
    ].copy()
    if second.empty or "second_jid" not in chains.columns:
        fig = go.Figure()
        fig.add_annotation(text="資料不足", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    merged = chains.merge(
        second.rename(columns={"jid": "second_jid", "appealed_by": "appellant"}),
        on="second_jid",
        how="left",
    )
    merged["appellant"] = merged["appellant"].fillna("未知")
    merged["appeal_outcome_y"] = merged["appeal_outcome_y"] if "appeal_outcome_y" in merged.columns else merged["appeal_outcome"]

    outcome_col = "appeal_outcome_y" if "appeal_outcome_y" in merged.columns else "appeal_outcome"
    grp = merged.groupby(["appellant", outcome_col]).size().reset_index(name="count")
    grp.columns = ["appellant", "appeal_outcome", "count"]

    fig = px.bar(
        grp,
        x="appellant",
        y="count",
        color="appeal_outcome",
        barmode="group",
        title="上訴結果 × 上訴人",
        labels={"appellant": "上訴人", "count": "案件數", "appeal_outcome": "上訴結果"},
        color_discrete_map={
            "上訴駁回": "#5B9BD5",
            "撤銷改判": "#ED7D31",
            "撤銷發回": "#A9D18E",
        },
    )
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        legend_title="上訴結果",
    )
    return fig


def sentence_scatter_fig(chains: pd.DataFrame) -> go.Figure:
    plot_data = chains[
        chains["first_months"].notna() & chains["second_months"].notna()
    ].copy()

    if plot_data.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="無足夠的一審/二審刑期資料可繪製散佈圖",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        fig.update_layout(title="一審 vs 二審刑期對照")
        return fig

    plot_data["appeal_outcome"] = plot_data["appeal_outcome"].fillna("未知")
    color_map = {
        "上訴駁回": "#5B9BD5",
        "撤銷改判": "#ED7D31",
        "撤銷發回": "#A9D18E",
        "未知": "#BFBFBF",
    }

    fig = px.scatter(
        plot_data,
        x="first_months",
        y="second_months",
        color="appeal_outcome",
        color_discrete_map=color_map,
        hover_data={
            "first_court": True,
            "second_court": True,
            "sentence_delta": True,
            "first_months": ":.1f",
            "second_months": ":.1f",
        },
        labels={
            "first_months": "一審刑期（月）",
            "second_months": "二審刑期（月）",
            "appeal_outcome": "上訴結果",
            "first_court": "一審法院",
            "second_court": "二審法院",
            "sentence_delta": "刑期差（月）",
        },
        title="一審 vs 二審刑期散佈圖",
        opacity=0.75,
    )

    # Add diagonal reference line (no change)
    max_val = max(
        plot_data["first_months"].max(),
        plot_data["second_months"].max(),
        1,
    )
    fig.add_trace(go.Scatter(
        x=[0, max_val],
        y=[0, max_val],
        mode="lines",
        line=dict(color="gray", dash="dash", width=1),
        name="刑期不變基準線",
        showlegend=True,
    ))

    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font_family="Noto Sans TC, sans-serif",
        legend_title="上訴結果",
        annotations=[
            dict(
                text="上方 = 二審加重",
                xref="paper", yref="paper",
                x=0.02, y=0.98,
                showarrow=False,
                font=dict(size=10, color="gray"),
                bgcolor="rgba(255,255,255,0.7)",
            ),
            dict(
                text="下方 = 二審減輕",
                xref="paper", yref="paper",
                x=0.02, y=0.03,
                showarrow=False,
                font=dict(size=10, color="gray"),
                bgcolor="rgba(255,255,255,0.7)",
            ),
        ],
    )
    return fig


def chain_table(chains: pd.DataFrame) -> dash_table.DataTable:
    display = chains[[
        c for c in [
            "chain_id", "first_court", "first_jid", "first_months",
            "appeal_outcome", "second_court", "second_jid", "second_months",
            "sentence_delta", "drug_class", "year",
        ] if c in chains.columns
    ]].copy()

    col_labels = {
        "chain_id": "鏈ID",
        "first_court": "一審法院",
        "first_jid": "一審案號",
        "first_months": "一審刑期(月)",
        "appeal_outcome": "上訴結果",
        "second_court": "二審法院",
        "second_jid": "二審案號",
        "second_months": "二審刑期(月)",
        "sentence_delta": "刑期變化(月)",
        "drug_class": "毒品級別",
        "year": "年份",
    }

    for col in ["first_months", "second_months", "sentence_delta"]:
        if col in display.columns:
            display[col] = display[col].apply(
                lambda v: f"{v:.1f}" if pd.notna(v) else ""
            )

    columns = [
        {"name": col_labels.get(c, c), "id": c}
        for c in display.columns
    ]

    return dash_table.DataTable(
        data=display.fillna("").to_dict("records"),
        columns=columns,
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": "#343a40",
            "color": "white",
            "fontWeight": "bold",
            "textAlign": "center",
        },
        style_cell={
            "fontFamily": "Noto Sans TC, sans-serif",
            "fontSize": "0.85rem",
            "textAlign": "center",
            "padding": "6px 10px",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": '{appeal_outcome} = "撤銷改判"'},
                "backgroundColor": "#fff3cd",
            },
            {
                "if": {"filter_query": '{appeal_outcome} = "撤銷發回"'},
                "backgroundColor": "#d1e7dd",
            },
            {
                "if": {"row_index": "odd"},
                "backgroundColor": "#f8f9fa",
            },
        ],
    )


def layout(df: pd.DataFrame) -> html.Div:
    """Build the appeal-chain analysis page layout."""
    chains = get_chain_summary(df)

    if chains.empty:
        return html.Div([
            html.H5("審級分析", className="mt-3 mb-3 fw-bold"),
            _no_data_message(),
        ])

    return html.Div([
        html.H5("審級分析：上訴結果與量刑變化", className="mt-2 mb-3 fw-bold"),

        # Section 1: KPI row
        make_kpis(chains),

        # Section 2: Outcome breakdown
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("上訴結果分佈"),
                    dbc.CardBody(dcc.Graph(figure=outcome_pie_fig(chains))),
                ], className="shadow-sm"),
                width=5,
            ),
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("上訴結果 × 上訴人"),
                    dbc.CardBody(dcc.Graph(figure=outcome_by_appellant_fig(chains, df))),
                ], className="shadow-sm"),
                width=7,
            ),
        ], className="mb-4 g-3"),

        # Section 3: Sentence scatter
        dbc.Row([
            dbc.Col(
                dbc.Card([
                    dbc.CardHeader("一審 vs 二審刑期對照（每點為一個案件鏈）"),
                    dbc.CardBody(dcc.Graph(figure=sentence_scatter_fig(chains))),
                ], className="shadow-sm"),
                width=12,
            ),
        ], className="mb-4"),

        # Section 4: Chain table
        dbc.Row([
            dbc.Col([
                html.H6("案件鏈明細", className="mb-2 fw-bold"),
                chain_table(chains),
            ]),
        ], className="mb-4"),
    ])
