import ast
import re
import os
import sys
from typing import List, Tuple, Optional


def extract_function_code(file_path: str, function_name: str) -> Optional[str]:
    """从Python文件中提取指定函数的完整源代码（包括装饰器）"""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            lines = source.splitlines()
            start = node.lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])
    return None


def extract_python_code(llm_output: str) -> str:
    """从LLM返回的文本中提取第一个Python代码块（```python ... ```）"""
    pattern = r"```python\n(.*?)```"
    matches = re.findall(pattern, llm_output, re.DOTALL)
    if matches:
        return matches[0].strip()
    # 如果没有代码块标记，尝试寻找以import或def开头的代码
    lines = llm_output.splitlines()
    code_lines = []
    in_code = False
    for line in lines:
        if line.strip().startswith(("import ", "from ", "def ", "class ")):
            in_code = True
        if in_code:
            code_lines.append(line)
    return "\n".join(code_lines)


def validate_and_fix_code(code: str) -> Tuple[str, List[str]]:
    """验证 Python 代码是否可编译，尝试自动修复常见问题

    Returns:
        (fixed_code, warnings): 修复后的代码和警告列表
    """
    warnings = []

    # 1. 移除裸的 """ —— 不在 def/class 后且不在行首作为文档字符串闭合的
    lines = code.splitlines()
    fixed_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 检查是否是裸的 """ 单独一行
        if stripped == '"""' or stripped == "'''":
            # 检查上一行是否是 def/class 定义
            is_docstring = False
            for j in range(i - 1, max(i - 4, -1), -1):
                prev = lines[j].strip() if j >= 0 else ""
                if prev.startswith(("def ", "class ", "@")):
                    is_docstring = True
                    break
                if prev and not prev.startswith("#"):
                    break
            # 检查下一行是否看起来像函数体
            if not is_docstring and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith(("def ", "class ", "@", "#", "import ", "from ")):
                    is_docstring = True

            if not is_docstring:
                warnings.append(f"Line {i+1}: 移除了裸的 triple-quote")
                fixed_lines.append("# (removed stray triple-quote)")
                continue
        fixed_lines.append(line)

    fixed_code = "\n".join(fixed_lines)

    # 2. 移除推理文字行（不在注释/字符串中的自然语言）
    reasoning_patterns = [
        r'^\s*Therefore\s', r'^\s*Thus\s', r'^\s*So\s',
        r'^\s*Let\'s\s', r'^\s*We\s+(can|should|need|write)\s',
        r'^\s*Note\s+that\s', r'^\s*Actually[,\s]', r'^\s*The\s+(code|function)\s',
    ]
    lines2 = fixed_code.splitlines()
    cleaned_lines = []
    for line in lines2:
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "import ", "from ", "def ", "class ",
                                                    "@", "if ", "for ", "while ", "try:",
                                                    "return ", "assert ", "with ", "raise ",
                                                    "else:", "elif ", "except ", "finally:",
                                                    "yield ", "pass", "break", "continue",
                                                    '"""', "'''")):
            # 检查是否像推理文字
            is_reasoning = False
            for pat in reasoning_patterns:
                if re.match(pat, stripped, re.IGNORECASE):
                    is_reasoning = True
                    break
            # 也检查是否以大写字母开头且包含自然语言词汇
            if is_reasoning:
                warnings.append(f"移除推理文字: {stripped[:60]}...")
                cleaned_lines.append(f"# {stripped}")
                continue
        cleaned_lines.append(line)

    final_code = "\n".join(cleaned_lines)

    # 3. 编译验证
    try:
        compile(final_code, "<generated>", "exec")
    except SyntaxError as e:
        warnings.append(f"语法错误仍然存在 (line {e.lineno}): {e.msg}")
        # 尝试更激进的修复：移除错误行
        lines3 = final_code.splitlines()
        if e.lineno and e.lineno <= len(lines3):
            bad_line = lines3[e.lineno - 1]
            warnings.append(f"  移除错误行 {e.lineno}: {bad_line.strip()[:80]}")
            lines3[e.lineno - 1] = f"# (removed syntax error) {bad_line}"
        final_code = "\n".join(lines3)
        try:
            compile(final_code, "<generated>", "exec")
            warnings.append("二次编译成功")
        except SyntaxError as e2:
            warnings.append(f"二次编译仍然失败 (line {e2.lineno}): {e2.msg}")

    # 4. 验证常见导入
    fixed_code = _fix_common_imports(final_code, warnings)

    return fixed_code, warnings


def _fix_common_imports(code: str, warnings: List[str]) -> str:
    """修复 LLM 常见的导入幻觉"""
    # 已知正确的导入映射
    import_fixes = {
        "from sympy.concrete.gosper import hypersimp": "from sympy.simplify.simplify import hypersimp",
        "from sympy.simplify import hypersimp": "from sympy.simplify.simplify import hypersimp",
        "from sympy.simplify import inversecombine": "from sympy.simplify.simplify import inversecombine",
        "from sympy.simplify import nthroot": "from sympy.simplify.simplify import nthroot",
        "from sympy.simplify import posify": "from sympy.simplify.simplify import posify",
    }
    for wrong, correct in import_fixes.items():
        if wrong in code:
            warnings.append(f"修复导入: {wrong} → {correct}")
            code = code.replace(wrong, correct)
    return code


def save_test_file(content: str, output_path: str, validate: bool = True):
    """保存测试文件，并添加必要的导入头，可选编译验证"""
    header = """import pytest
from sympy import symbols, simplify, S, Rational, sqrt, sin, cos, pi
"""

    if validate:
        fixed_content, warnings = validate_and_fix_code(content)
        if warnings:
            print(f"[代码验证] 发现 {len(warnings)} 个问题:")
            for w in warnings:
                print(f"  - {w}")
        content = fixed_content

    full_content = header + "\n" + content
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_content)
    print(f"测试文件已保存: {output_path}")