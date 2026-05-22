"""
变异测试（Mutation Testing）执行脚本

对源码进行变异注入，然后运行测试套件，计算变异分数（Mutation Score）。

变异操作包括：
  - AOR: 算术运算符替换 (+, -, *, /, **)
  - ROR: 关系运算符替换 (>, <, >=, <=, ==, !=)
  - LCR: 逻辑连接词替换 (and, or)
  - CRR: 常量替换 (0, 1, -1, True, False)
  - BSR: 边界值偏移 (ratio=1.7 -> ratio=0.5, ratio=3.0)
  - RLR: 返回值替换 (return x -> return -x)

用法:
  python scripts/run_mutation.py \\
      --source sympy/sympy/simplify/simplify.py \\
      --test my_tests/baseline/test_simplify_manual.py \\
      --output my_tests/results/mutation_score_baseline.txt

  python scripts/run_mutation.py \\
      --source sympy/sympy/simplify/simplify.py \\
      --test my_tests/generated/round1_initial.py \\
      --output my_tests/results/mutation_score_round1.txt
"""

import ast
import copy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field


# ============================================================================
# 变异算子定义
# ============================================================================

@dataclass
class Mutant:
    """变异体"""
    id: str
    operator: str           # 变异算子类型
    file_path: str          # 源文件路径
    line_number: int        # 行号
    original: str           # 原始代码
    mutated: str            # 变异后代码
    description: str        # 可读描述


class MutationOperator:
    """变异算子基类"""
    name: str = "base"

    def generate(self, tree: ast.AST, source: str, file_path: str) -> List[Mutant]:
        raise NotImplementedError


# ============================================================================
# 具体变异算子
# ============================================================================

class AOR_Operator(MutationOperator):
    """算术运算符替换: + <-> -, * <-> /, ** <-> *"""
    name = "AOR"

    OPS = {
        ast.Add: [ast.Sub],
        ast.Sub: [ast.Add],
        ast.Mult: [ast.Div],
        ast.Div: [ast.Mult],
        ast.Pow: [ast.Mult],
    }

    def generate(self, tree: ast.AST, source: str, file_path: str) -> List[Mutant]:
        mutants = []
        lines = source.splitlines()

        class Visitor(ast.NodeVisitor):
            def visit_BinOp(self, node):
                op_type = type(node.op)
                if op_type in AOR_Operator.OPS:
                    for repl in AOR_Operator.OPS[op_type]:
                        # 只对数值运算做变异
                        mut_id = f"AOR_{node.lineno}"
                        orig_str = ast.get_source_segment(source, node)
                        if orig_str:
                            new_op = _ast_op_to_str(repl())
                            old_op = _ast_op_to_str(node.op)
                            mut_str = orig_str.replace(old_op, new_op, 1)
                            mutants.append(Mutant(
                                id=mut_id,
                                operator="AOR",
                                file_path=file_path,
                                line_number=node.lineno,
                                original=orig_str.strip(),
                                mutated=mut_str.strip(),
                                description=f"将 '{old_op}' 替换为 '{new_op}' (行 {node.lineno})"
                            ))
                self.generic_visit(node)

        Visitor().visit(tree)
        return mutants


class ROR_Operator(MutationOperator):
    """关系运算符替换"""
    name = "ROR"

    OPS = {
        ast.Gt: [ast.GtE, ast.Lt, ast.Eq],
        ast.Lt: [ast.LtE, ast.Gt, ast.Eq],
        ast.GtE: [ast.Gt, ast.Lt],
        ast.LtE: [ast.Lt, ast.Gt],
        ast.Eq: [ast.NotEq],
        ast.NotEq: [ast.Eq],
    }

    def generate(self, tree: ast.AST, source: str, file_path: str) -> List[Mutant]:
        mutants = []
        lines = source.splitlines()

        class Visitor(ast.NodeVisitor):
            def visit_Compare(self, node):
                for i, op in enumerate(node.ops):
                    op_type = type(op)
                    if op_type in ROR_Operator.OPS:
                        for repl in ROR_Operator.OPS[op_type]:
                            mut_id = f"ROR_{node.lineno}_{i}"
                            orig_str = ast.get_source_segment(source, node)
                            if orig_str:
                                old_op_str = _ast_op_to_str(op)
                                new_op_str = _ast_op_to_str(repl())
                                mut_str = orig_str.replace(old_op_str, new_op_str, 1)
                                mutants.append(Mutant(
                                    id=mut_id,
                                    operator="ROR",
                                    file_path=file_path,
                                    line_number=node.lineno,
                                    original=orig_str.strip(),
                                    mutated=mut_str.strip(),
                                    description=f"将 '{old_op_str}' 替换为 '{new_op_str}' (行 {node.lineno})"
                                ))
                self.generic_visit(node)

        Visitor().visit(tree)
        return mutants


