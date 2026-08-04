"""Simple CLI to look up blocked brands/industries for IRM inventory targets.

Examples:
  py irm_lookup.py --league NFL
  py irm_lookup.py --genre Documentaries
  py irm_lookup.py --publisher ESPN
  py irm_lookup.py --search nfl
  py irm_lookup.py --list leagues
"""
import argparse
import json
import os
import sys


def load_lookup():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "irm-lookup.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


LEAGUE_ALIASES = {
    "nfl": ["national football league", "nfl football"],
    "nba": ["national basketball association", "national basketball league", "wnba"],
    "mlb": ["major league baseball", "mlb baseball"],
    "nhl": ["national hockey league"],
    "ncaa": ["ncaaf", "ncaam", "ncaa"],
    "ufc": ["ultimate fighting championship"],
    "f1": ["formula 1"],
}


def find_matches(lookup, dimension, query):
    """Find keys matching query (substring, case-insensitive)."""
    dim = lookup.get(dimension, {})
    q = query.lower()
    aliases = LEAGUE_ALIASES.get(q, []) if dimension == "sports_league" else []
    return [
        (k, v)
        for k, v in dim.items()
        if q in k
        or q in v["display_name"].lower()
        or any(a in k or a in v["display_name"].lower() for a in aliases)
    ]


MERGE_FIELDS = [
    "excluded_brands", "excluded_industries", "excluded_asset_tags",
    "excluded_ad_products", "excluded_agencies",
    "included_brands", "included_industries", "included_asset_tags",
    "included_ad_products", "included_agencies", "exceptions",
]


def merge_results(matches):
    """Merge multiple index entries into one view."""
    merged = {f: set() for f in MERGE_FIELDS}
    merged["rules"] = []
    for _k, v in matches:
        for field in MERGE_FIELDS:
            merged[field].update(v.get(field, []))
        merged["rules"].extend(v["rules"])
    result = {f: sorted(merged[f], key=str.lower) for f in MERGE_FIELDS}
    result["rule_count"] = len(merged["rules"])
    result["rules"] = merged["rules"]
    return result


def print_section(title, items):
    if not items:
        return
    print(f"\n  {title} ({len(items)}):")
    for item in items:
        print(f"    - {item}")


def print_result(label, result):
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  Rules contributing: {result['rule_count']}")

    print_section("BLOCKED BRANDS", result.get("excluded_brands", []))
    print_section("BLOCKED INDUSTRIES", result.get("excluded_industries", []))
    print_section("BLOCKED ASSET TAGS", result.get("excluded_asset_tags", []))
    print_section("BLOCKED AD PRODUCTS", result.get("excluded_ad_products", []))
    print_section("BLOCKED AGENCIES", result.get("excluded_agencies", []))
    print_section("ALLOWED ONLY (brands)", result.get("included_brands", []))
    print_section("ALLOWED ONLY (industries)", result.get("included_industries", []))
    print_section("ALLOWED ONLY (asset tags)", result.get("included_asset_tags", []))
    print_section("EXCEPTIONS (still allowed)", result.get("exceptions", []))

    if not any(result.get(f) for f in MERGE_FIELDS):
        print("\n  No ad restrictions found for this target.")

    if result["rules"]:
        print("\n  Source rules:")
        seen = set()
        for r in result["rules"]:
            key = r["name"]
            if key in seen:
                continue
            seen.add(key)
            pubs = ", ".join(r["publisher"]) if r["publisher"] else "any"
            print(f"    - {r['name']}  (publisher: {pubs})")


def list_dimension(lookup, dimension):
    dim = lookup.get(dimension, {})
    print(f"\nAvailable {dimension} values ({len(dim)}):")
    for _k, v in sorted(dim.items(), key=lambda x: x[1]["display_name"].lower()):
        n_brands = len(v.get("excluded_brands", []))
        n_ind = len(v.get("excluded_industries", []))
        n_tags = len(v.get("excluded_asset_tags", []))
        if n_brands or n_ind or n_tags:
            print(
                f"  {v['display_name']}  "
                f"({n_brands} blocked brands, {n_ind} blocked industries, {n_tags} blocked asset tags)"
            )


def main():
    parser = argparse.ArgumentParser(description="Look up IRM ad restrictions")
    parser.add_argument("--league", help="Sports league (e.g. NFL, NBA, MLB)")
    parser.add_argument("--genre", help="Content genre")
    parser.add_argument("--series", help="TV series name (partial match)")
    parser.add_argument("--publisher", help="Publisher (e.g. ESPN, Disney Plus)")
    parser.add_argument("--preset", help="Inventory preset")
    parser.add_argument("--country", help="Country")
    parser.add_argument("--search", help="Search all dimensions for a keyword")
    parser.add_argument("--list", choices=[
        "leagues", "genres", "publishers", "presets", "series", "countries",
    ], help="List available values in a dimension")
    args = parser.parse_args()

    lookup = load_lookup()

    dim_map = {
        "leagues": "sports_league",
        "genres": "genre",
        "publishers": "publisher",
        "presets": "inventory_preset",
        "series": "series",
        "countries": "country",
    }

    if args.list:
        list_dimension(lookup, dim_map[args.list])
        return

    if args.search:
        print(f"Searching all dimensions for '{args.search}'...")
        found_any = False
        for dim in lookup:
            matches = find_matches(lookup, dim, args.search)
            if matches:
                found_any = True
                result = merge_results(matches)
                labels = ", ".join(v["display_name"] for _k, v in matches)
                print_result(f"{dim}: {labels}", result)
        if not found_any:
            print(f"No matches for '{args.search}'")
        return

    queries = [
        ("sports_league", args.league, "Sports League"),
        ("genre", args.genre, "Genre"),
        ("series", args.series, "Series"),
        ("publisher", args.publisher, "Publisher"),
        ("inventory_preset", args.preset, "Inventory Preset"),
        ("country", args.country, "Country"),
    ]

    ran = False
    for dimension, query, label in queries:
        if not query:
            continue
        ran = True
        matches = find_matches(lookup, dimension, query)
        if not matches:
            print(f"No {label} matches for '{query}'")
            continue
        result = merge_results(matches)
        names = ", ".join(v["display_name"] for _k, v in matches)
        print_result(f"{label}: {names}", result)

    if not ran:
        parser.print_help()


if __name__ == "__main__":
    main()
