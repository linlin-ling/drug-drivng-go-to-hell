"""個案查詢頁：可篩選的判決書 DataTable。"""
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd


DISPLAY_COLS = [
    {"name": "案號", "id": "case_no"},
    {"name": "法院", "id": "court"},
    {"name": "法官", "id": "judge"},
    {"name": "年份", "id": "year"},
    {"name": "毒品級別", "id": "drug_class_label"},
    {"name": "毒品種類", "id": "drug_substance"},
    {"name": "刑期（月）", "id": "effective_months"},
    {"name": "緩刑", "id": "sentence_suspended"},
    {"name": "累犯", "id": "is_repeat_offender"},
    {"name": "肇事嚴重程度", "id": "severity"},
    {"name": "認罪", "id": "guilty_plea"},
]


def layout(df: pd.DataFrame) -> html.Div:
    courts = ["全部"] + sorted(df["court"].dropna().unique().tolist())
    years = sorted(df["year"].dropna().unique().astype(int).tolist())
    drug_labels = ["全部"] + sorted(df["drug_class_label"].dropna().unique().tolist())

    display_df = df[
        [c["id"] for c in DISPLAY_COLS if c["id"] in df.columns]
    ].copy()

    # Boolean → 是/否
    for col in ["sentence_suspended", "is_repeat_offender", "guilty_plea"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].map({True: "是", False: "否"})

    if "effective_months" in display_df.columns:
        display_df["effective_months"] = display_df["effective_months"].round(1)
    if "year" in display_df.columns:
        display_df["year"] = display_df["year"].astype("Int64")

    return html.Div([
        # Filter controls
        dbc.Row([
            dbc.Col([
                html.Label("法院", className="fw-bold"),
                dbc.Select(
                    id="explorer-court",
                    options=[{"label": c, "value": c} for c in courts],
                    value="全部",
                ),
            ], width=3),
            dbc.Col([
                html.Label("年份範圍", className="fw-bold"),
                dcc.RangeSlider(
                    id="explorer-years",
                    min=min(years) if years else 2016,
                    max=max(years) if years else 2026,
                    step=1,
                    value=[min(years) if years else 2016, max(years) if years else 2026],
                    marks={y: str(y) for y in years},
                    tooltip={"placement": "bottom"},
                ),
            ], width=4),
            dbc.Col([
                html.Label("毒品級別", className="fw-bold"),
                dbc.Select(
                    id="explorer-drug",
                    options=[{"label": d, "value": d} for d in drug_labels],
                    value="全部",
                ),
            ], width=2),
            dbc.Col([
                html.Label("刑期範圍（月）", className="fw-bold"),
                dcc.RangeSlider(
                    id="explorer-sentence",
                    min=0, max=240, step=6,
                    value=[0, 240],
                    marks={i: str(i) for i in range(0, 241, 24)},
                    tooltip={"placement": "bottom"},
                ),
            ], width=3),
        ], className="mb-3 align-items-end"),

        dbc.Row([
            dbc.Col([
                dbc.Checklist(
                    options=[
                        {"label": "僅顯示緩刑案件", "value": "suspended"},
                        {"label": "僅顯示累犯", "value": "repeat"},
                        {"label": "僅顯示肇事案件", "value": "accident"},
                    ],
                    value=[],
                    id="explorer-flags",
                    inline=True,
                ),
            ], width=12),
        ], className="mb-3"),

        html.Div(id="explorer-count", className="text-muted mb-2"),

        dash_table.DataTable(
            id="case-table",
            data=display_df.fillna("").to_dict("records"),
            columns=DISPLAY_COLS,
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": "#37474F",
                "color": "white",
                "fontWeight": "bold",
                "fontFamily": "Noto Sans TC, sans-serif",
            },
            style_cell={
                "fontFamily": "Noto Sans TC, sans-serif",
                "fontSize": "13px",
                "padding": "8px",
                "textAlign": "left",
                "maxWidth": "200px",
                "overflow": "hidden",
                "textOverflow": "ellipsis",
            },
            style_data_conditional=[
                {
                    "if": {"filter_query": '{sentence_suspended} = "是"'},
                    "backgroundColor": "#FFF9C4",
                },
                {
                    "if": {"filter_query": '{is_repeat_offender} = "是"'},
                    "backgroundColor": "#FFCCBC",
                },
            ],
            page_size=25,
            sort_action="native",
            filter_action="native",
            export_format="csv",
            export_headers="display",
        ),
    ])
