"""
LLM 驱动的测试用例生成脚本

支持三种模式：
  1. initial  - 根据函数源码生成初始测试用例（Round 1）
  2. coverage - 根据覆盖率缺口补充测试用例（Round 2）
  3. mutation - 根据变异体生成 Killing Test（Round 3）

用法:
  python scripts/generate_tests.py --mode initial \\
      --file sympy/sympy/simplify/simplify.py --function simplify \\
      --output my_tests/generated/round1_initial.py

  python scripts/generate_tests.py --mode coverage \\
      --uncovered my_tests/results/uncovered_lines_coverage_baseline.txt \\
      --source-file sympy/sympy/simplify/simplify.py \\
      --existing-test my_tests/generated/round1_initial.py \\
      --output my_tests/generated/round2_coverage.py

  python scripts/generate_tests.py --mode mutation \\
      --source-file sympy/sympy/simplify/simplify.py --function simplify \\
      --mutant-desc "将 ratio=1.7 改为 ratio=0.5" \\
      --existing-test my_tests/generated/round2_coverage.py \\
      --output my_tests/generated/round3_mutation.py

环境变量（在 .env 中配置）:
  OPENAI_API_KEY  或 DEEPSEEK_API_KEY
  OPENAI_BASE_URL 或 DEEPSEEK_BASE_URL
  LLM_MODEL        模型名称
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# 添加项目根目录到路径
sys.path.append(str(Path(__file__).parent.parent))
from scripts.utils import extract_function_code, extract_python_code, save_test_file

# 加载环境变量
load_dotenv(Path(__file__).parent.parent / ".env")

# 初始化客户端
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
)
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# 日志路径
LOG_PATH = Path(__file__).parent.parent / "my_tests" / "logs" / "generation_log.jsonl"


def load_prompt(template_name: str) -> str:
    """读取 prompt 模板文件"""
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{template_name}.txt"
    if not prompt_path.exists():
        print(f"[警告] prompt 模板不存在: {prompt_path}")
        return ""
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def call_llm(prompt: str, temperature: float = 0.3, max_tokens: int = 4096) -> str:
    """调用大模型并返回文本"""
    print(f"[LLM] 调用模型 {MODEL}... (prompt 长度: {len(prompt)} 字符)")
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        print(f"[LLM] 返回 {len(content)} 字符")
        return content
    except Exception as e:
        print(f"[LLM] 调用失败: {e}")
        raise


def log_generation(round_name: str, function_name: str, prompt: str, output: str):
    """将生成记录写入日志"""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "round": round_name,
        "function": function_name,
        "model": MODEL,
        "prompt_length": len(prompt),
        "output_length": len(output),
        "prompt": prompt[:500],  # 只存前500字符用于审计
        "output": output,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def generate_initial_tests(source_file: str, function_name: str, output_path: str):
    """Round 1: 根据函数源码生成初始测试用例"""
    prompt_template = load_prompt("initial_generation")
    code = extract_function_code(source_file, function_name)
    if not code:
        print(f"[错误] 未找到函数 {function_name} 在 {source_file} 中")
        sys.exit(1)

    prompt = prompt_template.format(code=code, function_name=function_name)
    print(f"\n{'='*60}")
    print(f"Round 1: 生成 {function_name} 的初始测试用例")
    print(f"{'='*60}")

    llm_output = call_llm(prompt)
    test_code = extract_python_code(llm_output)

    if not test_code:
        print("[错误] LLM 未返回有效的 Python 代码")
        # 尝试保存原始输出以便调试
        test_code = f"# 解析失败，原始输出:\n# {llm_output[:500]}"
        save_test_file(test_code, output_path)
    else:
        save_test_file(test_code, output_path)

    log_generation("initial", function_name, prompt, llm_output)
    print(f"[完成] 初始测试已保存到 {output_path}")


def generate_coverage_gap_tests(uncovered_file: str, source_file: str,
                                 existing_test: str, output_path: str):
    """Round 2: 根据覆盖率缺口补充测试"""
    prompt_template = load_prompt("coverage_gap")

    # 读取未覆盖行信息，但只保留目标源文件相关的行
    uncovered_info = _filter_uncovered_for_file(uncovered_file, source_file)

    # 读取已有测试（只取函数签名，不取完整实现以节省 token）
    existing_tests = _summarize_test_file(existing_test)

    # 读取源码中未覆盖的部分
    source_code_snippets = _extract_uncovered_snippets(uncovered_file, source_file)

    # 构造 prompt 并检查长度
    prompt = prompt_template.format(
        uncovered_lines=uncovered_info,
        source_snippets=source_code_snippets,
        existing_tests=existing_tests
    )

    # 如果 prompt 仍然太大，进一步截断
    MAX_PROMPT_CHARS = 50000  # ~12500 tokens, 安全边界
    if len(prompt) > MAX_PROMPT_CHARS:
        print(f"[警告] prompt 过长 ({len(prompt)} 字符)，进行截断...")
        # 截断 uncovered_info
        max_uncovered = MAX_PROMPT_CHARS // 2
        if len(uncovered_info) > max_uncovered:
            uncovered_info = uncovered_info[:max_uncovered] + "\n... (已截断)"
        # 截断 existing_tests
        max_existing = MAX_PROMPT_CHARS // 4
        if len(existing_tests) > max_existing:
            existing_tests = existing_tests[:max_existing] + "\n# ... (已截断)"
        # 截断 snippets
        max_snippets = MAX_PROMPT_CHARS // 4
        if len(source_code_snippets) > max_snippets:
            source_code_snippets = source_code_snippets[:max_snippets] + "\n# ... (已截断)"

        prompt = prompt_template.format(
            uncovered_lines=uncovered_info,
            source_snippets=source_code_snippets,
            existing_tests=existing_tests
        )

    print(f"\n{'='*60}")
    print(f"Round 2: 根据覆盖率缺口补充测试")
    print(f"  prompt 长度: {len(prompt)} 字符")
    print(f"{'='*60}")

    llm_output = call_llm(prompt)
    new_tests = extract_python_code(llm_output)

    if not new_tests:
        print("[错误] LLM 未返回有效的 Python 代码")
        new_tests = f"# 解析失败\n# {llm_output[:300]}"

    save_test_file(new_tests, output_path)
    log_generation("coverage", source_file, prompt, llm_output)
    print(f"[完成] 覆盖率补充测试已保存到 {output_path}")


def generate_mutation_tests(source_file: str, function_name: str,
                             mutant_desc: str, existing_test: str,
                             output_path: str):
    """Round 3: 针对变异体生成 Killing Test"""
    prompt_template = load_prompt("mutation_killing")

    code = extract_function_code(source_file, function_name)
    if not code:
        print(f"[错误] 未找到函数 {function_name}")
        sys.exit(1)

    with open(existing_test, "r", encoding="utf-8") as f:
        existing_tests = f.read()

    prompt = prompt_template.format(
        original_code=code,
        function_name=function_name,
        mutant_description=mutant_desc,
        existing_tests=existing_tests,
    )

    print(f"\n{'='*60}")
    print(f"Round 3: 生成变异 Killing Test")
    print(f"{'='*60}")

    llm_output = call_llm(prompt, temperature=0.4)
    test_code = extract_python_code(llm_output)

    if not test_code:
        print("[错误] LLM 未返回有效的 Python 代码")
        test_code = f"# 解析失败\n# {llm_output[:300]}"

    save_test_file(test_code, output_path)
    log_generation("mutation", function_name, prompt, llm_output)
    print(f"[完成] 变异测试已保存到 {output_path}")


def generate_batch_initial(output_dir: str):
    """批量生成多个函数的初始测试"""
    # 定义要测试的 (源文件, 函数名, 正确的import提示) 对
    targets = [
        ("sympy/sympy/simplify/simplify.py", "simplify",
         "from sympy import simplify"),
        ("sympy/sympy/simplify/simplify.py", "separatevars",
         "from sympy import separatevars"),
        ("sympy/sympy/simplify/simplify.py", "signsimp",
         "from sympy import signsimp"),
        ("sympy/sympy/simplify/simplify.py", "logcombine",
         "from sympy import logcombine"),
        ("sympy/sympy/simplify/simplify.py", "posify",
         "from sympy.simplify.simplify import posify"),
        ("sympy/sympy/simplify/simplify.py", "hypersimp",
         "from sympy.simplify.simplify import hypersimp"),
        ("sympy/sympy/simplify/simplify.py", "inversecombine",
         "from sympy.simplify.simplify import inversecombine"),
        ("sympy/sympy/simplify/simplify.py", "nthroot",
         "from sympy.simplify.simplify import nthroot"),
    ]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_tests = []
    for src_file, func_name, import_hint in targets:
        try:
            full_src = str(Path(__file__).parent.parent / src_file)
            code = extract_function_code(full_src, func_name)
            if not code:
                print(f"[跳过] 未找到 {func_name}")
                continue

            prompt_template = load_prompt("initial_generation")
            prompt = prompt_template.format(code=code, function_name=func_name)
            # 追加导入提示
            prompt += f"\n\n注意：正确的导入语句是 `{import_hint}`，请勿使用其他模块路径。"
            llm_output = call_llm(prompt)
            test_code = extract_python_code(llm_output)

            if test_code:
                all_tests.append(f"# ===== 测试 {func_name} =====\n{test_code}")
                log_generation("initial_batch", func_name, prompt, llm_output)
            else:
                print(f"[警告] {func_name} 生成失败，跳过")
        except Exception as e:
            print(f"[错误] {func_name} 生成异常: {e}")

    if all_tests:
        combined = "\n\n".join(all_tests)
        save_test_file(combined, str(output_dir / "round1_initial.py"))


def _extract_uncovered_snippets(uncovered_file: str, source_file: str) -> str:
    """从源码中提取未覆盖行的代码片段"""
    snippets = []
    try:
        with open(uncovered_file, "r", encoding="utf-8") as f:
            content = f.read()

        with open(source_file, "r", encoding="utf-8") as f:
            source_lines = f.readlines()

        # 简单解析未覆盖行文件
        import re
        pattern = r'未覆盖行号:\s*\[([^\]]+)\]'
        for match in re.finditer(pattern, content):
            line_str = match.group(1)
            lines = [int(x.strip()) for x in line_str.split(",") if x.strip()]
            if lines:
                # 取未覆盖行的上下文（前后各 5 行）
                for ln in lines[:10]:  # 限制数量避免 prompt 过长
                    start = max(0, ln - 6)
                    end = min(len(source_lines), ln + 5)
                    snippet = "".join(source_lines[start:end])
                    snippets.append(f"# 未覆盖行 {ln} 附近:\n{snippet}")
    except Exception as e:
        print(f"[警告] 提取源码片段失败: {e}")

    return "\n".join(snippets[:5])  # 最多 5 个片段


def _filter_uncovered_for_file(uncovered_file: str, source_file: str) -> str:
    """从未覆盖行文件中只提取目标源文件相关的信息"""
    try:
        with open(uncovered_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取目标文件名（只取最后一部分用于匹配）
        target_name = Path(source_file).name  # e.g. "simplify.py"
        target_module = str(Path(source_file)).replace("/", ".").replace(".py", "")

        lines = content.splitlines()
        filtered = []
        in_target_block = False
        for line in lines:
            # 检测是否进入了目标文件的 block
            if target_name in line or target_module in line:
                in_target_block = True
            elif line.startswith("文件:") or line.startswith("sympy/"):
                in_target_block = target_name in line or target_module in line

            if in_target_block:
                filtered.append(line)
                # 空行或下一个文件块开始时结束
                if line.strip() == "" and len(filtered) > 1:
                    # 检查下一行是否是新文件
                    pass  # 继续收集

        result = "\n".join(filtered)
        if not result.strip():
            # 如果过滤后为空，返回简化的摘要
            return f"目标文件: {source_file}\n(未覆盖行信息请参考覆盖率报告)"

        print(f"[过滤] 未覆盖信息从 {len(content)} 字符缩减到 {len(result)} 字符")
        return result
    except Exception as e:
        print(f"[警告] 过滤未覆盖信息失败: {e}")
        return f"目标文件: {source_file}\n(解析失败)"


def _summarize_test_file(test_file: str, max_chars: int = 3000) -> str:
    """提取测试文件的摘要（函数签名和注释），避免 prompt 过长"""
    try:
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 如果文件本身不长，直接返回
        if len(content) <= max_chars:
            return content

        # 提取关键行：import、class、def、注释
        lines = content.splitlines()
        summary_lines = []
        for line in lines:
            stripped = line.strip()
            if (stripped.startswith(("import ", "from ", "def test_", "class Test",
                                      "# ", '"""', "@pytest"))
                    or stripped == ""):
                summary_lines.append(line)

        result = "\n".join(summary_lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n# ... (已截断，共 {} 个测试函数)".format(
                content.count("def test_"))

        print(f"[摘要] 测试文件从 {len(content)} 字符缩减到 {len(result)} 字符")
        return result
    except Exception as e:
        print(f"[警告] 提取测试摘要失败: {e}")
        return "# (无法读取测试文件)"


