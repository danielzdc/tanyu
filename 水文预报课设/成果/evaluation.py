"""
精度评定模块
日模型: 径流深相对误差 + 确定性系数
次洪模型: 径流深相对误差 + 洪峰相对误差 + 峰现时差 + 确定性系数
"""
import numpy as np


def runoff_depth_error(R_sim, R_obs):
    """径流深相对误差 (%)
    R_sim: 模拟径流深 (mm)
    R_obs: 实测径流深 (mm)
    """
    return abs(R_sim - R_obs) / max(R_obs, 0.01) * 100.0


def nash_sutcliffe(Q_sim, Q_obs):
    """确定性系数 (Nash-Sutcliffe Efficiency)
    DC = 1 - Σ(Q_sim-Q_obs)² / Σ(Q_obs-Q_mean)²
    """
    numerator = np.sum((Q_sim - Q_obs) ** 2)
    denominator = np.sum((Q_obs - np.mean(Q_obs)) ** 2)
    if denominator < 1e-10:
        return -999.0
    return 1.0 - numerator / denominator


def peak_flow_error(Qp_sim, Qp_obs):
    """洪峰相对误差 (%)"""
    return abs(Qp_sim - Qp_obs) / max(Qp_obs, 0.01) * 100.0


def peak_time_error(tp_sim, tp_obs, dt_hours=1.0):
    """峰现时差 (时段数)"""
    return abs(tp_sim - tp_obs) * dt_hours


def evaluate_daily(Q_sim, Q_obs, R_sim, R_obs):
    """日模型精度评定
    返回: dict with keys R_err, DC
    """
    results = {}
    results['R_err'] = runoff_depth_error(R_sim, R_obs)
    results['DC'] = nash_sutcliffe(Q_sim, Q_obs)
    results['Qp_sim'] = np.max(Q_sim)
    results['Qp_obs'] = np.max(Q_obs)
    return results


def evaluate_flood(Q_sim, Q_obs, R_sim, R_obs, dt_hours=1.0):
    """次洪模型精度评定
    返回: dict with keys R_err, Qp_err, Tp_err, DC
    """
    results = {}
    results['R_err'] = runoff_depth_error(R_sim, R_obs)
    results['DC'] = nash_sutcliffe(Q_sim, Q_obs)

    # 洪峰误差
    idx_sim = np.argmax(Q_sim)
    idx_obs = np.argmax(Q_obs)
    results['Qp_err'] = peak_flow_error(Q_sim[idx_sim], Q_obs[idx_obs])
    results['Tp_err'] = peak_time_error(idx_sim, idx_obs, dt_hours)
    results['Qp_sim'] = Q_sim[idx_sim]
    results['Qp_obs'] = Q_obs[idx_obs]
    results['tp_sim'] = idx_sim
    results['tp_obs'] = idx_obs

    return results


def calc_total_runoff(Q_obs, F, dt_hours):
    """由流量过程计算径流深
    Q_obs: 实测流量 (m³/s)
    F: 流域面积 km²
    dt_hours: 时段长 小时
    返回: R_obs (mm)
    """
    R_obs = np.sum(Q_obs) * 3.6 * dt_hours / F
    return R_obs


def calc_total_runoff_from_sim(R_arr, area_factor=1.0):
    """由产流输出计算总径流深
    R_arr: 产流量系列 (mm)
    """
    return np.sum(R_arr) * area_factor


if __name__ == '__main__':
    print("=== 精度评定模块自检 ===")

    # 1. 径流深误差
    assert abs(runoff_depth_error(105, 100) - 5.0) < 0.01
    assert abs(runoff_depth_error(85, 100) - 15.0) < 0.01
    print("径流深误差 PASSED")

    # 2. 确定性系数
    Q_sim = np.array([1, 3, 5, 3, 1])
    Q_obs = np.array([1, 4, 6, 4, 2])
    dc = nash_sutcliffe(Q_sim, Q_obs)
    print(f"DC={dc:.4f}")
    assert dc > 0.5  # 应当较好
    print("确定性系数 PASSED")

    # 3. 洪峰误差
    Qp_err = peak_flow_error(90, 100)
    assert abs(Qp_err - 10.0) < 0.01
    print("洪峰误差 PASSED")

    # 4. 峰现时差
    Tp_err = peak_time_error(5, 3, 1.0)
    assert Tp_err == 2.0
    print("峰现时差 PASSED")

    # 5. 流量→径流深换算
    F = 290.0
    Q_arr = np.ones(24) * 10  # 10 m3/s for 24h
    R = calc_total_runoff(Q_arr, F, 1.0)
    expected = 10 * 24 * 3.6 / 290  # about 2.98 mm
    print(f"Q=10*24h -> R={R:.3f}mm (expected={expected:.2f})")

    print("\n所有精度评定测试通过!")
