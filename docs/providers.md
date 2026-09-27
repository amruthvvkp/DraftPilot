# Provider setup

## The default: local LM Studio

Out of the box, every agent uses the model server set by the `LLM__` settings. The default is LM
Studio on your machine:

```bash
LLM__PROVIDER=lm_studio
LLM__BASE_URL=http://host.docker.internal:1234/v1   # compose default; http://localhost:1234/v1 outside Docker
LLM__MODEL=auto                                     # the first model LM Studio reports as loaded
LLM__THINKING=auto                                  # auto (per role) · on · off
```

Load a chat model in LM Studio (the room is tuned on `qwen/qwen3.8-27b`), load
`text-embedding-nomic-embed-text-v1.5` for retrieval, and start the server. **Settings → Default
model server** lists what it offers, with the loaded models marked. `host.docker.internal` is a
trusted model host, so containers can reach LM Studio on the host. Other private addresses stay
blocked.

Tests and evals always use local LM Studio (`EVAL__BASE_URL`), never a cloud provider.

## More providers

**Settings → Add provider** stores extra profiles for LM Studio, Ollama, OpenAI, OpenRouter, any
OpenAI-compatible gateway, Anthropic and Google Gemini. The room chat API (`/room/chat`) and room
workflows accept a `provider_profile_id` to use one of them instead of the default.

API keys are write-only. The API only ever reports `has_api_key`, and keys are encrypted with
`SECRETS__MASTER_KEY` before they are stored. Set a real Fernet key before creating profiles:

```bash
export SECRETS__MASTER_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

## Safety

The server validates provider URLs before it builds a model. It rejects:

- embedded credentials;
- cloud-metadata targets;
- private, link-local or reserved IP literals and DNS results, except the trusted model hosts in
  `LLM__TRUSTED_MODEL_HOSTS`;
- multicast addresses.

Loopback addresses stay available for local development. Credentials never reach the browser.

When no provider is enabled, agent features return a clear `503` and keep your message.