class CRR_Operator(MutationOperator):
    """常量替换"""
    name = "CRR"

    CONSTANTS = {
        0: [1, -1],
        1: [0, -1, 2],
        -1: [0, 1],
        2: [1, 3],
    }

    def generate(self, tree: ast.AST, source: str, file_path: str) -> List[Mutant]:
        mutants = []

        class Visitor(ast.NodeVisitor):
            def visit_Constant(self, node):
                if isinstance(node.value, (int, float)):
                    val = node.value
                    if val in CRR_Operator.CONSTANTS:
                        for repl in CRR_Operator.CONSTANTS[val]:
                            mut_id = f"CRR_{node.lineno}"
                            mutants.append(Mutant(
                                id=mut_id,
                                operator="CRR",
                                file_path=file_path,
                                line_number=node.lineno,
                                original=str(val),
                                mutated=str(repl),
                                description=f"将常量 {val} 替换为 {repl} (行 {node.lineno})"
                            ))
                self.generic_visit(node)

        Visitor().visit(tree)
        return mutants


class BSR_Operator(MutationOperator):
    """边界值偏移 —— 专门针对 simplify 的 ratio 参数等"""
    name = "BSR"

    PATTERNS = [
        ("ratio=1.7", "ratio=0.5"),
        ("ratio=1.7", "ratio=3.0"),
        ("ratio=oo", "ratio=1"),
    ]

    def generate(self, tree: ast.AST, source: str, file_path: str) -> List[Mutant]:
        mutants = []
        for orig, repl in self.PATTERNS:
            if orig in source:
                # 找到所有出现位置
                idx = 0
                line_num = 1
                for i, line in enumerate(source.splitlines(), 1):
                    if orig in line:
                        mut_id = f"BSR_{i}"
                        mutants.append(Mutant(
                            id=mut_id,
                            operator="BSR",
                            file_path=file_path,
                            line_number=i,
                            original=orig,
                            mutated=repl,
                            description=f"将默认参数 '{orig}' 改为 '{repl}' (行 {i})"
                        ))
        return mutants


# ============================================================================
# 辅助函数
# ============================================================================

def _ast_op_to_str(op) -> str:
    """将 AST 运算符转为字符串"""
    mapping = {
        ast.Add: '+', ast.Sub: '-', ast.Mult: '*', ast.Div: '/', ast.Pow: '**',
        ast.Gt: '>', ast.Lt: '<', ast.GtE: '>=', ast.LtE: '<=',
        ast.Eq: '==', ast.NotEq: '!=',
        ast.And: 'and', ast.Or: 'or',
    }
    return mapping.get(type(op), str(op))


def generate_mutants(source_file: str, operators: List[str] = None) -> List[Mutant]:
    """对源文件生成所有变异体"""
    with open(source_file, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)

    op_map = {
        "AOR": AOR_Operator(),
        "ROR": ROR_Operator(),
        "CRR": CRR_Operator(),
        "BSR": BSR_Operator(),
    }

    if operators is None:
        operators = list(op_map.keys())

    all_mutants = []
    for op_name in operators:
        if op_name in op_map:
            op = op_map[op_name]
            mutants = op.generate(tree, source, source_file)
            all_mutants.extend(mutants)
            print(f"[变异] {op_name}: 生成 {len(mutants)} 个变异体")

    # 去重
    seen = set()
    unique = []
    for m in all_mutants:
        key = (m.line_number, m.mutated)
        if key not in seen:
            seen.add(key)
            unique.append(m)

    print(f"[变异] 总共 {len(unique)} 个唯变异体")
    return unique


