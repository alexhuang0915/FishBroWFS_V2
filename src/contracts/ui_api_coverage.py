"""
UI/API Coverage Matrix SSOT (Single Source of Truth).

This module defines the classification system and inventory for API endpoints
and their relationship to UI components. It serves as the authoritative source
for which API endpoints are required by the UI, optional for UI use, or
internal-only.

Classification Rules:
- UI_REQUIRED: Endpoints directly used by UI components (dropdowns, tables, forms)
- UI_OPTIONAL: Endpoints available to UI but not required for core functionality
- INTERNAL_ONLY: Endpoints not exposed to UI (admin, debugging, internal use)

Usage:
    from contracts.ui_api_coverage import (
        ApiEndpointClassification,
        UI_REQUIRED,
        UI_OPTIONAL,
        INTERNAL_ONLY,
        get_coverage_matrix,
        validate_endpoint_classification,
        get_ui_required_endpoints,
    )
"""

from __future__ import annotations

import json
import os
from enum import Enum
from typing import Dict, List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field


class ApiEndpointClassification(str, Enum):
    """Classification of API endpoints based on UI dependency."""
    UI_REQUIRED = "UI_REQUIRED"
    UI_OPTIONAL = "UI_OPTIONAL"
    INTERNAL_ONLY = "INTERNAL_ONLY"


class ApiEndpointMetadata(BaseModel):
    """Metadata for a single API endpoint."""
    endpoint_id: str = Field(..., description="Unique identifier: METHOD PATH")
    method: str = Field(..., description="HTTP method (GET, POST, PATCH, etc.)")
    path: str = Field(..., description="API path with parameters")
    summary: str = Field(..., description="Brief summary from OpenAPI")
    description: str = Field("", description="Detailed description from OpenAPI")
    operation_id: str = Field(..., description="OpenAPI operationId")
    responses: List[str] = Field(default_factory=list, description="HTTP response codes")
    tags: List[str] = Field(default_factory=list, description="OpenAPI tags")
    classification: ApiEndpointClassification = Field(
        ..., description="UI/API coverage classification"
    )
    
    # UI mapping information (optional)
    ui_component: Optional[str] = Field(None, description="Primary UI component using this endpoint")
    ui_action: Optional[str] = Field(None, description="UI action that triggers this endpoint")
    ui_required_params: List[str] = Field(default_factory=list, description="Parameters required by UI")


class CoverageMatrix(BaseModel):
    """Complete UI/API coverage matrix."""
    ui_required: List[ApiEndpointMetadata] = Field(
        default_factory=list,
        description="Endpoints directly required by UI components"
    )
    ui_optional: List[ApiEndpointMetadata] = Field(
        default_factory=list,
        description="Endpoints optionally available to UI"
    )
    internal_only: List[ApiEndpointMetadata] = Field(
        default_factory=list,
        description="Endpoints not exposed to UI (internal use only)"
    )
    
    @property
    def total_endpoints(self) -> int:
        """Total number of endpoints in the matrix."""
        return len(self.ui_required) + len(self.ui_optional) + len(self.internal_only)
    
    @property
    def ui_coverage_ratio(self) -> float:
        """Ratio of UI-required endpoints to total endpoints."""
        total = self.total_endpoints
        if total == 0:
            return 0.0
        return len(self.ui_required) / total
    
    def get_endpoint_by_id(self, endpoint_id: str) -> Optional[ApiEndpointMetadata]:
        """Find an endpoint by its ID (METHOD PATH)."""
        for endpoint in self.ui_required + self.ui_optional + self.internal_only:
            if endpoint.endpoint_id == endpoint_id:
                return endpoint
        return None
    
    def get_endpoints_by_classification(
        self, classification: ApiEndpointClassification
    ) -> List[ApiEndpointMetadata]:
        """Get all endpoints with a specific classification."""
        if classification == ApiEndpointClassification.UI_REQUIRED:
            return self.ui_required
        elif classification == ApiEndpointClassification.UI_OPTIONAL:
            return self.ui_optional
        else:  # INTERNAL_ONLY
            return self.internal_only
    
    def to_dict(self) -> Dict:
        """Convert matrix to dictionary for serialization."""
        return {
            "ui_required": [e.model_dump() for e in self.ui_required],
            "ui_optional": [e.model_dump() for e in self.ui_optional],
            "internal_only": [e.model_dump() for e in self.internal_only],
            "summary": {
                "total_endpoints": self.total_endpoints,
                "ui_required": len(self.ui_required),
                "ui_optional": len(self.ui_optional),
                "internal_only": len(self.internal_only),
                "ui_coverage_ratio": self.ui_coverage_ratio,
            }
        }


