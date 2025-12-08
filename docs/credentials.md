# Credentials & API Keys

Algent prefers reading provider API keys from environment variables, but can fall back to the system keyring for convenience.

## Order of Precedence
1. Environment variables (set before starting the backend / Tauri app)
2. Keys saved via the in-app **Model API Keys** panel (writes to keyring)
3. Keyring entries added manually under service `algent` (per provider username)

If neither is present, provider calls will fail until keys are supplied.

## Supported Providers

| Provider  | Env Var               | Keyring Username      | Default Model         |
|-----------|----------------------|-----------------------|-----------------------|
| OpenAI    | `OPENAI_API_KEY`     | `openai_api_key`      | `gpt-4o-mini`         |
| Anthropic | `ANTHROPIC_API_KEY`  | `anthropic_api_key`   | `claude-3-5-sonnet`   |
| Gemini    | `GEMINI_API_KEY` \*  | `gemini_api_key`      | `gemini-1.5-pro`      |
| xAI       | `XAI_API_KEY`        | `xai_api_key`         | `grok-beta`           |

\* Gemini will also fall back to `GOOGLE_API_KEY` if `GEMINI_API_KEY` is absent.

## Managing Keys with Keyring

Store + verify keys using Python’s keyring CLI (after installing `keyring` in your environment):

```powershell
python -m keyring set algent openai_api_key
python -m keyring get algent openai_api_key
```

Repeat for other providers using the usernames from the table above.

## Tips
- Never hardcode secrets into source files or commit history.
- When testing multiple providers, prefer setting per-shell env vars (`$env:OPENAI_API_KEY="..."`) so you can swap quickly.
- For deployments beyond personal use, consider vault-backed solutions; this keyring workflow is intended for local developer ergonomics.
- The frontend button is the fastest way to rotate a key: select provider → paste key → Save. Running the backend during this step is enough; no restarts required unless the provider client caches credentials.
