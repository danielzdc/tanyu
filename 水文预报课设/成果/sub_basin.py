"""
单个子流域XAJ模型 — 蒸散发→产流→三水源→坡地汇流→河网汇流
"""
import numpy as np
from evaporation import evaporation_single
from runoff_generation import set_params as rg_set_params, calc_a, runoff_generation
from water_source import water_source_separation


def run_sub_basin(P, E0, area_km2, dt_hours, params, init_state=None, return_detailed=False):
    """
    单个子流域日/时模型计算

    参数:
    P: (n,) 降雨系列 mm
    E0: (n,) 蒸发皿蒸发 mm
    area_km2: 子流域面积 km2
    dt_hours: 时段长 小时
    params: dict with K, WUM, WLM, WDM, C, WM, b, IM, SM, EX, KG, KI, CI, CG, CS, L
    init_state: dict with WU, WL, WD, S, FR, QI, QG (None=默认)
    return_detailed: 是否返回逐时段中间变量(蒸散发分量/产流/水源/汇流各环节)

    返回: dict with keys Q, RS, RI, RG, W_end, S_end 等
          若return_detailed=True, 额外包含WU, WL, WD, EU, EL, ED, PE, a, FR, S, QS, QI, QG, QT, QT_lagged 逐时段序列
    """
    n = len(P)
    K = params['K']
    WUM, WLM, WDM = params['WUM'], params['WLM'], params['WDM']
    C = params['C']
    WM, b, IM = params['WM'], params['b'], params['IM']
    SM, EX = params['SM'], params['EX']
    KG, KI = params['KG'], params['KI']
    CI, CG = params['CI'], params['CG']
    CS, L = params['CS'], params['L']

    WMM = WM * (1.0 + b) / (1.0 - IM)
    U = area_km2 / (3.6 * dt_hours)  # mm -> m3/s 换算系数

    # 初始状态
    if init_state is None:
        WU, WL, WD = WUM, WLM, WDM
        S_val, FR_prev = 0.0, 0.0
        QI_prev, QG_prev = 0.0, 0.0
    else:
        WU = init_state['WU']
        WL = init_state['WL']
        WD = init_state['WD']
        S_val = init_state.get('S', 0.0)
        FR_prev = init_state.get('FR', 0.0)
        QI_prev = init_state.get('QI', 0.0)
        QG_prev = init_state.get('QG', 0.0)

    Q_prev = 0.0  # 河网上时段出流
    # 滞后缓冲区
    lag_buf = np.zeros(max(1, L))
    lag_ptr = 0

    Q_arr = np.zeros(n)
    RS_arr = np.zeros(n)
    RI_arr = np.zeros(n)
    RG_arr = np.zeros(n)
    E_arr = np.zeros(n)
    R_arr = np.zeros(n)

    if return_detailed:
        WU_arr = np.zeros(n); WL_arr = np.zeros(n); WD_arr = np.zeros(n)
        EU_arr = np.zeros(n); EL_arr = np.zeros(n); ED_arr = np.zeros(n)
        PE_arr = np.zeros(n); a_arr = np.zeros(n); FR_arr = np.zeros(n)
        S_arr = np.zeros(n)
        QS_arr = np.zeros(n); QI_arr_d = np.zeros(n); QG_arr_d = np.zeros(n)
        QT_arr = np.zeros(n); QT_lag_arr = np.zeros(n)

    for t in range(n):
        P_t = float(P[t])
        E0_t = float(E0[t])

        # === 蒸散发 ===
        WU_pre, WL_pre, WD_pre = WU, WL, WD
        E_t, WU, WL, WD = evaporation_single(P_t, E0_t, WU, WL, WD, K, WUM, WLM, C)
        EU_t = WU_pre + P_t - WU  # 上层蒸发
        EL_t = WL_pre - WL        # 下层蒸发
        ED_t = E_t - EU_t - EL_t  # 深层蒸发
        W_post = WU + WL + WD
        PE = max(0.0, P_t - E_t)
        W_start = W_post - PE

        # === 产流 ===
        a = calc_a(W_start, WM, WMM, b, IM)
        R, FR = runoff_generation(PE, a, W_start, WM, WMM, b, IM)

        W_new = W_start + PE - R
        if W_new < 0: W_new = 0.0

        # 三层分配: 蒸散发后各层已正确(P→WU, E:WU→WL→WD)
        # R来自地表超渗, 从上向下扣除; 若WU超容量则向下溢流
        remaining_R = R
        if remaining_R > 0:
            rem = min(remaining_R, WU); WU -= rem; remaining_R -= rem
        if remaining_R > 0:
            rem = min(remaining_R, WL); WL -= rem; remaining_R -= rem
        if remaining_R > 0:
            rem = min(remaining_R, WD); WD -= rem

        # WU超容量则向下溢流(重力)
        if WU > WUM:
            overflow = WU - WUM; WU = WUM
            if WL < WLM:
                fill = min(overflow, WLM - WL); WL += fill; overflow -= fill
            WD += overflow
        if WL > WLM:
            overflow = WL - WLM; WL = WLM
            WD += overflow

        # === 水源划分 ===
        if FR > 0 and R > 0:
            RS, RI, RG, S_new = water_source_separation(PE, R, S_val, FR_prev, FR, SM, EX, KG, KI)
        else:
            # PE=0或R=0，但S>0时仍有退水
            RS = 0.0
            RI = KG * S_val * FR_prev if FR_prev > 0 else 0.0
            RG = KG * S_val * FR_prev if FR_prev > 0 else 0.0
            S_new = S_val * (1.0 - KI - KG) if FR_prev > 0 else max(0.0, S_val * (1.0 - KI - KG))
            # 更准确的退水处理
            if FR_prev > 1e-10:
                RS = 0.0
                RI = KI * S_val * FR_prev
                RG = KG * S_val * FR_prev
            else:
                RS = RI = RG = 0.0

        RS = max(0.0, RS)
        RI = max(0.0, RI)
        RG = max(0.0, RG)
        S_new = max(0.0, S_new)

        # === 坡地汇流 ===
        QS = RS * U
        QI = CI * QI_prev + (1.0 - CI) * RI * U
        QG = CG * QG_prev + (1.0 - CG) * RG * U
        QT = QS + QI + QG

        # === 河网滞后演算 ===
        QT_lagged = lag_buf[lag_ptr]
        lag_buf[lag_ptr] = QT
        lag_ptr = (lag_ptr + 1) % len(lag_buf)
        Q_t = CS * Q_prev + (1.0 - CS) * QT_lagged

        Q_arr[t] = Q_t
        RS_arr[t] = RS
        RI_arr[t] = RI
        RG_arr[t] = RG
        E_arr[t] = E_t
        R_arr[t] = R

        if return_detailed:
            WU_arr[t] = WU; WL_arr[t] = WL; WD_arr[t] = WD
            EU_arr[t] = EU_t; EL_arr[t] = EL_t; ED_arr[t] = ED_t
            PE_arr[t] = PE; a_arr[t] = a; FR_arr[t] = FR
            S_arr[t] = S_new
            QS_arr[t] = QS; QI_arr_d[t] = QI; QG_arr_d[t] = QG
            QT_arr[t] = QT; QT_lag_arr[t] = QT_lagged

        # 更新状态
        S_val = S_new
        FR_prev = FR
        QI_prev = QI
        QG_prev = QG
        Q_prev = Q_t

    result = {
        'Q': Q_arr, 'RS': RS_arr, 'RI': RI_arr, 'RG': RG_arr,
        'E': E_arr, 'R': R_arr,
        'WU_end': WU, 'WL_end': WL, 'WD_end': WD,
        'S_end': S_val, 'FR_end': FR_prev,
        'QI_end': QI_prev, 'QG_end': QG_prev
    }
    if return_detailed:
        result.update({
            'WU': WU_arr, 'WL': WL_arr, 'WD': WD_arr,
            'EU': EU_arr, 'EL': EL_arr, 'ED': ED_arr,
            'PE': PE_arr, 'a': a_arr, 'FR_series': FR_arr,
            'S': S_arr,
            'QS': QS_arr, 'QI_series': QI_arr_d, 'QG_series': QG_arr_d,
            'QT': QT_arr, 'QT_lagged': QT_lag_arr,
        })
    return result


