"""
Anthem Smoke Tests — verify engines produce real computed results.
Run with: pytest tests/test_smoke.py -v
"""

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bue.simulation.monte_carlo import MonteCarloSimulator, SimulationInputs
from bue.simulation.taxonomy import get_industry_defaults
from urpe.core.risk_engine import RiskEngine, RiskFactor


class TestMonteCarloSimulator:
    """BUE Monte Carlo produces real distributions, not hardcoded values."""

    def test_basic_simulation_runs(self):
        sim = MonteCarloSimulator()
        inputs = SimulationInputs(
            current_revenue=5_000_000,
            growth_rate=0.06,
            volatility=0.20,
            n_simulations=1_000,
            horizon_years=5,
            seed=42,
        )
        result = sim.simulate(inputs)

        # Verify real distribution stats
        assert result.mean > 0
        assert result.p5 < result.p25 < result.median < result.p75 < result.p95
        assert 0 <= result.probability_of_decline <= 1
        assert 0 <= result.probability_of_default <= 1
        assert result.n_simulations == 1_000

    def test_higher_volatility_increases_spread(self):
        sim = MonteCarloSimulator()
        low_vol = sim.simulate(SimulationInputs(
            current_revenue=1_000_000, volatility=0.05, n_simulations=2_000, seed=42
        ))
        high_vol = sim.simulate(SimulationInputs(
            current_revenue=1_000_000, volatility=0.40, n_simulations=2_000, seed=42
        ))

        # Higher vol → wider spread
        low_spread = low_vol.p95 - low_vol.p5
        high_spread = high_vol.p95 - high_vol.p5
        assert high_spread > low_spread

    def test_negative_growth_increases_decline_probability(self):
        sim = MonteCarloSimulator()
        growing = sim.simulate(SimulationInputs(
            current_revenue=1_000_000, growth_rate=0.10, n_simulations=2_000, seed=42
        ))
        shrinking = sim.simulate(SimulationInputs(
            current_revenue=1_000_000, growth_rate=-0.10, n_simulations=2_000, seed=42
        ))

        assert shrinking.probability_of_decline > growing.probability_of_decline

    def test_calibration_from_history(self):
        sim = MonteCarloSimulator()
        # Provide revenue history that implies ~10% growth
        result = sim.simulate(SimulationInputs(
            current_revenue=1_000_000,
            revenue_history=[500_000, 600_000, 700_000, 800_000, 900_000, 1_000_000],
            n_simulations=1_000,
            seed=42,
        ))
        # Should calibrate growth from history
        assert result.growth_rate > 0.05  # History shows strong growth
        assert result.mean > 1_000_000   # Should project continued growth

    def test_to_dict_structure(self):
        sim = MonteCarloSimulator()
        result = sim.simulate(SimulationInputs(
            current_revenue=1_000_000, n_simulations=100, seed=42
        ))
        d = result.to_dict()

        assert "distribution" in d
        assert "risk_metrics" in d
        assert "simulation_params" in d
        assert "mean" in d["distribution"]
        assert "var_95" in d["risk_metrics"]
        assert "n_simulations" in d["simulation_params"]


class TestRiskEngine:
    """URPE risk engine produces real sensitivity analysis, not hardcoded tiers."""

    def test_sensitivity_analysis_runs(self):
        engine = RiskEngine()
        inputs = SimulationInputs(
            current_revenue=5_000_000,
            growth_rate=0.04,
            volatility=0.18,
            n_simulations=500,  # Fewer for test speed
            seed=42,
        )
        factors = [
            RiskFactor("growth_rate", 0.04, "Growth rate", 0.02, 0.04),
            RiskFactor("volatility", 0.18, "Volatility", 0.05, 0.10),
        ]

        result = engine.analyze(inputs, factors, n_simulations=500)

        # Should have base case + 4 scenarios per factor (±1σ, ±2σ)
        assert result.base_case is not None
        assert len(result.scenarios) == 8  # 2 factors × 4 perturbations
        assert 0 <= result.overall_risk_score <= 1
        assert result.risk_tier in ("LOW", "MEDIUM", "HIGH", "SEVERE")
        assert len(result.recommendations) > 0

    def test_high_volatility_increases_risk_score(self):
        engine = RiskEngine()
        stable = engine.analyze(
            SimulationInputs(current_revenue=1_000_000, volatility=0.05, n_simulations=500, seed=42),
            [RiskFactor("volatility", 0.05, "Vol", 0.02, 0.04)],
            n_simulations=500,
        )
        volatile = engine.analyze(
            SimulationInputs(current_revenue=1_000_000, volatility=0.40, n_simulations=500, seed=42),
            [RiskFactor("volatility", 0.40, "Vol", 0.10, 0.20)],
            n_simulations=500,
        )

        assert volatile.overall_risk_score > stable.overall_risk_score

    def test_to_dict_structure(self):
        engine = RiskEngine()
        result = engine.analyze(
            SimulationInputs(current_revenue=1_000_000, n_simulations=100, seed=42),
            [RiskFactor("growth_rate", 0.04, "Growth", 0.02, 0.04)],
            n_simulations=100,
        )
        d = result.to_dict()

        assert "base_case" in d
        assert "scenarios" in d
        assert "overall_risk_score" in d
        assert "risk_tier" in d
        assert "recommendations" in d


class TestIndustryTaxonomy:
    """Industry defaults are priors, not hardcoded outputs."""

    def test_known_industries_have_defaults(self):
        for industry in ["software", "energy", "healthcare", "retail"]:
            defaults = get_industry_defaults(industry)
            assert "growth_rate" in defaults
            assert "volatility" in defaults
            assert "operating_margin" in defaults

    def test_unknown_industry_falls_back_to_general(self):
        defaults = get_industry_defaults("underwater_basket_weaving")
        general = get_industry_defaults("general")
        assert defaults == general

    def test_software_is_higher_growth_than_utilities(self):
        sw = get_industry_defaults("software")
        util = get_industry_defaults("utilities")
        assert sw["growth_rate"] > util["growth_rate"]
        assert sw["volatility"] > util["volatility"]
