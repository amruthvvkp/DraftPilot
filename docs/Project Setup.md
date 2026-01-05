
Comprehensive Technical Architecture and Implementation Strategy for the Screenplay AI Platform
Executive Summary
This Technical Design Document (TDD) outlines the architectural blueprint, implementation strategy, and development directives for "DraftPilot," a next-generation screenplay analysis and editing platform. The system is engineered to bridge the gap between creative writing and artificial intelligence by integrating a professional-grade code editor (Monaco) with a structure-aware parsing engine (Fountain/Pydantic) and autonomous agentic capabilities (PydanticAI/FastMCP).

The core innovation of this platform lies in its "Context-Aware" nature. Unlike traditional text editors that treat screenplays as unstructured strings, DraftPilot utilizes a domain-specific parsing layer to convert raw Fountain syntax into structured Pydantic models in real-time. This structured data is then exposed via the Model Context Protocol (MCP) to local and remote Large Language Models (LLMs), effectively transforming the application into a semantic environment where AI agents can reason about plot structure, character arcs, and scene pacing with the same fidelity as the human author.

The architecture adopts a Modular Monolith pattern using a unified Python stack. NiceGUI (running on FastAPI) serves as the reactive frontend, enabling seamless state synchronization between the browser and the server-side Pydantic models. FastMCP provides the standardized interface for AI tool usage, while Logfire ensures observability into the non-deterministic execution of agentic logic. This document serves as the primary reference for the engineering team and includes specific, machine-consumable instructions (agents.md) to guide AI coding assistants in the autonomous generation of the codebase.

1. Strategic Architecture and Technology Selection
The selection of the technology stack for DraftPilot is driven by the requirement to minimize the impedance mismatch between the application's internal state (Python objects) and the AI's reasoning capabilities (which increasingly favor Pythonic interfaces).

1.1 The Shift to Backend-Driven UI with NiceGUI

Traditional web development often involves a "split-stack" approach—React or Vue on the client and Python/Node on the server—connected via REST or GraphQL. While scalable for massive distributed teams, this architecture introduces significant complexity in state management and serialization. For an AI-centric application where the "intelligence" resides on the server, a Backend-Driven UI approach offers superior velocity and consistency.   

NiceGUI (v2.0+) was selected as the presentation layer framework. Built on top of FastAPI, it leverages the Abstract Server Gateway Interface (ASGI) to maintain persistent WebSocket connections with the client. This allows the application to modify the DOM (Document Object Model) directly from Python code, eliminating the need for a separate Javascript frontend codebase for 90% of the functionality.

The architectural implication is profound: the Pydantic models representing the screenplay (the "Source of Truth") reside in the server's memory. When an AI agent modifies a scene, the update is pushed instantaneously to the user's browser via WebSocket, without complex polling mechanisms or client-side state reconciliation. This creates a "Live View" experience essential for collaborative AI-human writing sessions.   

1.2 The Domain-Specific Editor: Monaco

While NiceGUI provides standard UI components, a screenplay editor requires a specialized text editing interface. The Monaco Editor—the core of Visual Studio Code—was chosen over simpler alternatives (like CodeMirror or Ace) due to its superior handling of large documents, robust accessibility features, and, critically, its architecture which supports the Language Server Protocol (LSP).

Integrating Monaco into a Python-native framework like NiceGUI requires a custom wrapper. We leverage Vue.js (which NiceGUI uses internally) to create a bridge. The complexity here lies in the "dual-state" problem: the editor maintains its own internal text buffer in the browser, while the server maintains the Pydantic model state. The architecture must implement a debounce-and-sync strategy to ensure these two states remain eventually consistent without overriding the user's cursor position or causing race conditions during rapid typing.   

1.3 The Intelligence Backbone: PydanticAI and FastMCP

The platform is designed "AI-First." This means the application is not just a tool for humans but a tool for agents. To achieve this, we utilize FastMCP, an implementation of Anthropic’s Model Context Protocol. FastMCP allows us to expose the internal functions of the application (e.g., get_scene_list, analyze_dialogue) as standardized "Tools" that any MCP-compliant LLM client (such as Claude Desktop, Cursor, or Windsurf) can discover and execute.

PydanticAI serves as the orchestration layer for these agents. Unlike LangChain, which can be verbose and loosely typed, PydanticAI leverages Python's type system to enforce rigorous schema validation on agent inputs and outputs. This is critical for screenplay formatting, where a deviation in syntax (e.g., missing a period in a Scene Heading) renders the script invalid. By defining our domain logic with Pydantic models, we ensure that agents interact with the script structure safely and predictably.   

