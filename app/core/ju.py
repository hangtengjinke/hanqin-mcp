# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""定局（计算核心层）—— 起局三法：拆补 / 置闰 / 茅山。

方案文档 6.3 要求"奇门起局存在置闰、拆补、茅山三种方法，结果不同，必须做成可切换参数"。
本模块把三法都实现为可切换参数，并各自返回其推导依据，便于从业者核对。

三法同源异流，核心分歧都在"如何处理符头与节气的错位"：

    拆补法  节气优先。交节即换节气，日干支只负责定三元（符头），
            允许"残局补缺"，上中下三元顺序被打散。主流、最常用。
    置闰法  符头优先。以符头定三元，节气"就近归节"（超神接气），
            偏移量过大时由 ±7.5 日的自然回卷完成一次"闰奇"。
    茅山法  节气至上，完全忽略符头。交节即起上元，上元走满 60 时辰进中元，
            中元走满 60 时辰进下元，下元一直用到下一个交节。

术语：
    符头   甲日或己日（每五日一元之元首）
    上元符头 只有甲子、己卯、甲午、己酉四种，每隔 15 日出现一次
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime

from .calendar_util import (
    JieQi,
    current_jieqi,
    day_ganzhi,
    nearest_futou_on_or_before,
    nearest_jieqi_by_moment,
    shangyuan_futou_on_or_before,
    shichen_serial,
    yuan_of_futou,
)
from .constants import JU_TABLE, YUAN_NAMES, YIN_JIEQI

METHODS = {
    "chaibu": "拆补法",
    "zhirun": "置闰法",
    "maoshan": "茅山法",
}


@dataclass
class JuResult:
    """定局结果。"""
    method: str            # 方法代号 chaibu / zhirun / maoshan
    method_name: str       # 中文名
    dun: str               # 阳遁 / 阴遁
    ju: int                # 局数 1–9
    jieqi: str             # 实际节气（定气）
    jieqi_moment: str      # 交节时刻
    yuan: str              # 上元 / 中元 / 下元
    yuan_index: int        # 0 / 1 / 2
    futou: str             # 所依据的符头日干支
    futou_date: str        # 符头公历日
    reason: str            # 推导说明（给从业者核对用）

    def as_dict(self) -> dict:
        return asdict(self)


def _lookup_xun(dt: datetime, ju: int, dun: str) -> str:
    """由局数反推三奇六仪首仪"戊"所落之宫（供说明文案使用）。"""
    return f"阳遁{ju}局，戊落{JG[ju]}宫" if dun == "阳遁" else f"阴遁{ju}局，戊落{JG[ju]}宫"


JG = {1: "坎一", 2: "坤二", 3: "震三", 4: "巽四", 5: "中五",
      6: "乾六", 7: "兑七", 8: "艮八", 9: "离九"}


def _dun_of(jieqi_name: str) -> str:
    return "阳遁" if jieqi_name not in YIN_JIEQI else "阴遁"


# ---------------------------------------------------------------------------
# 拆补法
# ---------------------------------------------------------------------------

def ju_chaibu(dt: datetime) -> JuResult:
    """拆补法：节气优先，以符头地支定三元。"""
    jq: JieQi = current_jieqi(dt)
    futou_date: date = nearest_futou_on_or_before(dt.date())
    futou_gz = day_ganzhi(futou_date)
    yuan_idx = yuan_of_futou(futou_gz)
    dun = _dun_of(jq.name)
    ju = JU_TABLE[dun][jq.name][yuan_idx]

    return JuResult(
        method="chaibu", method_name=METHODS["chaibu"], dun=dun, ju=ju,
        jieqi=jq.name, jieqi_moment=jq.moment.strftime("%Y-%m-%d %H:%M:%S"),
        yuan=YUAN_NAMES[yuan_idx], yuan_index=yuan_idx,
        futou=futou_gz, futou_date=futou_date.isoformat(),
        reason=(
            f"实际节气为{jq.name}（{dun}）；日柱{day_ganzhi(dt.date())}，"
            f"逆推符头为{futou_date.isoformat()} {futou_gz}，"
            f"符头地支「{futou_gz[1]}」定{YUAN_NAMES[yuan_idx]}；"
            f"查《{jq.name}{dun}》三元局数 "
            f"{'/'.join(map(str, JU_TABLE[dun][jq.name]))} → 取{YUAN_NAMES[yuan_idx]}{ju}局。"
        ),
    )