def main():
    parser = argparse.ArgumentParser(
        description="LLM 驱动的测试用例生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="mode", help="运行模式")

    # 模式 1: initial
    p_init = subparsers.add_parser("initial", help="生成初始测试（Round 1）")
    p_init.add_argument("--file", required=True, help="源码文件路径")
    p_init.add_argument("--function", required=True, help="函数名")
    p_init.add_argument("--output", required=True, help="输出测试文件路径")

    # 模式 2: coverage
    p_cov = subparsers.add_parser("coverage", help="覆盖率缺口补充（Round 2）")
    p_cov.add_argument("--uncovered", required=True, help="未覆盖行信息文件")
    p_cov.add_argument("--source-file", required=True, help="源码文件")
    p_cov.add_argument("--existing-test", required=True, help="已有测试文件")
    p_cov.add_argument("--output", required=True, help="输出测试文件路径")

    # 模式 3: mutation
    p_mut = subparsers.add_parser("mutation", help="变异 Killing Test（Round 3）")
    p_mut.add_argument("--source-file", required=True, help="源码文件")
    p_mut.add_argument("--function", required=True, help="函数名")
    p_mut.add_argument("--mutant-desc", required=True, help="变异描述")
    p_mut.add_argument("--existing-test", required=True, help="已有测试文件")
    p_mut.add_argument("--output", required=True, help="输出测试文件路径")

    # 模式 4: batch
    p_batch = subparsers.add_parser("batch", help="批量生成")
    p_batch.add_argument("--output-dir", default="my_tests/generated",
                         help="输出目录")

    args = parser.parse_args()

    if args.mode == "initial":
        generate_initial_tests(args.file, args.function, args.output)
    elif args.mode == "coverage":
        generate_coverage_gap_tests(args.uncovered, args.source_file,
                                    args.existing_test, args.output)
    elif args.mode == "mutation":
        generate_mutation_tests(args.source_file, args.function,
                                args.mutant_desc, args.existing_test, args.output)
    elif args.mode == "batch":
        generate_batch_initial(args.output_dir)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()