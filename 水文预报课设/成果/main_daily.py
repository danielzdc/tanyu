"""
新安江日模型 (Δt=24h) — 多子流域版本
每个子流域独立计算 → 直接相加 → 流域出口总流量
"""
import numpy as np
from sub_basin import run_sub_basin


def run_daily_model_multi(P_stations, E0, sub_areas, sub_nseg_daily, params, init_states=None):
    """
    多子流域日模型

    参数:
    P_stations: (n_days, 10) 各站降雨量 mm
    E0: (n_days,) 蒸发皿蒸发 mm
    sub_areas: (10,) 各子流域面积 km2
    params: dict, 模型参数(日尺度)
    init_states: list[dict] 各子流域初始状态, None=默认

    返回:
    Q_total: (n_days,) 流域出口总流量 m3/s
    sub_results: list[dict] 各子流域详细结果
    """
    n_subs = 10
    n_days = len(E0)

    Q_total = np.zeros(n_days)
    sub_results = []

    for i in range(n_subs):
        P_sub = P_stations[:, i]
        area = sub_areas[i]
        state = init_states[i] if init_states else None
        result = run_sub_basin(P_sub, E0, area, 24.0, params, state)
        Q_total += result['Q']

        sub_results.append({
            'name': f'sub_{i}', 'area': area, 'Q': result['Q'],
            'R_sum': result['R'].sum(), 'E_sum': result['E'].sum(),
            'RS_sum': result['RS'].sum(), 'RI_sum': result['RI'].sum(),
            'RG_sum': result['RG'].sum(),
            'state_end': {
                'WU': result['WU_end'], 'WL': result['WL_end'], 'WD': result['WD_end'],
                'S': result['S_end'], 'FR': result['FR_end'],
                'QI': result['QI_end'], 'QG': result['QG_end']
            }
        })

    return Q_total, sub_results


if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from data_reader import read_xaj_data

    excel_path = os.path.join(os.path.dirname(__file__), '..',
                              '呈村流域资料（含场次洪水）-0613更新场次洪水实测流量.xls')
    daily, hourly, subs, events, param_ref = read_xaj_data(excel_path)
    sub_areas = subs['areas']

    params = {
        'K': 1.02, 'WUM': 20, 'WLM': 60, 'WDM': 40, 'C': 0.18,
        'WM': 120, 'b': 0.3, 'IM': 0.01,
        'SM': 22, 'EX': 1.5, 'KG': 0.15, 'KI': 0.55,
        'CI': 0.85, 'CG': 0.985, 'CS': 0.0, 'L': 0,
        'K_daily': 24.0, 'X_daily': 0.30
    }

    init_daily = [{'WU': 6.7, 'WL': 60, 'WD': 40, 'S': 0, 'FR': 0, 'QI': 0, 'QG': 0} for _ in range(10)]
    Q_total, sub_results = run_daily_model_multi(
        daily['P_stations'], daily['E0'],
        sub_areas, subs['m_routing_daily'], params, init_states=init_daily
    )
    print(f"日模型多子流域: Q范围=[{Q_total.min():.1f}, {Q_total.max():.1f}] m3/s")
    rsums = [f'{r["R_sum"]:.1f}' for r in sub_results]
    print(f"各子流域径流深: {rsums}")
