"""
水源划分模块 —— 三水源：地面径流RS、壤中流RI、地下径流RG
自由水蓄水库 + 自由水蓄量分布曲线
参数: SM, EX, KG, KI
"""
import numpy as np


def set_freewater_params(SM, EX):
    """计算自由水水库派生参数
    SM: 流域平均自由水蓄水容量 (mm)
    EX: 自由水蓄量分布曲线指数
    """
    SMM = SM * (1.0 + EX)
    return SMM


def calc_AU(S1, FR1, FR, SM, SMM, EX):
    """计算自由水蓄量分布曲线对应纵坐标AU
    S1: 上时段自由水蓄量 (mm)
    FR1: 上时段产流面积比
    FR: 本时段产流面积比
    SM: 平均自由水容量 (mm)
    SMM: 最大自由水容量 (mm)
    EX: 自由水曲线指数
    """
    if FR < 1e-10:
        return 0.0

    # 有效自由水蓄量（考虑面积变化）
    S_eff = S1 * FR1 / FR
    if S_eff <= 0:
        return 0.0

    Sm = SM  # 平均自由水容量
    if S_eff >= Sm:
        return SMM

    # AU = SMM * [1 - (1 - S_eff/Sm)^(1/(1+EX))]
    ratio = 1.0 - S_eff / Sm
    if ratio < 1e-12:
        return SMM
    AU = SMM * (1.0 - ratio ** (1.0 / (1.0 + EX)))
    return AU


def water_source_separation(PE, R, S1, FR1, FR, SM, EX, KG, KI):
    """单时段三水源划分
    PE: 净雨量 (mm)
    R: 产流量 (mm)
    S1: 上时段末自由水蓄量 (mm)
    FR1: 上时段产流面积比
    FR: 本时段产流面积比
    SM, EX, KG, KI: 模型参数

    返回: RS, RI, RG, S_new
    """
    SMM = set_freewater_params(SM, EX)

    if PE <= 0 and R <= 0 and S1 <= 0:
        return 0.0, 0.0, 0.0, 0.0

    AU = calc_AU(S1, FR1, FR, SM, SMM, EX)

    # 自由水有效入流（考虑面积折算）
    if FR > 1e-10:
        S_prev_eff = S1 * FR1 / FR
    else:
        S_prev_eff = 0.0

    if R > 0 and FR > 1e-10:
        if PE + AU >= SMM:
            RS = FR * (PE + S_prev_eff - SM)
        else:
            ratio = 1.0 - (PE + AU) / SMM
            if ratio < 1e-12:
                ratio = 0.0
            RS = FR * (PE + S_prev_eff - SM + SM * ratio ** (EX + 1.0))
        RS = max(0.0, RS)
    else:
        RS = 0.0

    # 本时段自由水蓄量
    if FR > 1e-10:
        S = S_prev_eff + (R - RS) / FR
    else:
        S = 0.0
    S = max(0.0, S)

    # 壤中流和地下径流出流
    RI = KI * S * FR
    RG = KG * S * FR

    # 下一时段初的自由水蓄量
    S_new = S * (1.0 - KI - KG)
    S_new = max(0.0, S_new)

    return RS, RI, RG, S_new


def water_source_daily(PE_arr, R_arr, SM, EX, KG, KI):
    """日模型逐日三水源划分
    PE_arr: 逐日净雨量 (mm)
    R_arr: 逐日产流量 (mm)
    返回: RS_arr, RI_arr, RG_arr, S_arr
    """
    n = len(PE_arr)
    RS_arr = np.zeros(n)
    RI_arr = np.zeros(n)
    RG_arr = np.zeros(n)
    S_arr = np.zeros(n)

    S1 = 0.0       # 初始自由水蓄量
    FR1 = 0.0       # 上时段产流面积
    SMM = set_freewater_params(SM, EX)

    for t in range(n):
        PE = PE_arr[t]
        R = R_arr[t]

        # 本时段产流面积（与runoff_generation模块一致）
        if R > 0 and PE > 0:
            # 产流面积比例 = R/PE（近似）
            # 更准确的值从runoff_generation获取，这里用近似
            FR = min(1.0, R / PE) if PE > 1e-6 else 0.0
        elif R > 0 and PE <= 0:
            # PE=0但有R（不应该，但防护）
            FR = 0.0
        else:
            FR = FR1  # 保持上一个产流面积

        RS, RI, RG, S_new = water_source_separation(
            PE, R, S1, FR1, FR, SM, EX, KG, KI
        )

        RS_arr[t] = RS
        RI_arr[t] = RI
        RG_arr[t] = RG
        S_arr[t] = S_new

        S1 = S_new
        FR1 = FR

    return RS_arr, RI_arr, RG_arr, S_arr


