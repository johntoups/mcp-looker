"""Session and workspace management functionality.

WORKSPACE SAFETY NOTES:
- Looker has two workspaces: 'production' and 'dev'
- Workspace preference is persisted to .looker_session.json (defaults to 'dev')
- Any function that MODIFIES project state MUST ensure dev workspace first
- This module provides get_current_workspace() and switch_to_workspace() helpers
- All modification functions in this module already handle workspace switching
"""

from typing import Any

from looker_sdk.sdk.api40 import models
from rich.console import Console

from lookerctl.core.client import LookerClient
from lookerctl.core.session_storage import save_session
from lookerctl.utils.git import get_current_branch

console = Console()


def get_current_workspace(client: LookerClient) -> str:
    """
    Get the current workspace (production or dev).

    Args:
        client: Looker client instance

    Returns:
        Current workspace ID
    """
    session = client.get_session()
    return session.workspace_id or "production"


def switch_to_workspace(client: LookerClient, workspace: str) -> dict[str, Any]:
    """
    Switch to a different workspace and persist the preference.

    Args:
        client: Looker client instance
        workspace: Workspace ID ('production' or 'dev')

    Returns:
        Result dictionary with success status
    """
    result = {"success": False, "workspace": workspace}

    try:
        # Update session to switch workspace
        client.sdk.update_session(body=models.WriteApiSession(workspace_id=workspace))

        # Verify the switch
        curr_session = client.get_session()
        if curr_session.workspace_id == workspace:
            result["success"] = True
            console.print(f"[green]✓[/green] Switched to {workspace} workspace")

            # Persist the workspace preference
            save_session(workspace)
            console.print(
                "[dim]Workspace preference saved (will persist across CLI invocations)[/dim]"
            )
        else:
            console.print(f"[red]✗[/red] Failed to switch to {workspace} workspace")

    except Exception as e:
        result["error"] = str(e)
        console.print(f"[red]Error:[/red] {e}")

    return result


def checkout_git_branch(client: LookerClient, project_id: str, branch: str) -> dict[str, Any]:
    """
    Checkout a git branch in a Looker project.

    Args:
        client: Looker client instance
        project_id: Project ID
        branch: Git branch name

    Returns:
        Result dictionary with success status
    """
    result = {"success": False, "branch": branch, "project_id": project_id}

    try:
        # First, make sure we're in dev workspace
        current_workspace = get_current_workspace(client)
        if current_workspace != "dev":
            console.print("[yellow]Switching to dev workspace first...[/yellow]")
            switch_result = switch_to_workspace(client, "dev")
            if not switch_result["success"]:
                result["error"] = "Failed to switch to dev workspace"
                return result

        # Update the project's git branch
        console.print(f"Checking out branch '{branch}' in project '{project_id}'...")
        client.sdk.update_git_branch(project_id, body=models.WriteGitBranch(name=branch))

        # Verify the checkout
        git_branch_info = client.sdk.git_branch(project_id)
        current_branch = git_branch_info.name if git_branch_info else None

        if current_branch == branch:
            result["success"] = True
            console.print(f"[green]✓[/green] Checked out branch '{branch}'")
        else:
            console.print(
                f"[yellow]Warning:[/yellow] Expected branch '{branch}', "
                f"but project is on '{current_branch}'"
            )

    except Exception as e:
        result["error"] = str(e)
        console.print(f"[red]Error:[/red] {e}")

    return result


def sync_with_local_git(client: LookerClient, project_id: str) -> dict[str, Any]:
    """
    Sync Looker project branch with local git repository branch.

    This will:
    1. Detect the current git branch in the local repository
    2. Switch to dev workspace
    3. Checkout the corresponding branch in Looker
    4. Reset to remote to pull the latest commits

    Args:
        client: Looker client instance
        project_id: Project ID

    Returns:
        Result dictionary with success status
    """
    result = {
        "success": False,
        "local_branch": None,
        "looker_branch": None,
        "project_id": project_id,
    }

    try:
        # Get local git branch
        local_branch = get_current_branch()
        if not local_branch:
            result["error"] = "Not in a git repository or unable to detect branch"
            console.print(f"[red]Error:[/red] {result['error']}")
            return result

        result["local_branch"] = local_branch
        console.print(f"Local git branch: [cyan]{local_branch}[/cyan]")

        # Checkout the branch in Looker
        checkout_result = checkout_git_branch(client, project_id, local_branch)

        if checkout_result["success"]:
            # Reset to remote to pull latest commits
            console.print("[dim]Pulling latest commits from remote...[/dim]")
            reset_result = reset_to_remote(client, project_id)

            if reset_result["success"]:
                result["success"] = True
                result["looker_branch"] = local_branch

                # Show commit info
                git_status = get_project_git_status(client, project_id)
                if "commit_sha" in git_status:
                    console.print(
                        f"[green]✓[/green] Synced to commit: [cyan]{git_status['commit_sha'][:7]}[/cyan]"
                    )
            else:
                result["error"] = reset_result.get("error", "Failed to reset to remote")
                console.print(
                    "[yellow]Warning:[/yellow] Branch checked out but failed to pull from remote"
                )

    except Exception as e:
        result["error"] = str(e)
        console.print(f"[red]Error:[/red] {e}")

    return result


