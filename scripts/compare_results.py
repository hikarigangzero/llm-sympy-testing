"""
实验结果对比脚本

读取覆盖率 JSON 报告和变异测试结果，生成对比表格和可视化。

用法:
  python scripts/compare_results.py
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any


def find_json_files(directory: Path, pattern: str) -> List[Path]:
    """查找目录下匹配的 JSON 文件"""
    return sorted(directory.glob(pattern))


def load_coverage_summary(json_path: Path) -> Dict[str, Any]:
    """加载覆盖率 JSON 并提取摘要"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    totals = data.get("totals", {})
    files_data = data.get("files", {})

    # 找到 simplify.py 的文件级覆盖率
    simplify_coverage = {}
    for file_path, file_data in files_data.items():
        if "simplify/simplify.py" in file_path:
            simplify_coverage = file_data.get("summary", {})
            break

    return {
        "file": str(json_path.name),
        "overall_pct": totals.get("percent_covered", 0),
        "overall_covered": totals.get("covered_lines", 0),
        "overall_total": totals.get("num_statements", 0),
        "overall_missing": totals.get("missing_lines", 0),
        "simplify_pct": simplify_coverage.get("percent_covered", 0),
        "simplify_covered": simplify_coverage.get("covered_lines", 0),
        "simplify_total": simplify_coverage.get("num_statements", 0),
        "simplify_missing": simplify_coverage.get("missing_lines", 0),
    }


def load_mutation_score(txt_path: Path) -> Dict[str, Any]:
    """加载变异测试结果"""
    # 先尝试 .json
    json_path = txt_path.with_suffix(".json")
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # 解析文本报告
    result = {"total": 0, "killed": 0, "survived": 0, "mutation_score": 0}
    if txt_path.exists():
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()
            for line in content.splitlines():
                if "总数:" in line or "变异体总数:" in line:
                    try:
                        result["total"] = int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                if "已杀死:" in line:
                    try:
                        result["killed"] = int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                if "存活:" in line:
                    try:
                        result["survived"] = int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                if "变异分数:" in line:
                    try:
                        pct_str = line.split(":")[-1].strip().rstrip("%")
                        result["mutation_score"] = float(pct_str) / 100
                    except ValueError:
                        pass
    return result


def count_test_functions(test_file: Path) -> int:
    """统计测试文件中的测试函数数量"""
    if not test_file.exists():
        return 0
    with open(test_file, "r", encoding="utf-8") as f:
        content = f.read()
    import re
    return len(re.findall(r'^\s*def test_', content, re.MULTILINE))


def generate_comparison_table(baseline_cov: Dict, round1_cov: Dict,
                               round2_cov: Dict = None) -> str:
    """生成覆盖率对比表格"""
    rows = [
        ("指标", "人工基线", "LLM Round 1", "LLM Round 2"),
    ]

    # simplify.py 覆盖率
    rows.append((
        "simplify.py 覆盖率",
        f"{baseline_cov.get('simplify_pct', 0):.1f}%",
        f"{round1_cov.get('simplify_pct', 0):.1f}%",
        f"{round2_cov.get('simplify_pct', 0):.1f}%" if round2_cov else "N/A",
    ))

    rows.append((
        "simplify.py 覆盖行",
        str(baseline_cov.get('simplify_covered', 0)),
        str(round1_cov.get('simplify_covered', 0)),
        str(round2_cov.get('simplify_covered', 0)) if round2_cov else "N/A",
    ))

    rows.append((
        "simplify.py 总行数",
        str(baseline_cov.get('simplify_total', 0)),
        str(round1_cov.get('simplify_total', 0)),
        str(round2_cov.get('simplify_total', 0)) if round2_cov else "N/A",
    ))

    rows.append((
        "simplify.py 未覆盖行",
        str(baseline_cov.get('simplify_missing', 0)),
        str(round1_cov.get('simplify_missing', 0)),
        str(round2_cov.get('simplify_missing', 0)) if round2_cov else "N/A",
    ))

    # 整体覆盖率
    rows.append((
        "整体覆盖率",
        f"{baseline_cov.get('overall_pct', 0):.1f}%",
        f"{round1_cov.get('overall_pct', 0):.1f}%",
        f"{round2_cov.get('overall_pct', 0):.1f}%" if round2_cov else "N/A",
    ))

    # 格式化为 Markdown 表格
    col_widths = [25, 18, 18, 18]
    lines = []
    # header
    header = "| " + " | ".join(f"{r:<{w}}" for r, w in zip(rows[0], col_widths)) + " |"
    lines.append(header)
    lines.append("|" + "|".join("-" * (w + 2) for w in col_widths) + "|")
    for row in rows[1:]:
        line = "| " + " | ".join(f"{str(r):<{w}}" for r, w in zip(row, col_widths)) + " |"
        lines.append(line)

    return "\n".join(lines)


