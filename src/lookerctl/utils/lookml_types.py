"""Enhanced type definitions for LookML parsing with file/line tracking."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class FieldType(str, Enum):
    """LookML field types."""

    DIMENSION = "dimension"
    DIMENSION_GROUP = "dimension_group"
    MEASURE = "measure"
    FILTER = "filter"
    PARAMETER = "parameter"


class JoinType(str, Enum):
    """SQL join types."""

    LEFT_OUTER = "left_outer"
    FULL_OUTER = "full_outer"
    INNER = "inner"
    CROSS = "cross"


class JoinRelationship(str, Enum):
    """Looker join relationships."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


@dataclass
class SourceLocation:
    """Track where something was defined in source files."""

    file_path: Path
    line_number: Optional[int] = None
    column: Optional[int] = None

    def __str__(self) -> str:
        if self.line_number:
            return f"{self.file_path}:{self.line_number}"
        return str(self.file_path)


@dataclass
class Field:
    """Represents a field in a LookML view."""

    name: str
    field_type: FieldType
    sql: Optional[str] = None
    type: Optional[str] = None  # string, number, date, etc.
    description: Optional[str] = None
    label: Optional[str] = None
    hidden: bool = False
    primary_key: bool = False
    drill_fields: list[str] = field(default_factory=list)
    view_label: Optional[str] = None  # For display in UI
    group_label: Optional[str] = None

    # Source tracking
    source: Optional[SourceLocation] = None

    # For dimension_group
    timeframes: list[str] = field(default_factory=list)
    datatype: Optional[str] = None  # For dimension_group: date, timestamp, etc.

    # Additional properties
    value_format: Optional[str] = None
    required_fields: list[str] = field(default_factory=list)

    def get_qualified_name(self, view_name: str) -> str:
        """Get fully qualified field name (view.field)."""
        return f"{view_name}.{self.name}"


@dataclass
class Join:
    """Represents a join in a LookML explore."""

    name: str
    from_view: Optional[str] = None  # View to join from
    type: JoinType = JoinType.LEFT_OUTER
    relationship: Optional[JoinRelationship] = None
    sql_on: Optional[str] = None
    sql_where: Optional[str] = None
    foreign_key: Optional[str] = None
    required_joins: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)  # Field scoping for this join

    # Source tracking
    source: Optional[SourceLocation] = None


@dataclass
class View:
    """Represents a LookML view."""

    name: str
    sql_table_name: Optional[str] = None
    derived_table: Optional[dict[str, Any]] = None
    fields: list[Field] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)

    # Source tracking
    source: Optional[SourceLocation] = None

    # Additional properties
    label: Optional[str] = None
    description: Optional[str] = None
    suggestions: bool = True

    def get_field(self, field_name: str) -> Optional[Field]:
        """Get field by name."""
        for f in self.fields:
            if f.name == field_name:
                return f
        return None

    def get_dimensions(self) -> list[Field]:
        """Get all dimension fields."""
        return [
            f
            for f in self.fields
            if f.field_type in (FieldType.DIMENSION, FieldType.DIMENSION_GROUP)
        ]

    def get_measures(self) -> list[Field]:
        """Get all measure fields."""
        return [f for f in self.fields if f.field_type == FieldType.MEASURE]

    def has_field(self, field_name: str) -> bool:
        """Check if field exists."""
        return any(f.name == field_name for f in self.fields)


@dataclass
class Explore:
    """Represents a LookML explore."""

    name: str
    view_name: Optional[str] = None  # Base view (defaults to explore name)
    joins: list[Join] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)  # Field scoping
    extends: list[str] = field(default_factory=list)
    hidden: bool = False

    # Source tracking
    source: Optional[SourceLocation] = None

    # Additional properties
    label: Optional[str] = None
    description: Optional[str] = None
    group_label: Optional[str] = None
    access_filters: list[dict[str, str]] = field(default_factory=list)
    always_filter: dict[str, Any] = field(default_factory=dict)

    def get_base_view_name(self) -> str:
        """Get the base view name (view_name or explore name)."""
        return self.view_name or self.name

    def get_join(self, join_name: str) -> Optional[Join]:
        """Get join by name."""
        for j in self.joins:
            if j.name == join_name:
                return j
        return None

    def has_field_scoping(self) -> bool:
        """Check if explore limits available fields."""
        return len(self.fields) > 0


@dataclass
class Model:
    """Represents a LookML model."""

    name: str
    connection: Optional[str] = None
    explores: list[Explore] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)

    # Source tracking
    source: Optional[SourceLocation] = None

    # Additional properties
    label: Optional[str] = None
    datagroups: list[dict[str, Any]] = field(default_factory=list)
    access_grants: list[dict[str, Any]] = field(default_factory=list)

    def get_explore(self, explore_name: str) -> Optional[Explore]:
        """Get explore by name."""
        for e in self.explores:
            if e.name == explore_name:
                return e
        return None

    def has_explore(self, explore_name: str) -> bool:
        """Check if explore exists."""
        return any(e.name == explore_name for e in self.explores)


@dataclass
class ValidationError:
    """Represents a validation error."""

    type: str  # error type: invalid_field_reference, missing_view, etc.
    message: str
    file_path: Path
    line_number: Optional[int] = None
    severity: str = "error"  # error, warning, info

    # Context
    view_name: Optional[str] = None
    explore_name: Optional[str] = None
    field_name: Optional[str] = None

    def __str__(self) -> str:
        location = (
            f"{self.file_path}:{self.line_number}" if self.line_number else str(self.file_path)
        )
        return f"[{self.severity.upper()}] {location} - {self.message}"


@dataclass
class FieldReference:
    """Represents a reference to a field in SQL or LookML."""

    view_name: Optional[str]  # None for local field references
    field_name: str
    raw_reference: str  # Original ${...} text

    # Where this reference appears
    source: Optional[SourceLocation] = None

    def is_local(self) -> bool:
        """Check if this is a local field reference (${field})."""
        return self.view_name is None

    def get_qualified_name(self) -> str:
        """Get fully qualified name."""
        if self.view_name:
            return f"{self.view_name}.{self.field_name}"
        return self.field_name


@dataclass
class Constant:
    """Represents a constant defined in manifest."""

    name: str
    value: str
    export: Optional[str] = None  # override_required, override_optional
    source: Optional[SourceLocation] = None


@dataclass
class Refinement:
    """Represents a LookML refinement (+view or +explore)."""

    target_name: str  # View or explore being refined
    refinement_type: str  # "view" or "explore"
    properties: dict[str, Any] = field(default_factory=dict)
    source: Optional[SourceLocation] = None


@dataclass
class DashboardElement:
    """Represents a tile/element in a dashboard."""

    title: str
    model: Optional[str] = None
    explore: Optional[str] = None
    fields: list[str] = field(default_factory=list)  # Field references like view.field
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class Dashboard:
    """Represents a user-defined dashboard (YAML format)."""

    name: str  # Dashboard name/id
    title: str
    elements: list[DashboardElement] = field(default_factory=list)
    source: Optional[SourceLocation] = None

    def get_explore_references(self) -> set[str]:
        """Get all unique model.explore references from this dashboard."""
        explores = set()
        for element in self.elements:
            if element.model and element.explore:
                explores.add(f"{element.model}.{element.explore}")
        return explores

    def get_field_references(self) -> set[str]:
        """Get all unique field references from this dashboard."""
        fields = set()
        for element in self.elements:
            fields.update(element.fields)
            # Also extract fields from filters
            for filter_field in element.filters.keys():
                fields.add(filter_field)
        return fields
