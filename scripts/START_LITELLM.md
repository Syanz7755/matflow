# Model Service Launcher

`start_model_services.bat` starts every enabled service in `config/model_services.json`, currently the LiteLLM gateway and the Jev decision gateway. `start_litellm.bat` is a backward-compatible alias and starts the same complete set of services despite its older name.

The launcher checks only whether required environment variables exist. It never displays, prompts for, or persists their values. If a user environment variable was added recently, open a new terminal or sign in again before launching the script.

Healthy services are reused instead of started twice. Newly started services run in hidden background processes. The current repository does not provide a matching stop script.

See the authoritative [Startup Scripts Guide](../docs/STARTUP_SCRIPTS.md) for configuration, ports, validation mode, failure recovery, and the distinction between model-service and MatFlow launchers.

To probe the gateway after startup, run:

```powershell
uv run python examples\evaluate_llm_gateway.py
```

Never put upstream credentials in `config/litellm.yaml`, `data/settings.json`, scripts, Git commits, or test reports.
