"""Generate the demo datasets shipped with Atlas.

The data is synthetic but deliberately messy — formatted currency strings,
mixed-case categories, nulls, duplicate rows, an outage spike and a churn
event — so every engine (ingestion, quality, anomaly, insight, forecast) has
something real to find.

Usage:  python datasets/generate.py
"""
from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
RNG = np.random.default_rng(20261031)

REGIONS = {
    "North America": {"base": 1.00, "growth": 0.34, "churn": 2.1},
    "EMEA": {"base": 0.78, "growth": 0.27, "churn": 2.4},
    "APAC": {"base": 0.52, "growth": 0.61, "churn": 2.9},
    "LATAM": {"base": 0.31, "growth": 0.45, "churn": 3.4},
}
SEGMENTS = {
    "Enterprise": {"base": 5.8, "seats": 420, "plan": "Enterprise", "nps": 41},
    "Mid-Market": {"base": 2.6, "seats": 140, "plan": "Scale", "nps": 36},
    "SMB": {"base": 0.92, "seats": 38, "plan": "Growth", "nps": 27},
    "Startup": {"base": 0.34, "seats": 11, "plan": "Starter", "nps": 22},
}
FIRST_DAY = date(2025, 1, 1)
DAYS = 638  # through 2026-09-30
HOLIDAYS = {(3, 9), (3, 10), (3, 11), (3, 12), (3, 13), (7, 6), (7, 7), (7, 8), (7, 9), (7, 10)}


def _money(v: float) -> str:
    return f"${v:,.2f}"


