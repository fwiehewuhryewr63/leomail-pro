"""
SMS Country Map — Phase 3: SMS/Phone Analysis
Queries all SMS providers for Yahoo pricing and availability.
Builds country priority table + identifies WhatsApp-only countries.

Usage:
    cd Leomail
    python -m tests.sms_country_map

Output:
    Console table + JSON/MD reports in user_data/debug_screenshots/
"""
import sys
import os
import io
import json
import time

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.modules.birth._helpers import (
    PHONE_COUNTRY_MAP, COUNTRY_FALLBACK_PRIORITY,
    get_sms_chain,
)

SCREENSHOT_DIR = os.path.join("user_data", "debug_screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Country names for display
COUNTRY_NAMES = {
    "us": "USA", "uk": "UK", "de": "Germany", "nl": "Netherlands",
    "se": "Sweden", "pl": "Poland", "br": "Brazil", "ca": "Canada",
    "fr": "France", "es": "Spain", "ru": "Russia", "it": "Italy",
    "at": "Austria", "cz": "Czech Rep", "ee": "Estonia", "ro": "Romania",
    "ie": "Ireland", "ua": "Ukraine", "il": "Israel", "id": "Indonesia",
    "ph": "Philippines", "in": "India", "my": "Malaysia", "ke": "Kenya",
    "tz": "Tanzania", "hk": "Hong Kong", "ng": "Nigeria", "eg": "Egypt",
    "za": "South Africa", "co": "Colombia", "tr": "Turkey", "mx": "Mexico",
    "th": "Thailand", "pe": "Peru", "nz": "New Zealand", "ar": "Argentina",
    "vn": "Vietnam", "bd": "Bangladesh", "pk": "Pakistan", "cl": "Chile",
    "be": "Belgium", "bg": "Bulgaria", "hu": "Hungary", "pt": "Portugal",
    "gr": "Greece", "fi": "Finland", "dk": "Denmark", "no": "Norway",
    "ch": "Switzerland", "au": "Australia", "jp": "Japan", "ge": "Georgia",
    "ae": "UAE", "sa": "Saudi Arabia", "kz": "Kazakhstan", "cn": "China",
    "hr": "Croatia", "si": "Slovenia", "lv": "Latvia", "lt": "Lithuania",
}


def main():
    print("📱 SMS Country Map — Phase 3: SMS/Phone Analysis")
    print("=" * 60)

    sms_chain = get_sms_chain()
    if not sms_chain:
        print("❌ No SMS providers configured!")
        return

    provider_names = [name for name, _ in sms_chain]
    print(f"\n📋 Providers: {provider_names}")

    # Query balances
    for name, provider in sms_chain:
        try:
            bal = provider.get_balance()
            if isinstance(bal, dict):
                bal = bal.get("balance", bal.get("amount", 0))
            print(f"  💰 {name}: {float(bal):.2f} RUB")
        except Exception as e:
            print(f"  ⚠️ {name}: {e}")

    # Query prices per provider — each returns {"prices": [list of dicts]}
    # Each dict: {"country": "us", "cost": 5.0, "count": 100, ...}
    provider_prices = {}  # provider_name -> {country_2letter: {"cost": X, "count": Y}}

    for name, provider in sms_chain:
        print(f"\n📊 Querying {name} for Yahoo prices...")
        try:
            result = provider.get_prices("yahoo")
            prices_list = result.get("prices", []) if isinstance(result, dict) else []

            parsed = {}
            for item in prices_list:
                cc = item.get("country", "")
                cost = float(item.get("cost", 0))
                count = int(item.get("count", 0))
                if cc and cost > 0:
                    # Keep the most expensive (best quality) if multiple entries
                    if cc not in parsed or cost > parsed[cc]["cost"]:
                        parsed[cc] = {"cost": cost, "count": count}

            provider_prices[name] = parsed
            print(f"  ✅ {name}: {len(parsed)} countries with Yahoo numbers")
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            provider_prices[name] = {}

    # Build unified country map
    all_countries = set()
    for parsed in provider_prices.values():
        all_countries.update(parsed.keys())

    # Also add all known from PHONE_COUNTRY_MAP
    all_countries.update(PHONE_COUNTRY_MAP.keys())

    print(f"\n{'='*90}")
    print("📊 YAHOO SMS AVAILABILITY MAP")
    print(f"{'='*90}")

    country_data = {}
    for cc in sorted(all_countries):
        name = COUNTRY_NAMES.get(cc, cc.upper())
        prefix = PHONE_COUNTRY_MAP.get(cc, "?")
        prefix_str = f"+{prefix}" if prefix != "?" else "?"

        entry = {
            "country": cc,
            "name": name,
            "prefix": prefix_str,
            "providers": {},
            "max_price": 0,
            "min_price": None,
            "total_count": 0,
            "available_at": [],
        }

        for prov_name in provider_names:
            prices = provider_prices.get(prov_name, {})
            if cc in prices:
                p = prices[cc]
                entry["providers"][prov_name] = p
                entry["available_at"].append(prov_name)
                entry["total_count"] += p["count"]
                if p["cost"] > entry["max_price"]:
                    entry["max_price"] = p["cost"]
                if entry["min_price"] is None or p["cost"] < entry["min_price"]:
                    entry["min_price"] = p["cost"]

        # Tier classification
        if not entry["available_at"]:
            entry["tier"] = "❌ N/A"
        elif entry["max_price"] >= 20:
            entry["tier"] = "⭐ PREMIUM"
        elif entry["max_price"] >= 5:
            entry["tier"] = "✅ GOOD"
        elif entry["max_price"] >= 1:
            entry["tier"] = "⚠️ CHEAP"
        else:
            entry["tier"] = "💀 VERY CHEAP"

        country_data[cc] = entry

    # Print table (available only)
    available = {cc: e for cc, e in country_data.items() if e["available_at"]}
    unavailable = {cc: e for cc, e in country_data.items() if not e["available_at"]}

    print(f"\n{'Country':<18} {'Pfx':<6} ", end="")
    for pn in provider_names:
        print(f"{pn:<16} ", end="")
    print(f"{'Count':<8} {'Tier'}")

    print(f"{'-'*18} {'-'*6} ", end="")
    for _ in provider_names:
        print(f"{'-'*16} ", end="")
    print(f"{'-'*8} {'-'*15}")

    # Sort by max price DESC
    for entry in sorted(available.values(), key=lambda x: -x["max_price"]):
        line = f"{entry['name']:<18} {entry['prefix']:<6} "
        for pn in provider_names:
            p = entry["providers"].get(pn)
            if p:
                line += f"₽{p['cost']:<5.2f} ({p['count']:<5})" + " "
            else:
                line += f"{'—':<16} "
        line += f"{entry['total_count']:<8} {entry['tier']}"
        print(line)

    # Tier lists
    tier1 = [e for e in available.values() if "PREMIUM" in e["tier"]]
    tier2 = [e for e in available.values() if "GOOD" in e["tier"]]
    tier3 = [e for e in available.values() if "CHEAP" in e["tier"] and "VERY" not in e["tier"]]
    tier4 = [e for e in available.values() if "VERY CHEAP" in e["tier"]]

    print(f"\n{'='*60}")
    print("🏆 TIER LIST")
    print(f"{'='*60}")

    for tier_name, items in [
        ("⭐ Tier 1 — Premium (real SIM likely)", tier1),
        ("✅ Tier 2 — Good", tier2),
        ("⚠️ Tier 3 — Cheap (virtual likely)", tier3),
        ("💀 Tier 4 — Very Cheap", tier4),
    ]:
        print(f"\n{tier_name} ({len(items)} countries):")
        for e in sorted(items, key=lambda x: -x["max_price"]):
            prov = ", ".join(e["available_at"])
            print(f"  {e['name']:<18} {e['prefix']:<6} max ₽{e['max_price']:>6.2f}  [{prov}]")

    print(f"\n❌ Unavailable for Yahoo ({len(unavailable)} countries)")

    # Priority list for Yahoo bot
    print(f"\n{'='*60}")
    print("📋 RECOMMENDED YAHOO SMS PRIORITY (for bot)")
    print(f"{'='*60}")

    # Priority: countries with MOST availability + reasonable price
    priority_order = []

    # First: countries from COUNTRY_FALLBACK_PRIORITY that are available
    for cc in COUNTRY_FALLBACK_PRIORITY:
        if cc in available:
            priority_order.append(available[cc])

    # Then: remaining available, sorted by max_price DESC (quality)
    for e in sorted(available.values(), key=lambda x: -x["max_price"]):
        if e not in priority_order:
            priority_order.append(e)

    for i, e in enumerate(priority_order[:30], 1):
        prov = ", ".join(e["available_at"])
        print(f"  {i:2d}. {e['name']:<18} {e['prefix']:<6} max ₽{e['max_price']:>6.2f}  count={e['total_count']:<6} [{prov}]")

    # Save report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "providers": provider_names,
        "balances": {},
        "summary": {
            "total_countries_available": len(available),
            "total_countries_unavailable": len(unavailable),
            "tier1_premium": len(tier1),
            "tier2_good": len(tier2),
            "tier3_cheap": len(tier3),
            "tier4_very_cheap": len(tier4),
        },
        "country_data": {
            cc: {
                "name": e["name"],
                "prefix": e["prefix"],
                "providers": e["providers"],
                "max_price": e["max_price"],
                "total_count": e["total_count"],
                "available_at": e["available_at"],
                "tier": e["tier"],
            }
            for cc, e in country_data.items()
        },
        "priority_order": [e["country"] for e in priority_order],
    }

    report_path = os.path.join(SCREENSHOT_DIR, f"sms_country_map_{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n📄 Report: {report_path}")

    print(f"\n{'='*60}")
    print("✅ SMS Country Map complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
