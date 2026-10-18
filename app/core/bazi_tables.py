# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""八字干支关系表（十神 / 藏干 / 纳音 / 十二长生 / 旬空 / 胎元）。

为什么单独一张表文件
--------------------
这些关系**各派略有差异** —— 藏干的中气余气、纳音字形、十二长生的顺逆、
胎元取法，各家表述不完全相同。集中在一处才好替换与核对；
散进逻辑里，将来客户说"你这个藏干跟我用的不一样"就找不到地方改。

这也符合本项目的既有原则：确定性规则必须**精确命中、逐条可审计**，
不能藏在算法内部。

为什么不用历法库的十神
----------------------
`lunar_python` 能算十神，但它的十神基于**它自己排的日柱与时柱**。
而它的 `sect=2`（库默认）在晚子时会给出「日柱用当日、时柱按次日日干起」的
不一致组合 —— 我们在 `calendar_util.four_pillars()` 里已经自算时柱避开了这个坑，
所以派生信息也必须基于**我们自己的四柱**推导，不能混用两套结果。

这里的表都是主流口径；如需替换门派，改本文件顶部即可。
"""

from __future__ import annotations

from .constants import GAN, JIAZI_INDEX, ZHI

# ---------------------------------------------------------------------------
# 五行与阴阳
# ---------------------------------------------------------------------------

GAN_WUXING: dict[str, str] = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}

GAN_YINYANG: dict[str, str] = {
    "甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳",
    "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴",
}

ZHI_WUXING: dict[str, str] = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 五行相生：木→火→土→金→水→木
WUXING_SHENG: dict[str, str] = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
# 五行相克：木克土、土克水、水克火、火克金、金克木
WUXING_KE: dict[str, str] = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

WUXING_ORDER = ("木", "火", "土", "金", "水")


# ---------------------------------------------------------------------------
# 十神
# ---------------------------------------------------------------------------
#
# 以日干为「我」，与另一个天干比较生克与阴阳：
#   同我 → 比肩（同阴阳）/ 劫财（异阴阳）
#   我生 → 食神（同）    / 伤官（异）
#   我克 → 偏财（同）    / 正财（异）
#   克我 → 七杀（同）    / 正官（异）
#   生我 → 偏印（同）    / 正印（异）

_SHISHEN_LABEL = {
    ("同我", True): "比肩", ("同我", False): "劫财",
    ("我生", True): "食神", ("我生", False): "伤官",
    ("我克", True): "偏财", ("我克", False): "正财",
    ("克我", True): "七杀", ("克我", False): "正官",
    ("生我", True): "偏印", ("生我", False): "正印",
}


def shishen(day_gan: str, other_gan: str) -> str:
    """以日干为「我」，求 other_gan 的十神。

    **同干论「比肩」**（同五行、同阴阳），不返回「日主」。
    十神是两个天干之间的关系，日主自身不是十神 ——
    「日主」只是**日柱那一格的柱位标注**，由 `bazi._pillars_detail` 单独写。
    早期版本在这里返回「日主」，导致大运、流年、藏干里凡与日主同干者
    全被标成「日主」（如乙日主见乙酉大运），是错的。
    """
    me, it = GAN_WUXING[day_gan], GAN_WUXING[other_gan]
    same = GAN_YINYANG[day_gan] == GAN_YINYANG[other_gan]

    if it == me:
        key = "同我"
    elif WUXING_SHENG[me] == it:
        key = "我生"
    elif WUXING_KE[me] == it:
        key = "我克"
    elif WUXING_KE[it] == me:
        key = "克我"
    elif WUXING_SHENG[it] == me:
        key = "生我"
    else:                                   # 理论上不可达
        return ""
    return _SHISHEN_LABEL[(key, same)]


# ---------------------------------------------------------------------------
# 藏干
# ---------------------------------------------------------------------------
#
# 顺序即本气 / 中气 / 余气。这份表是主流口径；
# 分歧点多在「午藏丁己」是否含己、「亥藏壬甲」的排序，替换时改这里。

ZHI_CANGAN: dict[str, list[str]] = {
    "子": ["癸"],
    "丑": ["己", "癸", "辛"],
    "寅": ["甲", "丙", "戊"],
    "卯": ["乙"],
    "辰": ["戊", "乙", "癸"],
    "巳": ["丙", "庚", "戊"],
    "午": ["丁", "己"],
    "未": ["己", "丁", "乙"],
    "申": ["庚", "壬", "戊"],
    "酉": ["辛"],
    "戌": ["戊", "辛", "丁"],
    "亥": ["壬", "甲"],
}

CANGAN_WEIGHT = {"本气": 1.0, "中气": 0.5, "余气": 0.3}


def canggan(zhi: str) -> list[dict]:
    """地支藏干，标注本气/中气/余气。"""
    names = ["本气", "中气", "余气"]
    return [{"gan": g, "role": names[i] if i < len(names) else "余气",
             "weight": CANGAN_WEIGHT.get(names[i] if i < len(names) else "余气", 0.3)}
            for i, g in enumerate(ZHI_CANGAN.get(zhi, []))]


# ---------------------------------------------------------------------------
# 纳音（六十甲子，每两个干支共用一个）
# ---------------------------------------------------------------------------

NAYIN: dict[str, str] = {
    "甲子": "海中金", "乙丑": "海中金", "丙寅": "炉中火", "丁卯": "炉中火",
    "戊辰": "大林木", "己巳": "大林木", "庚午": "路旁土", "辛未": "路旁土",
    "壬申": "剑锋金", "癸酉": "剑锋金", "甲戌": "山头火", "乙亥": "山头火",
    "丙子": "涧下水", "丁丑": "涧下水", "戊寅": "城头土", "己卯": "城头土",
    "庚辰": "白蜡金", "辛巳": "白蜡金", "壬午": "杨柳木", "癸未": "杨柳木",
    "甲申": "泉中水", "乙酉": "泉中水", "丙戌": "屋上土", "丁亥": "屋上土",
    "戊子": "霹雳火", "己丑": "霹雳火", "庚寅": "松柏木", "辛卯": "松柏木",
    "壬辰": "长流水", "癸巳": "长流水", "甲午": "砂中金", "乙未": "砂中金",
    "丙申": "山下火", "丁酉": "山下火", "戊戌": "平地木", "己亥": "平地木",
    "庚子": "壁上土", "辛丑": "壁上土", "壬寅": "金箔金", "癸卯": "金箔金",
    "甲辰": "覆灯火", "乙巳": "覆灯火", "丙午": "天河水", "丁未": "天河水",
    "戊申": "大驿土", "己酉": "大驿土", "庚戌": "钗钏金", "辛亥": "钗钏金",
    "壬子": "桑柘木", "癸丑": "桑柘木", "甲寅": "大溪水", "乙卯": "大溪水",
    "丙辰": "沙中土", "丁巳": "沙中土", "戊午": "天上火", "己未": "天上火",
    "庚申": "石榴木", "辛酉": "石榴木", "壬戌": "大海水", "癸亥": "大海水",
}


def nayin(ganzhi: str) -> str:
    return NAYIN.get(ganzhi, "")


# ---------------------------------------------------------------------------
# 十二长生（地势）
# ---------------------------------------------------------------------------
#
# 阳干顺行、阴干逆行。长生位：甲亥、乙午、丙戊寅、丁己酉、庚巳、辛子、壬申、癸卯。

_SHENG_12 = ("长生", "沐浴", "冠带", "临官", "帝旺", "衰",
             "病", "死", "墓", "绝", "胎", "养")

_CHANGSHENG_POS: dict[str, str] = {
    "甲": "亥", "乙": "午", "丙": "寅", "丁": "酉", "戊": "寅",
    "己": "酉", "庚": "巳", "辛": "子", "壬": "申", "癸": "卯",
}


def dishi(gan: str, zhi: str) -> str:
    """求天干在某地支的十二长生状态。"""
    if gan not in _CHANGSHENG_POS or zhi not in ZHI:
        return ""
    start = ZHI.index(_CHANGSHENG_POS[gan])
    cur = ZHI.index(zhi)
    step = (cur - start) % 12 if GAN_YINYANG.get(gan) == "阳" else (start - cur) % 12
    return _SHENG_12[step]


# ---------------------------------------------------------------------------
# 旬空（空亡）
# ---------------------------------------------------------------------------

_XUN_TABLE: dict[str, str] = {}


def _build_xun() -> None:
    """预生成 60 甲子的旬空表（与 calendar_util 的口径一致）。"""
    for gz, idx in JIAZI_INDEX.items():
        head = (idx // 10) * 10
        _XUN_TABLE[gz] = ZHI[(head + 10) % 12] + ZHI[(head + 11) % 12]


_build_xun()


def xun_kong(ganzhi: str) -> str:
    """该柱所属旬的空亡两支。"""
    return _XUN_TABLE.get(ganzhi, "")


def xun_shou(ganzhi: str) -> str:
    """该柱所属旬的旬首（甲子 / 甲戌 / …）。"""
    idx = JIAZI_INDEX.get(ganzhi)
    if idx is None:
        return ""
    head = (idx // 10) * 10
    return next((gz for gz, i in JIAZI_INDEX.items() if i == head), "")


# ---------------------------------------------------------------------------
# 胎元（月柱天干进一位、地支进三位）
# ---------------------------------------------------------------------------

def taiyuan(month_gz: str) -> str:
    """胎元。主流取法：月干进一、月支进三。"""
    if len(month_gz) != 2:
        return ""
    g = GAN[(GAN.index(month_gz[0]) + 1) % 10]
    z = ZHI[(ZHI.index(month_gz[1]) + 3) % 12]
    return g + z


# ---------------------------------------------------------------------------
# 命宫 / 身宫
# ---------------------------------------------------------------------------
#
# 这两者的算法**流派分歧较大**，此处给出主流取法（以节气月支序 + 时辰序推算），
# 并保留 `minggong_alt` 供替换。若与贵派传承不符，改这里即可。
#
# 时支在晚子时永远是「子」，与日柱流派无关 —— 所以命宫不受早晚子时口径影响。

def minggong(month_zhi: str, hour_zhi: str) -> str:
    """命宫地支。

    取法：以月支序（寅=1）与时辰序（子=1）相加，
    小于等于 14 则用 14 减，大于 14 则用 26 减，所得数对应地支序（寅=1 起算）。
    """
    if month_zhi not in ZHI or hour_zhi not in ZHI:
        return ""
    m = (ZHI.index(month_zhi) - ZHI.index("寅")) % 12 + 1     # 寅月 = 1
    h = ZHI.index(hour_zhi) + 1                                # 子时 = 1
    total = m + h
    n = 14 - total if total <= 14 else 26 - total
    zhi = ZHI[(ZHI.index("寅") + n - 1) % 12]
    return zhi


def shengong(month_zhi: str, hour_zhi: str) -> str:
    """身宫地支。主流取法：月支序 + 时辰序，超过 12 则减 12。"""
    if month_zhi not in ZHI or hour_zhi not in ZHI:
        return ""
    m = (ZHI.index(month_zhi) - ZHI.index("寅")) % 12 + 1
    h = ZHI.index(hour_zhi) + 1
    n = (m + h) % 12 or 12
    return ZHI[(ZHI.index("寅") + n - 1) % 12]


# ---------------------------------------------------------------------------
# 五行力量统计
# ---------------------------------------------------------------------------
#
# 用于「事实清单」—— A 类口径 C4 建议一期只给出可核对的事实，
# 不替从业者下旺衰结论。这里给两种口径，默认第二种（含藏干加权）。

def wuxing_count(pillars: dict[str, str], include_cangan: bool = True) -> dict:
    """统计五行力量。

    include_cangan=False → 只数四个天干 + 四个地支本气（各计 1）
    include_cangan=True  → 天干各 1，地支按本气 1.0 / 中气 0.5 / 余气 0.3 加权
    """
    score = {w: 0.0 for w in WUXING_ORDER}
    detail: list[dict] = []

    for pos in ("year", "month", "day", "hour"):
        gz = pillars.get(pos, "")
        if len(gz) != 2:
            continue
        g, z = gz[0], gz[1]
        score[GAN_WUXING[g]] += 1.0
        detail.append({"pos": pos, "gan": g, "wuxing": GAN_WUXING[g],
                       "weight": 1.0, "from": "天干"})

        if include_cangan:
            for item in canggan(z):
                score[GAN_WUXING[item["gan"]]] += item["weight"]
                detail.append({"pos": pos, "gan": item["gan"],
                               "wuxing": GAN_WUXING[item["gan"]],
                               "weight": item["weight"], "from": f"地支{item['role']}"})
        else:
            ben = ZHI_CANGAN.get(z, [])
            if ben:
                score[GAN_WUXING[ben[0]]] += 1.0
                detail.append({"pos": pos, "gan": ben[0],
                               "wuxing": GAN_WUXING[ben[0]],
                               "weight": 1.0, "from": "地支本气"})

    total = sum(score.values()) or 1.0
    return {
        "score": {k: round(v, 2) for k, v in score.items()},
        "percent": {k: round(v / total * 100, 1) for k, v in score.items()},
        "total": round(total, 2),
        "detail": detail,
    }
