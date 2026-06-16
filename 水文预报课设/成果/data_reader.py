"""
数据读取与预处理模块
功能：读取Excel日数据/小时数据，泰森多边形面雨量计算
"""
import xlrd
import numpy as np
from datetime import datetime, timedelta


def read_xaj_data(excel_path):
    """读取呈村流域Excel数据文件
    返回: daily_data, hourly_data, sub_basins, flood_events, param_ref
    """
    wb = xlrd.open_workbook(excel_path)

    # === Sheet 1: 日资料 ===
    ds = wb.sheet_by_name('日资料')
    daily_data = {}
    daily_data['n_days'] = ds.nrows - 1  # 减去表头
    daily_data['dates'] = []
    daily_data['Q_obs'] = np.zeros(ds.nrows - 1)
    daily_data['E0'] = np.zeros(ds.nrows - 1)        # 蒸发皿蒸发
    # 10个雨量站
    station_names = ['呈村', '汪村', '樟源口', '棣甸', '董坑坞', '用功城', '左龙', '冯村', '田里', '大连']
    daily_data['station_names'] = station_names
    daily_data['P_stations'] = np.zeros((ds.nrows - 1, 10))

    for r in range(1, ds.nrows):
        i = r - 1
        date_float = ds.cell_value(r, 0)
        date_str = str(int(date_float))
        yr, mo, dy = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
        daily_data['dates'].append(datetime(yr, mo, dy))
        daily_data['Q_obs'][i] = ds.cell_value(r, 1)
        daily_data['E0'][i] = ds.cell_value(r, 2)
        for j in range(10):
            daily_data['P_stations'][i, j] = ds.cell_value(r, 3 + j)

    # === Sheet 2: 时段资料 (小时数据) ===
    hs = wb.sheet_by_name('时段资料')
    hourly_data = {}
    hourly_data['n_hours'] = hs.nrows - 1
    hourly_data['datetimes'] = []
    hourly_data['Q_obs'] = np.zeros(hs.nrows - 1)
    hourly_data['P_stations'] = np.zeros((hs.nrows - 1, 10))

    for r in range(1, hs.nrows):
        i = r - 1
        date_float = hs.cell_value(r, 0)
        date_str = str(int(date_float))
        yr, mo, dy = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
        hr = int(date_str[8:10]) if len(date_str) >= 10 else 0
        hourly_data['datetimes'].append(datetime(yr, mo, dy, hr))
        hourly_data['Q_obs'][i] = hs.cell_value(r, 1)
        for j in range(10):
            hourly_data['P_stations'][i, j] = hs.cell_value(r, 2 + j)

    # === Sheet 3: 子流域 (泰森多边形权重) ===
    ss = wb.sheet_by_name('子流域')
    sub_basins = {}
    sub_basins['names'] = []
    sub_basins['areas'] = np.zeros(ss.nrows - 1)
    sub_basins['area_weights'] = np.zeros(ss.nrows - 1)
    sub_basins['m_routing_daily'] = np.zeros(ss.nrows - 1, dtype=int)
    sub_basins['m_routing_flood'] = np.zeros(ss.nrows - 1, dtype=int)

    for r in range(1, ss.nrows):
        i = r - 1
        sub_basins['names'].append(ss.cell_value(r, 1))
        sub_basins['areas'][i] = ss.cell_value(r, 2)
        sub_basins['area_weights'][i] = ss.cell_value(r, 3)
        sub_basins['m_routing_daily'][i] = int(ss.cell_value(r, 4))
        sub_basins['m_routing_flood'][i] = int(ss.cell_value(r, 5))

    # === Sheet 4: 场次洪水 ===
    fs = wb.sheet_by_name('场次')
    flood_events = {}
    flood_events['daily'] = []   # 日模型场次
    flood_events['flood'] = []   # 次洪模型场次

    # 日模型场次 (n=8, 从row 2开始, row 1是重复表头)
    for r in range(2, 10):
        serial_start = fs.cell_value(r, 1)
        serial_end = fs.cell_value(r, 2)
        if isinstance(serial_start, (int, float)) and serial_start > 1000:
            dt_start = datetime(1899, 12, 30) + timedelta(days=int(serial_start))
            dt_end = datetime(1899, 12, 30) + timedelta(days=int(serial_end))
            flood_events['daily'].append({
                'start': dt_start,
                'end': dt_end,
                'type': str(fs.cell_value(r, 3)).strip() if fs.cell_value(r, 3) else ''
            })

    # 次洪模型场次 (n=15, 从row 2开始, row 1是重复表头)
    for r in range(2, 17):
        start_str = str(fs.cell_value(r, 8)).strip()
        end_str = str(fs.cell_value(r, 9)).strip()
        if start_str and len(start_str) > 10 and '-' in start_str:
            try:
                dt_start = datetime.strptime(start_str[:19], '%Y-%m-%d %H:%M:%S')
                dt_end = datetime.strptime(end_str[:19], '%Y-%m-%d %H:%M:%S')
                etype = str(fs.cell_value(r, 10)).strip() if fs.cell_value(r, 10) else ''
                flood_events['flood'].append({'start': dt_start, 'end': dt_end, 'type': etype})
            except Exception as e:
                print(f"Warning: failed to parse flood event row {r}: {e}")

    # === Sheet 5: 参数参考值 ===
    ps = wb.sheet_by_name('参数')
    param_ref = {}
    for r in range(1, ps.nrows):
        name = str(ps.cell_value(r, 0)).strip().replace('：', '').replace(':', '')
        desc = str(ps.cell_value(r, 1)).strip()
        val_str = str(ps.cell_value(r, 2)).strip()
        param_ref[name] = {'desc': desc, 'ref': val_str}

    return daily_data, hourly_data, sub_basins, flood_events, param_ref


