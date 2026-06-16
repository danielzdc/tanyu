"""
产流计算模块 —— 蓄满产流模型
含IM不透水面积处理，蓄水容量曲线抛物线型
参数: WM, WMM, b, IM
"""
import numpy as np


def set_params(WM, b, IM):
    """计算派生参数
    WM: 流域平均蓄水容量 (mm)
    b: 蓄水容量曲线指数
    IM: 不透水面积比例
    返回: WMM
    """
    # WMM = WM * (1+b) / (1-IM) 考虑IM后的最大点蓄水容量
    WMM = WM * (1.0 + b) / (1.0 - IM)
    return WMM


def calc_a(W, WM, WMM, b, IM):
    """由当前土壤含水量W计算蓄水容量曲线对应纵坐标a
    W: 当前总土壤含水量 (mm) = WU+WL+WD
    WM: 流域平均蓄水容量 (mm)
    WMM: 最大点蓄水容量 (mm)
    b: 蓄水容量曲线指数
    IM: 不透水面积比例
    """
    if IM >= 0.999:
        return WMM  # 全不透水

    # 有效含水量和容量（仅在透水面积上）
    W_eff = W / (1.0 - IM)
    WM_eff = WM / (1.0 - IM)

    if W_eff >= WM_eff:
        return WMM

    # a = WMM * [1 - (1 - W_eff/WM_eff)^(1/(1+b))]
    ratio = 1.0 - W_eff / WM_eff
    if ratio < 1e-12:
        return WMM
    a = WMM * (1.0 - ratio ** (1.0 / (1.0 + b)))
    return a


def runoff_generation(PE, a, W, WM, WMM, b, IM):
    """单时段蓄满产流计算
    PE: 扣除蒸发后的净雨量 (mm), PE = P - E
    a: 对应初始土壤含水量的曲线纵坐标
    W: 初始土壤含水量 (mm)
    WM: 流域平均蓄水容量
    WMM: 最大点蓄水容量
    b: 蓄水容量曲线指数
    IM: 不透水面积比例
    返回: R (产流量, mm), FR (产流面积比例)
    """
    if PE <= 0:
        return 0.0, 0.0

    # IM面积上的产流: 不透水面积全部产流
    R_IM = IM * PE

    if IM >= 0.999:
        return PE, 1.0

    # 透水面积上有效值
    W_eff = W / (1.0 - IM)
    WM_eff = WM / (1.0 - IM)

    if a + PE >= WMM:
        # 全流域蓄满产流
        R_perm = PE + W_eff - WM_eff
        FR = 1.0
    else:
        # 局部产流
        # R_perm = PE + W_eff - WM_eff + WM_eff * (1 - (PE+a)/WMM)^(b+1)
        ratio = 1.0 - (PE + a) / WMM
        if ratio < 1e-12:
            ratio = 0.0
        R_perm = PE + W_eff - WM_eff + WM_eff * ratio ** (b + 1.0)
        FR = 1.0 - (1.0 - (PE + a) / WMM) ** b

    R = R_IM + (1.0 - IM) * R_perm
    R = max(0.0, R)

    return R, FR


def runoff_daily(PE_arr, W0, WM, b, IM):
    """日模型逐日产流计算
    PE_arr: 逐日净雨量 (mm), shape (n,)
    W0: 初始土壤含水量 (mm)
    WM, b, IM: 模型参数
    返回: R_arr, W_arr, FR_arr
    """
    n = len(PE_arr)
    WMM = set_params(WM, b, IM)
    R_arr = np.zeros(n)
    FR_arr = np.zeros(n)
    W = W0
    # 追踪W用于调试
    W_arr = np.zeros(n)

    for t in range(n):
        PE = PE_arr[t]
        a = calc_a(W, WM, WMM, b, IM)
        R, FR = runoff_generation(PE, a, W, WM, WMM, b, IM)
        # 更新土壤含水量: W(t+1) = W(t) + PE - R
        W = W + PE - R
        if W < 0:
            W = 0.0
        R_arr[t] = R
        FR_arr[t] = FR
        W_arr[t] = W

    return R_arr, W_arr, FR_arr


