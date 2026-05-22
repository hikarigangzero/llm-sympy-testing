"""
人工编写的基线测试用例 —— 针对 SymPy simplify 模块

测试目标模块: sympy/simplify/simplify.py
测试函数:
  - simplify: 通用表达式化简
  - separatevars: 变量分离
  - signsimp: 符号化简
  - logcombine: 对数合并
  - posify: 符号正定性假设
  - hypersimp: 超几何项化简
  - inversecombine: 反函数组合化简
  - nthroot: n次方根化简

这些测试由人工编写，作为基线，后续将与 LLM 生成的测试进行对比。
"""

import pytest
from sympy import (
    symbols, Symbol, Function, Integer, Rational, S, pi, E, I, oo, zoo, nan,
    sqrt, exp, log, sin, cos, tan, asin, acos, atan, sinh, cosh,
    factorial, gamma, binomial, simplify, separatevars,
    signsimp, logcombine, sympify, count_ops, Expr, Add, Mul, Pow,
    Piecewise, Sum, Product,
    Integral, Matrix, And, Or, Eq, Ne, Gt, Lt,
)
from sympy.simplify.simplify import (
    posify, hypersimp, inversecombine, nthroot,
)
from sympy.abc import x, y, z, a, b, c, n, k, t


# ============================================================================
# simplify 测试
# ============================================================================

class TestSimplifyBasic:
    """simplify 基本功能测试"""

    def test_simplify_atomic(self):
        """测试原子表达式的化简（不变）"""
        assert simplify(1) == 1
        assert simplify(pi) == pi
        assert simplify(E) == E
        assert simplify(I) == I
        assert simplify(oo) == oo

    def test_simplify_algebraic(self):
        """测试代数表达式化简"""
        # 多项式合并
        assert simplify(x + x) == 2 * x
        assert simplify(2*x + 3*x) == 5 * x
        assert simplify(x - x) == 0

        # 有理式化简
        assert simplify((x**2 - 1) / (x - 1)) == x + 1
        assert simplify((x**3 + x**2 - x - 1) / (x**2 + 2*x + 1)) == x - 1

        # 分数简化
        e = 1/x + 1/y
        assert simplify(e) == (x + y) / (x * y)

    def test_simplify_trig(self):
        """测试三角表达式化简"""
        # 基本恒等式
        assert simplify(sin(x)**2 + cos(x)**2) == 1
        # 三角化简由 trigsimp 完成
        expr = sin(x)/cos(x)
        assert simplify(expr) == tan(x)

    def test_simplify_log(self):
        """测试对数表达式化简"""
        p = symbols('p', positive=True)
        q = symbols('q', positive=True)
        assert simplify(log(p) + log(q)) == log(p * q)
        assert simplify(log(p) - log(q)) == log(p / q)

    def test_simplify_zero_one(self):
        """测试零和一相关的化简"""
        assert simplify(x * 0) == 0
        assert simplify(x * 1) == x
        assert simplify(x ** 0) == 1
        assert simplify(x ** 1) == x
        assert simplify(0 / x) == 0

    def test_simplify_power(self):
        """测试幂运算化简"""
        assert simplify(x**a * x**b) == x**(a + b)
        # (x**a)**b == x**(a*b) 在无假设条件下不成立
        assert simplify(sqrt(x**2)) == sqrt(x**2)  # 不假设符号


class TestSimplifyAdvanced:
    """simplify 高级功能测试"""

    def test_simplify_ratio(self):
        """测试 ratio 参数 —— 控制化简程度"""
        # ratio=1 时，化简后表达式不能比原表达式长
        expr = 1/(sqrt(2) + 3)
        assert simplify(expr, ratio=1) == expr
        # ratio=oo 时，总是尝试化简
        simplified = simplify(expr, ratio=oo)
        assert simplified != expr

    def test_simplify_measure(self):
        """测试自定义 measure 函数"""
        expr = log(a) + log(b) + log(a) * log(1/b)
        # 默认 measure
        s1 = simplify(expr)
        # 自定义 measure: 增大 POW 权重
        POW = Symbol('POW')
        def my_measure(e):
            cnt = count_ops(e, visual=True).subs(POW, 10)
            cnt = cnt.replace(Symbol, type(S.One))
            return cnt
        s2 = simplify(expr, measure=my_measure)
        assert s2 is not None  # 至少能返回结果

    def test_simplify_rational(self):
        """测试 rational 参数 —— Float 转 Rational"""
        expr = 0.5 * x + 0.25 * x
        result = simplify(expr, rational=True)
        # 化简后应该是 3*x/4 或等价形式
        assert result is not None

    def test_simplify_inverse(self):
        """测试 inverse 参数 —— 反函数组合"""
        # inverse=True 时，asin(sin(x)) 直接返回 x
        result = simplify(asin(sin(x)), inverse=True)
        assert result == x
        # inverse=False 时不做此简化
        result2 = simplify(asin(sin(x)), inverse=False)
        assert result2 != x

    def test_simplify_piecewise(self):
        """测试分段函数化简"""
        pw = Piecewise((x, x > 0), (-x, True))
        result = simplify(pw)
        assert result is not None

    def test_simplify_matrix(self):
        """测试矩阵表达式的化简"""
        A = Matrix([[2*k - n, -k], [-k, k - n]])
        expr = A.inv()
        result = simplify(expr)
        assert result is not None

    def test_simplify_doit(self):
        """测试 doit 参数"""
        from sympy import Derivative
        expr = Derivative(x**2, x)
        # doit=True 时会求值
        assert simplify(expr, doit=True) == 2*x
        # doit=False 时保留导数形式
        assert simplify(expr, doit=False) != 2*x


