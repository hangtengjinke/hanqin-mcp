# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""知识规则层 · 格局库。

本层是"确定性规则"，与大模型严格分离：格局的识别只由这里完成，
大模型只负责把识别结果组织成自然语言，不得自行"看出"新的格局。

格局判定口径以《烟波钓叟歌》体系为基准，覆盖：
    · 十干克应（天盘干 + 地盘干）：青龙返首、飞鸟跌穴、青龙逃走、白虎猖狂……
    · 三奇（乙丙丁）特殊组合：三奇得使、三奇升殿、玉女守门、三遁
    · 门与宫的五行生克：门迫、门制
    · 全局性：值符伏吟
    · 神煞类：五不遇时、六仪击刑、旬空、驿马
    · 值使门吉凶（断事第一看）

注：本库为"可核对清单"而非"唯一真理"。流派差异处（如三奇得使的配对、
三遁的附加条件）集中在本文件顶部，便于从业者按自家传承替换。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..core.constants import (
    DOOR_JIXIONG,
    DOOR_WUXING,
    GAN_WUXING,
    GONG_WUXING,
    JI_XING,
    STAR_TO_BENWEI,
    WUXING_KE,
    gong_for_ring,
)

LEVEL_ORDER = {"大吉": 0, "吉": 1, "中平": 2, "凶": 3, "大凶": 4}

# 十干序，用于把六仪还原为甲（戊→甲子、己→甲戌 ……）
YI_TO_JIA = {"戊": "甲子", "己": "甲戌", "庚": "甲申", "辛": "甲午", "壬": "甲辰", "癸": "甲寅"}

# 宫号 → 中文宫名（文案用）
JIXING_GONG_NAME = {1: "坎一", 2: "坤二", 3: "震三", 4: "巽四",
                    6: "乾六", 7: "兑七", 8: "艮八", 9: "离九", 5: "中五"}


@dataclass
class Pattern:
    name: str
    level: str          # 大吉 / 吉 / 中平 / 凶 / 大凶
    gong: int           # 所在宫；0 表示全局性
    detail: str
    advice: str

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 一、十干克应（天盘干 → 地盘干）
# ---------------------------------------------------------------------------

GAN_KE_YING: dict[tuple[str, str], tuple[str, str, str, str]] = {
    # ---- 大吉格 ----
    ("戊", "丙"): ("青龙返首", "大吉", "尊甲得明主，奇临仪位",
                   "谋事有成、贵人提携、启动大事皆宜。"),
    ("丙", "戊"): ("飞鸟跌穴", "大吉", "月奇归本，动而速成",
                   "机会突至，宜速取速办，迟疑则失。"),
    # ---- 凶格 ----
    ("乙", "辛"): ("青龙逃走", "凶", "乙木被辛金所伤，奇不得地",
                   "主离去、离职、离散、人财两空，忌签长约。"),
    ("辛", "乙"): ("白虎猖狂", "大凶", "辛金克乙木，白虎逞凶",
                   "主车祸、伤灾、斗殴、被劫，远行与大动大改最忌。"),
    ("丁", "癸"): ("朱雀投江", "凶", "丁火入癸水，朱雀坠江",
                   "主文书口舌、音信断绝、诉讼败诉，考试报批不利。"),
    ("癸", "丁"): ("螣蛇夭矫", "凶", "癸丁水火相激，蛇妖作祟",
                   "主虚惊怪异、纠缠反复、疑心暗鬼，宜静守待明。"),
    ("庚", "丙"): ("太白入荧", "凶", "太白犯荧惑，金入火乡",
                   "主盗贼入室、破财被算计，防盗防小人防泄密。"),
    ("丙", "庚"): ("荧入太白", "中平", "荧惑入太白，火克金而力尽",
                   "主耗散财去人离；幸得吉门吉星尚可转危。"),
    ("庚", "癸"): ("大格", "凶", "庚癸相冲，格而不通",
                   "主行人不至、谋事阻隔，出行与远程协作为大忌。"),
    ("庚", "壬"): ("小格（上格）", "凶", "金水相荡，消息失真",
                   "主远行迷失、音信不通，务必核实再动。"),
    ("庚", "己"): ("刑格", "大凶", "庚加甲戌，金土成刑",
                   "主刑罚官非、伤病缠身，切忌对抗规则。"),
    ("庚", "庚"): ("战格", "大凶", "两庚相并，金金相击",
                   "主正面对垒、硬碰硬、两败俱伤，宜避锋。"),
    ("庚", "戊"): ("伏宫格", "凶", "庚加甲子，动则受制",
                   "主困守难进，宜守不宜攻。"),
    ("戊", "庚"): ("飞宫格", "中平", "甲子加庚，金逼甲遁",
                   "主变动、离所、迁移；本意求动反为得机。"),
    ("乙", "庚"): ("日奇被刑", "凶", "乙木遇庚金，姐妹受制",
                   "主婚恋受挫、女性受伤、合作生变。"),
    ("庚", "乙"): ("日奇入太白", "凶", "庚金克乙木，谋泄于人",
                   "主谋划泄露、被人截胡、竞争失利。"),
    ("壬", "己"): ("九地藏形", "中平", "壬水入土，隐而不显",
                   "主暗藏不露，宜潜伏静守、不宜声张。"),
    ("癸", "己"): ("华盖地户", "中平", "癸水入土，闭塞不通",
                   "主闭塞难行，宜收敛守成。"),
    ("壬", "壬"): ("伏吟（水）", "中平", "壬加壬，天水重沓", "主静守、反复，宜复盘。"),
    ("癸", "癸"): ("伏吟（阴水）", "中平", "癸加癸，重阴叠水", "主暗昧、拖延，宜待明。"),
}