def apply_mutant(source_file: str, mutant: Mutant) -> str:
    """将变异应用到源码，返回变异后的临时文件路径"""
    with open(source_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 修改指定行
    line_idx = mutant.line_number - 1
    if 0 <= line_idx < len(lines):
        old_line = lines[line_idx]
        # 只替换行内第一次匹配
        new_line = old_line.replace(mutant.original, mutant.mutated, 1)
        if old_line == new_line:
            # 尝试更宽松的替换：只替换 mutant.original 中不带空格的部分
            new_line = old_line.replace(mutant.original.strip(), mutant.mutated.strip(), 1)
        lines[line_idx] = new_line

    # 写入临时文件
    tmp_dir = Path(tempfile.gettempdir()) / "sympy_mutation"
    tmp_dir.mkdir(exist_ok=True)
    tmp_file = tmp_dir / f"mutant_{mutant.id}.py"

    with open(tmp_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return str(tmp_file)


def run_test_on_mutant(test_file: str, mutated_source: str,
                       original_source_dir: str) -> Tuple[bool, str]:
    """
    对变异体运行测试
    返回 (是否被杀死, 输出信息)
    被杀死 = 测试在变异体上失败（说明测试检测到了变异）
    """
    # 复制整个 sympy 目录到临时位置以便替换
    tmp_sympy = Path(tempfile.gettempdir()) / "sympy_mutation_test"
    if tmp_sympy.exists():
        shutil.rmtree(tmp_sympy)

    # 复制 sympy 源码
    src_dir = Path(original_source_dir)
    shutil.copytree(src_dir, tmp_sympy,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))

    # 替换变异文件
    relative_path = Path(mutated_source).name
    target = tmp_sympy / "sympy" / "simplify" / "simplify.py"
    if target.exists():
        shutil.copy2(mutated_source, target)

    # 运行 pytest
    # 需要将临时目录加入 sys.path
    env = {**__import__('os').environ, 'PYTHONPATH': str(tmp_sympy)}

    cmd = [
        sys.executable, "-m", "pytest", str(test_file),
        "-v", "--tb=short", "--timeout=30",
        "-x",  # 遇到第一个失败就停止
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(tmp_sympy),
            env=env,
        )
        killed = result.returncode != 0
        output = result.stdout[-500:] + result.stderr[-200:]
        return killed, output
    except subprocess.TimeoutExpired:
        return True, "超时"  # 超时视为杀死
    except Exception as e:
        return True, str(e)
    finally:
        # 清理
        if tmp_sympy.exists():
            shutil.rmtree(tmp_sympy, ignore_errors=True)


def run_mutation_testing(source_file: str, test_file: str, output_path: str,
                          operators: List[str] = None,
                          max_mutants: int = 20,
                          sympy_src_dir: str = None) -> dict:
    """
    执行完整的变异测试流程

    Returns:
        dict: {
            "total": 总数,
            "killed": 被杀死的变异体数,
            "survived": 存活的变异体数,
            "mutation_score": 变异分数,
            "details": [{"id": ..., "killed": ..., "description": ...}, ...]
        }
    """
    print(f"\n{'='*60}")
    print(f"变异测试")
    print(f"  源文件: {source_file}")
    print(f"  测试文件: {test_file}")
    print(f"{'='*60}\n")

    # 1. 生成变异体
    mutants = generate_mutants(source_file, operators)

    if len(mutants) == 0:
        print("[变异] 没有生成变异体，退出")
        return {"total": 0, "killed": 0, "survived": 0, "mutation_score": 1.0, "details": []}

    # 限制数量
    if max_mutants and len(mutants) > max_mutants:
        print(f"[变异] 限制为 {max_mutants} 个变异体（共 {len(mutants)} 个）")
        mutants = mutants[:max_mutants]

    # 确定 sympy 源码目录
    if sympy_src_dir is None:
        sympy_src_dir = str(Path(source_file).parent.parent.parent)

    # 2. 对每个变异体运行测试
    results = []
    killed_count = 0

    for i, mutant in enumerate(mutants):
        print(f"[{i+1}/{len(mutants)}] 测试变异体 {mutant.id}: {mutant.description[:60]}")

        try:
            mutated_file = apply_mutant(source_file, mutant)
            killed, output = run_test_on_mutant(test_file, mutated_file, sympy_src_dir)

            if killed:
                killed_count += 1
                status = "✓ 已杀死"
            else:
                status = "✗ 存活"

            print(f"  {status}")

            results.append({
                "id": mutant.id,
                "operator": mutant.operator,
                "line": mutant.line_number,
                "description": mutant.description,
                "killed": killed,
                "status": status,
            })
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            results.append({
                "id": mutant.id,
                "operator": mutant.operator,
                "line": mutant.line_number,
                "description": mutant.description,
                "killed": False,
                "status": f"错误: {e}",
            })

        # 清理临时文件
        tmp_file = Path(tempfile.gettempdir()) / "sympy_mutation" / f"mutant_{mutant.id}.py"
        if tmp_file.exists():
            tmp_file.unlink()

    # 3. 计算变异分数
    total = len(mutants)
    score = killed_count / total if total > 0 else 1.0

    summary = {
        "test_file": test_file,
        "source_file": source_file,
        "total": total,
        "killed": killed_count,
        "survived": total - killed_count,
        "mutation_score": round(score, 4),
        "details": results,
    }

    # 4. 输出结果
    print(f"\n{'='*60}")
    print(f"变异测试结果")
    print(f"  总数: {total}")
    print(f"  已杀死: {killed_count}")
    print(f"  存活: {total - killed_count}")
    print(f"  变异分数: {score:.2%}")
    print(f"{'='*60}")

    # 输出存活的变异体
    survived = [r for r in results if not r["killed"]]
    if survived:
        print(f"\n存活的变异体 ({len(survived)}):")
        for r in survived:
            print(f"  {r['id']}: {r['description']}")

    # 5. 保存结果
    import json
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存 JSON
    with open(output_path.with_suffix(".json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 保存可读文本
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"变异测试报告\n")
        f.write(f"{'='*60}\n")
        f.write(f"测试文件: {test_file}\n")
        f.write(f"源文件: {source_file}\n")
        f.write(f"变异体总数: {total}\n")
        f.write(f"已杀死: {killed_count}\n")
        f.write(f"存活: {total - killed_count}\n")
        f.write(f"变异分数: {score:.2%}\n")
        f.write(f"\n详细结果:\n")
        for r in results:
            f.write(f"  [{r['status']}] {r['id']}: {r['description']}\n")
        if survived:
            f.write(f"\n未杀死的变异体:\n")
            for r in survived:
                f.write(f"  {r['id']}: {r['description']}\n")

    print(f"\n[变异] 报告已保存: {output_path}")
    return summary


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="变异测试执行")
    parser.add_argument("--source", required=True, help="源码文件路径")
    parser.add_argument("--test", required=True, help="测试文件路径")
    parser.add_argument("--output", required=True, help="输出报告路径")
    parser.add_argument("--operators", nargs="+", default=["BSR", "CRR", "ROR"],
                        choices=["AOR", "ROR", "CRR", "BSR"],
                        help="使用的变异算子（默认 BSR CRR ROR）")
    parser.add_argument("--max-mutants", type=int, default=15,
                        help="最大变异体数量")
    parser.add_argument("--sympy-dir",
                        default=str(Path(__file__).parent.parent),
                        help="SymPy 项目根目录")

    args = parser.parse_args()

    run_mutation_testing(
        source_file=args.source,
        test_file=args.test,
        output_path=args.output,
        operators=args.operators,
        max_mutants=args.max_mutants,
        sympy_src_dir=args.sympy_dir,
    )
