# Provider setup

Provider profiles are managed by the server under `/api/v1/settings/providers`. API keys are
write-only: the API returns only `has_api_key`, and values are encrypted with
`SECRETS__MASTER_KEY` before they are persisted.

Set a valid Fernet key before creating profiles:

```bash
export SECRETS__MASTER_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

Supported OpenAI-compatible routes include OpenAI, OpenRouter, custom gateways, Ollama, and
LM Studio. Use `base_url` for a gateway or a container-to-host address such as
`http://host.docker.internal:11434/v1`. Provider calls are optional until a profile is enabled;
credentials remain server-side and are never sent to the browser.
Provider URLs are validated server-side before model construction; embedded credentials,
cloud-metadata targets, private/link-local/reserved IP literals or DNS results, and multicast
addresses are rejected. Hostnames must resolve before a provider request is opened. Loopback
endpoints remain available for local-first development.

The Copilot response endpoint uses the process-level `LLM__*` settings for its active model. A
configured `LLM__ENABLED=true`, provider, model, and endpoint are required before it calls a model;
otherwise it returns an explicit `503` and retains the writer's turn. Persisted provider profiles
are encrypted configuration records and are the next selection layer for multi-profile routing.
