"""
Dash application entry point.
Loads the processed dataset and starts the interactive web dashboard.
"""
import sys
from pathlib import Path

import dash
import dash_bootstrap_components as dbc

from analysis.data_cleaner import load_csv
from dashboard.layout import make_layout
from dashboard.callbacks import register_callbacks


def create_app(df) -> dash.Dash:
    app = dash.Dash(
        __name__,
        external_stylesheets=[
            dbc.themes.FLATLY,
            "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap",
        ],
        suppress_callback_exceptions=True,
        title="毒駕判決量刑分析 | 司法改革資料庫",
        meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
    )
    app.layout = make_layout()
    register_callbacks(app, df)
    return app


def run(host: str = "0.0.0.0", port: int = 8050, debug: bool = False) -> None:
    print("載入資料集…")
    try:
        df = load_csv()
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"載入 {len(df):,} 筆判決資料，啟動網頁…")
    app = create_app(df)
    app.run(host=host, port=port, debug=debug)
