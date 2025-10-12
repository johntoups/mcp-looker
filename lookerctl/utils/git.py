"""Git integration utilities."""

from pathlib import Path

import git
from git import Repo


def get_current_branch(repo_path: Path | None = None) -> str | None:
    """
    Get the current git branch name.

    Args:
        repo_path: Path to git repository (defaults to current directory)

    Returns:
        Current branch name or None if not in a git repository
    """
    try:
        if repo_path is None:
            repo_path = Path.cwd()

        repo = Repo(repo_path, search_parent_directories=True)
        return repo.active_branch.name

    except (git.InvalidGitRepositoryError, git.GitCommandError):
        return None


def get_repo_root(start_path: Path | None = None) -> Path | None:
    """
    Get the root directory of the git repository.

    Args:
        start_path: Path to start searching from (defaults to current directory)

    Returns:
        Path to repository root or None if not in a git repository
    """
    try:
        if start_path is None:
            start_path = Path.cwd()

        repo = Repo(start_path, search_parent_directories=True)
        return Path(repo.working_dir)

    except (git.InvalidGitRepositoryError, git.GitCommandError):
        return None


def get_remote_url(repo_path: Path | None = None) -> str | None:
    """
    Get the remote URL for the git repository.

    Args:
        repo_path: Path to git repository (defaults to current directory)

    Returns:
        Remote URL or None if not configured
    """
    try:
        if repo_path is None:
            repo_path = Path.cwd()

        repo = Repo(repo_path, search_parent_directories=True)

        if repo.remotes:
            return repo.remotes.origin.url

        return None

    except (git.InvalidGitRepositoryError, git.GitCommandError, AttributeError):
        return None


def is_clean_working_tree(repo_path: Path | None = None) -> bool:
    """
    Check if the working tree is clean (no uncommitted changes).

    Args:
        repo_path: Path to git repository (defaults to current directory)

    Returns:
        True if working tree is clean, False otherwise
    """
    try:
        if repo_path is None:
            repo_path = Path.cwd()

        repo = Repo(repo_path, search_parent_directories=True)
        return not repo.is_dirty()

    except (git.InvalidGitRepositoryError, git.GitCommandError):
        return False


def get_changed_files(repo_path: Path | None = None) -> list[str]:
    """
    Get list of changed files in the working tree.

    Args:
        repo_path: Path to git repository (defaults to current directory)

    Returns:
        List of changed file paths
    """
    try:
        if repo_path is None:
            repo_path = Path.cwd()

        repo = Repo(repo_path, search_parent_directories=True)

        # Get both staged and unstaged changes
        changed = []

        # Unstaged changes
        changed.extend([item.a_path for item in repo.index.diff(None)])

        # Staged changes
        changed.extend([item.a_path for item in repo.index.diff("HEAD")])

        # Untracked files
        changed.extend(repo.untracked_files)

        return list(set(changed))

    except (git.InvalidGitRepositoryError, git.GitCommandError):
        return []


def get_commits_ahead_behind(
    repo_path: Path | None = None, remote: str = "origin"
) -> tuple[int, int]:
    """
    Get number of commits ahead and behind the remote branch.

    Args:
        repo_path: Path to git repository (defaults to current directory)
        remote: Remote name (defaults to 'origin')

    Returns:
        Tuple of (commits_ahead, commits_behind)
    """
    try:
        if repo_path is None:
            repo_path = Path.cwd()

        repo = Repo(repo_path, search_parent_directories=True)

        current_branch = repo.active_branch
        remote_branch = f"{remote}/{current_branch.name}"

        # Get commits ahead and behind
        ahead = list(repo.iter_commits(f"{remote_branch}..{current_branch.name}"))
        behind = list(repo.iter_commits(f"{current_branch.name}..{remote_branch}"))

        return len(ahead), len(behind)

    except (git.InvalidGitRepositoryError, git.GitCommandError, AttributeError):
        return 0, 0


def list_branches(repo_path: Path | None = None, remote: bool = False) -> list[str]:
    """
    List all branches in the repository.

    Args:
        repo_path: Path to git repository (defaults to current directory)
        remote: If True, list remote branches instead of local

    Returns:
        List of branch names
    """
    try:
        if repo_path is None:
            repo_path = Path.cwd()

        repo = Repo(repo_path, search_parent_directories=True)

        if remote:
            branches = []
            for ref in repo.remotes.origin.refs:
                # Skip HEAD reference
                if ref.name != "origin/HEAD":
                    branches.append(ref.name.replace("origin/", ""))
            return branches
        else:
            return [branch.name for branch in repo.branches]

    except (git.InvalidGitRepositoryError, git.GitCommandError, AttributeError):
        return []