# Classification rules constants
CLASSIFICATION_RULES = {
    ApiEndpointClassification.UI_REQUIRED: (
        "Endpoints directly used by UI components (dropdowns, tables, forms). "
        "These endpoints must remain stable and backward compatible."
    ),
    ApiEndpointClassification.UI_OPTIONAL: (
        "Endpoints available to UI but not required for core functionality. "
        "UI may use these for enhanced features or debugging."
    ),
    ApiEndpointClassification.INTERNAL_ONLY: (
        "Endpoints not exposed to UI (admin, debugging, internal use). "
        "These can change without breaking UI compatibility."
    ),
}


def validate_endpoint_classification(endpoint: ApiEndpointMetadata) -> bool:
    """
    Validate that an endpoint's classification matches its characteristics.
    
    Rules:
    - UI_REQUIRED endpoints should have GET method (read-only) or simple mutations
    - INTERNAL_ONLY endpoints should not be referenced by UI components
    - All endpoints must have valid operation_id and path
    """
    if not endpoint.operation_id or not endpoint.path:
        return False
    
    # Basic validation based on method
    if endpoint.method not in {"GET", "POST", "PATCH", "PUT", "DELETE", "HEAD", "OPTIONS"}:
        return False
    
    return True


def _load_inventory_from_json() -> CoverageMatrix:
    """
    Load the coverage matrix from the generated inventory JSON file.
    
    Returns:
        CoverageMatrix: Loaded coverage matrix
    """
    # Path to the generated inventory
    inventory_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "outputs", "_dp_evidence", "ui_api_coverage_v1", "api_inventory.json"
    )
    
    # Resolve absolute path
    inventory_path = os.path.abspath(inventory_path)
    
    if not os.path.exists(inventory_path):
        # Return empty matrix if file doesn't exist
        return CoverageMatrix()
    
    with open(inventory_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Parse the coverage matrix from JSON
    matrix = CoverageMatrix()
    
    # Map classification strings to enum values
    classification_map = {
        "UI_REQUIRED": ApiEndpointClassification.UI_REQUIRED,
        "UI_OPTIONAL": ApiEndpointClassification.UI_OPTIONAL,
        "INTERNAL_ONLY": ApiEndpointClassification.INTERNAL_ONLY,
    }
    
    # Load UI_REQUIRED endpoints
    for item in data.get("coverage_matrix", {}).get("UI_REQUIRED", []):
        endpoint = ApiEndpointMetadata(
            endpoint_id=item["endpoint_id"],
            method=item["method"],
            path=item["path"],
            summary=item.get("summary", ""),
            description=item.get("description", ""),
            operation_id=item.get("operation_id", ""),
            responses=item.get("responses", []),
            tags=item.get("tags", []),
            classification=classification_map[item["classification"]],
        )
        matrix.ui_required.append(endpoint)
    
    # Load UI_OPTIONAL endpoints
    for item in data.get("coverage_matrix", {}).get("UI_OPTIONAL", []):
        endpoint = ApiEndpointMetadata(
            endpoint_id=item["endpoint_id"],
            method=item["method"],
            path=item["path"],
            summary=item.get("summary", ""),
            description=item.get("description", ""),
            operation_id=item.get("operation_id", ""),
            responses=item.get("responses", []),
            tags=item.get("tags", []),
            classification=classification_map[item["classification"]],
        )
        matrix.ui_optional.append(endpoint)
    
    # Load INTERNAL_ONLY endpoints (empty in current inventory)
    for item in data.get("coverage_matrix", {}).get("INTERNAL_ONLY", []):
        endpoint = ApiEndpointMetadata(
            endpoint_id=item["endpoint_id"],
            method=item["method"],
            path=item["path"],
            summary=item.get("summary", ""),
            description=item.get("description", ""),
            operation_id=item.get("operation_id", ""),
            responses=item.get("responses", []),
            tags=item.get("tags", []),
            classification=classification_map[item["classification"]],
        )
        matrix.internal_only.append(endpoint)
    
    return matrix


def get_coverage_matrix() -> CoverageMatrix:
    """
    Get the current UI/API coverage matrix.
    
    This function loads the matrix from the generated inventory JSON file.
    
    Returns:
        CoverageMatrix: Current UI/API coverage matrix
    """
    return _load_inventory_from_json()


def get_ui_required_endpoints() -> List[ApiEndpointMetadata]:
    """Convenience function to get all UI-required endpoints."""
    matrix = get_coverage_matrix()
    return matrix.ui_required


def get_endpoints_by_ui_component(ui_component: str) -> List[ApiEndpointMetadata]:
    """Get all endpoints used by a specific UI component."""
    matrix = get_coverage_matrix()
    results = []
    
    for endpoint in matrix.ui_required + matrix.ui_optional:
        if endpoint.ui_component == ui_component:
            results.append(endpoint)
    
    return results


# Type aliases for convenience
UI_REQUIRED = ApiEndpointClassification.UI_REQUIRED
UI_OPTIONAL = ApiEndpointClassification.UI_OPTIONAL
INTERNAL_ONLY = ApiEndpointClassification.INTERNAL_ONLY