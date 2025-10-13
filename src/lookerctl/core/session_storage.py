"""Persistent session storage for workspace preferences."""

import json
from pathlib import Path
from typing import Any


def get_session_file_path() -> Path:
    """Get the path to the session storage file."""
    # Store in the project root directory
    return Path.cwd() / ".looker_session.json"


def load_session() -> dict[str, Any]:
    """
    Load session preferences from disk.

    Returns:
        Dictionary with session preferences (workspace, etc.)
    """
    session_file = get_session_file_path()

    if not session_file.exists():
        # Return default preferences - dev workspace to avoid accidental production changes
        return {"workspace": "dev"}

    try:
        return json.loads(session_file.read_text())
    except Exception:
        # If file is corrupted, return default
        return {"workspace": "dev"}


def save_session(workspace: str) -> None:
    """
    Save session preferences to disk.

    Args:
        workspace: Workspace ID to persist ('production' or 'dev')
    """
    session_file = get_session_file_path()

    session_data = {"workspace": workspace}

    try:
        session_file.write_text(json.dumps(session_data, indent=2))
    except Exception:
        # Silently fail if we can't write - not critical
        pass


def get_preferred_workspace() -> str:
    """
    Get the user's preferred workspace from storage.

    Returns:
        Workspace ID ('production' or 'dev'), defaults to 'dev' for safety
    """
    session = load_session()
    return session.get("workspace", "dev")
