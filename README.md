# RealResearch — 螺旋式深度研究，持久化记忆

> **基于 [Hindsight](https://github.com/vectorize-io/hindsight) 的长期记忆引擎，零侵入引用，开箱即用。**

RealResearch 是一套面向深度研究（Deep Research）场景的 CLI 工具集。它将网络搜索、研报分析、记忆存储、智能检索和反思推理串联成一个**螺旋迭代工作流**，让研究过程具备**持久化记忆**和**跨会话积累**能力。

---

## 快速启动（3 步）

### 1. 克隆 Hindsight 引擎

```bash
# 在 RealResearch 目录下执行：
git clone https://github.com/vectorize-io/hindsight.git hindsightbase
```

> **目录结构要求**：`hindsightbase/` 必须位于 `RealResearch/` 内部。
> ```
> RealResearch/
> ├── hindsightbase/          # ← git clone 得到
> │   └── hindsight-api-slim/
> ├── real_research/          # ← Python 源码
> ├── pyproject.toml
> └── .env
> ```

### 2. 安装依赖

```bash
cd RealResearch

# 推荐用 uv
uv pip install -e .

# 或传统 pip
pip install -e .

# 如需零配置嵌入式数据库（自动启动本地 PostgreSQL）
pip install -e ".[embedded-db]"
```

### 3. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

| 变量 | 用途 | 获取地址 |
|------|------|---------|
| `RR_EMBEDDING_API_KEY` | 文本嵌入 | [阿里云百炼](https://bailian.console.aliyun.com) |
| `RR_RERANK_API_KEY` | 结果重排序 | [阿里云百炼](https://bailian.console.aliyun.com) |
| `RR_LLM_API_KEY` | LLM 推理 | 任意 OpenAI 兼容服务（默认小米 MiMo） |
| `RR_SEARCH_API_KEY` | 网络搜索 | [Tavily](https://tavily.com) |
| `RR_TUSHARE_TOKEN` | 研报索引（可选） | [Tushare](https://tushare.pro) |
| `RR_TEXTIN_APP_ID` | PDF 转换（可选） | [TextIn](https://www.textin.com) |

---

## 验证安装

```bash
rr-env-check
```

全部通过即可开始使用。

---

## CLI 工具速查

| 命令 | 功能 | 典型用法 |
|------|------|---------|
| `rr-search` | 网络搜索 | `rr-search -q "量子计算最新进展" -n 8` |
| `rr-fetch` | 网页抓取 | `rr-fetch -u https://... -m 20000` |
| `rr-retain` | 存入记忆 | `rr-retain -c "...发现..." -b ai-chips` |
| `rr-recall` | 检索记忆 | `rr-recall -q "昇腾技术参数" -b ai-chips` |
| `rr-reflect` | 深度反思 | `rr-reflect -q "综合分析" -b ai-chips --budget high` |
| `rr-report` | 保存报告 | `rr-report -q "主题" -c "## 内容..."` |
| `rr-bank` | 记忆库管理 | `rr-bank list`, `rr-bank create --id ...` |
| `rr-route` | 智能路由 | `rr-route -q "AI芯片"` |
| `rr-tushare-index` | 研报索引构建 | `rr-tushare-index --months 3` |
| `rr-tushare-search` | 研报搜索 | `rr-tushare-search -q "半导体" --industry "电子"` |
| `rr-tushare-fetch` | 研报 PDF 转 Markdown | `rr-tushare-fetch --url "..." --topic "研究主题" --save ./report.md` |
| `rr-log` | 查看研究日志 | `rr-log list`, `rr-log show <session-id>` |

---

## 螺旋研究工作流

RealResearch 的核心思想是**螺旋式深度研究**——每一轮研究都不是从零开始，而是基于已有知识继续深入。

```
Phase 0: Initialize     → 环境检查、更新研报索引
Phase 1: Grounding      → 回忆已有知识（rr-recall）
Phase 2: Gap Analysis   → 分析知识缺口，制定搜索计划
Phase 3: Deep Search    → 双通道搜索（网页 + 研报）
Phase 4: Immediate Retain → 立即存储发现（rr-retain）
Phase 5: Connection Recall → 再次回忆，发现交叉关联
Phase 6: Convergence Check → 判断继续深入还是收敛
Phase 7: Reflect        → 综合分析所有记忆（rr-reflect）
Phase 8: Final Report   → 生成最终报告（rr-report）
```

### 示例

```bash
# 创建研究库
rr-bank create --id coal-chem --name "煤化工研究"

# Spiral 1: 搜索并存储
rr-search -q "煤化工设备市场规模 2026" -n 8
rr-retain -c "..." -b coal-chem --context "Spiral 1"

# Spiral 2: 基于已有知识深入
rr-recall -q "煤化工设备" -b coal-chem
rr-tushare-search -q "煤化工" --industry "化工" -n 5
rr-tushare-fetch --url "..." --topic "煤化工设备" --save ./report.md
rr-retain -c "..." -b coal-chem --context "Spiral 2"

# 综合分析并生成报告
rr-reflect -q "煤化工设备供应和工程服务企业分析" -b coal-chem --budget high
```

---

## 可选配置

```bash
# 使用外部 PostgreSQL（留空则自动启动 pg0-embedded）
RR_DATABASE_URL=postgresql://user:pass@localhost:5432/hindsight

# 默认记忆库
RR_DEFAULT_BANK=deep-research

# 各阶段独立指定 LLM
RR_RETAIN_LLM_PROVIDER=openai
RR_REFLECT_LLM_PROVIDER=openai
```

---

## 项目结构

```
RealResearch/
├── real_research/              # Python 源码
│   ├── engine.py               # MemoryEngine 生命周期 + MiMo 兼容修复
│   ├── config.py               # RR_* 统一配置读取
│   ├── search.py               # rr-search（网页搜索）
│   ├── fetch.py                # rr-fetch（网页抓取）
│   ├── retain.py               # rr-retain（存入记忆）
│   ├── recall.py               # rr-recall（检索记忆）
│   ├── reflect.py              # rr-reflect（深度反思）
│   ├── report.py               # rr-report（保存报告）
│   ├── bank.py                 # rr-bank（记忆库管理）
│   ├── route.py                # rr-route（智能路由）
│   ├── tushare_index.py        # rr-tushare-index（研报索引）
│   ├── tushare_search.py       # rr-tushare-search（研报搜索）
│   ├── tushare_fetch.py        # rr-tushare-fetch（研报蒸馏）
│   ├── log_view.py             # rr-log（日志查看）
│   ├── logger.py               # 会话日志记录
│   ├── env_check.py            # rr-env-check（环境检查）
│   └── utils.py                # 共享工具
├── hindsightbase/              # Hindsight 引擎（git clone）
├── pyproject.toml              # 项目配置 + CLI 入口点
├── .env.example                # 配置模板
├── SKILL.md                    # Agent 工作流指南
└── README.md                   # 本文件
```

---

## 技术特色

- **螺旋研究**：每轮基于已有知识，逐步深入
- **双通道搜索**：网页实时性 + 研报专业性
- **智能蒸馏**：必选 + 自由维度，LLM 自适应提取研报洞察
- **持久记忆**：跨会话、跨研究方向的知识积累
- **实体图谱**：自动关联实体，发现隐藏关系
- **非侵入式**：不修改 Hindsight 源码，通过 monkey-patch 兼容
- **全链路日志**：每步操作可追溯、可复盘

---

## 相关链接

- **Hindsight 文档**: https://hindsight.vectorize.io
- **Hindsight 论文**: https://arxiv.org/abs/2512.12818
- **Hindsight 源码**: https://github.com/vectorize-io/hindsight

---

## License

MIT — Built on top of [Hindsight](https://github.com/vectorize-io/hindsight) by Vectorize.io.
