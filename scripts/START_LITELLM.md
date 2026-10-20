# Model Service Launchers

`start_llm.bat` makes the LLM gateway available. It reads `config/llm.json` (host, port, key variable, models), reuses a running LiteLLM gateway that accepts the key in `LITELLM_DEFAULT_API_KEY`, and otherwise starts LiteLLM from `config/litellm.yaml`. `-CheckOnly` only reports readiness; `-Port N` uses another port for one run. `start_litellm.bat` is a backward-compatible alias of `start_llm.bat`.

`start_model_services.bat` starts every enabled service in `config/model_services.json`: the LiteLLM gateway (port 4078) and the Jev decision gateway (port 4079). MatFlow routes tools through Jev when it answers and through the LLM otherwise, so Jev is optional at run time.

Both launchers check only whether required environment variables exist. They never display, prompt for, or persist their values. A variable set with `setx` is read from the user environment even in a terminal opened before it was set.

Healthy services are reused instead of started twice. Newly started services run in hidden background processes. The repository does not provide a matching stop script.

See the authoritative [Startup Scripts Guide](../docs/STARTUP_SCRIPTS.md) for configuration, ports, validation mode, failure recovery, and the distinction between model-service and MatFlow launchers.

To probe the gateway after startup, run:

```powershell
uv run python examples\evaluate_llm_gateway.py
```

Never put upstream credentials in `config/litellm.yaml`, `config/llm.json`, a save's `settings.json`, scripts, Git commits, or test reports.
