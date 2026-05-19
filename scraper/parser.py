"""
Extract structured data from Taiwan criminal judgment full text (JFULL).
All text is Traditional Chinese. Sentences are in the 主文 section.
"""
import re
from pathlib import Path
import json


# ── Section boundaries ────────────────────────────────────────────────────────

SECTION_MAIN = re.compile(r"主\s*[文旨]")
SECTION_FACTS = re.compile(r"事\s*實")
SECTION_REASON = re.compile(r"理\s*由")
SECTION_SIG = re.compile(r"中\s*華\s*民\s*國")


# ── Metadata patterns ─────────────────────────────────────────────────────────

COURT_RE = re.compile(
    r"(臺灣高等法院(?:(?:臺中|臺南|高雄|花蓮)分院)?"
    r"|最高法院"
    r"|臺灣[^\s,，、。（(法]{1,5}地方法院)"
)
CASE_NO_RE = re.compile(r"(?:民國\s*)?(\d{2,3})\s*年度\s*([^\s第號]{1,8})\s*字第\s*(\d+)\s*號")
DATE_ROC_RE = re.compile(r"中\s*華\s*民\s*國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
JUDGE_RE = re.compile(r"(?:審判長\s*)?法\s*官\s*([一-鿿]{2,4})")

# ── Appeal / cross-instance patterns ──────────────────────────────────────────

# Extract original case reference in appeal judgments: "不服XX法院 YYY年度ZZZ字第NNN號"
ORIGINAL_CASE_RE = re.compile(
    r"不服(臺灣[^\s,，、。（(]{2,12}(?:地方|高等)法院|最高法院)[^,，\n]{0,30}?"
    r"(\d{2,3})年度([^\s第號,，]{1,10})字第(\d+)號"
)

# Appeal outcome patterns (search 主文)
APPEAL_UPHELD_RE = re.compile(r"上訴駁回|駁回上訴")
APPEAL_OVERTURN_RE = re.compile(r"撤銷原判決[^。\n]{0,30}有期徒刑|撤銷.*?改判")
APPEAL_REMAND_RE = re.compile(r"撤銷.*?發回[更原]?審|發回更審")

# When appeal is upheld, original sentence is mentioned in reasoning
# Match: "判處被告有期徒刑X月", "量處有期徒刑X月", "處有期徒刑X月"
REASONING_SENTENCE_RE = re.compile(
    r"(?:判處被告|量處|諭知|處)\s*有期徒刑(?:(\d+)年)?(?:(\d+)月)?"
)

# Appealed by
DEFENDANT_APPEAL_RE = re.compile(r"上訴人\s*即\s*被告|被告[^\n]{0,5}提起上訴")
PROSECUTOR_APPEAL_RE = re.compile(r"上訴人\s*即\s*檢察官|檢察官[^\n]{0,10}(?:提起)?上訴")


# ── Sentencing patterns ───────────────────────────────────────────────────────

# 有期徒刑 X 年 X 月 (prison term)
PRISON_YEAR_MONTH_RE = re.compile(r"有期徒刑(?:(\d+)年)?(?:(\d+)月)?")
# 有期徒刑X個月 (alternative phrasing)
PRISON_MONTHS_ALT_RE = re.compile(r"有期徒刑(\d+)個月")
# 應執行有期徒刑 (concurrent/merged sentence, take this if present)
MERGED_SENTENCE_RE = re.compile(r"應執行有期徒刑(?:(\d+)年)?(?:(\d+)月)?")
# 拘役 (detention, < 60 days)
DETENTION_RE = re.compile(r"拘役\s*(\d+)\s*日")
# 緩刑 (suspended)
SUSPENDED_RE = re.compile(r"緩刑\s*(\d+)\s*(年|月)")
# 罰金 (fine)
FINE_RE = re.compile(r"罰金新臺幣\s*([\d,]+)\s*元|罰金新臺幣\s*(\d+)\s*萬(?:\s*(\d+)\s*千)?元")
# 易科罰金 (convertible)
CONVERTIBLE_RE = re.compile(r"以新臺幣\s*(\d+)\s*元折算壹日")
# 無罪 / acquittal
ACQUIT_RE = re.compile(r"無罪|公訴不受理|免訴|不受理|不另為無罪之諭知")
# 駕照吊扣/吊銷
LICENSE_SUSPEND_RE = re.compile(r"吊扣駕駛執照\s*(\d+)\s*(年|月)")
LICENSE_REVOKE_RE = re.compile(r"吊銷駕駛執照")


# ── Drug patterns ─────────────────────────────────────────────────────────────

DRUG_CLASS_RE = re.compile(r"第\s*(一|二|三|四)\s*級\s*毒品")
CLASS_MAP = {"一": 1, "二": 2, "三": 3, "四": 4}

SUBSTANCE_KEYWORDS = {
    "甲基安非他命": "methamphetamine",
    "安非他命": "amphetamine",
    "海洛因": "heroin",
    "嗎啡": "morphine",
    "大麻": "cannabis",
    "愷他命": "ketamine",
    "氯胺酮": "ketamine",
    "MDMA": "MDMA",
    "搖頭丸": "MDMA",
    "可待因": "codeine",
    "芬太尼": "fentanyl",
    "K他命": "ketamine",
    "安眠藥": "sedative",
}

BLOOD_CONC_RE = re.compile(
    r"血(?:液中|中).*?(\d+(?:\.\d+)?)\s*(?:ng/mL|μg/mL|ug/mL|mg/L|ng/ml)"
)
URINE_POS_RE = re.compile(r"尿液.*?(?:呈陽性|驗出|檢出|陽性反應)")


# ── Aggravating factor patterns ───────────────────────────────────────────────

REPEAT_RE = re.compile(r"累犯")
ACCIDENT_RE = re.compile(r"肇(?:事|致)|發生車禍|撞擊|碰撞")
DEATH_RE = re.compile(r"(?:致|造成|肇致).*?(?:死亡|當場死亡|死者)")
INJURY_RE = re.compile(r"(?:致|造成|肇致).*?(?:受傷|傷害|傷亡)")
SERIOUS_INJURY_RE = re.compile(r"重(?:傷|大傷害|傷害罪)")
GUILTY_PLEA_RE = re.compile(r"坦承|自白|認罪|承認犯行|坦認|認罪協商")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _roc_to_ce(roc_year: int) -> int:
    return roc_year + 1911


def _to_months(years: str | None, months: str | None) -> int | None:
    y = int(years) if years else 0
    m = int(months) if months else 0
    total = y * 12 + m
    return total if total > 0 else None


def _extract_section(text: str, start_re: re.Pattern, end_re: re.Pattern) -> str:
    """Extract text between two section markers."""
    start = start_re.search(text)
    if not start:
        return ""
    end = end_re.search(text, start.end())
    if end:
        return text[start.end():end.start()]
    return text[start.end():]


def parse_judgment(raw: dict) -> dict:
    """Parse a raw judgment dict and return structured data."""
    text = raw.get("full_text", "") or raw.get("JFULL", "")
    jid = raw.get("jid", "")
    year_ce = raw.get("year_ce")

    result: dict = {
        "jid": jid,
        "year_ce": year_ce,
        "court": None,
        "case_no": None,
        "judgment_date": None,
        "judge": None,
        # Sentence
        "prison_months": None,
        "detention_days": None,
        "sentence_suspended": False,
        "suspended_duration_months": None,
        "fine_ntd": None,
        "convertible_per_day": None,
        "acquitted": False,
        "license_action": None,
        "license_months": None,
        # Drug
        "drug_class": None,
        "drug_substance": None,
        "blood_conc": None,
        "urine_positive": False,
        # Aggravating
        "is_repeat_offender": False,
        "caused_accident": False,
        "caused_death": False,
        "caused_injury": False,
        "caused_serious_injury": False,
        "guilty_plea": False,
        # Cross-instance / appeal
        "court_level": None,
        "case_instance": None,
        "case_type_word": None,
        "original_court_ref": None,
        "original_case_no_ref": None,
        "appeal_outcome": None,
        "appealed_by": None,
        # Quality
        "parse_warnings": [],
    }

    if not text:
        result["parse_warnings"].append("empty_text")
        return result

    # ── Metadata ─────────────────────────────────────────────────────────────

    court_m = COURT_RE.search(text)
    if court_m:
        result["court"] = court_m.group(1)

    # Court level and case instance
    court_val = result["court"] or ""
    if "地方法院" in court_val:
        result["court_level"] = 1
        result["case_instance"] = "一審"
    elif "高等法院" in court_val:
        result["court_level"] = 2
        result["case_instance"] = "二審"
    elif "最高法院" in court_val:
        result["court_level"] = 3
        result["case_instance"] = "三審"

    case_m = CASE_NO_RE.search(text)
    if case_m:
        roc_year, word, no = case_m.groups()
        result["case_no"] = f"{roc_year}年{word}字第{no}號"
        result["case_type_word"] = word
        if year_ce is None:
            result["year_ce"] = _roc_to_ce(int(roc_year))

    # Original case reference (for appeal judgments)
    orig_m = ORIGINAL_CASE_RE.search(text)
    if orig_m:
        result["original_court_ref"] = orig_m.group(1)
        result["original_case_no_ref"] = (
            f"{orig_m.group(2)}年{orig_m.group(3)}字第{orig_m.group(4)}號"
        )

    date_m = DATE_ROC_RE.findall(text)
    if date_m:
        # Use the last occurrence (signature date)
        roc_y, mon, day = date_m[-1]
        try:
            ce_y = _roc_to_ce(int(roc_y))
            result["judgment_date"] = f"{ce_y}-{int(mon):02d}-{int(day):02d}"
        except ValueError:
            result["parse_warnings"].append("bad_date")

    judges = JUDGE_RE.findall(text)
    if judges:
        result["judge"] = judges[0]

    # ── Extract 主文 section for sentencing ───────────────────────────────────

    main_text = _extract_section(text, SECTION_MAIN, SECTION_FACTS)
    if not main_text:
        main_text = text[:2000]  # fallback: first 2000 chars

    # ── Extract 理由 (reasoning) section ─────────────────────────────────────

    reason_text = _extract_section(text, SECTION_REASON, SECTION_SIG)

    # ── Acquittal check ───────────────────────────────────────────────────────

    if ACQUIT_RE.search(main_text):
        result["acquitted"] = True
        # Some acquittals still have partial sentences for other charges; continue

    # ── Appeal outcome (search 主文) ──────────────────────────────────────────

    if APPEAL_REMAND_RE.search(main_text):
        result["appeal_outcome"] = "撤銷發回"
    elif APPEAL_OVERTURN_RE.search(main_text):
        result["appeal_outcome"] = "撤銷改判"
    elif APPEAL_UPHELD_RE.search(main_text):
        result["appeal_outcome"] = "上訴駁回"

    # ── Appealed by ───────────────────────────────────────────────────────────

    def_appeal = bool(DEFENDANT_APPEAL_RE.search(text))
    pros_appeal = bool(PROSECUTOR_APPEAL_RE.search(text))
    if def_appeal and pros_appeal:
        result["appealed_by"] = "雙方"
    elif def_appeal:
        result["appealed_by"] = "被告"
    elif pros_appeal:
        result["appealed_by"] = "檢察官"

    # ── Prison term ───────────────────────────────────────────────────────────

    # Prefer "應執行" (merged concurrent sentence)
    merged_m = MERGED_SENTENCE_RE.search(main_text)
    if merged_m:
        result["prison_months"] = _to_months(merged_m.group(1), merged_m.group(2))
    else:
        # Collect all individual prison terms, take max
        terms = []
        for m in PRISON_YEAR_MONTH_RE.finditer(main_text):
            months = _to_months(m.group(1), m.group(2))
            if months:
                terms.append(months)
        for m in PRISON_MONTHS_ALT_RE.finditer(main_text):
            terms.append(int(m.group(1)))
        if terms:
            result["prison_months"] = max(terms)

    # Fix: when appeal is upheld, original sentence is in the reasoning section
    if result["prison_months"] is None and result["appeal_outcome"] == "上訴駁回":
        search_text = reason_text if reason_text else text
        for m in REASONING_SENTENCE_RE.finditer(search_text):
            months = _to_months(m.group(1), m.group(2))
            if months and months > 0:
                result["prison_months"] = months
                break

    # Detention (拘役) — mutually exclusive with prison
    det_m = DETENTION_RE.search(main_text)
    if det_m and result["prison_months"] is None:
        result["detention_days"] = int(det_m.group(1))

    # ── Suspended sentence ────────────────────────────────────────────────────

    susp_m = SUSPENDED_RE.search(text)
    if susp_m:
        result["sentence_suspended"] = True
        dur = int(susp_m.group(1))
        unit = susp_m.group(2)
        result["suspended_duration_months"] = dur * 12 if unit == "年" else dur

    # ── Fine ──────────────────────────────────────────────────────────────────

    fine_m = FINE_RE.search(main_text)
    if fine_m:
        if fine_m.group(1):
            result["fine_ntd"] = int(fine_m.group(1).replace(",", ""))
        else:
            wan = int(fine_m.group(2)) * 10000
            qian = int(fine_m.group(3)) * 1000 if fine_m.group(3) else 0
            result["fine_ntd"] = wan + qian

    conv_m = CONVERTIBLE_RE.search(main_text)
    if conv_m:
        result["convertible_per_day"] = int(conv_m.group(1))

    # ── License ───────────────────────────────────────────────────────────────

    lic_m = LICENSE_SUSPEND_RE.search(text)
    if lic_m:
        result["license_action"] = "吊扣"
        dur = int(lic_m.group(1))
        unit = lic_m.group(2)
        result["license_months"] = dur * 12 if unit == "年" else dur
    elif LICENSE_REVOKE_RE.search(text):
        result["license_action"] = "吊銷"

    # ── Drug ──────────────────────────────────────────────────────────────────

    classes = [CLASS_MAP[m] for m in DRUG_CLASS_RE.findall(text)]
    if classes:
        result["drug_class"] = min(classes)  # most serious (lowest number = higher class)

    for keyword, eng in SUBSTANCE_KEYWORDS.items():
        if keyword in text:
            result["drug_substance"] = keyword
            break

    blood_m = BLOOD_CONC_RE.search(text)
    if blood_m:
        result["blood_conc"] = float(blood_m.group(1))

    if URINE_POS_RE.search(text):
        result["urine_positive"] = True

    # ── Aggravating factors (search full text) ────────────────────────────────

    result["is_repeat_offender"] = bool(REPEAT_RE.search(text))
    result["caused_accident"] = bool(ACCIDENT_RE.search(text))
    result["caused_death"] = bool(DEATH_RE.search(text))
    result["caused_injury"] = bool(INJURY_RE.search(text))
    result["caused_serious_injury"] = bool(SERIOUS_INJURY_RE.search(text))
    result["guilty_plea"] = bool(GUILTY_PLEA_RE.search(text))

    # ── Quality check ─────────────────────────────────────────────────────────

    if result["prison_months"] is None and result["detention_days"] is None and not result["acquitted"]:
        result["parse_warnings"].append("no_sentence_found")
    if result["drug_class"] is None:
        result["parse_warnings"].append("no_drug_class")
    if result["court"] is None:
        result["parse_warnings"].append("no_court")

    return result


def parse_all(raw_dir: str = "data/raw", out_path: str = "data/processed/judgments.json") -> list[dict]:
    """Parse all raw JSON files and write structured output."""
    raw_root = Path(raw_dir)
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    all_parsed = []
    raw_files = sorted(raw_root.rglob("*.json"))
    # Exclude progress file
    raw_files = [f for f in raw_files if f.name != "progress.json"]

    print(f"解析 {len(raw_files)} 個判決書檔案…")
    for fpath in raw_files:
        try:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
            parsed = parse_judgment(raw)
            all_parsed.append(parsed)
        except Exception as e:
            print(f"  [WARN] {fpath.name}: {e}")

    out_file.write_text(
        json.dumps(all_parsed, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"解析完成，共 {len(all_parsed)} 筆，輸出至 {out_path}")
    return all_parsed
