"""
Extract structured data from Taiwan criminal judgment full text (JFULL).
All text is Traditional Chinese. Sentences are in the 主文 section.
"""
from __future__ import annotations
import re
from pathlib import Path
import json


# ── Section boundaries ────────────────────────────────────────────────────────

SECTION_MAIN = re.compile(r"主\s*[文旨]")
SECTION_FACTS = re.compile(r"事\s*實")
SECTION_REASON = re.compile(r"理\s*由")
SECTION_SIG = re.compile(r"中\s*華\s*民\s*國")


# ── Number helpers (Arabic and Chinese formal/informal numerals) ──────────────

_NP = r"(?:\d+|[壹貳參肆伍陸柒捌玖拾百千]+|[一二三四五六七八九十百千]+)"

_DIGIT_MAP = {
    "零": 0, "〇": 0,
    "一": 1, "壹": 1, "二": 2, "貳": 2, "三": 3, "參": 3,
    "四": 4, "肆": 4, "五": 5, "伍": 5, "六": 6, "陸": 6,
    "七": 7, "柒": 7, "八": 8, "捌": 8, "九": 9, "玖": 9,
}
_UNIT_MAP = {"十": 10, "拾": 10, "百": 100, "千": 1000, "仟": 1000}


def _parse_num(s: str | None) -> int | None:
    """Convert Arabic or Chinese numeral string to int. Returns None on failure."""
    if not s:
        return None
    s = s.strip()
    if s.isdigit():
        return int(s)
    result, current = 0, 0
    for ch in s:
        if ch in _UNIT_MAP:
            result += (current if current else 1) * _UNIT_MAP[ch]
            current = 0
        elif ch in _DIGIT_MAP:
            current = _DIGIT_MAP[ch]
        else:
            return None
    return result + current or None


# ── Metadata patterns ─────────────────────────────────────────────────────────

