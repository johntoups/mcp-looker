"""Dependency mapping and analysis functionality.

Updated to use LookMLProject for better parsing and graph capabilities.
"""

import json
from pathlib import Path
from typing import Any

import networkx as nx
from rich.console import Console
from rich.tree import Tree

from ..utils.lookml_project import LookMLProject

console = Console()


def qualify_node_name(graph: nx.DiGraph, node_name: str) -> str | None:
    """
    Convert a node name to qualified format (type.name).

    Handles both qualified ('view.name') and unqualified ('name') inputs.

    Args:
        graph: Dependency graph with qualified node names
        node_name: Either 'name' or 'type.name'

    Returns:
        Qualified name ('type.name'), or None if not found
    """
    # Already qualified and exists
    if node_name in graph:
        return node_name

    # Try prefixing with 'view.'
    qualified_view = f"view.{node_name}"
    if qualified_view in graph:
        return qualified_view

    # Try prefixing with 'explore.'
    qualified_explore = f"explore.{node_name}"
    if qualified_explore in graph:
        return qualified_explore

    return None


def build_dependency_graph(
    project_dir: Path, include_fields: bool = False, use_cache: bool = True
) -> nx.DiGraph:
    """
    Build a directed graph of LookML dependencies using enhanced parser.

    Args:
        project_dir: Path to the LookML project directory
        include_fields: If True, include field-level nodes in the graph
        use_cache: If True, use pickle cache for incremental parsing

    Returns:
        NetworkX directed graph with nodes for views/explores (and optionally fields)
    """
    console.print("\n[bold]Building dependency graph...[/bold]\n")

    # Use LookMLProject to parse and build graph
    project = LookMLProject(
        project_dir, include_fields=include_fields, use_cache=use_cache, console=console
    )

    console.print(
        f"  [green]✓[/green] Loaded {len(project.views)} views\n"
        f"  [green]✓[/green] Loaded {len(project.explores)} explores\n"
        f"  [green]✓[/green] Loaded {len(project.models)} models\n"
        f"  [green]✓[/green] Loaded {len(project.dashboards)} dashboards\n"
    )

    if include_fields:
        field_nodes = [
            n
            for n in project.graph.nodes()
            if project.graph.nodes[n].get("type") in ["field", "explore_field"]
        ]
        console.print(f"  [green]✓[/green] Loaded {len(field_nodes)} field nodes\n")

    return project.graph


def find_dependents(graph: nx.DiGraph, node: str) -> list[str]:
    """
    Find all nodes that depend on the given node.

    Args:
        graph: Dependency graph
        node: Node to find dependents for

    Returns:
        List of dependent node names
    """
    if node not in graph:
        return []

    return list(graph.predecessors(node))


def find_dependencies(graph: nx.DiGraph, node: str) -> list[str]:
    """
    Find all nodes that the given node depends on.

    Args:
        graph: Dependency graph
        node: Node to find dependencies for

    Returns:
        List of dependency node names
    """
    if node not in graph:
        return []

    return list(graph.successors(node))


def find_circular_dependencies(graph: nx.DiGraph) -> list[list[str]]:
    """
    Find circular dependencies in the graph.

    Args:
        graph: Dependency graph

    Returns:
        List of cycles (each cycle is a list of node names)
    """
    try:
        cycles = list(nx.simple_cycles(graph))
        return cycles
    except nx.NetworkXNoCycle:
        return []


def get_dependency_tree(graph: nx.DiGraph, node: str, max_depth: int = 5) -> dict[str, Any]:
    """
    Get dependency tree for a node.

    Args:
        graph: Dependency graph
        node: Root node
        max_depth: Maximum depth to traverse

    Returns:
        Nested dictionary representing the dependency tree
    """
    if node not in graph or max_depth == 0:
        return {}

    tree = {"node": node, "type": graph.nodes[node].get("type", "unknown"), "dependencies": []}

    for dep in graph.successors(node):
        subtree = get_dependency_tree(graph, dep, max_depth - 1)
        tree["dependencies"].append(subtree)

    return tree


def print_dependency_tree(graph: nx.DiGraph, node: str, max_depth: int = 5) -> None:
    """
    Print a dependency tree in a readable format.

    Args:
        graph: Dependency graph
        node: Root node (accepts 'name' or 'type.name')
        max_depth: Maximum depth to traverse
    """
    # Qualify the node name
    qualified_node = qualify_node_name(graph, node)
    if not qualified_node:
        console.print(f"[red]Error:[/red] Node '{node}' not found in graph")
        console.print("[dim]Hint: Use 'view.name' or 'explore.name' format, or just 'name'[/dim]")
        return

    node = qualified_node
    tree = Tree(f"[cyan]{node}[/cyan] ({graph.nodes[node].get('type', 'unknown')})")

    def add_branches(parent_tree: Tree, current_node: str, depth: int, visited: set) -> None:
        if depth == 0 or current_node in visited:
            return

        visited.add(current_node)

        for dep in graph.successors(current_node):
            node_type = graph.nodes[dep].get("type", "unknown")
            edge_relation = graph.edges.get((current_node, dep), {}).get("relation", "")
            label = f"[cyan]{dep}[/cyan] ({node_type})"
            if edge_relation:
                label += f" [{edge_relation}]"
            branch = parent_tree.add(label)
            add_branches(branch, dep, depth - 1, visited)

    add_branches(tree, node, max_depth, set())
    console.print(tree)


