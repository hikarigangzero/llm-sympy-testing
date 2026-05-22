# LLM-SymPy-Testing

> **智能化软件开发与测试技术 课程大作业**  
> 大模型赋能的软件测试案例研究 —— 以 SymPy simplify 模块为例

---

## 项目概述

本项目以开源数学库 [SymPy](https://github.com/sympy/sympy)（GitHub 12k+ stars）的 `simplify` 模块为真实软件对象，研究大语言模型（LLM）如何赋能软件测试活动。

核心思路：设计三阶段 LLM 测试生成流水线（初始生成 → 覆盖率缺口补充 → 变异杀死测试），与人工编写的基线测试进行覆盖率、变异分数等维度的定量对比，并系统分析 LLM 在测试生成中的失败模式与兜底机制。

### 关键实验结果

| 指标 | 人工基线 | LLM Round 1 |
|------|:---:|:---:|
| simplify.py 覆盖率 | 37.8% | **39.4%** ✨ |
| 测试函数数 | 51 | 78 |
| 可执行率 | 100% | 75.6% |
| 综合评分 | 75.1 | **75.8** |

---

## 目录结构

```
llm-sympy-testing/
├── README.md                    # 本文件（项目说明与复现步骤）
├── requirements.txt             # Python 依赖
├── .env                         # API Key（不提交到 Git）
├── .gitignore
│
├── sympy/                       # SymPy 官方源码（需要 clone 到本地）
│   └── sympy/simplify/          # 本次实验的被测模块
│
├── my_tests/
│   ├── baseline/                # 人工基线测试（已写好，无需重新生成）
│   │   └── test_simplify_manual.py    # 51 个人工测试用例
│   ├── generated/               # LLM 生成的测试文件
│   │   ├── round1_initial.py         # Round 1: 初始生成
│   │   ├── round2_coverage.py        # Round 2: 覆盖率缺口补充
│   │   └── round3_mutation.py        # Round 3: 变异杀死测试（可选）
│   ├── logs/
│   │   └── generation_log.jsonl      # LLM 调用日志
│   └── results/                      # 所有实验结果
│       ├── coverage_baseline.json    # 基线覆盖率
│       ├── coverage_round1.json      # Round 1 覆盖率
│       ├── coverage_round2.json      # Round 2 覆盖率
│       ├── mutation_score_baseline.txt
│       ├── mutation_score_round1.txt
│       └── mutation_score_round2.txt
│
├── scripts/
│   ├── generate_tests.py        # LLM 测试生成（核心脚本，支持 4 种模式）
│   ├── run_coverage.py          # 覆盖率分析（pytest + coverage.py）
│   ├── run_mutation.py          # 变异测试（BSR/CRR/ROR 算子）
│   ├── compare_results.py       # 结果对比与综合评分
│   └── utils.py                 # 公共函数（代码提取、编译验证、导入修复）
│
├── prompts/
│   ├── initial_generation.txt   # Round 1 Prompt 模板
│   ├── coverage_gap.txt         # Round 2 Prompt 模板
│   └── mutation_killing.txt     # Round 3 Prompt 模板
│
└── report/
    └── 实验报告.md               # 完整实验报告（4000+ 字）
```

---

## 复现步骤

### 前置条件

- Python >= 3.9
- 可用的 DeepSeek API Key（或 OpenAI 兼容 API）

### Step 0: 环境准备

```bash
# 克隆本仓库
git clone <your-repo-url>
cd llm-sympy-testing

# 安装 Python 依赖
pip install -r requirements.txt

# 克隆 SymPy 源码并安装
git clone https://github.com/sympy/sympy.git
cd sympy && pip install -e . && cd ..

# 配置 API Key
cp .env.example .env   # 或直接编辑 .env
# 编辑 .env，填入你的 API Key:
#   DEEPSEEK_API_KEY=sk-xxxx
#   DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
#   LLM_MODEL=deepseek-v4-flash
```

### Step 1: 运行人工基线覆盖率

```bash
python scripts/run_coverage.py \
  --test-file my_tests/baseline/test_simplify_manual.py \
  --output coverage_baseline \
  --target-file sympy/simplify/simplify.py
```

> 预期 simplify.py 约 37-38% 覆盖率。生成 `my_tests/results/coverage_baseline.json`

### Step 2: LLM Round 1 —— 批量生成初始测试

```bash
python scripts/generate_tests.py batch --output-dir my_tests/generated
```

> 调用 DeepSeek API 为 8 个函数生成测试，约需 1-2 分钟。生成的文件：`my_tests/generated/round1_initial.py`

### Step 3: 验证 Round 1 测试

```bash
cd sympy && python -m pytest ../my_tests/generated/round1_initial.py -v --tb=short 2>&1 | tail -30
cd ..
```

> 预期：约 59 passed, 18 failed。失败主要由 LLM 幻觉导致（详见报告第 6 节）

### Step 4: Round 1 覆盖率分析

```bash
python scripts/run_coverage.py \
  --test-file my_tests/generated/round1_initial.py \
  --output coverage_round1 \
  --target-file sympy/simplify/simplify.py
```

> 预期 simplify.py 约 39-40% 覆盖率

### Step 5: LLM Round 2 —— 覆盖率缺口补充

```bash
python scripts/generate_tests.py coverage \
  --uncovered my_tests/results/uncovered_lines_coverage_round1.txt \
  --source-file sympy/sympy/simplify/simplify.py \
  --existing-test my_tests/generated/round1_initial.py \
  --output my_tests/generated/round2_coverage.py
```

> Prompt 会自动过滤和截断，将约 192 万字符压缩到约 1.5 万字符以适配模型上下文窗口

### Step 6: 验证 Round 2 测试

```bash
cd sympy && python -m pytest ../my_tests/generated/round2_coverage.py -v --tb=short 2>&1 | tail -20
cd ..
```

### Step 7: Round 2 覆盖率分析

```bash
python scripts/run_coverage.py \
  --test-file my_tests/generated/round2_coverage.py \
  --output coverage_round2 \
  --target-file sympy/simplify/simplify.py
```

### Step 8: 变异测试 —— 人工基线

```bash
python scripts/run_mutation.py \
  --source sympy/sympy/simplify/simplify.py \
  --test my_tests/baseline/test_simplify_manual.py \
  --output my_tests/results/mutation_score_baseline.txt \
  --max-mutants 15
```

### Step 9: 变异测试 —— LLM Round 1

```bash
python scripts/run_mutation.py \
  --source sympy/sympy/simplify/simplify.py \
  --test my_tests/generated/round1_initial.py \
  --output my_tests/results/mutation_score_round1.txt \
  --max-mutants 15
```

### Step 10: 变异测试 —— LLM Round 2

```bash
python scripts/run_mutation.py \
  --source sympy/sympy/simplify/simplify.py \
  --test my_tests/generated/round2_coverage.py \
  --output my_tests/results/mutation_score_round2.txt \
  --max-mutants 15
```

### Step 11: 生成最终对比报告

```bash
python scripts/compare_results.py
```

> 输出五段对比内容：测试数量统计、覆盖率对比表、变异测试对比表、综合评分、分析要点

---

## 测试目标函数

| 函数 | 源文件 | 功能描述 |
|------|--------|---------|
| `simplify` | `sympy/simplify/simplify.py` | 通用表达式化简（~400 行，最复杂） |
| `separatevars` | 同上 | 多变量表达式分离 |
| `signsimp` | 同上 | 符号规范化处理 |
| `logcombine` | 同上 | 对数合并 |
| `posify` | 同上 | 符号正定性假设替换 |
| `hypersimp` | 同上 | 超几何项化简 |
| `inversecombine` | 同上 | 反函数组合化简 |
| `nthroot` | 同上 | n 次方根数值计算 |

---

## LLM 失败模式速览

实验中发现 LLM 生成测试存在 6 种典型失败模式（详见报告第 6 节）：

| 模式 | 严重程度 | 是否可自动修复 |
|------|:---:|:---:|
| 语法错误（散落 `"""`） | 致命 | ✅ 部分 |
| 导入幻觉（虚构模块路径） | 致命 | ✅ 可自动 |
| 语义幻觉（错误断言） | 中等 | ❌ 需人工 |
| 死循环触发 | 致命 | ❌ 需人工 |
| 过度注释/推理混入 | 轻微 | ✅ 可自动 |
| 计算爆炸 | 致命 | ❌ 需人工 |

项目中已实现 `validate_and_fix_code()` 自动修复函数处理约 40% 的失败模式，剩余需人工审核。

---

## 依赖

```
openai
python-dotenv
coverage
pytest
sympy (editable install from ./sympy/)
```

---

## 作者

- 学号：[SC2616041]  姓名：[杨余松]
- 课程：智能化软件开发与测试技术，2026 春季学期
- 完整实验报告：`report/SC2616041-杨余松-智能化软件开发与测试技术大作业报告.pdf`