# ---------------------------------------------------------------------------
# 二、三奇特殊组合
# ---------------------------------------------------------------------------

# 三奇得使：奇加对应之甲（旬首之仪）
SANQI_DESHI: dict[str, tuple[str, ...]] = {
    "乙": ("己", "辛"),   # 乙奇得使于甲戌己、甲午辛
    "丙": ("戊", "庚"),   # 丙奇得使于甲子戊、甲申庚
    "丁": ("壬", "癸"),   # 丁奇得使于甲辰壬、甲寅癸
}
SANQI_QIMEN = {"乙": "日奇", "丙": "月奇", "丁": "星奇"}

# 三奇升殿：奇临本位之宫
SANQI_SHENGDIAN = {"乙": 3, "丙": 9, "丁": 7}
SANQI_SHENGDIAN_DESC = {
    "乙": ("三奇升殿·日奇", "主名位得正、文书顺达，利求名、考试、申报。"),
    "丙": ("三奇升殿·月奇", "主光明显达、名声在外，利宣传、公关、露脸。"),
    "丁": ("三奇升殿·星奇", "主文书音信得力，利谈判、签约、递材料。"),
}

# 三遁：门 + 天盘奇 + 附加条件
SANDUN = {
    "天遁": {"door": "生门", "qi": "丙", "dipan": "丁", "level": "大吉",
             "detail": "生门临丙奇并会地盘丁（六丁）",
             "advice": "得天之助、贵人垂青，宜求人、求财、上达。"},
    "地遁": {"door": "开门", "qi": "乙", "dipan": "己", "level": "大吉",
             "detail": "开门临乙奇并会地盘己（六己）",
             "advice": "得地之利、根基稳固，宜置业、动土、仓储。"},
    "人遁": {"door": "休门", "qi": "丁", "dipan": None, "god": "太阴", "level": "大吉",
             "detail": "休门临丁奇并会太阴",
             "advice": "得人和、有暗中助力，宜结盟、密谈、托人。"},
}


# ---------------------------------------------------------------------------
# 三、格局识别
# ---------------------------------------------------------------------------

def _ke_ying_pairs(pan) -> dict[int, tuple[str, str]]:
    """{宫: (天盘干, 地盘干)}。转盘的中五宫不参与十干克应（该宫无天盘）。"""
    out: dict[int, tuple[str, str]] = {}
    for p in pan.palaces:
        if not p.tianpan_gan or not p.dipan_gan:
            continue
        if p.gong == 5 and pan.pan_type == "zhuan":
            continue
        out[p.gong] = (p.tianpan_gan, p.dipan_gan)
    return out


