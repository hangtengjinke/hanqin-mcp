# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""历法底座（计算核心层）。

职责：
    1. 真太阳时换算（经度时差 + 均时差）—— 方案文档 6.1
    2. 四柱干支（年柱以立春为界、月柱以节气为界、支持早晚子时开关）
    3. 定气节气时刻查询（太阳黄经天文算法，由 lunar_python 提供）—— 方案文档 6.2

设计原则：本模块只做"时间 → 干支/节气"的确定性换算，不含任何奇门逻辑。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from lunar_python import Solar

from .constants import GAN, JIAZI_INDEX, JIEQI_ORDER, ZHI

# 东经 120 度为东八区标准经线
STANDARD_MERIDIAN = 120.0
# 中国境内经度参考区间，用于参数校验
CHINA_LON_RANGE = (73.0, 135.1)
CHINA_LAT_RANGE = (3.5, 53.6)


# ---------------------------------------------------------------------------
# 一、均时差 Equation of Time
# ---------------------------------------------------------------------------

def equation_of_time_minutes(dt: datetime) -> float:
    """均时差（分钟），NOAA 近似公式，精度约 ±10 秒。

    真太阳时 = 平太阳时 + 均时差。均时差在一年内于 −14.2 ~ +16.4 分钟之间摆动，
    夏至前后约 −2 分钟、11 月初约 +16 分钟。别小看这十几分钟：
    23:00、01:00、03:00 这些时辰边界上，均时差足以把整个命盘推进或退后一个小时辰。
    """
    n = dt.timetuple().tm_yday
    gamma = 2.0 * math.pi / 365.0 * (n - 1 + (dt.hour - 12) / 24.0)
    eot = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    return eot


def mean_to_true_solar(dt: datetime, longitude: float, use_eot: bool = True) -> datetime:
    """平太阳时 → 真太阳时。

    Args:
        dt: 北京时间（东八区）朴素 datetime。
        longitude: 当地经度（东经为正）。
        use_eot: 是否叠加均时差。False 时只做经度修正（部分流派只用经度差）。

    Returns:
        真太阳时（同样以朴素 datetime 表达，不做时区标注）。
    """
    lon_offset_min = (longitude - STANDARD_MERIDIAN) * 4.0   # 每度 4 分钟
    eot_min = equation_of_time_minutes(dt) if use_eot else 0.0
    return dt + timedelta(minutes=lon_offset_min + eot_min)


# ---------------------------------------------------------------------------
# 二、节气（定气）
# ---------------------------------------------------------------------------

@dataclass
class JieQi:
    name: str
    moment: datetime

    @property
    def day(self) -> date:
        return self.moment.date()


def _jieqi_table_at(dt: datetime) -> list[JieQi]:
    """取 dt 所在年份附近的二十四节气（定气）时刻表。"""
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    raw = solar.getLunar().getJieQiTable()
    out: list[JieQi] = []
    for name in JIEQI_ORDER:
        s = raw.get(name)
        if s is None:
            continue
        out.append(JieQi(name, datetime(s.getYear(), s.getMonth(), s.getDay(),
                                        s.getHour(), s.getMinute(), s.getSecond())))
    out.sort(key=lambda x: x.moment)
    return out


_JIEQI_CACHE: dict[tuple[int, int], list[JieQi]] = {}


def jieqi_span(dt: datetime) -> list[JieQi]:
    """返回覆盖 dt 前后各约 1 年的、按时间排序的节气序列（带缓存）。

    lunar_python 的单次节气表只覆盖约一年，跨年查询时会缺项，
    这里用前后各探一次再合并去重，保证 prev/next/argmin 永远有解。
    """
    key = (dt.year, dt.month)
    if key in _JIEQI_CACHE:
        return _JIEQI_CACHE[key]

    merged: dict[tuple[str, str], JieQi] = {}
    for probe in (dt - timedelta(days=200), dt, dt + timedelta(days=200)):
        for item in _jieqi_table_at(probe):
            merged[(item.name, item.moment.isoformat())] = item
    seq = sorted(merged.values(), key=lambda x: x.moment)
    _JIEQI_CACHE[key] = seq
    return seq


def current_jieqi(dt: datetime) -> JieQi:
    """返回 dt 时刻"正在生效"的节气（交节时刻 <= dt 的最后一个）。"""
    span = jieqi_span(dt)
    valid = [j for j in span if j.moment <= dt]
    if valid:
        return valid[-1]
    # 极端兜底：dt 早于缓存窗口首项
    return next(j for j in span if j.moment > dt)


def next_jieqi(dt: datetime) -> JieQi:
    span = jieqi_span(dt)
    for j in span:
        if j.moment > dt:
            return j
    raise RuntimeError("节气表范围不足，无法定位下一个节气")


def nearest_jieqi_by_moment(target: datetime) -> JieQi:
    """返回交节时刻距 target 最近的节气（置闰法"就近归节"用）。"""
    span = jieqi_span(target)
    return min(span, key=lambda j: abs((j.moment - target).total_seconds()))


# ---------------------------------------------------------------------------
# 三、四柱干支
# ---------------------------------------------------------------------------

# 五鼠遁：日干 → 子时天干
_WU_SHU_DUN = {"甲": "甲", "己": "甲", "乙": "丙", "庚": "丙", "丙": "戊",
               "辛": "戊", "丁": "庚", "壬": "庚", "戊": "壬", "癸": "壬"}


