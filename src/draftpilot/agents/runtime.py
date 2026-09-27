"""Build and run room agents that work through DraftPilot's own MCP server.

In-app agents use exactly the tools external MCP clients see, filtered by the run's permission
mode, while bound to one project as the internal client. Every run is measured as an
``AgentRun`` (model, tokens, tools, duration, trace id).
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import logfire
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.run import AgentRunResult

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.specs import RoleSpec
from draftpilot.core.agent_identity import InternalAgent, acting_as
from draftpilot.core.db import session_scope
from draftpilot.models import AgentRun

READ_TOOLS = frozenset(
    {
        "read_project_overview",
        "read_project_artifacts",
        "read_screenplay_scenes",
        "retrieve_project_context",
        "read_dialogue_translations",
        "read_scene_revisions",
        "read_project_evaluations",
    }
)
PROPOSE_TOOLS = frozenset({"propose_screenplay_change", "propose_timeline_reorder", "propose_dialogue_translation"})
EDIT_TOOLS = frozenset({"apply_story_operation", "start_context_workflow"})


def tools_for_mode(permission_mode: str) -> frozenset[str]:
    """Return the MCP tools a permission mode allows: read, then propose, then edit."""
    if permission_mode == "project_edit":
        return READ_TOOLS | PROPOSE_TOOLS | EDIT_TOOLS
    if permission_mode in {"suggest", "scoped_edit"}:
        return READ_TOOLS | PROPOSE_TOOLS
    return READ_TOOLS


def room_toolset(permission_mode: str) -> Any:
    """Return DraftPilot's MCP server as an in-process toolset filtered for a permission mode."""
    from draftpilot.mcp.server import (
        mcp,  # imported lazily: loading the server has side effects
    )

    allowed = tools_for_mode(permission_mode)
    return MCPToolset(mcp, id="draftpilot").filtered(lambda _ctx, tool: tool.name in allowed)


def _context_instructions(ctx: RunContext[RoomDeps]) -> str:
    """Describe the writer's current focus, layered instructions, and retrieved context."""
    deps = ctx.deps
    lines = [
        (
            f"Project id: {deps.project_id}. Pass project_id={deps.project_id} to every DraftPilot tool; "
            "other projects are not accessible."
        ),
        f"The writer is on page '{deps.page or 'studio'}'"
        + (f", working in {deps.artifact}" if deps.artifact else "")
        + (f", with selection: {deps.selection!r}" if deps.selection else "")
        + ".",
        f"Permission mode: {deps.permission_mode}. "
        + (
            "You may only read and advise; describe changes in prose."
            if deps.permission_mode == "chat_only"
            else "You may create proposals; the writer approves or rejects every one. Never claim a change is applied."
        ),
    ]
    if deps.scene_id:
        lines.append(f"Current scene id: {deps.scene_id}.")
    if deps.project_instruction:
        lines.append(f"Project instruction from the writer: {deps.project_instruction}")
    if deps.scene_instruction:
        lines.append(f"Scene instruction from the writer: {deps.scene_instruction}")
    if deps.retrieved_context:
        lines.append(
            "Retrieved project context (cite it when used): "
            + json.dumps(deps.retrieved_context[:8], ensure_ascii=False, default=str)[:6_000]
        )
    return "\n".join(lines)


BASE_INSTRUCTIONS = (
    "You are part of DraftPilot's writers' room, working for one screenwriter. "
    "Answer the writer directly and concretely. Preserve the screenplay's language. "
    "Use the DraftPilot tools to read the actual project before making claims about it."
)


def build_room_agent(spec: RoleSpec, model: Any, permission_mode: str) -> Agent[RoomDeps, str]:
    """Build a role agent with its spec, the writer's context, and permission-filtered MCP tools."""
    agent: Agent[RoomDeps, str] = Agent(
        model,
        deps_type=RoomDeps,
        name=spec.key,
        toolsets=[room_toolset(permission_mode)],
        model_settings={"temperature": spec.temperature},
        retries=2,
    )

    @agent.instructions
    def instructions(ctx: RunContext[RoomDeps]) -> str:
        """Render every instruction layer as one system prompt.

        Local chat templates (e.g. Qwen in LM Studio) reject more than one system message,
        so base, role, and run-context layers are joined rather than sent separately.
        """
        return "\n\n".join([BASE_INSTRUCTIONS, spec.instructions.strip(), _context_instructions(ctx)])

    return agent


def usage_limits(spec: RoleSpec) -> UsageLimits:
    """Bound one run's model requests so a confused model cannot loop forever."""
    return UsageLimits(request_limit=spec.max_requests)


def tools_used(messages: list[ModelMessage]) -> list[str]:
    """Return the names of the tools an agent called, in order."""
    return [
        part.tool_name
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart)
    ]


@dataclass
class RunMeter:
    """Track one agent run for the AgentRun record."""

    project_id: int
    role: str
    kind: str
    provider: str
    model: str
    workflow_run_id: int | None = None
    started: float = field(default_factory=monotonic)
    trace_id: str | None = None

    async def finish(self, result: AgentRunResult[Any] | None, error: BaseException | None = None) -> AgentRun:
        """Persist the measured run with usage, tools, duration, and outcome."""
        usage = result.usage if result is not None else None
        messages = result.all_messages() if result is not None else []
        record = AgentRun(
            project_id=self.project_id,
            workflow_run_id=self.workflow_run_id,
            kind=self.kind,
            role=self.role,
            provider=self.provider,
            model=self.model,
            status="failed" if error is not None else "succeeded",
            requests=usage.requests if usage else 0,
            tool_calls=usage.tool_calls if usage else 0,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            duration_ms=round((monotonic() - self.started) * 1000),
            trace_id=self.trace_id,
            tools_used=tools_used(messages),
            error=str(error)[:500] if error is not None else None,
        )
        async with session_scope() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record


@asynccontextmanager
async def measured_run(meter: RunMeter, run_id: int | None = None) -> AsyncIterator[RunMeter]:
    """Open a traced span bound to the internal agent identity for one room run."""
    with (
        logfire.span("room agent {role}", role=meter.role, project_id=meter.project_id, kind=meter.kind) as span,
        acting_as(InternalAgent(project_id=meter.project_id, role=meter.role, run_id=run_id)),
    ):
        context = span.get_span_context()
        meter.trace_id = format(context.trace_id, "032x") if context and context.trace_id else None
        yield meter


async def run_room_agent(
    spec: RoleSpec,
    model: Any,
    deps: RoomDeps,
    prompt: str,
    *,
    provider: str,
    model_name: str,
    kind: str = "chat",
    history: list[ModelMessage] | None = None,
    workflow_run_id: int | None = None,
) -> tuple[str, AgentRun]:
    """Run one room agent to completion and record its AgentRun."""
    agent = build_room_agent(spec, model, deps.permission_mode)
    meter = RunMeter(deps.project_id, spec.key, kind, provider, model_name, workflow_run_id)
    async with measured_run(meter, workflow_run_id):
        try:
            result = await agent.run(prompt, deps=deps, message_history=history, usage_limits=usage_limits(spec))
        except Exception as exc:
            await meter.finish(None, exc)
            raise
    record = await meter.finish(result)
    return str(result.output), record
