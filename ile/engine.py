"""
ILE Engine — Internal Learning Engine.

Tracks feedback across agent invocations, computes drift metrics using
exponential moving averages, and generates actionable learning signals.
No hardcoded responses. All measurements data-driven.
"""

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEvent:
    """A single feedback event from an agent invocation."""
    agent_id: str
    task: str
    expected_outcome: Optional[Dict[str, Any]]
    actual_outcome: Optional[Dict[str, Any]]
    outcome: str  # "success", "partial", "failure"
    latency_ms: int
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task": self.task,
            "expected_outcome": self.expected_outcome,
            "actual_outcome": self.actual_outcome,
            "outcome": self.outcome,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DriftMetrics:
    """Computed drift metrics for an agent over a time window."""
    agent_id: str
    window_size: int
    samples_analyzed: int
    outcome_drift: float  # EMA-smoothed outcome deviation
    latency_drift: float  # EMA-smoothed latency deviation
    combined_drift: float  # Weighted combination
    z_score: float  # Standard deviations from baseline
    is_anomaly: bool
    trend: str  # "improving", "stable", "degrading"
    confidence: float  # 0-1 confidence in the measurement

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "window_size": self.window_size,
            "samples_analyzed": self.samples_analyzed,
            "outcome_drift": round(self.outcome_drift, 4),
            "latency_drift": round(self.latency_drift, 4),
            "combined_drift": round(self.combined_drift, 4),
            "z_score": round(self.z_score, 4),
            "is_anomaly": self.is_anomaly,
            "trend": self.trend,
            "confidence": round(self.confidence, 4),
        }


@dataclass
class LearningSignal:
    """A learning signal with actionable recommendations."""
    agent_id: str
    signal_type: str  # "parameter_adjustment", "retraining_needed", "governance_alert"
    recommendation: str
    confidence: float
    supporting_evidence: Dict[str, Any]
    requires_governance: bool
    generated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "signal_type": self.signal_type,
            "recommendation": self.recommendation,
            "confidence": round(self.confidence, 4),
            "supporting_evidence": self.supporting_evidence,
            "requires_governance": self.requires_governance,
            "generated_at": self.generated_at.isoformat(),
        }


