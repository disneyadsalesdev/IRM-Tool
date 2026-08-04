"""Build a consolidated IRM rules lookup from IRM_Rules.xlsx."""
import json
import os
import re
import sys
import uuid
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

# Dimensions exported to the sports-only lookup UI.
INDEX_DIMENSIONS = ("sports_league", "inventory_preset")

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

LATAM_COUNTRIES = frozenset(
    {"argentina", "peru", "chile", "mexico", "colombia", "brazil"}
)

SPORTS_PRESET_PATTERNS = re.compile(
    r"college sports ncaa|little league|special olympics|nfl flag|mlb tv|inside the nba|tennis|wimbledon|us open",
    re.I,
)

NON_SPORTS_PRESET_PATTERNS = re.compile(
    r"emea|portugal|latam|my little pony|diageo|mandalorian|vanderpump|mormon|creaturette|grogu|"
    r"tune-in content partner|ad selector|diageo restrictions|rip restrictions|critically acclaimed|"
    r"larger than life|lollapalooza|secret lives|star wars|robody",
    re.I,
)


def split_vals(val):
    if pd.isna(val) or str(val).strip() == "":
        return []
    return [v.strip() for v in str(val).split(",") if v.strip()]


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
    parts = re.split(
        r",\s*(?=(?:BRAND|INDUSTRY|ASSET_TAG|AD_PRODUCT|AGENCY)=)",
        text,
        flags=re.I,
    )
    normalized = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^(BRAND|INDUSTRY|ASSET_TAG|AD_PRODUCT|AGENCY)=(.+)$", part, re.I)
        if match:
            typ, rest = match.group(1).upper(), match.group(2).strip()
            if typ == "BRAND" and "," in rest:
                brands = sorted(
                    [b.strip() for b in rest.split(",") if b.strip()],
                    key=str.lower,
                )
                part = f"{typ}={', '.join(brands)}"
            else:
                part = f"{typ}={rest}"
        normalized.append(part)
    return sorted(normalized, key=str.lower)


def is_excluded_region(row, inv):
    """Drop international / non-US-sports regional rules (LATAM, Portugal, EMEA, etc.)."""
    name = str(row.get("Rule Name", "")).lower()
    if any(token in name for token in ("| latam |", "latam |", "| brazil |", "portugal", "| emea")):
        return True

    countries = [c.lower() for c in inv.get("country", [])]
    if countries and not any(c == "united states" for c in countries):
        if all(c in LATAM_COUNTRIES for c in countries):
            return True

    for preset in inv.get("inventory_preset", []):
        if NON_SPORTS_PRESET_PATTERNS.search(preset):
            return True

    return False


def has_sports_inventory(inv):
    if inv.get("sports_league"):
        return True
    for preset in inv.get("inventory_preset", []):
        if SPORTS_PRESET_PATTERNS.search(preset):
            return True
    return False


def is_sports_rule(row, inv):
    if is_excluded_region(row, inv):
        return False
    if not has_sports_inventory(inv):
        return False
    return has_restrictions_row(row, inv)


def has_restrictions_row(row, inv, entry=None):
    if entry is not None:
        return has_restrictions(entry)
    restrict_cols = [col for _, col in RESTRICT_FIELDS]
    if any(split_restrictions(field, row.get(col)) for field, col in RESTRICT_FIELDS):
        return True
    return bool(parse_exceptions(row.get("AdRestrictions Exceptions")))


def has_restrictions(entry):
    list_fields = [f for f in EMPTY_BUCKET if f != "rules"]
    return any(entry[f] for f in list_fields)


def add_to_index(index, key_type, key_val, entry):
    if not key_val or key_type not in INDEX_DIMENSIONS:
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
    for dim in INDEX_DIMENSIONS:
        buckets = idx.get(dim, {})
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


