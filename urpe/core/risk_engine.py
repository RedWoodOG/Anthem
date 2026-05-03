"""
URPE Risk Engine — Real probabilistic risk assessment.

Consumes BUE Monte Carlo baselines and stress-tests them under
adversarial conditions. No aliens. No interplanetary missions.
No hardcoded floats.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bue.simulation.monte_carlo import MonteCarloSimulator, SimulationInputs, SimulationResult

logger = logging.getLogger(__name__)


@dataclass
class RiskFactor:
    """A single risk factor that can be perturbed."""
    name: str
    base_value: float
    description: str
    perturbation_1sigma: float  # ±1σ shift
    perturbation_2sigma: float  # ±2σ shift


@dataclass
class ScenarioResult:
    """Result of running a stressed scenario."""
    scenario_name: str
    perturbations: Dict[str, float]  # factor_name -> perturbed value
    simulation: Dict[str, Any]       # SimulationResult.to_dict()
    delta_vs_base: Dict[str, float]  # How this scenario differs from base


@dataclass
class SensitivityAnalysis:
    """Complete sensitivity analysis across multiple risk factors."""
    base_case: Dict[str, Any]
    scenarios: List[ScenarioResult]
    risk_factors: List[RiskFactor]
    overall_risk_score: float  # 0-1, computed from scenario outcomes
    risk_tier: str             # LOW, MEDIUM, HIGH, SEVERE
    recommendations: List[str]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_case": self.base_case,
            "scenarios": [
                {
                    "name": s.scenario_name,
                    "perturbations": s.perturbations,
                    "simulation": s.simulation,
                    "delta_vs_base": s.delta_vs_base,
                }
                for s in self.scenarios
            ],
            "risk_factors": [
                {
                    "name": rf.name,
                    "base_value": rf.base_value,
                    "description": rf.description,
                }
                for rf in self.risk_factors
            ],
            "overall_risk_score": round(self.overall_risk_score, 4),
            "risk_tier": self.risk_tier,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
        }


class RiskEngine:
    """
    Runs adversarial scenario analysis on top of BUE Monte Carlo baselines.

    For each risk factor:
    1. Perturb ±1σ and ±2σ
    2. Re-run Monte Carlo with perturbed inputs
    3. Compare stressed results to base case
    4. Score overall risk from worst-case scenarios
    """

    def __init__(self) -> None:
        self.simulator = MonteCarloSimulator()

    def analyze(
        self,
        base_inputs: SimulationInputs,
        risk_factors: List[RiskFactor],
        n_simulations: int = 5_000,  # Fewer per scenario for speed
    ) -> SensitivityAnalysis:
        """Run sensitivity analysis across all risk factors."""

        # 1. Run base case
        logger.info("Running base case simulation")
        base_result = self.simulator.simulate(base_inputs)
        base_dict = base_result.to_dict()

        # 2. Run stressed scenarios
        scenarios: List[ScenarioResult] = []
        for factor in risk_factors:
            for sigma_label, sigma_mult in [("-2σ", -2), ("-1σ", -1), ("+1σ", 1), ("+2σ", 2)]:
                perturbation = factor.perturbation_1sigma * abs(sigma_mult)
                if sigma_mult < 0:
                    perturbation = -perturbation

                stressed = self._perturb_inputs(base_inputs, factor.name, perturbation)
                stressed.n_simulations = n_simulations

                scenario_name = f"{factor.name} {sigma_label}"
                logger.info("Running scenario: %s", scenario_name)

                stressed_result = self.simulator.simulate(stressed)
                stressed_dict = stressed_result.to_dict()

                delta = self._compute_delta(base_result, stressed_result)
                scenarios.append(ScenarioResult(
                    scenario_name=scenario_name,
                    perturbations={factor.name: perturbation},
                    simulation=stressed_dict,
                    delta_vs_base=delta,
                ))

        # 3. Compute overall risk score
        risk_score = self._compute_overall_risk(base_result, scenarios)
        risk_tier = self._score_to_tier(risk_score)

        # 4. Generate recommendations
        recommendations = self._generate_recommendations(
            base_result, scenarios, risk_factors, risk_score
        )

        warnings = []
        if base_result.probability_of_default > 0.1:
            warnings.append(
                f"Base case probability of default is {base_result.probability_of_default:.1%} — elevated risk"
            )
        if risk_score > 0.6:
            warnings.append("Overall risk score exceeds 0.6 — detailed review recommended")

        return SensitivityAnalysis(
            base_case=base_dict,
            scenarios=scenarios,
            risk_factors=risk_factors,
            overall_risk_score=risk_score,
            risk_tier=risk_tier,
            recommendations=recommendations,
            warnings=warnings,
        )

    def _perturb_inputs(
        self, base: SimulationInputs, factor_name: str, perturbation: float
    ) -> SimulationInputs:
        """Create a copy of inputs with one factor perturbed."""
        # Map factor names to SimulationInputs fields
        field_map = {
            "growth_rate": "growth_rate",
            "volatility": "volatility",
            "operating_margin": "operating_margin",
            "debt_service_ratio": "debt_service_ratio",
            "revenue": "current_revenue",
        }

        field_name = field_map.get(factor_name, factor_name)
        kwargs = {
            "current_revenue": base.current_revenue,
            "growth_rate": base.growth_rate,
            "volatility": base.volatility,
            "operating_margin": base.operating_margin,
            "debt_service_ratio": base.debt_service_ratio,
            "revenue_history": base.revenue_history,
            "n_simulations": base.n_simulations,
            "horizon_years": base.horizon_years,
        }

        if field_name in kwargs:
            kwargs[field_name] = max(0.001, kwargs[field_name] + perturbation)

        return SimulationInputs(**kwargs)

    def _compute_delta(
        self, base: SimulationResult, stressed: SimulationResult
    ) -> Dict[str, float]:
        """Compute difference between base and stressed scenarios."""
        return {
            "mean_change_pct": round(
                (stressed.mean - base.mean) / base.mean * 100 if base.mean else 0, 2
            ),
            "p5_change_pct": round(
                (stressed.p5 - base.p5) / base.p5 * 100 if base.p5 else 0, 2
            ),
            "var_95_change_pct": round(
                (stressed.var_95 - base.var_95) / base.var_95 * 100 if base.var_95 else 0, 2
            ),
            "default_prob_change": round(
                stressed.probability_of_default - base.probability_of_default, 4
            ),
            "decline_prob_change": round(
                stressed.probability_of_decline - base.probability_of_decline, 4
            ),
        }

    def _compute_overall_risk(
        self, base: SimulationResult, scenarios: List[ScenarioResult]
    ) -> float:
        """
        Compute a single risk score from all scenarios.
        Higher = more risk. Range [0, 1].
        """
        if not scenarios:
            return base.probability_of_default

        # Worst-case metrics across scenarios
        worst_default_prob = max(
            s.simulation["risk_metrics"]["probability_of_default"]
            for s in scenarios
        )
        worst_decline_prob = max(
            s.simulation["risk_metrics"]["probability_of_decline"]
            for s in scenarios
        )
        worst_drawdown = max(
            s.simulation["risk_metrics"]["max_drawdown_mean"]
            for s in scenarios
        )

        # Weighted combination
        score = (
            0.40 * worst_default_prob
            + 0.30 * worst_decline_prob
            + 0.30 * worst_drawdown
        )

        return min(1.0, max(0.0, score))

    @staticmethod
    def _score_to_tier(score: float) -> str:
        if score > 0.7:
            return "SEVERE"
        if score > 0.4:
            return "HIGH"
        if score > 0.2:
            return "MEDIUM"
        return "LOW"

    def _generate_recommendations(
        self,
        base: SimulationResult,
        scenarios: List[ScenarioResult],
        risk_factors: List[RiskFactor],
        risk_score: float,
    ) -> List[str]:
        """Generate actionable recommendations based on analysis."""
        recs = []

        if risk_score > 0.7:
            recs.append("CRITICAL: Overall risk is severe. Do not proceed without risk mitigation.")

        # Find most sensitive factor
        if scenarios:
            worst_scenario = max(
                scenarios,
                key=lambda s: s.simulation["risk_metrics"]["probability_of_default"],
            )
            recs.append(
                f"Most sensitive factor: '{worst_scenario.scenario_name}' — "
                f"default probability reaches "
                f"{worst_scenario.simulation['risk_metrics']['probability_of_default']:.1%}"
            )

        if base.probability_of_default > 0.05:
            recs.append(
                f"Base case default probability ({base.probability_of_default:.1%}) "
                f"exceeds 5% threshold. Consider risk mitigation before proceeding."
            )

        if base.max_drawdown_mean > 0.3:
            recs.append(
                f"Average max drawdown of {base.max_drawdown_mean:.0%} is significant. "
                f"Consider revenue diversification."
            )

        if not recs:
            recs.append("Risk profile is within acceptable bounds for the base case.")

        return recs


# ---------------------------------------------------------------------------
# Tool handlers (for Luna harness)
# ---------------------------------------------------------------------------

async def handle_sensitivity_analysis(params: Dict[str, Any]) -> Dict[str, Any]:
    """Tool handler for run_sensitivity_analysis."""
    engine = RiskEngine()

    base_inputs = SimulationInputs(
        current_revenue=params.get("current_revenue", 0),
        growth_rate=params.get("growth_rate", 0.04),
        volatility=params.get("volatility", 0.18),
        operating_margin=params.get("operating_margin", 0.18),
        debt_service_ratio=params.get("debt_service_ratio", 0.0),
        revenue_history=params.get("revenue_history"),
        horizon_years=params.get("horizon_years", 5),
    )

    if base_inputs.current_revenue <= 0:
        return {"error": "current_revenue must be positive"}

    # Build risk factors from params or use defaults
    raw_factors = params.get("risk_factors", [])
    if not raw_factors:
        raw_factors = [
            {"name": "growth_rate", "description": "Revenue growth rate", "perturbation_1sigma": 0.02},
            {"name": "volatility", "description": "Revenue volatility", "perturbation_1sigma": 0.05},
            {"name": "operating_margin", "description": "Operating margin", "perturbation_1sigma": 0.03},
        ]

    risk_factors = [
        RiskFactor(
            name=rf["name"],
            base_value=getattr(base_inputs, rf["name"], 0),
            description=rf.get("description", rf["name"]),
            perturbation_1sigma=rf.get("perturbation_1sigma", 0.02),
            perturbation_2sigma=rf.get("perturbation_2sigma", rf.get("perturbation_1sigma", 0.02) * 2),
        )
        for rf in raw_factors
    ]

    result = engine.analyze(base_inputs, risk_factors)
    return result.to_dict()
