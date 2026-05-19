"""
Generate synthetic drug-driving judgment data for dashboard testing.
Mimics the real data structure produced by scraper/parser.py.
"""
import json
import random
from pathlib import Path
from datetime import date, timedelta

random.seed(42)

COURTS = [
    "臺灣臺北地方法院", "臺灣士林地方法院", "臺灣新北地方法院",
    "臺灣桃園地方法院", "臺灣新竹地方法院", "臺灣臺中地方法院",
    "臺灣臺南地方法院", "臺灣高雄地方法院", "臺灣屏東地方法院",
    "臺灣花蓮地方法院", "臺灣宜蘭地方法院", "臺灣彰化地方法院",
]

JUDGES_PER_COURT = {c: [f"法官{chr(65+i)}{chr(65+j)}" for i in range(3) for j in range(4)]
                    for c in COURTS}

SUBSTANCES = ["甲基安非他命", "海洛因", "大麻", "愷他命", "MDMA", None]
SUBSTANCE_WEIGHTS = [0.60, 0.10, 0.10, 0.12, 0.04, 0.04]

DRUG_CLASS_BY_SUBSTANCE = {
    "甲基安非他命": 2, "海洛因": 1, "大麻": 2,
    "愷他命": 3, "MDMA": 2, None: 2,
}

BASE_DATE = date(2016, 1, 1)
DATE_RANGE = (date(2026, 5, 1) - BASE_DATE).days


def random_date(year_ce: int) -> str:
    start = date(year_ce, 1, 1)
    end = date(year_ce, 12, 31)
    delta = (end - start).days
    d = start + timedelta(days=random.randint(0, delta))
    return d.isoformat()


def generate_sentence(drug_class, repeat, death, serious_injury, injury, court, year):
    # Base sentence by drug class
    base = {1: 24, 2: 6, 3: 4, 4: 2}[drug_class]

    # Court-level bias (simulate disparity)
    court_bias = {
        "臺灣臺北地方法院": 2, "臺灣士林地方法院": 0,
        "臺灣新北地方法院": 1, "臺灣桃園地方法院": -1,
        "臺灣新竹地方法院": -2, "臺灣臺中地方法院": 3,
        "臺灣臺南地方法院": -1, "臺灣高雄地方法院": 1,
        "臺灣屏東地方法院": -3, "臺灣花蓮地方法院": -2,
        "臺灣宜蘭地方法院": -1, "臺灣彰化地方法院": 0,
    }.get(court, 0)

    # Temporal trend: slightly harsher each year
    year_bump = (year - 2016) * 0.3

    # Aggravating factors
    sev_bump = 0
    if death:
        sev_bump = 48
    elif serious_injury:
        sev_bump = 18
    elif injury:
        sev_bump = 8

    repeat_bump = 6 if repeat else 0
    noise = random.gauss(0, 3)

    months = max(1, round(base + court_bias + year_bump + sev_bump + repeat_bump + noise))
    return months


def generate_sample(n: int = 3000) -> list[dict]:
    records = []
    for i in range(n):
        year = random.randint(2016, 2025)
        court = random.choice(COURTS)
        judge = random.choice(JUDGES_PER_COURT[court])
        substance = random.choices(SUBSTANCES, weights=SUBSTANCE_WEIGHTS)[0]
        drug_class = DRUG_CLASS_BY_SUBSTANCE[substance]

        repeat = random.random() < 0.28
        death = random.random() < 0.02
        serious_injury = (not death) and random.random() < 0.03
        injury = (not death and not serious_injury) and random.random() < 0.08
        accident = death or serious_injury or injury or random.random() < 0.05

        prison_months = generate_sentence(
            drug_class, repeat, death, serious_injury, injury, court, year
        )
        acquitted = random.random() < 0.01
        suspended = (not acquitted) and (not death) and random.random() < (
            0.35 if drug_class >= 2 and not repeat else 0.15
        )

        records.append({
            "jid": f"TPD,{year - 1911},交簡,{i+1:05d},{year}0101,1",
            "year_ce": year,
            "court": court,
            "case_no": f"{year - 1911}年交簡字第{i+1}號",
            "judgment_date": random_date(year),
            "judge": judge,
            "prison_months": None if acquitted else prison_months,
            "detention_days": None,
            "sentence_suspended": suspended,
            "suspended_duration_months": random.choice([24, 36]) if suspended else None,
            "fine_ntd": random.choice([15000, 20000, 30000, None]),
            "convertible_per_day": 1000 if not suspended and not acquitted else None,
            "acquitted": acquitted,
            "license_action": random.choice(["吊扣", "吊銷", None, None, None]),
            "license_months": random.choice([12, 24, None]),
            "drug_class": drug_class,
            "drug_substance": substance,
            "blood_conc": round(random.uniform(50, 5000), 1) if random.random() < 0.4 else None,
            "urine_positive": random.random() < 0.85,
            "is_repeat_offender": repeat,
            "caused_accident": accident,
            "caused_death": death,
            "caused_injury": injury or serious_injury,
            "caused_serious_injury": serious_injury,
            "guilty_plea": random.random() < 0.72,
            "parse_warnings": [],
        })

    return records


if __name__ == "__main__":
    records = generate_sample(3000)
    out = Path("data/processed/judgments.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(records)} 筆模擬資料 → {out}")
