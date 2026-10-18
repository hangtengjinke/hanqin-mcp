# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""八字神煞库（自实现，逐项可开关）。

为什么自己做
------------
`lunar_python` 不提供神煞，必须自实现。而神煞**恰恰是最容易和客户"打架"的地方** ——
几百种神煞，各派取用的集合不同、查法基准不同、同名神煞的表格也不同。

所以本文件遵循三条原则：
    1. **只做常用集**，不做全量。做得越多，与客户的传承冲突面越大。
    2. **每项独立可开关**，来自定义自己的取用集合。
    3. **表集中在顶部**，与逻辑分离 —— 客户说"你这个天乙贵人不对"，改一行即可。

已知的分歧项（默认取主流，可切换）
----------------------------------
· **天乙贵人**：主流口诀「甲戊**庚**牛羊」（庚见丑未）；
  另有「甲戊**兼**牛羊」（庚见午寅）。见 `TIANYI_VARIANT`。
· **羊刃**：主流只论阳干（甲卯/丙午/戊午/庚酉/壬子）；
  也有阴阳干都论的说法（乙寅/丁巳/己巳/辛申/癸亥）。见 `YANGREN_VARIANT`。
· **查法基准**：贵人、文昌一类以**日干**查；桃花、驿马一类以**年支或日支**查
  （三合局起）。本实现按主流标注，改动时注意基准别挪错。

