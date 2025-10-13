"""Enhanced LookML parser with comprehensive construct support and source tracking.

This parser provides:
- Complete parsing of all LookML constructs (views, explores, models, refinements, etc.)
- Field reference extraction (${view.field}, ${field}, ${TABLE})
- Source location tracking for precise error reporting
- Liquid template handling in constants
- View inheritance (extends) tracking
"""

import re
from pathlib import Path
from typing import Any, Optional

import lkml
import yaml

from lookerctl.utils.lookml_types import (
    Constant,
    Dashboard,
    DashboardElement,
    Explore,
    Field,
    FieldReference,
    FieldType,
    Join,
    JoinRelationship,
    JoinType,
    Model,
    Refinement,
    SourceLocation,
    View,
)


class LookMLParser:
    """Enhanced LookML parser with full construct support."""

    # Field reference patterns
    FIELD_REF_PATTERN = re.compile(r"\$\{([^}]+)\}")
    TABLE_REF_PATTERN = re.compile(r"\$\{TABLE\}")

    # Liquid template patterns
    LIQUID_VAR_PATTERN = re.compile(r"\{\{([^}]+)\}\}")
    LIQUID_TAG_PATTERN = re.compile(r"\{%([^%]+)%\}")

    def __init__(self):
        """Initialize parser."""
        self._current_file: Optional[Path] = None

    def _is_yaml_dashboard(self, content: str) -> bool:
        """Check if file content is a YAML dashboard instead of LookML."""
        # YAML dashboards start with --- and have dashboard: key
        return content.strip().startswith("---") or (
            content.strip().startswith("- dashboard:") or "- dashboard:" in content[:200]
        )

    def _parse_yaml_dashboard(self, file_path: Path, content: str) -> Dashboard:
        """Parse a YAML dashboard file.

        YAML dashboards have structure:
        ---
        - dashboard: name
          title: Dashboard Title
          elements:
          - title: Element Title
            model: model_name
            explore: explore_name
            fields: [field1, field2]
            filters:
              field_name: value
        """
        try:
            data = yaml.safe_load(content)
        except Exception as e:
            raise ValueError(f"Failed to parse YAML dashboard {file_path}: {e}") from e

        # YAML dashboards are arrays with single dashboard object
        if isinstance(data, list) and len(data) > 0:
            dash_data = data[0]
        else:
            dash_data = data

        if not isinstance(dash_data, dict):
            raise ValueError(f"Invalid dashboard structure in {file_path}")

        # Extract dashboard info
        dashboard_name = dash_data.get("dashboard", file_path.stem)
        dashboard_title = dash_data.get("title", dashboard_name)

        # Parse elements
        elements = []
        for elem_data in dash_data.get("elements", []):
            if not isinstance(elem_data, dict):
                continue

            # Extract fields from element
            fields = elem_data.get("fields", [])
            if isinstance(fields, str):
                fields = [fields]
            elif not isinstance(fields, list):
                fields = []

            # Parse fields - handle both formats: ["field1", "field2"] and multi-line
            parsed_fields = []
            for field_item in fields:
                if isinstance(field_item, str):
                    # Could be comma-separated like "field1, field2"
                    parsed_fields.extend([f.strip() for f in field_item.split(",")])
                elif isinstance(field_item, list):
                    parsed_fields.extend(field_item)

            element = DashboardElement(
                title=elem_data.get("title", elem_data.get("name", "Untitled")),
                model=elem_data.get("model"),
                explore=elem_data.get("explore"),
                fields=parsed_fields,
                filters=elem_data.get("filters", {}),
            )
            elements.append(element)

        return Dashboard(
            name=dashboard_name,
            title=dashboard_title,
            elements=elements,
            source=SourceLocation(file_path=file_path),
        )

    def parse_file(self, file_path: Path) -> dict[str, Any]:
        """Parse a LookML file and return structured data.

        Returns dict with keys:
        - views: list[View]
        - explores: list[Explore]
        - models: list[Model]
        - constants: list[Constant]
        - refinements: list[Refinement]
        - dashboards: list[Dashboard]
        """
        self._current_file = file_path

        content = file_path.read_text()

        # Check if this is a YAML dashboard instead of LookML
        if self._is_yaml_dashboard(content):
            dashboard = self._parse_yaml_dashboard(file_path, content)
            return {
                "views": [],
                "explores": [],
                "models": [],
                "constants": [],
                "refinements": [],
                "dashboards": [dashboard],
            }

        # Parse as traditional LookML
        try:
            parsed = lkml.load(content)
        except Exception as e:
            raise ValueError(f"Failed to parse {file_path}: {e}") from e

        result: dict[str, Any] = {
            "views": [],
            "explores": [],
            "models": [],
            "constants": [],
            "refinements": [],
            "dashboards": [],
        }

        # Parse based on file type and content
        if "connection" in parsed:
            # This is a model file
            result["models"].append(self._parse_model(parsed))

        # Parse views
        if "views" in parsed:
            for view_data in parsed["views"]:
                result["views"].append(self._parse_view(view_data))

        # Parse explores (can be in model or separate file)
        if "explores" in parsed:
            for explore_data in parsed["explores"]:
                result["explores"].append(self._parse_explore(explore_data))

        # Parse constants (manifest.lkml)
        if "constant" in parsed:
            result["constants"].append(self._parse_constant(parsed["constant"]))

        # Parse refinements
        for key in parsed:
            if key.startswith("+"):
                refinement_type = "view" if key == "+view" else "explore"
                for refinement_data in parsed[key]:
                    result["refinements"].append(
                        self._parse_refinement(refinement_data, refinement_type)
                    )

        return result

    def _parse_model(self, data: dict[str, Any]) -> Model:
        """Parse a LookML model."""
        explores = []
        if "explores" in data:
            for explore_data in data["explores"]:
                explores.append(self._parse_explore(explore_data))

        includes = data.get("includes", [])
        if isinstance(includes, str):
            includes = [includes]

        datagroups = data.get("datagroups", [])
        access_grants = data.get("access_grants", [])

        return Model(
            name=data.get("name", self._current_file.stem),
            connection=data.get("connection"),
            explores=explores,
            includes=includes,
            source=self._make_source_location(),
            label=data.get("label"),
            datagroups=datagroups,
            access_grants=access_grants,
        )

    def _parse_view(self, data: dict[str, Any]) -> View:
        """Parse a LookML view."""
        fields = []

        # Parse all field types
        for field_type_key, field_type_enum in [
            ("dimensions", FieldType.DIMENSION),
            ("dimension_groups", FieldType.DIMENSION_GROUP),
            ("measures", FieldType.MEASURE),
            ("filters", FieldType.FILTER),
            ("parameters", FieldType.PARAMETER),
        ]:
            if field_type_key in data:
                for field_data in data[field_type_key]:
                    fields.append(self._parse_field(field_data, field_type_enum))

        extends = data.get("extends", [])
        if isinstance(extends, str):
            extends = [extends]

        # Parse derived table if present
        derived_table = data.get("derived_table") or data.get("sql_table_name")

        return View(
            name=data["name"],
            sql_table_name=data.get("sql_table_name"),
            derived_table=derived_table if isinstance(derived_table, dict) else None,
            fields=fields,
            extends=extends,
            source=self._make_source_location(),
            label=data.get("label"),
            description=data.get("description"),
            suggestions=data.get("suggestions", True),
        )

    def _parse_field(self, data: dict[str, Any], field_type: FieldType) -> Field:
        """Parse a field (dimension, measure, filter, parameter)."""
        # Handle dimension_group timeframes
        timeframes = []
        datatype = None
        if field_type == FieldType.DIMENSION_GROUP:
            timeframes = data.get("timeframes", [])
            if isinstance(timeframes, str):
                timeframes = [timeframes]
            datatype = data.get("datatype") or data.get("type")

        # Extract drill fields
        drill_fields = []
        if "drill_fields" in data:
            drill_fields = data["drill_fields"]
            if isinstance(drill_fields, str):
                drill_fields = [drill_fields]

        # Extract required fields
        required_fields = []
        if "required_fields" in data:
            required_fields = data["required_fields"]
            if isinstance(required_fields, str):
                required_fields = [required_fields]

        return Field(
            name=data["name"],
            field_type=field_type,
            sql=data.get("sql"),
            type=data.get("type"),
            description=data.get("description"),
            label=data.get("label"),
            hidden=data.get("hidden", False),
            primary_key=data.get("primary_key", False),
            drill_fields=drill_fields,
            view_label=data.get("view_label"),
            group_label=data.get("group_label"),
            source=self._make_source_location(),
            timeframes=timeframes,
            datatype=datatype,
            value_format=data.get("value_format"),
            required_fields=required_fields,
        )

    def _parse_explore(self, data: dict[str, Any]) -> Explore:
        """Parse a LookML explore."""
        joins = []
        if "joins" in data:
            for join_data in data["joins"]:
                joins.append(self._parse_join(join_data))

        # Parse field scoping
        fields = []
        if "fields" in data:
            fields = data["fields"]
            if isinstance(fields, str):
                fields = [fields]

        extends = data.get("extends", [])
        if isinstance(extends, str):
            extends = [extends]

        # Parse filters
        access_filters = data.get("access_filters", [])
        always_filter = data.get("always_filter", {})

        return Explore(
            name=data["name"],
            view_name=data.get("view_name") or data.get("from"),
            joins=joins,
            fields=fields,
            extends=extends,
            hidden=data.get("hidden", False),
            source=self._make_source_location(),
            label=data.get("label"),
            description=data.get("description"),
            group_label=data.get("group_label"),
            access_filters=access_filters,
            always_filter=always_filter,
        )

    def _parse_join(self, data: dict[str, Any]) -> Join:
        """Parse a join in an explore."""
        # Parse join type
        join_type = JoinType.LEFT_OUTER
        if "type" in data:
            try:
                join_type = JoinType(data["type"])
            except ValueError:
                pass  # Use default

        # Parse relationship
        relationship = None
        if "relationship" in data:
            try:
                relationship = JoinRelationship(data["relationship"])
            except ValueError:
                pass

        # Parse required joins
        required_joins = []
        if "required_joins" in data:
            required_joins = data["required_joins"]
            if isinstance(required_joins, str):
                required_joins = [required_joins]

        # Parse field scoping
        fields = []
        if "fields" in data:
            fields = data["fields"]
            if isinstance(fields, str):
                fields = [fields]

        return Join(
            name=data["name"],
            from_view=data.get("from"),
            type=join_type,
            relationship=relationship,
            sql_on=data.get("sql_on"),
            sql_where=data.get("sql_where"),
            foreign_key=data.get("foreign_key"),
            required_joins=required_joins,
            fields=fields,
            source=self._make_source_location(),
        )

    def _parse_constant(self, data: dict[str, Any]) -> Constant:
        """Parse a constant definition."""
        return Constant(
            name=data["name"],
            value=data["value"],
            export=data.get("export"),
            source=self._make_source_location(),
        )

    def _parse_refinement(self, data: dict[str, Any], refinement_type: str) -> Refinement:
        """Parse a refinement (+view or +explore)."""
        return Refinement(
            target_name=data["name"],
            refinement_type=refinement_type,
            properties=data,
            source=self._make_source_location(),
        )

    def extract_field_references(self, sql: Optional[str]) -> list[FieldReference]:
        """Extract all field references from SQL string.

        Handles:
        - ${view.field} - cross-view reference
        - ${field} - local field reference
        - ${TABLE} - table reference (not a field)
        """
        if not sql:
            return []

        references = []
        for match in self.FIELD_REF_PATTERN.finditer(sql):
            ref_text = match.group(1).strip()

            # Skip ${TABLE} - it's not a field reference
            if ref_text == "TABLE":
                continue

            # Parse view.field or field
            parts = ref_text.split(".")
            if len(parts) == 2:
                view_name, field_name = parts
                references.append(
                    FieldReference(
                        view_name=view_name,
                        field_name=field_name,
                        raw_reference=match.group(0),
                        source=self._make_source_location(),
                    )
                )
            elif len(parts) == 1:
                # Local field reference
                references.append(
                    FieldReference(
                        view_name=None,
                        field_name=parts[0],
                        raw_reference=match.group(0),
                        source=self._make_source_location(),
                    )
                )

        return references

    def extract_liquid_variables(self, value: str) -> list[str]:
        """Extract Liquid template variables from a string.

        Handles:
        - {{ variable }}
        - {% if condition %}
        """
        variables = []

        # Extract {{ variable }} patterns
        for match in self.LIQUID_VAR_PATTERN.finditer(value):
            var_name = match.group(1).strip()
            # Remove filters (e.g., {{ var | filter }})
            var_name = var_name.split("|")[0].strip()
            variables.append(var_name)

        # Extract {% tag %} patterns (for conditionals, loops, etc.)
        for match in self.LIQUID_TAG_PATTERN.finditer(value):
            tag_content = match.group(1).strip()
            # Extract variable names from if/unless/for statements
            # e.g., "if condition" -> ["condition"]
            parts = tag_content.split()
            if len(parts) > 1 and parts[0] in ("if", "unless", "elsif", "for"):
                variables.append(parts[1])

        return list(set(variables))

    def _make_source_location(self, line_number: Optional[int] = None) -> SourceLocation:
        """Create a SourceLocation for the current file."""
        return SourceLocation(
            file_path=self._current_file,
            line_number=line_number,
        )