2. Detailed System Design
2.1 Backend Core: FastAPI and Lifecycle Management

The backend is the spine of DraftPilot. It must coordinate three distinct operational modes:

HTTP/REST: Serving standard API requests and static assets.

WebSocket: Maintaining real-time connections for the NiceGUI frontend.

MCP/SSE: Streaming Server-Sent Events for AI agent communication.

A critical architectural challenge identified in the research is the conflict between FastAPI's lifecycle events and FastMCP's internal server management. Both frameworks attempt to control the startup/shutdown sequence. To resolve this, we adopt a Sub-Application Mounting Strategy.   

The root application is a standard FastAPI instance. NiceGUI is attached using the ui.run_with method, which allows it to piggyback on the existing ASGI app rather than creating its own. The FastMCP server is then mounted as a separate sub-application (typically at /mcp).

Lifecycle Merging: To ensure that database connections and agent resources are available to both the UI and the MCP server, we must implement a unified lifespan context manager. This manager initializes the shared resources (database connection pools, vector store clients) and then yields control to the FastAPI app. This ensures that if the database fails to connect, the entire application halts immediately, preventing a "zombie" state where the UI loads but cannot save data.   

2.2 Directory Structure and Module Organization

To support the modular monolith architecture, the codebase is organized using a "src-layout" to prevent import side-effects and strictly enforce layer boundaries.

Table 1: Scalable Directory Structure

Directory	Role & Responsibility	Key Components
src/app/	Application Layer: Entry point and configuration.	main.py (Mounting), lifespan.py (Startup/Shutdown), config.py (Env vars).
src/core/	Infrastructure Layer: Database and low-level utils.	database.py (SQLModel), security.py (Auth), logging.py (Logfire setup).
src/domain/	Domain Layer: Pure business logic and models.	models.py (Fountain schemas), parser.py (Regex logic), validation.py.
src/features/	Presentation Layer: UI features grouped by capability.	editor/ (Monaco wrapper), analysis/ (Charts), navigation/ (Sidebar).
src/agents/	Intelligence Layer: AI agents and tools.	orchestrator.py, tools/ (MCP definitions), prompts.py.
src/mcp/	Protocol Layer: MCP server implementation.	server.py (FastMCP instance), routes.py (SSE endpoints).
This structure ensures that the domain logic remains pure Python, independent of the web framework (NiceGUI) or the AI framework (PydanticAI). This decoupling allows the parser to be extracted into a separate library or CLI tool in the future without refactoring the entire web application.   

3. Domain Logic: The Fountain Parsing Engine
The heart of the application is its ability to understand Fountain syntax. Fountain is a plain-text markup language similar to Markdown but strict in its formatting rules regarding line breaks and capitalization.

3.1 Pydantic Modeling of Screenplay Elements

We reject the approach of storing the screenplay as a generic Abstract Syntax Tree (AST) or JSON blob. Instead, we define a Discriminated Union of Pydantic models. This leverages Pydantic's powerful validation engine to ensure structural integrity.   

The base class, ScriptElement, contains metadata common to all elements (UUID, line number). Subclasses represent specific screenplay components:

SceneHeading: Must validate strict patterns (starts with INT., EXT., I/E., or a forced period .). It parses the raw line to extract location and time_of_day.

Character: Must be uppercase. It handles "Dual Dialogue" (indicated by a caretaker ^) and extensions like (V.O.) or (O.S.).

Dialogue: The text block following a Character element.

Parenthetical: Wrapped in parentheses, used for actor direction.

Action: The default fallback for text that doesn't match other patterns.

Transition: Uppercase text ending in TO: or forced with >.

By typing these strictly, PydanticAI agents can be instructed to "Return a list of SceneHeading objects," and the framework will automatically validate that the AI's output matches the schema, retrying if it generates invalid data.   

3.2 Incremental Parsing Algorithm

Parsing a 120-page script (approx. 20,000 words) on every keystroke is computationally expensive and causes input latency. The parsing engine implements an incremental strategy.

The parser maintains a "Context Window" of the previous two elements to determine the type of the current line. For example, a line is interpreted as Dialogue only if the preceding element was Character or Parenthetical. If the preceding element was Action, the line remains Action.

State Machine Logic: The parser functions as a generator that yields ScriptElement objects.

Input: Stream of strings (lines).

Process:

Check for "Forced" types (lines starting with . ! @ >).

Check for Scene Headings (Regex match against INT/EXT).

Check for Transitions (Regex match TO:$).

Check for Character (Uppercase, centered alignment heuristic).

Check for Dialogue (Preceded by Character/Parenthetical).

Output: Typed Pydantic model.