def analyze_impact(graph: nx.DiGraph, node: str) -> dict[str, Any]:
    """
    Analyze the impact of changing/removing a node.

    Args:
        graph: Dependency graph
        node: Node to analyze (accepts 'name' or 'type.name')

    Returns:
        Dictionary with impact analysis
    """
    # Qualify the node name
    qualified_node = qualify_node_name(graph, node)
    if not qualified_node:
        return {"error": f"Node '{node}' not found in graph"}

    node = qualified_node

    # Find all nodes that would be affected (using NetworkX ancestors - all reachable predecessors)
    affected = nx.ancestors(graph, node)

    # Separate explores and views
    affected_explores = [n for n in affected if graph.nodes[n].get("type") == "explore"]
    affected_views = [n for n in affected if graph.nodes[n].get("type") == "view"]

    # Direct dependents
    direct_dependents = list(graph.predecessors(node))

    return {
        "node": node,
        "total_affected": len(affected),
        "affected_explores": affected_explores,
        "affected_views": affected_views,
        "direct_dependents": direct_dependents,
    }


def print_impact_analysis(analysis: dict[str, Any]) -> None:
    """
    Print impact analysis in a readable format.

    Args:
        analysis: Analysis results from analyze_impact
    """
    if "error" in analysis:
        console.print(f"[red]Error:[/red] {analysis['error']}")
        return

    console.print(f"\n[bold]Impact Analysis for: [cyan]{analysis['node']}[/cyan][/bold]\n")
    console.print(f"Total nodes affected: {analysis['total_affected']}")

    if analysis["direct_dependents"]:
        console.print(f"\nDirect dependents ({len(analysis['direct_dependents'])}):")
        for dep in analysis["direct_dependents"]:
            console.print(f"  • {dep}")

    if analysis["affected_explores"]:
        console.print(f"\nAffected explores ({len(analysis['affected_explores'])}):")
        for explore in analysis["affected_explores"][:10]:
            console.print(f"  • {explore}")
        if len(analysis["affected_explores"]) > 10:
            console.print(f"  ... and {len(analysis['affected_explores']) - 10} more")

    if analysis["affected_views"]:
        console.print(f"\nAffected views ({len(analysis['affected_views'])}):")
        for view in analysis["affected_views"][:10]:
            console.print(f"  • {view}")
        if len(analysis["affected_views"]) > 10:
            console.print(f"  ... and {len(analysis['affected_views']) - 10} more")


def get_orphaned_views(graph: nx.DiGraph) -> list[str]:
    """
    Find views that are not used by any explores.

    Args:
        graph: Dependency graph

    Returns:
        List of orphaned view names
    """
    orphaned = []

    for node in graph.nodes():
        if graph.nodes[node].get("type") == "view":
            # Check if any explores depend on this view
            has_explore_dependent = any(
                graph.nodes[dep].get("type") == "explore" for dep in graph.predecessors(node)
            )

            if not has_explore_dependent:
                orphaned.append(node)

    return orphaned


def export_dependency_graph(graph: nx.DiGraph, output_file: Path, format: str = "json") -> None:
    """
    Export dependency graph to a file.

    Args:
        graph: Dependency graph
        output_file: Output file path
        format: Export format ('json' or 'dot')
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if format == "json":
        # Convert to JSON-serializable format
        data = {
            "nodes": [{"id": node, **graph.nodes[node]} for node in graph.nodes()],
            "edges": [
                {
                    "source": source,
                    "target": target,
                    **graph.edges[source, target],
                }
                for source, target in graph.edges()
            ],
        }
        output_file.write_text(json.dumps(data, indent=2))

    elif format == "dot":
        # Export as GraphViz DOT format
        from networkx.drawing.nx_pydot import write_dot

        write_dot(graph, str(output_file))

    console.print(f"\n[green]✓[/green] Exported dependency graph to {output_file}")


def get_statistics(graph: nx.DiGraph) -> dict[str, Any]:
    """
    Get statistics about the dependency graph.

    Args:
        graph: Dependency graph

    Returns:
        Dictionary with graph statistics
    """
    views = [n for n in graph.nodes() if graph.nodes[n].get("type") == "view"]
    explores = [n for n in graph.nodes() if graph.nodes[n].get("type") == "explore"]
    dashboards = [n for n in graph.nodes() if graph.nodes[n].get("type") == "dashboard"]

    return {
        "total_nodes": graph.number_of_nodes(),
        "total_edges": graph.number_of_edges(),
        "total_views": len(views),
        "total_explores": len(explores),
        "total_dashboards": len(dashboards),
        "avg_dependencies": (
            sum(graph.out_degree(n) for n in graph.nodes()) / graph.number_of_nodes()
            if graph.number_of_nodes() > 0
            else 0
        ),
        "avg_dependents": (
            sum(graph.in_degree(n) for n in graph.nodes()) / graph.number_of_nodes()
            if graph.number_of_nodes() > 0
            else 0
        ),
    }
