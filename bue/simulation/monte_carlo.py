"""
BUE Monte Carlo Simulator — Real probabilistic underwriting.

Uses geometric Brownian motion to simulate revenue paths,
calculates VaR, CVaR, probability of default, and distribution statistics.
No hardcoded floats. No theater.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Reproducible but different per run — set seed=None for production
DEFAULT_SEED = None
DEFAULT_N_SIMULATIONS = 10_000
DEFAULT_HORIZON_YEARS = 5
DEFAULT_STEPS_PER_YEAR = 12  # Monthly steps


@dataclass
class SimulationInputs:
    """Inputs for a Monte Carlo revenue simulation."""
    current_revenue: float                          # Annual revenue (USD)
    growth_rate: float = 0.04                       # Annual growth rate (decimal)
    volatility: float = 0.18                        # Annual volatility (decimal)
    operating_margin: float = 0.18                  # Operating margin (decimal)
    debt_service_ratio: float = 0.0                 # Annual debt payments / revenue
    revenue_history: Optional[List[float]] = None   # Historical annual revenues
    n_simulations: int = DEFAULT_N_SIMULATIONS
    horizon_years: int = DEFAULT_HORIZON_YEARS
    seed: Optional[int] = DEFAULT_SEED


@dataclass
class SimulationResult:
    """Complete output from a Monte Carlo simulation."""
    # Distribution statistics for terminal revenue
    mean: float
    median: float
    std_dev: float
    p5: float       # 5th percentile (downside)
    p25: float      # 25th percentile
    p75: float      # 75th percentile
    p95: float      # 95th percentile (upside)

    # Risk metrics
    var_95: float           # Value at Risk (95% confidence)
    cvar_95: float          # Conditional VaR (expected loss beyond VaR)
    probability_of_decline: float   # P(terminal < current)
    probability_of_default: float   # P(terminal < debt service threshold)
    max_drawdown_mean: float        # Average max drawdown across paths

    # Inputs echo (for audit)
    n_simulations: int
    horizon_years: int
    growth_rate: float
    volatility: float
    current_revenue: float

    # Path statistics
    all_terminal_values: List[float] = field(default_factory=list, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "distribution": {
                "mean": round(self.mean, 2),
                "median": round(self.median, 2),
                "std_dev": round(self.std_dev, 2),
                "p5": round(self.p5, 2),
                "p25": round(self.p25, 2),
                "p75": round(self.p75, 2),
                "p95": round(self.p95, 2),
            },
            "risk_metrics": {
                "var_95": round(self.var_95, 2),
                "cvar_95": round(self.cvar_95, 2),
                "probability_of_decline": round(self.probability_of_decline, 4),
                "probability_of_default": round(self.probability_of_default, 4),
                "max_drawdown_mean": round(self.max_drawdown_mean, 4),
            },
            "simulation_params": {
                "n_simulations": self.n_simulations,
                "horizon_years": self.horizon_years,
                "growth_rate": self.growth_rate,
                "volatility": self.volatility,
                "current_revenue": round(self.current_revenue, 2),
            },
        }


class MonteCarloSimulator:
    """
    Geometric Brownian Motion revenue simulator.

    Models revenue as:  dS = μ·S·dt + σ·S·dW

    Where:
    - S = revenue at time t
    - μ = drift (growth rate)
    - σ = volatility
    - dW = Wiener process increment
    """

    def simulate(self, inputs: SimulationInputs) -> SimulationResult:
        """
        Run the full Monte Carlo simulation.
        Returns distribution statistics and risk metrics.
        """
        rng = np.random.default_rng(inputs.seed)

        # Calibrate from history if available
        growth, vol = self._calibrate(inputs)

        dt = 1.0 / DEFAULT_STEPS_PER_YEAR
        n_steps = inputs.horizon_years * DEFAULT_STEPS_PER_YEAR
        S0 = inputs.current_revenue

        logger.info(
            "Running %d simulations: S0=%.2f, μ=%.4f, σ=%.4f, horizon=%dy",
            inputs.n_simulations, S0, growth, vol, inputs.horizon_years,
        )

        # Generate all random increments at once (vectorized)
        # Shape: (n_simulations, n_steps)
        z = rng.standard_normal((inputs.n_simulations, n_steps))

        # GBM: S(t+dt) = S(t) * exp((μ - σ²/2)dt + σ√dt·Z)
        drift_term = (growth - 0.5 * vol**2) * dt
        diffusion_term = vol * np.sqrt(dt) * z

        log_returns = drift_term + diffusion_term
        log_paths = np.cumsum(log_returns, axis=1)

        # Full price paths
        paths = S0 * np.exp(log_paths)

        # Prepend S0 to each path for drawdown calc
        full_paths = np.column_stack([np.full(inputs.n_simulations, S0), paths])

        # Terminal values
        terminal = paths[:, -1]

        # Max drawdown per path
        running_max = np.maximum.accumulate(full_paths, axis=1)
        drawdowns = (running_max - full_paths) / running_max
        max_drawdowns = np.max(drawdowns, axis=1)

        # Debt service threshold
        if inputs.debt_service_ratio > 0:
            default_threshold = inputs.current_revenue * inputs.debt_service_ratio * 2
        else:
            default_threshold = inputs.current_revenue * 0.3  # 70% revenue loss

        # Compute VaR as loss from current revenue
        losses = S0 - terminal
        var_95 = float(np.percentile(losses, 95))
        # CVaR = expected loss beyond VaR
        tail_losses = losses[losses >= var_95]
        cvar_95 = float(np.mean(tail_losses)) if len(tail_losses) > 0 else var_95

        result = SimulationResult(
            mean=float(np.mean(terminal)),
            median=float(np.median(terminal)),
            std_dev=float(np.std(terminal)),
            p5=float(np.percentile(terminal, 5)),
            p25=float(np.percentile(terminal, 25)),
            p75=float(np.percentile(terminal, 75)),
            p95=float(np.percentile(terminal, 95)),
            var_95=max(0.0, var_95),
            cvar_95=max(0.0, cvar_95),
            probability_of_decline=float(np.mean(terminal < S0)),
            probability_of_default=float(np.mean(terminal < default_threshold)),
            max_drawdown_mean=float(np.mean(max_drawdowns)),
            n_simulations=inputs.n_simulations,
            horizon_years=inputs.horizon_years,
            growth_rate=growth,
            volatility=vol,
            current_revenue=S0,
        )

        logger.info(
            "Simulation complete: mean=%.2f, p5=%.2f, p95=%.2f, P(decline)=%.3f",
            result.mean, result.p5, result.p95, result.probability_of_decline,
        )

        return result

    def _calibrate(self, inputs: SimulationInputs) -> tuple:
        """
        Calibrate growth and volatility from historical data if available.
        Falls back to provided defaults (flagged as priors).
        """
        if inputs.revenue_history and len(inputs.revenue_history) >= 3:
            revenues = np.array(inputs.revenue_history, dtype=float)
            # Filter out zeros/negatives
            revenues = revenues[revenues > 0]
            if len(revenues) >= 3:
                log_returns = np.diff(np.log(revenues))
                historical_growth = float(np.mean(log_returns))
                historical_vol = float(np.std(log_returns))
                if historical_vol > 0:
                    logger.info(
                        "Calibrated from %d data points: μ=%.4f, σ=%.4f",
                        len(revenues), historical_growth, historical_vol,
                    )
                    return historical_growth, historical_vol

        logger.info("Using prior defaults: μ=%.4f, σ=%.4f", inputs.growth_rate, inputs.volatility)
        return inputs.growth_rate, inputs.volatility


# ---------------------------------------------------------------------------
# Tool handler (for Luna harness integration)
# ---------------------------------------------------------------------------

async def handle_monte_carlo_simulate(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tool handler for the BUE agent's monte_carlo_simulate tool.
    """
    simulator = MonteCarloSimulator()
    inputs = SimulationInputs(
        current_revenue=params.get("current_revenue", 0),
        growth_rate=params.get("growth_rate", 0.04),
        volatility=params.get("volatility", 0.18),
        operating_margin=params.get("operating_margin", 0.18),
        debt_service_ratio=params.get("debt_service_ratio", 0.0),
        revenue_history=params.get("revenue_history"),
        n_simulations=params.get("n_simulations", DEFAULT_N_SIMULATIONS),
        horizon_years=params.get("horizon_years", DEFAULT_HORIZON_YEARS),
    )

    if inputs.current_revenue <= 0:
        return {"error": "current_revenue must be positive"}

    result = simulator.simulate(inputs)
    return result.to_dict()