This stateless design allows the MCP tools to send just a fragment of text (e.g., a single scene) to the parser and receive a valid structure back, without needing the context of the entire file.   

4. Frontend Implementation: The Monaco-NiceGUI Bridge
Integrating Monaco Editor into NiceGUI is the most technically demanding component of the frontend. NiceGUI uses Vue.js 3 under the hood, but it abstracts away the .vue file compilation process. To include a complex third-party library like Monaco, we must manually construct the Vue component lifecycle.   

4.1 The AMD Loading Strategy

Monaco is traditionally distributed as an AMD (Asynchronous Module Definition) package. While newer ESM (ECMAScript Module) versions exist, they often require complex bundler configurations (Webpack/Vite plugins) that conflict with NiceGUI's internal build process.

We opt for the CDN-based AMD Loader approach. The implementation logic involves:

Resource Injection: The Python backend injects a script tag for the Monaco loader (loader.js) via ui.add_head_html.

Vue Component Mounting:

The mounted() hook of the Vue component checks for the global require object.

It configures the paths config to point to the CDN (e.g., cdnjs or unpkg).

It calls require(['vs/editor/editor.main'],...) to asynchronously load the editor core.

Initialization: Once loaded, monaco.editor.create() is called on the target DOM element.

This strategy decouples the editor resources from the application bundle, reducing initial load time and avoiding "Monaco is not defined" race conditions.   

4.2 Custom Language Definition (Fountain)

Monaco does not support Fountain natively. We must define a Monarch Tokenizer within the frontend component. This tokenizer uses regular expressions to assign CSS classes to different parts of the text.

Table 2: Monarch Tokenizer Rules for Fountain

