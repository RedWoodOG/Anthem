"""
BUE Industry Taxonomy Defaults.
These are priors, not conclusions.
Used only when company-specific data is missing.
"""

from typing import Dict

# Conservative defaults by industry
DEFAULTS: Dict[str, Dict[str, float]] = {
    "general": {"growth_rate": 0.04, "volatility": 0.18, "operating_margin": 0.18},
    "software": {"growth_rate": 0.12, "volatility": 0.25, "operating_margin": 0.22},
    "saas": {"growth_rate": 0.15, "volatility": 0.28, "operating_margin": 0.25},
    "manufacturing": {"growth_rate": 0.03, "volatility": 0.16, "operating_margin": 0.14},
    "energy": {"growth_rate": 0.03, "volatility": 0.12, "operating_margin": 0.22},
    "utilities": {"growth_rate": 0.02, "volatility": 0.10, "operating_margin": 0.20},
    "healthcare": {"growth_rate": 0.05, "volatility": 0.15, "operating_margin": 0.18},
    "biotech": {"growth_rate": 0.20, "volatility": 0.35, "operating_margin": 0.05},
    "retail": {"growth_rate": 0.04, "volatility": 0.20, "operating_margin": 0.08},
    "real_estate": {"growth_rate": 0.03, "volatility": 0.10, "operating_margin": 0.30},
    "finance": {"growth_rate": 0.05, "volatility": 0.14, "operating_margin": 0.26},
}


def get_industry_defaults(industry: str) -> Dict[str, float]:
    """Return prior defaults for an industry."""
    return DEFAULTS.get(industry.lower(), DEFAULTS["general"])