def get_project_git_status(client: LookerClient, project_id: str) -> dict[str, Any]:
    """
    Get comprehensive git status for a Looker project.

    Args:
        client: Looker client instance
        project_id: Project ID

    Returns:
        Dictionary with git status information including:
        - branch name
        - commit SHA
        - ahead/behind counts
        - remote URL
        - workspace info
    """
    try:
        project = client.get_project(project_id)

        # Get current workspace
        current_workspace = get_current_workspace(client)

        # Get detailed git branch info
        try:
            git_branch_info = client.sdk.git_branch(project_id)
            current_branch = git_branch_info.name if git_branch_info else "unknown"

            # Extract all available git info
            status = {
                "project_id": project_id,
                "project_name": project.name,
                "workspace": current_workspace,
                "git_remote_url": project.git_remote_url,
                "git_branch": current_branch,
                "git_production_branch": project.git_production_branch_name,
                "is_production_branch": current_branch == project.git_production_branch_name,
            }

            # Add commit SHA if available
            if hasattr(git_branch_info, "ref") and git_branch_info.ref:
                status["commit_sha"] = git_branch_info.ref

            # Add ahead/behind counts if available
            if hasattr(git_branch_info, "ahead_count"):
                status["ahead_count"] = git_branch_info.ahead_count
            if hasattr(git_branch_info, "behind_count"):
                status["behind_count"] = git_branch_info.behind_count

            # Add remote info
            if hasattr(git_branch_info, "remote"):
                status["remote_name"] = git_branch_info.remote
            if hasattr(git_branch_info, "remote_name"):
                status["remote_branch"] = git_branch_info.remote_name

        except Exception as e:
            status = {
                "project_id": project_id,
                "project_name": project.name,
                "workspace": current_workspace,
                "git_remote_url": project.git_remote_url,
                "git_branch": "unknown",
                "error": f"Failed to get git branch info: {str(e)}",
            }

        return status

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return {"error": str(e)}


def create_dev_branch(
    client: LookerClient, project_id: str, branch_name: str, from_branch: str | None = None
) -> dict[str, Any]:
    """
    Create a new development branch in a Looker project.

    Args:
        client: Looker client instance
        project_id: Project ID
        branch_name: Name for the new branch
        from_branch: Branch to create from (defaults to production branch)

    Returns:
        Result dictionary with success status
    """
    result = {
        "success": False,
        "branch_name": branch_name,
        "project_id": project_id,
    }

    try:
        # Make sure we're in dev workspace
        current_workspace = get_current_workspace(client)
        if current_workspace != "dev":
            console.print("[yellow]Switching to dev workspace first...[/yellow]")
            switch_result = switch_to_workspace(client, "dev")
            if not switch_result["success"]:
                result["error"] = "Failed to switch to dev workspace"
                return result

        # If no from_branch specified, use production branch
        if not from_branch:
            project = client.get_project(project_id)
            from_branch = project.git_production_branch_name or "main"

        console.print(
            f"Creating branch '{branch_name}' from '{from_branch}' in project '{project_id}'..."
        )

        # Create the branch
        client.sdk.create_git_branch(
            project_id, body=models.WriteGitBranch(name=branch_name, ref=from_branch)
        )

        # Checkout the new branch
        checkout_result = checkout_git_branch(client, project_id, branch_name)

        if checkout_result["success"]:
            result["success"] = True
            console.print(f"[green]✓[/green] Created and checked out branch '{branch_name}'")

    except Exception as e:
        result["error"] = str(e)
        console.print(f"[red]Error:[/red] {e}")

    return result


def reset_to_remote(client: LookerClient, project_id: str) -> dict[str, Any]:
    """
    Hard reset Looker project to match git remote.

    This discards any local changes in the dev workspace and pulls the latest
    commit from the git remote for the current branch. Use this when Looker
    shows stale schema despite git branch being updated.

    Args:
        client: Looker client instance
        project_id: Project ID

    Returns:
        Result dictionary with success status
    """
    result = {"success": False, "project_id": project_id}

    try:
        # Must be in dev workspace to reset
        current_workspace = get_current_workspace(client)
        if current_workspace != "dev":
            console.print("[yellow]Switching to dev workspace first...[/yellow]")
            switch_result = switch_to_workspace(client, "dev")
            if not switch_result["success"]:
                result["error"] = "Failed to switch to dev workspace"
                return result

        # Get current branch info before reset
        git_status = get_project_git_status(client, project_id)
        current_branch = git_status.get("git_branch", "unknown")

        console.print(
            f"[yellow]Warning:[/yellow] Resetting project '{project_id}' "
            f"branch '{current_branch}' to remote state..."
        )
        console.print("[dim]This will discard any local changes in dev workspace[/dim]")

        # Reset to remote
        response = client.sdk.reset_project_to_remote(project_id)

        result["success"] = True
        result["branch"] = current_branch
        result["message"] = response
        console.print("[green]✓[/green] Reset to remote completed")
        console.print(f"[dim]Response: {response}[/dim]")

    except Exception as e:
        result["error"] = str(e)
        console.print(f"[red]Error:[/red] {e}")

    return result
