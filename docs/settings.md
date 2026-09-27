# Settings & appearance

Open **Settings** from the sidebar.

## Appearance

Pick a theme and an accent colour:

- **Themes:** **Paper** (warm light), **Slate** (cool light), **Night** (dark), or **System**,
  which follows your OS.
- **Accents:** amber, teal, rose, indigo or sage, or choose any colour with **Custom**.

Changes apply immediately and are saved to your writer profile, so they follow you to other
browsers. Appearance is never shown to the agents.

## Writer profile and memories

The room reads your profile before every task:

- your name and pen name;
- your default format and language;
- a short bio and your style notes;
- preferences such as things to avoid.

**Memories** are short notes the room must always respect. Pin them globally or to one project, for
example "Never kill the dog" or "Edward always speaks in parables".

## Models

**Default model server** lists what the installation's `LLM__` server offers. By default that's LM
Studio, with the loaded models marked. **Add provider** stores more profiles:

- LM Studio, Ollama, OpenAI, OpenRouter, an OpenAI-compatible gateway, Anthropic or Google;
- the server encrypts API keys, which never come back to the browser.

Test a profile, or list its models, from its card. See [Provider setup](providers.md).

### Speed on local models

Local reasoning models spend most of their time thinking. Set `LLM__THINKING`:

- `auto` (the default) follows each role;
- `off` is fastest everywhere;
- `on` forces reasoning everywhere.

The graders (script doctor, audience evaluator, coverage reader and continuity supervisor) answer
without reasoning by default.