def generate_mutation_comparison(baseline_mut: Dict, round1_mut: Dict,
                                  round2_mut: Dict = None) -> str:
    """生成变异测试对比表格"""
    rows = [
        ("指标", "人工基线", "LLM Round 1", "LLM Round 2"),
        (
            "变异分数",
            f"{baseline_mut.get('mutation_score', 0):.1%}",
            f"{round1_mut.get('mutation_score', 0):.1%}",
            f"{round2_mut.get('mutation_score', 0):.1%}" if round2_mut else "N/A",
        ),
        (
            "杀死/总数",
            f"{baseline_mut.get('killed', 0)}/{baseline_mut.get('total', 0)}",
            f"{round1_mut.get('killed', 0)}/{round1_mut.get('total', 0)}",
            f"{round2_mut.get('killed', 0)}/{round2_mut.get('total', 0)}" if round2_mut else "N/A",
        ),
    ]

    col_widths = [20, 20, 20, 20]
    lines = []
    header = "| " + " | ".join(f"{r:<{w}}" for r, w in zip(rows[0], col_widths)) + " |"
    lines.append(header)
    lines.append("|" + "|".join("-" * (w + 2) for w in col_widths) + "|")
    for row in rows[1:]:
        line = "| " + " | ".join(f"{str(r):<{w}}" for r, w in zip(row, col_widths)) + " |"
        lines.append(line)

    return "\n".join(lines)


