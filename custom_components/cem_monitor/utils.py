from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def get_int(d: dict[str, Any], *keys: str) -> Optional[int]:
    """
    Extract integer value from dict using multiple possible keys.
    
    Args:
        d: Dictionary to search
        *keys: Variable number of key names to try in order
        
    Returns:
        First valid integer value found, or None if none found
    """
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return int(d[k])
            except Exception:
                pass
    return None


def get_str(d: dict[str, Any], *keys: str) -> Optional[str]:
    """
    Extract string value from dict using multiple possible keys.
    
    Args:
        d: Dictionary to search
        *keys: Variable number of key names to try in order
        
    Returns:
        First non-empty stripped string value found, or None if none found
    """
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def get_str_nonempty(*vals: Optional[str]) -> Optional[str]:
    """
    Return first non-empty string from values (not from a dict).
    
    Args:
        *vals: Variable number of string values to check
        
    Returns:
        First non-empty stripped string value found, or None if none found
    """
    for v in vals:
        if isinstance(v, str):
            s = v.strip()
            if s:
                return s
    return None


def slug_int(v: Optional[int]) -> str:
    """
    Convert integer to slug string.
    
    Args:
        v: Integer value to convert
        
    Returns:
        String representation of integer, or "unknown" if None
    """
    return str(v) if v is not None else "unknown"


def slug_text(s: Optional[str]) -> str:
    """
    Convert text to slug format (lowercase, alphanumeric + underscores).
    
    Args:
        s: String to convert
        
    Returns:
        Slugified string, or "unknown" if input is empty/None
    """
    if not isinstance(s, str) or not s.strip():
        return "unknown"
    out = []
    for ch in s.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", ".", "/"):
            out.append("_")
        else:
            out.append("_")
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_") or "unknown"


def ms_to_iso(ms: Any) -> Optional[str]:
    """
    Convert milliseconds timestamp to ISO format string.
    
    Args:
        ms: Milliseconds timestamp (int, string, or None)
        
    Returns:
        ISO format datetime string, or None if invalid/None/empty/0
    """
    try:
        if ms is None or ms == "" or ms == 0:
            return None
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None



