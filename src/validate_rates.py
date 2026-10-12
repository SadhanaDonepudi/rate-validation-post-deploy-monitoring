"""Pre-deployment rate validation suite.

For each synthetic test quote the suite rates the quote twice - once with the
deployed rating engine (reading the CSV tables under test) and once with the
independent reference implementation of the approved rate manual - and
compares the premiums in whole cents.

On a mismatch the suite records a *detection signature* per rate element that
disagrees: (element, lookup key, deployed value, reference value). Signatures
are grouped so each distinct table defect surfaces as one attributable
finding. The suite never sees the defect manifest; attribution of signatures
to the 23 planted defects happens in the test harness via
:func:`attribute_defects`.

ALL DATA IN THIS REPOSITORY IS SYNTHETIC.
"""

from __future__ import annotations

import json

import rate_manual

ELEMENTS = ("base", "territory", "breed", "age_band", "plan", "deductible")


def _quote_key(element: str, quote: dict, reference: dict, version: str) -> str:
    if element == "base":
        return version
    if element == "territory":
        return quote["territory"]
    if element == "breed":
        return quote["breed_group"]
    if element == "age_band":
        return reference["band_label"]
    if element == "plan":
        return quote["plan"]
    if element == "deductible":
        return str(quote["deductible"])
    raise ValueError(element)


def _fmt(value):
    if isinstance(value, str):
        return value
    return round(float(value), 6)


def diff_signatures(quote: dict, engine_result: dict, reference: dict,
                    version: str) -> list[tuple]:
    """Signatures for every rate element where engine and reference disagree."""
    signatures = []
    eng_factors = engine_result["factors"]
    ref_factors = reference["factors"]
    for element in ELEMENTS:
        fkey = element if element != "age_band" else "age"
        eng_val = eng_factors.get(fkey)
        ref_val = ref_factors[fkey]
        if engine_result.get("unrated") and element == "age_band":
            signatures.append(
                ("age_band", _quote_key(element, quote, reference, version),
                 "UNRATED", _fmt(ref_val)))
            continue
        if eng_val is None or abs(float(eng_val) - float(ref_val)) > 1e-9:
            signatures.append(
                (element, _quote_key(element, quote, reference, version),
                 _fmt(eng_val), _fmt(ref_val)))
    return signatures


def run_validation_suite(engine, version: str, quotes: list[dict]) -> dict:
    """Run the differential validation suite. Returns the full report dict."""
    mismatches = 0
    detected: dict[tuple, dict] = {}
    for quote in quotes:
        eng = engine.calculate_premium(quote)
        ref = rate_manual.calculate_premium(quote, version)
        if eng["premium_cents"] != ref["premium_cents"]:
            mismatches += 1
            for sig in diff_signatures(quote, eng, ref, version):
                element, key, deployed, reference_val = sig
                group_key = (element, key, deployed)
                entry = detected.setdefault(group_key, {
                    "element": element, "key": key,
                    "deployed_value": deployed, "reference_value": reference_val,
                    "quote_count": 0, "example_quotes": [],
                })
                entry["quote_count"] += 1
                if len(entry["example_quotes"]) < 3:
                    entry["example_quotes"].append(quote["quote_id"])
    n = len(quotes)
    return {
        "version": version,
        "engine_tables": engine.table_dir,
        "quotes_tested": n,
        "mismatches": mismatches,
        "match_rate": (n - mismatches) / n if n else 1.0,
        "distinct_signatures": len(detected),
        "signatures": sorted(detected.values(),
                             key=lambda s: (-s["quote_count"], s["element"], s["key"])),
    }


def _values_match(deployed_sig, deployed_manifest) -> bool:
    if isinstance(deployed_manifest, str) or isinstance(deployed_sig, str):
        return deployed_sig == deployed_manifest
    return abs(float(deployed_sig) - float(deployed_manifest)) < 1e-9


def attribute_defects(report: dict, manifest: list[dict]) -> list[dict]:
    """Attribute detected signatures to manifest defects.

    A defect counts as caught when every affected (element, key) it lists has
    a detected signature with the manifest's deployed value.
    """
    by_sig = {(s["element"], s["key"]): s for s in report["signatures"]}
    results = []
    for defect in manifest:
        affected_results = []
        for aff in defect["affected"]:
            sig = by_sig.get((defect["element"], aff["key"]))
            matched = sig is not None and _values_match(
                sig["deployed_value"], aff["deployed_value"])
            affected_results.append({
                "key": aff["key"],
                "deployed_value": aff["deployed_value"],
                "reference_value": aff["reference_value"],
                "matched": matched,
                "quote_count": sig["quote_count"] if sig else 0,
            })
        caught = all(a["matched"] for a in affected_results)
        results.append({
            "id": defect["id"],
            "category": defect["category"],
            "description": defect["description"],
            "caught": caught,
            "affected": affected_results,
        })
    return results


def write_report(report: dict, attribution: list[dict], path: str) -> None:
    caught = sum(1 for d in attribution if d["caught"])
    payload = {
        **report,
        "defects_total": len(attribution),
        "defects_caught": caught,
        "defects": attribution,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
