"""
Scraper for Taiwan's Judicial Yuan verdict search system.
Target: https://judgment.judicial.gov.tw/FJUD/default.aspx

Searches for drug-driving (毒駕) criminal cases (刑法185-3) over the past 10 years.
Results are stored as JSON files under data/raw/<year>/<case_id>.json.
Supports resumable scraping via data/raw/progress.json.
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from tqdm import tqdm

from scraper.utils import load_progress, make_session, polite_sleep, safe_get, safe_post, save_progress

BASE_URL = "https://judgment.judicial.gov.tw/FJUD"
SEARCH_URL = f"{BASE_URL}/Default_AD.aspx"     # advanced search form
RESULTS_URL = f"{BASE_URL}/qryresultlst.aspx"  # iframe results list

# ROC year = CE year - 1911
ROC_OFFSET = 1911

# Search queries: primary keyword + law article filter
SEARCH_KEYWORDS = [
    "不能安全駕駛 毒",
    "毒駕 刑法第185條之3",
    "吸毒 駕車",
]

RAW_DIR = Path("data/raw")


def ce_to_roc(year: int) -> int:
    return year - ROC_OFFSET


def year_range_roc(start_ce: int = 2016, end_ce: int = 2026):
    """Yield (roc_start, roc_end) pairs for each year in range."""
    for y in range(start_ce, end_ce + 1):
        roc = ce_to_roc(y)
        yield y, f"{roc}0101", f"{roc}1231"


def _extract_viewstate(html: str) -> dict:
    """Extract ASP.NET hidden form fields needed for POST."""
    soup = BeautifulSoup(html, "lxml")
    fields = {}
    for name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        tag = soup.find("input", {"name": name})
        if tag:
            fields[name] = tag.get("value", "")
    return fields


def _parse_result_list(html: str) -> list[dict]:
    """Parse qryresultlst.aspx and return judgment metadata list."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for a in soup.select("a.hlTitle_scroll[href*='data.aspx']"):
        href = a["href"]
        id_match = re.search(r"[?&]id=([^&]+)", href)
        if not id_match:
            continue
        jid = id_match.group(1)
        full_url = f"{BASE_URL}/{href}" if not href.startswith("http") else href

        row = a.find_parent("tr")
        cells = row.find_all("td") if row else []
        date_text = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        cause_text = cells[3].get_text(strip=True) if len(cells) > 3 else ""

        results.append({
            "jid": jid,
            "url": full_url,
            "title": a.get_text(strip=True),
            "court": "",        # extracted by parser from full text
            "date_raw": date_text,
            "case_no": cause_text,
        })

    return results


def _count_pages(html: str) -> int:
    """Return total pages from qryresultlst.aspx pagination."""
    soup = BeautifulSoup(html, "lxml")
    # "最末頁" link contains the last page number
    last_link = soup.find("a", string=re.compile(r"最末頁"))
    if last_link and last_link.get("href"):
        m = re.search(r"page=(\d+)", last_link["href"])
        if m:
            return int(m.group(1))
    # Fallback: total count ÷ 20
    count_div = soup.find(id="result-count")
    if count_div:
        m = re.search(r"(\d+)", count_div.get_text())
        if m:
            return (int(m.group(1)) + 19) // 20
    return 1


def fetch_judgment_text(session, url: str, jid: str) -> dict | None:
    """Download full text of a single judgment."""
    try:
        polite_sleep(1.0, 2.5)
        resp = safe_get(session, url)
        soup = BeautifulSoup(resp.text, "lxml")

        # Full text is usually in a div with id="jud" or class containing "jud"
        content_div = (
            soup.find("div", id="jud")
            or soup.find("div", class_=re.compile(r"jud"))
            or soup.find("pre")
        )
        full_text = content_div.get_text("\n") if content_div else soup.get_text("\n")

        # Extract court and case number from header
        header = soup.find("h4") or soup.find("h3")
        header_text = header.get_text(strip=True) if header else ""

        return {
            "jid": jid,
            "url": url,
            "header": header_text,
            "full_text": full_text,
        }
    except Exception as e:
        print(f"  [WARN] Failed to fetch {jid}: {e}", file=sys.stderr)
        return None