def hour_ganzhi(day_gan: str, hour: int) -> str:
    """由日干与小时求时柱干支（五鼠遁）。

    时支：23:00–01:00 子、01:00–03:00 丑 …… 21:00–23:00 亥。
    """
    zhi_idx = ((hour + 1) // 2) % 12          # 23 点 → 0（子）
    start_gan = _WU_SHU_DUN[day_gan]
    gan_idx = (GAN.index(start_gan) + zhi_idx) % 10
    return GAN[gan_idx] + ZHI[zhi_idx]


@dataclass
class Pillars:
    """四柱与派生信息。"""
    year: str
    month: str
    day: str
    hour: str
    zishi_sect: str = "next"          # next=晚子时归次日(默认) / same=晚子时不换日
    used_datetime: datetime = None    # 实际用于取干支的时间（真太阳时）
    xun_shou: str = field(default="")  # 时柱所属旬：甲子 / 甲戌 …
    xun_kong: str = field(default="")  # 旬空两支：如 "寅卯"

    @property
    def hour_gan(self) -> str:
        return self.hour[0]

    @property
    def hour_zhi(self) -> str:
        return self.hour[1]

    @property
    def day_gan(self) -> str:
        return self.day[0]

    @property
    def day_zhi(self) -> str:
        return self.day[1]

    def as_dict(self) -> dict:
        return {
            "year": self.year, "month": self.month, "day": self.day, "hour": self.hour,
            "zishi_sect": self.zishi_sect,
            "xun_shou": self.xun_shou, "xun_kong": self.xun_kong,
        }


def four_pillars(dt: datetime, zishi_sect: str = "next") -> Pillars:
    """按指定子时界流派求四柱。

    年柱：立春为界（getYearInGanZhiExact）。
    月柱：节气为界（getMonthInGanZhiExact）。
    日柱：zishi_sect="next" 时晚子时（23:00 后）归次日；"same" 时不换日。
    时柱：由所选日干按五鼠遁推导，保证与日柱自洽。
    """
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
    lunar = solar.getLunar()

    year_gz = lunar.getYearInGanZhiExact()
    month_gz = lunar.getMonthInGanZhiExact()

    if zishi_sect == "next":
        day_gz = lunar.getDayInGanZhiExact()
    else:
        day_gz = lunar.getDayInGanZhi()

    hour_gz = hour_ganzhi(day_gz[0], dt.hour)

    # 旬与旬空：以时柱为准（奇门的旬首取时旬）
    idx = JIAZI_INDEX[hour_gz]
    xun_head_idx = (idx // 10) * 10
    xun_shou = next(gz for gz, i in JIAZI_INDEX.items() if i == xun_head_idx)
    k1 = ZHI[(xun_head_idx + 10) % 12]
    k2 = ZHI[(xun_head_idx + 11) % 12]
    xun_kong = k1 + k2

    return Pillars(year=year_gz, month=month_gz, day=day_gz, hour=hour_gz,
                   zishi_sect=zishi_sect, used_datetime=dt,
                   xun_shou=xun_shou, xun_kong=xun_kong)


# ---------------------------------------------------------------------------
# 四、符头工具（定局用）
# ---------------------------------------------------------------------------

def is_futou(gz: str) -> bool:
    """是否为符头日（甲日或己日）。"""
    return gz[0] in ("甲", "己")


def is_shangyuan_futou(gz: str) -> bool:
    """是否为上元符头（甲子、己卯、甲午、己酉）。"""
    return gz in ("甲子", "己卯", "甲午", "己酉")


def yuan_of_futou(gz: str) -> int:
    """由符头地支定三元：子午卯酉→上元(0)，寅申巳亥→中元(1)，辰戌丑未→下元(2)。"""
    zhi = gz[1]
    if zhi in "子午卯酉":
        return 0
    if zhi in "寅申巳亥":
        return 1
    return 2


def day_ganzhi(d: date) -> str:
    """某公历日的日干支（取当日 12:00 计算，规避子时边界歧义）。"""
    solar = Solar.fromYmdHms(d.year, d.month, d.day, 12, 0, 0)
    return solar.getLunar().getDayInGanZhi()


def nearest_futou_on_or_before(d: date) -> date:
    """不晚于 d 的最近符头日（甲日或己日）。"""
    cur = d
    for _ in range(61):
        if is_futou(day_ganzhi(cur)):
            return cur
        cur -= timedelta(days=1)
    raise RuntimeError(f"无法在 60 日内定位符头：{d}")


def shangyuan_futou_on_or_before(d: date) -> date:
    """不晚于 d 的最近上元符头日（甲子/己卯/甲午/己酉）。"""
    cur = d
    for _ in range(16):
        if is_shangyuan_futou(day_ganzhi(cur)):
            return cur
        cur -= timedelta(days=1)
    raise RuntimeError(f"无法在 15 日内定位上元符头：{d}")


# ---------------------------------------------------------------------------
# 五、时辰序号（茅山法"以交节起算 60 时辰"用）
# ---------------------------------------------------------------------------

_EPOCH = date(1900, 1, 1)


def shichen_serial(dt: datetime) -> int:
    """连续时辰序号：以 23:00 换子时，每 2 小时一个时辰。"""
    day_no = (dt.date() - _EPOCH).days
    if dt.hour == 23:
        return day_no * 12          # 当日 23:00 起为子时
    if dt.hour == 0:
        return (day_no - 1) * 12    # 00:00–01:00 归前一日子时
    return day_no * 12 + (dt.hour + 1) // 2