Token Class	Regex Pattern	Visual Style
scene-heading	/^((INT|EXT|EST|I\/E)[\.]?.*)|^\..*$/	Bold, Blue (#569CD6)
character	/^[A-Z][A-Z0-9 ]+(\(.*\))?$/	Red (#CE9178)
transition	/^[A-Z ]+TO:$/	Uppercase, Purple (#C586C0)
note	/\[\[.*\]\]/	Italic, Grey (#6A9955)
section	/^#+ /	Orange (#D7BA7D)
These styles are applied by defining a custom theme (monaco.editor.defineTheme) that maps these token classes to specific colors. This visual feedback is essential for the user to trust that the parser (running on the backend) is interpreting their input correctly.   

4.3 Two-Way Data Binding and Latency

Synchronization is handled via a specialized protocol.

Client-to-Server: When the user types, the onDidChangeModelContent event fires. This event is debounced (e.g., 300ms) to prevent flooding the WebSocket. The current value is emitted to the server via emitEvent('change', value).

Server-to-Client: If an AI agent updates the script, the Pydantic model changes. The Python backend pushes the new string to the component using element.run_method('setValue', new_text).

Critical Optimization: To prevent the cursor from jumping to the start of the file when an AI update arrives, the client-side component must implement logic to capture the current cursor position (editor.getPosition()), apply the update, and then restore the position (editor.setPosition()). Alternatively, using editor.executeEdits() is preferred as it preserves the undo stack and cursor naturally.   

5. Intelligence Layer: Agents, MCP, and Observability
5.1 PydanticAI Agent Architecture

The application uses PydanticAI to define autonomous agents. These agents are not generic chatbots; they are specialized workers with strict schemas.

The Orchestrator Agent: This is the primary interface for the user. It determines whether a user's request requires:

Structural Modification: Adding scenes, renaming characters (requires Tool Usage).

Analysis: Summarizing plot points, checking pacing (requires Vector Search).

Creative Writing: Generating dialogue (requires pure LLM generation).

Dependency Injection (DI): PydanticAI's DI system is used to inject the AgentDependencies dataclass into every tool execution. This dataclass contains the AsyncSession for the SQLite database and the ChromaDB client for vector search. This ensures that tools are stateless and testable—we can inject mock databases during unit tests without changing the agent code.   

5.2 FastMCP Integration

The FastMCP server allows the application to "eat its own dogfood." The same tools used by the internal PydanticAI agents are exposed via MCP to external clients.

Mounting Strategy: The FastMCP instance is initialized in src/mcp/server.py. In src/app/main.py, we use the mcp.http_app() method to generate an ASGI app, which is then mounted to the main FastAPI app.

SSE Transport: We utilize Server-Sent Events (SSE) for the transport layer. This allows local AI clients (like Cursor) to connect to http://localhost:8000/mcp/sse. The advantages of SSE over Stdio in a web context are significant: it allows multiple clients to connect simultaneously and works seamlessly in containerized environments where Stdio is detached.   

5.3 Observability with Logfire

Given the non-deterministic nature of LLMs, debugging "why did the agent delete Scene 5?" is difficult. We integrate Logfire to provide distributed tracing.

Span Tracing: Every agent run is a trace. Each tool call is a span within that trace.

Payload Capture: Logfire captures the exact JSON payload sent to the LLM and the raw response.

Validation Errors: If the LLM generates a malformed Fountain string that fails the Pydantic parser, Logfire records the validation error. This feedback loop allows developers to fine-tune the system prompts to align with the Pydantic schemas.   

6. Implementation Guide and Developer Instructions (agents.md)
The following content constitutes the machine-consumable instructions for AI coding assistants. It is formatted to be copied directly into the agents.md file in the project root.

Agent Development Instructions (agents.md)
1. Project Context & Objectives
Project Name: DraftPilot Description: A full-stack screenplay editor utilizing NiceGUI (Frontend), FastAPI (Backend), and PydanticAI (Agents). The core function is parsing Fountain syntax into structured Pydantic models to enable AI reasoning. Architecture: Modular Monolith. Backend-driven UI. Target Audience: Domain Expert Developers.

2. Tech Stack & Dependencies
Language: Python 3.11+

Package Manager: uv (Use uv add, uv sync, uv run).

Frontend: NiceGUI 2.0+ (Vue 3 wrapper).

Backend: FastAPI, SQLModel (SQLite/Postgres).

Editor: Monaco Editor (via CDN + Custom Vue Component).

AI/Agents: PydanticAI, FastMCP (Model Context Protocol), Logfire.

Testing: Pytest, Playwright.

3. Directory Structure Rules
Maintain strict separation of concerns. Do not mix UI logic with Domain logic.

src/app/: Configuration, Lifecycle, Main Entry.

src/domain/: Pure Python Fountain parsing logic (No NiceGUI/FastAPI imports).

src/features/: UI Components (Editor, Sidebar) using NiceGUI.

src/agents/: PydanticAI Agents and FastMCP Tools.

src/core/: Database, Security, Utilities.

4. Coding Standards
Type Hints: MANDATORY. Use typing.Annotated, typing.Optional.

Docstrings: Google Style. Required for all public modules and functions.

Asynchrony: All I/O (DB, Network, AI) must be async.

Error Handling: Use Pydantic validation for data integrity. Catch specific exceptions.

5. Detailed Implementation Tasks
Task 5.1: Domain Logic - Fountain Parser

Goal: Create a robust parser for Fountain syntax. File: src/domain/models.py

Define a ScriptElement discriminated union.

Implement specific models: SceneHeading, Action, Character, Dialogue, Parenthetical, Transition, Boneyard.

Ensure SceneHeading validates INT, EXT, I/E, and forced headings (.). File: src/domain/parser.py

Implement parse_fountain_lines(lines: List[str]) -> Iterator.

Use a state machine approach: Track previous_element to distinguish Dialogue from Action.

Handle "Dual Dialogue" (caret ^).

Reference:  Fountain spec nuances.   

Task 5.2: Feature - Monaco Editor Wrapper

Goal: Integrate Monaco Editor into NiceGUI. File: src/features/editor/monaco.js

Create a Vue 3 component.

Use an AMD loader pattern to fetch Monaco from jsdelivr.

Implement monaco.languages.register({ id: 'fountain' }).

Define monarchTokensProvider for Fountain syntax highlighting.

Handle editor.onDidChangeModelContent -> emit change event (Debounce 300ms). File: src/features/editor/monaco.py

Subclass nicegui.ui.element.

Link to monaco.js using add_resource.

Implement set_value method that updates the editor content without resetting cursor (if possible via diffs, otherwise standard replace).

Task 5.3: Application - Main & Lifecycle

Goal: Wire FastAPI, NiceGUI, and FastMCP. File: src/app/lifespan.py

Create lifespan(app: FastAPI) using @asynccontextmanager.

Initialize DB connection (SQLModel).

Initialize Logfire (logfire.configure()).

Start FastMCP resources.

Yield.

Shutdown resources. File: src/app/main.py

Create app = FastAPI(lifespan=lifespan).

Initialize mcp = FastMCP("DraftPilot").

Mount MCP: app.mount("/mcp", mcp.http_app()).

Mount NiceGUI: ui.run_with(app, storage_secret=...).

Task 5.4: Agents - PydanticAI Integration

Goal: Create an agent that understands the script. File: src/agents/dependencies.py

Define AgentDependencies dataclass with db: AsyncSession and vector_store: Chroma. File: src/agents/tools.py

Create analyze_scene(ctx: RunContext, scene_text: str) tool.

Use src.domain.parser to parse text.

Return structured stats (character count, location). File: src/agents/orchestrator.py

Define ScriptAgent using pydantic_ai.Agent.

Register tools.

Set system prompt to act as a "Screenplay Consultant".

6. Acceptance Criteria
Parser: Passes unit tests for "Big Fish" sample script elements.

UI: Editor loads, highlights Fountain syntax, and persists text to DB on change.

MCP: /mcp/sse endpoint is active and discoverable by MCP Inspector.

Agent: Can answer "Who speaks the most in Scene 1?" by parsing the underlying text.

7. Project Roadmap and Delivery
The implementation is structured into four distinct phases, each culminating in a verifyable milestone.

Table 3: Development Roadmap

Phase	Duration	Deliverables	Definition of Done
1. Domain Foundation	Week 1	src/domain modules, Unit Tests.	Parser correctly identifies 99% of elements in the test corpus (e.g., standard sample scripts). Pydantic models enforce valid schemas.
2. Editor Integration	Week 2	src/features/editor, monaco.js.	NiceGUI app launches. Monaco loads. Typing updates the Python state variable. Syntax highlighting works for Scene Headings and Characters.
3. Protocol Layer	Week 3	src/mcp, src/app/main.py.	FastAPI app handles lifecycle correctly. MCP server is mounted. External MCP clients can connect via SSE and list tools.
4. Agentic Intelligence	Week 4	src/agents, Logfire setup.	Agents can read the script state via DI. Agents can modify the script (append scenes). Logfire shows full traces of agent reasoning.
8. Quality Assurance and Observability Strategy
8.1 Testing Strategy

Given the mix of UI, API, and Logic, a multi-tiered testing strategy is required.

Unit Tests (pytest): Focused strictly on src/domain. These tests verify that the Regex logic in the parser accurately handles edge cases (e.g., character names with spaces, dual dialogue).

Integration Tests: Verify the interaction between src/agents and the database. We use an in-memory SQLite database for these tests to ensure speed.

E2E Tests (playwright): Verify the NiceGUI frontend. These tests will launch the browser, type into the Monaco editor, and assert that the changes are reflected in the backend state.

8.2 Observability with Logfire

Logfire is not just a logger; it is our "X-Ray" machine for the AI.

Configuration: Logfire is configured in src/app/lifespan.py with logfire.configure(send_to_logfire='if-token-present'). This prevents errors during local dev if no token is set.

Instrumentation: We explicitly call logfire.instrument_pydantic_ai(), logfire.instrument_fastapi(), and logfire.instrument_sqlite3().

Dashboard Usage: The team will use the Logfire dashboard to monitor the "Token Usage" and "Latency" of the agents. This is crucial for optimizing cost and performance before production deployment.   

9. Security and Deployment Considerations
9.1 Execution Sandbox

The application runs AI agents that may execute code (if the python-interpreter tool is enabled). While our initial scope relies on Pydantic parsing, future expansions might allow the AI to run Python scripts for analysis.

Recommendation: Run the application within a Docker container with limited privileges.

Network Policy: The container should only have egress access to the specific LLM API endpoints (OpenAI/Anthropic) and the Logfire telemetry endpoint.

9.2 Secret Management

API keys (OpenAI, Logfire) must never be hardcoded. We use pydantic-settings to manage configuration.

Config Loader: src/app/config.py defines a Settings class that reads from .env.

Validation: The application will fail to start if critical keys (like OPENAI_API_KEY) are missing, preventing runtime failures deep in an agent task.

9.3 Deployment Infrastructure

Container: A multi-stage Dockerfile builds the application. Stage 1 installs dependencies with uv. Stage 2 copies the source.

Reverse Proxy: In production, Nginx or Traefik should sit in front of Uvicorn. Crucially, the proxy must support WebSocket upgrading for NiceGUI and Long-polling/SSE for FastMCP.

HTTPS: Secure WebSocket (wss://) is mandatory for production to prevent Man-in-the-Middle attacks on the real-time script data.

10. Conclusion
The "DraftPilot" architecture represents a sophisticated convergence of modern web technologies and agentic AI. By leveraging NiceGUI for the frontend, we maintain high developer velocity with a unified Python stack. The rigorous use of Pydantic and Fountain parsing ensures that the data structure remains pristine, enabling PydanticAI agents to reason effectively about the content. Finally, the FastMCP integration future-proofs the platform, allowing it to serve as a robust backend for the emerging ecosystem of AI-powered development tools. This document provides the complete roadmap and technical specification required to execute this vision with precision.

