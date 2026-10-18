# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""八字排盘引擎（四柱 + 十神 + 大运流年 + 事实清单）。

铁律：确定性计算，绝不由大模型推算。
月柱/日柱/时柱/大运全部由此层精确算出，大模型只允许在算好的盘面之上组织语言。

三层拼装，各司其职
------------------
    civil_time.to_standard()         客户报的出生信息 → 公历日期 + 标准北京时间
    calendar_util.four_pillars()     标准时间（经真太阳时修正）→ 四柱（时柱自算）
    bazi_tables.*                    干支关系表 → 十神 / 藏干 / 纳音 / 地势 / 旬空
    本模块                            编排 + 大运流年 + 事实清单

两个已被验证的坑（改动时别踩回去）
----------------------------------
1. **时柱不能用历法库的输出。** `lunar_python` 的 `sect=2`（库默认）在晚子时给出
   「日柱用当日、时柱按次日日干起」的不一致组合。`four_pillars()` 已用五鼠遁自算绕开，
   本模块的十神/旬空等派生信息也必须基于**那份自算的四柱**，不能混用两套结果。

2. **早晚子时默认与奇门保持一致（归次日）。** 否则同一个客户在奇门与八字两个模块
   会得到不同的日柱 —— 这在从业者眼里就是"你这个软件不准"。