def main():
    results_dir = Path(__file__).parent.parent / "my_tests" / "results"

    print("=" * 70)
    print("SymPy simplify 模块 —— LLM 赋能测试实验结果对比")
    print("=" * 70)

    # =========================================================================
    # 1. 覆盖率对比
    # =========================================================================
    print("\n## 1. 测试函数数量统计\n")

    baseline_test = Path(__file__).parent.parent / "my_tests" / "baseline" / "test_simplify_manual.py"
    round1_test = Path(__file__).parent.parent / "my_tests" / "generated" / "round1_initial.py"
    round2_test = Path(__file__).parent.parent / "my_tests" / "generated" / "round2_coverage.py"

    baseline_count = count_test_functions(baseline_test)
    round1_count = count_test_functions(round1_test)
    round2_count = count_test_functions(round2_test)

    print(f"| 类型 | 测试文件 | 测试函数数 |")
    print(f"|------|---------|-----------|")
    print(f"| 人工基线 | test_simplify_manual.py | {baseline_count} |")
    print(f"| LLM Round 1 | round1_initial.py | {round1_count} |")
    print(f"| LLM Round 2 | round2_coverage.py | {round2_count} |")

    # =========================================================================
    # 2. 覆盖率对比
    # =========================================================================
    print("\n## 2. 代码覆盖率对比\n")

    baseline_cov_file = results_dir / "coverage_baseline.json"
    round1_cov_file = results_dir / "coverage_round1.json"
    round2_cov_file = results_dir / "coverage_round2.json"

    baseline_cov = load_coverage_summary(baseline_cov_file) if baseline_cov_file.exists() else {}
    round1_cov = load_coverage_summary(round1_cov_file) if round1_cov_file.exists() else {}
    round2_cov = load_coverage_summary(round2_cov_file) if round2_cov_file.exists() else {}

    table = generate_comparison_table(baseline_cov, round1_cov, round2_cov)
    print(table)

    # =========================================================================
    # 3. 变异测试对比
    # =========================================================================
    print("\n## 3. 变异测试对比\n")

    baseline_mut_file = results_dir / "mutation_score_baseline.txt"
    round1_mut_file = results_dir / "mutation_score_round1.txt"
    round2_mut_file = results_dir / "mutation_score_round2.txt"

    baseline_mut = load_mutation_score(baseline_mut_file)
    round1_mut = load_mutation_score(round1_mut_file)
    round2_mut = load_mutation_score(round2_mut_file)

    mut_table = generate_mutation_comparison(baseline_mut, round1_mut, round2_mut)
    print(mut_table)

    # =========================================================================
    # 4. 综合评分
    # =========================================================================
    print("\n## 4. 综合评估\n")

    # 计算综合得分（简单加权）
    def calc_score(cov_pct: float, mut_score: float, test_count: int,
                   max_tests: int = 40) -> float:
        """综合评分 = 覆盖率(40%) + 变异分数(40%) + 测试数量(20%)"""
        cov_norm = cov_pct / 100.0
        mut_norm = mut_score
        count_norm = min(test_count / max_tests, 1.0)
        return round(cov_norm * 40 + mut_norm * 40 + count_norm * 20, 1)

    b_score = calc_score(
        baseline_cov.get("simplify_pct", 0),
        baseline_mut.get("mutation_score", 0),
        baseline_count,
    )
    r1_score = calc_score(
        round1_cov.get("simplify_pct", 0),
        round1_mut.get("mutation_score", 0),
        round1_count,
    )
    r2_score = calc_score(
        round2_cov.get("simplify_pct", 0),
        round2_mut.get("mutation_score", 0),
        round2_count,
    )

    print(f"| 方法 | 综合评分 (满分100) |")
    print(f"|------|-------------------|")
    print(f"| 人工基线 | {b_score:.1f} |")
    print(f"| LLM Round 1 | {r1_score:.1f} |")
    print(f"| LLM Round 2 | {r2_score:.1f} |")

    improvement = r2_score - b_score
    if improvement > 0:
        print(f"\n✅ LLM Round 2 相比人工基线提升了 {improvement:.1f} 分")
    elif improvement == 0:
        print(f"\n⚖️ LLM Round 2 与人工基线持平")
    else:
        print(f"\n⚠️ LLM Round 2 低于人工基线 {abs(improvement):.1f} 分")

    # =========================================================================
    # 5. 输出分析
    # =========================================================================
    print("\n## 5. 分析要点\n")

    # 覆盖率增量分析
    if baseline_cov and round2_cov:
        delta_cov = round2_cov.get("simplify_pct", 0) - baseline_cov.get("simplify_pct", 0)
        delta_missing = baseline_cov.get("simplify_missing", 0) - round2_cov.get("simplify_missing", 0)
        print(f"- 覆盖率增量: {delta_cov:+.1f}% (未被覆盖的行减少 {delta_missing} 行)")
        if delta_cov > 5:
            print("  → LLM 显著提升了代码覆盖率")

    # 变异分数分析
    if baseline_mut.get("total", 0) > 0:
        delta_mut = round2_mut.get("mutation_score", 0) - baseline_mut.get("mutation_score", 0)
        print(f"- 变异分数增量: {delta_mut:+.1%}")
        if delta_mut > 0.05:
            print("  → LLM 生成的测试对变异体的检测能力更强")

    # 效率分析
    if baseline_count > 0 and round2_count > 0:
        ratio = round2_count / baseline_count
        print(f"- 测试数量比: LLM/人工 = {ratio:.1f}x")
        if round2_cov and baseline_cov:
            b_cov = baseline_cov.get("simplify_pct", 0)
            r2_cov = round2_cov.get("simplify_pct", 0)
            if b_cov > 0:
                cov_per_test_baseline = b_cov / baseline_count
                cov_per_test_round2 = r2_cov / round2_count
                print(f"- 每个测试的平均覆盖率贡献: 人工={cov_per_test_baseline:.2f}%, LLM={cov_per_test_round2:.2f}%")

    print("\n" + "=" * 70)
    print("对比报告完成。以上结果可复制到实验报告中。")
    print("=" * 70)


if __name__ == "__main__":
    main()
