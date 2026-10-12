"""Rate-table builder and defect injector.

Builds the clean deployed CSV rate tables for pricing versions v1 and v2 from
the approved manual, then applies EXACTLY 23 planted defects to a copy of the
v2 tables. Every defect is recorded in a manifest with its expected detection
signature: (rate element, lookup key, deployed value, reference value).

The manifest is ground truth for the *test assertions only* - the validation
suite never sees it. The suite must genuinely detect each defect by
differential comparison against the reference implementation.

Defect catalogue (23):
  wrong factor values ......... DEF-01..DEF-06, DEF-17, DEF-18, DEF-21..DEF-23
  mis-keyed territory rows .... DEF-07..DEF-10
  off-by-one rate tiers ....... DEF-11..DEF-13
  swapped factors ............. DEF-14, DEF-15
  missing row ................. DEF-16
  duplicate/conflicting row ... DEF-19
  base-rate typo .............. DEF-20

ALL DATA IN THIS REPOSITORY IS SYNTHETIC.
"""

from __future__ import annotations

import json
import os

import pandas as pd

import rate_manual as manual

EXPECTED_DEFECT_COUNT = 23

TABLE_FILES = {
    "base": "base_rates.csv",
    "territories": "territories.csv",
    "breeds": "breeds.csv",
    "age_bands": "age_bands.csv",
    "plans": "plans.csv",
    "deductibles": "deductibles.csv",
}


def build_clean_tables() -> dict[str, pd.DataFrame]:
    """Build clean deployed tables for v1 and v2 from the approved manual."""
    tables = {}
    tables["base"] = pd.DataFrame([
        {"version": v, "annual_base_premium": manual.BASE_PREMIUM[v]}
        for v in manual.VERSIONS
    ])
    tables["territories"] = pd.DataFrame([
        {"version": v, "territory_code": code, "factor": factor}
        for v in manual.VERSIONS
        for code, factor in manual.TERRITORY_FACTORS[v].items()
    ])
    tables["breeds"] = pd.DataFrame([
        {"version": v, "breed_group": bg, "factor": factor}
        for v in manual.VERSIONS
        for bg, factor in manual.BREED_FACTORS[v].items()
    ])
    tables["age_bands"] = pd.DataFrame([
        {"version": v, "band_id": b["band_id"], "band_label": b["band_label"],
         "min_age": b["min_age"], "max_age": b["max_age"], "factor": b["factor"]}
        for v in manual.VERSIONS
        for b in manual.AGE_BANDS[v]
    ])
    tables["plans"] = pd.DataFrame([
        {"version": v, "plan": plan, "factor": factor}
        for v in manual.VERSIONS
        for plan, factor in manual.PLAN_FACTORS[v].items()
    ])
    tables["deductibles"] = pd.DataFrame([
        {"version": v, "deductible": ded, "factor": factor}
        for v in manual.VERSIONS
        for ded, factor in manual.DEDUCTIBLE_FACTORS[v].items()
    ])
    return tables


def write_tables(tables: dict[str, pd.DataFrame], directory: str) -> None:
    os.makedirs(directory, exist_ok=True)
    for name, filename in TABLE_FILES.items():
        tables[name].to_csv(os.path.join(directory, filename), index=False)


def _v2(df: pd.DataFrame) -> pd.Series:
    return df["version"] == "v2"


def _record(defects: list, defect_id: str, category: str, description: str,
            element: str, affected: list[dict]) -> None:
    defects.append({
        "id": defect_id,
        "category": category,
        "description": description,
        "element": element,
        "affected": affected,  # [{key, deployed_value, reference_value}, ...]
    })


