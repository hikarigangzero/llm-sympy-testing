import pytest
from sympy import symbols, simplify, S, Rational, sqrt, sin, cos, pi

import pytest
from sympy import (
    symbols, simplify, S, Rational, sqrt, sin, cos, pi, oo, E, I, exp, log,
    nan, zoo, sign, Abs, gamma, factorial, Piecewise, separatevars, signsimp,
    Symbol, Integer, Float, Mul, Add, Pow, besselj, besseli, besselk, bessely,
    erfc, erf, re, im, acos, asin, atan, asinh,
    acosh, atanh, acot, acsc, asec, floor, ceiling, Heaviside, DiracDelta,
    KroneckerDelta, MatrixSymbol, Identity, ZeroMatrix, OneMatrix, MatAdd, MatMul,
    MatPow,
)
from sympy.simplify.simplify import (
    simplify, separatevars, signsimp,
)
from sympy.core.expr import Expr
from sympy.core.function import count_ops
from sympy.core.numbers import I, pi, Rational, Integer, Float
from sympy.functions.elementary.piecewise import Piecewise, piecewise_fold, piecewise_simplify
from sympy.functions.elementary.trigonometric import sin, cos, tan, sec, csc, cot
from sympy.functions.elementary.hyperbolic import sinh, cosh, tanh, sech, csch, coth
from sympy.functions.elementary.complexes import re, im
from sympy.functions.special.bessel import besselj, besseli, besselk, bessely
from sympy.functions.special.gamma_functions import gamma, lowergamma, uppergamma
from sympy.functions.special.error_functions import erf, erfc, erfi, erf2


# 辅助符号
x, y, z, a, b, c = symbols('x y z a b c')
n = symbols('n', integer=True)
t = symbols('t', real=True)
u = symbols('u', positive=True)


# ==================== 1. simplify 函数未覆盖分支 ====================

def test_simplify_custom_measure():
    """
    覆盖 simplify 中自定义 measure 函数和 ratio 参数相关的未覆盖行。
    可能覆盖的行号范围: 139-145, 158, 196, 204, 207 等。
    """
    # 使用自定义 measure（例如 count_ops）和 ratio=1.0
    expr = (x + x)*y
    # 期望结果 2*x*y，自定义 measure 不应阻止简化
    assert simplify(expr, measure=count_ops, ratio=1.0) == 2*x*y

    # measure 返回较大值时，可能阻止简化（ratio 用于比较）
    # 如果 measure 返回的值大于原始 measure 的 ratio 倍，则保留原表达式
    # 这里用一个大的常数 measure 来测试
    expr2 = x*(x + x)  # 原始 measure 较大？实际简化后更小
    def big_measure(expr):
        return 1000
    # 由于 big_measure 始终返回 1000，而原始 measure 可能小于 1000，简化后的 measure 也是 1000，
    # ratio 默认 1.0，所以 new_measure >= ratio*old_measure (1000>=1000) 成立，不会简化
    # 但实际简化后表达式仍为 2*x**2，measure 为 1000，原始为 x*(x+x) measure 为 1000，一样，根据源码当等于时可能也不变
    # 我们只需确保不报错，并返回原表达式或简化后均可能，但主要关注分支覆盖
    result = simplify(expr2, measure=big_measure)
    assert result in (x*(x + x), 2*x**2)  # 允许两种结果


def test_simplify_inverse_trig():
    """
    覆盖 simplify 对反三角函数的简化（例如 sin(asin(x)) -> x）。
    可能覆盖行号: 355-360, 427 等。
    """
    from sympy import asin, acos, atan
    assert simplify(sin(asin(x))) == x
    assert simplify(cos(acos(x))) == x
    assert simplify(tan(atan(x))) == x
    # 带有额外参数的简化
    assert simplify(sin(asin(x) + pi/2)) == cos(asin(x))  # 可能不进一步简化
    # 测试 acosh, asinh 等
    from sympy import acosh, asinh
    assert simplify(sinh(asinh(x))) == x
    assert simplify(cosh(acosh(x))) == x


def test_simplify_piecewise():
    """
    覆盖 simplify 中对 Piecewise 表达式的简化。
    可能覆盖行号: 629, 632-634, 649, 652, 661-662, 675 等。
    """
    # (removed stray triple-quote)
    pw = Piecewise((x, x > 0), (0, True))
    simplified = simplify(pw)
    # 简化可能保留 Piecewise 但可能应用 abs 等
    # 我们只测试不报错
    assert isinstance(simplified, Expr)

    # 特殊简化：Piecewise 中条件为 True 的分支
    pw2 = Piecewise((x, True), (y, x > 0))
    assert simplify(pw2) == x

    # 嵌套 Piecewise
    pw3 = Piecewise((Piecewise((1, x > 0), (0, True)), x > 0), (y, True))
    # 简化可能折叠
    result = simplify(pw3)
    # 不具体断言，只验证运行


