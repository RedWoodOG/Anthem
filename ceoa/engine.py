"""
CEOA Engine — Compute Energy Orchestration

Schedules compute workloads with carbon-awareness across cloud regions.
Uses real regional carbon intensity averages as fallback data.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class WorkloadType(Enum):
    """Workload types affecting scheduling priorities."""
    BATCH = "batch"
    INTERACTIVE = "interactive"
    LATENCY_SENSITIVE = "latency-sensitive"
    FLEXIBLE = "flexible"


class OptimizationGoal(Enum):
    """Optimization goals for placement."""
    MIN_CARBON = "min-carbon"
    MIN_COST = "min-cost"
    BALANCED = "balanced"
    LATENCY_PRIORITY = "latency-priority"


@dataclass
class RegionData:
    """Carbon and cost data for a cloud region."""
    region_id: str
    region_name: str
    carbon_intensity: float  # gCO2/kWh
    cost_per_hour: float  # USD per compute unit
    renewable_percentage: float  # 0-100
    latency_weight: float = 1.0  # Multiplier for latency-sensitive workloads


@dataclass
class Workload:
    """A compute workload to be scheduled."""
    workload_id: str
    workload_type: WorkloadType
    cpu_cores: int = 4
    memory_gb: float = 16.0
    gpu_required: bool = False
    max_cost_per_hour: Optional[float] = None
    priority: int = 1


@dataclass
class PlacementResult:
    """Result of a placement decision."""
    workload_id: str
    region_id: str
    region_name: str
    carbon_intensity: float
    cost_per_hour: float
    score: float
    explanation: str


@dataclass
class OptimizationResult:
    """Result of multi-workload optimization."""
    placements: List[PlacementResult]
    total_carbon_score: float
    total_cost: float
    explanation: str


# Regional carbon intensity data (gCO2/kWh) based on real grid averages
# Sources: IEA, ElectricityMap, EPA eGRID, European Environment Agency
# Values are annual averages; real-time API should be preferred when available
REGION_CARBON_DATA: Dict[str, RegionData] = {
    # US Regions
    "us-east-1": RegionData(
        region_id="us-east-1",
        region_name="US East (N. Virginia)",
        carbon_intensity=380.0,  # PJM Interconnection grid average
        cost_per_hour=0.096,
        renewable_percentage=18.0,
    ),
    "us-west-2": RegionData(
        region_id="us-west-2",
        region_name="US West (Oregon)",
        carbon_intensity=285.0,  # Pacific Northwest mix (hydro + some fossil)
        cost_per_hour=0.088,
        renewable_percentage=35.0,
    ),
    # European Regions
    "eu-west-1": RegionData(
        region_id="eu-west-1",
        region_name="EU West (Ireland)",
        carbon_intensity=320.0,  # Irish grid with growing wind
        cost_per_hour=0.102,
        renewable_percentage=38.0,
    ),
    "eu-central-1": RegionData(
        region_id="eu-central-1",
        region_name="EU Central (Frankfurt)",
        carbon_intensity=380.0,  # German grid (post-nuclear, coal phase-out)
        cost_per_hour=0.108,
        renewable_percentage=45.0,
    ),
    # Asia-Pacific Regions
    "ap-southeast-1": RegionData(
        region_id="ap-southeast-1",
        region_name="Asia Pacific (Singapore)",
        carbon_intensity=490.0,  # Natural gas dominated grid
        cost_per_hour=0.112,
        renewable_percentage=5.0,
    ),
    # Additional major regions for broader coverage
    "us-east-2": RegionData(
        region_id="us-east-2",
        region_name="US East (Ohio)",
        carbon_intensity=420.0,  # Ohio Valley coal/gas mix
        cost_per_hour=0.092,
        renewable_percentage=12.0,
    ),
    "eu-north-1": RegionData(
        region_id="eu-north-1",
        region_name="EU North (Stockholm)",
        carbon_intensity=28.0,  # Nordic hydro + nuclear
        cost_per_hour=0.095,
        renewable_percentage=98.0,
    ),
    "ap-northeast-1": RegionData(
        region_id="ap-northeast-1",
        region_name="Asia Pacific (Tokyo)",
        carbon_intensity=480.0,  # Japanese grid (post-Fukushima fossil reliance)
        cost_per_hour=0.128,
        renewable_percentage=20.0,
    ),
}


class CEOAEngine:
    """
    Compute Energy Orchestration API Engine.
    
    Schedules compute workloads to cloud regions based on carbon intensity,
    cost, and workload requirements.
    """

    def __init__(self, region_data: Optional[Dict[str, RegionData]] = None):
        """
        Initialize the CEOA engine.
        
        Args:
            region_data: Optional custom region data. Defaults to built-in data.
        """
        self.region_data = region_data or REGION_CARBON_DATA.copy()
        self._carbon_cache_timestamp: Optional[float] = None
        logger.info(f"CEOA Engine initialized with {len(self.region_data)} regions")

    def carbon_score(self, region_id: str) -> float:
        """
        Calculate carbon score for a region (0-1, lower is better).
        
        Score is normalized based on the range of carbon intensities
        across all known regions.
        
        Args:
            region_id: The cloud region identifier
            
        Returns:
            Score from 0 (best) to 1 (worst)
        """
        if region_id not in self.region_data:
            logger.warning(f"Unknown region: {region_id}, returning worst-case score")
            return 1.0
        
        region = self.region_data[region_id]
        
        # Get min/max for normalization
        intensities = [r.carbon_intensity for r in self.region_data.values()]
        min_intensity = min(intensities)
        max_intensity = max(intensities)
        
        # Normalize to 0-1 range (0 = best/lowest carbon)
        if max_intensity == min_intensity:
            return 0.5
        
        score = (region.carbon_intensity - min_intensity) / (max_intensity - min_intensity)
        return max(0.0, min(1.0, score))

    def cost_score(self, region_id: str) -> float:
        """
        Calculate cost score for a region (0-1, lower is better).
        
        Args:
            region_id: The cloud region identifier
            
        Returns:
            Score from 0 (cheapest) to 1 (most expensive)
        """
        if region_id not in self.region_data:
            return 1.0
        
        region = self.region_data[region_id]
        
        # Get min/max for normalization
        costs = [r.cost_per_hour for r in self.region_data.values()]
        min_cost = min(costs)
        max_cost = max(costs)
        
        if max_cost == min_cost:
            return 0.5
        
        score = (region.cost_per_hour - min_cost) / (max_cost - min_cost)
        return max(0.0, min(1.0, score))

    def _calculate_placement_score(
        self,
        region_id: str,
        workload: Workload,
        goal: OptimizationGoal = OptimizationGoal.BALANCED
    ) -> float:
        """
        Calculate overall placement score for a region given a workload.
        
        Lower scores are better.
        
        Args:
            region_id: The cloud region
            workload: The workload to place
            goal: Optimization goal
            
        Returns:
            Placement score (lower is better)
        """
        if region_id not in self.region_data:
            return float('inf')
        
        region = self.region_data[region_id]
        carbon = self.carbon_score(region_id)
        cost = self.cost_score(region_id)
        
        # Apply workload type adjustments
        if workload.workload_type == WorkloadType.LATENCY_SENSITIVE:
            # Latency-sensitive workloads penalize distant regions
            # (simplified: US workloads prefer US regions)
            latency_penalty = 0.0 if region_id.startswith("us-") else 0.3
        elif workload.workload_type == WorkloadType.BATCH:
            # Batch workloads can follow renewables more aggressively
            carbon_weight = 0.8
            cost_weight = 0.2
            if goal == OptimizationGoal.BALANCED:
                return (carbon * carbon_weight + cost * cost_weight) * (1.0 - region.renewable_percentage / 100.0)
        elif workload.workload_type == WorkloadType.FLEXIBLE:
            # Flexible workloads optimize purely for carbon
            return carbon * 0.9 + cost * 0.1
        
        # Default balanced scoring
        if goal == OptimizationGoal.MIN_CARBON:
            return carbon
        elif goal == OptimizationGoal.MIN_COST:
            return cost
        elif goal == OptimizationGoal.LATENCY_PRIORITY:
            # Heavily weight latency (simplified heuristic)
            return cost * 0.3 + carbon * 0.3 + (0.4 if not region_id.startswith("us-") else 0.0)
        else:  # BALANCED
            return carbon * 0.5 + cost * 0.5

    def schedule(
        self,
        workload: Workload,
        candidate_regions: Optional[List[str]] = None,
        goal: OptimizationGoal = OptimizationGoal.BALANCED
    ) -> PlacementResult:
        """
        Schedule a workload to the best region.
        
        Args:
            workload: The workload to schedule
            candidate_regions: Optional list of candidate regions (defaults to all)
            goal: Optimization goal
            
        Returns:
            Placement result with selected region and explanation
        """
        # Filter to candidate regions
        regions = candidate_regions or list(self.region_data.keys())
        
        # Enforce minimum 3 regions constraint
        if len(regions) < 3:
            # Add more regions from available pool
            available = [r for r in self.region_data.keys() if r not in regions]
            regions.extend(available[:3 - len(regions)])
            logger.info(f"Expanded candidate regions to {len(regions)} to meet minimum constraint")
        
        # Validate cost constraint
        if workload.max_cost_per_hour is not None:
            regions = [
                r for r in regions
                if self.region_data[r].cost_per_hour <= workload.max_cost_per_hour
            ]
            if not regions:
                raise ValueError(
                    f"No regions available within cost constraint ${workload.max_cost_per_hour}/hr"
                )
        
        # Score all candidate regions
        scored_regions = []
        for region_id in regions:
            score = self._calculate_placement_score(region_id, workload, goal)
            scored_regions.append((region_id, score))
        
        # Sort by score (lower is better)
        scored_regions.sort(key=lambda x: x[1])
        
        if not scored_regions:
            raise ValueError("No valid regions for placement")
        
        best_region_id, best_score = scored_regions[0]
        best_region = self.region_data[best_region_id]
        
        # Generate explanation
        explanation = (
            f"Selected {best_region.region_name} ({best_region_id}) "
            f"with carbon intensity {best_region.carbon_intensity:.0f} gCO2/kWh "
            f"and cost ${best_region.cost_per_hour:.3f}/hr. "
            f"Placement score: {best_score:.3f}. "
            f"Region has {best_region.renewable_percentage:.0f}% renewable energy."
        )
        
        return PlacementResult(
            workload_id=workload.workload_id,
            region_id=best_region_id,
            region_name=best_region.region_name,
            carbon_intensity=best_region.carbon_intensity,
            cost_per_hour=best_region.cost_per_hour,
            score=best_score,
            explanation=explanation
        )

    def optimize(
        self,
        workloads: List[Workload],
        goal: OptimizationGoal = OptimizationGoal.BALANCED,
        max_regions: Optional[int] = None
    ) -> OptimizationResult:
        """
        Optimize placement of multiple workloads across regions.
        
        Distributes workloads to minimize aggregate carbon/cost while
        respecting constraints.
        
        Args:
            workloads: List of workloads to place
            goal: Optimization goal
            max_regions: Optional limit on number of regions used
            
        Returns:
            Optimization result with all placements
        """
        if not workloads:
            return OptimizationResult(
                placements=[],
                total_carbon_score=0.0,
                total_cost=0.0,
                explanation="No workloads to optimize"
            )
        
        # Sort workloads by priority (higher priority first)
        sorted_workloads = sorted(workloads, key=lambda w: -w.priority)
        
        placements: List[PlacementResult] = []
        used_regions: set = set()
        total_carbon = 0.0
        total_cost = 0.0
        
        for workload in sorted_workloads:
            # Determine candidate regions
            candidates = list(self.region_data.keys())
            
            # Apply max_regions constraint
            if max_regions is not None and len(used_regions) >= max_regions:
                # Must use existing regions
                candidates = list(used_regions)
            
            placement = self.schedule(workload, candidates, goal)
            placements.append(placement)
            used_regions.add(placement.region_id)
            total_carbon += placement.carbon_intensity
            total_cost += placement.cost_per_hour
        
        # Generate aggregate explanation
        unique_regions = len(set(p.region_id for p in placements))
        avg_carbon = total_carbon / len(placements) if placements else 0.0
        
        explanation = (
            f"Optimized {len(workloads)} workloads across {unique_regions} regions. "
            f"Average carbon intensity: {avg_carbon:.0f} gCO2/kWh. "
            f"Total hourly cost: ${total_cost:.3f}. "
            f"Optimization goal: {goal.value}."
        )
        
        return OptimizationResult(
            placements=placements,
            total_carbon_score=total_carbon,
            total_cost=total_cost,
            explanation=explanation
        )

    def get_carbon_intensity(
        self,
        regions: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get carbon intensity data for regions.
        
        Args:
            regions: Optional list of regions (defaults to all)
            
        Returns:
            Dictionary of region data
        """
        region_ids = regions or list(self.region_data.keys())
        
        result = {}
        for region_id in region_ids:
            if region_id in self.region_data:
                r = self.region_data[region_id]
                result[region_id] = {
                    "region_name": r.region_name,
                    "carbon_intensity": r.carbon_intensity,
                    "cost_per_hour": r.cost_per_hour,
                    "renewable_percentage": r.renewable_percentage,
                    "carbon_score": self.carbon_score(region_id),
                }
        
        return result