# ============================================================================
# separatevars 测试
# ============================================================================

class TestSeparatevars:
    """separatevars 变量分离函数测试"""

    def test_separatevars_basic(self):
        """测试基本的变量分离"""
        result = separatevars(2*x**2*z*sin(y) + 2*z*x**2)
        assert result == 2*x**2*z*(sin(y) + 1)

    def test_separatevars_force(self):
        """测试 force 参数"""
        result = separatevars((x*y)**y, force=True)
        assert result == x**y * y**y

    def test_separatevars_not_separable(self):
        """测试不可分离的表达式返回原表达式"""
        eq = 2*x + y*sin(x)
        assert separatevars(eq) == eq

    def test_separatevars_dict_mode(self):
        """测试 dict=True 模式"""
        result = separatevars(2*x**2*z*sin(y) + 2*z*x**2,
                              symbols=(x, y), dict=True)
        assert result is not None
        assert 'coeff' in result
        assert result['coeff'] == 2*z

    def test_separatevars_none_dict(self):
        """测试不可分离时 dict=True 返回 None"""
        eq = 2*x + y*sin(x)
        assert separatevars(eq, symbols=(x, y), dict=True) is None

    def test_separatevars_empty_symbols(self):
        """测试空 symbols 列表"""
        result = separatevars(2*x*y, symbols=[])
        assert result == 2*x*y


# ============================================================================
# signsimp 测试
# ============================================================================

class TestSignsimp:
    """signsimp 符号化简函数测试"""

    def test_signsimp_basic(self):
        """测试基本符号化简"""
        from sympy.abc import x as sx
        n = -1 + 1/x
        expr = n/x/(-n)**2 - 1/n/x
        assert signsimp(expr) == 0

    def test_signsimp_add(self):
        """测试含 Add 的符号化简"""
        from sympy.abc import x as sx
        n = -1 + 1/x
        expr = x*n + x*(-n)
        assert signsimp(expr) == 0

    def test_signsimp_evaluate(self):
        """测试 evaluate 参数"""
        e = exp(y - x)
        # 默认 evaluate=True 时可能返回原表达式
        s = signsimp(e)
        assert s is not None
        # evaluate=False
        s2 = signsimp(e, evaluate=False)
        assert s2 is not None

    def test_signsimp_atom(self):
        """测试原子表达式"""
        assert signsimp(x) == x
        assert signsimp(5) == 5

    def test_signsimp_negative_power(self):
        """测试负幂的符号处理"""
        i = symbols('i', odd=True)
        expr = (-2)**i
        result = signsimp(expr)
        assert result is not None


# ============================================================================
# logcombine 测试
# ============================================================================

class TestLogcombine:
    """logcombine 对数合并函数测试"""

    def test_logcombine_basic(self):
        """测试基本对数合并"""
        p, q, r = symbols('p q r', positive=True)
        a_real = symbols('a_real', real=True)
        assert logcombine(a_real*log(p) + log(q) - log(r)) == log(p**a_real*q/r)

    def test_logcombine_force(self):
        """测试 force 参数"""
        result = logcombine(a*log(x) + log(y) - log(z), force=True)
        assert result == log(x**a*y/z)

    def test_logcombine_no_force(self):
        """测试 force=False 时不合并无假设的变量"""
        result = logcombine(a*log(x) + log(y) - log(z))
        # 无假设时不应强制合并
        assert 'log' in str(result)

    def test_logcombine_single_log(self):
        """测试单个对数"""
        assert logcombine(log(x)) == log(x)

    def test_logcombine_constants(self):
        """测试带常数的对数合并"""
        result = logcombine(2*log(2) + 3*log(3), force=True)
        assert result == log(108)  # 2^2 * 3^3 = 108

    def test_logcombine_complex(self):
        """测试复系数"""
        eq = (2 + 3*I)*log(x)
        assert logcombine(eq, force=True) == eq
        expanded = logcombine(eq.expand(), force=True)
        assert 'log' in str(expanded)


