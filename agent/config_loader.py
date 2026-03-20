"""Config loader for agent.promptforge.yaml.

Reads prompt and skill configuration from YAML, builds the system prompt,
and extracts enabled tool lists.  Falls back gracefully when the file is
missing so the agent can use its legacy hardcoded prompts.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Config file names to search for (in priority order)
_CONFIG_FILENAMES = [
    "agent.promptforge.yaml",
    "agent.promptforge.yml",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_config_file(search_dir: Optional[str] = None) -> Optional[str]:
    """Locate the ``agent.promptforge.yaml`` (or ``.yml``) config file.

    Parameters
    ----------
    search_dir:
        Directory to search in.  Defaults to the repository root, which is
        assumed to be the parent of the ``agent/`` package directory.

    Returns
    -------
    str or None
        Absolute path to the config file, or *None* if not found.
    """
    if search_dir is None:
        # Default: parent of the agent/ package directory (i.e. the repo root)
        search_dir = str(Path(__file__).resolve().parent.parent)

    search_path = Path(search_dir)
    for filename in _CONFIG_FILENAMES:
        candidate = search_path / filename
        if candidate.is_file():
            return str(candidate)

    return None


def load_agent_config(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load the YAML config and return the ``agent`` dict.

    Parameters
    ----------
    path:
        Explicit path to the YAML file.  When *None*, :func:`find_config_file`
        is used to locate it automatically.

    Returns
    -------
    dict or None
        The ``config["agent"]`` dictionary, or *None* when the file is missing
        or cannot be parsed.
    """
    if path is None:
        path = find_config_file()

    if path is None or not Path(path).is_file():
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception:
        logger.exception("Failed to parse YAML config at %s", path)
        return None

    if not isinstance(data, dict) or "agent" not in data:
        logger.warning("YAML config at %s missing 'agent' key", path)
        return None

    return data["agent"]


def build_system_prompt(config: Dict[str, Any], **runtime_vars: Any) -> str:
    """Combine all enabled prompts and skill prompts into a single string.

    * Iterates ``config["prompts"]``: skips entries whose ``depends_on.skills``
      are not a subset of the currently enabled skills.
    * Applies ``value.format(**runtime_vars)`` for variable substitution,
      catching :class:`KeyError` gracefully so unresolved placeholders survive.
    * Iterates ``config["skills"]``: includes the ``prompt`` field for every
      skill with ``enabled: true``.
    * Joins all parts with ``\\n\\n``.

    Parameters
    ----------
    config:
        The ``agent`` dict returned by :func:`load_agent_config`.
    **runtime_vars:
        Variables to substitute into prompt templates (e.g. ``parent_id``).
    """
    enabled_skill_names = _enabled_skill_names(config)
    parts: List[str] = []

    # 1. Prompts
    for prompt_entry in config.get("prompts", []):
        # Check depends_on.skills
        depends_on = prompt_entry.get("depends_on") or {}
        required_skills = set(depends_on.get("skills", []))
        if required_skills and not required_skills.issubset(enabled_skill_names):
            continue

        value = prompt_entry.get("value", "")
        # Variable substitution (graceful on missing keys)
        try:
            value = value.format(**runtime_vars)
        except KeyError:
            # Partial substitution: replace what we can, leave the rest
            import string
            formatter = string.Formatter()
            result_parts = []
            for literal_text, field_name, format_spec, conversion in formatter.parse(value):
                result_parts.append(literal_text)
                if field_name is not None:
                    if field_name in runtime_vars:
                        result_parts.append(str(runtime_vars[field_name]))
                    else:
                        # Reconstruct the original placeholder
                        result_parts.append("{" + field_name + "}")
            value = "".join(result_parts)

        parts.append(value.strip())

    # 2. Skill prompts (enabled only)
    for skill in config.get("skills", []):
        if skill.get("enabled", False) and skill.get("prompt"):
            parts.append(skill["prompt"].strip())

    return "\n\n".join(parts)


def get_enabled_tools(config: Dict[str, Any]) -> List[str]:
    """Return the flat list of tool names from all enabled skills.

    Parameters
    ----------
    config:
        The ``agent`` dict returned by :func:`load_agent_config`.
    """
    tools: List[str] = []
    for skill in config.get("skills", []):
        if skill.get("enabled", False):
            tools.extend(skill.get("tools_dependencies", []))
    return tools


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enabled_skill_names(config: Dict[str, Any]) -> set:
    """Return a set of skill names that are currently enabled."""
    return {
        skill["name"]
        for skill in config.get("skills", [])
        if skill.get("enabled", False)
    }
