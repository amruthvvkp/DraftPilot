# 🎬 DraftPilot

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![UV](https://img.shields.io/badge/UV-package%20manager-green.svg)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

**AI-powered screenplay editor and story development platform for visual storytellers** - Leverage intelligent assistance for character development, dialogue enhancement, plot structure analysis, and creative brainstorming while maintaining your unique voice.

## ✨ Features

- 🤖 **AI-Assisted Writing** - Get intelligent suggestions for dialogue, scene descriptions, and story development
- 📝 **Industry-Standard Formatting** - Automatic screenplay formatting following Hollywood standards
- 🎭 **Character Development** - AI-powered character arc tracking and consistency checking
- 📊 **Story Structure Analysis** - Real-time feedback on pacing, plot points, and narrative flow
- 🎬 **Scene Management** - Organize, rearrange, and track scenes with intelligent suggestions
- 💡 **Creative Brainstorming** - AI collaboration for plot ideas, dialogue alternatives, and story solutions
- 📚 **Genre Intelligence** - Tailored suggestions based on genre conventions and expectations

## 🚀 Quick Start

### Prerequisites

- Python 3.12 or higher
- [UV](https://github.com/astral-sh/uv) package manager

### Installation

1. **Install UV** (if you haven't already):
```bash
# On macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. **Clone the repository**:
```bash
git clone https://github.com/yourusername/DraftPilot.git
cd DraftPilot
```

3. **Create virtual environment and install dependencies** (optional but recommended):
```bash
uv sync --package draftpilot # Install the main DraftPilot package
uv sync --package draftpilot-mcp # Install the MCP Server
```

4. **Run the application**:
```bash
uv run --package draftpilot python -m draftpilot.main # Main application
uv run --package draftpilot-mcp python -m draftpilot_mcp.main # MCP Server
```

## 🛠️ Development Setup

### Installing development dependencies
```bash
uv sync --all-groups --all-extras -U --all-packages # Installing dependencies for the entire workspace
uv sync --all-groups --all-extras -U --package draftpilot # Install dependencies only for the main DraftPilot package
uv sync --all-groups --all-extras -U --package draftpilot-mcp # Install dependencies only for the MCP Server
```

### Running tests
```bash
pytest tests/
```

### Code formatting and linting
```bash
# Format code
ruff format .

# Lint code
ruff check .
```

### Building from source
```bash
uv build
```

## 📁 Project Structure

```
draftpilot/                    # Root (workspace + UI package)
├── src/
│   └── draftpilot/           # UI package source
│       ├── __init__.py
│       ├── main.py
│       ├── components.py
│       └── api_routes.py
├── packages/
│   ├── core/                 # Core package (shared, not published)
│   │   ├── src/
│   │   │   └── draftpilot_core/
│   │   │       ├── __init__.py
│   │   │       ├── models.py
│   │   │       ├── parser.py
│   │   │       ├── formatter.py
│   │   │       ├── ai.py
│   │   │       └── config.py
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── draftpilot-mcp/       # MCP server package
│       ├── src/
│       │   └── draftpilot_mcp/
│       │       ├── __init__.py
│       │       └── server.py
│       ├── pyproject.toml
│       └── README.md
├── pyproject.toml            # Root config (workspace + UI)
├── uv.lock                   # Single lockfile for all packages
├── .python-version           # Python version for the project
├── .gitignore
└── README.md
```

## 🎯 Usage Examples

### Basic screenplay creation
```python
from draftpilot import Screenplay, AIAssistant

# Initialize a new screenplay
screenplay = Screenplay(title="My Story")

# Get AI assistance for a scene
assistant = AIAssistant()
scene_suggestion = assistant.suggest_scene(
    context="INT. COFFEE SHOP - DAY",
    genre="drama",
    mood="tense"
)
```

### Command-line interface
```bash
# Create a new project
draftpilot new "My Screenplay"

# Open existing project
draftpilot open ./my-screenplay.draft

# Export to standard formats
draftpilot export --format pdf output.pdf
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📊 Roadmap

- [x] Core screenplay formatting engine
- [x] Basic AI integration
- [ ] Advanced character tracking
- [ ] Multi-language support
- [ ] Collaboration features
- [ ] Cloud sync
- [ ] Mobile companion app
- [ ] Industry standard export formats (FDX, Fountain)
- [ ] Production planning tools

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [UV](https://github.com/astral-sh/uv) for fast, reliable Python package management
- AI capabilities powered by [Your AI Provider]
- Inspired by the needs of modern storytellers

## 💬 Support

- 📧 Email: amruthvvkp@gmail.com
- 💭 Discussions: [GitHub Discussions](https://github.com/amruthvvkp/DraftPilot/discussions)
- 🐛 Issues: [GitHub Issues](https://github.com/amruthvvkp/DraftPilot/issues)

---

**Made with ❤️ for storytellers, by storytellers**