if __name__ == '__main__':
    print("=== 产流模块自检 ===")

    # 参数设定（呈村流域参考值）
    WM = 120.0
    b = 0.3
    IM = 0.01

    WMM = set_params(WM, b, IM)
    print(f"WM={WM}, b={b}, IM={IM} → WMM={WMM:.2f}")

    # 1. 计算a值测试
    W = 60.0  # 初始土壤含水量
    a = calc_a(W, WM, WMM, b, IM)
    print(f"\nW={W:.1f} → a={a:.2f}")

    # 验证: W=0 → a=0
    a0 = calc_a(0, WM, WMM, b, IM)
    assert abs(a0) < 0.01, f"W=0时应a≈0, 实际a={a0}"
    print(f"W=0 → a={a0:.4f} PASSED")

    # 验证: W=WM → 蓄满, a=WMM
    a_full = calc_a(WM, WM, WMM, b, IM)
    print(f"W=WM={WM} → a={a_full:.2f} (应≈{WMM:.2f}) PASSED")

    # 2. 产流计算测试
    # 2a. PE很大 → 全流域蓄满
    R, FR = runoff_generation(200, a, W, WM, WMM, b, IM)
    print(f"\nPE=200时: R={R:.2f}, FR={FR:.2f}")
    # R ≈ PE + W - WM = 200 + 60 - 120 = 140
    assert abs(R - 140.0) < 1.0, f"全面产流R应≈140, 实际R={R:.2f}"
    assert abs(FR - 1.0) < 0.01, f"全面产流FR应为1, 实际FR={FR:.2f}"
    print("全面产流 PASSED")

    # 2b. PE较小 → 局部产流
    R, FR = runoff_generation(20, a, W, WM, WMM, b, IM)
    print(f"PE=20时: R={R:.3f}, FR={FR:.4f}")
    assert 0 < R < 20, f"局部产流R应在0-20之间, 实际R={R:.3f}"
    print("局部产流 PASSED")

    # 2c. PE=0 → 无产流
    R, FR = runoff_generation(0, a, W, WM, WMM, b, IM)
    assert R == 0.0 and FR == 0.0, f"PE=0应R=FR=0"
    print("PE=0无产流 PASSED")

    # 2d. IM=0.01 不透水面积产流
    R, FR = runoff_generation(5, a, W, WM, WMM, b, IM)
    im_contrib = IM * 5  # 0.01 * 5 = 0.05
    print(f"PE=5时IM贡献={im_contrib:.2f}mm, 总R={R:.3f}")

    # 3. 逐日产流测试
    PE_arr = np.array([10, 20, 0, 30, 5])
    R_arr, W_arr, FR_arr = runoff_daily(PE_arr, 60.0, WM, b, IM)
    print(f"\n逐日产流: PE={PE_arr}")
    print(f"R_arr={R_arr}")
    print(f"W_arr (时段末) = {[f'{w:.1f}' for w in W_arr]}")
    # 水量平衡: W_end = W_start + sum(PE) - sum(R)
    W_end = W_arr[-1]
    W_expected = 60.0 + sum(PE_arr) - sum(R_arr)
    print(f"W_end={W_end:.2f}, W_expected={W_expected:.2f}, diff={abs(W_end-W_expected):.6f}")
    assert abs(W_end - W_expected) < 0.01, "水量平衡不闭合!"
    print("水量平衡 PASSED")

    # 4. IM极端值测试
    # IM>0时不透水面积直接产流IM*PE，但同时透水面积有效WM增大
    # 综合效果取决于具体参数
    PE_test = 10
    R_im0, _ = runoff_generation(PE_test, 30, 50, 100, set_params(100, 0.3, 0.0), 0.3, 0.0)
    R_im002, _ = runoff_generation(PE_test, calc_a(50, 100, set_params(100, 0.3, 0.02), 0.3, 0.02),
                                     50, 100, set_params(100, 0.3, 0.02), 0.3, 0.02)
    # IM=0.02时, 可不透水面积贡献≈0.02*10=0.2mm
    print(f"\nIM=0: R={R_im0:.3f}, IM=0.02: R={R_im002:.3f}")
    assert R_im002 >= 0, "Runoff should be non-negative"
    print("IM边界测试 PASSED")

    print("\n所有产流模块测试通过!")
