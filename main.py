#!/usr/bin/env python3
"""
台灣毒駕判決量刑分析系統
CLI entry point.

用法：
  python main.py scrape [--start 2016] [--end 2026]   # 爬取判決書
  python main.py parse                                  # 解析原始資料
  python main.py analyze                                # 統計分析
  python main.py serve [--port 8050] [--debug]         # 啟動網頁
  python main.py all                                    # 一鍵全流程
"""
import sys
import click


@click.group()
def cli():
    """台灣毒駕判決量刑分析系統。"""
    pass


@cli.command()
@click.option("--start", default=2016, show_default=True, help="起始年份（西元）")
@click.option("--end", default=2026, show_default=True, help="結束年份（西元）")
def scrape(start: int, end: int):
    """爬取司法院判決書並儲存至 data/raw/"""
    from scraper.judicial_scraper import scrape as do_scrape
    do_scrape(start_year=start, end_year=end)


@cli.command()
def parse():
    """解析已爬取的原始判決書，輸出結構化資料至 data/processed/"""
    from scraper.parser import parse_all
    from analysis.data_cleaner import load_and_clean, save_csv

    records = parse_all()
    if not records:
        click.echo("沒有找到原始資料，請先執行 `python main.py scrape`", err=True)
        sys.exit(1)

    import pandas as pd
    df_raw = pd.DataFrame(records)
    df_raw.to_json("data/processed/judgments.json", orient="records", force_ascii=False, indent=2)

    df_clean = load_and_clean("data/processed/judgments.json")
    save_csv(df_clean)
    click.echo(f"清洗後共 {len(df_clean):,} 筆有效資料")


@cli.command()
def analyze():
    """執行統計分析，輸出 stats.json 與 disparity.json"""
    from analysis.data_cleaner import load_csv
    from analysis.sentencing_analysis import run_analysis
    from analysis.disparity_analysis import run_disparity_analysis

    df = load_csv()
    click.echo(f"載入 {len(df):,} 筆資料，開始分析…")
    run_analysis(df)
    run_disparity_analysis(df)
    click.echo("分析完成。")


@cli.command()
@click.option("--port", default=8050, show_default=True, help="網頁埠號")
@click.option("--debug", is_flag=True, default=False, help="開啟 Dash debug 模式")
@click.option("--host", default="0.0.0.0", show_default=True, help="監聽位址")
def serve(port: int, debug: bool, host: str):
    """啟動互動式分析網頁（預設 http://localhost:8050）"""
    from dashboard.app import run
    run(host=host, port=port, debug=debug)


@cli.command()
@click.option("--start", default=2016, show_default=True, help="起始年份")
@click.option("--end", default=2026, show_default=True, help="結束年份")
@click.option("--port", default=8050, show_default=True)
def all(start: int, end: int, port: int):
    """一鍵執行完整流程：爬取 → 解析 → 分析 → 啟動網頁"""
    from scraper.judicial_scraper import scrape as do_scrape
    from scraper.parser import parse_all
    from analysis.data_cleaner import load_and_clean, save_csv
    from analysis.sentencing_analysis import run_analysis
    from analysis.disparity_analysis import run_disparity_analysis
    from dashboard.app import run

    click.echo("=== 步驟 1/4：爬取判決書 ===")
    do_scrape(start_year=start, end_year=end)

    click.echo("\n=== 步驟 2/4：解析資料 ===")
    records = parse_all()
    import pandas as pd
    pd.DataFrame(records).to_json(
        "data/processed/judgments.json", orient="records", force_ascii=False, indent=2
    )
    df_clean = load_and_clean("data/processed/judgments.json")
    save_csv(df_clean)

    click.echo("\n=== 步驟 3/4：統計分析 ===")
    run_analysis(df_clean)
    run_disparity_analysis(df_clean)

    click.echo(f"\n=== 步驟 4/4：啟動網頁（port {port}）===")
    run(port=port)


if __name__ == "__main__":
    cli()
