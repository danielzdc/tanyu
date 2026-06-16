"""
次洪模型精细率定 — 约束SM_f>=22, 全参数不超Excel范围
策略: 粗搜→精搜两轮, 同时监控R_err和Qp_err
"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from data_reader import read_xaj_data, extract_flood_data
from main_flood import run_flood_model_multi
from evaluation import evaluate_flood, calc_total_runoff

DAILY = {'K': 1.02, 'WUM': 20, 'WLM': 60, 'WDM': 40, 'C': 0.18,
         'WM': 120, 'b': 0.3, 'IM': 0.01, 'EX': 1.5,
         'SM': 22, 'KG': 0.15, 'KI': 0.55,
         'CI': 0.85, 'CG': 0.985, 'CS': 0.25, 'L': 0}
F = 290.0

# Excel约束
SM_RANGE = (22, 60)     # SM_f >= SM_daily=22
KG_RANGE = (0.01, 0.69)
CI_RANGE = (0.01, 0.90)
CG_RANGE = (0.980, 0.998)
CS_RANGE = (0.10, 0.90)
L_RANGE = (1, 2)
X_RANGE = (0.30, 0.35)

excel_path = os.path.join(os.path.dirname(__file__), '..',
                          '呈村流域资料（含场次洪水）-0613更新场次洪水实测流量.xls')
daily_data, hourly_data, subs, events, param_ref = read_xaj_data(excel_path)
sub_areas = subs['areas']
sub_nseg_flood = subs['m_routing_flood']
flood_rate = [e for e in events['flood'] if e['start'].year <= 1994]
flood_test = [e for e in events['flood'] if e['start'].year >= 1995]

# E0 helpers
def make_hourly_E0(flood_start, n_h, daily_e0_map):
    """生成次洪逐时蒸发, sin分布全天>0, 峰值14:00, 每天总量=对应日E0

    flood_start: datetime, 洪水起始时刻
    n_h: 洪水总小时数
    daily_e0_map: dict {date: E0值}, 日模型逐日E0
    """
    from datetime import timedelta
    default_e0 = np.mean(list(daily_e0_map.values())) if daily_e0_map else 5.0
    FULL_DAY_RAW_SUM = 12.0  # 完整24h的sin权重总和, 始终用此值做分母

    h = np.zeros(n_h)
    for i in range(n_h):
        dt = flood_start + timedelta(hours=i)
        actual_hour = dt.hour  # 0~23, 实际钟点
        day_e0 = daily_e0_map.get(dt.date(), default_e0)
        raw = 0.5 + 0.45 * np.sin(2 * np.pi * (actual_hour - 8) / 24)
        h[i] = raw * day_e0 / FULL_DAY_RAW_SUM
    return h

def get_states(target_date):
    from sub_basin import run_sub_basin
    st = [{'WU': DAILY['WUM']/3, 'WL': DAILY['WLM'], 'WD': DAILY['WDM'],
           'S': 0, 'FR': 0, 'QI': 0, 'QG': 0} for _ in range(10)]
    ti = None
    for i, dt in enumerate(daily_data['dates']):
        if dt.date() == target_date.date(): ti = i; break
    if ti is None: return st
    we = min(180, ti)
    if we > 0:
        for i in range(10):
            r = run_sub_basin(daily_data['P_stations'][:we,i], daily_data['E0'][:we],
                              sub_areas[i], 24, DAILY, st[i])
            st[i] = {'WU': r['WU_end'], 'WL': r['WL_end'], 'WD': r['WD_end'],
                     'S': r['S_end'], 'FR': r['FR_end'], 'QI': r['QI_end'], 'QG': r['QG_end']}
    if ti > we:
        for i in range(10):
            r = run_sub_basin(daily_data['P_stations'][we:ti,i], daily_data['E0'][we:ti],
                              sub_areas[i], 24, DAILY, st[i])
            st[i] = {'WU': r['WU_end'], 'WL': r['WL_end'], 'WD': r['WD_end'],
                     'S': r['S_end'], 'FR': r['FR_end'], 'QI': r['QI_end'], 'QG': r['QG_end']}
    return st

# 建立日E0映射 {date: E0}
daily_e0_map = {}
for i, dt in enumerate(daily_data['dates']):
    daily_e0_map[dt.date()] = daily_data['E0'][i]

print("预加载...")
flood_cache = {}
for fe in flood_rate + flood_test:
    fd = extract_flood_data(hourly_data, fe)
    if fd is None or fd['n'] < 10: continue
    flood_cache[fe['start']] = {'E0_h': make_hourly_E0(fe['start'], fd['n'], daily_e0_map),
                                'states': get_states(fe['start']), 'fd': fd}



def obj_BO_peak(Q_sim, Q_obs):
    w = Q_obs ** 2
    return np.sum(np.abs(Q_sim - Q_obs) * w) / max(np.sum(Q_obs * w), 0.01)

def evaluate_params(p, fe_list):
    """跑多场洪水, 返回 avg_BOw, avg_R_err, avg_Qp_err, n_OK"""
    BOws, R_errs, Qp_errs, Oks = [], [], [], 0
    for fe in fe_list:
        if fe['start'] not in flood_cache: continue
        c = flood_cache[fe['start']]
        Q_sim, _ = run_flood_model_multi(c['fd']['P_stations'], c['E0_h'],
                                         sub_areas, sub_nseg_flood,
                                         p, x_muskingum=p.get('X', 0.30),
                                         init_states=c['states'])
        R_s = Q_sim.sum() * 3.6 / F
        R_o = calc_total_runoff(c['fd']['Q_obs'], F, 1.0)
        ev = evaluate_flood(Q_sim, c['fd']['Q_obs'], R_s, R_o)
        BOws.append(obj_BO_peak(Q_sim, c['fd']['Q_obs']))
        R_errs.append(ev['R_err'])
        Qp_errs.append(ev['Qp_err'])
        if ev['R_err'] <= 20 and ev['Qp_err'] <= 20: Oks += 1
    return np.mean(BOws), np.mean(R_errs), np.mean(Qp_errs), Oks

# ============ 分层精细率定 ============
# 当前最佳参数
best = {'SM': 34, 'KG': 0.03, 'KI': 0.11, 'CI': 0.85, 'CG': 0.985,
        'CS': 0.75, 'L': 1, 'X': 0.30}

def make_p(SM, KG, CI, CG, CS, L, X):
    ki = KG * DAILY['KI'] / DAILY['KG']
    return {**DAILY, 'SM': SM, 'KG': KG, 'KI': ki, 'CI': CI, 'CG': CG,
            'CS': CS, 'L': L, 'X': X}

# === Round 1: KG 精细 (0.01~0.15, step 0.01) ===
print("\n=== R1: KG 精细搜索 (0.01~0.15) ===")
best_bo = 1e10
for kg in np.arange(0.01, 0.16, 0.01):
    kg = round(kg, 3)
    ki = kg * DAILY['KI'] / DAILY['KG']
    p = make_p(best['SM'], kg, best['CI'], best['CG'], best['CS'], best['L'], best['X'])
    bo, re, qe, ok = evaluate_params(p, flood_rate)
    print(f"  KG={kg:.3f} KI={ki:.3f}: BOw={bo:.4f} R={re:.1f}% Qp={qe:.1f}% OK={ok}")
    if bo < best_bo: best_bo = bo; best['KG'] = kg
best['KI'] = best['KG'] * DAILY['KI'] / DAILY['KG']
print(f"最佳 KG={best['KG']:.3f} KI={best['KI']:.3f}")

# === Round 2: SM 精细 (22~50, step 2) ===
print(f"\n=== R2: SM 精细 ({SM_RANGE[0]}~50) ===")
best_bo = 1e10
for sm in np.arange(SM_RANGE[0], 52, 2):
    p = make_p(sm, best['KG'], best['CI'], best['CG'], best['CS'], best['L'], best['X'])
    bo, re, qe, ok = evaluate_params(p, flood_rate)
    print(f"  SM={sm}: BOw={bo:.4f} R={re:.1f}% Qp={qe:.1f}% OK={ok}")
    if bo < best_bo: best_bo = bo; best['SM'] = sm
print(f"最佳 SM={best['SM']}")

# === Round 3: CI 精细 (0.01~0.90, step 0.05) ===
print(f"\n=== R3: CI 精细 ===")
best_bo = 1e10
for ci in np.arange(CI_RANGE[0], CI_RANGE[1], 0.05):
    ci = round(ci, 2)
    p = make_p(best['SM'], best['KG'], ci, best['CG'], best['CS'], best['L'], best['X'])
    bo, re, qe, ok = evaluate_params(p, flood_rate)
    print(f"  CI={ci:.2f}: BOw={bo:.4f} R={re:.1f}% Qp={qe:.1f}% OK={ok}")
    if bo < best_bo: best_bo = bo; best['CI'] = ci
print(f"最佳 CI={best['CI']:.2f}")

# === Round 4: CG 精细 (0.980~0.998) ===
print(f"\n=== R4: CG 精细 ===")
best_bo = 1e10
for cg in [0.980, 0.982, 0.985, 0.988, 0.990, 0.992, 0.995, 0.998]:
    p = make_p(best['SM'], best['KG'], best['CI'], cg, best['CS'], best['L'], best['X'])
    bo, re, qe, ok = evaluate_params(p, flood_rate)
    print(f"  CG={cg:.3f}: BOw={bo:.4f} R={re:.1f}% Qp={qe:.1f}% OK={ok}")
    if bo < best_bo: best_bo = bo; best['CG'] = cg
print(f"最佳 CG={best['CG']:.3f}")

# === Round 5: CS 精细 (0.10~0.90, step 0.05) ===
print(f"\n=== R5: CS 精细 ===")
best_bo = 1e10
for cs in np.arange(CS_RANGE[0], CS_RANGE[1], 0.05):
    cs = round(cs, 2)
    p = make_p(best['SM'], best['KG'], best['CI'], best['CG'], cs, best['L'], best['X'])
    bo, re, qe, ok = evaluate_params(p, flood_rate)
    print(f"  CS={cs:.2f}: BOw={bo:.4f} R={re:.1f}% Qp={qe:.1f}% OK={ok}")
    if bo < best_bo: best_bo = bo; best['CS'] = cs
print(f"最佳 CS={best['CS']:.2f}")

# === Round 6: L 精细 (0~2) ===
print(f"\n=== R6: L 精细 ===")
best_bo = 1e10
for l in range(L_RANGE[0], L_RANGE[1]+1):
    p = make_p(best['SM'], best['KG'], best['CI'], best['CG'], best['CS'], l, best['X'])
    bo, re, qe, ok = evaluate_params(p, flood_rate)
    print(f"  L={l}: BOw={bo:.4f} R={re:.1f}% Qp={qe:.1f}% OK={ok}")
    if bo < best_bo: best_bo = bo; best['L'] = l
print(f"最佳 L={best['L']}")

# === Round 7: X 精细 (0.30~0.35) ===
print(f"\n=== R7: X 精细 ===")
best_bo = 1e10
for x in np.arange(X_RANGE[0], X_RANGE[1]+0.005, 0.005):
    x = round(x, 3)
    p = make_p(best['SM'], best['KG'], best['CI'], best['CG'], best['CS'], best['L'], x)
    bo, re, qe, ok = evaluate_params(p, flood_rate)
    print(f"  X={x:.3f}: BOw={bo:.4f} R={re:.1f}% Qp={qe:.1f}% OK={ok}")
    if bo < best_bo: best_bo = bo; best['X'] = x
print(f"最佳 X={best['X']:.3f}")

# === 最终验证 ===
print("\n" + "=" * 60)
print("全部15场 最终验证")
print("=" * 60)

p_final = make_p(best['SM'], best['KG'], best['CI'], best['CG'], best['CS'], best['L'], best['X'])
flood_results = []
for fe in events['flood']:
    if fe['start'] not in flood_cache: continue
    c = flood_cache[fe['start']]
    Q_sim, _ = run_flood_model_multi(c['fd']['P_stations'], c['E0_h'],
                                     sub_areas, sub_nseg_flood,
                                     p_final, x_muskingum=p_final['X'],
                                     init_states=c['states'])
    R_s = Q_sim.sum() * 3.6 / F
    R_o = calc_total_runoff(c['fd']['Q_obs'], F, 1.0)
    ev = evaluate_flood(Q_sim, c['fd']['Q_obs'], R_s, R_o)
    bow = obj_BO_peak(Q_sim, c['fd']['Q_obs'])
    is_rate = fe['start'].year <= 1994
    ok = "OK" if ev['R_err'] <= 20 and ev['Qp_err'] <= 20 else ""
    print(f"  #{len(flood_results)+1} {'率' if is_rate else '检'} {fe['start'].strftime('%Y-%m-%d')}: "
          f"BOw={bow:.4f} R={ev['R_err']:.1f}% Qp={ev['Qp_err']:.1f}% Tp={ev['Tp_err']:.0f}h DC={ev['DC']:.4f} {ok}")
    flood_results.append({**ev, 'no': len(flood_results)+1, 'is_rate': is_rate, 'BOw': bow})

rate_r = [f['R_err'] for f in flood_results if f['is_rate']]
test_r = [f['R_err'] for f in flood_results if not f['is_rate']]
rate_q = [f['Qp_err'] for f in flood_results if f['is_rate']]
test_q = [f['Qp_err'] for f in flood_results if not f['is_rate']]
rate_bo = [f['BOw'] for f in flood_results if f['is_rate']]
test_bo = [f['BOw'] for f in flood_results if not f['is_rate']]
all_r_ok = sum(1 for f in flood_results if f['R_err'] <= 20)
all_q_ok = sum(1 for f in flood_results if f['Qp_err'] <= 20)
all_ok = sum(1 for f in flood_results if f['R_err'] <= 20 and f['Qp_err'] <= 20)
p_ki = best['KG'] * DAILY['KI'] / DAILY['KG']
print()
print("=== 最终参数 ===")
print(f"SM={best['SM']} KG={best['KG']:.3f} KI={p_ki:.3f} CI={best['CI']:.2f} CG={best['CG']:.3f} CS={best['CS']:.2f} L={best['L']} X={best['X']:.3f}")
print(f"率定: BOw={np.mean(rate_bo):.4f} R={np.mean(rate_r):.1f}% Qp={np.mean(rate_q):.1f}%")
print(f"检验: BOw={np.mean(test_bo):.4f} R={np.mean(test_r):.1f}% Qp={np.mean(test_q):.1f}%")
print(f"双达标: 率定{sum(1 for f in flood_results if f['is_rate'] and f['R_err']<=20 and f['Qp_err']<=20)}/{len(rate_r)} 检验{sum(1 for f in flood_results if not f['is_rate'] and f['R_err']<=20 and f['Qp_err']<=20)}/{len(test_r)}")