# ============================================================================
# posify 测试
# ============================================================================

class TestPosify:
    """posify 符号正定性假设测试"""

    def test_posify_basic(self):
        """测试基本功能"""
        result, reps = posify(x)
        assert result.name == x.name
        assert result.is_positive  # posify 后的符号应为正

    def test_posify_expression(self):
        """测试表达式"""
        result, reps = posify(x + 1)
        assert result is not None

    def test_posify_negative(self):
        """测试负表达式"""
        result, reps = posify(-x)
        assert result is not None

    def test_posify_multiple(self):
        """测试多符号"""
        result, reps = posify(x*y)
        assert result is not None


# ============================================================================
# hypersimp 测试
# ============================================================================

class TestHypersimp:
    """hypersimp 超几何项化简测试"""

    def test_hypersimp_factorial(self):
        """测试阶乘相关"""
        result = hypersimp(factorial(k), k)
        assert result == k + 1

    def test_hypersimp_binomial(self):
        """测试二项式系数"""
        result = hypersimp(binomial(n, k), k)
        assert result is not None

    def test_hypersimp_gamma(self):
        """测试 Gamma 函数"""
        result = hypersimp(gamma(k), k)
        assert result == k


# ============================================================================
# inversecombine 测试
# ============================================================================

class TestInversecombine:
    """inversecombine 反函数组合化简测试"""

    def test_inversecombine_sin_asin(self):
        """测试 sin(asin(x))"""
        result = inversecombine(sin(asin(x)))
        assert result == x

    def test_inversecombine_asin_sin(self):
        """测试 asin(sin(x))"""
        result = inversecombine(asin(sin(x)))
        assert result == x

    def test_inversecombine_log_exp(self):
        """测试 log(exp(x))"""
        result = inversecombine(log(exp(x)))
        assert result == x

    def test_inversecombine_exp_log(self):
        """测试 exp(log(x))"""
        result = inversecombine(exp(log(x)))
        assert result == x

    def test_inversecombine_nested(self):
        """测试嵌套反函数"""
        result = inversecombine(sin(asin(log(exp(x)))))
        assert result == x

    def test_inversecombine_no_inverse(self):
        """测试无反函数的表达式"""
        result = inversecombine(sin(x))
        assert result == sin(x)


# ============================================================================
# nthroot 测试
# ============================================================================

class TestNthroot:
    """nthroot n次方根化简测试"""

    def test_nthroot_square(self):
        """测试平方根"""
        result = nthroot(4, 2)
        assert result == 2

    def test_nthroot_cube(self):
        """测试立方根"""
        result = nthroot(8, 3)
        assert result == 2

    def test_nthroot_rational(self):
        """测试有理数结果"""
        result = nthroot(Rational(27, 8), 3)
        assert result == Rational(3, 2)

    def test_nthroot_not_exact(self):
        """测试非精确根返回符号形式"""
        result = nthroot(2, 2)
        # nthroot 返回符号形式 sqrt(2) 而非 None
        assert result == sqrt(2)

    def test_nthroot_symbolic(self):
        """测试符号输入"""
        result = nthroot(x, 2)
        # 符号输入返回 sqrt(x)
        assert result == sqrt(x)


# ============================================================================
# 综合测试：多函数协同
# ============================================================================

class TestIntegration:
    """综合测试：模拟真实使用场景"""

    def test_simplify_signsimp_chain(self):
        """先 signsimp 再 simplify 的链式调用"""
        from sympy.abc import x as sx
        n = -1 + 1/x
        expr = n/x/(-n)**2 - 1/n/x
        simplified = simplify(signsimp(expr))
        assert simplified == 0

    def test_logcombine_with_simplify(self):
        """logcombine 与 simplify 配合使用"""
        p, q = symbols('p q', positive=True)
        expr = log(p) + log(q)
        combined = logcombine(expr, force=True)
        assert simplify(combined) == log(p * q)

    def test_separatevars_with_simplify(self):
        """separatevars 后 simplify"""
        expr = 2*x**2*z*sin(y) + 2*z*x**2
        sep = separatevars(expr)
        simplified = simplify(sep)
        assert simplified == 2*x**2*z*(sin(y) + 1)