class LookMLProjectParser:
    """Parser for entire LookML projects (directories of .lkml files)."""

    def __init__(self):
        """Initialize project parser."""
        self.parser = LookMLParser()

    def parse_directory(self, directory: Path) -> dict[str, Any]:
        """Parse all LookML files in a directory.

        Returns dict with:
        - views: dict[str, View] - All views by name
        - explores: dict[str, Explore] - All explores by name
        - models: dict[str, Model] - All models by name
        - constants: dict[str, Constant] - All constants by name
        - refinements: list[Refinement] - All refinements
        - dashboards: dict[str, Dashboard] - All dashboards by name
        - files: dict[Path, dict] - Parsed data by file
        """
        result = {
            "views": {},
            "explores": {},
            "models": {},
            "constants": {},
            "refinements": [],
            "dashboards": {},
            "files": {},
        }

        # Find all .lkml files
        lkml_files = list(directory.rglob("*.lkml"))

        for file_path in lkml_files:
            try:
                parsed = self.parser.parse_file(file_path)
                result["files"][file_path] = parsed

                # Merge into global collections
                for view in parsed["views"]:
                    result["views"][view.name] = view

                for explore in parsed["explores"]:
                    result["explores"][explore.name] = explore

                for model in parsed["models"]:
                    result["models"][model.name] = model

                for constant in parsed["constants"]:
                    result["constants"][constant.name] = constant

                result["refinements"].extend(parsed["refinements"])

                # Add dashboards
                for dashboard in parsed.get("dashboards", []):
                    result["dashboards"][dashboard.name] = dashboard

            except Exception as e:
                # Log parsing error but continue with other files
                print(f"Warning: Failed to parse {file_path}: {e}")
                continue

        return result

    def find_view_dependencies(self, view: View) -> set[str]:
        """Find all views that this view depends on (via field references)."""
        dependencies = set()

        # Check extends
        dependencies.update(view.extends)

        # Check field SQL for references
        for field in view.fields:
            if field.sql:
                refs = self.parser.extract_field_references(field.sql)
                for ref in refs:
                    if ref.view_name:
                        dependencies.add(ref.view_name)

        # Check derived table SQL
        if view.derived_table and isinstance(view.derived_table, dict):
            sql = view.derived_table.get("sql")
            if sql:
                refs = self.parser.extract_field_references(sql)
                for ref in refs:
                    if ref.view_name:
                        dependencies.add(ref.view_name)

        return dependencies

    def find_explore_dependencies(self, explore: Explore) -> dict[str, set[str]]:
        """Find all views that this explore depends on.

        Returns dict with:
        - base_view: The explore's base view
        - joined_views: Views referenced in joins
        """
        dependencies = {
            "base_view": explore.get_base_view_name(),
            "joined_views": set(),
        }

        for join in explore.joins:
            dependencies["joined_views"].add(join.name)
            if join.from_view:
                dependencies["joined_views"].add(join.from_view)

        return dependencies
