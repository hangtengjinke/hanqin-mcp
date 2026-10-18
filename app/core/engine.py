# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""编排层：一次调用产出完整结果。

    北京时间 → 真太阳时 → 四柱干支 → 定局（三法可选）→ 布盘（转/飞）→ 格局与用神分析

这一层是"确定性计算"的出口。它输出的 dict 才允许交给解读层（大模型）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .calendar_util import (
    CHINA_LAT_RANGE,
    CHINA_LON_RANGE,
    mean_to_true_solar,
    four_pillars,
)
from .ju import compare_methods, determine_ju
from .pan import build_pan
from .analysis import analyze


@dataclass
class QiJuOptions:
    method: str = "chaibu"           # chaibu / zhirun / maoshan
    pan_type: str = "zhuan"          # zhuan / fei
    use_true_solar_time: bool = True
    use_eot: bool = True             # 是否叠加均时差
    zishi_sect: str = "next"         # next=晚子时归次日 / same=不换日
    question_type: str = "综合运势"
    include_compare: bool = True     # 是否返回三法对照
    # 来源信息（仅作记录，不参与计算）
    place: str = ""
    longitude: float = 120.0
    latitude: float | None = None


def qi_ju(beijing_dt: datetime, opts: QiJuOptions) -> dict:
    """起局主入口。

    Args:
        beijing_dt: 输入的北京时间（朴素 datetime，东八区）。
        opts: 起局选项。

    Returns:
        完整结果 dict，含：
            input        原始输入与换算过程
            pillars      四柱
            ju           定局结果与推导说明
            ju_compare   三法对照（供从业者比对）
            pan          九宫盘面
            analysis     格局、用神、断语要点
    """
    if opts.method not in ("chaibu", "zhirun", "maoshan"):
        raise ValueError(f"不支持的起局法：{opts.method}")
    if opts.pan_type not in ("zhuan", "fei"):
        raise ValueError(f"不支持的盘式：{opts.pan_type}")
    if opts.zishi_sect not in ("next", "same"):
        raise ValueError(f"不支持的子时界：{opts.zishi_sect}")

    if opts.use_true_solar_time:
        tst = mean_to_true_solar(beijing_dt, opts.longitude, opts.use_eot)
    else:
        tst = beijing_dt

    pillars = four_pillars(tst, zishi_sect=opts.zishi_sect)
    ju = determine_ju(tst, method=opts.method)
    pan = build_pan(pillars, ju, pan_type=opts.pan_type)
    analysis = analyze(pan, question_type=opts.question_type)

    lon_note = ""
    if opts.use_true_solar_time:
        delta_min = (tst - beijing_dt).total_seconds() / 60.0
        lon_note = (f"经度时差 + 均时差合计 {delta_min:+.1f} 分钟"
                    f"（经度 {opts.longitude}°，基准东经120°）")

    return {
        "input": {
            "beijing_time": beijing_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "true_solar_time": tst.strftime("%Y-%m-%d %H:%M:%S"),
            "place": opts.place,
            "longitude": opts.longitude,
            "latitude": opts.latitude,
            "method": opts.method,
            "pan_type": opts.pan_type,
            "zishi_sect": opts.zishi_sect,
            "question_type": opts.question_type,
            "true_solar_note": lon_note or "未启用真太阳时修正",
        },
        "pillars": pillars.as_dict(),
        "ju": ju.as_dict(),
        "ju_compare": compare_methods(tst) if opts.include_compare else {},
        "pan": pan.as_dict(),
        "analysis": analysis,
    }


def validate_coords(longitude: float | None, latitude: float | None) -> list[str]:
    """坐标合法性与范围提示。"""
    warns: list[str] = []
    if longitude is None:
        warns.append("未提供经度，已按东经 120° 计算，真太阳时可能不准。")
        return warns
    if not (CHINA_LON_RANGE[0] <= longitude <= CHINA_LON_RANGE[1]) and not (-180 <= longitude <= 180):
        warns.append(f"经度 {longitude} 超出常规范围，请检查。")
    if latitude is not None and not (CHINA_LAT_RANGE[0] <= latitude <= CHINA_LAT_RANGE[1]):
        warns.append(f"纬度 {latitude} 不在中国境内常规范围，请检查。")
    return warns