COURT_RE = re.compile(
    r"(臺灣高等法院(?:(?:臺中|臺南|高雄|花蓮)分院)?"
    r"|最高法院"
    r"|臺灣[^\s,，、。（(法]{1,5}地方法院)"
)
CASE_NO_RE = re.compile(r"(?:民國\s*)?(\d{2,3})\s*年度\s*([^\s第號]{1,8})\s*字第\s*(\d+)\s*號")
DATE_ROC_RE = re.compile(r"中\s*華\s*民\s*國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
JUDGE_RE = re.compile(r"(?:審判長\s*)?法\s*官\s*([一-鿿]{2,4})")

# ── Drug-driving case filter ──────────────────────────────────────────────────

# True when 刑法185條之3 is an actual charged statute in this judgment (not
# just a mention in the defendant's prior criminal history)
DD_CHARGE_RE = re.compile(
    r"(?:係犯|犯|核係|論以|應論以|核被告所為[，,\s]*係犯)"
    r"[^。\n]{0,50}?185條之3"
    r"|185條之3[^。\n]{0,30}?(?:之罪|罪名|罪章|公共危險罪)"
    r"|185條之3第[一二三四]款"
    r"|公共危險罪[^。\n]{0,20}?185條之3",
    re.DOTALL,
)


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
REASONING_SENTENCE_RE = re.compile(
    r"(?:判處被告|量處|諭知|處)\s*有期徒刑\s*"
    r"(?:(" + _NP + r")\s*年(?:\s*(" + _NP + r")\s*月)?|(" + _NP + r")\s*月)",
    re.DOTALL,
)

# Appealed by
DEFENDANT_APPEAL_RE = re.compile(r"上訴人\s*即\s*被告|被告[^\n]{0,5}提起上訴")
PROSECUTOR_APPEAL_RE = re.compile(r"上訴人\s*即\s*檢察官|檢察官[^\n]{0,10}(?:提起)?上訴")


# ── Sentencing patterns ───────────────────────────────────────────────────────

# 有期徒刑 N年M月 / N年 / M月  (captures year group and optional month group,
# or just a month group — two alternatives so both are non-optional)
PRISON_YEAR_MONTH_RE = re.compile(
    r"有期徒刑\s*(" + _NP + r")\s*年(?:\s*(" + _NP + r")\s*月)?"
    r"|有期徒刑\s*(" + _NP + r")\s*月",
    re.DOTALL,
)
# 有期徒刑X個月 (alternative phrasing)
PRISON_MONTHS_ALT_RE = re.compile(r"有期徒刑\s*(" + _NP + r")\s*個月")
# 應執行有期徒刑 (concurrent/merged sentence, take this if present)
MERGED_SENTENCE_RE = re.compile(
    r"應執行有期徒刑\s*(" + _NP + r")\s*年(?:\s*(" + _NP + r")\s*月)?"
    r"|應執行有期徒刑\s*(" + _NP + r")\s*月",
    re.DOTALL,
)
# 拘役 (detention, < 60 days)
DETENTION_RE = re.compile(r"拘役\s*(" + _NP + r")\s*日")
# 緩刑 (suspended)
SUSPENDED_RE = re.compile(r"緩刑\s*(" + _NP + r")\s*(年|月)")
# 罰金 (fine) — amounts typically in Arabic but support Chinese too
FINE_RE = re.compile(
    r"罰金新臺幣\s*([\d,]+)\s*元"
    r"|罰金新臺幣\s*(" + _NP + r")\s*萬(?:\s*(" + _NP + r")\s*千)?元"
)
# 易科罰金 (convertible) — 壹仟/一千/1000 are all common
CONVERTIBLE_RE = re.compile(r"以新臺幣\s*(" + _NP + r")\s*元折算壹日")
# 無罪 / acquittal
ACQUIT_RE = re.compile(r"無罪|公訴不受理|免訴|不受理|不另為無罪之諭知")
# 駕照吊扣/吊銷
LICENSE_SUSPEND_RE = re.compile(r"吊扣駕駛執照\s*(" + _NP + r")\s*(年|月)")
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
    y = _parse_num(years) or 0
    m = _parse_num(months) or 0
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
        "is_drug_driving_case": False,
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

    def _extract_prison(search_text: str) -> int | None:
        # MERGED_SENTENCE_RE: g1=year g2=month OR g3=month-only
        merged_m = MERGED_SENTENCE_RE.search(search_text)
        if merged_m:
            if merged_m.group(1):
                return _to_months(merged_m.group(1), merged_m.group(2))
            return _parse_num(merged_m.group(3))

        terms = []
        # PRISON_YEAR_MONTH_RE: g1=year g2=opt-month OR g3=month-only
        for m in PRISON_YEAR_MONTH_RE.finditer(search_text):
            if m.group(1):
                v = _to_months(m.group(1), m.group(2))
            else:
                v = _parse_num(m.group(3))
            if v:
                terms.append(v)
        # PRISON_MONTHS_ALT_RE: g1=months
        for m in PRISON_MONTHS_ALT_RE.finditer(search_text):
            v = _parse_num(m.group(1))
            if v:
                terms.append(v)
        return max(terms) if terms else None

    result["prison_months"] = _extract_prison(main_text)

    # For upheld appeals, the sentence is in the reasoning section
    if result["prison_months"] is None and result["appeal_outcome"] == "上訴駁回":
        search_text = reason_text if reason_text else text
        for m in REASONING_SENTENCE_RE.finditer(search_text):
            if m.group(1):
                v = _to_months(m.group(1), m.group(2))
            else:
                v = _parse_num(m.group(3))
            if v:
                result["prison_months"] = v
                break

    # Detention (拘役) — mutually exclusive with prison
    det_m = DETENTION_RE.search(main_text)
    if det_m and result["prison_months"] is None:
        result["detention_days"] = _parse_num(det_m.group(1))

    # ── Suspended sentence ────────────────────────────────────────────────────

    susp_m = SUSPENDED_RE.search(text)
    if susp_m:
        result["sentence_suspended"] = True
        dur = _parse_num(susp_m.group(1)) or 0
        unit = susp_m.group(2)
        result["suspended_duration_months"] = dur * 12 if unit == "年" else dur

    # ── Fine ──────────────────────────────────────────────────────────────────

    fine_m = FINE_RE.search(main_text)
    if fine_m:
        if fine_m.group(1):
            result["fine_ntd"] = int(fine_m.group(1).replace(",", ""))
        else:
            wan = (_parse_num(fine_m.group(2)) or 0) * 10000
            qian = (_parse_num(fine_m.group(3)) or 0) * 1000
            result["fine_ntd"] = wan + qian

    conv_m = CONVERTIBLE_RE.search(main_text)
    if conv_m:
        result["convertible_per_day"] = _parse_num(conv_m.group(1))

    # ── License ───────────────────────────────────────────────────────────────

    lic_m = LICENSE_SUSPEND_RE.search(text)
    if lic_m:
        result["license_action"] = "吊扣"
        dur = _parse_num(lic_m.group(1)) or 0
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

    # ── Drug-driving case flag ────────────────────────────────────────────────

    case_tw = result.get("case_type_word") or ""
    # Traffic-type cases (交*) are drug/alcohol driving cases
    is_traffic = "交" in case_tw
    # 毒聲/毒抗 are drug-rehab procedural rulings, never drug driving
    is_tox_procedural = case_tw.startswith("毒")
    # For non-traffic types, require 185條之3 to appear as a direct charge
    result["is_drug_driving_case"] = (
        is_traffic or (not is_tox_procedural and bool(DD_CHARGE_RE.search(text)))
    )

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