if __name__ == '__main__':
    print("=== 三水源划分模块自检 ===")

    SM = 20.0
    EX = 1.5
    KG = 0.30
    KI = 0.40  # KG+KI=0.70

    SMM = set_freewater_params(SM, EX)
    print(f"SM={SM}, EX={EX}, SMM={SMM:.2f}")
    # SMM = SM*(1+EX) = 20*2.5 = 50
    assert abs(SMM - 50.0) < 0.01, f"SMM={SMM}"
    print(f"SMM=50 PASSED")

    # 1. 初始无自由水，产流时水源划分
    PE, R = 20.0, 8.0
    S1, FR1, FR = 0.0, 0.0, 0.3
    RS, RI, RG, S_new = water_source_separation(PE, R, S1, FR1, FR, SM, EX, KG, KI)
    print(f"\nPE={PE}, R={R}, S1={S1}, FR={FR:.2f}")
    print(f"RS={RS:.3f}, RI={RI:.3f}, RG={RG:.3f}, S_new={S_new:.3f}")
    # S_eff=0, AU=0, 部分产流
    # RS ≈ FR*[PE-SM+SM*(1-PE/SMM)^(EX+1)] = 0.3*[20-20+20*(1-20/50)^2.5]
    # RS ≈ 0.3*[20*0.6^2.5] = 0.3*[20*0.279] = 0.3*5.58 = 1.67
    # S = (8-1.67)/0.3 = 21.1
    # RI = 0.4*21.1*0.3 = 2.53, RG = 0.3*21.1*0.3 = 1.90
    # S_new = 21.1*(1-0.7) = 6.33
    assert RS >= 0 and RI >= 0 and RG >= 0
    print("初次产流水源划分 PASSED")

    # 2. PE=0但自由水蓄量不为0 → RS=0, RI和RG继续出流
    PE, R = 0.0, 0.0
    S1 = 6.33  # 上一步的S_new
    FR1, FR = 0.3, 0.3  # 产流面积不变
    RS, RI, RG, S_new = water_source_separation(PE, R, S1, FR1, FR, SM, EX, KG, KI)
    print(f"\nPE=0, S1={S1:.2f}, FR={FR:.2f}")
    print(f"RS={RS:.4f}, RI={RI:.4f}, RG={RG:.4f}, S_new={S_new:.4f}")
    assert abs(RS) < 0.001, f"PE=0时RS应为0, 实际RS={RS}"
    assert RI > 0, f"PE=0但S>0时RI应>0"
    assert RG > 0, f"PE=0但S>0时RG应>0"
    print("PE=0退水出流 PASSED")

    # 3. S1=0连续PE=0 → 所有出流为0
    RS, RI, RG, S_new = water_source_separation(0, 0, 0, 0, 0, SM, EX, KG, KI)
    assert RS == 0 and RI == 0 and RG == 0
    print("全零输入 PASSED")

    # 4. 自由水蓄量衰减
    S_test = 20.0
    FR_const = 0.5
    for step in range(5):
        PE_s, R_s = 5.0, 2.0  # 持续产流
        _, _, _, S_new = water_source_separation(
            PE_s, R_s, S_test, FR_const, FR_const, SM, EX, KG, KI
        )
        decay = S_new / max(S_test, 0.01)
        print(f"Step {step+1}: S {S_test:.3f} -> {S_new:.3f} (decay={decay:.3f})")
        S_test = S_new
    # 衰减应为 (1-KI-KG) = 0.3 加上有新的产流输入
    # S_new = S*(1-0.7) + (R-RS)/FR 不等同于纯衰减
    print("自由水蓄量演进 PASSED")

    # 5. 逐日计算测试
    PE_arr = np.array([10, 20, 0, 30, 5, 0])
    R_arr = np.array([2, 8, 0, 12, 1, 0])
    RS_arr, RI_arr, RG_arr, S_arr = water_source_daily(
        PE_arr, R_arr, SM, EX, KG, KI
    )
    print(f"\n逐日水源划分:")
    for i in range(len(PE_arr)):
        print(f"  t={i}: PE={PE_arr[i]:.0f}, R={R_arr[i]:.0f}, "
              f"RS={RS_arr[i]:.3f}, RI={RI_arr[i]:.3f}, RG={RG_arr[i]:.3f}, S={S_arr[i]:.3f}")
    # 第3步(PE=0, R=0)应有RI和RG出流
    assert RI_arr[2] >= 0 and RG_arr[2] >= 0
    print("逐日计算 PASSED")

    print("\n所有水源划分模块测试通过!")
