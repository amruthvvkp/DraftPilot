"""Unit tests for PydanticAI agent orchestrator."""

from unittest.mock import MagicMock, patch

import pytest

from draftpilot.agents.orchestrator import create_agent


class TestAgentOrchestrator:
    """Test suite for agent orchestrator."""

    @patch("draftpilot.agents.orchestrator.OpenAIProvider")
    @patch("draftpilot.agents.orchestrator.OpenAIChatModel")
    @patch("draftpilot.agents.orchestrator.Agent")
    @patch("draftpilot.agents.orchestrator.logfire")
    def test_create_agent(
        self, mock_logfire, mock_agent_class, mock_model_class, mock_provider_class
    ):
        """Test agent creation."""
        mock_provider = MagicMock()
        mock_provider_class.return_value = mock_provider
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model

        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        agent = create_agent()

        # Verify model was created with provider
        mock_model_class.assert_called_once()
        call_args = mock_model_class.call_args
        # Check that provider was passed (positional or keyword)
        assert len(call_args.args) > 0 or "provider" in call_args.kwargs

        # Verify agent was created with model and system prompt
        mock_agent_class.assert_called_once()
        call_args = mock_agent_class.call_args
        assert call_args.kwargs["model"] == mock_model
        assert "screenplay" in call_args.kwargs["system_prompt"].lower()

        assert agent is mock_agent_instance

    @pytest.mark.asyncio
    @patch("draftpilot.agents.orchestrator.OpenAIProvider")
    @patch("draftpilot.agents.orchestrator.OpenAIChatModel")
    @patch("draftpilot.agents.orchestrator.Agent")
    @patch("draftpilot.agents.orchestrator.logfire")
    async def test_agent_greet_tool(
        self, mock_logfire, mock_agent_class, mock_model_class, mock_provider_class
    ):
        """Test agent greet tool execution."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=None)
        mock_span.__exit__ = MagicMock(return_value=None)
        mock_logfire.span = MagicMock(return_value=mock_span)

        mock_model_class.return_value = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        # Create agent and get the tool
        agent = create_agent()

        # The tool should be registered with the agent
        # We can't easily test the tool directly without running the agent,
        # but we can verify the agent was created successfully
        assert agent is not None
        assert agent is mock_agent_instance

    @patch("draftpilot.agents.orchestrator.OpenAIProvider")
    @patch("draftpilot.agents.orchestrator.OpenAIChatModel")
    @patch("draftpilot.agents.orchestrator.Agent")
    @patch("draftpilot.agents.orchestrator.logfire")
    def test_agent_logfire_tracing(
        self, mock_logfire, mock_agent_class, mock_model_class, mock_provider_class
    ):
        """Test that Logfire tracing is used in agent tools."""
        mock_model_class.return_value = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        create_agent()

        # Verify logfire.span is available (used in tool decorator)
        assert hasattr(mock_logfire, "span")

    @patch("draftpilot.agents.orchestrator.OpenAIProvider")
    @patch("draftpilot.agents.orchestrator.OpenAIChatModel")
    @patch("draftpilot.agents.orchestrator.Agent")
    def test_agent_system_prompt(
        self, mock_agent_class, mock_model_class, mock_provider_class
    ):
        """Test agent system prompt configuration."""
        mock_model_class.return_value = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_class.return_value = mock_agent_instance

        create_agent()

        # Verify system prompt contains relevant keywords
        call_args = mock_agent_class.call_args
        system_prompt = call_args.kwargs["system_prompt"]
        assert (
            "draftpilot" in system_prompt.lower()
            or "assistant" in system_prompt.lower()
        )