一切以「可核对清单」定位交付 —— 不是唯一真理，请按自家传承调整本文件的表。
"""

from __future__ import annotations

from .bazi_tables import GAN_YINYANG, dishi

# ---------------------------------------------------------------------------
# 分歧开关
# ---------------------------------------------------------------------------

# "geng"  → 甲戊庚牛羊（主流）
# "jian"  → 甲戊兼牛羊（庚的贵人为午寅）
TIANYI_VARIANT = "geng"

# "yang_only" → 只论阳干（主流）
# "both"      → 阴阳干都论
YANGREN_VARIANT = "yang_only"


# ---------------------------------------------------------------------------
# 表（集中在顶部，便于替换）
# ---------------------------------------------------------------------------

# 天乙贵人（以日干查地支）
TIANYI_GENG = {
    "甲": "丑未", "戊": "丑未", "庚": "丑未",
    "乙": "子申", "己": "子申",
    "丙": "亥酉", "丁": "亥酉",
    "壬": "卯巳", "癸": "卯巳",
    "辛": "午寅",
}
TIANYI_JIAN = {
    "甲": "丑未", "戊": "丑未",
    "庚": "午寅", "辛": "午寅",
    "乙": "子申", "己": "子申",
    "丙": "亥酉", "丁": "亥酉",
    "壬": "卯巳", "癸": "卯巳",
}

# 文昌贵人（以日干查地支）
WENCHANG = {"甲": "巳", "乙": "午", "丙": "申", "戊": "申", "丁": "酉",
            "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯"}

# 国印贵人（以日干查地支）
GUOYIN = {"甲": "戌", "乙": "亥", "丙": "丑", "丁": "寅", "戊": "丑",
          "己": "寅", "庚": "辰", "辛": "巳", "壬": "未", "癸": "申"}

# 羊刃（以日干查地支）
YANGREN_YANG_ONLY = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}
YANGREN_BOTH = {"甲": "卯", "乙": "寅", "丙": "午", "丁": "巳", "戊": "午",
                "己": "巳", "庚": "酉", "辛": "申", "壬": "子", "癸": "亥"}

# 禄神：即十二长生的「临官」位，直接由 dishi() 判定

# 金舆（以日干查地支）
JINYU = {"甲": "辰", "乙": "巳", "丙": "未", "丁": "申", "戊": "未",
         "己": "申", "庚": "戌", "辛": "亥", "壬": "丑", "癸": "寅"}

# 红艳煞（以日干查地支）
HONGYAN = {"甲": "午", "乙": "午", "丙": "寅", "丁": "未", "戊": "辰",
           "己": "辰", "庚": "戌", "辛": "酉", "壬": "子", "癸": "申"}

# 天德贵人（以月支查天干或地支）
TIANDE = {"寅": "丁", "卯": "申", "辰": "壬", "巳": "辛", "午": "亥", "未": "甲",
          "申": "癸", "酉": "寅", "戌": "丙", "亥": "乙", "子": "巳", "丑": "庚"}

# 月德贵人（以月支三合局查天干）
YUEDE = {"寅午戌": "丙", "申子辰": "壬", "亥卯未": "甲", "巳酉丑": "庚"}


# 三合局归属（用于以年支/日支起的神煞）
SANHE_GROUP = {
    "申": "申子辰", "子": "申子辰", "辰": "申子辰",
    "寅": "寅午戌", "午": "寅午戌", "戌": "寅午戌",
    "巳": "巳酉丑", "酉": "巳酉丑", "丑": "巳酉丑",
    "亥": "亥卯未", "卯": "亥卯未", "未": "亥卯未",
}

# 以三合局查的神煞（值均为单个地支）
TAOHUA = {"申子辰": "酉", "寅午戌": "卯", "巳酉丑": "午", "亥卯未": "子"}
YIMA = {"申子辰": "寅", "寅午戌": "申", "巳酉丑": "亥", "亥卯未": "巳"}
HUAGAI = {"申子辰": "辰", "寅午戌": "戌", "巳酉丑": "丑", "亥卯未": "未"}
JIANGXING = {"申子辰": "子", "寅午戌": "午", "巳酉丑": "酉", "亥卯未": "卯"}
JIESHA = {"申子辰": "巳", "寅午戌": "亥", "巳酉丑": "寅", "亥卯未": "申"}
WANGSHEN = {"申子辰": "亥", "寅午戌": "巳", "巳酉丑": "申", "亥卯未": "寅"}


# 神煞元信息：名称 → (吉凶倾向, 查法基准, 说明)
META: dict[str, tuple[str, str, str]] = {
    "天乙贵人": ("吉", "日干", "最尊贵之吉星，主逢凶化吉、遇贵人扶助"),
    "天德贵人": ("吉", "月支", "主逢凶化吉、天赐之德"),
    "月德贵人": ("吉", "月支", "与天德并称，主慈祥恺悌、福泽绵长"),
    "文昌贵人": ("吉", "日干", "主聪慧好学、文书利达、科名有成"),
    "国印贵人": ("吉", "日干", "主掌权、司印信，利公职与名位"),
    "禄神": ("吉", "日干", "日干临官之地，主衣食丰足、身体康健"),
    "金舆": ("吉", "日干", "主车马之贵、娶得贤配"),
    "桃花": ("中性", "年支/日支", "又名咸池，主人缘、情缘、才艺；过旺则易生情困"),
    "驿马": ("中性", "年支/日支", "主迁动、出行、变更；主动则利、静则劳"),
    "华盖": ("中性", "年支/日支", "主孤高、艺文、玄学、宗教缘"),
    "将星": ("吉", "年支/日支", "三合局之中神，主统御、威望、居要位"),
    "羊刃": ("凶", "日干", "刚烈刑伤之星，主性烈、争斗、破耗；制化得宜亦有威权"),
    "红艳": ("中性", "日干", "主容貌出众、异性缘浓；过盛则易生是非"),
    "劫煞": ("凶", "年支/日支", "主劫夺、破耗、意外之失"),
    "亡神": ("凶", "年支/日支", "主耗散、忧虑、心性不稳"),
}

# 默认启用的集合（全部启用；调用方可传入子集来定制自己的取用）
DEFAULT_ENABLED: set[str] = set(META)


# ---------------------------------------------------------------------------
# 查找
# ---------------------------------------------------------------------------

def _hit(needles: str, branches: dict[str, str]) -> list[str]:
    """needles 是待查的地支字符串（如 "丑未"），branches 是 {柱位: 地支}。

    返回命中的柱位名称列表。
    """
    got = []
    for pos, zhi in branches.items():
        if zhi and zhi in needles:
            got.append(pos)
    return got


def shensha(pillars: dict[str, str],
            enabled: set[str] | None = None,
            tianyi_variant: str | None = None,
            yangren_variant: str | None = None) -> list[dict]:
    """求神煞。

    `pillars` 形如 {"year": "庚午", "month": "辛巳", "day": "乙酉", "hour": "庚辰"}。
    以日干查的用日干，以年支/日支查的用**年支与日支各查一次**（主流做法：两者皆可为基）。

    两个变体口径做成参数而不是靠改模块全局 —— 全局在 `python -m` 下会因为
    「模块被导入两次」（`__main__` 与包内模块是两个对象）而静默失效。
    调用方（含 API 层、测试）按客户传承显式传入即可。
    """
    on = DEFAULT_ENABLED if enabled is None else enabled
    tv = tianyi_variant or TIANYI_VARIANT
    yv = yangren_variant or YANGREN_VARIANT

    pos_names = {"year": "年支", "month": "月支", "day": "日支", "hour": "时支"}
    gan_names = {"year": "年干", "month": "月干", "day": "日干", "hour": "时干"}
    # 只取四个柱位 —— 调用方传进来的 dict 可能还带 xun_shou / xun_kong 等派生字段，
    # 这里对额外键免疫，免得每次调用都要先裁剪一遍。
    pillars = {k: v for k, v in pillars.items() if k in pos_names and len(str(v)) == 2}
    branches = {pos_names[k]: v[1] for k, v in pillars.items()}
    gans = {gan_names[k]: v[0] for k, v in pillars.items()}

    day_gan = pillars["day"][0] if len(pillars.get("day", "")) == 2 else ""
    year_zhi = pillars.get("year", "")[1:2]
    day_zhi = pillars.get("day", "")[1:2]
    month_zhi = pillars.get("month", "")[1:2]

    out: list[dict] = []

    def add(name: str, hits: list[str], extra: str = "") -> None:
        if name not in on or not hits:
            return
        level, basis, desc = META.get(name, ("中性", "", ""))
        out.append({
            "name": name, "level": level, "basis": basis,
            "hit_at": hits, "detail": desc + (f"（{extra}）" if extra else ""),
        })

    # ---- 以日干查 ----
    tianyi_table = TIANYI_GENG if tv == "geng" else TIANYI_JIAN
    if day_gan in tianyi_table:
        add("天乙贵人", _hit(tianyi_table[day_gan], branches),
            f"{day_gan}日见{tianyi_table[day_gan]}")
    if day_gan in WENCHANG:
        add("文昌贵人", _hit(WENCHANG[day_gan], branches), f"{day_gan}日见{WENCHANG[day_gan]}")
    if day_gan in GUOYIN:
        add("国印贵人", _hit(GUOYIN[day_gan], branches), f"{day_gan}日见{GUOYIN[day_gan]}")
    if day_gan in JINYU:
        add("金舆", _hit(JINYU[day_gan], branches), f"{day_gan}日见{JINYU[day_gan]}")
    if day_gan in HONGYAN:
        add("红艳", _hit(HONGYAN[day_gan], branches), f"{day_gan}日见{HONGYAN[day_gan]}")

    yangren_table = YANGREN_YANG_ONLY if yv == "yang_only" else YANGREN_BOTH
    if day_gan in yangren_table:
        add("羊刃", _hit(yangren_table[day_gan], branches), f"{day_gan}日见{yangren_table[day_gan]}")

    # 禄神 = 日干在四支的十二长生为「临官」
    ru_hits = [pos for pos, zhi in branches.items() if dishi(day_gan, zhi) == "临官"]
    add("禄神", ru_hits, f"{day_gan}之临官位")

    # ---- 以月支查 ----
    if month_zhi:
        td = TIANDE.get(month_zhi, "")
        if td:
            # 天德可能落在天干上，也可能落在地支上（如「卯月见申」「酉月见寅」）
            hits = [p for p, g in gans.items() if g == td] or _hit(td, branches)
            add("天德贵人", hits, f"{month_zhi}月见{td}")
        group = SANHE_GROUP.get(month_zhi, "")
        yd = YUEDE.get(group, "")
        if yd:
            add("月德贵人", [p for p, g in gans.items() if g == yd], f"{month_zhi}月见{yd}")

    # ---- 以年支 / 日支（三合局）查 ----
    for label, base_zhi in (("年支", year_zhi), ("日支", day_zhi)):
        group = SANHE_GROUP.get(base_zhi, "")
        if not group:
            continue
        add("桃花", _hit(TAOHUA.get(group, ""), branches), f"{label}{base_zhi}起")
        add("驿马", _hit(YIMA.get(group, ""), branches), f"{label}{base_zhi}起")
        add("华盖", _hit(HUAGAI.get(group, ""), branches), f"{label}{base_zhi}起")
        add("将星", _hit(JIANGXING.get(group, ""), branches), f"{label}{base_zhi}起")
        add("劫煞", _hit(JIESHA.get(group, ""), branches), f"{label}{base_zhi}起")
        add("亡神", _hit(WANGSHEN.get(group, ""), branches), f"{label}{base_zhi}起")

    # 去重：同名神煞从年支与日支可能各命中一次，合并命中的柱位
    merged: dict[str, dict] = {}
    for item in out:
        key = item["name"]
        if key in merged:
            for h in item["hit_at"]:
                if h not in merged[key]["hit_at"]:
                    merged[key]["hit_at"].append(h)
        else:
            merged[key] = item
    return list(merged.values())


def summarize(items: list[dict]) -> dict:
    """按吉凶倾向汇总，供解读层做口径锚点。"""
    tally = {"吉": 0, "凶": 0, "中性": 0}
    for it in items:
        tally[it.get("level", "中性")] = tally.get(it.get("level", "中性"), 0) + 1
    return tally


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    # 1990-05-20 08:30 男 → 庚午 辛巳 乙酉 庚辰
    p = {"year": "庚午", "month": "辛巳", "day": "乙酉", "hour": "庚辰"}
    items = shensha(p)
    print("═" * 60)
    print("神煞（庚午 辛巳 乙酉 庚辰）")
    print("═" * 60)
    for it in items:
        print(f"  [{it['level']}] {it['name']:6} 命于 {'、'.join(it['hit_at']):12} "
              f"（{it['basis']}）")
        print(f"          {it['detail']}")
    print()
    print("汇总：", summarize(items))

    print()
    print("═" * 60)
    print("开关效果：只启用「天乙贵人 / 桃花 / 驿马」")
    print("═" * 60)
    for it in shensha(p, enabled={"天乙贵人", "桃花", "驿马"}):
        print(f"  [{it['level']}] {it['name']} → {it['hit_at']}")

    print()
    print("═" * 60)
    print("天乙贵人两种口诀的差异（庚午 庚辰 庚申 丙子）")
    print("═" * 60)
    p2 = {"year": "庚午", "month": "庚辰", "day": "庚申", "hour": "丙子"}
    for variant, label in (("geng", "甲戊庚牛羊（主流）"), ("jian", "甲戊兼牛羊")):
        hit = [it for it in shensha(p2, tianyi_variant=variant) if it["name"] == "天乙贵人"]
        print(f"  {label}: {('命于 ' + '、'.join(hit[0]['hit_at'])) if hit else '未命中'}")