def muskingum_segment_routing(Q_in, n_seg, x_total, dt_hours=1.0):
    """马斯京根分段连续演算
    Q_in: 入流过程 (m3/s)
    n_seg: 分段数
    x_total: 总X参数
    dt_hours: 时段长 (h), K_l = dt

    返回: Q_out (m3/s) 在出口断面
    """
    if n_seg <= 0:
        return np.array(Q_in, dtype=float)

    n = int(n_seg)
    K_l = dt_hours  # 每段K = Δt

    # x_l = 1/2 - (1-2x)/(2n)
    x_l = 0.5 - (1.0 - 2.0 * x_total) / (2.0 * n)
    x_l = max(0.0, min(0.5, x_l))  # 约束在合理范围

    # 每段马斯京根系数
    denom = 0.5 * K_l + K_l - K_l * x_l
    if abs(denom) < 1e-10:
        return np.array(Q_in, dtype=float)
    C0 = (0.5 * K_l - K_l * x_l) / denom
    C1 = (0.5 * K_l + K_l * x_l) / denom
    C2 = (-0.5 * K_l + K_l - K_l * x_l) / denom

    Q_work = np.array(Q_in, dtype=float)

    for seg in range(n):
        Q_next = np.zeros(len(Q_work))
        Q_next[0] = Q_work[0]
        for t in range(1, len(Q_work)):
            Q_next[t] = C0 * Q_work[t] + C1 * Q_work[t - 1] + C2 * Q_next[t - 1]
            if Q_next[t] < 0:
                Q_next[t] = 0.0
        Q_work = Q_next

    return Q_work
