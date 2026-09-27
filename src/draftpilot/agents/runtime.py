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
from pydantic_ai import Agent, ModelRetry, ModelSettings, RunContext, UsageLimits
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.run import AgentRunResult

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.specs import RoleSpec
from draftpilot.core.agent_identity import InternalAgent, acting_as
from draftpilot.core.config import settings
from draftpilot.core.db import session_scope
from draftpilot.models import AgentRun

READ_TOOLS = frozenset(
    {
        "read_project_overview",
        "read_story_twin",
        "read_project_artifacts",
        "read_screenplay_scenes",
        "retrieve_project_context",
        "read_dialogue_translations",
        "read_scene_revisions",
        "read_project_evaluations",
    }
)
PROPOSE_TOOLS = frozenset(
    {
        "propose_screenplay_change",
        "propose_timeline_reorder",
        "propose_dialogue_translation",
        "list_room_workflows",
        "start_room_workflow",
    }
)
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
    if deps.writer_brief:
        lines.append(f"Writer twin (who you are writing for):\n{deps.writer_brief}")
    if deps.story_brief:
        lines.append(f"Story twin (the project as it stands):\n{deps.story_brief}")
    if deps.retrieved_context:
        lines.append(
            "Retrieved project context (cite it when used): "
            + json.dumps(deps.retrieved_context[:8], ensure_ascii=False, default=str)[:6_000]
        )
    return "\n".join(lines)


BASE_INSTRUCTIONS = (
    "You are part of DraftPilot's writers' room, working for one screenwriter. "
    "Answer the writer directly and concretely. Preserve the screenplay's language. "
    "Use the DraftPilot tools to read the actual project before making claims about it. "
    "Read economically: start from the Story twin and project overview, use retrieve_project_context "
    "to find the passages that matter, and read only the scenes you need (by scene_ids or a small page), "
    "never the whole script."
)


def role_model_settings(spec: RoleSpec) -> ModelSettings:
    """Return a role's sampling settings, with reasoning off when the role or ``LLM__THINKING`` says so."""
    model_settings = ModelSettings(temperature=spec.temperature, max_tokens=spec.max_tokens)
    thinking = {"on": True, "off": False}.get(settings.llm.thinking, spec.thinking)
    if not thinking:
        # The unified flag covers Anthropic/Google; OpenAI-compatible servers (LM Studio) need the effort.
        model_settings["thinking"] = False
        model_settings["openai_reasoning_effort"] = "none"  # type: ignore[typeddict-unknown-key]
    return model_settings


def build_room_agent(
    spec: RoleSpec, model: Any, permission_mode: str, output_type: Any = str, *, tools: bool = True
) -> Agent[RoomDeps, Any]:
    """Build a role agent with its spec, the writer's context, and (unless ``tools=False``) permission-filtered MCP tools."""
    agent: Agent[RoomDeps, Any] = Agent(
        model,
        deps_type=RoomDeps,
        name=spec.key,
        output_type=output_type,
        toolsets=[room_toolset(permission_mode)] if tools else [],
        model_settings=role_model_settings(spec),
        retries=2,
    )

    if spec.key == SHOWRUNNER:
        _add_consult_tool(agent)

    @agent.instructions
    def instructions(ctx: RunContext[RoomDeps]) -> str:
        """Render every instruction layer as one system prompt.

        Local chat templates (e.g. Qwen in LM Studio) reject more than one system message,
        so base, role, and run-context layers are joined rather than sent separately.
        """
        return "\n\n".join([BASE_INSTRUCTIONS, spec.instructions.strip(), _context_instructions(ctx)])

    return agent


SHOWRUNNER = "showrunner"
SPECIALISTS = frozenset(
    {
        "story_architect",
        "story_editor",
        "brainstormer",
        "character_specialist",
        "scene_writer",
        "script_editor",
        "script_doctor",
        "researcher",
        "continuity_supervisor",
        "associate_director",
        "audience_evaluator",
        "coverage_reader",
    }
)


def _add_consult_tool(agent: Agent[RoomDeps, Any]) -> None:
    """Give the showrunner a tool to delegate one brief to one specialist."""

    @agent.tool
    async def consult(ctx: RunContext[RoomDeps], role: str, brief: str) -> str:
        """Ask one room specialist to handle a self-contained brief and return their answer.

        role: one of story_architect, story_editor, brainstormer, character_specialist, scene_writer,
        script_editor, script_doctor, researcher, continuity_supervisor, associate_director,
        audience_evaluator, coverage_reader.
        """
        from draftpilot.agents.specs import role_spec

        if role not in SPECIALISTS:
            raise ModelRetry(f"Unknown specialist {role!r}; choose one of {', '.join(sorted(SPECIALISTS))}")
        spec = role_spec(role)
        specialist = build_room_agent(spec, ctx.model, ctx.deps.permission_mode)
        meter = RunMeter(
            ctx.deps.project_id,
            role,
            "delegate",
            getattr(ctx.model, "system", ""),
            getattr(ctx.model, "model_name", ""),
        )
        with logfire.span("showrunner consults {role}", role=role, brief=brief[:500]):
            try:
                result = await specialist.run(brief, deps=ctx.deps, usage=ctx.usage, usage_limits=usage_limits(spec))
            except Exception as exc:
                await meter.finish(None, exc)
                raise
        await meter.finish(result)
        return f"[{spec.label}] {result.output}"


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
    reply: str
    reply, record = await run_role(
        spec,
        model,
        deps,
        prompt,
        str,
        provider=provider,
        model_name=model_name,
        kind=kind,
        history=history,
        workflow_run_id=workflow_run_id,
    )
    return str(reply), record


async def run_role[OutputT](
    spec: RoleSpec,
    model: Any,
    deps: RoomDeps,
    prompt: str,
    output_type: type[OutputT] | Any,
    *,
    provider: str,
    model_name: str,
    kind: str = "chat",
    history: list[ModelMessage] | None = None,
    workflow_run_id: int | None = None,
    tools: bool = True,
) -> tuple[OutputT, AgentRun]:
    """Run one room role to a typed output and record its AgentRun."""
    agent = build_room_agent(spec, model, deps.permission_mode, output_type, tools=tools)
    meter = RunMeter(deps.project_id, spec.key, kind, provider, model_name, workflow_run_id)
    async with measured_run(meter, workflow_run_id):
        try:
            result = await agent.run(prompt, deps=deps, message_history=history, usage_limits=usage_limits(spec))
        except Exception as exc:
            await meter.finish(None, exc)
            raise
    record = await meter.finish(result)
    return result.output, record
