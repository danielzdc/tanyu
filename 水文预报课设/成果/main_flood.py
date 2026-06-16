"""
新安江次洪模型 (Δt=1h) — 多子流域 + 马斯京根分段河道演算
"""
import numpy as np
from sub_basin import run_sub_basin, muskingum_segment_routing


def convert_params_daily_to_hourly(params_daily, dt_hours=1.0):
    """日模型参数转换到小时尺度"""
    D = 24.0 / dt_hours
    p = params_daily.copy()

    # CI, CG
    p['CI'] = p['CI'] ** (1.0 / D)
    p['CG'] = p['CG'] ** (1.0 / D)

    # KG, KI
    KG_day = p.get('KG', 0.30)
    KI_day = p.get('KI', 0.40)
    total_day = KG_day + KI_day
    if total_day > 0:
        total_hourly = 1.0 - (1.0 - total_day) ** (1.0 / D)
        p['KG'] = total_hourly * KG_day / total_day
        p['KI'] = total_hourly * KI_day / total_day

    # SM: 次洪需加大(~1.5倍)
    p['SM'] = p.get('SM', 20.0) * 1.5

    # CS, L: 日模型值直接用于小时模型（保持相同物理意义）
    # 不覆盖，使用传入的参数值进行率定

    return p


def run_flood_model_multi(P_stations, E0_hourly, sub_areas, sub_nseg_flood,
                           params_hourly, x_muskingum, init_states=None):
    """
    多子流域次洪模型

    参数:
    P_stations: (n_hours, 10) 各站小时降雨
    E0_hourly: (n_hours,) 小时蒸发
    sub_areas: (10,) 子流域面积
    sub_nseg_flood: (10,) 各子流域马斯京根分段数(呈村=0, 其余=2~5)
    params_hourly: 小时尺度模型参数
    x_muskingum: 马斯京根总X参数(0.30~0.35)
    init_states: 各子流域初始状态

    返回:
    Q_total: (n_hours,) 流域出口总流量
    sub_results: 各子流域结果
    """
    n_subs = 10
    n_hours = len(E0_hourly)

    sub_Qs = []  # 各子流域出口流量

    for i in range(n_subs):
        P_sub = P_stations[:, i]
        area = sub_areas[i]
        n_seg = int(sub_nseg_flood[i])

        state = init_states[i] if init_states else None
        result = run_sub_basin(P_sub, E0_hourly, area, 1.0, params_hourly, state)

        Q_sub_outlet = result['Q']  # 子流域出口流量

        if n_seg > 0:
            # 马斯京根分段演算到流域出口
            Q_routed = muskingum_segment_routing(Q_sub_outlet, n_seg, x_muskingum, 1.0)
            sub_Qs.append(Q_routed)
        else:
            # 呈村(n=0)已在流域出口, 不演算
            sub_Qs.append(Q_sub_outlet)

    # 同时段所有子流域出流量相加
    Q_total = np.sum(sub_Qs, axis=0)

    return Q_total, sub_Qs


if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from data_reader import read_xaj_data, extract_flood_data

    excel_path = os.path.join(os.path.dirname(__file__), '..',
                              '呈村流域资料（含场次洪水）-0613更新场次洪水实测流量.xls')
    daily, hourly, subs, events, param_ref = read_xaj_data(excel_path)
    weights = subs['area_weights']
    sub_areas = subs['areas']

    daily_params = {
        'K': 0.8, 'WUM': 20, 'WLM': 60, 'WDM': 40, 'C': 0.18,
        'WM': 120, 'b': 0.3, 'IM': 0.01,
        'SM': 30, 'EX': 1.5, 'KG': 0.30, 'KI': 0.40,
        'CI': 0.85, 'CG': 0.985, 'CS': 0.5, 'L': 2
    }
    hour_params = convert_params_daily_to_hourly(daily_params)

    flood_event = events['flood'][0]
    flood_data = extract_flood_data(hourly, flood_event)

    if flood_data:
        # 小时E0: sin分布全天>0, 峰值14:00, 部分天只有部分小时自然少蒸发
        from datetime import timedelta
        FULL_DAY_RAW_SUM = 12.0
        daily_e0_map = {}
        for i, dt in enumerate(daily['dates']):
            daily_e0_map[dt.date()] = daily['E0'][i]
        default_e0 = daily['E0'].mean()

        E0_hourly = np.zeros(flood_data['n'])
        start_dt = flood_event['start']
        for i in range(flood_data['n']):
            dt = start_dt + timedelta(hours=i)
            actual_hour = dt.hour
            day_e0 = daily_e0_map.get(dt.date(), default_e0)
            raw = 0.5 + 0.45 * np.sin(2 * np.pi * (actual_hour - 8) / 24)
            E0_hourly[i] = raw * day_e0 / FULL_DAY_RAW_SUM

        Q_total, sub_Qs = run_flood_model_multi(
            flood_data['P_stations'], E0_hourly,
            sub_areas, subs['m_routing_flood'],
            hour_params, x_muskingum=0.30
        )
        print(f"次洪模型: Q范围=[{Q_total.min():.1f}, {Q_total.max():.1f}] m3/s")
        print(f"实测: Q范围=[{flood_data['Q_obs'].min():.1f}, {flood_data['Q_obs'].max():.1f}]")
        print(f"子流域分段: {subs['m_routing_flood']}")
