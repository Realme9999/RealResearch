# RealResearch 研究实例

以下两个研究项目展示了 RealResearch 螺旋式深度研究框架的实际应用效果。

---

## 实例一：中国国产 AI 芯片研究（china-gpu）

> **研究问题**：中国国产 GPU / AI 芯片产业全景分析——技术路线、市场格局、财务数据与估值

### Bank 信息

| 字段 | 值 |
|------|-----|
| Bank ID | `china-gpu` |
| 研究主题 | 中国国产 AI 芯片 |
| 记忆条数 | **875 条** |
| 覆盖厂商 | 华为昇腾、寒武纪、海光信息、摩尔线程、沐曦、壁仞、天数智芯、燧原、百度昆仑芯 |
| 研究维度 | 财务数据、产品技术路线、市场格局与市占率、估值分析、竞争动态与供应链 |

### 研究过程

研究经历了多轮螺旋迭代，每轮聚焦不同维度：

```
Spiral 1: 国产算力卡 2024-2025 年发展现状
  → 搜索各厂商最新产品发布、技术参数、市场动态
  → 存入 200+ 条基础事实

Spiral 2: 财务数据与盈利预测
  → 搜索海光信息、寒武纪等上市公司财报数据
  → 存入营收、利润、合同负债、估值等结构化数据

Spiral 3: 竞争格局与客户结构
  → 分析各厂商客户集中度、下游应用场景
  → 发现寒武纪对字节跳动依赖度高（79.15%）

Spiral 4: 产业链上下游
  → 研究 HBM 存储、先进封装、EDA 工具等上游环节
  → 分析下游 AI 训练/推理需求变化
```

### 记忆库中的数据样例

**华为昇腾 910C 技术参数**：
> 昇腾910C 采用达芬奇架构 3.0，FP16 算力 352 TFLOPS，INT8 算力 704 TOPS，中芯国际 7nm（N+2）工艺，功耗 310W。DeepSeek V4 全面适配昇腾全系列。

**华为昇腾产品线**：
> 训练卡：昇腾910C、昇腾910B。推理卡：Atlas 350（昇腾950PR），2026年3月发布，国内唯一支持 FP4 低精度推理，FP4 算力 1.56P，HBM 112GB，带宽 1.4TB/s，单卡算力达 H20 的 2.87 倍。

**海光信息财务数据**：
> 2026Q1 营收 40.34 亿元（同比 +68.06%），归母净利润 6.87 亿元（同比 +35.82%）。2025 年净利润 19.61 亿元，首次实现全年盈利。2026 年预测净利润 28-32 亿元。

**寒武纪财务与估值**：
> 2025 年营收 64.97 亿元，净利润 20.59 亿元，首次实现全年盈利。2026 年预测营收 209.44 亿元，净利润 61.56 亿元。MLU590 在字节跳动大规模部署，市占率约 4%。

### 数据来源

- 网页搜索（Tavily）：新闻、公告、行业报告
- 券商研报（Tushare）：华鑫证券、中信建投、国泰君安等机构研报
- 蒸馏存储：研报全文通过 LLM 蒸馏后存入结构化洞察

---

## 实例二：全球 AI 硬件研究（global-ai-hardware）

> **研究问题**：全球 AI 硬件产业——NVIDIA 生态、竞品格局、技术路线图

### Bank 信息

| 字段 | 值 |
|------|-----|
| Bank ID | `global-ai-hardware` |
| 研究主题 | 全球 AI 硬件（超越 NVIDIA 视角） |
| 记忆条数 | **242 条** |
| 覆盖范围 | NVIDIA 全产品线、AMD MI 系列、Google TPU、Cerebras、Groq、Microsoft Maia、Intel Gaudi |
| 研究维度 | 技术架构演进、软件生态、HBM 与先进封装、训练/推理架构创新、市场竞争格局 |

### 研究过程

```
Spiral 1: NVIDIA GTC 2026 发布内容
  → 搜索 Blackwell Ultra、Vera Rubin、Feynman 架构路线图
  → 存入产品发布时间线、技术参数

Spiral 2: 竞品生态分析
  → 搜索 AMD MI400、Google TPU v6、Cerebras WSE-3
  → 存入各竞品的算力、功耗、客户案例

Spiral 3: HBM 与先进封装
  → 搜索 HBM4、CoWoS、3D 堆叠技术进展
  → 存入存储带宽、封装产能等供应链数据

Spiral 4: 软件生态与护城河
  → 研究 CUDA 生态、ROCm、oneAPI 等竞争态势
  → 分析 NVIDIA 软件护城河的可持续性
```

### 记忆库中的数据样例

**NVIDIA 路线图**：
> NVIDIA Feynman 架构定于 2028 年发布，作为 Rubin/Rubin Ultra 的继任者，采用先进 3D 堆叠技术、定制 HBM 内存和 Rosa CPU 平台。

**Vera Rubin 时间线**：
> NVIDIA Vera Rubin NVL72 机架将于 2026 年下半年上市。

**竞品对比**：
> AMD MI400 系列对标 NVIDIA Blackwell，Google TPU v6 面向云原生训练优化，Cerebras WSE-3 晶圆级处理器在特定工作负载下展现数量级优势。

### 与 china-gpu 的交叉引用

两个 Bank 的研究存在自然交叉：
- china-gpu 研究华为昇腾时，需要对比 NVIDIA 的技术参数 → 从 global-ai-hardware 中 recall
- global-ai-hardware 研究竞品时，需要了解中国厂商进展 → 从 china-gpu 中 recall

这种跨 Bank 的信息互补，正是螺旋研究的价值——不同研究方向的知识可以互相印证和补充。

---

## 如何复现

### 创建研究 Bank

```bash
# 创建 Bank
rr-bank create --id china-gpu --name "China GPU & AI Chips"
rr-bank create --id global-ai-hardware --name "Global AI Hardware Beyond NVIDIA"
```

### 按螺旋工作流研究

```bash
# --- Spiral 1: 基础信息 ---

# 网页搜索
rr-search -q "华为昇腾910C 最新进展 2026" -n 8
rr-retain -c "<搜索结果摘要>" -b china-gpu --context "Spiral 1"

# 研报搜索
rr-tushare-search -q "国产GPU 算力" --mode semantic -n 5
rr-tushare-fetch --url "<pdf_url>" --topic "国产GPU" --save ./reports/gpu_report.md
rr-retain -c "<蒸馏后的结构化洞察>" -b china-gpu --context "Spiral 1, 来源: 研报"

# --- Spiral 2: 基于已有知识深入 ---

# 回忆已有知识
rr-recall -q "海光信息 财务数据" -b china-gpu

# 发现缺口：缺少估值数据，定向搜索
rr-search -q "海光信息 估值 PE 2026" -n 8
rr-retain -c "<新发现>" -b china-gpu --context "Spiral 2"

# --- 综合分析 ---

# 反思所有记忆
rr-reflect -q "国产AI芯片产业综合分析" -b china-gpu --budget high

# 生成报告
rr-report -q "国产AI芯片产业分析报告" -c "## 完整报告内容..."
```

### 查看研究日志

```bash
# 列出所有研究会话
rr-log list

# 查看某次会话详情
rr-log show <session-id>
```