def detect_patterns(pan) -> list[Pattern]:
    """识别全部格局，按吉凶等级排序返回。"""
    res: list[Pattern] = []
    pairs = _ke_ying_pairs(pan)
    hour_zhi = pan.pillars.get("hour", "")[1:2]

    # ---- 1. 十干克应 ----
    for gong, (tg, dg) in pairs.items():
        hit = GAN_KE_YING.get((tg, dg))
        if hit:
            name, level, detail, advice = hit
            res.append(Pattern(name, level, gong, f"天盘{tg} + 地盘{dg}（{detail}）", advice))

    # ---- 2. 三奇得使 ----
    for gong, (tg, dg) in pairs.items():
        if tg in SANQI_DESHI and dg in SANQI_DESHI[tg]:
            jia = YI_TO_JIA.get(dg, dg)
            res.append(Pattern(
                f"三奇得使·{SANQI_QIMEN[tg]}", "大吉", gong,
                f"天盘{tg}（{SANQI_QIMEN[tg]}）加地盘{dg}（{jia}）",
                "奇逢其使，所谋易成，主贵人应允、文书顺达，宜出手。"))

    # ---- 3. 三奇升殿 ----
    for p in pan.palaces:
        g = p.tianpan_gan
        if g in SANQI_SHENGDIAN and gong_for_ring(p.gong) == gong_for_ring(SANQI_SHENGDIAN[g]):
            nm, advice = SANQI_SHENGDIAN_DESC[g]
            res.append(Pattern(nm, "吉", p.gong,
                               f"天盘{g}临{gong_for_ring(p.gong)}宫本位", advice))

    # ---- 4. 玉女守门（天盘丁奇与值使门同宫）----
    for p in pan.palaces:
        if p.tianpan_gan == "丁" and p.is_zhishi and p.door:
            res.append(Pattern("玉女守门", "大吉", p.gong,
                               f"丁奇（玉女）与值使{p.door}同宫",
                               "主私密之事得成、暗中有人相助，婚姻托请谈判皆宜。"))

    # ---- 5. 三遁 ----
    for p in pan.palaces:
        if not p.door or not p.tianpan_gan:
            continue
        for nm, cfg in SANDUN.items():
            if p.door != cfg["door"] or p.tianpan_gan != cfg["qi"]:
                continue
            if cfg.get("dipan") is not None and p.dipan_gan != cfg["dipan"]:
                continue
            if cfg.get("god") is not None and p.god != cfg["god"]:
                continue
            res.append(Pattern(nm, cfg["level"], p.gong, cfg["detail"], cfg["advice"]))

    # ---- 6. 五不遇时（时干克日干且阴阳同性）----
    dg = pan.pillars.get("day", "")[:1]
    hg = pan.pillars.get("hour", "")[:1]
    if dg in GAN_WUXING and hg in GAN_WUXING:
        yang = set("甲丙戊庚壬")
        same = (dg in yang) == (hg in yang)
        if WUXING_KE.get(GAN_WUXING[hg]) == GAN_WUXING[dg] and same:
            res.append(Pattern("五不遇时", "大凶", 0,
                               f"时干{hg}克日干{dg}（同阴阳），时干克日",
                               "百事不宜，宜静守、勿启动新事，或另择时辰。"))

    # ---- 7. 六仪击刑 ----
    for p in pan.palaces:
        g = p.tianpan_gan
        if g in JI_XING and gong_for_ring(p.gong) == gong_for_ring(JI_XING[g]):
            jin_gong = JI_XING[g]
            res.append(Pattern("六仪击刑", "凶", p.gong,
                               f"天盘{g}（{YI_TO_JIA.get(g, g)}）落"
                               f"{JIXING_GONG_NAME.get(jin_gong, jin_gong)}本位，犯击刑",
                               "主内耗自伤、事倍功半，该宫所主之事减分，忌强推。"))

    # ---- 8. 门迫 / 门制 ----
    for p in pan.palaces:
        if not p.door or p.gong == 5:
            continue
        dw, gw = DOOR_WUXING.get(p.door), GONG_WUXING.get(p.gong)
        if not dw or not gw:
            continue
        if WUXING_KE.get(dw) == gw:
            res.append(Pattern("门迫", "凶", p.gong,
                               f"{p.door}（{dw}）克{p.gong_name}宫（{gw}）",
                               "门反压宫，主用事受阻、人事不协，宜暂缓。"))
        elif WUXING_KE.get(gw) == dw:
            res.append(Pattern("门制", "中平", p.gong,
                               f"{p.gong_name}宫（{gw}）克{p.door}（{dw}）",
                               "宫克门，事有牵制但可控，宜按流程稳步推进。"))

    # ---- 9. 伏吟（天盘干与本宫地盘干相同）----
    for gong, (tg, dg) in pairs.items():
        if tg == dg:
            res.append(Pattern(f"伏吟·{tg}", "中平", gong,
                               f"天盘{tg}加地盘{dg}同宫",
                               "主静守停滞、原地打转，宜守不宜进。"))

    # ---- 10. 旬空落宫 ----
    for p in pan.palaces:
        if p.kong_wang and p.gong != 5:
            res.append(Pattern("旬空", "中平", p.gong,
                               f"{p.gong_name}宫落时旬空亡（{pan.xun_kong}）",
                               "空则力弱：吉不实、凶减半，主事多虚而多变。"))

    # ---- 11. 驿马 ----
    ma = next((p for p in pan.palaces if p.yi_ma), None)
    if ma is not None:
        res.append(Pattern("驿马", "中平", ma.gong,
                           f"时支{hour_zhi}取马在{pan.yi_ma_zhi}，落{ma.gong_name}宫",
                           "主动、搬迁、出行、异地；求动得马则速，求静得马则散。"))

    # ---- 12. 值符伏吟 / 反吟 ----
    bw = STAR_TO_BENWEI.get(pan.zhi_fu_star)
    if bw is not None and bw != 5:
        if gong_for_ring(pan.zhi_fu_gong) == gong_for_ring(bw):
            res.append(Pattern("值符伏吟", "中平", pan.zhi_fu_gong,
                               f"值符{pan.zhi_fu_star}落回本位{bw}宫",
                               "天盘星伏吟，全局主静；利守成复旧，不利开创。"))
        from ..core.constants import CHONG
        if gong_for_ring(pan.zhi_fu_gong) == gong_for_ring(CHONG[bw]):
            res.append(Pattern("值符反吟", "凶", pan.zhi_fu_gong,
                               f"值符{pan.zhi_fu_star}落对冲宫{bw}之反位",
                               "天盘星反吟，主反复、去而复返、事情兜圈子，宜稳住节奏。"))

    # ---- 13. 值使门吉凶（断事第一看）----
    if pan.zhi_shi_door:
        raw = DOOR_JIXIONG.get(pan.zhi_shi_door, "中平")
        if "大吉" in raw:
            lvl = "大吉"
        elif raw.startswith("吉"):
            lvl = "吉"
        elif "大凶" in raw:
            lvl = "大凶"
        elif "凶" in raw:
            lvl = "凶"
        else:
            lvl = "中平"
        res.append(Pattern(f"值使门·{pan.zhi_shi_door}", lvl, pan.zhi_shi_gong,
                           f"值使为{pan.zhi_shi_door}，落{pan.zhi_shi_gong}宫（{raw}）",
                           "值使代表事情的执行过程与走向，是断事时最先看的一环。"))

    res.sort(key=lambda x: (LEVEL_ORDER.get(x.level, 9), -x.gong))
    return res


def summarize(patterns: list[Pattern]) -> dict:
    """统计吉凶分布与倾向，供解读层作为"口径锚点"，避免大模型自由发挥。"""
    bucket = {"大吉": 0, "吉": 0, "中平": 0, "凶": 0, "大凶": 0}
    for p in patterns:
        if p.level in bucket:
            bucket[p.level] += 1
    score = bucket["大吉"] * 2 + bucket["吉"] - bucket["凶"] - bucket["大凶"] * 2
    if score >= 4:
        tone = "偏吉"
    elif score <= -4:
        tone = "偏凶"
    else:
        tone = "吉凶相杂"
    return {"counts": bucket, "score": score, "tone": tone}
