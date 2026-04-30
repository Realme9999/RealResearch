# RealResearch Skill — 螺旋式深度研究，持久化记忆

> **基于 [Hindsight](https://github.com/vectorize-io/hindsight) 的长期记忆引擎，零侵入引用，开箱即用。**

RealResearch 是一套面向深度研究（Deep Research）场景的 CLI 工具集。它将网络搜索、网页抓取、记忆存储、智能检索和反思推理串联成一个**螺旋迭代工作流**，让 AI 研究过程具备**持久化记忆**和**跨会话积累**能力。

---

## 🚀 新电脑快速启动（3 步）

### 1. 克隆 Hindsight 引擎

```bash
# 在与本文件夹（RRskills）同级的目录下执行：
git clone https://github.com/vectorize-io/hindsight.git hindsightbase
```

> **目录关系要求**：`hindsightbase/` 必须位于 `RRskills/` 的**父目录**或**同级目录**。示例：
> ```
> your-workspace/
> ├── hindsightbase/          # ← git clone 得到
> │   └── hindsight-api-slim/
> └── RRskills/               # ← 本文件夹
>     ├── real_research/
>     └── ...
> ```

### 2. 安装依赖

```bash
# 进入 RRskills 目录
cd RRskills

# 推荐用 uv
uv pip install -e .

# 或传统 pip
pip install -e .

# 如需零配置嵌入式数据库（自动启动本地 PostgreSQL）
uv pip install -e ".[embedded-db]"
# 或
pip install -e ".[embedded-db]"
```

### 3. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 4 个 API Key
```

| 变量 | 用途 | 获取地址 |
|------|------|---------|
| `RR_EMBEDDING_API_KEY` | 文本嵌入 | [SiliconFlow](https://siliconflow.cn)（默认 Qwen3-Embedding-4B）|
| `RR_RERANK_API_KEY` | 结果重排序 | [SiliconFlow](https://siliconflow.cn)（默认 Qwen3-Reranker-8B）|
| `RR_LLM_API_KEY` | LLM 推理 | [Groq](https://groq.com) 或任意 OpenAI 兼容服务 |
| `RR_SEARCH_API_KEY` | 网络搜索 | [Tavily](https://tavily.com)（免费额度充足）|
| `RR_TUSHARE_TOKEN` | Tushare 研报索引（可选）| [Tushare](https://tushare.pro) |

---

## ✅ 验证安装

```bash
rr-env-check
```

全部通过即可开始使用。

---

## 📚 CLI 工具速查

| 命令 | 功能 | 典型用法 |
|------|------|---------|
| `rr-search` | 网络搜索 | `rr-search -q "量子计算最新进展" -n 8` |
| `rr-fetch` | 网页抓取 | `rr-fetch -u https://... -m 20000` |
| `rr-retain` | 存入记忆 | `rr-retain -c "...发现..." -b ai-chips` |
| `rr-recall` | 检索记忆 | `rr-recall -q "昇腾技术参数" -b ai-chips` |
| `rr-reflect` | 深度反思 | `rr-reflect -q "综合分析" -b ai-chips --budget high` |
| `rr-report` | 保存报告 | `rr-report -q "主题" -c "## 内容..."` |
| `rr-bank` | 库管理 | `rr-bank list`, `rr-bank create --id ...` |
| `rr-route` | 智能路由 | `rr-route -q "AI芯片"` |
| `rr-tushare-index` | 研报索引构建 | `rr-tushare-index --months 3` |
| `rr-tushare-search` | 研报搜索 | `rr-tushare-search -q "半导体" -i "电子"` |
| `rr-tushare-fetch` | 研报PDF转Markdown | `rr-tushare-fetch --url "https://..." ` |

---

## 🌀 Spiral 深度研究工作流

```bash
# Step 1: 创建研究库
rr-bank create --id china-ai-chips --name "国产AI芯片研究" --tags "半导体,算力"

# Step 2: Spiral 1 — 搜索并保存初始素材
rr-search -q "2026年国产GPU市场份额 华为昇腾 寒武纪" -n 8
# → 将搜索结果 retain 到库中

# Step 3: Spiral 2 — 深入技术细节
rr-search -q "昇腾950PR FP4算力 HBM 价格 集群" -n 8
# → retain 到库中

# Step 4: 深度反思，生成报告
rr-reflect -q "国产算力卡发展现状综合分析" \
           -b china-ai-chips \
           --budget high \
           --max-tokens 32768
# 报告自动保存到 Reports/ 目录
```

---

## ⚙️ 可选配置

```bash
# 使用外部 PostgreSQL（留空则自动启动 pg0-embedded）
RR_DATABASE_URL=postgresql://user:pass@localhost:5432/hindsight

# 默认记忆库
RR_DEFAULT_BANK=deep-research

# 各阶段独立指定 LLM
RR_RETAIN_LLM_PROVIDER=groq
RR_REFLECT_LLM_PROVIDER=groq
```

---

## 📁 项目结构

```
RRskills/
├── real_research/          # 应用层源码
│   ├── engine.py           # MemoryEngine 生命周期 + 配置翻译
│   ├── config.py           # RR_* 统一配置读取
│   ├── search.py           # rr-search
│   ├── fetch.py            # rr-fetch
│   ├── retain.py           # rr-retain
│   ├── recall.py           # rr-recall
│   ├── reflect.py          # rr-reflect
│   ├── report.py           # rr-report
│   ├── bank.py             # rr-bank
│   ├── route.py            # rr-route
│   ├── env_check.py        # rr-env-check
│   └── utils.py            # 共享工具
├── Reports/                # 默认报告输出目录
├── pyproject.toml          # 项目配置 + CLI 入口点
├── .env.example            # 配置模板
└── README.md               # 本文件
```

---

## 🔗 Hindsight 参考

- **文档**: https://hindsight.vectorize.io
- **论文**: https://arxiv.org/abs/2512.12818
- **源码**: https://github.com/vectorize-io/hindsight

---

## License

MIT — Built on top of [Hindsight](https://github.com/vectorize-io/hindsight) by Vectorize.io.
