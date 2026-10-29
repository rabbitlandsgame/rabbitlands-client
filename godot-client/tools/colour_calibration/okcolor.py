"""Reference OKLab / OKHSL in double precision: a Python port of Bjorn
Ottosson's ok_color.h (https://bottosson.github.io/posts/colorpicker/), used to
freeze the colour model's test vectors and palette coordinates
(tests/test_appearance_colours.gd; colour model spec revision 3).

ok_color.h is MIT licensed:

Copyright (c) 2021 Bjorn Ottosson

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import math

def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def linear_to_srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055

def linear_srgb_to_oklab(r, g, b):
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)

def oklab_to_linear_srgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)

def srgb_to_oklab(rgb):
    return linear_srgb_to_oklab(*(srgb_to_linear(c) for c in rgb))

def oklab_to_srgb(lab):
    return tuple(linear_to_srgb(c) for c in oklab_to_linear_srgb(*lab))

def compute_max_saturation(a, b):
    if -1.88170328 * a - 0.80936493 * b > 1:
        k0, k1, k2, k3, k4 = 1.19086277, 1.76576728, 0.59662641, 0.75515197, 0.56771245
        wl, wm, ws = 4.0767416621, -3.3077115913, 0.2309699292
    elif 1.81444104 * a - 1.19445276 * b > 1:
        k0, k1, k2, k3, k4 = 0.73956515, -0.45954404, 0.08285427, 0.12541070, 0.14503204
        wl, wm, ws = -1.2684380046, 2.6097574011, -0.3413193965
    else:
        k0, k1, k2, k3, k4 = 1.35733652, -0.00915799, -1.15130210, -0.50559606, 0.00692167
        wl, wm, ws = -0.0041960863, -0.7034186147, 1.7076147010
    S = k0 + k1 * a + k2 * b + k3 * a * a + k4 * a * b
    k_l = 0.3963377774 * a + 0.2158037573 * b
    k_m = -0.1055613458 * a - 0.0638541728 * b
    k_s = -0.0894841775 * a - 1.2914855480 * b
    l_ = 1 + S * k_l; m_ = 1 + S * k_m; s_ = 1 + S * k_s
    l = l_ ** 3; m = m_ ** 3; s = s_ ** 3
    l_dS = 3 * k_l * l_ * l_; m_dS = 3 * k_m * m_ * m_; s_dS = 3 * k_s * s_ * s_
    l_dS2 = 6 * k_l * k_l * l_; m_dS2 = 6 * k_m * k_m * m_; s_dS2 = 6 * k_s * k_s * s_
    f = wl * l + wm * m + ws * s
    f1 = wl * l_dS + wm * m_dS + ws * s_dS
    f2 = wl * l_dS2 + wm * m_dS2 + ws * s_dS2
    return S - f * f1 / (f1 * f1 - 0.5 * f * f2)

def find_cusp(a, b):
    S_cusp = compute_max_saturation(a, b)
    rgb = oklab_to_linear_srgb(1, S_cusp * a, S_cusp * b)
    L_cusp = (1 / max(rgb)) ** (1 / 3)
    return L_cusp, L_cusp * S_cusp

def find_gamut_intersection(a, b, L1, C1, L0, cusp=None):
    if cusp is None:
        cusp = find_cusp(a, b)
    cL, cC = cusp
    if ((L1 - L0) * cC - (cL - L0) * C1) <= 0:
        return cC * L0 / (C1 * cL + cC * (L0 - L1))
    t = cC * (L0 - 1) / (C1 * (cL - 1) + cC * (L0 - L1))
    dL = L1 - L0; dC = C1
    k_l = 0.3963377774 * a + 0.2158037573 * b
    k_m = -0.1055613458 * a - 0.0638541728 * b
    k_s = -0.0894841775 * a - 1.2914855480 * b
    l_dt = dL + dC * k_l; m_dt = dL + dC * k_m; s_dt = dL + dC * k_s
    L = L0 * (1 - t) + t * L1; C = t * C1
    l_ = L + C * k_l; m_ = L + C * k_m; s_ = L + C * k_s
    l = l_ ** 3; m = m_ ** 3; s = s_ ** 3
    ldt = 3 * l_dt * l_ * l_; mdt = 3 * m_dt * m_ * m_; sdt = 3 * s_dt * s_ * s_
    ldt2 = 6 * l_dt * l_dt * l_; mdt2 = 6 * m_dt * m_dt * m_; sdt2 = 6 * s_dt * s_dt * s_
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s - 1
    r1 = 4.0767416621 * ldt - 3.3077115913 * mdt + 0.2309699292 * sdt
    r2 = 4.0767416621 * ldt2 - 3.3077115913 * mdt2 + 0.2309699292 * sdt2
    u_r = r1 / (r1 * r1 - 0.5 * r * r2); t_r = -r * u_r
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s - 1
    g1 = -1.2684380046 * ldt + 2.6097574011 * mdt - 0.3413193965 * sdt
    g2 = -1.2684380046 * ldt2 + 2.6097574011 * mdt2 - 0.3413193965 * sdt2
    u_g = g1 / (g1 * g1 - 0.5 * g * g2); t_g = -g * u_g
    b_ = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s - 1
    b1 = -0.0041960863 * ldt - 0.7034186147 * mdt + 1.7076147010 * sdt
    b2 = -0.0041960863 * ldt2 - 0.7034186147 * mdt2 + 1.7076147010 * sdt2
    u_b = b1 / (b1 * b1 - 0.5 * b_ * b2); t_b = -b_ * u_b
    t_r = t_r if u_r >= 0 else 1e30
    t_g = t_g if u_g >= 0 else 1e30
    t_b = t_b if u_b >= 0 else 1e30
    return t + min(t_r, t_g, t_b)

def toe(x):
    k1, k2 = 0.206, 0.03
    k3 = (1 + k1) / (1 + k2)
    return 0.5 * (k3 * x - k1 + math.sqrt((k3 * x - k1) ** 2 + 4 * k2 * k3 * x))

def toe_inv(x):
    k1, k2 = 0.206, 0.03
    k3 = (1 + k1) / (1 + k2)
    return (x * x + k1 * x) / (k3 * (x + k2))

def to_ST(cusp):
    L, C = cusp
    return C / L, C / (1 - L)

def get_ST_mid(a_, b_):
    S = 0.11516993 + 1 / (7.44778970 + 4.15901240 * b_
        + a_ * (-2.19557347 + 1.75198401 * b_
        + a_ * (-2.13704948 - 10.02301043 * b_
        + a_ * (-4.24894561 + 5.38770819 * b_ + 4.69891013 * a_))))
    T = 0.11239642 + 1 / (1.61320320 - 0.68124379 * b_
        + a_ * (0.40370612 + 0.90148123 * b_
        + a_ * (-0.27087943 + 0.61223990 * b_
        + a_ * (0.00299215 - 0.45399568 * b_ - 0.14661872 * a_))))
    return S, T

def get_Cs(L, a_, b_):
    cusp = find_cusp(a_, b_)
    C_max = find_gamut_intersection(a_, b_, L, 1, L, cusp)
    S_max, T_max = to_ST(cusp)
    k = C_max / min(L * S_max, (1 - L) * T_max)
    S_mid, T_mid = get_ST_mid(a_, b_)
    C_a = L * S_mid; C_b = (1 - L) * T_mid
    C_mid = 0.9 * k * math.sqrt(math.sqrt(1 / (1 / C_a ** 4 + 1 / C_b ** 4)))
    C_a = L * 0.4; C_b = (1 - L) * 0.8
    C_0 = math.sqrt(1 / (1 / C_a ** 2 + 1 / C_b ** 2))
    return C_0, C_mid, C_max

def okhsl_to_srgb(h, s, l):
    if l == 1.0:
        return (1.0, 1.0, 1.0)
    if l == 0.0:
        return (0.0, 0.0, 0.0)
    a_ = math.cos(2 * math.pi * h); b_ = math.sin(2 * math.pi * h)
    L = toe_inv(l)
    C_0, C_mid, C_max = get_Cs(L, a_, b_)
    mid = 0.8; mid_inv = 1.25
    if s < mid:
        t = mid_inv * s
        k_1 = mid * C_0; k_2 = 1 - k_1 / C_mid
        C = t * k_1 / (1 - k_2 * t)
    else:
        t = (s - mid) / (1 - mid)
        k_0 = C_mid; k_1 = (1 - mid) * C_mid * C_mid * mid_inv * mid_inv / C_0
        k_2 = 1 - k_1 / (C_max - C_mid)
        C = k_0 + t * k_1 / (1 - k_2 * t)
    rgb = oklab_to_linear_srgb(L, C * a_, C * b_)
    return tuple(linear_to_srgb(c) for c in rgb)

def srgb_to_okhsl(rgb):
    lab = linear_srgb_to_oklab(*(srgb_to_linear(c) for c in rgb))
    C = math.hypot(lab[1], lab[2])
    if C < 1e-12:
        return 0.0, 0.0, toe(lab[0])
    a_ = lab[1] / C; b_ = lab[2] / C
    L = lab[0]
    h = 0.5 + 0.5 * math.atan2(-lab[2], -lab[1]) / math.pi
    C_0, C_mid, C_max = get_Cs(L, a_, b_)
    mid = 0.8; mid_inv = 1.25
    if C < C_mid:
        k_1 = mid * C_0; k_2 = 1 - k_1 / C_mid
        t = C / (k_1 + k_2 * C)
        s = t * mid
    else:
        k_0 = C_mid; k_1 = (1 - mid) * C_mid * C_mid * mid_inv * mid_inv / C_0
        k_2 = 1 - k_1 / (C_max - C_mid)
        t = (C - k_0) / (k_1 + k_2 * (C - k_0))
        s = mid + (1 - mid) * t
    return h, s, toe(L)

def wire_triple(rgb):
    h, s, l = srgb_to_okhsl(rgb)
    return (int(round(h * 240)) % 240 + 1, int(round(s * 100)) + 1, int(round(l * 100)) + 1)

def triple_to_srgb(t):
    return okhsl_to_srgb((t[0] - 1) / 240, (t[1] - 1) / 100, (t[2] - 1) / 100)

def delta_e(lab1, lab2):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(lab1, lab2)))