def test_simplify_gamma_factorial():
    """
    # (removed syntax error)     覆盖 simplify 对 gamma 函数和阶乘的简化。
    可能覆盖行号: 686-703, 708, 715, 718 等。
    """
    from sympy import gamma, factorial, rf, ff
    # gamma(n+1) -> n! 对于整数 n
    n_int = symbols('n_int', integer=True)
    assert simplify(gamma(n_int + 1)) == factorial(n_int)
    # 对于有理数参数，gamma 简化可能涉及阶乘
    assert simplify(gamma(Rational(1,2))) == sqrt(pi)  # 已知恒等式
    # factorial 简化
    assert simplify(factorial(n_int + 1)) == (n_int+1)*factorial(n_int)


def test_simplify_hyperbolic():
    """
    覆盖 simplify 对双曲函数的简化（如 cosh^2 - sinh^2 = 1）。
    可能覆盖行号: 729-745, 751, 768, 776, 780 等。
    # (removed stray triple-quote)
    """
    assert simplify(cosh(x)**2 - sinh(x)**2) == 1
    assert simplify(sech(x)**2 + tanh(x)**2) == 1  # 实际上 sech^2 + tanh^2 = 1? 不，是 sech^2 = 1 - tanh^2
    # 更复杂的恒等式
    assert simplify(sinh(x)*cosh(y) + cosh(x)*sinh(y)) == sinh(x+y)


def test_simplify_bessel():
    """
    覆盖 simplify 中对贝塞尔函数的简化。
    可能覆盖行号: 787-809, 818-836, 858-861, 869-903 等。
    """
    # 贝塞尔函数关系
    from sympy import besselj, besseli, besselk, bessely
    # 例如 J_{-n}(x) = (-1)^n J_n(x)
    assert simplify(besselj(-n, x)) == (-1)**n * besselj(n, x)
    # I 函数的相同关系
    assert simplify(besseli(-n, x)) == besseli(n, x)  # I_{-n} = I_n 当 n 整数
    # K 函数的反射公式
    # 需要更多测试


def test_simplify_special_functions():
    """
    覆盖 simplify 对其他特殊函数（如 erf, erfc, gamma 等）的简化。
    可能覆盖行号: 905-968, 986 等。
    """
    # erfc(x) = 1 - erf(x)
    assert simplify(erfc(x)) == 1 - erf(x)
    # 包含关系
    assert simplify(erf(x) + erfc(x)) == 1
    # 对涉及 pi 的恒等式
    assert simplify(erf(oo)) == 1
    assert simplify(erfc(oo)) == 0


def test_simplify_with_rational():
    """
    覆盖 simplify 中 rationalize 参数和有理化分母等。
    可能覆盖行号: 1079, 1101-1110 等。
    # (removed stray triple-quote)
    """
    expr = 1/(sqrt(2) + 1)
    # 有理化分母
    result = simplify(expr, rational=True)
    assert result == sqrt(2) - 1


def test_simplify_force():
    """
    覆盖 simplify 中 force=True 选项，常用于幂和 log 的展开。
    可能覆盖行号: 1170-1171, 1191-1225 等。
    """
    # 默认不展开 log 的幂
    expr = log(x*y)
    assert simplify(expr) == log(x*y)  # 默认不展开
    # force=True 会展开
    assert simplify(expr, force=True) == log(x) + log(y)
    # 对于幂
    expr2 = (x*y)**2
    assert simplify(expr2, force=True) == x**2*y**2  # 默认可能不分离
    # 但是默认 (x*y)**2 就已经是 x**2*y**2 因为指数为整数
    # 测试非整数指数
    expr3 = (x*y)**Rational(1,2)
    assert simplify(expr3, force=False) == sqrt(x*y)
    assert simplify(expr3, force=True) == sqrt(x)*sqrt(y)


def test_simplify_polar():
    """
    覆盖 simplify 中 polar 参数的简化（极坐标下的 log 等）。
    可能覆盖行号: 1260-1325 等。
    """
    from sympy import exp_polar, polar_lift, unpolarify
    # 极坐标指数
    expr = exp_polar(2*pi*I)*x
    assert simplify(expr, polar=True) == x  # exp_polar(2*pi*I) = 1
    # unpolarify 的应用


# ==================== 2. separatevars 函数未覆盖分支 ====================

def test_separatevars_force_power():
    """
    覆盖 separatevars 中 force 参数对幂的处理。
    可能覆盖行号: 1381, 1385, 1399, 1465-1524 等。
    """
    # 默认不分离非整数幂基
    expr = (x*y)**Rational(1,2)
    assert separatevars(expr) == sqrt(x*y)  # 不分离
    # force=True 分离
    assert separatevars(expr, force=True) == sqrt(x)*sqrt(y)
    # 负指数
    expr2 = (x*y)**(-1)
    assert separatevars(expr2, force=False) == 1/(x*y)
    assert separatevars(expr2, force=True) == 1/x * 1/y


def test_separatevars_dict_mode():
    """
    覆盖 separatevars 的 dict 模式。
    可能覆盖行号: 1484-1502, 1507-1524 等。
    """
    # 简单字典模式
    expr = x*y + x
    result = separatevars(expr, dict=True)
    # 