def load_supplemental_rules(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rules", [])


def supplemental_to_entry(rule_def):
    entry = {field: set(rule_def.get(field, [])) for field in EMPTY_BUCKET if field != "rules"}
    entry["exceptions"] = set(parse_exceptions_from_list(rule_def.get("exceptions", [])))
    rule_summary = {
        "id": rule_def.get("id") or str(uuid.uuid4()),
        "name": rule_def["name"],
        "publisher": rule_def.get("publisher", []),
        "country": rule_def.get("country", []),
        "notes": rule_def.get("notes", ""),
        "excluded_industries": sorted(entry["excluded_industries"], key=str.lower),
        "excluded_asset_tags": sorted(entry["excluded_asset_tags"], key=str.lower),
        "excluded_brands": sorted(entry["excluded_brands"], key=str.lower),
        "exceptions": sorted(entry["exceptions"], key=str.lower),
    }
    entry["rule_summary"] = rule_summary
    return entry, rule_def


def parse_exceptions_from_list(items):
    if not items:
        return []
    if len(items) == 1 and isinstance(items[0], str) and "=" not in items[0]:
        return parse_exceptions(items[0])
    out = []
    for item in items:
        out.extend(parse_exceptions(item))
    return out


def main():
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\syeda012\Downloads\IRM_Rules.xlsx"
    out_dir = os.path.dirname(os.path.abspath(__file__))
    supplemental_path = os.path.join(out_dir, "supplemental-rules.json")

    df = pd.read_excel(xlsx_path, sheet_name="IRM_Rules")
    df = df[df["Status"] == "ENABLED"].copy()

    index = defaultdict(dict)
    all_rules = []
    skipped = 0

    for _, row in df.iterrows():
        entry = {field: split_restrictions(field, row.get(col)) for field, col in RESTRICT_FIELDS}
        entry = {field: set(vals) for field, vals in entry.items()}
        entry["exceptions"] = set(parse_exceptions(row.get("AdRestrictions Exceptions")))

        if not has_restrictions(entry):
            continue

        inv = {k: split_vals(row.get(col)) for k, col in INV_COLS.items()}

        if not is_sports_rule(row, inv):
            skipped += 1
            continue

        rule_summary = {
            "id": row["ID"],
            "name": row["Rule Name"],
            "publisher": inv.get("publisher", []),
            "country": inv.get("country", []),
            "notes": str(row.get("Notes", "")) if pd.notna(row.get("Notes")) else "",
            "excluded_industries": sorted(entry["excluded_industries"], key=str.lower),
            "excluded_asset_tags": sorted(entry["excluded_asset_tags"], key=str.lower),
            "excluded_brands": sorted(entry["excluded_brands"], key=str.lower),
            "exceptions": sorted(entry["exceptions"], key=str.lower),
        }

        entry["rule_summary"] = rule_summary
        all_rules.append({**{f: list(entry[f]) for f in EMPTY_BUCKET if f != "rules"}, "inventory": inv})

        for dim in INDEX_DIMENSIONS:
            for v in inv.get(dim, []):
                add_to_index(index, dim, v, entry)

    for rule_def in load_supplemental_rules(supplemental_path):
        entry, meta = supplemental_to_entry(rule_def)
        if not has_restrictions(entry):
            continue
        all_rules.append(entry)
        target_dim = meta.get("target_dimension", "inventory_preset")
        target_key = meta.get("target_key") or meta.get("display_target")
        display = meta.get("display_target") or target_key
        add_to_index(index, target_dim, target_key, entry)
        if display.lower() != target_key.lower():
            bucket = index[target_dim][target_key.lower()]
            bucket["display_name"] = display

    serialized = serialize_index(index)

    lookup_path = os.path.join(out_dir, "irm-lookup.json")
    with open(lookup_path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)

    print(f"Wrote {lookup_path}")
    print(f"Sports rules indexed: {len(all_rules)}")
    print(f"Skipped non-sports / regional rules: {skipped}")
    print(f"Sports leagues: {len(serialized.get('sports_league', {}))}")
    print(f"Inventory presets: {len(serialized.get('inventory_preset', {}))}")


if __name__ == "__main__":
    main()
