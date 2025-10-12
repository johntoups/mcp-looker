"""Configuration utilities for Looker CLI."""

import os
from pathlib import Path


def get_project_root() -> Path:
    """
    Get the project root directory (where .git directory exists).

    Returns:
        Path to project root

    Raises:
        RuntimeError: If not in a git repository
    """
    current = Path.cwd()

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    raise RuntimeError("Not in a git repository")


def get_lookml_dirs() -> dict[str, Path]:
    """
    Get standard LookML directories in the project.

    Returns:
        Dictionary with keys: 'explores', 'views', 'dashboards', 'root'
    """
    root = get_project_root()

    return {
        "root": root,
        "explores": root / "explores",
        "views": root / "views",
        "dashboards": root / "dashboards",
    }


def verify_env_vars() -> None:
    """
    Verify required LOOKERSDK_* environment variables are set.

    Raises:
        RuntimeError: If required env vars are missing
    """
    required = ["LOOKERSDK_BASE_URL", "LOOKERSDK_CLIENT_ID", "LOOKERSDK_CLIENT_SECRET"]
    missing = [var for var in required if not os.getenv(var)]

    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Make sure to source .env file: source .env"
        )
