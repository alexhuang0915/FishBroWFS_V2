"""
UI Action Registry SSOT (Single Source of Truth).

This module provides a comprehensive registry of all UI actions in the system,
mapping them to their corresponding API endpoints and UI components.

Key Concepts:
- UI Action: A user-initiated operation in the GUI (e.g., "submit job", "view gate summary")
- Action Pattern: The target string format used by ActionRouterService (e.g., "gate_summary", "job_admission://{job_id}")
- API Endpoint: The backend API endpoint that fulfills the action
- UI Component: The Qt widget or service that initiates the action

Governance Rules:
1. Every UI action must be registered here
2. Every UI action must map to at least one API endpoint (except internal navigation)
3. UI actions must be classified as UI_REQUIRED or UI_OPTIONAL
4. Action patterns must follow established conventions
"""

from enum import Enum
from typing import Dict, List, Optional, Set, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

from contracts.ui_api_coverage import ApiEndpointClassification, ApiEndpointMetadata


class UiActionType(str, Enum):
    """Type of UI action."""
    
    # Core job operations
    JOB_SUBMISSION = "job_submission"
    JOB_LISTING = "job_listing"
    JOB_DETAILS = "job_details"
    JOB_ABORT = "job_abort"
    JOB_EXPLAIN = "job_explain"
    
    # Registry operations (dropdown population)
    REGISTRY_DATASETS = "registry_datasets"
    REGISTRY_STRATEGIES = "registry_strategies"
    REGISTRY_INSTRUMENTS = "registry_instruments"
    REGISTRY_TIMEFRAMES = "registry_timeframes"
    
    # Data operations
    DATA_READINESS = "data_readiness"
    DATA_PREPARATION = "data_preparation"
    
    # Portfolio operations
    PORTFOLIO_BUILD = "portfolio_build"
    PORTFOLIO_ARTIFACTS = "portfolio_artifacts"
    PORTFOLIO_REPORT = "portfolio_report"
    
    # Gate operations
    GATE_SUMMARY = "gate_summary"
    GATE_DASHBOARD = "gate_dashboard"
    
    # Navigation operations (internal routing)
    NAVIGATE_JOB_ADMISSION = "navigate_job_admission"
    NAVIGATE_ARTIFACT = "navigate_artifact"
    NAVIGATE_EXPLAIN = "navigate_explain"
    NAVIGATE_GATE_DASHBOARD = "navigate_gate_dashboard"
    
    # System operations
    SYSTEM_HEALTH = "system_health"
    SYSTEM_PRIME_REGISTRIES = "system_prime_registries"
    
    # Batch operations
    BATCH_STATUS = "batch_status"
    BATCH_METADATA = "batch_metadata"
    
    # Season operations
    SEASON_MANAGEMENT = "season_management"
    SEASON_COMPARE = "season_compare"
    SEASON_EXPORT = "season_export"


class UiActionPattern(BaseModel):
    """Pattern definition for a UI action target."""
    
    pattern: str = Field(..., description="Action target pattern (e.g., 'gate_summary', 'job_admission://{job_id}')")
    description: str = Field(..., description="Human-readable description of the action")
    parameters: List[str] = Field(default_factory=list, description="Parameters in the pattern (e.g., ['job_id'])")
    example: Optional[str] = Field(None, description="Example target string")
    
    model_config = ConfigDict(frozen=True)


class UiActionMetadata(BaseModel):
    """Metadata for a UI action."""
    
    action_type: UiActionType = Field(..., description="Type of UI action")
    description: str = Field(..., description="Human-readable description")
    action_patterns: List[UiActionPattern] = Field(default_factory=list, description="Supported action patterns")
    api_endpoints: List[str] = Field(default_factory=list, description="API endpoint IDs that fulfill this action")
    ui_components: List[str] = Field(default_factory=list, description="UI components that initiate this action")
    classification: ApiEndpointClassification = Field(..., description="Classification (UI_REQUIRED/UI_OPTIONAL)")
    requires_auth: bool = Field(default=True, description="Whether action requires authentication")
    is_mutation: bool = Field(default=False, description="Whether action performs mutation (POST/PUT/PATCH/DELETE)")
    
    model_config = ConfigDict(frozen=True)


