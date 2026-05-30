# AGENTS.md — AlertHub

## Project Overview

AlertHub 是一个轻量级的告警转发网关，基于 **FastAPI** 构建。它接收来自不同来源（如 Prometheus Alertmanager）的告警，并将其并发分发到多个通知渠道（Bark、Telegram）。

- **版本**: 0.1.1
- **Python**: ≥ 3.13
- **包管理**: uv (pyproject.toml + uv.lock)
- **运行方式**: uvicorn ASGI server
- **容器化**: Dockerfile (python:3.13-slim)

## Repository Structure

```
alerthub/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用入口，生命周期管理，路由定义与异常全局拦截
│   ├── formatters.py            # Pydantic 消息模型 (Alert/AlertGroup) 及文本格式化模块
│   └── modules/
│       ├── __init__.py
│       └── AlertHub.py          # 核心告警分发引擎，支持超时、连接池与并发分发
├── tests/                       # 测试套件目录
│   ├── __init__.py
│   ├── conftest.py              # 全局 pytest 配置及 Mock 夹具 (fixtures)
│   ├── test_alerthub.py         # 告警分发引擎单元测试
│   ├── test_formatters.py       # 消息格式化模块单元测试
│   └── test_main.py             # 路由端点集成测试
├── pyproject.toml               # 项目元数据与依赖（包含 pytest/respx 开发依赖）
├── uv.lock                      # uv 锁定文件
├── Dockerfile                   # Docker 构建配置（包含原生 HEALTHCHECK 探针）
├── .dockerignore                # Docker 构建上下文排除列表
├── .python-version              # Python 版本锁定 (3.13)
├── .gitignore
└── README.md
```

## Architecture

```
HTTP Request
     │
     ▼
┌──────────┐     ┌────────────────────────────────────────────────────────┐
│  FastAPI  │────▶│                   AlertHub (分发引擎)                  │
│  main.py  │     │  - FuturesSession (并发 HTTP)                          │
│ (lifespan)│     │  - HTTPAdapter (重试 + 连接池)                          │
└──────────┘     │  - config 校验 + 优雅关闭 (close)                        │
     │            └──────┬──────────┬─────────────────────────────────────┘
     │                   │          │
     ▼              ┌────▼───┐ ┌───▼──────┐
┌──────────┐        │  Bark  │ │ Telegram │
│formatters│        └────────┘ └──────────┘
│.py 格式化│
└──────────┘
```

## Key Components

### `app/main.py` — FastAPI 应用

- **框架**: FastAPI + uvicorn
- **生命周期**: 使用 `@asynccontextmanager lifespan` 管理应用的启动与关闭。启动时初始化全局 `AlertHub` 并挂载至 `app.state.alerthub`，关闭时调用 `close()` 进行资源回收。
- **数据模型** (Pydantic):
  - `CustomAlert` — 通用自定义告警格式
  - `AlertResponse` — 统一输出报文格式（形如 `{"status": "ok"}`）
- **路由**:
  - `GET /health` — 系统状态健康检查端点
  - `POST /alert` — 通用告警接口（通过依赖注入获取并调用 `AlertHub`）
  - `POST /alertmanager-webhook` — Prometheus Alertmanager 原生 webhook 接口
- **异常处理**: 全局拦截 `AlerHubException`、`RequestValidationError`、`StarletteHTTPException` 及通用 `Exception`，全部包含详细日志捕获。

### `app/formatters.py` — 消息模型与格式化

- **数据模型** (Pydantic):
  - `Alert` — 单条告警详情模型（支持严重度 `severity` 与概要 `summary` 的安全缺省提取）
  - `AlertGroup` — 告警组模型
- **核心格式化函数**:
  - `build_alert_title(alert_group, firing_count)` — 组装告警通知的标题（如 `[FIRING: 3] job:prometheus`）
  - `format_alert_details(alert)` — 格式化单条告警明细，处理 Grafana URL 字符转义及非核心标签排除
  - `build_alert_message(firing_alerts, resolved_alerts)` — 合并 firing 和 resolved 的告警并输出文本消息体

### `app/modules/AlertHub.py` — 告警分发引擎

- **类 `AlertHub`**:
  - 通过环境变量或 dict 配置初始化，支持 `request_timeout` 设置（默认 10s）
  - **启动校验**: 在 `__init__` 中即时检测 Bark 及 Telegram 渠道配置完整性并输出 WARNING 日志
  - 使用 `requests-futures` 的 `FuturesSession` 进行并发非阻塞 HTTP 请求（max_workers=5）
  - **错误聚合**: 并发发送到所有渠道，收集所有 future 执行状态后一并抛出异常，防止部分发送失败被掩盖
  - **优雅关闭**: 暴露 `close()` 方法用于在应用关闭时注销并关闭后台 HTTP 会话资源
  - 支持 SOCKS 代理（用于 Telegram 等需要代理的场景）
- **通知渠道**:
  - `send_bark()` — 并发发送到 Bark 推送服务
  - `send_telegram()` — 并发发送到 Telegram Bot（支持在消息体及标题中优雅展现 `level` 等级）
  - `send()` — 并发分发统一入口

## Environment Variables

| 变量名 | 用途 | 必填 | 默认值 |
|---|---|---|---|
| `BARK_KEY` | Bark 推送 Key | 至少配置一个渠道 | 无 |
| `BARK_URL` | Bark 服务地址 | 否 | `https://api.day.app` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 至少配置一个渠道 | 无 |
| `TELEGRAM_CHAT_ID` | Telegram 目标 Chat ID | 配合 Bot Token | 无 |
| `SOCKS_PROXY` | SOCKS 代理地址（如 `socks5://host:port`） | 否 | 无 |
| `REQUEST_TIMEOUT` | HTTP 超时时间（秒） | 否 | `10` |

## Dependencies

| 包 | 用途 |
|---|---|
| `fastapi` | Web 框架 |
| `uvicorn` | ASGI 服务器 |
| `requests` | HTTP 客户端 |
| `requests-futures` | 异步并发 HTTP 请求 |
| `pysocks` | SOCKS 代理支持 |

## Development

### Local Run

```bash
# 安装生产及开发测试依赖
uv sync --dev

# 启动开发服务器
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Testing

本项目的测试覆盖了核心逻辑的各个方面：

```bash
# 执行全部自动化测试
pytest tests/ -v
```

### Docker

```bash
# 构建镜像
docker build -t alerthub .

# 本地运行并包含探针检测
docker run -d -p 8000:8000 \
  -e BARK_KEY=your_key \
  -e TELEGRAM_BOT_TOKEN=your_token \
  -e TELEGRAM_CHAT_ID=your_chat_id \
  --name alerthub-prod \
  alerthub
```

---

## Code Conventions

- **语言**: Python 3.13+，强类型注解
- **结构化配置**: 完美支持从 `os.environ` 纯环境变量启动，或通过显式 `config` 字典实例化（方便进行完备测试）
- **日志记录**: 使用标准 `logging` 模块，应用统一与 Uvicorn 日志对齐
- **错误捕获**: 全局气泡式捕获错误并返回友好的统一 JSON。

## Notes for AI Agents

- 新增或改动业务逻辑时，必须运行 `pytest tests/` 确保所有 24 个基础用例保持通过。
- 添加新渠道时，在 `AlertHub` 增加 `send_<channel>()` 后，于 `send()` 方法的 `future_map` 注册即可。
- 注意 `AlerHubException` 的既有拼写（少一个 `t`），保持一致以防引发引入错误。
