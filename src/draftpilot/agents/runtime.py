"""Build and run room agents that work through DraftPilot's own MCP server.

There is one agent per role (``room_agents``), and each is durable. Inside a Temporal workflow,
its model requests and tool calls become activities (``TemporalDurability``). Anywhere else, it
runs in-process as a plain agent. In-app agents use exactly the tools external MCP clients see,
filtered per run by permission mode, and every tool call carries the run's signed internal
identity, bound to one project. Every run is measured as an ``AgentRun`` (model, tokens, tools,
duration, trace id).
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import timedelta
from functools import cache
from time import monotonic
from typing import Any

import logfire
from pydantic_ai import (
    Agent,
    DeferredToolRequests,
    ModelRetry,
    ModelSettings,
    RunContext,
    UsageLimits,
)
from pydantic_ai.capabilities import ResolveModelId
from pydantic_ai.durable_exec.temporal import TemporalDurability
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import ToolDefinition
from temporalio.common import RetryPolicy
from temporalio.workflow import ActivityConfig

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.models import default_ref, register_model, resolve_room_model
from draftpilot.agents.specs import RoleSpec, load_specs
from draftpilot.core.agent_identity import InternalAgent, identity_meta
from draftpilot.core.config import settings
from draftpilot.core.db import session_scope
from draftpilot.core.providers import parse_model_ref
from draftpilot.models import AgentRun

READ_TOOLS = frozenset(
    {
        "read_project_overview",
        "read_story_twin",
        "read_story_context",
        "read_storyline",
        "list_story_entities",
        "read_character",
        "read_outline",
        "read_project_artifacts",
        "read_screenplay_scenes",
        "retrieve_project_context",
        "read_dialogue_translations",
        "read_scene_revisions",
        "diff_scene_revisions",
        "read_project_evaluations",
        "list_proposals",
        "list_room_workflows",
        "read_workflow_run",
        "read_writer_twin",
    }
)
PROPOSE_TOOLS = frozenset(
    {
        "propose_story_change",
        "propose_outline",
        "propose_screenplay_change",
        "propose_timeline_reorder",
        "propose_dialogue_translation",
        "start_room_workflow",
        "start_evaluation",
        "snapshot_scene",
        "refresh_story_twin_now",
        "reindex_project_search",
    }
)
# Direct writes. Each needs the writer's approval for that exact call: in chat it is asked for
# in place (an AG-UI interrupt), and the approval becomes the call's approval_id.
APPROVAL_TOOLS = frozenset(
    {
        "update_project",
        "write_reference",
        "create_story_entity",
        "update_story_entity",
        "delete_story_entity",
        "create_act",
        "update_act",
        "delete_act",
        "create_scene",
        "write_scene",
        "update_scene",
        "move_scene",
        "delete_scene",
        "create_block",
        "update_block",
        "delete_block",
        "reorder_blocks",
        "restore_scene_revision",
        "review_screenplay_proposal",
        "reject_proposal",
        "review_timeline_proposal",
        "reject_timeline_proposal",
        "apply_story_operation",
        "apply_context_workflow",
        "write_canon_node",
        "write_canon_edge",
        "write_artifact",
        "update_writer_profile",
        "remember_writer_preference",
        "create_project_backup",
        "control_workflow_run",
    }
)
EDIT_TOOLS = APPROVAL_TOOLS | {"start_context_workflow", "import_screenplay", "duplicate_project"}


def tools_for_mode(permission_mode: str) -> frozenset[str]:
    """Return the MCP tools a permission mode allows: read, then propose, then edit (each write approved)."""
    if permission_mode == "project_edit":
        return READ_TOOLS | PROPOSE_TOOLS | EDIT_TOOLS
    if permission_mode in {"suggest", "scoped_edit"}:
        return READ_TOOLS | PROPOSE_TOOLS
    return READ_TOOLS


async def _stamp_identity(ctx: RunContext[RoomDeps], call_tool: Callable[..., Any], name: str, args: dict[str, Any]) -> Any:
    """Send one tool call with the run's signed internal-agent identity in its request ``_meta``."""
    role = getattr(getattr(ctx, "agent", None), "name", None) or "room"
    agent = InternalAgent(project_id=ctx.deps.project_id, role=role, run_id=ctx.deps.workflow_run_id)
    return await call_tool(name, args, metadata=identity_meta(agent))