# ---------------------------------------------------------------------------
# 置闰法
# ---------------------------------------------------------------------------

def ju_zhirun(dt: datetime) -> JuResult:
    """置闰法：以符头定三元，节气"就近归节"（超神接气）。

    实现要点：先定位不晚于当日的上元符头 H（每 15 日一个），
    再取交节时刻距 H 最近的节气作为"奇门节气"。
    当符头与节气的累计偏移超过半元（约 7.5 日）时，归属自然回卷一位，
    等效于传统"芒种 / 大雪置闰"的一次闰奇——这正是置闰法"符头优先"的体现。
    """
    h_date: date = shangyuan_futou_on_or_before(dt.date())
    h_gz = day_ganzhi(h_date)
    h_moment = datetime(h_date.year, h_date.month, h_date.day, 0, 0, 0)

    # 就近归节
    jq: JieQi = nearest_jieqi_by_moment(h_moment)
    days = (dt.date() - h_date).days
    yuan_idx = (days // 5) % 3
    dun = _dun_of(jq.name)
    ju = JU_TABLE[dun][jq.name][yuan_idx]

    offset_days = (jq.moment.date() - h_date).days
    super_or_late = "超神（符头先于交节）" if offset_days > 0 else (
        "接气（交节先于符头）" if offset_days < 0 else "正授（符头与交节同日）")

    return JuResult(
        method="zhirun", method_name=METHODS["zhirun"], dun=dun, ju=ju,
        jieqi=jq.name, jieqi_moment=jq.moment.strftime("%Y-%m-%d %H:%M:%S"),
        yuan=YUAN_NAMES[yuan_idx], yuan_index=yuan_idx,
        futou=h_gz, futou_date=h_date.isoformat(),
        reason=(
            f"上元符头为{h_date.isoformat()} {h_gz}，距交节"
            f"（{jq.name} {jq.moment.strftime('%m-%d %H:%M')}）{abs(offset_days)}日，"
            f"属{super_or_late}；就近归节取「{jq.name}」，"
            f"符头后第 {days + 1} 日 → {YUAN_NAMES[yuan_idx]}；"
            f"查《{jq.name}{dun}》→ {ju}局。"
        ),
    )


# ---------------------------------------------------------------------------
# 茅山法
# ---------------------------------------------------------------------------

def ju_maoshan(dt: datetime) -> JuResult:
    """茅山法（不置闰法）：节气至上，以交节起算 60 时辰分三元。"""
    jq: JieQi = current_jieqi(dt)
    elapsed = shichen_serial(dt) - shichen_serial(jq.moment)
    if elapsed < 0:
        elapsed = 0
    yuan_idx = 0 if elapsed < 60 else (1 if elapsed < 120 else 2)
    dun = _dun_of(jq.name)
    ju = JU_TABLE[dun][jq.name][yuan_idx]

    return JuResult(
        method="maoshan", method_name=METHODS["maoshan"], dun=dun, ju=ju,
        jieqi=jq.name, jieqi_moment=jq.moment.strftime("%Y-%m-%d %H:%M:%S"),
        yuan=YUAN_NAMES[yuan_idx], yuan_index=yuan_idx,
        futou="（茅山法不计符头）", futou_date="",
        reason=(
            f"交节{jq.name}于{jq.moment.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"本时刻距交节已过第 {elapsed + 1} 个时辰，"
            f"{'未满60时辰' if yuan_idx == 0 else ('满60未满120时辰' if yuan_idx == 1 else '已满120时辰')}"
            f" → {YUAN_NAMES[yuan_idx]}；查《{jq.name}{dun}》→ {ju}局。"
        ),
    )


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------

_DISPATCH = {"chaibu": ju_chaibu, "zhirun": ju_zhirun, "maoshan": ju_maoshan}


def determine_ju(dt: datetime, method: str = "chaibu") -> JuResult:
    """按指定起局法定局。

    Args:
        dt: 真太阳时（建议先做真太阳时换算再传入）。
        method: chaibu（拆补，默认）/ zhirun（置闰）/ maoshan（茅山）。
    """
    if method not in _DISPATCH:
        raise ValueError(f"不支持的起局法：{method}，可选 {list(_DISPATCH)}")
    return _DISPATCH[method](dt)


def compare_methods(dt: datetime) -> dict:
    """一次算出三法结果，供从业者对照——这是从业者工作台的高频需求。"""
    return {name: _DISPATCH[name](dt).as_dict() for name in _DISPATCH}
