"""
Domain Cortex Synthesis Engine.

Aggregates results from multiple agents and finds cross-domain correlations.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Contradiction:
    """A contradiction detected between agent outputs."""
    agent_a: str
    agent_b: str
    claim_a: str
    claim_b: str
    domain: str
    severity: str  # "low", "medium", "high"
    confidence: float


@dataclass
class Correlation:
    """A correlation found across agent outputs."""
    agents: List[str]
    description: str
    strength: float  # 0.0 to 1.0
    correlation_type: str  # "positive", "negative", "causal", "coincident"
    domains: List[str]


@dataclass
class SynthesisReport:
    """Unified synthesis report from multiple agent results."""
    contributing_agents: List[str]
    aggregated_metrics: Dict[str, Any]
    contradictions: List[Contradiction]
    correlations: List[Correlation]
    overall_confidence: float
    summary: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DomainCortexEngine:
    """
    Synthesis engine that aggregates results from multiple specialist agents.
    
    Responsibilities:
    - Aggregate key metrics from multiple NormalizedResult outputs
    - Detect contradictions between agent conclusions
    - Score confidence based on agent reliability and data freshness
    - Find cross-domain correlations
    """
    
    def __init__(self, max_results: int = 10):
        """
        Initialize the synthesis engine.
        
        Args:
            max_results: Maximum number of result sets to process at once
        """
        self.max_results = max_results
        self._agent_reliability: Dict[str, float] = {}
    
    def set_agent_reliability(self, agent_id: str, reliability: float) -> None:
        """
        Set reliability score for an agent (used in confidence weighting).
        
        Args:
            agent_id: Agent identifier
            reliability: Reliability score from 0.0 to 1.0
        """
        self._agent_reliability[agent_id] = max(0.0, min(1.0, reliability))
    
    def aggregate(self, results: List[Dict[str, Any]]) -> SynthesisReport:
        """
        Aggregate multiple agent results into a unified synthesis report.
        
        Args:
            results: List of NormalizedResult dicts from different agents
            
        Returns:
            SynthesisReport with aggregated metrics, contradictions, and correlations
            
        Raises:
            ValueError: If more than max_results are provided
        """
        if len(results) > self.max_results:
            raise ValueError(
                f"Too many results: {len(results)} exceeds maximum of {self.max_results}"
            )
        
        if not results:
            return SynthesisReport(
                contributing_agents=[],
                aggregated_metrics={},
                contradictions=[],
                correlations=[],
                overall_confidence=0.0,
                summary="No results provided for synthesis."
            )
        
        # Extract contributing agent IDs
        contributing_agents = self._extract_agent_ids(results)
        
        # Aggregate metrics
        aggregated_metrics = self._aggregate_metrics(results)
        
        # Detect contradictions
        contradictions = self.detect_contradictions(results)
        
        # Find correlations
        correlations = self.find_correlations(results)
        
        # Score overall confidence
        overall_confidence = self.score_confidence(results, contradictions)
        
        # Generate summary
        summary = self._generate_summary(
            contributing_agents,
            aggregated_metrics,
            contradictions,
            correlations,
            overall_confidence
        )
        
        return SynthesisReport(
            contributing_agents=contributing_agents,
            aggregated_metrics=aggregated_metrics,
            contradictions=contradictions,
            correlations=correlations,
            overall_confidence=overall_confidence,
            summary=summary
        )
    
    def _extract_agent_ids(self, results: List[Dict[str, Any]]) -> List[str]:
        """Extract agent IDs from results."""
        agents = []
        for result in results:
            agent_id = result.get("agent_id") or result.get("source_agent")
            if agent_id:
                agents.append(str(agent_id))
        return agents
    
    def _aggregate_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract and aggregate key metrics from agent results.
        
        Combines numeric metrics with weighted averages,
        collects categorical metrics with frequency counts.
        """
        metrics: Dict[str, List[Any]] = {}
        
        for result in results:
            # Look for metrics in standard locations
            data = result.get("data", {})
            if isinstance(data, dict):
                for key, value in data.items():
                    if key not in metrics:
                        metrics[key] = []
                    metrics[key].append(value)
            
            # Also check top-level keys
            for key, value in result.items():
                if key in ("agent_id", "source_agent", "timestamp", "data"):
                    continue
                if key not in metrics:
                    metrics[key] = []
                metrics[key].append(value)
        
        # Aggregate each metric
        aggregated: Dict[str, Any] = {}
        for key, values in metrics.items():
            if all(isinstance(v, (int, float)) for v in values if v is not None):
                # Numeric: compute weighted average
                numeric_values = [v for v in values if isinstance(v, (int, float))]
                if numeric_values:
                    aggregated[key] = {
                        "mean": sum(numeric_values) / len(numeric_values),
                        "min": min(numeric_values),
                        "max": max(numeric_values),
                        "count": len(numeric_values)
                    }
            elif all(isinstance(v, str) for v in values if v is not None):
                # Categorical: compute frequency
                freq: Dict[str, int] = {}
                for v in values:
                    if v:
                        freq[v] = freq.get(v, 0) + 1
                aggregated[key] = {
                    "values": list(freq.keys()),
                    "frequency": freq,
                    "most_common": max(freq, key=freq.get) if freq else None
                }
            else:
                # Mixed or complex: just list them
                aggregated[key] = {"values": values, "count": len(values)}
        
        return aggregated
    
    def detect_contradictions(self, results: List[Dict[str, Any]]) -> List[Contradiction]:
        """
        Detect contradictions between agent outputs.
        
        Flags when two agents disagree on key conclusions.
        Examples:
        - BUE says low risk, URPE says high risk
        - One agent recommends approval, another recommends rejection
        
        Args:
            results: List of agent results to compare
            
        Returns:
            List of detected contradictions
        """
        contradictions: List[Contradiction] = []
        
        if len(results) < 2:
            return contradictions
        
        # Extract key claims from each result
        claims_by_domain: Dict[str, List[Tuple[str, str, float]]] = {}
        
        for result in results:
            agent_id = result.get("agent_id", "unknown")
            data = result.get("data", {})
            
            # Look for risk assessments
            risk_level = data.get("risk_level") or data.get("risk") or result.get("risk_level")
            if risk_level:
                domain = data.get("domain", "risk")
                if domain not in claims_by_domain:
                    claims_by_domain[domain] = []
                confidence = result.get("confidence", 0.5)
                claims_by_domain[domain].append((agent_id, str(risk_level), confidence))
            
            # Look for recommendations
            recommendation = data.get("recommendation") or result.get("recommendation")
            if recommendation:
                domain = data.get("domain", "recommendation")
                if domain not in claims_by_domain:
                    claims_by_domain[domain] = []
                confidence = result.get("confidence", 0.5)
                claims_by_domain[domain].append((agent_id, str(recommendation), confidence))
            
            # Look for conclusions
            conclusion = data.get("conclusion") or result.get("conclusion")
            if conclusion:
                domain = data.get("domain", "conclusion")
                if domain not in claims_by_domain:
                    claims_by_domain[domain] = []
                confidence = result.get("confidence", 0.5)
                claims_by_domain[domain].append((agent_id, str(conclusion), confidence))
        
        # Check for contradictions within each domain
        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        
        for domain, claims in claims_by_domain.items():
            if len(claims) < 2:
                continue
            
            for i, (agent_a, claim_a, conf_a) in enumerate(claims):
                for agent_b, claim_b, conf_b in claims[i+1:]:
                    if self._is_contradiction(claim_a, claim_b, risk_order):
                        severity = self._contradiction_severity(claim_a, claim_b, risk_order)
                        contradictions.append(Contradiction(
                            agent_a=agent_a,
                            agent_b=agent_b,
                            claim_a=claim_a,
                            claim_b=claim_b,
                            domain=domain,
                            severity=severity,
                            confidence=min(conf_a, conf_b)
                        ))
        
        return contradictions
    
    def _is_contradiction(
        self,
        claim_a: str,
        claim_b: str,
        risk_order: Dict[str, int]
    ) -> bool:
        """Check if two claims contradict each other."""
        # Normalize claims
        a_lower = claim_a.lower()
        b_lower = claim_b.lower()
        
        # Exact match = no contradiction
        if a_lower == b_lower:
            return False
        
        # Check for risk level contradictions
        if a_lower in risk_order and b_lower in risk_order:
            diff = abs(risk_order.get(a_lower, 1) - risk_order.get(b_lower, 1))
            return diff >= 2  # Low vs High or Medium vs Critical
        
        # Check for recommendation contradictions
        approve_terms = {"approve", "approved", "accept", "go", "proceed", "yes"}
        reject_terms = {"reject", "rejected", "deny", "no-go", "stop", "no"}
        
        a_approve = any(term in a_lower for term in approve_terms)
        a_reject = any(term in a_lower for term in reject_terms)
        b_approve = any(term in b_lower for term in approve_terms)
        b_reject = any(term in b_lower for term in reject_terms)
        
        if (a_approve and b_reject) or (a_reject and b_approve):
            return True
        
        return False
    
    def _contradiction_severity(
        self,
        claim_a: str,
        claim_b: str,
        risk_order: Dict[str, int]
    ) -> str:
        """Determine severity of a contradiction."""
        a_lower = claim_a.lower()
        b_lower = claim_b.lower()
        
        # Check risk level gap
        if a_lower in risk_order and b_lower in risk_order:
            diff = abs(risk_order.get(a_lower, 1) - risk_order.get(b_lower, 1))
            if diff >= 3:
                return "high"
            elif diff >= 2:
                return "medium"
            else:
                return "low"
        
        # Default to medium for non-risk contradictions
        return "medium"
    
    def find_correlations(self, results: List[Dict[str, Any]]) -> List[Correlation]:
        """
        Find statistical correlations across agent outputs.
        
        Args:
            results: List of agent results to analyze
            
        Returns:
            List of detected correlations
        """
        correlations: List[Correlation] = []
        
        if len(results) < 2:
            return correlations
        
        # Extract numeric metrics across all results
        metrics_by_agent: Dict[str, Dict[str, float]] = {}
        
        for result in results:
            agent_id = result.get("agent_id", "unknown")
            data = result.get("data", {})
            
            metrics: Dict[str, float] = {}
            
            # Look for numeric values
            for key, value in data.items() if isinstance(data, dict) else []:
                if isinstance(value, (int, float)):
                    metrics[key] = float(value)
            
            # Also check top-level
            for key, value in result.items():
                if key in ("agent_id", "source_agent", "timestamp", "data", "confidence"):
                    continue
                if isinstance(value, (int, float)):
                    metrics[key] = float(value)
            
            if metrics:
                metrics_by_agent[agent_id] = metrics
        
        # Find correlations between metrics
        all_metric_names = set()
        for metrics in metrics_by_agent.values():
            all_metric_names.update(metrics.keys())
        
        # Simple correlation detection: look for metrics that appear together
        for metric_name in all_metric_names:
            agents_with_metric = [
                agent for agent, metrics in metrics_by_agent.items()
                if metric_name in metrics
            ]
            
            if len(agents_with_metric) >= 2:
                # Compute simple correlation based on co-occurrence
                values = [metrics_by_agent[a][metric_name] for a in agents_with_metric]
                strength = self._compute_correlation_strength(values)
                
                if strength >= 0.5:
                    correlations.append(Correlation(
                        agents=agents_with_metric,
                        description=f"Metric '{metric_name}' shows consistent patterns across agents",
                        strength=strength,
                        correlation_type="positive",
                        domains=[metric_name]
                    ))
        
        return correlations
    
    def _compute_correlation_strength(self, values: List[float]) -> float:
        """
        Compute correlation strength for a set of values.
        
        Returns a value between 0.0 and 1.0 indicating how correlated the values are.
        """
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        
        if variance == 0:
            return 1.0  # Perfect correlation (all same value)
        
        # Coefficient of variation inverse as correlation proxy
        std_dev = variance ** 0.5
        cv = std_dev / abs(mean) if mean != 0 else float('inf')
        
        # Convert to 0-1 scale (lower CV = higher correlation)
        strength = 1.0 / (1.0 + cv)
        return min(1.0, max(0.0, strength))
    
    def score_confidence(
        self,
        results: List[Dict[str, Any]],
        contradictions: List[Contradiction]
    ) -> float:
        """
        Score overall confidence based on agent reliability and data freshness.
        
        Args:
            results: List of agent results
            contradictions: Detected contradictions (reduce confidence)
            
        Returns:
            Confidence score from 0.0 to 1.0
        """
        if not results:
            return 0.0
        
        # Base confidence from individual result confidences
        confidences = []
        for result in results:
            agent_id = result.get("agent_id", "unknown")
            result_confidence = result.get("confidence", 0.5)
            
            # Weight by agent reliability if known
            reliability = self._agent_reliability.get(agent_id, 0.7)
            weighted_confidence = (result_confidence + reliability) / 2
            confidences.append(weighted_confidence)
        
        base_confidence = sum(confidences) / len(confidences)
        
        # Penalize for contradictions
        contradiction_penalty = 0.0
        for contradiction in contradictions:
            if contradiction.severity == "high":
                contradiction_penalty += 0.15
            elif contradiction.severity == "medium":
                contradiction_penalty += 0.10
            else:
                contradiction_penalty += 0.05
        
        # Penalize for age of data
        freshness_penalty = self._compute_freshness_penalty(results)
        
        final_confidence = base_confidence - contradiction_penalty - freshness_penalty
        return max(0.0, min(1.0, final_confidence))
    
    def _compute_freshness_penalty(self, results: List[Dict[str, Any]]) -> float:
        """Compute penalty based on age of results."""
        now = datetime.now(timezone.utc)
        max_age_hours = 24.0
        penalty = 0.0
        
        for result in results:
            timestamp = result.get("timestamp")
            if timestamp:
                try:
                    if isinstance(timestamp, datetime):
                        ts = timestamp
                    elif isinstance(timestamp, str):
                        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    else:
                        continue
                    
                    age_hours = (now - ts).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        penalty += 0.05 * min(1.0, (age_hours - max_age_hours) / 24)
                except (ValueError, TypeError):
                    pass
        
        return min(0.2, penalty / max(1, len(results)))
    
    def _generate_summary(
        self,
        agents: List[str],
        metrics: Dict[str, Any],
        contradictions: List[Contradiction],
        correlations: List[Correlation],
        confidence: float
    ) -> str:
        """Generate human-readable summary of the synthesis."""
        parts = []
        
        # Agent summary
        if agents:
            parts.append(f"Synthesis based on {len(agents)} agent(s): {', '.join(agents)}.")
        
        # Contradiction warning
        if contradictions:
            high_sev = [c for c in contradictions if c.severity == "high"]
            if high_sev:
                parts.append(
                    f"WARNING: {len(high_sev)} high-severity contradiction(s) detected "
                    "between agents."
                )
            else:
                parts.append(
                    f"Note: {len(contradictions)} contradiction(s) detected between agents."
                )
        
        # Correlations
        if correlations:
            strong = [c for c in correlations if c.strength >= 0.7]
            if strong:
                parts.append(
                    f"{len(strong)} strong cross-domain correlation(s) identified."
                )
        
        # Confidence
        if confidence >= 0.8:
            parts.append("High confidence in synthesis.")
        elif confidence >= 0.6:
            parts.append("Moderate confidence in synthesis.")
        else:
            parts.append("Low confidence — review contradictions and data quality.")
        
        return " ".join(parts)
