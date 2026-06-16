"""
蒸散发计算模块 —— 三层蒸发模式
参数: K, WUM, WLM, C
"""
import numpy as np


def evaporation_single(P, E0, WU, WL, WD, K, WUM, WLM, C):
    """单时段三层蒸发计算
    P: 降水量 (mm)
    E0: 蒸发皿蒸发量 (mm)
    WU, WL, WD: 三层初始土壤含水量 (mm)
    K: 蒸散发折算系数
    WUM, WLM: 上/下层蓄水容量 (mm)
    C: 深层蒸散发系数

    返回: E, WU_new, WL_new, WD_new
    """
    EP = K * E0  # 蒸发能力

    if WU + P >= EP:
        # Case 1: 上层充分供水
        EU = EP
        EL = 0.0
        ED = 0.0
    else:
        EU = WU + P
        remaining = EP - EU
        if WL >= C * WLM:
            # Case 2: 下层按比例供水
            EL = remaining * WL / WLM
            ED = 0.0
        elif WL >= C * remaining:
            # Case 3: 下层按C系数供水
            EL = C * remaining
            ED = 0.0
        else:
            # Case 4: 下层不足，深层补充
            EL = WL
            ED = C * remaining - EL
            if ED < 0:
                ED = 0.0

    # 更新各层土壤含水量
    WU_new = max(0.0, WU + P - EU)
    WL_new = max(0.0, WL - EL)
    WD_new = max(0.0, WD - ED)

    E = EU + EL + ED  # 总蒸发量

    return E, WU_new, WL_new, WD_new


def evaporation_daily(P, E0, WU, WL, WD, K, WUM, WLM, C, WDM):
    """日模型逐日三层蒸发计算
    P: 逐日降雨量, shape (n_days,)
    E0: 逐日蒸发皿蒸发量, shape (n_days,)
    WU, WL, WD: 初始值 (标量)
    返回: E_array, WU_end, WL_end, WD_end
    """
    n = len(P)
    E_arr = np.zeros(n)
    WU_arr = np.zeros(n)
    WL_arr = np.zeros(n)
    WD_arr = np.zeros(n)
    EU_arr = np.zeros(n)
    EL_arr = np.zeros(n)
    ED_arr = np.zeros(n)

    for t in range(n):
        E_arr[t], WU, WL, WD = evaporation_single(
            P[t], E0[t], WU, WL, WD, K, WUM, WLM, C
        )
        # 不截断重分配——超容量水保留在各层，产流公式自然处理

        WU_arr[t] = WU
        WL_arr[t] = WL
        WD_arr[t] = WD

    return E_arr, WU_arr, WL_arr, WD_arr


def evaporation_hourly(P, E0, WU, WL, WD, K, WUM, WLM, C, WDM):
    """次洪模型逐时三层蒸发计算（与日模型逻辑相同）"""
    if len(P) == 0:
        return np.array([]), WU, WL, WD
    return evaporation_daily(P, E0, WU, WL, WD, K, WUM, WLM, C, WDM)


if __name__ == '__main__':
    # === 自检1：手算验证 ===
    # Case 1: WU+P >= EP
    WU, WL, WD = 15, 60, 40
    E, WU2, WL2, WD2 = evaporation_single(10, 5, WU, WL, WD, 1.0, 20, 80, 0.18)
    print(f"Case 1 (充足供水): E={E:.3f}, WU={WU2:.1f}, WL={WL2:.1f}, WD={WD2:.1f}")
    # EP=5, WU+P=25 >= 5, so EU=5, EL=0, ED=0
    # WU_new = 15+10-5 = 20, WL=60, WD=40
    assert abs(E - 5.0) < 0.01, f"Case1 failed: E={E}"
    assert abs(WU2 - 20) < 0.01, f"Case1 failed: WU2={WU2}"
    print("  PASSED")

    # Case 2: WU+P < EP, WL >= C*WLM (WL完整按比例)
    WU, WL, WD = 5, 60, 40
    # EP = 1.0 * 8 = 8, WU+P = 5+0 = 5 < 8
    # C*WLM = 0.18*80 = 14.4, WL=60 >= 14.4
    # EU=5, EL=(8-5)*60/80=3*0.75=2.25, ED=0
    E, WU2, WL2, WD2 = evaporation_single(0, 8, WU, WL, WD, 1.0, 20, 80, 0.18)
    print(f"Case 2 (下层比例): E={E:.3f}, WU={WU2:.1f}, WL={WL2:.1f}, WD={WD2:.1f}")
    assert abs(E - 7.25) < 0.01, f"Case2 failed: E={E}"
    assert abs(WU2) < 0.01, f"Case2 WU should be 0: {WU2}"
    assert abs(WL2 - 57.75) < 0.01, f"Case2 WL2.1 off: {WL2}"
    print("  PASSED")

    # Case 3: WL between C*rem and C*WLM
    WU, WL, WD = 5, 3, 40
    # EP=8, WU+P=5 < 8, EU=5, remaining=3
    # C*WLM=14.4, WL=3, C*rem=0.54
    # 3 >= 0.54: Case 3: EL=C*rem=0.54, ED=0
    E, WU2, WL2, WD2 = evaporation_single(0, 8, WU, WL, WD, 1.0, 20, 80, 0.18)
    print(f"Case 3 (下层C系数): E={E:.3f}, WU={WU2:.1f}, WL={WL2:.1f}, WD={WD2:.1f}")
    assert abs(WL2 - 2.46) < 0.01, f"Case3 WL2: {WL2}"
    print("  PASSED")

    # Case 4: WL < C*rem
    WU, WL, WD = 5, 0.2, 40
    # EP=8, WU+P=5 < 8, EU=5, remaining=3
    # WL=0.2 < C*rem=0.54
    # EL=WL=0.2, ED=C*rem-EL=0.54-0.2=0.34
    E, WU2, WL2, WD2 = evaporation_single(0, 8, WU, WL, WD, 1.0, 20, 80, 0.18)
    print(f"Case 4 (深层补充): E={E:.3f}, WU={WU2:.1f}, WL={WL2:.1f}, WD={WD2:.1f}")
    assert abs(WL2) < 0.001, f"Case4 WL2 should be 0: {WL2}"
    assert abs(WD2 - 39.66) < 0.01, f"Case4 WD2: {WD2}"
    print("  PASSED")

    # === 自检2：逐日计算验证 ===
    P = np.array([5, 0, 0, 0, 10])
    E0 = np.array([3, 4, 5, 2, 1])
    WU, WL, WD = 20, 80, 40
    E_arr, WU_arr, WL_arr, WD_arr = evaporation_daily(P, E0, WU, WL, WD, 0.9, 20, 80, 0.18, 60)
    print(f"\n逐日蒸发测试:")
    print(f"E_arr: {E_arr}")
    print(f"WU_arr: {WU_arr}")
    print(f"第一天蒸发后WU={WU_arr[0]:.2f}, WL={WL_arr[0]:.2f}")
    # Day 1: EP=0.9*3=2.7, WU+P=20+5=25 >= 2.7
    # EU=2.7, EL=0, ED=0, WU=25-2.7=22.3, cap to 20
    assert abs(WU_arr[0] - 20) < 0.01
    print("  PASSED")

    print("\n所有蒸发模块测试通过!")
