# hanqin-mcp

瀚钦 · 国学历法与象数文化计算 —— 确定性 MCP 服务。

提供真太阳时换算、定气节气查询、干支四柱推演、奇门盘面结构与八字盘面结构的确定性计算能力，服务于国学历法研究与象数文化教学场景。全部结果由本地确定性引擎算出，不经过任何大模型。

## 安装与启动

### 方式一：uvx 直接运行（推荐）

```bash
uvx --from git+https://github.com/hangtengjinke/hanqin-mcp hanqin-mcp
```

### 方式二：pip 安装

```bash
pip install git+https://github.com/hangtengjinke/hanqin-mcp
hanqin-mcp
```

### 方式三：源码运行

```bash
python -m app.mcp_server --transport stdio
```

HTTP 模式（可选，供远程调试）：

```bash
python -m app.mcp_server --transport streamable-http --port 8000
```

## WorkBuddy / MCP 客户端连接器配置

stdio 连接器配置示例（`.mcp.json`）：

```json
{
  "mcpServers": {
    "hanqin-guoxue": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/hangtengjinke/hanqin-mcp",
        "hanqin-mcp"
      ],
      "timeout": 30000
    }
  }
}
```

依赖说明：`uvx` 需要本机已安装 uv（https://github.com/astral-sh/uv）。GitHub 仓库需保持公开，uvx 才能拉取。

## MCP 工具列表

| 工具 | 说明 | 主要参数 |
|---|---|---|
| `service_info` | 查询能力清单、流派参数可选项与合规边界 | 无 |
| `true_solar_time` | 真太阳时换算（经度时差 + 均时差） | moment, longitude, use_eot, utc_offset_hours |
| `solar_term` | 定气节气查询（当前 / 下一个 / 全年表） | moment, utc_offset_hours |
| `ganzhi_four_pillars` | 干支四柱推演（年 / 月 / 日 / 时柱） | moment, zishi_sect, longitude, use_true_solar_time, use_eot, utc_offset_hours |
| `qimen_layout` | 奇门盘面结构计算（定局 + 布盘 + 格局要点） | moment, method, pan_type, longitude, question_type, detail, question 等 |
| `bazi_chart` | 八字盘面结构计算（四柱 + 大运流年 + 神煞） | year, month, day, hour, minute, era, calendar, region, gender 等 |

所有工具统一返回 `{ok, data, note, disclaimer}` 结构；`disclaimer` 字段必须原样保留在最终回答中。参数合法性可先调用 `service_info` 查询。

## 开发与构建

- 运行环境：Python 3.11+（推荐 3.12）。
- 依赖：`mcp>=1.9,<2`、`pydantic`、`lunar_python`（`uvicorn` 仅供 HTTP 模式使用）。
- 目录结构：

```
hanqin-mcp/
├── app/
│   ├── mcp_server.py      # MCP 服务端入口（工具注册与启动）
│   ├── compliance.py      # 合规拦截（医疗 / 金融 / 赌博 / 法律 / 安全五域）
│   ├── schemas.py         # 时间解析
│   ├── core/              # 确定性计算引擎（真太阳时 / 节气 / 四柱 / 奇门 / 八字）
│   └── knowledge/         # 确定性规则库（格局模式）
├── pyproject.toml
└── README.md
```

- 构建 wheel：`pip install build && python -m build`
- 入口声明：`[project.scripts] hanqin-mcp = "app.mcp_server:main"`

## 版权与合规声明

- 本仓库 © 2026 瀚钦（丹东）智能科技有限公司，保留所有权利。公开仓库仅用于 WorkBuddy 连接器拉取运行，不授予再分发与商业转售权利。
- 本服务只输出历法换算与盘面结构的确定性计算结果，供传统文化研究与教学参考；不提供任何论断或决策建议。
- 涉及医疗、金融、法律、人身安全、赌博等领域的诉求会被工具直接拒绝并返回合规提示，请勿尝试绕过。
- 免责声明：结果仅供参考，使用者应自行判断其适用性。