class UiActionRegistry(BaseModel):
    """Registry of all UI actions in the system."""
    
    # Core collections
    actions: Dict[UiActionType, UiActionMetadata] = Field(default_factory=dict, description="All registered UI actions")
    action_patterns: Dict[str, UiActionType] = Field(default_factory=dict, description="Mapping from pattern to action type")
    
    # Statistics
    statistics: Dict[str, int] = Field(default_factory=dict, description="Registry statistics")
    
    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="When registry was generated")
    version: str = Field(default="1.0.0", description="Registry version")
    
    model_config = ConfigDict(frozen=True)
    
    def __init__(self, **data):
        super().__init__(**data)
        # Build pattern mapping after initialization
        self._build_pattern_mapping()
    
    def _build_pattern_mapping(self) -> None:
        """Build mapping from action patterns to action types."""
        pattern_map = {}
        for action_type, metadata in self.actions.items():
            for pattern in metadata.action_patterns:
                pattern_map[pattern.pattern] = action_type
        # Use object.__setattr__ to bypass frozen model
        object.__setattr__(self, "action_patterns", pattern_map)
    
    def get_action_by_type(self, action_type: UiActionType) -> Optional[UiActionMetadata]:
        """Get action metadata by type."""
        return self.actions.get(action_type)
    
    def get_action_by_pattern(self, pattern: str) -> Optional[UiActionMetadata]:
        """Get action metadata by action pattern."""
        action_type = self.action_patterns.get(pattern)
        if action_type:
            return self.actions.get(action_type)
        return None
    
    def find_action_for_target(self, target: str) -> Optional[UiActionMetadata]:
        """
        Find action metadata for a given target string.
        
        Args:
            target: Action target string (e.g., "gate_summary", "job_admission://job123")
            
        Returns:
            Action metadata if target matches any pattern, None otherwise
        """
        # Exact match
        if target in self.action_patterns:
            return self.get_action_by_pattern(target)
        
        # Pattern matching for parameterized targets
        for action_type, metadata in self.actions.items():
            for action_pattern in metadata.action_patterns:
                pattern = action_pattern.pattern
                # Simple prefix matching for patterns with parameters
                if "{" in pattern:
                    # Extract base pattern (before parameter)
                    base_pattern = pattern.split("{")[0]
                    if target.startswith(base_pattern):
                        return metadata
                # Check if pattern is a prefix of target (for patterns like "explain://")
                elif target.startswith(pattern):
                    return metadata
        
        return None
    
    def get_actions_by_classification(self, classification: ApiEndpointClassification) -> List[UiActionMetadata]:
        """Get all actions with given classification."""
        return [
            metadata for metadata in self.actions.values()
            if metadata.classification == classification
        ]
    
    def get_actions_by_ui_component(self, ui_component: str) -> List[UiActionMetadata]:
        """Get all actions initiated by a specific UI component."""
        return [
            metadata for metadata in self.actions.values()
            if ui_component in metadata.ui_components
        ]
    
    def get_api_endpoints_for_action(self, action_type: UiActionType) -> List[str]:
        """Get all API endpoint IDs for a given action."""
        action = self.get_action_by_type(action_type)
        if action:
            return action.api_endpoints
        return []
    
    def validate_action_target(self, target: str) -> bool:
        """Validate if a target string matches any registered action pattern."""
        return self.find_action_for_target(target) is not None
    
    def get_statistics(self) -> Dict[str, int]:
        """Get registry statistics."""
        stats = {
            "total_actions": len(self.actions),
            "total_patterns": len(self.action_patterns),
            "ui_required": len(self.get_actions_by_classification(ApiEndpointClassification.UI_REQUIRED)),
            "ui_optional": len(self.get_actions_by_classification(ApiEndpointClassification.UI_OPTIONAL)),
            "mutation_actions": sum(1 for a in self.actions.values() if a.is_mutation),
            "readonly_actions": sum(1 for a in self.actions.values() if not a.is_mutation),
        }
        return stats


# -----------------------------------------------------------------------------
# Default UI Action Registry
# -----------------------------------------------------------------------------