def saas_revenue() -> None:
    rows: list[dict] = []
    n = 0
    for i in range(DAYS):
        day = FIRST_DAY + timedelta(days=i)
        t = i / 365.0
        annual = 1.0 + 0.055 * math.sin(2 * math.pi * day.timetuple().tm_yday / 365 - 1.1)
        weekly = 1.0 + 0.028 * math.sin(2 * math.pi * day.weekday() / 7)
        for region, rcfg in REGIONS.items():
            for segment, scfg in SEGMENTS.items():
                n += 1
                base = 21_500 * rcfg["base"] * scfg["base"]
                growth = 1.0 + rcfg["growth"] * t
                noise = float(RNG.normal(1.0, 0.022))
                revenue = base * growth * annual * weekly * noise
                churn = rcfg["churn"] * (1.0 - 0.18 * t) + float(RNG.normal(0, 0.28))
                tickets = max(0, int(RNG.poisson(6.5 + scfg["base"] * 1.4 + (2.5 if segment == "Enterprise" else 0))))
                nps = int(np.clip(RNG.normal(scfg["nps"] + (3 if region == "North America" else 0), 12), 0, 100))
                seats = int(scfg["seats"] * growth * RNG.normal(1.0, 0.03))
                customers = max(1, int(seats / RNG.uniform(3.5, 9.0)))
                trials = max(0, int(RNG.poisson(4 + scfg["base"] * 3)))
                email = f"ops{n:05d}@{(segment + region).replace(' ', '').lower()}.example.com"

                if (day.month, day.day) in HOLIDAYS:
                    if day.month == 3:
                        tickets = int(tickets * 3.4)
                    else:
                        churn *= 2.6
                        revenue *= 0.84

                # Deliberate mess: casing drift, formatted currency, nulls.
                shown_region = region
                if RNG.random() < 0.035 and region == "EMEA":
                    shown_region = random.choice(["emea", " EMEA", "Emea"])
                if RNG.random() < 0.025 and region == "North America":
                    shown_region = "North america"

                rev_value: object = round(revenue, 2)
                if RNG.random() < 0.04:
                    rev_value = _money(revenue)

                rows.append(
                    {
                        "date": day.isoformat(),
                        "region": shown_region,
                        "segment": segment,
                        "plan": scfg["plan"],
                        "revenue": rev_value,
                        "seats": seats,
                        "customers": customers,
                        "churn_rate": "" if RNG.random() < 0.012 else round(max(0.2, churn), 3),
                        "support_tickets": "" if RNG.random() < 0.008 else tickets,
                        "nps": "N/A" if RNG.random() < 0.028 else nps,
                        "trial_signups": trials,
                        "account_id": f"ACC-{n:06d}",
                        "contact_email": "" if RNG.random() < 0.006 else email,
                    }
                )

    # Duplicate a handful of rows, as happens in real exports.
    for _ in range(34):
        rows.append(dict(rows[random.randrange(len(rows))]))
    random.shuffle(rows)

    with open(OUT / "saas_revenue.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"saas_revenue.csv       {len(rows):,} rows")


def marketing_channels() -> None:
    channels = {
        "Paid Search": {"cpc": 2.4, "ctr": 0.032, "cvr": 0.016, "aov": 410},
        "Paid Social": {"cpc": 1.1, "ctr": 0.011, "cvr": 0.009, "aov": 330},
        "Display": {"cpc": 0.42, "ctr": 0.004, "cvr": 0.0035, "aov": 240},
        "Email": {"cpc": 1.2, "ctr": 0.021, "cvr": 0.022, "aov": 520},
        "Affiliate": {"cpc": 0.65, "ctr": 0.018, "cvr": 0.011, "aov": 380},
        "Content": {"cpc": 0.31, "ctr": 0.009, "cvr": 0.0055, "aov": 460},
    }
    rows: list[dict] = []
    start = date(2025, 1, 6)
    for w in range(91):
        week = start + timedelta(weeks=w)
        season = 1 + 0.24 * math.sin(2 * math.pi * w / 52 - 0.8)
        for channel, cfg in channels.items():
            spend = max(0.0, (600 + 2400 * RNG.random()) * season * (1.15 if channel == "Paid Social" else 1.0))
            clicks = int(spend / cfg["cpc"] * RNG.normal(1.0, 0.10))
            impressions = int(clicks / cfg["ctr"] * RNG.normal(1.0, 0.06))
            leads = int(clicks * cfg["cvr"] * RNG.normal(1.0, 0.14))
            conv = int(leads * RNG.uniform(0.31, 0.52))
            revenue = conv * cfg["aov"] * RNG.normal(1.0, 0.10)
            rows.append(
                {
                    "week": week.isoformat(),
                    "channel": channel,
                    "spend": round(spend, 2),
                    "impressions": impressions,
                    "clicks": clicks,
                    "leads": leads,
                    "conversions": conv,
                    "revenue": round(revenue, 2),
                }
            )
    with open(OUT / "marketing_channels.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"marketing_channels.csv {len(rows):,} rows")


def hr_attrition() -> None:
    departments = {
        "Sales": {"salary": 1.12, "attrition": 0.21},
        "R&D": {"salary": 1.24, "attrition": 0.11},
        "Support": {"salary": 0.78, "attrition": 0.18},
        "Finance": {"salary": 1.05, "attrition": 0.09},
        "Marketing": {"salary": 0.96, "attrition": 0.14},
    }
    roles = {
        "Sales": ["Account Executive", "Sales Manager", "SDR"],
        "R&D": ["Software Engineer", "Data Scientist", "QA Engineer"],
        "Support": ["Support Specialist", "Support Lead"],
        "Finance": ["Financial Analyst", "Controller"],
        "Marketing": ["Content Strategist", "Growth Marketer"],
    }
    rows: list[dict] = []
    for emp in range(1, 1471):
        dept = random.choices(list(departments), weights=[28, 30, 18, 10, 14])[0]
        cfg = departments[dept]
        role = random.choice(roles[dept])
        age = int(np.clip(RNG.normal(36, 8), 21, 60))
        tenure = round(max(0.2, RNG.gamma(2.0, 2.6)), 1)
        overtime = "Yes" if RNG.random() < (0.34 if dept in ("Sales", "Support") else 0.17) else "No"
        satisfaction = int(np.clip(RNG.normal(2.9 - (0.45 if overtime == "Yes" else 0), 0.85), 1, 4))
        income = int(cfg["salary"] * RNG.uniform(48_000, 132_000) / 12 * (1 + 0.012 * tenure))
        p_leave = cfg["attrition"] * (1.9 if overtime == "Yes" else 1.0) * (1.7 if satisfaction <= 2 else 1.0)
        attrition = "Yes" if RNG.random() < min(0.62, p_leave) else "No"
        rows.append(
            {
                "employee_id": f"EMP-{emp:04d}",
                "age": age,
                "department": dept,
                "job_role": role,
                "monthly_income": income,
                "tenure_years": tenure,
                "overtime": overtime,
                "satisfaction": satisfaction,
                "distance_from_home": int(np.clip(RNG.gamma(2.2, 5.0), 1, 45)),
                "performance_rating": int(np.clip(round(RNG.normal(3.1, 0.55)), 1, 4)),
                "attrition": attrition,
            }
        )
    with open(OUT / "hr_attrition.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"hr_attrition.csv       {len(rows):,} rows")


if __name__ == "__main__":
    saas_revenue()
    marketing_channels()
    hr_attrition()
