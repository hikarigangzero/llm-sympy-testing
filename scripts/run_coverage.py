import subprocess
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
SYMPY_SRC = PROJECT_ROOT / "sympy"


def run_coverage(test_file: str, source_module: str = "sympy",
                 output_name: str = "coverage",
                 target_file: Optional[str] = None) -> Dict[str, List[int]]:
    """运行pytest覆盖率分析，生成JSON和HTML报告

    Args:
        test_file: 测试文件路径（相对于项目根目录或绝对路径）
        source_module: 要测量覆盖率的源码模块
        output_name: 输出文件名前缀
        target_file: 要关注的源码文件路径（如 "sympy/simplify/simplify.py"）

    Returns:
        未覆盖行字典 {文件名: [行号列表]}
    """
    test_path = Path(test_file)
    if not test_path.is_absolute():
        test_path = PROJECT_ROOT / test_path

    results_dir = PROJECT_ROOT / "my_tests" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    cov_data_file = results_dir / f".coverage_{output_name}"
    cov_report = results_dir / f"{output_name}.json"

    # 1. 运行 pytest + coverage（必须在 sympy 目录下运行以避免循环导入）
    cmd = [
        sys.executable, "-m", "coverage", "run",
        "--data-file", str(cov_data_file),
        f"--source={source_module}",
        "-m", "pytest", str(test_path), "-v", "--tb=short"
    ]
    print(f"[run_coverage] 运行: {' '.join(cmd)}")
    print(f"[run_coverage] 工作目录: {SYMPY_SRC}")
    result = subprocess.run(cmd, capture_output=False, cwd=str(SYMPY_SRC))
    if result.returncode != 0:
        print(f"[run_coverage] 警告: pytest 退出码 {result.returncode}")

    # 2. 生成 JSON 报告
    subprocess.run([
        sys.executable, "-m", "coverage", "json",
        "--data-file", str(cov_data_file),
        "-o", str(cov_report)
    ], check=True)

    # 3. 生成 HTML 报告
    html_dir = results_dir / f"htmlcov_{output_name}"
    subprocess.run([
        sys.executable, "-m", "coverage", "html",
        "--data-file", str(cov_data_file),
        "-d", str(html_dir)
    ], check=True)

    print(f"[run_coverage] 覆盖率报告已保存: {cov_report}")

    # 4. 解析并提取未覆盖的行
    with open(cov_report, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 计算总体覆盖率
    totals = data.get("totals", {})
    total_stmts = totals.get("num_statements", 0)
    covered_stmts = totals.get("covered_lines", 0)
    pct = totals.get("percent_covered", 0.0)
    print(f"[run_coverage] 总体覆盖率: {covered_stmts}/{total_stmts} = {pct:.1f}%")

    uncovered = {}
    files_data = data.get("files", {})
    for file_path, file_data in files_data.items():
        # 如果指定了 target_file，只关注该文件；否则关注 sympy/simplify
        if target_file and target_file in file_path:
            pass
        elif not target_file and "sympy/simplify" not in file_path:
            continue

        # coverage.py JSON 格式中 missing_lines 是未执行的行号列表
        missing = file_data.get("missing_lines", [])
        executed = file_data.get("executed_lines", [])
        total_lines = len(missing) + len(executed)
        file_pct = file_data.get("summary", {}).get("percent_covered", 0.0)

        print(f"  {file_path}: {len(executed)}/{total_lines} = {file_pct:.1f}%"
              f" (未覆盖: {len(missing)} 行)")

        if missing:
            uncovered[file_path] = missing

    # 5. 保存未覆盖行到文本文件
    uncovered_file = results_dir / f"uncovered_lines_{output_name}.txt"
    with open(uncovered_file, "w", encoding="utf-8") as f:
        for path, lines in uncovered.items():
            f.write(f"文件: {path}\n")
            f.write(f"未覆盖行号: {lines}\n\n")
    print(f"[run_coverage] 未覆盖行信息已保存: {uncovered_file}")

    return uncovered


def get_coverage_summary(json_path: str) -> dict:
    """读取覆盖率 JSON 报告，返回汇总信息"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("totals", {})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行 pytest 覆盖率分析")
    parser.add_argument("--test-file", required=True, help="测试文件路径")
    parser.add_argument("--source", default="sympy", help="源码模块（默认 sympy）")
    parser.add_argument("--output", default="coverage", help="输出文件名前缀")
    parser.add_argument("--target-file", default=None,
                        help="关注的源码文件（如 sympy/simplify/simplify.py）")
    args = parser.parse_args()
    run_coverage(args.test_file, source_module=args.source,
                 output_name=args.output, target_file=args.target_file)