def create_default_ui_action_registry() -> UiActionRegistry:
    """Create the default UI action registry with all known actions."""
    
    actions = {
        # Core job operations
        UiActionType.JOB_SUBMISSION: UiActionMetadata(
            action_type=UiActionType.JOB_SUBMISSION,
            description="Submit a new job (research/backtest/optimize/wfs)",
            action_patterns=[
                UiActionPattern(
                    pattern="job_submission",
                    description="Submit job via API",
                    parameters=[],
                    example="job_submission"
                )
            ],
            api_endpoints=["POST /api/v1/jobs"],
            ui_components=["OpTab", "OpTabV2", "OpTabLegacy"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=True
        ),
        
        UiActionType.JOB_LISTING: UiActionMetadata(
            action_type=UiActionType.JOB_LISTING,
            description="List all jobs for display in tables",
            action_patterns=[
                UiActionPattern(
                    pattern="job_listing",
                    description="List jobs via API",
                    parameters=[],
                    example="job_listing"
                )
            ],
            api_endpoints=["GET /api/v1/jobs"],
            ui_components=["OpTab", "AuditTab", "GateSummaryDashboardTab"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.JOB_DETAILS: UiActionMetadata(
            action_type=UiActionType.JOB_DETAILS,
            description="Get details for a specific job",
            action_patterns=[
                UiActionPattern(
                    pattern="job_details://{job_id}",
                    description="Get job details",
                    parameters=["job_id"],
                    example="job_details://job_abc123"
                )
            ],
            api_endpoints=["GET /api/v1/jobs/{job_id}"],
            ui_components=["ArtifactNavigator", "JobDetailsDialog"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.JOB_ABORT: UiActionMetadata(
            action_type=UiActionType.JOB_ABORT,
            description="Abort a running job",
            action_patterns=[
                UiActionPattern(
                    pattern="job_abort://{job_id}",
                    description="Abort job",
                    parameters=["job_id"],
                    example="job_abort://job_abc123"
                )
            ],
            api_endpoints=["POST /api/v1/jobs/{job_id}/abort"],
            ui_components=["OpTab", "ControlActionsGate"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=True
        ),
        
        UiActionType.JOB_EXPLAIN: UiActionMetadata(
            action_type=UiActionType.JOB_EXPLAIN,
            description="Get semantic explanation for job outcome",
            action_patterns=[
                UiActionPattern(
                    pattern="explain://{job_id}",
                    description="Get job explanation",
                    parameters=["job_id"],
                    example="explain://job_abc123"
                )
            ],
            api_endpoints=["GET /api/v1/jobs/{job_id}/explain"],
            ui_components=["ExplainHubWidget", "ArtifactNavigator"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        # Registry operations
        UiActionType.REGISTRY_DATASETS: UiActionMetadata(
            action_type=UiActionType.REGISTRY_DATASETS,
            description="Get dataset registry for UI dropdowns",
            action_patterns=[
                UiActionPattern(
                    pattern="registry_datasets",
                    description="Get dataset registry",
                    parameters=[],
                    example="registry_datasets"
                )
            ],
            api_endpoints=["GET /api/v1/meta/datasets", "GET /api/v1/registry/datasets"],
            ui_components=["OpTab", "RegistryTab", "DataPreparePanel"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.REGISTRY_STRATEGIES: UiActionMetadata(
            action_type=UiActionType.REGISTRY_STRATEGIES,
            description="Get strategy registry for UI dropdowns",
            action_patterns=[
                UiActionPattern(
                    pattern="registry_strategies",
                    description="Get strategy registry",
                    parameters=[],
                    example="registry_strategies"
                )
            ],
            api_endpoints=["GET /api/v1/meta/strategies", "GET /api/v1/registry/strategies"],
            ui_components=["OpTab", "RegistryTab"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.REGISTRY_INSTRUMENTS: UiActionMetadata(
            action_type=UiActionType.REGISTRY_INSTRUMENTS,
            description="Get instrument symbols for UI dropdowns",
            action_patterns=[
                UiActionPattern(
                    pattern="registry_instruments",
                    description="Get instrument registry",
                    parameters=[],
                    example="registry_instruments"
                )
            ],
            api_endpoints=["GET /api/v1/registry/instruments"],
            ui_components=["OpTab", "RegistryTab"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.REGISTRY_TIMEFRAMES: UiActionMetadata(
            action_type=UiActionType.REGISTRY_TIMEFRAMES,
            description="Get timeframe display names for UI dropdowns",
            action_patterns=[
                UiActionPattern(
                    pattern="registry_timeframes",
                    description="Get timeframe registry",
                    parameters=[],
                    example="registry_timeframes"
                )
            ],
            api_endpoints=["GET /api/v1/registry/timeframes"],
            ui_components=["OpTab", "RegistryTab"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        # Data operations
        UiActionType.DATA_READINESS: UiActionMetadata(
            action_type=UiActionType.DATA_READINESS,
            description="Check if bars/features are ready for given season/dataset/timeframe",
            action_patterns=[
                UiActionPattern(
                    pattern="data_readiness://{season}/{dataset_id}/{timeframe}",
                    description="Check data readiness",
                    parameters=["season", "dataset_id", "timeframe"],
                    example="data_readiness://2024Q1/VX/15m"
                )
            ],
            api_endpoints=["GET /api/v1/readiness/{season}/{dataset_id}/{timeframe}"],
            ui_components=["DataPreparePanel", "DataReadinessService"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        # Portfolio operations
        UiActionType.PORTFOLIO_ARTIFACTS: UiActionMetadata(
            action_type=UiActionType.PORTFOLIO_ARTIFACTS,
            description="Get portfolio artifacts and admission decisions",
            action_patterns=[
                UiActionPattern(
                    pattern="portfolio_artifacts://{portfolio_id}",
                    description="Get portfolio artifacts",
                    parameters=["portfolio_id"],
                    example="portfolio_artifacts://portfolio_abc123"
                )
            ],
            api_endpoints=["GET /api/v1/portfolios/{portfolio_id}/artifacts"],
            ui_components=["PortfolioAdmissionTab", "ArtifactNavigator"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        # Gate operations (from ActionRouterService)
        UiActionType.GATE_SUMMARY: UiActionMetadata(
            action_type=UiActionType.GATE_SUMMARY,
            description="Get gate summary for jobs (via consolidated service)",
            action_patterns=[
                UiActionPattern(
                    pattern="gate_summary",
                    description="Open gate summary",
                    parameters=[],
                    example="gate_summary"
                )
            ],
            api_endpoints=[],  # Internal contract, not direct API
            ui_components=["GateSummaryDashboardTab", "ConsolidatedGateSummaryService"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.GATE_DASHBOARD: UiActionMetadata(
            action_type=UiActionType.GATE_DASHBOARD,
            description="Navigate to gate dashboard",
            action_patterns=[
                UiActionPattern(
                    pattern="gate_dashboard",
                    description="Open gate dashboard",
                    parameters=[],
                    example="gate_dashboard"
                )
            ],
            api_endpoints=[],  # Internal navigation only
            ui_components=["GateSummaryDashboardTab", "ActionRouterService"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        # Navigation operations (from ActionRouterService)
        UiActionType.NAVIGATE_JOB_ADMISSION: UiActionMetadata(
            action_type=UiActionType.NAVIGATE_JOB_ADMISSION,
            description="Navigate to job admission decision artifact",
            action_patterns=[
                UiActionPattern(
                    pattern="job_admission://{job_id}",
                    description="Open job admission decision",
                    parameters=["job_id"],
                    example="job_admission://job_abc123"
                )
            ],
            api_endpoints=[],  # File system navigation, not API
            ui_components=["ActionRouterService", "ArtifactNavigator"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.NAVIGATE_ARTIFACT: UiActionMetadata(
            action_type=UiActionType.NAVIGATE_ARTIFACT,
            description="Navigate to job artifact",
            action_patterns=[
                UiActionPattern(
                    pattern="artifact://{job_id}/{artifact_name}",
                    description="Open job artifact",
                    parameters=["job_id", "artifact_name"],
                    example="artifact://job_abc123/strategy_report_v1.json"
                )
            ],
            api_endpoints=[],  # File system navigation, not API
            ui_components=["ActionRouterService", "ArtifactNavigator"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.NAVIGATE_EXPLAIN: UiActionMetadata(
            action_type=UiActionType.NAVIGATE_EXPLAIN,
            description="Navigate to job explain view",
            action_patterns=[
                UiActionPattern(
                    pattern="explain_navigate://{job_id}",
                    description="Navigate to explain view",
                    parameters=["job_id"],
                    example="explain_navigate://job_abc123"
                )
            ],
            api_endpoints=[],  # Internal navigation only
            ui_components=["ActionRouterService", "ExplainHubWidget"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.NAVIGATE_GATE_DASHBOARD: UiActionMetadata(
            action_type=UiActionType.NAVIGATE_GATE_DASHBOARD,
            description="Navigate to gate dashboard",
            action_patterns=[
                UiActionPattern(
                    pattern="internal://gate_dashboard",
                    description="Internal navigation to gate dashboard",
                    parameters=[],
                    example="internal://gate_dashboard"
                )
            ],
            api_endpoints=[],  # Internal navigation only
            ui_components=["ActionRouterService"],
            classification=ApiEndpointClassification.UI_REQUIRED,
            requires_auth=True,
            is_mutation=False
        ),
        
        # System operations
        UiActionType.SYSTEM_HEALTH: UiActionMetadata(
            action_type=UiActionType.SYSTEM_HEALTH,
            description="Check system health and identity",
            action_patterns=[
                UiActionPattern(
                    pattern="system_health",
                    description="Check system health",
                    parameters=[],
                    example="system_health"
                )
            ],
            api_endpoints=["GET /health", "GET /api/v1/identity", "GET /api/v1/run_status"],
            ui_components=["ControlStation", "SupervisorClient"],
            classification=ApiEndpointClassification.UI_OPTIONAL,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.SYSTEM_PRIME_REGISTRIES: UiActionMetadata(
            action_type=UiActionType.SYSTEM_PRIME_REGISTRIES,
            description="Prime registries cache (explicit trigger)",
            action_patterns=[
                UiActionPattern(
                    pattern="prime_registries",
                    description="Prime registries",
                    parameters=[],
                    example="prime_registries"
                )
            ],
            api_endpoints=["POST /api/v1/meta/prime"],
            ui_components=["ControlStation", "RegistryTab"],
            classification=ApiEndpointClassification.UI_OPTIONAL,
            requires_auth=True,
            is_mutation=True
        ),
        
        # Batch operations
        UiActionType.BATCH_STATUS: UiActionMetadata(
            action_type=UiActionType.BATCH_STATUS,
            description="Get batch execution status",
            action_patterns=[
                UiActionPattern(
                    pattern="batch_status://{batch_id}",
                    description="Get batch status",
                    parameters=["batch_id"],
                    example="batch_status://batch_abc123"
                )
            ],
            api_endpoints=["GET /api/v1/batches/{batch_id}/status"],
            ui_components=["BatchMonitor"],  # If exists
            classification=ApiEndpointClassification.UI_OPTIONAL,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.BATCH_METADATA: UiActionMetadata(
            action_type=UiActionType.BATCH_METADATA,
            description="Get or update batch metadata",
            action_patterns=[
                UiActionPattern(
                    pattern="batch_metadata://{batch_id}",
                    description="Get batch metadata",
                    parameters=["batch_id"],
                    example="batch_metadata://batch_abc123"
                )
            ],
            api_endpoints=[
                "GET /api/v1/batches/{batch_id}/metadata",
                "PATCH /api/v1/batches/{batch_id}/metadata"
            ],
            ui_components=["BatchMonitor"],  # If exists
            classification=ApiEndpointClassification.UI_OPTIONAL,
            requires_auth=True,
            is_mutation=True  # PATCH is mutation
        ),
        
        # Season operations
        UiActionType.SEASON_MANAGEMENT: UiActionMetadata(
            action_type=UiActionType.SEASON_MANAGEMENT,
            description="Manage seasons (create, list, freeze, attach jobs)",
            action_patterns=[
                UiActionPattern(
                    pattern="season_management",
                    description="Manage seasons",
                    parameters=[],
                    example="season_management"
                )
            ],
            api_endpoints=[
                ep for ep in [
                    "GET /api/v1/seasons/ssot",
                    "POST /api/v1/seasons/ssot/create",
                    "GET /api/v1/seasons/ssot/{season_id}",
                    "POST /api/v1/seasons/ssot/{season_id}/attach",
                    "POST /api/v1/seasons/ssot/{season_id}/freeze",
                    "POST /api/v1/seasons/ssot/{season_id}/archive",
                    "POST /api/v1/seasons/ssot/{season_id}/analyze",
                    "POST /api/v1/seasons/ssot/{season_id}/admit",
                    "POST /api/v1/seasons/ssot/{season_id}/export_candidates"
                ]
            ],
            ui_components=["SeasonSSOTDialog"],
            classification=ApiEndpointClassification.UI_OPTIONAL,
            requires_auth=True,
            is_mutation=True
        ),
        
        UiActionType.SEASON_COMPARE: UiActionMetadata(
            action_type=UiActionType.SEASON_COMPARE,
            description="Compare season data (leaderboard, topk, batches)",
            action_patterns=[
                UiActionPattern(
                    pattern="season_compare://{season_id}",
                    description="Compare season data",
                    parameters=["season_id"],
                    example="season_compare://2024Q1"
                )
            ],
            api_endpoints=[
                "GET /api/v1/seasons/{season}/compare/batches",
                "GET /api/v1/seasons/{season}/compare/leaderboard",
                "GET /api/v1/seasons/{season}/compare/topk",
                "GET /api/v1/exports/seasons/{season}/compare/batches",
                "GET /api/v1/exports/seasons/{season}/compare/leaderboard",
                "GET /api/v1/exports/seasons/{season}/compare/topk"
            ],
            ui_components=["SeasonCompareView"],  # If exists
            classification=ApiEndpointClassification.UI_OPTIONAL,
            requires_auth=True,
            is_mutation=False
        ),
        
        UiActionType.SEASON_EXPORT: UiActionMetadata(
            action_type=UiActionType.SEASON_EXPORT,
            description="Export season data",
            action_patterns=[
                UiActionPattern(
                    pattern="season_export://{season_id}",
                    description="Export season",
                    parameters=["season_id"],
                    example="season_export://2024Q1"
                )
            ],
            api_endpoints=["POST /api/v1/seasons/{season}/export"],
            ui_components=["SeasonSSOTDialog"],
            classification=ApiEndpointClassification.UI_OPTIONAL,
            requires_auth=True,
            is_mutation=True
        ),
    }
    
    # Create registry
    registry = UiActionRegistry(actions=actions)
    
    # Update statistics
    stats = registry.get_statistics()
    object.__setattr__(registry, "statistics", stats)
    
    return registry


# -----------------------------------------------------------------------------
# Singleton instance
# -----------------------------------------------------------------------------

_DEFAULT_UI_ACTION_REGISTRY: Optional[UiActionRegistry] = None


def get_default_ui_action_registry() -> UiActionRegistry:
    """Get singleton instance of default UI action registry."""
    global _DEFAULT_UI_ACTION_REGISTRY
    if _DEFAULT_UI_ACTION_REGISTRY is None:
        _DEFAULT_UI_ACTION_REGISTRY = create_default_ui_action_registry()
    return _DEFAULT_UI_ACTION_REGISTRY


def reload_ui_action_registry() -> UiActionRegistry:
    """Reload the UI action registry (for testing)."""
    global _DEFAULT_UI_ACTION_REGISTRY
    _DEFAULT_UI_ACTION_REGISTRY = create_default_ui_action_registry()
    return _DEFAULT_UI_ACTION_REGISTRY


# -----------------------------------------------------------------------------
# Integration with ActionRouterService
# -----------------------------------------------------------------------------

def validate_action_router_target(target: str) -> bool:
    """
    Validate if a target string is a valid UI action.
    
    This function can be used by ActionRouterService to validate targets.
    """
    registry = get_default_ui_action_registry()
    return registry.validate_action_target(target)


def get_action_metadata_for_target(target: str) -> Optional[UiActionMetadata]:
    """
    Get action metadata for a given target string.
    
    This function can be used by ActionRouterService to get metadata for logging
    or analytics.
    """
    registry = get_default_ui_action_registry()
    return registry.find_action_for_target(target)


# -----------------------------------------------------------------------------
# Export
# -----------------------------------------------------------------------------

__all__ = [
    "UiActionType",
    "UiActionPattern",
    "UiActionMetadata",
    "UiActionRegistry",
    "create_default_ui_action_registry",
    "get_default_ui_action_registry",
    "reload_ui_action_registry",
    "validate_action_router_target",
    "get_action_metadata_for_target",
]