"""Approved Rate Manual - authoritative reference implementation.

This module is an *independent* implementation of the rating formula published
in the (synthetic) Approved Rate Manual for pet-insurance pricing versions
``v1`` (in force) and ``v2`` (candidate). It is coded separately from the
deployed rating engine and reads its parameters from the authoritative manual
tables below - never from the deployed CSV rate tables.

Rating formula (Manual section 4.2):

    annual_premium = round(base_premium
                           * territory_factor
                           * breed_factor
                           * age_factor
                           * plan_factor
                           * deductible_factor, 2)

The validation suite differentially compares this reference implementation
against the deployed engine. Because both implement the same published
formula, any premium difference on clean tables would indicate a defect in
the *deployed tables* (the object under test), not in the formula.

ALL DATA IN THIS REPOSITORY IS SYNTHETIC and generated for demonstration.
"""

from __future__ import annotations

VERSIONS = ("v1", "v2")

BASE_PREMIUM = {"v1": 480.00, "v2": 480.00}

TERRITORY_FACTORS = {
    "v1": {
        "IL-01": 0.98, "IL-02": 1.05, "IL-03": 1.22,
        "TX-01": 1.10, "TX-02": 1.18, "TX-03": 0.95,
        "CA-01": 0.95, "CA-02": 1.25,
        "FL-01": 1.12, "FL-02": 1.28,
        "NY-01": 1.15, "NY-02": 1.30,
        "OH-01": 1.10, "OH-02": 0.92,
        "GA-01": 1.02, "GA-02": 0.88,
        "WA-01": 1.08, "WA-02": 0.97,
    },
    "v2": {
        "IL-01": 0.98, "IL-02": 1.05, "IL-03": 1.22,
        "TX-01": 1.10, "TX-02": 1.24, "TX-03": 0.95,
        "CA-01": 0.95, "CA-02": 1.30,
        "FL-01": 1.12, "FL-02": 1.22,
        "NY-01": 1.15, "NY-02": 1.30,
        "OH-01": 1.10, "OH-02": 0.92,
        "GA-01": 1.02, "GA-02": 0.88,
        "WA-01": 1.08, "WA-02": 0.97,
    },
}

BREED_FACTORS = {
    "v1": {
        "BG-01": 0.82, "BG-02": 0.90, "BG-03": 1.05, "BG-04": 1.12,
        "BG-05": 0.95, "BG-06": 1.20, "BG-07": 1.32, "BG-08": 1.08,
        "BG-09": 0.88, "BG-10": 1.15, "BG-11": 1.25, "BG-12": 1.27,
        "BG-13": 0.98, "BG-14": 1.18, "BG-15": 1.35, "BG-16": 1.42,
    },
    "v2": {
        "BG-01": 0.82, "BG-02": 0.88, "BG-03": 1.05, "BG-04": 1.12,
        "BG-05": 0.95, "BG-06": 1.20, "BG-07": 1.32, "BG-08": 1.08,
        "BG-09": 0.88, "BG-10": 1.15, "BG-11": 1.25, "BG-12": 1.27,
        "BG-13": 0.98, "BG-14": 1.18, "BG-15": 1.40, "BG-16": 1.42,
    },
}

AGE_BANDS = {
    "v1": [
        {"band_id": "AB-1", "band_label": "0-1",  "min_age": 0,  "max_age": 1,  "factor": 1.10},
        {"band_id": "AB-2", "band_label": "2-3",  "min_age": 2,  "max_age": 3,  "factor": 1.00},
        {"band_id": "AB-3", "band_label": "4-6",  "min_age": 4,  "max_age": 6,  "factor": 1.05},
        {"band_id": "AB-4", "band_label": "7-9",  "min_age": 7,  "max_age": 9,  "factor": 1.20},
        {"band_id": "AB-5", "band_label": "10+",  "min_age": 10, "max_age": 99, "factor": 1.45},
    ],
    "v2": [
        {"band_id": "AB-1", "band_label": "0-1",  "min_age": 0,  "max_age": 1,  "factor": 1.10},
        {"band_id": "AB-2", "band_label": "2-3",  "min_age": 2,  "max_age": 3,  "factor": 1.00},
        {"band_id": "AB-3", "band_label": "4-6",  "min_age": 4,  "max_age": 6,  "factor": 1.05},
        {"band_id": "AB-4", "band_label": "7-9",  "min_age": 7,  "max_age": 9,  "factor": 1.20},
        {"band_id": "AB-5", "band_label": "10+",  "min_age": 10, "max_age": 99, "factor": 1.52},
    ],
}

PLAN_FACTORS = {
    "v1": {"Comprehensive": 1.00, "Accident-only": 0.62, "Wellness+": 1.18},
    "v2": {"Comprehensive": 1.00, "Accident-only": 0.62, "Wellness+": 1.22},
}

DEDUCTIBLE_FACTORS = {
    "v1": {250: 1.12, 500: 1.00, 1000: 0.86},
    "v2": {250: 1.12, 500: 1.00, 1000: 0.84},
}

PLANS = ["Comprehensive", "Accident-only", "Wellness+"]
DEDUCTIBLES = [250, 500, 1000]


def resolve_age_band(age_years: int, version: str) -> dict:
    """Return the manual age band covering ``age_years``."""
    for band in AGE_BANDS[version]:
        if band["min_age"] <= age_years <= band["max_age"]:
            return band
    raise KeyError(f"no manual age band for age {age_years} in {version}")


def rating_formula(base, f_territory, f_breed, f_age, f_plan, f_deductible) -> float:
    """Manual section 4.2 - canonical premium formula. Returns dollars."""
    return round(base * f_territory * f_breed * f_age * f_plan * f_deductible + 1e-9, 2)


def calculate_premium(quote: dict, version: str) -> dict:
    """Reference premium for a quote under ``version``.

    Returns {"premium_cents": int, "factors": {...}, "band_label": str}.
    """
    band = resolve_age_band(quote["pet_age_years"], version)
    factors = {
        "base": BASE_PREMIUM[version],
        "territory": TERRITORY_FACTORS[version][quote["territory"]],
        "breed": BREED_FACTORS[version][quote["breed_group"]],
        "age": band["factor"],
        "plan": PLAN_FACTORS[version][quote["plan"]],
        "deductible": DEDUCTIBLE_FACTORS[version][quote["deductible"]],
    }
    premium = rating_formula(
        factors["base"], factors["territory"], factors["breed"],
        factors["age"], factors["plan"], factors["deductible"],
    )
    return {
        "premium_cents": int(round(premium * 100)),
        "factors": factors,
        "band_label": band["band_label"],
    }
