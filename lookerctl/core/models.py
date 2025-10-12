"""Data models and types for Looker SDK CLI."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WorkspaceType(str, Enum):
    """Looker workspace type."""

    PRODUCTION = "production"
    DEV = "dev"


class Workspace(BaseModel):
    """Looker workspace information."""

    id: str
    name: Optional[str] = None
    workspace_type: WorkspaceType
    project: str
    is_default: bool = False


class ValidationError(BaseModel):
    """LookML validation error."""

    message: str
    severity: str  # error, warning, info
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    field_name: Optional[str] = None


class ValidationResult(BaseModel):
    """Result of LookML validation."""

    is_valid: bool
    errors: list[ValidationError] = Field(default_factory=list)
    warnings: list[ValidationError] = Field(default_factory=list)
    project: str
    timestamp: datetime = Field(default_factory=datetime.now)


class FileInfo(BaseModel):
    """LookML file information."""

    path: str
    name: str
    file_type: str  # explore, view, model, dashboard
    content: Optional[str] = None
    size: int = 0


class ExploreUsage(BaseModel):
    """Usage statistics for an explore."""

    explore_name: str
    model_name: str
    query_count: int = 0
    user_count: int = 0
    last_accessed: Optional[datetime] = None
    dashboards_using: list[str] = Field(default_factory=list)
    looks_using: list[str] = Field(default_factory=list)


class ViewUsage(BaseModel):
    """Usage statistics for a view."""

    view_name: str
    explores_using: list[str] = Field(default_factory=list)
    dashboards_using: list[str] = Field(default_factory=list)
    query_count: int = 0
    is_orphaned: bool = False


class FieldUsage(BaseModel):
    """Usage statistics for a field."""

    field_name: str
    view_name: str
    field_type: str  # dimension, measure, filter
    query_count: int = 0
    dashboard_count: int = 0
    is_used: bool = True


class DependencyNode(BaseModel):
    """Dependency graph node."""

    name: str
    node_type: str  # view, explore, model
    file_path: str
    depends_on: list[str] = Field(default_factory=list)
    used_by: list[str] = Field(default_factory=list)


class DependencyGraph(BaseModel):
    """Complete dependency graph."""

    nodes: list[DependencyNode] = Field(default_factory=list)
    circular_dependencies: list[list[str]] = Field(default_factory=list)


class ProjectInfo(BaseModel):
    """Looker project information."""

    id: str
    name: str
    git_remote_url: Optional[str] = None
    git_production_branch_name: Optional[str] = None
    uses_git: bool = True
    folder_count: Optional[int] = None
    file_count: Optional[int] = None


class ExportSummary(BaseModel):
    """Summary of LookML export operation."""

    project: str
    branch: str
    files_exported: int
    total_size: int
    timestamp: datetime = Field(default_factory=datetime.now)
    errors: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """Comprehensive analysis report."""

    project: str
    timestamp: datetime = Field(default_factory=datetime.now)
    explores: list[ExploreUsage] = Field(default_factory=list)
    views: list[ViewUsage] = Field(default_factory=list)
    fields: list[FieldUsage] = Field(default_factory=list)
    orphaned_views: list[str] = Field(default_factory=list)
    unused_fields: list[str] = Field(default_factory=list)
    total_queries_analyzed: int = 0
