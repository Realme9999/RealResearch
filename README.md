# RealResearch — 螺旋式深度研究，持久化记忆

> **基于 [Hindsight](https://github.com/vectorize-io/hindsight) 的长期记忆引擎，零侵入引用，开箱即用。**

RealResearch 是一套面向深度研究（Deep Research）场景的 CLI 工具集。它将网络搜索、研报分析、记忆存储、智能检索和反思推理串联成一个**螺旋迭代工作流**，让研究过程具备**持久化记忆**和**跨会话积累**能力。

---

## 技术架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent / User                              │
│                    （Claude Code 或其他 Agent）                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ 调用 CLI 工具
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RealResearch CLI 层                            │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │rr-search │ │rr-fetch  │ │rr-retain │ │rr-recall │           │
│  │ 网页搜索  │ │ 网页抓取  │ │ 存入记忆  │ │ 检索记忆  │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       │            │            │            │                   │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                  │
│  │rr-tushare- │ │rr-tushare- │ │rr-tushare- │  ...             │
│  │index       │ │search      │ │fetch       │                   │
│  │ 研报索引    │ │ 研报搜索    │ │ 研报蒸馏    │                   │
│  └────┬───────┘ └────┬───────┘ └────┬───────┘                  │
│       │            │            │            │                   │
│  ┌────┴────────────┴────────────┴────────────┴────┐             │
│  │              Hindsight MemoryEngine              │             │
│  │                                                  │             │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐     │             │
│  │  │ Fact      │ │ Entity    │ │ Vector    │     │             │
│  │  │ Extraction│ │ Graph     │ │ Search    │     │             │
│  │  └───────────┘ └───────────┘ └───────────┘     │             │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐     │             │
│  │  │ BM25      │ │ Temporal  │ │ Reranker  │     │             │
│  │  │ Search    │ │ Search    │ │ (Cohere)  │     │             │
│  │  └───────────┘ └───────────┘ └───────────┘     │             │
│  └──────────────────────┬──────────────────────────┘             │
│                         │                                        │
└─────────────────────────┼────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PostgreSQL + pgvector                        │
│              （持久化存储：facts、entities、embeddings）             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心技术原理

### 1. 螺旋研究法（Spiral Methodology）

传统研究是**线性**的：搜索 → 阅读 → 写报告，一次性完成，没有记忆。

RealResearch 是**螺旋**的：每一轮研究都在已有知识基础上推进，像螺旋楼梯一样逐层上升。

```
        第 3 轮：交叉验证 + 深挖细节
       ╱
      ╱   第 2 轮：定向填补缺口
     ╱   ╱
    ╱   ╱   第 1 轮：从零开始搜索
   ╱   ╱   ╱
  ╱   ╱   ╱
 ╱   ╱   ╱
━━━━━━━━━━━━━━  → 知识库持续增长
```

**为什么叫"螺旋"？** 因为每一轮都会回到同一个研究主题，但视角更深、信息更全。第 1 轮搜索"煤化工设备市场规模"，第 2 轮基于已有知识搜索"煤化工设备国产化率"，第 3 轮发现矛盾后搜索"煤化工设备技术壁垒"。每一轮都在上一轮的基础上推进。

**8 个阶段：**

| 阶段 | 名称 | 做什么 | 核心工具 |
|------|------|--------|---------|
| Phase 0 | Initialize | 环境检查、更新研报索引 | `rr-env-check`, `rr-tushare-index` |
| Phase 1 | Grounding | 回忆已有知识，找到起点 | `rr-recall` |
| Phase 2 | Gap Analysis | 分析知识缺口，制定搜索计划 | LLM 推理 |
| Phase 3 | Deep Search | 双通道搜索（网页 + 研报） | `rr-search`, `rr-tushare-search` |
| Phase 4 | Immediate Retain | 立即存储发现，不等到最后 | `rr-retain` |
| Phase 5 | Connection Recall | 再次回忆，发现交叉关联 | `rr-recall` |
| Phase 6 | Convergence Check | 判断继续还是收敛 | LLM 推理 |
| Phase 7 | Reflect | 综合分析所有记忆 | `rr-reflect` |
| Phase 8 | Final Report | 生成结构化报告 | `rr-report` |

### 2. 记忆引擎：Hindsight

RealResearch 的记忆能力来自 [Hindsight](https://github.com/vectorize-io/hindsight)——一个仿生学的 AI 记忆系统。

#### 记忆的结构

Hindsight 不是简单地存储文本，而是将信息分解为结构化的 **Fact**（事实）：

```
输入文本："中国化学2025年营收1895亿元，新签合同额首次突破4000亿元。"
    ↓ LLM 提取
Fact 1: {
    what: "中国化学2025年营收1895亿元",
    when: "2025年",
    where: "N/A",
    who: "中国化学",
    fact_type: "world"
}
Fact 2: {
    what: "新签合同额首次突破4000亿元",
    when: "2025年",
    where: "N/A",
    who: "中国化学",
    fact_type: "world"
}
```

#### 记忆的检索

`rr-recall` 使用 **4 路并行检索** + **重排序**：

| 检索策略 | 原理 | 擅长 |
|---------|------|------|
| **语义检索** | 向量相似度（pgvector） | "算力需求" 能匹配到 "AI芯片出货量" |
| **BM25 关键词** | 词频匹配 | 精确名词匹配，如公司名、产品型号 |
| **实体图谱** | 实体关联扩展 | 找到与"华为"相关的所有记忆 |
| **时间检索** | 时间范围过滤 | "最近一个月的发现" |

4 路结果通过 **Reciprocal Rank Fusion** 融合，再用 **Cohere Reranker** 重排序，返回最相关的结果。

#### 记忆的反思

`rr-reflect` 不是简单的总结，而是**结构化推理**：

```
输入：所有已存储的 memories
    ↓
LLM 分析：
- 核心发现有哪些？
- 有哪些矛盾？如何解决？
- 实体之间有什么关联？
- 哪些信息可信度高/低？
    ↓
输出：结构化反思报告（reflect.json + reflect.md）
```

### 3. 双通道搜索

RealResearch 同时支持两个搜索通道，互补使用：

#### 通道 1：网页搜索（Tavily）

- **优势**：实时性强，覆盖新闻、博客、论坛、官网
- **工具链**：`rr-search` → `rr-fetch`
- **适用**：最新动态、政策变化、市场情绪

#### 通道 2：研报搜索（Tushare）

- **优势**：专业深度，7000+ 篇券商研报，结构化数据
- **工具链**：`rr-tushare-index` → `rr-tushare-search` → `rr-tushare-fetch`
- **适用**：行业分析、公司财务、估值逻辑

两个通道的数据统一经过 `rr-retain` 存入 Hindsight，形成完整的知识库。

### 4. 研报智能蒸馏

研报 PDF 通常 50-100KB，直接存入记忆系统会导致噪声过大、语义碎片化。RealResearch 采用**分层蒸馏**策略：

```
研报 PDF（50-100KB）
    ↓ rr-tushare-fetch --topic "研究主题"
    ↓
┌─────────────────────────────────────┐
│ Layer 1: 摘要层（搜索结果自带）      │  ← 即时可用，~500字
├─────────────────────────────────────┤
│ Layer 2: 结构化洞察（LLM 蒸馏）      │  ← 存入记忆，~2-3KB
│   必选：核心观点/关键数据/投资建议/风险│
│   自由：模型根据内容自选维度          │
├─────────────────────────────────────┤
│ Layer 3: 全文存文件（--save）         │  ← 本地参考，50-100KB
└─────────────────────────────────────┘
```

**蒸馏模板设计**：采用"必选维度 + 自由维度"的灵活结构。

- **必选维度**（每篇都有）：核心观点、关键数据、投资建议、风险提示
- **自由维度**（模型自选）：产业链分析、竞争格局、订单/合同、产能利用率、政策因素等

模型根据研报内容和研究主题自行判断哪些维度最重要，不被固定模板限制。比如研究"煤化工设备供应商"时，模型会自动选择"下游龙头企业动态"这个维度，分析客户的资本开支对设备需求的影响。

### 5. 记忆库（Bank）隔离

不同研究方向的记忆存储在独立的 **Bank** 中，互不干扰：

```
Bank: china-gpu          → 国产 GPU 研究的所有记忆
Bank: coal-chem          → 煤化工研究的所有记忆
Bank: crypto-markets     → 加密货币研究的所有记忆
```

- 每个 Bank 有独立的 facts、entities、embeddings
- `rr-recall` 只在指定 Bank 内检索
- `rr-route` 可以根据查询自动路由到最匹配的 Bank
- 相关子主题可以共享同一个 Bank，便于交叉引用

### 6. 全链路日志

每次研究会话自动记录每个步骤的输入、输出、耗时、token 消耗：

```
Logs/sessions/
├── abc123/
│   ├── session.json          # 会话元数据
│   ├── step_001_search.json  # 第 1 步：搜索
│   ├── step_002_retain.json  # 第 2 步：存储
│   ├── step_003_recall.json  # 第 3 步：检索
│   └── ...
└── def456/
    └── ...
```

支持事后复盘：哪些搜索查询效果好、哪些研报最有价值、token 消耗分布等。

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
| `rr-tushare-fetch` | 研报蒸馏 | `rr-tushare-fetch --url "..." --topic "主题" --save ./report.md` |
| `rr-log` | 查看研究日志 | `rr-log list`, `rr-log show <session-id>` |

---

## 使用示例

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
RR_DATABASE_URL=postgresql://your_user:your_password@your_host:5432/your_database

# 默认记忆库
RR_DEFAULT_BANK=deep-research

# 各阶段独立指定 LLM
RR_RETAIN_LLM_PROVIDER=openai
RR_REFLECT_LLM_PROVIDER=openai
```

---

## 作为 Agent Skill 使用

RealResearch 不仅是独立的 CLI 工具，还可以作为 **Skill** 集成到各种 AI Agent 中，让 Agent 具备深度研究能力。

### 什么是 Skill？

Skill 是一种可复用的能力模块。Agent 通过调用 Skill，可以获得超出其自身知识范围的专业能力。RealResearch 就是一个"深度研究 Skill"——给 Agent 一个研究问题，它能自动搜索、分析、记忆、迭代，最终输出结构化报告。

### 支持的 Agent 平台

| 平台 | 集成方式 |
|------|---------|
| **Claude Code** | 将 `SKILL.md` 放入 `.claude/skills/` 目录，Claude 会自动识别并调用 |
| **其他支持 Skill 的 Agent** | 将 `SKILL.md` 作为能力描述文件，Agent 根据指引调用 CLI 工具 |

### 集成示例（Claude Code）

```bash
# 将 RealResearch 注册为 Claude Code 的 Skill
cp SKILL.md ~/.claude/skills/real-research.md
```

之后在 Claude Code 中，只需说：

```
帮我深度研究一下 2026 年国产 AI 算力产业链
```

Claude 会自动按照 SKILL.md 中定义的螺旋工作流，调用 `rr-search`、`rr-retain`、`rr-recall`、`rr-reflect` 等工具完成研究。

### 为什么用 Skill？

- **标准化工作流**：SKILL.md 定义了完整的研究流程（8 个阶段），Agent 不会遗漏步骤
- **持久化记忆**：研究结果存入 Hindsight，下次研究同领域可直接复用
- **可复用**：同一个 Skill 可以被不同 Agent、不同项目调用
- **可迭代**：升级 RealResearch 代码，所有使用该 Skill 的 Agent 自动获得新能力

---

## 项目结构

```
RealResearch/
├── real_research/              # Python 源码
│   ├── engine.py               # MemoryEngine 生命周期
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

## 相关链接

- **Hindsight 文档**: https://hindsight.vectorize.io
- **Hindsight 论文**: https://arxiv.org/abs/2512.12818
- **Hindsight 源码**: https://github.com/vectorize-io/hindsight

---

## License

MIT — Built on top of [Hindsight](https://github.com/vectorize-io/hindsight) by Vectorize.io.