一期只给事实、不下结论
----------------------
旺衰、格局取用、用神选取的分歧最大（见口径清单 C4），一期只输出**可核对的事实**：
十神、藏干、十二长生、旬空、五行力量统计、月令得气情况。
判断权留给从业者 —— 这也符合产品定位（工具不替代专业判断）。
"""

from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import bazi_shensha as SS
from . import bazi_tables as T
from .calendar_util import Pillars, four_pillars, mean_to_true_solar
from .constants import GAN, JIAZI_INDEX, ZHI

_POS_NAME = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
_POS_ORDER = ("year", "month", "day", "hour")


@dataclass
class BaziOptions:
    """排盘选项。默认值即口径清单里确认过的默认。"""
    gender: int = 1                      # 1 男 / 0 女
    zishi_sect: str = "next"             # next 晚子时归次日（与奇门一致）/ same 不换日
    use_true_solar_time: bool = True
    use_eot: bool = True
    longitude: float | None = None
    dayun_count: int = 10
    wuxing_weighted: bool = True         # 五行统计是否含藏干加权
    include_shensha: bool = True
    shensha_enabled: set[str] | None = None   # None = 用默认全量集合
    tianyi_variant: str | None = None          # geng（甲戊庚牛羊）/ jian（甲戊兼牛羊）
    yangren_variant: str | None = None         # yang_only / both


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _days_in_month(y: int, m: int) -> int:
    return _cal.monthrange(y, m)[1]


def _add_ymd(dt: datetime, years: int, months: int, days: int) -> datetime:
    """日期加「X 年 Y 月 Z 天」。用于由起运时长推算交运日期。"""
    y = dt.year + years
    m = dt.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    d = min(dt.day, _days_in_month(y, m))
    return datetime(y, m, d, dt.hour, dt.minute) + timedelta(days=days)


def _split(gz: str) -> tuple[str, str]:
    return (gz[0], gz[1]) if len(gz) == 2 else ("", "")


# ---------------------------------------------------------------------------
# 单柱派生信息
# ---------------------------------------------------------------------------

def _pillar_info(pos: str, gz: str, day_gan: str) -> dict:
    """一柱的全部派生信息：十神、藏干（含藏干十神）、纳音、地势、旬空。"""
    g, z = _split(gz)
    if not g:
        return {}

    hide = []
    for item in T.canggan(z):
        hide.append({
            "gan": item["gan"],
            "role": item["role"],
            "weight": item["weight"],
            "wuxing": T.GAN_WUXING[item["gan"]],
            "shishen": T.shishen(day_gan, item["gan"]),
        })

    return {
        "pos": pos,
        "pos_name": _POS_NAME[pos],
        "ganzhi": gz,
        "gan": g,
        "zhi": z,
        "gan_wuxing": T.GAN_WUXING.get(g, ""),
        "zhi_wuxing": T.ZHI_WUXING.get(z, ""),
        "gan_yinyang": T.GAN_YINYANG.get(g, ""),
        # 日柱天干即日主本身 —— 「日主」是柱位标注，不是十神，
        # 所以只在这一格特殊处理；其余位置（含大运/流年/藏干）一律走 shishen()。
        "shishen": "日主" if pos == "day" else T.shishen(day_gan, g),
        "canggan": hide,
        "nayin": T.nayin(gz),
        "dishi": T.dishi(day_gan, z),      # 地势以日干为主（八字惯例）
        "xun_shou": T.xun_shou(gz),
        "xun_kong": T.xun_kong(gz),
    }


# ---------------------------------------------------------------------------
# 大运与流年
# ---------------------------------------------------------------------------

def _liunian(dayun, day_gan: str, birth_year: int, now_year: int) -> list[dict]:
    """一步大运下的十年流年。取不到时返回空表，绝不影响主流程。"""
    try:
        return [{
            "year": n.getYear(),
            "age_virtual": n.getAge(),
            "age_real": n.getYear() - birth_year,
            "ganzhi": n.getGanZhi(),
            "shishen": T.shishen(day_gan, n.getGanZhi()[0]) if n.getGanZhi() else "",
            "is_now": n.getYear() == now_year,
        } for n in dayun.getLiuNian()]
    except Exception:  # noqa: BLE001
        return []


def _dayun(birth_dt: datetime, birth_year: int, pillars: dict, opts: BaziOptions) -> dict:
    """大运与流年。

    起运规则（已手算验证）：顺排算到下一个「节」、逆排算到上一个「节」；
    **3 天 = 1 年，1 天 = 4 个月，1 时辰 = 10 天**。
    顺逆：阳年男 / 阴年女 顺排，阴年男 / 阳年女 逆排（以**年干**阴阳定）。

    年龄给两套：虚岁（传统口径）+ 周岁（按年份差），避免客户对不上年龄。
    """
    out: dict = {"items": [], "start": {}, "current": None, "warnings": []}
    try:
        from lunar_python import Solar
        ec = Solar.fromYmdHms(birth_dt.year, birth_dt.month, birth_dt.day,
                              birth_dt.hour, birth_dt.minute, 0).getLunar().getEightChar()
        yun = ec.getYun(opts.gender)
    except Exception as exc:  # noqa: BLE001
        out["warnings"].append(f"大运计算失败：{type(exc).__name__}: {exc}")
        return out

    forward = bool(yun.isForward())
    sy, sm, sd = yun.getStartYear(), yun.getStartMonth(), yun.getStartDay()
    jiao = _add_ymd(birth_dt, sy, sm, sd)

    out["start"] = {
        "forward": forward,
        "direction": "顺排" if forward else "逆排",
        "years": sy, "months": sm, "days": sd,
        "text": f"{sy} 年 {sm} 个月 {sd} 天",
        "jiao_date": jiao.strftime("%Y-%m-%d"),
        "rule": ("阳年男/阴年女顺排" if forward else "阴年男/阳年女逆排") + " · 三天折一年",
    }

    day_gan = pillars["day"][0]
    now_year = datetime.now().year

    for i, d in enumerate(yun.getDaYun()[: max(1, opts.dayun_count)]):
        gz = d.getGanZhi() or ""
        start_year = d.getStartYear()
        item = {
            "index": i,
            "ganzhi": gz,
            "start_year": start_year,
            "end_year": d.getEndYear(),
            "age_virtual": d.getStartAge(),                       # 虚岁（传统）
            "age_real": start_year - birth_year,                  # 周岁（按年份差）
            "xun_kong": d.getXunKong() or "",
            "shishen": T.shishen(day_gan, gz[0]) if gz else "",
            "is_before_start": i == 0,                            # 步 0 是「起运前」占位
            "note": "起运前" if i == 0 else "",
        }
        if not item["is_before_start"] and gz:
            item["canggan"] = [{"gan": c["gan"], "role": c["role"],
                                "shishen": T.shishen(day_gan, c["gan"])}
                               for c in T.canggan(gz[1])]

        # 每一步都带上自己的十年流年 —— 界面要能点开任意一步看流年，
        # 只给「当前大运」会让时间轴变成只能看不能用的半成品。
        # 步 0 是「起运前」占位、没有大运干支，其流年不归大运所辖，故留空。
        item["liunian"] = [] if item["is_before_start"] else _liunian(d, day_gan, birth_year, now_year)
        out["items"].append(item)

        # 当前年份落在这一步 → 记为当前大运
        if (not item["is_before_start"]) and start_year <= now_year <= d.getEndYear():
            out["current"] = {
                "dayun_index": i,
                "dayun_ganzhi": gz,
                "year": now_year,
                "liunian": item["liunian"],
            }

    return out


# ---------------------------------------------------------------------------
# 事实清单（喂给解读层与从业者）
# ---------------------------------------------------------------------------

def _facts(pillars_detail: dict, day_gan: str, wuxing: dict,
           month_info: dict, dayun: dict) -> list[str]:
    """把盘面浓缩成可核对的事实条目。

    这是解读层唯一的输入来源 —— 大模型不允许自行推算任何一项。
    """
    f: list[str] = []

    f.append("四柱：" + "　".join(
        f"{_POS_NAME[p]}{pillars_detail[p]['ganzhi']}"
        f"（{pillars_detail[p]['gan_wuxing']}{pillars_detail[p]['gan_yinyang']}）"
        for p in _POS_ORDER if p in pillars_detail))

    f.append(f"日主：{day_gan}（{T.GAN_WUXING[day_gan]}{T.GAN_YINYANG[day_gan]}）")

    mz = month_info.get("zhi", "")
    if mz:
        ben = T.canggan(mz)
        f.append(f"月令：{mz}（{T.ZHI_WUXING.get(mz, '')}），本气藏干 "
                 f"{ben[0]['gan']}（{T.shishen(day_gan, ben[0]['gan'])}）"
                 + (f"，中气 {ben[1]['gan']}（{T.shishen(day_gan, ben[1]['gan'])}）"
                    if len(ben) > 1 else ""))

    f.append("五行力量：" + "　".join(
        f"{w} {wuxing['score'][w]}" for w in T.WUXING_ORDER)
        + f"（合计 {wuxing['total']}）")
    f.append("五行占比：" + "　".join(
        f"{w} {wuxing['percent'][w]}%" for w in T.WUXING_ORDER))

    tian_gan = [pillars_detail[p]["shishen"] for p in _POS_ORDER
                if p in pillars_detail and p != "day"]
    if tian_gan:
        f.append("天干十神：" + "　".join(tian_gan))

    zhi_shen = []
    for p in _POS_ORDER:
        if p not in pillars_detail:
            continue
        for c in pillars_detail[p]["canggan"]:
            zhi_shen.append(f"{pillars_detail[p]['zhi']}藏{c['gan']}={c['shishen']}")
    f.append("地支藏干十神：" + "　".join(zhi_shen))

    f.append("十二长生（以日干论四支）：" + "　".join(
        f"{pillars_detail[p]['zhi']}={pillars_detail[p]['dishi']}"
        for p in _POS_ORDER if p in pillars_detail))

    f.append("旬空：" + "　".join(
        f"{_POS_NAME[p]}{pillars_detail[p]['xun_kong']}"
        for p in _POS_ORDER if p in pillars_detail))

    st = dayun.get("start") or {}
    if st:
        f.append(f"大运：{st['direction']}（{st['rule']}），"
                 f"出生后 {st['text']} 起运，交运日 {st['jiao_date']}")

    cur = dayun.get("current")
    if cur:
        ln = next((x for x in cur["liunian"] if x["is_now"]), None)
        if ln:
            f.append(f"当前流年：{ln['year']} 年 {ln['ganzhi']}"
                     f"（十神 {ln['shishen']}），行 {cur['dayun_ganzhi']} 大运")

    return f


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def pai(standard_dt: datetime, opts: BaziOptions | None = None) -> dict:
    """由「标准北京时间」排出完整八字盘。

    `standard_dt` 应当是已经过 `civil_time.to_standard()` 处理的公历标准时间 ——
    纪年、历法、夏令时、历史时区的换算都在那一层完成。
    """
    opts = opts or BaziOptions()

    warnings: list[str] = []
    notes: list[str] = []

    # ---- 真太阳时（与奇门同一套算法）----
    dt = standard_dt
    if opts.use_true_solar_time:
        if opts.longitude is None:
            warnings.append("未提供出生地经度，已跳过真太阳时修正 —— 时辰可能因经度差异而偏差。")
        else:
            dt = mean_to_true_solar(standard_dt, opts.longitude, use_eot=opts.use_eot)
            notes.append(f"真太阳时 {dt:%H:%M}（经度 {opts.longitude}°"
                         + ("，含均时差" if opts.use_eot else "，未含均时差") + "）")

    # ---- 四柱（时柱自算，避开历法库的晚子时口径问题）----
    pl: Pillars = four_pillars(dt, zishi_sect=opts.zishi_sect)
    p = pl.as_dict()
    pillars_detail = {pos: _pillar_info(pos, p[pos], p["day"][0]) for pos in _POS_ORDER}
    day_gan = p["day"][0]

    # ---- 五行统计 ----
    wuxing = T.wuxing_count(p, include_cangan=opts.wuxing_weighted)

    # ---- 胎元 / 命宫 / 身宫 ----
    extra = {
        "taiyuan": T.taiyuan(p["month"]),
        "minggong": T.minggong(p["month"][1], p["hour"][1]),
        "shengong": T.shengong(p["month"][1], p["hour"][1]),
    }

    # ---- 大运流年 ----
    dayun = _dayun(dt, dt.year, p, opts)

    # ---- 神煞 ----
    sha: list[dict] = []
    if opts.include_shensha:
        sha = SS.shensha(p, enabled=opts.shensha_enabled,
                         tianyi_variant=opts.tianyi_variant,
                         yangren_variant=opts.yangren_variant)

    facts = _facts(pillars_detail, day_gan, wuxing, pillars_detail["month"], dayun)

    if sha:
        facts.append("神煞：" + "　".join(
            f"{s['name']}({s['level']}·{'、'.join(s['hit_at'])})" for s in sha))

    return {
        "pillars": p,
        "pillars_detail": pillars_detail,
        "day_master": day_gan,
        "day_master_wuxing": T.GAN_WUXING[day_gan],
        "wuxing": wuxing,
        "extra": extra,
        "dayun": dayun,
        "shensha": sha,
        "shensha_summary": SS.summarize(sha) if sha else {},
        "facts": facts,
        "options": {
            "gender": opts.gender,
            "gender_text": "男" if opts.gender else "女",
            "zishi_sect": opts.zishi_sect,
            "use_true_solar_time": opts.use_true_solar_time,
            "longitude": opts.longitude,
        },
        "used_datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "warnings": warnings + dayun.get("warnings", []),
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    cases = [
        ("1990-05-20 08:30 男（上海）",
         datetime(1990, 5, 20, 8, 30), BaziOptions(gender=1, longitude=121.47)),
        ("1990-05-20 08:30 女",
         datetime(1990, 5, 20, 8, 30), BaziOptions(gender=0, longitude=121.47)),
        ("1990-05-20 23:30 男（晚子时）",
         datetime(1990, 5, 20, 23, 30), BaziOptions(gender=1, longitude=121.47)),
        ("1990-05-20 23:30 男（晚子时不换日）",
         datetime(1990, 5, 20, 23, 30),
         BaziOptions(gender=1, longitude=121.47, zishi_sect="same")),
    ]

    for title, dt, op in cases:
        r = pai(dt, op)
        print("═" * 64)
        print(f"【{title}】")
        print("═" * 64)
        p = r["pillars"]
        print(f"  四柱：{p['year']}　{p['month']}　{p['day']}　{p['hour']}"
              f"　（日主 {r['day_master']}{r['day_master_wuxing']}）")
        print(f"  十神：" + "　".join(
            f"{r['pillars_detail'][k]['pos_name']}{r['pillars_detail'][k]['shishen']}"
            for k in _POS_ORDER))
        print(f"  纳音：" + "　".join(
            r["pillars_detail"][k]["nayin"] for k in _POS_ORDER))
        print(f"  地势：" + "　".join(
            r["pillars_detail"][k]["dishi"] for k in _POS_ORDER))
        print(f"  胎元 {r['extra']['taiyuan']}　命宫 {r['extra']['minggong']}"
              f"　身宫 {r['extra']['shengong']}")
        wy = r["wuxing"]
        print(f"  五行：{wy['score']}　占比 {wy['percent']}")
        st = r["dayun"]["start"]
        print(f"  大运：{st['direction']}　起运 {st['text']}　交运 {st['jiao_date']}")
        for it in r["dayun"]["items"][1:4]:
            print(f"    {it['start_year']}–{it['end_year']}　"
                  f"虚{it['age_virtual']:>2}岁/周{it['age_real']:>2}岁　"
                  f"{it['ganzhi']}　{it['shishen']}　空{it['xun_kong']}")
        cur = r["dayun"].get("current")
        if cur:
            now = next((x for x in cur["liunian"] if x["is_now"]), None)
            if now:
                print(f"  当前：{now['year']} 年 {now['ganzhi']}（{now['shishen']}）"
                      f"，行 {cur['dayun_ganzhi']} 大运")
        print()
        print("  ── 事实清单 ──")
        for line in r["facts"]:
            print(f"    · {line}")
        for w in r["warnings"]:
            print(f"    ⚠ {w}")
        print()