class ILEEngine:
    """
    Internal Learning Engine that tracks agent performance and detects drift.

    Uses exponential moving average (EMA) for smoothing drift measurements.
    Requires minimum 20 samples before claiming trends.
    Flags anomalies when drift exceeds 2 standard deviations.
    """

    MIN_SAMPLES_FOR_TREND = 20
    ANOMALY_THRESHOLD_ZSCORE = 2.0
    EMA_ALPHA = 0.3  # Smoothing factor for EMA (higher = more weight on recent)

    def __init__(self) -> None:
        # Storage: agent_id -> list of feedback events
        self._feedback: Dict[str, List[FeedbackEvent]] = {}
        # Baseline metrics per agent (computed from initial window)
        self._baselines: Dict[str, Dict[str, float]] = {}
        # EMA state per agent
        self._ema_state: Dict[str, Dict[str, float]] = {}
        logger.info("ILEEngine initialized")

    def record_feedback(
        self,
        agent_id: str,
        task: str,
        expected_outcome: Optional[Dict[str, Any]],
        actual_outcome: Optional[Dict[str, Any]],
        outcome: str,
        latency_ms: int,
        timestamp: Optional[datetime] = None,
    ) -> FeedbackEvent:
        """
        Store a feedback event with agent_id, task, expected vs actual outcome.

        Args:
            agent_id: The agent that produced this feedback
            task: The task or capability being evaluated
            expected_outcome: The expected result structure
            actual_outcome: The actual result produced
            outcome: High-level outcome classification (success/partial/failure)
            latency_ms: Execution latency in milliseconds
            timestamp: Event timestamp (defaults to now)

        Returns:
            The stored FeedbackEvent
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        event = FeedbackEvent(
            agent_id=agent_id,
            task=task,
            expected_outcome=expected_outcome,
            actual_outcome=actual_outcome,
            outcome=outcome,
            latency_ms=latency_ms,
            timestamp=timestamp,
        )

        if agent_id not in self._feedback:
            self._feedback[agent_id] = []
            self._ema_state[agent_id] = {}

        self._feedback[agent_id].append(event)
        logger.debug(
            "Recorded feedback for %s: task=%s, outcome=%s, latency=%dms",
            agent_id, task, outcome, latency_ms
        )

        # Update baseline if this is early data
        self._update_baseline_if_needed(agent_id)

        return event

    def _update_baseline_if_needed(self, agent_id: str) -> None:
        """Establish baseline metrics from the first MIN_SAMPLES_FOR_TREND samples."""
        if agent_id in self._baselines:
            return

        events = self._feedback.get(agent_id, [])
        if len(events) < self.MIN_SAMPLES_FOR_TREND:
            return

        # Compute baseline from initial window
        outcome_scores = [self._outcome_to_score(e.outcome) for e in events]
        latencies = [e.latency_ms for e in events]

        self._baselines[agent_id] = {
            "outcome_mean": statistics.mean(outcome_scores),
            "outcome_stdev": statistics.stdev(outcome_scores) if len(outcome_scores) > 1 else 1.0,
            "latency_mean": statistics.mean(latencies),
            "latency_stdev": statistics.stdev(latencies) if len(latencies) > 1 else 1.0,
        }

        # Initialize EMA state at baseline
        self._ema_state[agent_id] = {
            "outcome_ema": self._baselines[agent_id]["outcome_mean"],
            "latency_ema": self._baselines[agent_id]["latency_mean"],
        }

        logger.info(
            "Established baseline for %s: outcome_mean=%.3f, latency_mean=%.1fms",
            agent_id,
            self._baselines[agent_id]["outcome_mean"],
            self._baselines[agent_id]["latency_mean"],
        )

    def _outcome_to_score(self, outcome: str) -> float:
        """Convert outcome string to numeric score for drift calculation."""
        mapping = {
            "success": 1.0,
            "partial": 0.5,
            "failure": 0.0,
        }
        return mapping.get(outcome, 0.5)

    def _compute_ema(self, agent_id: str, current_value: float, ema_key: str) -> float:
        """
        Compute exponential moving average for a metric.

        EMA = alpha * current + (1 - alpha) * previous_ema
        """
        if agent_id not in self._ema_state:
            self._ema_state[agent_id] = {}

        previous_ema = self._ema_state[agent_id].get(ema_key, current_value)
        new_ema = self.EMA_ALPHA * current_value + (1 - self.EMA_ALPHA) * previous_ema
        self._ema_state[agent_id][ema_key] = new_ema
        return new_ema

    def compute_drift(
        self,
        agent_id: str,
        window_size: int = 100,
        metric: str = "combined",
    ) -> DriftMetrics:
        """
        Calculate drift over last N invocations using EMA.

        Args:
            agent_id: The agent to analyze
            window_size: Number of recent samples to include
            metric: Which drift metric to compute (outcome_drift, latency_drift, combined)

        Returns:
            DriftMetrics with computed drift values
        """
        events = self._feedback.get(agent_id, [])
        actual_window = min(window_size, len(events))

        if actual_window == 0:
            return DriftMetrics(
                agent_id=agent_id,
                window_size=window_size,
                samples_analyzed=0,
                outcome_drift=0.0,
                latency_drift=0.0,
                combined_drift=0.0,
                z_score=0.0,
                is_anomaly=False,
                trend="unknown",
                confidence=0.0,
            )

        # Use most recent events
        recent_events = events[-actual_window:]

        # Compute current metrics
        outcome_scores = [self._outcome_to_score(e.outcome) for e in recent_events]
        latencies = [e.latency_ms for e in recent_events]

        current_outcome = statistics.mean(outcome_scores)
        current_latency = statistics.mean(latencies)

        # Update EMA with current values
        ema_outcome = self._compute_ema(agent_id, current_outcome, "outcome_ema")
        ema_latency = self._compute_ema(agent_id, current_latency, "latency_ema")

        # Get baseline for comparison
        baseline = self._baselines.get(agent_id, {})
        baseline_outcome = baseline.get("outcome_mean", ema_outcome)
        baseline_latency = baseline.get("latency_mean", ema_latency)
        baseline_outcome_stdev = baseline.get("outcome_stdev", 1.0)
        baseline_latency_stdev = baseline.get("latency_stdev", 1.0)

        # Compute drift as deviation from baseline
        outcome_drift = abs(ema_outcome - baseline_outcome)
        latency_drift = abs(ema_latency - baseline_latency) / max(baseline_latency, 1)  # Normalize

        # Combined drift: weighted average (outcome more important)
        combined_drift = 0.6 * outcome_drift + 0.4 * latency_drift

        # Compute z-score for anomaly detection
        z_score_outcome = (ema_outcome - baseline_outcome) / max(baseline_outcome_stdev, 0.001)
        z_score_latency = (ema_latency - baseline_latency) / max(baseline_latency_stdev, 0.001)
        z_score = math.sqrt(z_score_outcome ** 2 + z_score_latency ** 2) / math.sqrt(2)

        is_anomaly = abs(z_score) > self.ANOMALY_THRESHOLD_ZSCORE

        # Determine trend (requires minimum samples)
        if len(events) < self.MIN_SAMPLES_FOR_TREND:
            trend = "insufficient_data"
        elif ema_outcome > baseline_outcome * 1.05:
            trend = "improving"
        elif ema_outcome < baseline_outcome * 0.95:
            trend = "degrading"
        else:
            trend = "stable"

        # Confidence increases with sample count, capped at 1.0
        confidence = min(1.0, len(events) / (self.MIN_SAMPLES_FOR_TREND * 2))

        return DriftMetrics(
            agent_id=agent_id,
            window_size=window_size,
            samples_analyzed=actual_window,
            outcome_drift=outcome_drift,
            latency_drift=latency_drift,
            combined_drift=combined_drift,
            z_score=z_score,
            is_anomaly=is_anomaly,
            trend=trend,
            confidence=confidence,
        )

    def detect_anomaly(self, agent_id: str, window_size: int = 100) -> Tuple[bool, DriftMetrics]:
        """
        Flag when drift exceeds threshold (z-score > 2).

        Args:
            agent_id: The agent to check
            window_size: Number of recent samples to analyze

        Returns:
            Tuple of (is_anomaly, DriftMetrics)
        """
        metrics = self.compute_drift(agent_id, window_size, metric="combined")
        return (metrics.is_anomaly, metrics)

    def generate_signal(
        self,
        agent_id: str,
        confidence_threshold: float = 0.7,
    ) -> Optional[LearningSignal]:
        """
        Produce a learning signal with parameter adjustment recommendation.

        Args:
            agent_id: The agent to generate signal for
            confidence_threshold: Minimum confidence to emit signal

        Returns:
            LearningSignal if confidence exceeds threshold, None otherwise
        """
        metrics = self.compute_drift(agent_id, window_size=100)

        if metrics.confidence < confidence_threshold:
            logger.debug(
                "Skipping signal for %s: confidence %.2f < threshold %.2f",
                agent_id, metrics.confidence, confidence_threshold
            )
            return None

        # Determine signal type and recommendation based on drift pattern
        now = datetime.now(timezone.utc)

        if metrics.is_anomaly and metrics.trend == "degrading":
            # Severe case: governance alert
            return LearningSignal(
                agent_id=agent_id,
                signal_type="governance_alert",
                recommendation=f"Immediate review required for {agent_id}: sustained degradation detected",
                confidence=metrics.confidence,
                supporting_evidence={
                    "z_score": metrics.z_score,
                    "combined_drift": metrics.combined_drift,
                    "trend": metrics.trend,
                    "samples_analyzed": metrics.samples_analyzed,
                },
                requires_governance=True,
                generated_at=now,
            )

        elif metrics.trend == "degrading":
            # Moderate degradation: recommend retraining
            return LearningSignal(
                agent_id=agent_id,
                signal_type="retraining_needed",
                recommendation=f"Schedule retraining for {agent_id}: performance declining",
                confidence=metrics.confidence,
                supporting_evidence={
                    "outcome_drift": metrics.outcome_drift,
                    "latency_drift": metrics.latency_drift,
                    "trend": metrics.trend,
                },
                requires_governance=False,
                generated_at=now,
            )

        elif metrics.trend == "improving" and metrics.confidence > 0.8:
            # Positive signal: capture what's working
            return LearningSignal(
                agent_id=agent_id,
                signal_type="parameter_adjustment",
                recommendation=f"Document successful patterns for {agent_id}: performance improving",
                confidence=metrics.confidence,
                supporting_evidence={
                    "outcome_drift": metrics.outcome_drift,
                    "trend": metrics.trend,
                },
                requires_governance=False,
                generated_at=now,
            )

        # No significant signal to emit
        logger.debug("No significant learning signal for %s: trend=%s", agent_id, metrics.trend)
        return None

    def get_feedback_history(
        self,
        agent_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent feedback events for an agent."""
        events = self._feedback.get(agent_id, [])
        return [e.to_dict() for e in events[-limit:]]

    def clear_history(self, agent_id: Optional[str] = None) -> None:
        """Clear feedback history (for testing or reset)."""
        if agent_id:
            self._feedback.pop(agent_id, None)
            self._baselines.pop(agent_id, None)
            self._ema_state.pop(agent_id, None)
        else:
            self._feedback.clear()
            self._baselines.clear()
            self._ema_state.clear()
