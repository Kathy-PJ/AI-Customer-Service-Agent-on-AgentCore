"""Tests for agent.config_loader — TDD: written before the implementation."""

import os
import tempfile
import textwrap

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONFIG_YAML = textwrap.dedent("""\
    agent:
      name: test-agent
      description: A test agent
      prompts:
        - name: system_prompt
          type: system
          value: |
            You are a helpful assistant.
        - name: session_context
          type: system
          variables: [parent_id]
          value: |
            Current user: {parent_id}
        - name: memory_guidance
          type: system
          depends_on:
            skills: [memory_search]
          value: |
            Use memory tools to recall user history.
      skills:
        - name: knowledge_search
          enabled: true
          description: FAQ search
          prompt: |
            Search the FAQ knowledge base.
          tools_dependencies:
            - search_faq
        - name: memory_search
          enabled: false
          description: Memory recall
          prompt: |
            Recall user preferences.
          tools_dependencies:
            - search_user_preferences
            - search_episodic_memories
        - name: booking
          enabled: true
          description: Booking ops
          prompt: |
            Handle booking operations.
          tools_dependencies:
            - book_item
            - cancel_item
""")


@pytest.fixture
def sample_yaml_path(tmp_path):
    """Write the sample YAML to a temp file and return its path."""
    p = tmp_path / "agent.promptforge.yaml"
    p.write_text(SAMPLE_CONFIG_YAML)
    return str(p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadConfig:
    """Tests for load_agent_config."""

    def test_load_config_from_yaml(self, sample_yaml_path):
        from agent.config_loader import load_agent_config

        config = load_agent_config(path=sample_yaml_path)
        assert config is not None
        assert config["name"] == "test-agent"
        assert "prompts" in config
        assert "skills" in config
        assert len(config["prompts"]) == 3
        assert len(config["skills"]) == 3

    def test_load_config_returns_none_when_missing(self, tmp_path):
        from agent.config_loader import load_agent_config

        # Point to a directory with no YAML file
        fake_path = str(tmp_path / "nonexistent.yaml")
        config = load_agent_config(path=fake_path)
        assert config is None


class TestBuildSystemPrompt:
    """Tests for build_system_prompt."""

    def _load_config(self, yaml_path):
        from agent.config_loader import load_agent_config
        return load_agent_config(path=yaml_path)

    def test_build_system_prompt_includes_enabled_skills(self, sample_yaml_path):
        from agent.config_loader import build_system_prompt

        config = self._load_config(sample_yaml_path)
        prompt = build_system_prompt(config, parent_id="p123")

        # Enabled skill "knowledge_search" prompt should be included
        assert "Search the FAQ knowledge base." in prompt
        # Enabled skill "booking" prompt should be included
        assert "Handle booking operations." in prompt
        # Disabled skill "memory_search" prompt should NOT be included
        assert "Recall user preferences." not in prompt

    def test_build_system_prompt_respects_depends_on(self, sample_yaml_path):
        from agent.config_loader import build_system_prompt

        config = self._load_config(sample_yaml_path)
        prompt = build_system_prompt(config, parent_id="p123")

        # memory_guidance depends on memory_search which is disabled
        assert "Use memory tools to recall user history." not in prompt

        # Now enable memory_search and rebuild
        for skill in config["skills"]:
            if skill["name"] == "memory_search":
                skill["enabled"] = True
        prompt2 = build_system_prompt(config, parent_id="p123")
        assert "Use memory tools to recall user history." in prompt2

    def test_build_system_prompt_substitutes_variables(self, sample_yaml_path):
        from agent.config_loader import build_system_prompt

        config = self._load_config(sample_yaml_path)
        prompt = build_system_prompt(config, parent_id="parent_42")

        assert "parent_42" in prompt
        # The raw placeholder should NOT be present
        assert "{parent_id}" not in prompt

    def test_build_system_prompt_graceful_missing_variable(self, sample_yaml_path):
        """If a variable placeholder cannot be resolved, it stays as-is."""
        from agent.config_loader import build_system_prompt

        config = self._load_config(sample_yaml_path)
        # Do NOT pass parent_id — the {parent_id} placeholder should survive
        prompt = build_system_prompt(config)
        assert "{parent_id}" in prompt


class TestGetEnabledTools:
    """Tests for get_enabled_tools."""

    def test_get_enabled_tools(self, sample_yaml_path):
        from agent.config_loader import load_agent_config, get_enabled_tools

        config = load_agent_config(path=sample_yaml_path)
        tools = get_enabled_tools(config)

        # knowledge_search (enabled) -> search_faq
        assert "search_faq" in tools
        # booking (enabled) -> book_item, cancel_item
        assert "book_item" in tools
        assert "cancel_item" in tools
        # memory_search (disabled) -> should NOT appear
        assert "search_user_preferences" not in tools
        assert "search_episodic_memories" not in tools
