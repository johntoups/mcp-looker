"""Looker SDK CLI Suite for managing and analyzing Looker instances."""

__version__ = "0.1.0"

# Register cattrs structure hook for str | bytes - needed for SDK's run_query.
# The Looker SDK declares run_query returns Union[str, bytes] but doesn't
# register a cattrs handler for this type. This patches the SDK's converter.
from types import UnionType
from typing import Any, Union, get_args

from looker_sdk.rtl import serialize as _sr


def _is_str_bytes_union(t: Any) -> bool:
    """Check if type is Union[str, bytes] or str | bytes."""
    if isinstance(t, UnionType):
        return set(get_args(t)) == {str, bytes}
    origin = getattr(t, "__origin__", None)
    if origin is Union:
        return set(get_args(t)) == {str, bytes}
    return False


def _str_bytes_passthrough(data: Any, _type: Any) -> str | bytes:
    """Pass through str/bytes unchanged - no structuring needed."""
    return data


_sr.converter40.register_structure_hook_func(_is_str_bytes_union, _str_bytes_passthrough)
