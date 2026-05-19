"""
Klein — Route Intelligence Layer

Multi-factor route scoring engine that ranks compute/data/energy routing
candidates on latency, cost, carbon, and reliability dimensions.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RouteCandidate:
    """A route candidate with raw metrics."""
    route_id: str
    latency_ms: float
    cost_usd: float
    carbon_gco2: float
    reliability_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredRoute:
    """A route with computed scores and breakdown."""
    route_id: str
    total_score: float
    latency_score: float
    cost_score: float
    carbon_score: float
    reliability_score: float
    score_breakdown: Dict[str, float]
    raw_metrics: Dict[str, Any]


@dataclass
class RouteRecommendation:
    """A single route recommendation with explanation."""
    route_id: str
    total_score: float
    explanation: str
    score_breakdown: Dict[str, float]
    alternatives: List[Dict[str, Any]] = field(default_factory=list)


DEFAULT_WEIGHTS = {
    "latency": 0.25,
    "cost": 0.25,
    "carbon": 0.25,
    "reliability": 0.25,
}


class KleinEngine:
    """
    Route scoring engine that evaluates candidates on multi-factor criteria.

    All scores are normalized to 0.0-1.0 range where higher is better.
    Weights must sum to 1.0. Missing reliability data is penalized.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize the engine with configurable weights.

        Args:
            weights: Dict with keys latency, cost, carbon, reliability.
                     Must sum to 1.0. Defaults to equal weights.
        """
        self.weights = self._validate_weights(weights or DEFAULT_WEIGHTS)
        logger.info(f"KleinEngine initialized with weights: {self.weights}")

    def _validate_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Validate that weights sum to 1.0 and contain required keys."""
        required = {"latency", "cost", "carbon", "reliability"}
        missing = required - set(weights.keys())
        if missing:
            raise ValueError(f"Missing required weight keys: {missing}")

        total = sum(weights.values())
        if not (0.999 <= total <= 1.001):
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        for key, val in weights.items():
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"Weight '{key}' must be between 0.0 and 1.0, got {val}")

        return weights

    def _normalize_value(self, value: float, min_val: float, max_val: float,
                         invert: bool = False) -> float:
        """
        Normalize a value to 0.0-1.0 range.

        Args:
            value: The value to normalize
            min_val: Minimum value in the dataset
            max_val: Maximum value in the dataset
            invert: If True, invert so lower raw values score higher

        Returns:
            Normalized score in 0.0-1.0 range
        """
        if max_val == min_val:
            return 1.0

        normalized = (value - min_val) / (max_val - min_val)
        return 1.0 - normalized if invert else normalized

    def _compute_latency_score(self, latency_ms: float,
                                min_latency: float,
                                max_latency: float) -> float:
        """Compute latency score (lower latency = higher score)."""
        return self._normalize_value(latency_ms, min_latency, max_latency, invert=True)

    def _compute_cost_score(self, cost_usd: float,
                            min_cost: float,
                            max_cost: float) -> float:
        """Compute cost score (lower cost = higher score)."""
        return self._normalize_value(cost_usd, min_cost, max_cost, invert=True)

    def _compute_carbon_score(self, carbon_gco2: float,
                              min_carbon: float,
                              max_carbon: float) -> float:
        """Compute carbon score (lower carbon = higher score)."""
        return self._normalize_value(carbon_gco2, min_carbon, max_carbon, invert=True)

    def _compute_reliability_score(self, reliability: Optional[float]) -> float:
        """
        Compute reliability score.

        Missing reliability data is penalized with a score of 0.5.
        """
        if reliability is None:
            return 0.5
        return max(0.0, min(1.0, reliability))

    def score(self, candidates: List[RouteCandidate],
              weights: Optional[Dict[str, float]] = None) -> List[ScoredRoute]:
        """
        Score each route candidate on multi-factor criteria.

        Args:
            candidates: List of route candidates to score
            weights: Optional override weights for this scoring run

        Returns:
            List of scored routes with breakdowns
        """
        if not candidates:
            return []

        effective_weights = self._validate_weights(weights) if weights else self.weights

        if len(candidates) > 50:
            logger.warning(f"Truncating {len(candidates)} candidates to 50 (max allowed)")
            candidates = candidates[:50]

        min_latency = min(c.latency_ms for c in candidates)
        max_latency = max(c.latency_ms for c in candidates)
        min_cost = min(c.cost_usd for c in candidates)
        max_cost = max(c.cost_usd for c in candidates)
        min_carbon = min(c.carbon_gco2 for c in candidates)
        max_carbon = max(c.carbon_gco2 for c in candidates)

        scored: List[ScoredRoute] = []

        for candidate in candidates:
            latency_score = self._compute_latency_score(
                candidate.latency_ms, min_latency, max_latency
            )
            cost_score = self._compute_cost_score(
                candidate.cost_usd, min_cost, max_cost
            )
            carbon_score = self._compute_carbon_score(
                candidate.carbon_gco2, min_carbon, max_carbon
            )
            reliability_score = self._compute_reliability_score(
                candidate.reliability_score
            )

            total_score = (
                latency_score * effective_weights["latency"] +
                cost_score * effective_weights["cost"] +
                carbon_score * effective_weights["carbon"] +
                reliability_score * effective_weights["reliability"]
            )

            scored.append(ScoredRoute(
                route_id=candidate.route_id,
                total_score=total_score,
                latency_score=latency_score,
                cost_score=cost_score,
                carbon_score=carbon_score,
                reliability_score=reliability_score,
                score_breakdown={
                    "latency": latency_score * effective_weights["latency"],
                    "cost": cost_score * effective_weights["cost"],
                    "carbon": carbon_score * effective_weights["carbon"],
                    "reliability": reliability_score * effective_weights["reliability"],
                },
                raw_metrics={
                    "latency_ms": candidate.latency_ms,
                    "cost_usd": candidate.cost_usd,
                    "carbon_gco2": candidate.carbon_gco2,
                    "reliability_score": candidate.reliability_score,
                }
            ))

        return scored

    def rank(self, scored_candidates: List[ScoredRoute],
             top_n: int = 10) -> List[ScoredRoute]:
        """
        Rank scored candidates and return top N.

        Args:
            scored_candidates: List of scored routes
            top_n: Number of top candidates to return

        Returns:
            Top N ranked candidates, sorted by total_score descending
        """
        ranked = sorted(scored_candidates, key=lambda c: c.total_score, reverse=True)
        return ranked[:top_n]

    def recommend(self, candidates: List[RouteCandidate],
                  weights: Optional[Dict[str, float]] = None,
                  workload_type: str = "batch") -> RouteRecommendation:
        """
        Produce a single route recommendation with explanation.

        Args:
            candidates: Route candidates to evaluate
            weights: Optional scoring weights
            workload_type: Workload type for heuristic adjustments

        Returns:
            Route recommendation with explanation
        """
        adjusted_weights = self._adjust_weights_for_workload(
            weights or self.weights, workload_type
        )

        scored = self.score(candidates, adjusted_weights)
        ranked = self.rank(scored, top_n=1)

        if not ranked:
            raise ValueError("No candidates to recommend")

        top = ranked[0]
        explanation = self._generate_explanation(top, workload_type)

        alternatives = []
        if len(scored) > 1:
            for alt in self.rank(scored, top_n=3)[1:]:
                alternatives.append({
                    "route_id": alt.route_id,
                    "total_score": alt.total_score,
                    "score_delta": top.total_score - alt.total_score,
                })

        return RouteRecommendation(
            route_id=top.route_id,
            total_score=top.total_score,
            explanation=explanation,
            score_breakdown=top.score_breakdown,
            alternatives=alternatives,
        )

    def _adjust_weights_for_workload(self, weights: Dict[str, float],
                                      workload_type: str) -> Dict[str, float]:
        """
        Adjust weights based on workload type heuristics.

        - realtime: Higher latency weight
        - batch: Higher cost weight
        - bulk: Higher carbon weight
        - critical: Higher reliability weight
        """
        adjusted = dict(weights)

        if workload_type == "realtime":
            adjusted["latency"] = min(1.0, adjusted["latency"] * 1.5)
            adjusted["cost"] = max(0.0, adjusted["cost"] * 0.7)
        elif workload_type == "batch":
            adjusted["cost"] = min(1.0, adjusted["cost"] * 1.5)
            adjusted["latency"] = max(0.0, adjusted["latency"] * 0.7)
        elif workload_type == "bulk":
            adjusted["carbon"] = min(1.0, adjusted["carbon"] * 1.5)
            adjusted["latency"] = max(0.0, adjusted["latency"] * 0.7)
        elif workload_type == "critical":
            adjusted["reliability"] = min(1.0, adjusted["reliability"] * 1.5)
            adjusted["cost"] = max(0.0, adjusted["cost"] * 0.7)

        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}

        return adjusted

    def _generate_explanation(self, route: ScoredRoute,
                              workload_type: str) -> str:
        """Generate human-readable explanation for the recommendation."""
        reasons = []

        best_factor = max(route.score_breakdown, key=route.score_breakdown.get)
        reasons.append(f"Best {best_factor} performance among candidates")

        if route.raw_metrics.get("reliability_score") is None:
            reasons.append("Note: reliability data missing, scored conservatively")

        if workload_type == "realtime":
            reasons.append("Optimized for low-latency workload")
        elif workload_type == "batch":
            reasons.append("Optimized for cost-effective batch processing")
        elif workload_type == "bulk":
            reasons.append("Optimized for lower carbon emissions")
        elif workload_type == "critical":
            reasons.append("Optimized for maximum reliability")

        return "; ".join(reasons)
