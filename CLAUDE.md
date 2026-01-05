# CLAUDE.md - Agent Development Guidelines for DraftPilot

This document provides comprehensive guidelines for AI coding assistants working on the DraftPilot project. Follow these directives strictly to ensure consistent, production-ready code that adheres to the project's architectural principles.

## Table of Contents
1. [Project Overview](#project-overview)
2. [Core Technology Stack](#core-technology-stack)
3. [Architecture Principles](#architecture-principles)
4. [Directory Structure & Module Organization](#directory-structure--module-organization)
5. [Coding Standards](#coding-standards)
6. [Testing Requirements](#testing-requirements)
7. [Data Validation with Pydantic](#data-validation-with-pydantic)
8. [NiceGUI Frontend/Backend Integration](#nicegui-frontendbackend-integration)
9. [PydanticAI Agent Development](#pydanticai-agent-development)
10. [Production Readiness Checklist](#production-readiness-checklist)

---

## Project Overview

**Project Name:** DraftPilot  
**Description:** A full-stack screenplay editor utilizing NiceGUI (Frontend/Backend), FastAPI (Backend), and PydanticAI (Agents). The core function is parsing Fountain syntax into structured Pydantic models to enable AI reasoning.  
**Architecture:** Modular Monolith with Backend-Driven UI  
**Target Audience:** Domain Expert Developers

### Core Innovation
DraftPilot is a "Context-Aware" platform that converts raw Fountain syntax into structured Pydantic models in real-time. This structured data is exposed via Model Context Protocol (MCP) to LLMs, enabling AI agents to reason about plot structure, character arcs, and scene pacing with high fidelity.

---

## Core Technology Stack

### Mandatory Technologies

- **Language:** Python 3.11+ (type hints mandatory)
- **Package Manager:** `uv` (MANDATORY - use `uv add`, `uv sync`, `uv run` for ALL Python execution)
- **Frontend/Backend:** NiceGUI 3.0+ (Vue 3 wrapper, uses FastAPI internally)
- **Backend Framework:** FastAPI (ASGI server)
- **Data Validation:** Pydantic 2.12+ (MANDATORY for all data models)
- **AI/Agents:** PydanticAI 1.39+ (agentic framework with multi-provider support), FastMCP (Model Context Protocol)
- **Database:** SQLModel (SQLite/Postgres) with async support
- **Editor:** Monaco Editor (via CDN + Custom Vue Component)
- **Observability:** Logfire 4.16+ with FastAPI instrumentation (distributed tracing)
- **Testing:** Pytest (unit/integration), NiceGUI User fixture (fast UI tests), Playwright (E2E)

### UV Package Manager Requirements

**CRITICAL:** This project uses `uv` as the exclusive package manager and Python runtime manager.

**MANDATORY Rules:**
- **NEVER** use `python`, `python3`, `pip`, or `poetry` commands directly
- **ALWAYS** use `uv run` to execute Python scripts, tests, or any Python command
- **ALWAYS** use `uv add` to add new dependencies
- **ALWAYS** use `uv sync` to sync dependencies
- **ALWAYS** use `uv` commands in Docker containers and CI/CD pipelines

**Examples:**
```bash
# ✅ CORRECT
uv run pytest tests/
uv run python src/draftpilot/app/main.py
uv run uvicorn draftpilot.app.main:app --host 0.0.0.0 --port 8000
uv add pydantic-ai
uv sync

# ❌ WRONG
python pytest tests/
python3 src/draftpilot/app/main.py
pip install pydantic-ai
poetry add pydantic-ai
```

### Key Dependencies

```python
# Core
nicegui[redis]>=3.4.1
fastapi>=0.128.0
pydantic>=2.12.4
pydantic-settings>=2.11.0
pydantic-ai>=1.39.0
fastmcp>=2.13.0.2
sqlmodel>=0.0.22
logfire[fastapi]>=4.16.0

# Testing
pytest>=8.4.1
pytest-asyncio>=0.24.0
playwright>=1.48.0
```

---

## Architecture Principles

### 1. Backend-Driven UI with NiceGUI

**CRITICAL:** DraftPilot uses NiceGUI for both frontend and backend. This is a **unified Python stack** approach.

- **Source of Truth:** Pydantic models reside in server memory
- **State Synchronization:** WebSocket connections maintain real-time sync between browser and server
- **No Separate Frontend:** 90% of functionality is Python-driven; minimal JavaScript required
- **Live Updates:** AI agent modifications push instantaneously to browser via WebSocket

**Implementation Rule:** When modifying UI, work in Python using NiceGUI components. Only use JavaScript/Vue for complex third-party integrations (like Monaco Editor).

### 2. Modular Monolith Pattern

Maintain strict separation of concerns:
- **Domain Layer:** Pure Python, no framework dependencies
- **Application Layer:** FastAPI/NiceGUI orchestration
- **Features Layer:** UI components using NiceGUI
- **Agents Layer:** PydanticAI agents and tools
- **Protocol Layer:** FastMCP server implementation

### 3. Pydantic-First Data Modeling

**MANDATORY:** All data structures MUST use Pydantic models:
- Discriminated unions for screenplay elements
- Strict validation for structural integrity
- Type safety for AI agent interactions
- Automatic schema validation in PydanticAI

**Never use:** Generic dicts, JSON blobs, or untyped data structures for domain models.

### 4. AI-First Design

The application is designed for agents, not just humans:
- All internal functions exposed as MCP tools
- PydanticAI agents with strict schemas
- Dependency injection for testability
- Observability via Logfire for debugging agent behavior

---

## Directory Structure & Module Organization

### Required Directory Layout

```
src/draftpilot/
├── app/              # Application Layer: Entry point and configuration
│   ├── main.py       # NiceGUI app setup, FastMCP mounting, Logfire instrumentation
│   └── lifespan.py   # Startup/shutdown lifecycle handlers (on_startup/on_shutdown)
│
├── core/             # Infrastructure Layer: Database and low-level utils
│   ├── config.py     # Settings with provider-specific nested classes
│   ├── database.py   # SQLModel setup, async session management
│   ├── security.py   # Authentication/authorization
│   └── logging.py    # Logfire OTEL configuration
│
├── domain/           # Domain Layer: Pure business logic (NO framework imports)
│   ├── models.py     # Pydantic models for Fountain elements
│   ├── parser.py     # Fountain parsing logic (state machine)
│   └── validation.py # Domain-specific validation rules
│
├── features/         # Presentation Layer: UI features grouped by capability
│   ├── editor/       # Monaco Editor wrapper
│   │   ├── monaco.py # NiceGUI element subclass
│   │   └── monaco.js # Vue component for Monaco
│   ├── analysis/     # Charts and analysis views
│   └── navigation/   # Sidebar, scene navigation
│
├── agents/           # Intelligence Layer: AI agents and tools
│   ├── orchestrator.py    # Main PydanticAI agent
│   ├── dependencies.py    # DI dataclass (db, vector_store)
│   ├── tools.py           # MCP tool definitions
│   └── prompts.py         # System prompts for agents
│
└── mcp/              # Protocol Layer: MCP server implementation
    ├── server.py     # FastMCP instance
    └── routes.py     # SSE endpoints (if needed)
```

### Import Rules

**STRICT ENFORCEMENT:**
- `src/domain/` MUST NOT import NiceGUI, FastAPI, or PydanticAI
- `src/features/` can import NiceGUI but NOT domain models directly (use dependency injection)
- `src/agents/` can import domain models and use PydanticAI
- `src/app/` orchestrates all layers

**Example:**
```python
# ✅ CORRECT: Domain layer is pure Python
# src/domain/models.py
from pydantic import BaseModel
from typing import Literal

# ❌ WRONG: Domain layer importing framework
# src/domain/models.py
from nicegui import ui  # NEVER DO THIS
```

---

## Coding Standards

### Type Hints (MANDATORY)

**Every function, method, and variable MUST have type hints:**

```python
from typing import Annotated, Optional, Iterator, List
from pydantic import BaseModel

def parse_fountain_lines(
    lines: List[str],
    previous_element: Optional[ScriptElement] = None
) -> Iterator[ScriptElement]:
    """Parse Fountain syntax into structured elements."""
    ...
```

**Use `typing.Annotated` for dependency injection:**
```python
from pydantic_ai import RunContext
from typing import Annotated

async def analyze_scene(
    ctx: RunContext,
    scene_text: Annotated[str, "The Fountain text to analyze"]
) -> SceneAnalysis:
    ...
```

### Docstrings (Sphinx Style - No Types)

**All public modules, classes, and functions MUST have docstrings in Sphinx format:**

**CRITICAL:** Use Sphinx-style docstrings WITHOUT type information (types are in function signatures):

```python
def parse_fountain_lines(lines: List[str]) -> Iterator[ScriptElement]:
    """Parse Fountain syntax into structured screenplay elements.

    This function implements a state machine that processes lines sequentially,
    using context from previous elements to determine the current element type.

    :param lines: List of strings representing the screenplay lines.
    :yield: Typed Pydantic models representing screenplay elements.
    :raises ValidationError: If a line cannot be parsed into a valid element.
    """
    ...
```

**Format Rules:**
- Use `:param name:` for parameters (no type info needed)
- Use `:return:` or `:yield:` for return values
- Use `:raises ExceptionType:` for exceptions
- Use `:yield:` for generators
- Do NOT include type information in docstrings (it's already in the signature)

### Asynchrony

**All I/O operations MUST be async:**
- Database queries
- Network requests
- AI agent calls
- File operations (use `aiofiles`)

```python
# ✅ CORRECT
async def get_scene_by_id(session: AsyncSession, scene_id: str) -> Scene:
    result = await session.get(Scene, scene_id)
    return result

# ❌ WRONG
def get_scene_by_id(session: Session, scene_id: str) -> Scene:  # Synchronous
    result = session.get(Scene, scene_id)
    return result
```

### Error Handling

**Use Pydantic validation for data integrity. Catch specific exceptions:**

```python
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

async def create_scene(data: dict) -> Scene:
    try:
        scene = Scene.model_validate(data)
    except ValidationError as e:
        logger.error(f"Invalid scene data: {e}")
        raise ValueError(f"Invalid scene: {e}") from e
    
    try:
        async with get_session() as session:
            session.add(scene)
            await session.commit()
            return scene
    except IntegrityError as e:
        logger.error(f"Database error: {e}")
        raise
```

---

## Testing Requirements

### Full Unit Test Coverage (MANDATORY)

**Every module MUST have corresponding unit tests with >90% coverage.**

### Test Organization

```
tests/
├── unit/
│   ├── test_domain_models.py      # Pydantic model validation
│   ├── test_domain_parser.py      # Fountain parsing logic
│   ├── test_domain_validation.py  # Domain validation rules
│   ├── test_core_config.py        # Settings configuration
│   ├── test_core_logging.py       # Logfire configuration
│   ├── test_agents_orchestrator.py # PydanticAI agent creation
│   ├── test_app_main.py           # Application setup
│   ├── test_app_lifespan.py       # Lifespan handlers
│   └── test_mcp_server.py         # FastMCP server
│
├── integration/
│   ├── test_nicegui_app.py        # NiceGUI UI integration tests (User fixture)
│   ├── test_agents_database.py    # Agent + DB interaction
│   └── test_mcp_tools.py          # MCP tool execution
│
└── e2e/
    ├── test_editor_integration.py  # Monaco + NiceGUI
    └── test_agent_ui_flow.py       # Full user workflows
```

### NiceGUI Testing with User Fixture

**Use NiceGUI's User fixture for fast, lightweight UI testing:**

```python
# pytest.ini configuration
[pytest]
asyncio_mode = auto
main_file = src/draftpilot/app/main.py
addopts = -p nicegui.testing.user_plugin -v --tb=short
```

**Integration Test Example:**
```python
from nicegui.testing import User

async def test_counter_increment(user: User):
    """Test counter button interaction."""
    await user.open("/")
    await user.should_see("Counter: 0")
    
    user.find("Increment").click()
    await user.should_see("Counter: 1")
    
    # Find by element type
    await user.should_see(kind=ui.button, content="Increment")
    
    # Negative assertions
    await user.should_not_see("Counter: 999")
```

**Key Points:**
- User fixture is fast (no browser needed) - execution time similar to unit tests
- Tests run in same async context as the app
- Use `user.find()` for interactions, `user.should_see()` for assertions
- All tests must be async when using User fixture

### Unit Test Standards

**Test Structure:**
```python
import pytest
from draftpilot.domain.models import SceneHeading, Character, Dialogue
from draftpilot.domain.parser import parse_fountain_lines

class TestFountainParser:
    """Test suite for Fountain syntax parsing."""
    
    def test_parse_scene_heading_int(self):
        """Test parsing INT. scene headings."""
        lines = ["INT. KITCHEN - DAY"]
        elements = list(parse_fountain_lines(lines))
        assert len(elements) == 1
        assert isinstance(elements[0], SceneHeading)
        assert elements[0].location == "KITCHEN"
        assert elements[0].time_of_day == "DAY"
    
    def test_parse_character_dialogue(self):
        """Test parsing character and dialogue blocks."""
        lines = [
            "JOHN",
            "Hello, how are you?"
        ]
        elements = list(parse_fountain_lines(lines))
        assert len(elements) == 2
        assert isinstance(elements[0], Character)
        assert isinstance(elements[1], Dialogue)
        assert elements[0].name == "JOHN"
    
    @pytest.mark.parametrize("input_line,expected_type", [
        ("INT. ROOM - NIGHT", SceneHeading),
        ("EXT. STREET - DAY", SceneHeading),
        ("FADE IN:", Transition),
    ])
    def test_parse_various_elements(self, input_line, expected_type):
        """Test parsing various Fountain element types."""
        elements = list(parse_fountain_lines([input_line]))
        assert isinstance(elements[0], expected_type)
```

### Integration Test Standards

**Use in-memory SQLite for speed:**
```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from draftpilot.core.database import Base

@pytest.fixture
async def test_db():
    """Create in-memory test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield async_session
    await engine.dispose()
```

### E2E Test Standards (Playwright)

```python
import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_editor_syntax_highlighting(page: Page):
    """Test Monaco editor highlights Fountain syntax."""
    await page.goto("http://localhost:8000")
    
    editor = page.locator(".monaco-editor")
    await editor.fill("INT. KITCHEN - DAY\nJOHN\nHello!")
    
    # Wait for syntax highlighting
    await page.wait_for_timeout(500)
    
    # Verify scene heading is highlighted (check CSS class)
    scene_heading = editor.locator(".mtk3")  # Monaco token class
    await expect(scene_heading).to_be_visible()
```

### Test Coverage Requirements

- **Minimum Coverage:** 90% for all modules
- **Critical Paths:** 100% coverage for domain parsing logic
- **Run Tests:** `uv run pytest --cov=src --cov-report=html --cov-report=term`
- **NEVER** use `python -m pytest` or `pytest` directly - always use `uv run pytest`

---

## Data Validation with Pydantic

### Pydantic Model Design

**ALL domain models MUST use Pydantic BaseModel:**

```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional
from uuid import UUID, uuid4

class ScriptElement(BaseModel):
    """Base class for all screenplay elements."""
    id: UUID = Field(default_factory=uuid4)
    line_number: int
    element_type: str
    
    @field_validator('element_type')
    @classmethod
    def validate_element_type(cls, v: str) -> str:
        allowed = {'scene_heading', 'action', 'character', 'dialogue', 
                   'parenthetical', 'transition', 'boneyard'}
        if v not in allowed:
            raise ValueError(f"Invalid element_type: {v}")
        return v

class SceneHeading(ScriptElement):
    """Scene heading element (INT./EXT./etc.)."""
    element_type: Literal['scene_heading'] = 'scene_heading'
    location: str
    time_of_day: Optional[str] = None
    forced: bool = False  # True if starts with "."
    
    @field_validator('location')
    @classmethod
    def validate_location(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Location cannot be empty")
        return v.strip().upper()
    
    @classmethod
    def from_line(cls, line: str, line_number: int) -> 'SceneHeading':
        """Parse a line into a SceneHeading model."""
        # Validation happens automatically via Pydantic
        if line.startswith('.'):
            location = line[1:].strip()
            forced = True
        else:
            # Parse INT./EXT./I/E. pattern
            ...
        return cls(
            line_number=line_number,
            location=location,
            time_of_day=time_of_day,
            forced=forced
        )
```

### Discriminated Unions

**Use discriminated unions for type safety:**

```python
from typing import Union, Literal

ScriptElement = Union[
    SceneHeading,
    Action,
    Character,
    Dialogue,
    Parenthetical,
    Transition,
    Boneyard
]

# PydanticAI can validate this automatically
def get_all_scenes(elements: List[ScriptElement]) -> List[SceneHeading]:
    """Extract only scene headings from element list."""
    return [e for e in elements if isinstance(e, SceneHeading)]
```

### Validation Best Practices

1. **Use Field() for constraints:**
```python
from pydantic import Field

class Character(ScriptElement):
    name: str = Field(..., min_length=1, max_length=50)
    extension: Optional[str] = Field(None, pattern=r'^\([A-Z\.]+\)$')
```

2. **Use @field_validator for complex rules:**
```python
@field_validator('name', mode='before')
@classmethod
def validate_character_name(cls, v: str) -> str:
    """Character names must be uppercase."""
    if not v.isupper():
        raise ValueError("Character names must be uppercase")
    return v.strip()
```

3. **Use @model_validator for cross-field validation:**
```python
from pydantic import model_validator

class Dialogue(ScriptElement):
    text: str
    character_id: Optional[UUID] = None
    
    @model_validator(mode='after')
    def validate_character_context(self):
        """Dialogue should follow a Character element."""
        if self.character_id is None:
            raise ValueError("Dialogue must be associated with a character")
        return self
```

---

## NiceGUI Frontend/Backend Integration

### Using NiceGUI's App Directly

**CRITICAL:** Use NiceGUI's built-in FastAPI app instead of creating a separate one:

```python
from nicegui import app, ui

# NiceGUI's app IS a FastAPI instance - use it directly
# Configure Logfire on NiceGUI's app
from draftpilot.core.logging import configure_logfire
configure_logfire(app)

# Mount FastMCP on NiceGUI's app
app.mount("/mcp", mcp.http_app())

# Use ui.run() to start the server (not uvicorn directly)
if __name__ == "__main__":
    ui.run(host="0.0.0.0", port=8000, reload=True)
```

**Benefits:**
- Simpler architecture - no need to mount NiceGUI on a separate FastAPI app
- Direct access to NiceGUI's app for instrumentation and mounting
- Standard NiceGUI patterns for deployment

### NiceGUI Component Usage

**Use NiceGUI components for all UI elements:**

```python
from nicegui import ui

@ui.page('/')
async def main_page():
    """Main application page."""
    with ui.column().classes('w-full h-full'):
        ui.label('DraftPilot').classes('text-2xl font-bold')
        
        # Monaco editor integration
        editor = MonacoEditor(value=initial_script)
        editor.on('change', handle_script_change)
        
        with ui.row():
            ui.button('Analyze', on_click=analyze_script)
            ui.button('Save', on_click=save_script)
```

### State Management

**Server-side state is the source of truth:**

```python
from nicegui import ui
from draftpilot.domain.models import Script

# Server-side state
current_script = Script()

@ui.page('/')
async def editor_page():
    editor = MonacoEditor(value=current_script.to_fountain())
    
    def handle_change(event):
        """Update server state when editor changes."""
        new_text = event.args
        # Parse and update Pydantic model
        current_script.update_from_fountain(new_text)
        # State automatically syncs via WebSocket
    
    editor.on('change', handle_change)
```

### Monaco Editor Integration

**Custom NiceGUI element for Monaco:**

```python
# src/features/editor/monaco.py
from nicegui import ui

class MonacoEditor(ui.element):
    """Monaco Editor wrapper for NiceGUI."""
    
    def __init__(self, value: str = '', **kwargs):
        super().__init__('div', **kwargs)
        self._props['value'] = value
        self._classes.append('monaco-editor-container')
        
        # Inject Monaco loader
        ui.add_head_html('''
            <script src="https://cdn.jsdelivr.net/npm/monaco-editor@latest/min/vs/loader.js"></script>
        ''')
        
        # Vue component for Monaco
        self._props['monaco-config'] = {
            'language': 'fountain',
            'theme': 'fountain-theme'
        }
    
    def set_value(self, value: str):
        """Update editor content without resetting cursor."""
        self.run_method('setValue', value)
    
    def get_value(self) -> str:
        """Get current editor content."""
        return self._props.get('value', '')
```

### WebSocket Communication

**NiceGUI handles WebSocket automatically. For custom events:**

```python
# Emit event from Python
editor.emit('change', new_text)

# Listen in Vue component
editor.on('change', lambda e: handle_change(e.args))
```

---

## PydanticAI Agent Development

### Agent Definition

**All agents MUST use PydanticAI with strict schemas and dynamic provider configuration:**

```python
from pydantic_ai import Agent, RunContext
from draftpilot.agents.orchestrator import create_agent

# Agent is created dynamically based on settings.llm_provider
# Supports: openai, anthropic, google, azure, bedrock, ollama, deepseek, alibaba, fireworks, together
agent = create_agent()

# Agent includes model settings for thinking/reasoning if configured
# Thinking is configured per-provider in settings (e.g., settings.openai.thinking_enabled)
```

**Provider-Specific Configuration:**
- Each provider has its own settings class (e.g., `OpenAISettings`, `AnthropicSettings`)
- Settings are nested in main `Settings` class (e.g., `settings.openai`, `settings.anthropic`)
- Environment variables use provider-specific prefixes (e.g., `DRAFTPILOT_OPENAI_API_KEY`)
- Model selection via `settings.llm_provider` and provider-specific `model_name`

**Thinking/Reasoning Configuration:**
- Configured per-provider in settings classes
- Applied via `model_settings` when creating agents
- Provider-specific: OpenAI (reasoning_effort), Anthropic (thinking_budget_tokens), etc.

### Tool Definition

**Tools MUST use Pydantic models for inputs/outputs:**

```python
from pydantic_ai import tool
from draftpilot.domain.models import ScriptElement, SceneHeading
from draftpilot.domain.parser import parse_fountain_lines

@tool
async def analyze_scene(
    ctx: RunContext,
    scene_text: Annotated[str, "Fountain text of the scene to analyze"]
) -> SceneAnalysis:
    """Analyze a scene and return structured statistics.
    
    Args:
        scene_text: The Fountain-formatted scene text.
        
    Returns:
        SceneAnalysis: Pydantic model with character counts, location, etc.
    """
    # Parse using domain logic
    elements = list(parse_fountain_lines(scene_text.split('\n')))
    
    # Extract scene heading
    scene_heading = next((e for e in elements if isinstance(e, SceneHeading)), None)
    
    # Count characters
    characters = [e for e in elements if isinstance(e, Character)]
    dialogue_lines = [e for e in elements if isinstance(e, Dialogue)]
    
    return SceneAnalysis(
        location=scene_heading.location if scene_heading else "UNKNOWN",
        character_count=len(set(c.name for c in characters)),
        dialogue_line_count=len(dialogue_lines),
        total_elements=len(elements)
    )

# Register tool with agent
script_agent = script_agent.with_tools([analyze_scene])
```

### Dependency Injection

**Use DI for database and external services:**

```python
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from chromadb import AsyncClient

@dataclass
class AgentDependencies:
    """Dependencies injected into agent tools."""
    db: AsyncSession
    vector_store: AsyncClient

# In tool, access via RunContext
@tool
async def get_scene_by_id(
    ctx: RunContext,
    scene_id: Annotated[str, "UUID of the scene"]
) -> Scene:
    """Retrieve a scene from the database."""
    deps: AgentDependencies = ctx.deps
    result = await deps.db.get(Scene, scene_id)
    if not result:
        raise ValueError(f"Scene {scene_id} not found")
    return result
```

### Agent Execution

```python
async def run_agent_query(query: str, script_id: UUID) -> ScriptAnalysis:
    """Execute agent with proper dependency injection."""
    async with get_db_session() as session:
        deps = AgentDependencies(
            db=session,
            vector_store=get_vector_store()
        )
        
        result = await script_agent.run(
            query,
            deps=deps
        )
        
        return result.data  # Pydantic model
```

### Dynamic Agent Creation

**Create agents with runtime provider/model selection:**

```python
from draftpilot.agents.orchestrator import create_agent_with_provider

# Create agent with specific provider and model at runtime
agent = create_agent_with_provider("ollama", "llama3")

# Run agent
result = await agent.run("Your message here")
print(result.output)
```

**Use Cases:**
- UI-based model selection (chat interfaces)
- A/B testing different models
- Multi-tenant scenarios with different providers
- Testing without modifying global settings

**Available Providers:**
- `openai`, `anthropic`, `google`, `azure`, `bedrock`
- `ollama`, `deepseek`, `together`, `alibaba`, `fireworks`

**Running the Application:**
```bash
# ✅ CORRECT - Use ui.run() via Python module (NiceGUI standard)
uv run python src/draftpilot/app/main.py

# ✅ CORRECT - Or use uvicorn directly (NiceGUI's app is ASGI-compatible)
uv run uvicorn draftpilot.app.main:app --host 0.0.0.0 --port 8000

# ❌ WRONG - Never use python directly
python src/draftpilot/app/main.py
python -m uvicorn draftpilot.app.main:app
```

**Note:** When using NiceGUI's app directly, `ui.run()` handles the server startup. For Docker/production, you can still use uvicorn since NiceGUI's app is a FastAPI instance.

---

## Production Readiness Checklist

### Code Quality

- [ ] **Type Hints:** All functions have complete type annotations
- [ ] **Docstrings:** All public APIs have Google-style docstrings
- [ ] **Error Handling:** Specific exceptions caught and logged
- [ ] **Async/Await:** All I/O operations are async
- [ ] **Pydantic Models:** All data structures use Pydantic validation

### Testing

- [ ] **Unit Tests:** >90% coverage for all modules
- [ ] **Integration Tests:** Database and agent interactions tested
- [ ] **E2E Tests:** Critical user flows tested with Playwright
- [ ] **Test Performance:** Unit tests complete in <5 seconds
- [ ] **CI/CD:** Tests run automatically on every commit

### Security

- [ ] **Secret Management:** API keys in environment variables (pydantic-settings)
- [ ] **Input Validation:** All user inputs validated via Pydantic
- [ ] **SQL Injection:** Use SQLModel ORM, never raw SQL
- [ ] **XSS Prevention:** NiceGUI handles escaping automatically
- [ ] **HTTPS:** WSS (WebSocket Secure) in production

### Performance

- [ ] **Database Indexing:** Critical queries have indexes
- [ ] **Caching:** Expensive operations cached appropriately
- [ ] **Debouncing:** Editor changes debounced (300ms)
- [ ] **Lazy Loading:** Monaco Editor loaded asynchronously
- [ ] **Connection Pooling:** Database connections pooled

### Observability

- [x] **Logfire Integration:** All agent runs traced
- [x] **Logfire Configuration:** Nested `LogfireSettings` class with OTEL endpoint
- [x] **FastAPI Instrumentation:** Logfire auto-instrumentation on NiceGUI's app
- [x] **Test Mode Detection:** Logfire instrumentation skipped during pytest
- [ ] **Error Logging:** Exceptions logged with context
- [ ] **Metrics:** Token usage and latency tracked
- [ ] **Health Checks:** `/health` endpoint for monitoring

### Deployment

- [x] **Docker:** Multi-stage Dockerfile with uv (use `uv run` for all commands)
- [x] **Docker Compose:** Services for UI, Redis, and Grafana LGTM
- [x] **Environment Config:** Pydantic-settings with nested provider classes
- [x] **NiceGUI App:** Uses `ui.run()` for standard NiceGUI deployment
- [x] **Docker venv Isolation:** Uses `UV_PROJECT_ENVIRONMENT=/opt/venv` to prevent host `.venv` from overwriting container venv
- [x] **Host Service Access:** Configured `host.docker.internal` for accessing services (e.g., Ollama) running on host from Docker container
- [ ] **Reverse Proxy:** Nginx/Traefik configured for WebSocket/SSE
- [ ] **Database Migrations:** Alembic or SQLModel migrations
- [x] **Graceful Shutdown:** Lifespan handlers (on_startup/on_shutdown) handle cleanup
- [x] **UV Commands:** All Docker commands use `uv run` (never `python` directly)

### Documentation

- [ ] **README:** Setup and usage instructions
- [ ] **API Docs:** FastAPI auto-generated docs at `/docs`
- [ ] **Code Comments:** Complex logic explained
- [ ] **Architecture Diagram:** System architecture documented

---

## Quick Reference: Common Patterns

### Creating a New Domain Model

```python
# src/domain/models.py
from pydantic import BaseModel, Field
from typing import Literal
from uuid import UUID, uuid4

class NewElement(BaseModel):
    """Description of the element."""
    id: UUID = Field(default_factory=uuid4)
    element_type: Literal['new_element'] = 'new_element'
    # Add fields with validation
```

### Creating a NiceGUI Feature

```python
# src/features/new_feature/component.py
from nicegui import ui

class NewComponent(ui.element):
    """New UI component."""
    def __init__(self, **kwargs):
        super().__init__('div', **kwargs)
        # Initialize component
```

### Creating a PydanticAI Tool

```python
# src/agents/tools.py
from pydantic_ai import tool, RunContext
from typing import Annotated

@tool
async def new_tool(
    ctx: RunContext,
    input_data: Annotated[str, "Description"]
) -> OutputModel:
    """Tool description."""
    # Tool implementation
    return OutputModel(...)
```

### Writing a Unit Test

```python
# tests/unit/test_new_feature.py
import pytest
from draftpilot.domain.models import NewElement

class TestNewElement:
    def test_validation(self):
        """Test element validation."""
        element = NewElement(...)
        assert element.element_type == 'new_element'
```

**Running Tests:**
```bash
# ✅ CORRECT - Use uv run
uv run pytest tests/unit/
uv run pytest tests/integration/  # NiceGUI integration tests
uv run pytest tests/unit/test_new_feature.py -v
uv run pytest --cov=src --cov-report=html

# ❌ WRONG - Never use python or pytest directly
python -m pytest tests/
pytest tests/
```

**NiceGUI Testing Setup:**
- Configure `pytest.ini` with `main_file` pointing to your NiceGUI app entry point
- Use `nicegui.testing.user_plugin` for fast User fixture tests
- All NiceGUI tests must be async and use the `user: User` fixture
- User fixture provides fast, browser-less simulation of user interactions

---

## Configuration Patterns

### Provider-Specific Settings

**Use nested settings classes for provider-specific configuration:**

```python
# Each provider has its own settings class
class OpenAISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="draftpilot_openai_")
    model_name: str = Field(default="gpt-4o-mini")
    api_key: str | None = Field(default=None)
    thinking_enabled: bool = Field(default=False)
    # ... provider-specific fields

class Settings(BaseSettings):
    llm_provider: str = Field(default="openai")
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    # ... other providers
```

**Benefits:**
- Clean separation of provider-specific settings
- Environment variable prefixes per provider (e.g., `DRAFTPILOT_OPENAI_API_KEY`)
- Easy to add new providers
- Type-safe configuration

### Logfire Configuration with NiceGUI

**Configure Logfire on NiceGUI's app with test detection:**

```python
def configure_logfire(app=None) -> Logfire | None:
    """Configure Logfire with OTEL exporter."""
    if not settings.logfire.enabled:
        return None
    
    # Skip instrumentation during testing
    is_testing = os.environ.get("PYTEST_CURRENT_TEST") is not None
    
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = settings.logfire.otel_endpoint
    logfire.configure(service_name=settings.logfire.service_name, send_to_logfire=False)
    
    if app is not None and not is_testing:
        logfire.instrument_fastapi(app)
    
    return logfire
```

### Settings Validator Pattern

**Use `@model_validator` to set environment variables from settings:**

```python
class Settings(BaseSettings):
    nicegui_redis_url: str | None = Field(
        default=None,
        description="NiceGUI Redis URL. If None, uses file-based storage.",
    )

    @model_validator(mode="after")
    def set_nicegui_redis_url(self) -> "Settings":
        """Set NICEGUI_REDIS_URL environment variable if configured.
        
        :return: Settings instance (for chaining).
        """
        if self.nicegui_redis_url:
            os.environ["NICEGUI_REDIS_URL"] = self.nicegui_redis_url
        return self
```

**Benefits:**
- Keeps environment variable setting logic in the settings class
- Automatic execution when settings are loaded
- Clean separation of concerns

### Docker Configuration

**Dockerfile Pattern for uv with venv isolation:**

```dockerfile
# Set venv location outside mounted directory
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY . /app

# Create venv during build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-cache
```

**Docker Compose Pattern for host service access:**

```yaml
services:
  app:
    environment:
      # Access services on host machine (Mac/Windows Docker Desktop)
      - DRAFTPILOT_OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
    volumes:
      - ./:/app
      # Note: .venv is not mounted - stored in /opt/venv
```

**Key Points:**
- Use `UV_PROJECT_ENVIRONMENT` to store venv outside mounted directory
- Use `host.docker.internal` to access host services from Docker (Mac/Windows)
- On Linux, use host IP or `172.17.0.1` (Docker bridge gateway)

## Final Notes

- **Always use UV:** Never use `python`, `pip`, or `poetry` directly - always use `uv run` for Python execution
- **Always use NiceGUI's app:** Use `from nicegui import app` directly, don't create separate FastAPI app
- **Always use Sphinx docstrings:** No type info in docstrings (types in signatures)
- **Always validate with Pydantic:** Never accept unvalidated data
- **Always write tests:** No code without tests - use NiceGUI User fixture for UI tests
- **Always use type hints:** Type safety is non-negotiable
- **Always use async:** I/O must be asynchronous
- **Always follow directory structure:** Maintain layer boundaries
- **Always document:** Public APIs need docstrings
- **Provider settings pattern:** Use nested settings classes for clean configuration

When in doubt, refer to the existing codebase patterns and the comprehensive Project Setup document in `docs/Project Setup.md`.

---

## Implementation Notes

### Current Architecture Decisions

1. **NiceGUI App as Base:** We use NiceGUI's built-in FastAPI app (`from nicegui import app`) directly instead of creating a separate FastAPI instance. This simplifies the architecture and follows NiceGUI best practices.

2. **Provider-Specific Settings:** LLM provider configuration uses nested settings classes (e.g., `OpenAISettings`, `AnthropicSettings`) within the main `Settings` class. This provides clean separation and type safety.

3. **Thinking Configuration:** Thinking/reasoning capabilities are configured per-provider in their respective settings classes and applied via `model_settings` when creating PydanticAI agents.

4. **Logfire Integration:** Logfire instrumentation is applied to NiceGUI's app and automatically skipped during pytest execution (detected via `PYTEST_CURRENT_TEST` environment variable).

5. **Lifespan Handlers:** Since NiceGUI already has its own lifespan, we use `on_startup` and `on_shutdown` handlers instead of a custom lifespan context manager.

6. **Testing Strategy:** Use NiceGUI's User fixture for fast UI integration tests. These tests run as fast as unit tests without requiring a browser.

7. **Docstring Style:** All docstrings use Sphinx format without type information (types are in function signatures).

8. **Docker venv Isolation:** Virtual environment stored at `/opt/venv` via `UV_PROJECT_ENVIRONMENT` to prevent host `.venv` from overwriting container's venv when using bind mounts.

9. **Host Service Access:** Docker containers access host services (e.g., Ollama) using `host.docker.internal` (Mac/Windows) or host IP (Linux).

10. **Dynamic Agent Creation:** `create_agent_with_provider()` function allows runtime selection of LLM provider and model without modifying global settings.

11. **Settings Validators:** Use `@model_validator` to automatically set environment variables from settings, keeping configuration logic centralized.

---

**Last Updated:** 2025-01-27  
**Version:** 1.2.0

