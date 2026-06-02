# Wind Langfuse Flask Cross-Process Demo

这个仓库演示如何在 Flask 主进程和独立 Python worker 进程里规范使用
`wind-langfuse-sdk`。业务逻辑刻意保持简单，重点放在 SDK 初始化、span、
generation、event、trace 字段更新、跨进程 trace 关联和 flush。

## 项目结构

```text
.
├── app.py               # Flask 服务入口，接收 HTTP 请求并拉起 worker.py
├── worker.py            # 子进程入口，使用 trace_context 关联到同一条 trace
├── langfuse_client.py   # WindLangfuse 集中初始化，其他文件都从这里获取客户端
├── services.py          # 很薄的示例业务函数
├── requirements.txt
└── .env.example
```

## 安装

```powershell
cd D:\git-code\wind-langfuse-python-sdk-test
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果 `wind-langfuse-sdk` 在私有源里：

```powershell
python -m pip install wind-langfuse-sdk --index-url https://<your-private-pypi>/simple
python -m pip install Flask python-dotenv
```

本地调试 SDK 源码时，也可以从相邻源码目录安装：

```powershell
python -m pip install -e D:\git-code\langfuse-python
python -m pip install Flask python-dotenv
```

## 配置

复制 `.env.example` 为 `.env` 后，填写你的 Langfuse 和 Wind 配置：

```powershell
Copy-Item .env.example .env
```

`langfuse_client.py` 会通过 `python-dotenv` 自动加载 `.env`。Flask 主进程和
`worker.py` 子进程都会复用这套配置。

`WIND_APP_NAME` 会作为观测名前缀。例如代码里写 `http.demo`，上报到
Langfuse 后会变成 `flask-cross-process-demo:http.demo`。

## 启动

```powershell
python app.py
```

默认监听 `http://127.0.0.1:5000`。需要换端口时：

```powershell
$env:FLASK_PORT="5010"
python app.py
```

## 调用

健康检查：

```powershell
curl http://127.0.0.1:5000/health
```

触发跨进程 demo：

```powershell
curl -X POST http://127.0.0.1:5000/demo `
  -H "Content-Type: application/json" `
  -H "X-Request-Id: demo-001" `
  -d "{\"user_id\":\"u-1\",\"session_id\":\"s-1\",\"text\":\" hello wind langfuse \"}"
```

返回示例：

```json
{
  "request_id": "demo-001",
  "answer": "demo-answer: esufgnal dniw olleh",
  "normalized_text": "hello wind langfuse"
}
```

## 停止

在运行 Flask 的终端按 `Ctrl+C`。`app.py` 注册了 `atexit` flush，正常退出时会尽量把
当前进程缓冲的观测数据发出；`worker.py` 在每次处理完成后也会主动 `flush()`。

## 这个 Demo 覆盖了哪些 SDK 用法

- `langfuse_client.py` 统一初始化 `WindLangfuse`，其他 py 文件通过
  `get_langfuse_client()` 获取当前进程的单例客户端。
- `app.py` 使用 `start_as_current_span()` 创建 HTTP 根 span。
- `app.py` 使用 `span.update_trace()` 更新 `user_id`、`session_id`、`tags` 和
  `metadata`；传入的 `name` 会被 Wind wrapper 丢弃，这是 SDK 的约定。
- `app.py` 使用 `create_event()` 记录请求接收事件。
- `worker.py` 使用 `trace_context={"trace_id": ..., "parent_span_id": ...}` 把子进程
  里的 span/generation 关联回 Flask 请求 trace。
- `worker.py` 使用 `start_as_current_generation()` 演示模型调用观测，并填写
  `usage_details`。
- `/trace-url/<trace_id>` 演示通过 `client.native_client` 调用未被 wrapper 封装的原生
  Langfuse 能力；日常创建观测仍建议优先使用 Wind wrapper 方法。

## 注意事项

- 每个 Python 进程都有自己的 Langfuse 客户端和发送队列。跨进程场景下，主进程和子进程
  都应该在合适时机调用 `flush()`。
- 子进程无法自动继承主进程的当前上下文，所以需要显式传递 `trace_id` 和
  `parent_span_id`。
- 不要在业务文件里到处 new `WindLangfuse`。集中初始化能避免 app 名、环境、版本和采样
  参数不一致。
