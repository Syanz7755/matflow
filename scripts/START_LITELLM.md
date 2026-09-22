# LiteLLM 双击启动器

双击项目根目录的 `start_litellm.bat` 可单独启动本地 LiteLLM 网关。启动器仅检查环境变量是否存在；不会显示、提示输入或将 `SJTU_ZHIYUAN_API_KEY` 写入任何文件。

前提是该密钥已作为 Windows **用户环境变量**配置。若刚配置完成，请重新打开终端或重新登录 Windows 后再双击启动器。网关保持运行时，双击窗口不可关闭；关闭窗口会停止服务。

启动后，可在另一个终端设置本地网关访问令牌并执行功能探测：

```powershell
$env:MATFLOW_LITELLM_API_KEY = "sk-local-wqs"
uv run python examples\evaluate_llm_gateway.py
```

上游密钥不应填入 `litellm.yaml`、`data/settings.json`、脚本、Git 提交或测试报告。