def inject_defects(tables: dict[str, pd.DataFrame]) -> list[dict]:
    """Apply exactly 23 defects to the v2 tables. Returns the manifest."""
    defects: list[dict] = []
    t = tables["territories"]
    b = tables["breeds"]
    a = tables["age_bands"]
    p = tables["plans"]
    d = tables["deductibles"]
    base = tables["base"]

    def set_factor(df, mask, value):
        df.loc[mask, "factor"] = value

    # ---- wrong factor values ------------------------------------------------
    set_factor(t, _v2(t) & (t["territory_code"] == "TX-02"), 1.42)   # DEF-01 transposed digits
    _record(defects, "DEF-01", "wrong factor",
            "Territory TX-02 factor transposed 1.24 -> 1.42 in v2 table.",
            "territory", [{"key": "TX-02", "deployed_value": 1.42, "reference_value": 1.24}])

    set_factor(b, _v2(b) & (b["breed_group"] == "BG-07"), 1.23)       # DEF-02
    _record(defects, "DEF-02", "wrong factor",
            "Breed group BG-07 factor 1.32 -> 1.23 (transposed digits).",
            "breed", [{"key": "BG-07", "deployed_value": 1.23, "reference_value": 1.32}])

    set_factor(a, _v2(a) & (a["band_label"] == "10+"), 1.25)          # DEF-03
    _record(defects, "DEF-03", "wrong factor",
            "Age band 10+ factor 1.52 -> 1.25 (transposed digits).",
            "age_band", [{"key": "10+", "deployed_value": 1.25, "reference_value": 1.52}])

    set_factor(p, _v2(p) & (p["plan"] == "Wellness+"), 1.12)          # DEF-04
    _record(defects, "DEF-04", "wrong factor",
            "Plan Wellness+ factor 1.22 -> 1.12 (digit typo).",
            "plan", [{"key": "Wellness+", "deployed_value": 1.12, "reference_value": 1.22}])

    set_factor(d, _v2(d) & (d["deductible"] == 1000), 0.48)           # DEF-05
    _record(defects, "DEF-05", "wrong factor",
            "Deductible $1000 factor 0.84 -> 0.48 (digit typo).",
            "deductible", [{"key": "1000", "deployed_value": 0.48, "reference_value": 0.84}])

    set_factor(t, _v2(t) & (t["territory_code"] == "CA-01"), 0.59)    # DEF-06
    _record(defects, "DEF-06", "wrong factor",
            "Territory CA-01 factor 0.95 -> 0.59 (digit typo).",
            "territory", [{"key": "CA-01", "deployed_value": 0.59, "reference_value": 0.95}])

    # ---- mis-keyed territory rows -------------------------------------------
    # DEF-07: IL-03's row re-keyed as IL-02; IL-02's own row removed.
    t.drop(t[_v2(t) & (t["territory_code"] == "IL-02")].index, inplace=True)
    t.loc[_v2(t) & (t["territory_code"] == "IL-03"), "territory_code"] = "IL-02"
    _record(defects, "DEF-07", "mis-keyed territory",
            "IL-03's factor row (1.22) keyed as IL-02; IL-03 left with no row "
            "(engine default 1.00 applies).",
            "territory", [
                {"key": "IL-02", "deployed_value": 1.22, "reference_value": 1.05},
                {"key": "IL-03", "deployed_value": 1.00, "reference_value": 1.22},
            ])

    # DEF-08/09/10: swapped territory codes.
    for defect_id, code_a, code_b in [("DEF-08", "NY-01", "NY-02"),
                                      ("DEF-09", "FL-01", "FL-02"),
                                      ("DEF-10", "GA-01", "GA-02")]:
        fa = float(t.loc[_v2(t) & (t["territory_code"] == code_a), "factor"].iloc[0])
        fb = float(t.loc[_v2(t) & (t["territory_code"] == code_b), "factor"].iloc[0])
        t.loc[_v2(t) & (t["territory_code"] == code_a), "territory_code"] = "__TMP__"
        t.loc[_v2(t) & (t["territory_code"] == code_b), "territory_code"] = code_a
        t.loc[_v2(t) & (t["territory_code"] == "__TMP__"), "territory_code"] = code_b
        _record(defects, defect_id, "mis-keyed territory",
                f"Territory codes {code_a}/{code_b} swapped (factors {fa}/{fb}).",
                "territory", [
                    {"key": code_a, "deployed_value": fb, "reference_value": fa},
                    {"key": code_b, "deployed_value": fa, "reference_value": fb},
                ])

    # ---- off-by-one rate tiers ----------------------------------------------
    a.loc[_v2(a) & (a["band_label"] == "7-9"), "min_age"] = 8        # DEF-11
    _record(defects, "DEF-11", "off-by-one tier",
            "Age band 7-9 lower bound 7 -> 8: age 7 falls into a tier gap and "
            "the engine leaves the quote UNRATED.",
            "age_band", [{"key": "7-9", "deployed_value": "UNRATED", "reference_value": 1.20}])

    a.loc[_v2(a) & (a["band_label"] == "0-1"), "max_age"] = 0        # DEF-12
    _record(defects, "DEF-12", "off-by-one tier",
            "Age band 0-1 upper bound 1 -> 0: age 1 falls into a tier gap and "
            "the engine leaves the quote UNRATED.",
            "age_band", [{"key": "0-1", "deployed_value": "UNRATED", "reference_value": 1.10}])

    a.loc[_v2(a) & (a["band_label"] == "4-6"), "max_age"] = 5        # DEF-13
    _record(defects, "DEF-13", "off-by-one tier",
            "Age band 4-6 upper bound 6 -> 5: age 6 falls into a tier gap and "
            "the engine leaves the quote UNRATED.",
            "age_band", [{"key": "4-6", "deployed_value": "UNRATED", "reference_value": 1.05}])

    # ---- swapped factors ------------------------------------------------------
    for defect_id, df_, keycol, ka, kb, elem, desc in [
        ("DEF-14", b, "breed_group", "BG-03", "BG-04", "breed",
         "Breed factors BG-03 (1.05) and BG-04 (1.12) swapped."),
        ("DEF-15", d, "deductible", 250, 500, "deductible",
         "Deductible factors $250 (1.12) and $500 (1.00) swapped."),
    ]:
        fa = float(df_.loc[_v2(df_) & (df_[keycol] == ka), "factor"].iloc[0])
        fb = float(df_.loc[_v2(df_) & (df_[keycol] == kb), "factor"].iloc[0])
        df_.loc[_v2(df_) & (df_[keycol] == ka), "factor"] = fb
        df_.loc[_v2(df_) & (df_[keycol] == kb), "factor"] = fa
        keyfmt = lambda k: str(k)
        _record(defects, defect_id, "swapped factors", desc, elem, [
            {"key": keyfmt(ka), "deployed_value": fb, "reference_value": fa},
            {"key": keyfmt(kb), "deployed_value": fa, "reference_value": fb},
        ])

    # ---- missing row ----------------------------------------------------------
    tables["territories"] = t = t.drop(
        t[_v2(t) & (t["territory_code"] == "OH-02")].index)           # DEF-16
    _record(defects, "DEF-16", "missing row",
            "Territory OH-02 row deleted; engine default factor 1.00 applies "
            "instead of the manual 0.92.",
            "territory", [{"key": "OH-02", "deployed_value": 1.00, "reference_value": 0.92}])

    # ---- more wrong factor values ---------------------------------------------
    set_factor(p, _v2(p) & (p["plan"] == "Accident-only"), 0.26)     # DEF-17
    _record(defects, "DEF-17", "wrong factor",
            "Plan Accident-only factor 0.62 -> 0.26 (digit typo).",
            "plan", [{"key": "Accident-only", "deployed_value": 0.26, "reference_value": 0.62}])

    set_factor(p, _v2(p) & (p["plan"] == "Comprehensive"), 1.10)      # DEF-18
    _record(defects, "DEF-18", "wrong factor",
            "Plan Comprehensive factor 1.00 -> 1.10 (digit typo).",
            "plan", [{"key": "Comprehensive", "deployed_value": 1.10, "reference_value": 1.00}])

    # ---- duplicate / conflicting row ------------------------------------------
    dup = t[_v2(t) & (t["territory_code"] == "WA-01")].copy()         # DEF-19
    dup["factor"] = 1.99
    tables["territories"] = t = pd.concat([t, dup], ignore_index=True)
    _record(defects, "DEF-19", "duplicate row",
            "Territory WA-01 appears twice; the conflicting second row carries "
            "factor 1.99 and wins under the engine's last-row-wins rule.",
            "territory", [{"key": "WA-01", "deployed_value": 1.99, "reference_value": 1.08}])

    # ---- base-rate typo ---------------------------------------------------------
    base.loc[_v2(base), "annual_base_premium"] = 408.00               # DEF-20
    _record(defects, "DEF-20", "wrong factor",
            "Base annual premium 480.00 -> 408.00 in the v2 table header; "
            "affects every v2 quote.",
            "base", [{"key": "v2", "deployed_value": 408.00, "reference_value": 480.00}])

    # ---- transposed digits ------------------------------------------------------
    set_factor(b, _v2(b) & (b["breed_group"] == "BG-12"), 1.72)       # DEF-21
    _record(defects, "DEF-21", "wrong factor",
            "Breed group BG-12 factor 1.27 -> 1.72 (transposed digits).",
            "breed", [{"key": "BG-12", "deployed_value": 1.72, "reference_value": 1.27}])

    set_factor(t, _v2(t) & (t["territory_code"] == "OH-01"), 1.01)    # DEF-22
    _record(defects, "DEF-22", "wrong factor",
            "Territory OH-01 factor 1.10 -> 1.01 (transposed digits).",
            "territory", [{"key": "OH-01", "deployed_value": 1.01, "reference_value": 1.10}])

    set_factor(a, _v2(a) & (a["band_label"] == "2-3"), 1.09)          # DEF-23
    _record(defects, "DEF-23", "wrong factor",
            "Age band 2-3 factor 1.00 -> 1.09 (digit typo).",
            "age_band", [{"key": "2-3", "deployed_value": 1.09, "reference_value": 1.00}])

    assert len(defects) == EXPECTED_DEFECT_COUNT, \
        f"expected {EXPECTED_DEFECT_COUNT} defects, built {len(defects)}"
    return defects


