#!/usr/bin/env python3
"""
Monthly batch scraper: scrape → parse → append to judgments.json

Searches each keyword × each month independently; deduplicates by JID.

Usage:
  # All keywords, specific months
  python scripts/scrape_monthly.py 2026-01 2026-02 2026-03 2026-04

  # Single keyword override (for testing or resuming one keyword)
  python scripts/scrape_monthly.py --keyword "海洛因 不能安全駕駛" 2026-01 2026-02
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from scraper.utils import make_session, polite_sleep
from scraper.judicial_scraper import search_year, fetch_judgment_text
from scraper.parser import parse_judgment

ROC_OFFSET = 1911

# All drug-driving keywords to search.  Each is run independently per month.
# Order matters: more common drugs first so progress is visible early.
ALL_KEYWORDS = [
    "甲基安非他命 不能安全駕駛",   # meth (class 2) — already run
    "海洛因 不能安全駕駛",          # heroin (class 1)
    "愷他命 不能安全駕駛",          # ketamine (class 3)
    "施用毒品 不能安全駕駛",        # generic catch-all (covers MDMA, cannabis, etc.)
]

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
PROGRESS_FILE = RAW_DIR / "progress.json"

MONTH_LAST_DAY = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                  7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def last_day_of(year_ce: int, month: int) -> int:
    if month == 2 and (year_ce % 4 == 0 and (year_ce % 100 != 0 or year_ce % 400 == 0)):
        return 29
    return MONTH_LAST_DAY[month]


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"downloaded": [], "failed": []}


def save_progress(p: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def scrape_month(session, keyword: str, year_ce: int, month: int) -> list[dict]:
    roc = year_ce - ROC_OFFSET
    last = last_day_of(year_ce, month)
    roc_start = f"{roc:03d}{month:02d}01"
    roc_end = f"{roc:03d}{month:02d}{last:02d}"

    print(f"\n{'='*60}")
    print(f"  搜尋 {year_ce}-{month:02d}  ROC {roc_start}~{roc_end}")
    print(f"  關鍵字: {keyword!r}")
    print(f"{'='*60}")

    meta_list = search_year(session, keyword, year_ce, roc_start, roc_end)

    cap_warn = "⚠️  已達 500 筆上限，可能有遺漏" if len(meta_list) >= 500 else "✅ 未達上限"
    print(f"  搜尋結果: {len(meta_list)} 筆  {cap_warn}")
    return meta_list


def download_month(session, meta_list: list[dict], year_ce: int, month: int) -> list[dict]:
    month_dir = RAW_DIR / str(year_ce) / f"{month:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)

    progress = load_progress()
    downloaded_set = set(progress["downloaded"])

    new_items = [m for m in meta_list if m["jid"] not in downloaded_set]
    skip = len(meta_list) - len(new_items)
    print(f"  下載: {len(new_items)} 筆（跳過已有 {skip} 筆）")

    saved_docs = []
    for m in tqdm(new_items, desc=f"  {year_ce}-{month:02d}"):
        polite_sleep(1.5, 2.5)
        doc = fetch_judgment_text(session, m["url"], m["jid"])
        if doc:
            doc.update({k: v for k, v in m.items() if k not in doc})
            doc["year_ce"] = year_ce
            safe_jid = m["jid"].replace(",", "_").replace("/", "_")[:80]
            out_path = month_dir / f"{safe_jid}.json"
            out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            downloaded_set.add(m["jid"])
            progress["downloaded"].append(m["jid"])
            saved_docs.append(doc)
        else:
            if m["jid"] not in progress["failed"]:
                progress["failed"].append(m["jid"])

        if len(saved_docs) % 50 == 0 and saved_docs:
            save_progress(progress)

    save_progress(progress)
    print(f"  ✅ 本月下載完成：{len(saved_docs)} 筆新資料")
    return saved_docs


def parse_docs(docs: list[dict]) -> list[dict]:
    parsed = []
    excluded = 0
    for doc in docs:
        try:
            r = parse_judgment(doc)
            if not r.get("is_drug_driving_case", True):
                excluded += 1
                continue
            parsed.append(r)
        except Exception as e:
            print(f"  [WARN] parse error {doc.get('jid','?')}: {e}", file=sys.stderr)
    warn_count = sum(1 for r in parsed if r.get("parse_warnings"))
    if excluded:
        print(f"  [filter] 排除 {excluded} 筆非毒駕案件")
    print(f"  解析完成：{len(parsed)} 筆（含警告 {warn_count} 筆）")
    return parsed


def append_to_processed(new_records: list[dict]) -> int:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_file = PROCESSED_DIR / "judgments.json"

    existing = []
    if out_file.exists():
        existing = json.loads(out_file.read_text(encoding="utf-8"))

    existing_jids = {r.get("jid") for r in existing}
    to_add = [r for r in new_records if r.get("jid") not in existing_jids]
    all_records = existing + to_add

    out_file.write_text(
        json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  已寫入 judgments.json：新增 {len(to_add)} 筆，累計 {len(all_records)} 筆")
    return len(to_add)


def run(keywords: list[str], months: list[tuple[int, int]]) -> None:
    session = make_session()
    grand_total = 0

    for keyword in keywords:
        print(f"\n{'#'*60}")
        print(f"  關鍵字批次: {keyword!r}")
        print(f"{'#'*60}")
        kw_total = 0

        for year_ce, month in months:
            meta = scrape_month(session, keyword, year_ce, month)
            if not meta:
                print("  無結果，跳過")
                continue

            polite_sleep(2.0, 3.0)
            docs = download_month(session, meta, year_ce, month)

            if docs:
                parsed = parse_docs(docs)
                added = append_to_processed(parsed)
                kw_total += added

            polite_sleep(3.0, 5.0)

        print(f"\n  關鍵字 {keyword!r} 完成，新增 {kw_total} 筆")
        grand_total += kw_total
        polite_sleep(5.0, 8.0)

    print(f"\n{'='*60}")
    print(f"  全部批次完成，共新增 {grand_total} 筆解析資料")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Monthly drug-driving judgment scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # All keywords, four months
  python scripts/scrape_monthly.py 2026-01 2026-02 2026-03 2026-04

  # Single keyword override
  python scripts/scrape_monthly.py --keyword "海洛因 不能安全駕駛" 2026-01 2026-02

  # Skip already-completed first keyword, run only remaining
  python scripts/scrape_monthly.py --skip-first 1 2026-01 2026-02
        """,
    )
    parser.add_argument(
        "months",
        nargs="+",
        metavar="YYYY-MM",
        help="Months to scrape, e.g. 2026-01 2026-02",
    )
    parser.add_argument(
        "--keyword",
        metavar="KW",
        help="Override: scrape only this keyword (instead of all ALL_KEYWORDS)",
    )
    parser.add_argument(
        "--skip-first",
        type=int,
        default=0,
        metavar="N",
        help="Skip the first N keywords in ALL_KEYWORDS (useful for resuming)",
    )

    args = parser.parse_args()

    month_list = []
    for ym in args.months:
        try:
            y, m = ym.split("-")
            month_list.append((int(y), int(m)))
        except ValueError:
            print(f"Bad format: {ym!r}，請使用 YYYY-MM")
            sys.exit(1)

    if args.keyword:
        keywords = [args.keyword]
    else:
        keywords = ALL_KEYWORDS[args.skip_first:]

    print(f"執行月份：{month_list}")
    print(f"執行關鍵字：{keywords}")
    run(keywords, month_list)
