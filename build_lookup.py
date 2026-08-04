"""Build a consolidated IRM rules lookup from IRM_Rules.xlsx."""
import json
import os
import re
import sys
from collections import defaultdict

import pandas as pd

INV_COLS = {
    "sports_league": "SPORTS_LEAGUE",
    "genre": "GENRE",
    "series": "SERIES",
    "movie": "MOVIE",
    "publisher": "PUBLISHER",
    "country": "COUNTRY",
    "inventory_preset": "INVENTORY_PRESET",
    "content_partner": "CONTENT_PARTNER",
    "rating_code": "RATING_CODE",
    "entity_type": "ENTITY_TYPE",
    "event": "EVENT",
}

RESTRICT_FIELDS = [
    ("excluded_brands", "AdRestrictions_exclude BRAND"),
    ("excluded_industries", "AdRestrictions_exclude INDUSTRY"),
    ("excluded_asset_tags", "AdRestrictions_exclude ASSET_TAG"),
    ("excluded_ad_products", "AdRestrictions_exclude AD_PRODUCT"),
    ("excluded_agencies", "AdRestrictions_exclude AGENCY"),
    ("included_brands", "AdRestrictions_include BRAND"),
    ("included_industries", "AdRestrictions_include INDUSTRY"),
    ("included_asset_tags", "AdRestrictions_include ASSET_TAG"),
    ("included_ad_products", "AdRestrictions_include AD_PRODUCT"),
    ("included_agencies", "AdRestrictions_include AGENCY"),
]

EMPTY_BUCKET = {
    "excluded_brands": set(),
    "excluded_industries": set(),
    "excluded_asset_tags": set(),
    "excluded_ad_products": set(),
    "excluded_agencies": set(),
    "included_brands": set(),
    "included_industries": set(),
    "included_asset_tags": set(),
    "included_ad_products": set(),
    "included_agencies": set(),
    "exceptions": set(),
    "rules": [],
}


def split_vals(val):
    if pd.isna(val) or str(val).strip() == "":
        return []
    return [v.strip() for v in str(val).split(",") if v.strip()]


# Split multi-industry cells on comma only at industry boundaries (not internal commas).
INDUSTRY_BOUNDARY = re.compile(
    r",\s+(?=(?:"
    r"CPG-|Entertainment-|Financial Services-|Health-|POLITICAL-|Political[\s\-–]"
    r"|Retail-|Automotive-|Travel-|Technology-|MSO-|Telecom-|Restaurant-"
    r"|Insurance-|Government(?:,|$|-|\s)|(?-i:SEXUAL HEALTH)|FANTASY|SPORTSBOOKS"
    r"|GAMBLING/CASINOS/ICASINOS|LOTTERY|SWEEPSTAKES|DATING APPS|DEATH SERVICES"
    r"|DIET PROGRAMS|WEIGHT LOSS|INTIMATES|COSMETIC/|PRESCRIPTION DRUGS"
    r"|Shipping,|Utilities(?:,|$)|Schools,|Non Profit|HOTELS &|FITNESS &|Events-"
    r"|ASTROLOGY,|Hulu(?:,|$)|Religion(?:,|$)|Legal(?:,|$)|Brokerage(?:,|$)"
    r"))",
)


def split_industries(val):
    if pd.isna(val) or str(val).strip() == "":
        return []
    text = str(val).strip()
    return [part.strip() for part in INDUSTRY_BOUNDARY.split(text) if part.strip()]


def split_restrictions(field, val):
    if field in ("excluded_industries", "included_industries"):
        return split_industries(val)
    return split_vals(val)


def parse_exceptions(val):
    """Parse 'BRAND=EA, INDUSTRY=Foo' style exception strings."""
    if pd.isna(val) or str(val).strip() == "":
        return []
    text = str(val).strip()
    parts = re.split(r",\s*(?=[A-Z_]+=)", text)
    return [p.strip() for p in parts if p.strip()]


def add_to_index(index, key_type, key_val, entry):
    if not key_val:
        return
    bucket = index[key_type]
    k = key_val.lower()
    if k not in bucket:
        bucket[k] = {field: set(v) for field, v in EMPTY_BUCKET.items() if field != "rules"}
        bucket[k]["display_name"] = key_val
        bucket[k]["rules"] = []

    for field in EMPTY_BUCKET:
        if field == "rules":
            bucket[k]["rules"].append(entry["rule_summary"])
        else:
            bucket[k][field].update(entry[field])


def serialize_index(idx):
    list_fields = [f for f in EMPTY_BUCKET if f != "rules"]
    out = {}
    for dim, buckets in idx.items():
        out[dim] = {}
        for _k, v in sorted(buckets.items(), key=lambda x: x[1]["display_name"].lower()):
            serialized = {
                "display_name": v["display_name"],
                "rule_count": len(v["rules"]),
                "rules": v["rules"],
            }
            for field in list_fields:
                serialized[field] = sorted(v[field], key=str.lower)
            out[dim][_k] = serialized
    return out


def has_restrictions(entry):
    list_fields = [f for f in EMPTY_BUCKET if f != "rules"]
    return any(entry[f] for f in list_fields)


def main():
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\syeda012\Downloads\IRM_Rules.xlsx"
    out_dir = os.path.dirname(os.path.abspath(__file__))

    df = pd.read_excel(xlsx_path, sheet_name="IRM_Rules")
    df = df[df["Status"] == "ENABLED"].copy()

    index = defaultdict(dict)
    all_rules = []

    for _, row in df.iterrows():
        entry = {field: split_restrictions(field, row.get(col)) for field, col in RESTRICT_FIELDS}
        entry["exceptions"] = parse_exceptions(row.get("AdRestrictions Exceptions"))

        if not has_restrictions(entry):
            continue

        inv = {k: split_vals(row.get(col)) for k, col in INV_COLS.items()}

        rule_summary = {
            "id": row["ID"],
            "name": row["Rule Name"],
            "publisher": inv.get("publisher", []),
            "country": inv.get("country", []),
            "notes": str(row.get("Notes", "")) if pd.notna(row.get("Notes")) else "",
            "excluded_industries": entry["excluded_industries"],
            "excluded_asset_tags": entry["excluded_asset_tags"],
            "excluded_brands": entry["excluded_brands"],
            "exceptions": entry["exceptions"],
        }

        entry["rule_summary"] = rule_summary
        all_rules.append({**entry, "inventory": inv})

        for dim, vals in inv.items():
            for v in vals:
                add_to_index(index, dim, v, entry)

        rn = str(row.get("Rule Name", "")).strip()
        if rn:
            add_to_index(index, "rule_name", rn, entry)

    serialized = serialize_index(index)

    lookup_path = os.path.join(out_dir, "irm-lookup.json")
    with open(lookup_path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)

    print(f"Wrote {lookup_path}")
    print(f"Rules with ad restrictions: {len(all_rules)}")
    print(f"Index dimensions: {', '.join(sorted(serialized.keys()))}")


if __name__ == "__main__":
    main()