def build_all(rate_tables_root: str, manifest_path: str) -> dict:
    """Build clean v1/v2 tables, defective v2 tables, and the manifest."""
    clean = build_clean_tables()
    write_tables({"base": clean["base"][clean["base"]["version"] == "v1"],
                  "territories": clean["territories"][clean["territories"]["version"] == "v1"],
                  "breeds": clean["breeds"][clean["breeds"]["version"] == "v1"],
                  "age_bands": clean["age_bands"][clean["age_bands"]["version"] == "v1"],
                  "plans": clean["plans"][clean["plans"]["version"] == "v1"],
                  "deductibles": clean["deductibles"][clean["deductibles"]["version"] == "v1"]},
                 os.path.join(rate_tables_root, "clean", "v1"))
    write_tables({"base": clean["base"][clean["base"]["version"] == "v2"],
                  "territories": clean["territories"][clean["territories"]["version"] == "v2"],
                  "breeds": clean["breeds"][clean["breeds"]["version"] == "v2"],
                  "age_bands": clean["age_bands"][clean["age_bands"]["version"] == "v2"],
                  "plans": clean["plans"][clean["plans"]["version"] == "v2"],
                  "deductibles": clean["deductibles"][clean["deductibles"]["version"] == "v2"]},
                 os.path.join(rate_tables_root, "clean", "v2"))

    defective = {name: df.copy() for name, df in clean.items()}
    manifest = inject_defects(defective)
    write_tables({name: df[df["version"] == "v2"] for name, df in defective.items()},
                 os.path.join(rate_tables_root, "defective", "v2"))

    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"defect_count": len(manifest), "defects": manifest}, fh, indent=2)
    return {"manifest": manifest}
