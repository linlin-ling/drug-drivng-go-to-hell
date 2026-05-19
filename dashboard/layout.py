"""Top-level Dash layout with tab navigation."""
from dash import dcc, html
import dash_bootstrap_components as dbc


NAVBAR = dbc.Navbar(
    dbc.Container([
        dbc.NavbarBrand(
            [
                html.Span("⚖️ ", style={"fontSize": "1.3rem"}),
                "台灣毒駕判決量刑分析",
            ],
            className="fw-bold fs-5",
        ),
        dbc.Nav([
            dbc.NavItem(dbc.NavLink("司法改革資料庫", href="#", className="text-white-50")),
        ], navbar=True),
        html.Small("資料來源：司法院法學資料檢索系統", className="text-white-50 ms-auto"),
    ], fluid=True),
    color="dark",
    dark=True,
    className="mb-0",
)


TABS = dbc.Tabs(
    id="main-tabs",
    active_tab="overview",
    children=[
        dbc.Tab(label="📊 總覽", tab_id="overview"),
        dbc.Tab(label="🗺️ 地區分析", tab_id="court-map"),
        dbc.Tab(label="👨‍⚖️ 法官分析", tab_id="judge-view"),
        dbc.Tab(label="📈 年份趨勢", tab_id="trends"),
        dbc.Tab(label="🔍 個案查詢", tab_id="case-explorer"),
        dbc.Tab(label="🔬 影響因素", tab_id="factors"),
        dbc.Tab(label="⚖️ 審級分析", tab_id="appeal-chain"),
    ],
    className="mt-3 mb-0",
)


def make_layout() -> html.Div:
    return html.Div([
        NAVBAR,
        dbc.Container([
            dbc.Alert(
                [
                    html.Strong("研究目的："),
                    "本系統透過量化分析台灣毒駕（刑法第185條之3）判決書，"
                    "揭露各法院、法官間量刑落差，作為推動司法改革的實證依據。",
                ],
                color="info",
                className="mt-3 mb-0",
                dismissable=True,
            ),
            TABS,
            html.Div(id="tab-content", className="mt-3"),
        ], fluid=True, className="px-4"),
    ])