def calc_areal_precip(P_stations, area_weights, n_stations=10):
    """泰森多边形法计算面平均降雨量
    P_stations: shape (n_timesteps, n_stations)
    area_weights: shape (n_stations,)
    返回: shape (n_timesteps,)
    """
    return np.dot(P_stations, area_weights)


def extract_flood_data(hourly_data, flood_event):
    """根据起止时间从小时数据中提取场次洪水数据"""
    dts = hourly_data['datetimes']
    start_mask = np.array([dt >= flood_event['start'] for dt in dts])
    end_mask = np.array([dt <= flood_event['end'] for dt in dts])
    mask = start_mask & end_mask

    indices = np.where(mask)[0]
    if len(indices) == 0:
        return None

    flood_data = {
        'datetimes': [dts[i] for i in indices],
        'Q_obs': hourly_data['Q_obs'][indices],
        'P_stations': hourly_data['P_stations'][indices],
        'n': len(indices)
    }
    return flood_data


def date_to_excel_serial(dt):
    """datetime转Excel日期序列号"""
    delta = dt - datetime(1899, 12, 30)
    return delta.days + delta.seconds / 86400.0


def extract_daily_period(daily_data, start_year, end_year):
    """按年份从日数据中提取指定时段"""
    dts = daily_data['dates']
    start_mask = np.array([dt.year >= start_year for dt in dts])
    end_mask = np.array([dt.year <= end_year for dt in dts])
    mask = start_mask & end_mask
    indices = np.where(mask)[0]

    period_data = {
        'dates': [dts[i] for i in indices],
        'Q_obs': daily_data['Q_obs'][indices],
        'E0': daily_data['E0'][indices],
        'P_stations': daily_data['P_stations'][indices],
        'n': len(indices)
    }
    return period_data


if __name__ == '__main__':
    import os
    excel_path = os.path.join(os.path.dirname(__file__), '..',
                              '呈村流域资料（含场次洪水）-0613更新场次洪水实测流量.xls')
    daily, hourly, subs, events, params = read_xaj_data(excel_path)

    print(f"日数据: {daily['n_days']}天, {len(daily['station_names'])}个雨量站")
    print(f"小时数据: {hourly['n_hours']}条")
    print(f"子流域数: {len(subs['names'])}")
    print(f"日模型场次: {len(events['daily'])}")
    print(f"次洪模型场次: {len(events['flood'])}")
    print(f"参数参考值: {len(params)}个")
    print(f"\n雨量站: {daily['station_names']}")
    print(f"权重: {subs['area_weights']}")
    print(f"前5天日期: {[d.strftime('%Y-%m-%d') for d in daily['dates'][:5]]}")

    # 验算面平均雨量
    P_areal = calc_areal_precip(daily['P_stations'], subs['area_weights'])
    print(f"\n前5天面平均雨量: {P_areal[:5]}")
    print(f"前5天实测流量: {daily['Q_obs'][:5]}")
    print(f"前5天蒸发: {daily['E0'][:5]}")
    print(f"\n次洪模型场次样例: {events['flood'][0] if events['flood'] else 'N/A'}")
