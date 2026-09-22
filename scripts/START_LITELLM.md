# LiteLLM 双击启动器

双击项目根目录的 `start_model_services.bat` 可启动本地 LiteLLM 网关和 Jev 决策网关。`start_litellm.bat` 保留为兼容别名，也会启动这两个模型。启动器仅检查环境变量是否存在；不会显示、提示输入或将 `SJTU_ZHIYUAN_API_KEY` 写入任何文件。

前提是该密钥已作为 Windows **用户环境变量**配置。若刚配置完成，请重新打开终端或重新登录 Windows 后再双击启动器。模型进程在后台运行；再次双击会复用健康的实例，不会重复占用端口。

启动后，可在另一个终端设置本地网关访问令牌并执行功能探测：

```powershell
The project launcher and the gateway-check script read the local gateway key from `config/litellm.yaml` automatically. It does not need to be copied into a terminal or displayed.
uv run python examples\evaluate_llm_gateway.py
```

上游密钥不应填入 `litellm.yaml`、`data/settings.json`、脚本、Git 提交或测试报告。
