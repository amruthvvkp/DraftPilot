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