def room_toolset(*, gate_writes: bool = False) -> Any:
    """Return DraftPilot's MCP server as an in-process toolset, filtered per run by ``deps``.

    With ``gate_writes`` (chat), calls to approval-required tools are deferred for the writer's
    in-chat approval instead of failing with a pending approval request.
    """
    from draftpilot.mcp.server import (
        mcp,  # imported lazily: loading the server has side effects
    )

    def allowed(ctx: RunContext[Any], tool: ToolDefinition) -> bool:
        """Offer a tool only when the run may use tools and its permission mode allows this one."""
        deps: RoomDeps = ctx.deps
        return deps.tools and tool.name in tools_for_mode(deps.permission_mode)

    toolset: MCPToolset[RoomDeps] = MCPToolset(mcp, id="draftpilot", process_tool_call=_stamp_identity)
    filtered = toolset.filtered(allowed)
    if not gate_writes:
        return filtered
    return filtered.approval_required(lambda _ctx, tool, args: tool.name in APPROVAL_TOOLS and "approval_id" not in args)


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
        + {
            "chat_only": "You may only read and advise; describe changes in prose.",
            "project_edit": (
                "You may change the project directly with the write tools; the writer approves each call before it runs, "
                "so ask for one coherent change at a time. Prefer propose_* tools for large or speculative changes."
            ),
        }.get(
            deps.permission_mode,
            "You may create proposals; the writer approves or rejects every one. Never claim a change is applied.",
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


def role_model_settings(spec: RoleSpec, thinking: bool | None = None) -> ModelSettings:
    """Return a role's sampling settings, with reasoning off when asked, or when the role or ``LLM__THINKING`` says so."""
    model_settings = ModelSettings(temperature=spec.temperature, max_tokens=spec.max_tokens)
    if thinking is None:
        thinking = {"on": True, "off": False}.get(settings.llm.thinking, spec.thinking)
    if not thinking:
        # The unified flag covers Anthropic/Google; OpenAI-compatible servers (LM Studio) need the effort.
        model_settings["thinking"] = False
        model_settings["openai_reasoning_effort"] = "none"  # type: ignore[typeddict-unknown-key]
    return model_settings


CHAT_TOPIC = "room-chat"


def _durability(name: str, event_stream_topic: str | None = None) -> TemporalDurability[RoomDeps]:
    """Return one agent's activity settings: long model calls, bounded retries, quick tool calls."""
    return TemporalDurability(
        name=name,
        event_stream_topic=event_stream_topic,
        model_activity_config=ActivityConfig(
            start_to_close_timeout=timedelta(seconds=settings.temporal.model_timeout_seconds),
            # A worker crash or lost connection is retried; a model error or runaway response is
            # not (it would only repeat), and consult's reasoning-off fallback handles runaways.
            retry_policy=RetryPolicy(maximum_attempts=3, non_retryable_error_types=["ModelHTTPError", "UnexpectedModelBehavior"]),
        ),
        toolset_activity_config={"draftpilot": ActivityConfig(start_to_close_timeout=timedelta(minutes=2))},
    )


def _build_role_agent(spec: RoleSpec, durability: TemporalDurability[RoomDeps], *, chat: bool = False) -> Agent[RoomDeps, Any]:
    """Build one role's durable agent: its spec, the writer's context, and the filtered MCP tools.

    Chat agents can end a turn by asking for the writer's approval (``DeferredToolRequests``).
    """
    agent: Agent[RoomDeps, Any] = Agent(
        default_ref(),
        deps_type=RoomDeps,
        name=spec.key,
        output_type=[str, DeferredToolRequests] if chat else str,
        toolsets=[room_toolset(gate_writes=chat)],
        retries=2,
        capabilities=[ResolveModelId(resolve_room_model), durability],
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


@cache
def room_agents() -> dict[str, Agent[RoomDeps, Any]]:
    """Return every role's agent, built once per process (outside any workflow, as Temporal requires)."""
    return {key: _build_role_agent(spec, _durability(key)) for key, spec in load_specs().items()}


@cache
def chat_agents() -> dict[str, Agent[RoomDeps, Any]]:
    """Return every role's chat agent: the same role, streaming its events to the chat workflow's topic.

    Room workflows host no event stream, so chat has agents of its own (``chat__<role>`` activities).
    """
    return {key: _build_role_agent(spec, _durability(f"chat__{key}", CHAT_TOPIC), chat=True) for key, spec in load_specs().items()}


def room_agent_activities() -> list[Callable[..., Any]]:
    """Return the Temporal activities of every role's durable agents (room and chat), for the worker to register."""
    activities: list[Callable[..., Any]] = []
    for agent in [*room_agents().values(), *chat_agents().values()]:
        durability = TemporalDurability.from_agent(agent)
        assert durability is not None
        activities.extend(durability.temporal_activities)
    return activities


def run_model(model: Any, deps: RoomDeps) -> str:
    """Return the model ref a run uses: an explicit ref or instance, else the deps' ref, else the default."""
    if isinstance(model, str) and model:
        return model
    if isinstance(model, Model):
        return register_model(model)
    return deps.model_ref or default_ref()


def model_identity(ref: str) -> tuple[str, str]:
    """Return ``(provider, model_name)`` from a model ref, for AgentRun records."""
    parsed = parse_model_ref(ref)
    return (parsed[1], parsed[2]) if parsed else ("", ref)


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


@dataclass
class Consultation:
    """One brief for one specialist."""

    role: str
    brief: str


def _add_consult_tool(agent: Agent[RoomDeps, Any]) -> None:
    """Give the showrunner tools to plan, and to delegate briefs to one or several specialists."""

    # A consultation runs a whole specialist, so its activity gets a model-sized timeout.
    @agent.tool(metadata={"temporal": ActivityConfig(start_to_close_timeout=timedelta(seconds=settings.temporal.model_timeout_seconds * 2))})
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
        ref = run_model(None, ctx.deps)
        meter = RunMeter(ctx.deps.project_id, role, "delegate", *model_identity(ref), ctx.deps.workflow_run_id)
        with logfire.span("showrunner consults {role}", role=role, brief=brief[:500]):
            try:
                result = await room_agents()[role].run(
                    brief,
                    deps=ctx.deps,
                    model=ref,
                    model_settings=role_model_settings(spec),
                    usage=ctx.usage,
                    usage_limits=usage_limits(spec),
                )
            except Exception as exc:
                await meter.finish(None, exc)
                raise
        await meter.finish(result)
        return f"[{spec.label}] {result.output}"

    @agent.tool(metadata={"temporal": ActivityConfig(start_to_close_timeout=timedelta(seconds=settings.temporal.model_timeout_seconds * 3))})
    async def consult_many(ctx: RunContext[RoomDeps], requests: list[Consultation]) -> list[str]:
        """Ask several specialists at once (in parallel), each with their own self-contained brief.

        Use it when the parts are independent: e.g. the character specialist on arcs and the
        continuity supervisor on facts. Each answer is labelled with its specialist.
        """
        if not requests or len(requests) > 6:
            raise ModelRetry("Send between 1 and 6 consultations")
        answers = await asyncio.gather(*(consult(ctx, item.role, item.brief) for item in requests), return_exceptions=True)
        return [answer if isinstance(answer, str) else f"[{item.role}] failed: {answer}" for item, answer in zip(requests, answers, strict=True)]

    @agent.tool_plain
    def plan(steps: list[str], goal: str = "") -> dict[str, Any]:
        """Write down your plan for a multi-step job before starting it; the writer sees it as a checklist.

        Call it again with the updated list as steps are done (prefix finished steps with "✓ ").
        """
        return {"goal": goal, "steps": steps[:20], "done": sum(step.startswith("✓") for step in steps)}


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

    def fields(self, result: AgentRunResult[Any] | None, error: BaseException | None, duration_ms: int) -> dict[str, Any]:
        """Describe the measured run as AgentRun fields: usage, tools, duration and outcome.

        Plain values only, so workflow code can build it and hand it to an activity.
        """
        usage = result.usage if result is not None else None
        messages = result.all_messages() if result is not None else []
        return {
            "project_id": self.project_id,
            "workflow_run_id": self.workflow_run_id,
            "kind": self.kind,
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "status": "failed" if error is not None else "succeeded",
            "requests": usage.requests if usage else 0,
            "tool_calls": usage.tool_calls if usage else 0,
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
            "duration_ms": duration_ms,
            "trace_id": self.trace_id,
            "tools_used": tools_used(messages),
            "error": failure_text(error)[:500] if error is not None else None,
        }

    async def finish(self, result: AgentRunResult[Any] | None, error: BaseException | None = None) -> AgentRun:
        """Persist the measured run with usage, tools, duration, and outcome."""
        duration_ms = round((monotonic() - self.started) * 1000)
        return await save_agent_run(AgentRun.model_validate(self.fields(result, error, duration_ms)))


async def save_agent_run(record: AgentRun) -> AgentRun:
    """Persist one AgentRun record."""
    async with session_scope() as session:
        session.add(record)
        await session.commit()
        await session.refresh(record)
    return record


@asynccontextmanager
async def measured_run(meter: RunMeter) -> AsyncIterator[RunMeter]:
    """Open a traced span for one room run and remember its trace id."""
    with logfire.span("room agent {role}", role=meter.role, project_id=meter.project_id, kind=meter.kind) as span:
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


def failure_text(error: BaseException) -> str:
    """Return a failure's message, including the causes a Temporal activity failure wraps."""
    messages: list[str] = []
    current: BaseException | None = error
    while current is not None and len(messages) < 6:
        messages.append(str(current))
        current = getattr(current, "cause", None) or current.__cause__
    return " <- ".join(message for message in messages if message) or type(error).__name__


def reasoning_ran_away(error: BaseException) -> bool:
    """Return whether a failure means the model reasoned too long: out of tokens, or the server gave up waiting."""
    message = failure_text(error).casefold()
    return "token limit" in message or ("timed out" in message and "without receiving data" in message)


def role_run_options(spec: RoleSpec, deps: RoomDeps, output_type: Any, thinking: bool | None) -> dict[str, Any]:
    """Return the per-run ``Agent.run`` options for one role: model, sampling, output type and budget."""
    return {
        "deps": deps,
        "model": deps.model_ref,
        "output_type": output_type,
        "model_settings": role_model_settings(spec, thinking),
        "usage_limits": usage_limits(spec),
    }


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
    """Run one room role in-process to a typed output and record its AgentRun.

    ``model`` is a model instance, a model ref, or ``None`` for the deps' model. Durable
    workflows use ``agents.workflows.consult`` instead, which records through activities.
    """
    deps = replace(deps, model_ref=run_model(model, deps), tools=tools and deps.tools, workflow_run_id=workflow_run_id or deps.workflow_run_id)
    agent = room_agents()[spec.key]
    thinking: bool | None = None
    for attempt in (1, 2):
        meter = RunMeter(deps.project_id, spec.key, kind, provider, model_name, deps.workflow_run_id)
        async with measured_run(meter):
            try:
                result = await agent.run(prompt, message_history=history, **role_run_options(spec, deps, output_type, thinking))
            except (UnexpectedModelBehavior, ModelHTTPError) as exc:
                await meter.finish(None, exc)
                if attempt == 1 and reasoning_ran_away(exc):
                    # The model reasoned past its budget (tokens, or the server's no-data timeout): answer without reasoning.
                    logfire.warning("{role} ran out of tokens while reasoning; retrying without reasoning", role=spec.key)
                    thinking = False
                    continue
                raise
            except Exception as exc:
                await meter.finish(None, exc)
                raise
        record = await meter.finish(result)
        return result.output, record
    raise AssertionError("unreachable")
