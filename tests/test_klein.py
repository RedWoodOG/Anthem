"""
Tests for Klein route scoring engine.

Validates:
- Imports resolve correctly
- Scoring produces different results when weights change
- Multi-factor scoring is traceable
"""

import pytest
from klein.engine import KleinEngine, RouteCandidate, DEFAULT_WEIGHTS


@pytest.fixture
def sample_candidates():
    """Sample route candidates for testing."""
    return [
        RouteCandidate(
            route_id="route-a",
            latency_ms=50,
            cost_usd=10.0,
            carbon_gco2=100.0,
            reliability_score=0.95,
        ),
        RouteCandidate(
            route_id="route-b",
            latency_ms=100,
            cost_usd=5.0,
            carbon_gco2=200.0,
            reliability_score=0.80,
        ),
        RouteCandidate(
            route_id="route-c",
            latency_ms=75,
            cost_usd=7.5,
            carbon_gco2=150.0,
            reliability_score=None,  # Missing reliability data
        ),
    ]


class TestEngineInitialization:
    """Test engine initialization and weight validation."""

    def test_default_weights(self):
        """Engine initializes with equal default weights."""
        engine = KleinEngine()
        assert engine.weights == DEFAULT_WEIGHTS

    def test_custom_weights(self):
        """Engine accepts custom weights that sum to 1.0."""
        custom = {"latency": 0.5, "cost": 0.3, "carbon": 0.1, "reliability": 0.1}
        engine = KleinEngine(weights=custom)
        assert engine.weights == custom

    def test_weights_must_sum_to_one(self):
        """Engine rejects weights that don't sum to 1.0."""
        invalid = {"latency": 0.5, "cost": 0.3, "carbon": 0.1, "reliability": 0.0}
        with pytest.raises(ValueError, match="sum to 1.0"):
            KleinEngine(weights=invalid)

    def test_weights_must_have_all_keys(self):
        """Engine rejects weights missing required keys."""
        invalid = {"latency": 0.5, "cost": 0.5}
        with pytest.raises(ValueError, match="Missing required"):
            KleinEngine(weights=invalid)


class TestScoring:
    """Test multi-factor scoring."""

    def test_score_all_candidates(self, sample_candidates):
        """Scoring returns scored routes for all candidates."""
        engine = KleinEngine()
        scored = engine.score(sample_candidates)
        assert len(scored) == len(sample_candidates)
        assert all(s.total_score >= 0.0 for s in scored)
        assert all(s.total_score <= 1.0 for s in scored)

    def test_score_breakdown_traceable(self, sample_candidates):
        """Score breakdown is traceable to inputs."""
        engine = KleinEngine()
        scored = engine.score(sample_candidates)

        for s in scored:
            assert "latency" in s.score_breakdown
            assert "cost" in s.score_breakdown
            assert "carbon" in s.score_breakdown
            assert "reliability" in s.score_breakdown

            # Breakdown components sum to total
            total_from_breakdown = sum(s.score_breakdown.values())
            assert abs(total_from_breakdown - s.total_score) < 0.001

    def test_missing_reliability_penalized(self, sample_candidates):
        """Routes with missing reliability data are penalized."""
        engine = KleinEngine()
        scored = engine.score(sample_candidates)

        route_c = next(s for s in scored if s.route_id == "route-c")
        assert route_c.reliability_score == 0.5  # Penalized score

    def test_weights_change_affects_scoring(self, sample_candidates):
        """Scoring produces different results when weights change."""
        latency_focused = {"latency": 0.7, "cost": 0.1, "carbon": 0.1, "reliability": 0.1}
        cost_focused = {"latency": 0.1, "cost": 0.7, "carbon": 0.1, "reliability": 0.1}

        engine_latency = KleinEngine(weights=latency_focused)
        engine_cost = KleinEngine(weights=cost_focused)

        scored_latency = engine_latency.score(sample_candidates)
        scored_cost = engine_cost.score(sample_candidates)

        # Get rankings for each
        ranked_latency = engine_latency.rank(scored_latency)
        ranked_cost = engine_cost.rank(scored_cost)

        # Top route should differ (route-a has best latency, route-b has best cost)
        assert ranked_latency[0].route_id == "route-a"  # Lowest latency wins
        assert ranked_cost[0].route_id == "route-b"  # Lowest cost wins

    def test_empty_candidates(self):
        """Scoring empty list returns empty list."""
        engine = KleinEngine()
        scored = engine.score([])
        assert scored == []

    def test_max_candidates_limit(self):
        """Scoring truncates to 50 candidates max."""
        engine = KleinEngine()
        many_candidates = [
            RouteCandidate(
                route_id=f"route-{i}",
                latency_ms=50 + i,
                cost_usd=10.0,
                carbon_gco2=100.0,
            )
            for i in range(100)
        ]
        scored = engine.score(many_candidates)
        assert len(scored) == 50


class TestRanking:
    """Test candidate ranking."""

    def test_rank_sorts_by_score(self, sample_candidates):
        """Ranking sorts candidates by total score descending."""
        engine = KleinEngine()
        scored = engine.score(sample_candidates)
        ranked = engine.rank(scored, top_n=10)

        for i in range(len(ranked) - 1):
            assert ranked[i].total_score >= ranked[i + 1].total_score

    def test_rank_limits_to_top_n(self, sample_candidates):
        """Ranking returns at most top_n candidates."""
        engine = KleinEngine()
        scored = engine.score(sample_candidates)
        ranked = engine.rank(scored, top_n=2)
        assert len(ranked) == 2


class TestRecommendation:
    """Test route recommendation."""

    def test_recommend_returns_top_choice(self, sample_candidates):
        """Recommendation returns top scored route."""
        engine = KleinEngine()
        rec = engine.recommend(sample_candidates)

        assert rec.route_id is not None
        assert rec.explanation
        assert rec.score_breakdown

    def test_recommend_includes_alternatives(self, sample_candidates):
        """Recommendation includes alternative routes."""
        engine = KleinEngine()
        rec = engine.recommend(sample_candidates)

        assert len(rec.alternatives) == 2  # 2 alternatives for 3 candidates

    def test_workload_type_affects_recommendation(self, sample_candidates):
        """Workload type affects which route is recommended."""
        engine = KleinEngine()

        rec_realtime = engine.recommend(sample_candidates, workload_type="realtime")
        rec_bulk = engine.recommend(sample_candidates, workload_type="bulk")

        # Explanations should reflect workload type
        assert "low-latency" in rec_realtime.explanation
        assert "carbon" in rec_bulk.explanation

    def test_recommend_empty_fails(self):
        """Recommendation with no candidates raises error."""
        engine = KleinEngine()
        with pytest.raises(ValueError, match="No candidates"):
            engine.recommend([])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