def search_year(session, keyword: str, year_ce: int, roc_start: str, roc_end: str) -> list[dict]:
    """Search for judgments matching keyword in a given year, returns metadata list.

    Flow:
      1. POST Default_AD.aspx → get QID
      2. GET qryresultlst.aspx?q=<QID>&page=N for each page
    """
    results = []
    try:
        # roc_start / roc_end are like "1130101" → split into y/m/d
        roc_y_start, roc_m_start, roc_d_start = roc_start[:3], roc_start[3:5].lstrip("0") or "1", roc_start[5:].lstrip("0") or "1"
        roc_y_end, roc_m_end, roc_d_end = roc_end[:3], roc_end[3:5].lstrip("0") or "12", roc_end[5:].lstrip("0") or "31"

        resp = safe_get(session, SEARCH_URL)
        vs_fields = _extract_viewstate(resp.text)
        polite_sleep()

        form_data = {
            **vs_fields,
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "jud_court": "",
            "jud_sys": "M",
            "jud_kw": keyword,
            "dy1": roc_y_start, "dm1": roc_m_start, "dd1": roc_d_start,
            "dy2": roc_y_end,   "dm2": roc_m_end,   "dd2": roc_d_end,
            "judtype": "JUDBOOK",
            "whosub": "0",
            "ctl00$cp_content$btnQry": "送出查詢",
        }
        resp = safe_post(session, SEARCH_URL, data=form_data)
        polite_sleep()

        qid_tag = BeautifulSoup(resp.text, "lxml").find("input", id="hidQID")
        if not qid_tag or not qid_tag.get("value"):
            print(f"  [WARN] 搜尋 {year_ce}/{keyword!r} 未取得 QID", file=sys.stderr)
            return results
        qid = qid_tag["value"]

        # Fetch first results page
        r = safe_get(session, f"{RESULTS_URL}?ty=JUDBOOK&q={qid}")
        polite_sleep()
        results.extend(_parse_result_list(r.text))

        total_pages = _count_pages(r.text)
        for page in range(2, min(total_pages + 1, 51)):  # cap 50 pages (~1000) per keyword/year
            polite_sleep(2.0, 4.0)
            r = safe_get(session, f"{RESULTS_URL}?q={qid}&sort=DS&page={page}")
            results.extend(_parse_result_list(r.text))

    except Exception as e:
        print(f"  [ERROR] search_year failed: {e}", file=sys.stderr)

    return results


def scrape(start_year: int = 2016, end_year: int = 2026) -> None:
    """Main entry point: scrape all drug-driving judgments and save to data/raw/."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()
    downloaded_ids = set(progress["downloaded"])

    session = make_session()
    total_new = 0

    for year_ce, roc_start, roc_end in year_range_roc(start_year, end_year):
        year_dir = RAW_DIR / str(year_ce)
        year_dir.mkdir(exist_ok=True)

        print(f"\n=== {year_ce} 年 ({roc_start} ~ {roc_end}) ===")

        # Collect metadata from all keywords for this year
        all_meta: dict[str, dict] = {}
        for keyword in SEARCH_KEYWORDS:
            print(f"  搜尋關鍵字: {keyword!r}")
            meta_list = search_year(session, keyword, year_ce, roc_start, roc_end)
            for m in meta_list:
                if m["jid"]:
                    all_meta[m["jid"]] = m

        print(f"  找到 {len(all_meta)} 筆（去重後）")

        new_ids = [jid for jid in all_meta if jid not in downloaded_ids]
        print(f"  尚未下載: {len(new_ids)} 筆")

        for jid in tqdm(new_ids, desc=f"  下載 {year_ce}"):
            meta = all_meta[jid]
            out_path = year_dir / f"{jid.replace(',', '_').replace('/', '_')}.json"

            doc = fetch_judgment_text(session, meta["url"], jid)
            if doc:
                doc.update({k: v for k, v in meta.items() if k not in doc})
                doc["year_ce"] = year_ce
                out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
                downloaded_ids.add(jid)
                progress["downloaded"].append(jid)
                total_new += 1

                # Save progress every 50 judgments
                if total_new % 50 == 0:
                    save_progress(progress)
            else:
                if jid not in progress["failed"]:
                    progress["failed"].append(jid)

        save_progress(progress)

    print(f"\n完成。本次共下載 {total_new} 筆新判決書。")
