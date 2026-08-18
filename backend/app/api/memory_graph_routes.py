"""
Memory Graph API Routes

This module provides FastAPI routes for retrieving and managing the knowledge graph
stored in FalkorDB via GraphLTM. It enables visualization of entities and relationships
in the ASTA memory system.
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from backend.app.auth.token_auth import verify_bearer_and_device
from backend.app.services.memory.graph_ltm import graph_ltm

# Configure logger for memory graph module
logger = logging.getLogger("MemoryGraphAPI")

# Initialize FastAPI router
router = APIRouter(tags=["memory-graph"])


# ============================================================================
# Pydantic Models
# ============================================================================

class GraphNode(BaseModel):
    """
    Represents a node (entity) in the knowledge graph.
    
    Attributes:
        id: Unique identifier for the node
        name: Display name of the entity
        entity_type: Classification of the entity (e.g., PERSON, SKILL, PROJECT)
        description: Optional descriptive text about the entity
        metadata: Additional entity-specific properties
    """
    id: str = Field(..., description="Unique node identifier")
    name: str = Field(..., description="Display name of the entity")
    entity_type: str = Field(..., description="Entity type classification")
    description: Optional[str] = Field(None, description="Optional entity description")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional properties")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "person_karthik",
                "name": "Karthik",
                "entity_type": "PERSON",
                "description": "Main user of ASTA system",
                "metadata": {
                    "role": "Student",
                    "location": "New Delhi, India",
                    "github": "karthik-user"
                }
            }
        }


class GraphEdge(BaseModel):
    """
    Represents an edge (relationship) between two nodes in the knowledge graph.
    
    Attributes:
        source_id: ID of the source node
        target_id: ID of the target node
        relationship_type: Type of relationship (e.g., HAS_SKILL, WORKS_ON)
        metadata: Additional relationship-specific properties
    """
    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    relationship_type: str = Field(..., description="Relationship type")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Relationship properties")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_id": "person_karthik",
                "target_id": "skill_python",
                "relationship_type": "HAS_SKILL",
                "metadata": {
                    "level": "Expert",
                    "priority": "High"
                }
            }
        }


class GraphResponse(BaseModel):
    """
    Complete graph data response containing nodes and edges.
    
    Attributes:
        nodes: List of all graph nodes
        edges: List of all graph edges
    """
    nodes: List[GraphNode] = Field(..., description="List of graph nodes")
    edges: List[GraphEdge] = Field(..., description="List of graph edges")
    
    class Config:
        json_schema_extra = {
            "example": {
                "nodes": [
                    {
                        "id": "person_karthik",
                        "name": "Karthik",
                        "entity_type": "PERSON",
                        "description": "Main user",
                        "metadata": {"role": "Student"}
                    }
                ],
                "edges": [
                    {
                        "source_id": "person_karthik",
                        "target_id": "skill_python",
                        "relationship_type": "HAS_SKILL",
                        "metadata": {"level": "Expert"}
                    }
                ]
            }
        }


# ============================================================================
# Error Response Models
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response structure."""
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Failed to retrieve graph data",
                "details": "Connection timeout to FalkorDB"
            }
        }


class ServiceUnavailableError(ErrorResponse):
    """Error response for HTTP 503 - Service Unavailable."""
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Graph database not initialized"
            }
        }


class InternalServerError(ErrorResponse):
    """Error response for HTTP 500 - Internal Server Error."""
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Failed to retrieve graph data",
                "details": "Database connection failed"
            }
        }


class GatewayTimeoutError(ErrorResponse):
    """Error response for HTTP 504 - Gateway Timeout."""
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Request timeout"
            }
        }


class UnauthorizedError(ErrorResponse):
    """Error response for HTTP 401 - Unauthorized."""
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Unauthorized"
            }
        }


# ============================================================================
# API Endpoints
# ============================================================================

@router.get(
    "/memory/graph",
    response_model=GraphResponse,
    responses={
        200: {
            "description": "Successfully retrieved graph data",
            "model": GraphResponse
        },
        401: {
            "description": "Authentication failed - invalid or missing token",
            "model": UnauthorizedError
        },
        503: {
            "description": "Graph database not initialized",
            "model": ServiceUnavailableError
        },
        500: {
            "description": "Internal server error during graph retrieval",
            "model": InternalServerError
        },
        504: {
            "description": "Request timeout (exceeded 3 seconds)",
            "model": GatewayTimeoutError
        }
    },
    summary="Retrieve complete knowledge graph",
    description="""
    Retrieves the complete knowledge graph from FalkorDB, including all entities
    (nodes) and their relationships (edges). The graph is centered around the user's
    identity and includes Skills, Projects, Goals, Priorities, Communities, and Organizations.
    
    **Authentication Required**: Bearer token + X-Device-Id header
    
    **Timeout**: 3 seconds maximum response time
    
    **Returns**:
    - Empty arrays if graph contains no data
    - Full graph structure with nodes and edges
    """
)
async def get_memory_graph(
    user: str = Depends(verify_bearer_and_device)
) -> GraphResponse:
    """
    Retrieve the complete knowledge graph from FalkorDB.
    
    This endpoint queries GraphLTM to fetch all nodes and edges from the knowledge graph.
    It requires authentication via Bearer token and device ID verification.
    
    Args:
        user: Authenticated user token (injected by dependency)
    
    Returns:
        GraphResponse: Complete graph with nodes and edges arrays
    
    Raises:
        HTTPException 401: If authentication fails (handled by verify_bearer_and_device)
        HTTPException 503: If GraphLTM is not initialized
        HTTPException 500: If graph retrieval fails
        HTTPException 504: If request exceeds 3-second timeout
    
    Examples:
        >>> # Successful response
        >>> {
        ...     "nodes": [
        ...         {"id": "p1", "name": "Karthik", "entity_type": "PERSON", ...}
        ...     ],
        ...     "edges": [
        ...         {"source_id": "p1", "target_id": "s1", "relationship_type": "HAS_SKILL", ...}
        ...     ]
        ... }
        
        >>> # Empty graph response
        >>> {"nodes": [], "edges": []}
    """
    from datetime import datetime, timezone
    
    # Log request with timestamp and user info
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info(
        f"[{timestamp}] Memory graph request received | "
        f"User: {user[:10]}... | "
        f"Endpoint: GET /api/memory/graph"
    )
    
    # This is a placeholder implementation for Task 1
    # The actual graph retrieval logic will be implemented in Task 2
    
    # Return empty graph for now
    # This will be replaced with actual implementation in subsequent tasks
    return GraphResponse(nodes=[], edges=[])


# ============================================================================
# Module Initialization
# ============================================================================

logger.info("Memory Graph API routes initialized")
