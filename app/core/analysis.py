# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""用神取用与断语要点（计算核心层 · 确定性规则）。

奇门断事的第一性原理：**先取用神，再看用神落宫的门、星、神、格**。
用神取错，后面全错。因此本模块把"取用神"做成显式规则表，
而不是丢给大模型自由联想。

同时给出确定性"断语要点"（talking points）：
    日干宫（求测人）与时干宫（事体）的生克关系；
    用神落宫的门星神组合、空亡、击刑、门迫；
    ——这些是解读层必须覆盖的锚点，大模型只能在此基础上组织语言。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .constants import (
    DOOR_JIXIONG,
    GAN_WUXING,
    GONG_WUXING,
    STAR_JIXIONG,
    WUXING_KE,
    WUXING_SHENG,
    GOD_JIXIONG,
    DOOR_XIANG,
    STAR_XIANG,
    GOD_XIANG,
    gong_for_ring,
)

# ---------------------------------------------------------------------------
# 诉求分类 → 用神取用规则
# kind: door / star / god / gan / shigan / rigan / ma
# ---------------------------------------------------------------------------

QUESTION_TYPES: dict[str, dict] = {
    "求财": {
        "label": "求财 / 生意 / 投资",
        "yongshen": [
            ("生门", "door", "生门为财路本身，是求财第一用神"),
            ("戊", "gan", "戊为资本、本金"),
            ("值符", "god", "值符为主方、主导者、可依靠之人"),
        ],
        "tips": "三处用神俱旺且得吉门吉星则财顺；生门空亡或受迫，则财路虚而不实。",
    },
    "事业求职": {
        "label": "事业 / 求职 / 升迁",
        "yongshen": [
            ("开门", "door", "开门为事业、官职、出路"),
            ("庚", "gan", "庚为竞争、阻隔、对手"),
            ("值符", "god", "值符为主管、贵人"),
        ],
        "tips": "开门旺相、日干宫生助开门宫则顺；庚落宫克开门则竞争激烈。",
    },
    "婚姻感情": {
        "label": "婚姻 / 恋爱 / 感情",
        "yongshen": [
            ("六合", "god", "六合为媒合、婚姻、和合之神"),
            ("乙", "gan", "乙为女方（或阴柔一方）"),
            ("庚", "gan", "庚为男方（或阳刚一方）"),
        ],
        "tips": "乙庚两宫相生则和；相克或六合落空，则媒合无力、聚少离多。",
    },
    "健康疾病": {
        "label": "健康 / 疾病",
        "yongshen": [
            ("天心", "star", "天心为医药、医生之象"),
            ("天芮", "star", "天芮为病星，看病情轻重"),
            ("死门", "door", "死门为危急、终结之象"),
        ],
        "tips": "天芮旺而克日干宫则病重；天心旺相且生助日干宫则易得医治。"
                "（本产品不对病情作任何医学结论，仅作传统象意参考。）",
    },
    "学业考试": {
        "label": "学业 / 考试 / 文书",
        "yongshen": [
            ("天辅", "star", "天辅为文昌、师长、学业之星"),
            ("景门", "door", "景门为文书、考试、信息"),
            ("丁", "gan", "丁为文星、文书"),
        ],
        "tips": "天辅景门俱吉则文思通达；景门落空或被制，则临场易失手。",
    },
    "出行移动": {
        "label": "出行 / 搬迁 / 异地",
        "yongshen": [
            ("开门", "door", "开门为通达、外出顺畅"),
            ("驿马", "ma", "驿马主动、行程"),
            ("日干", "rigan", "日干为求测人本体"),
        ],
        "tips": "日干宫与驿马宫相生则行顺；日干入墓或落空，不宜远行。",
    },
    "官非诉讼": {
        "label": "官非 / 诉讼 / 纠纷",
        "yongshen": [
            ("开门", "door", "开门为官府、执法"),
            ("惊门", "door", "惊门为惊恐、牢狱、口舌"),
            ("庚", "gan", "庚为刑伤、对方势力"),
        ],
        "tips": "开门旺而克日干宫则不利；日干宫得三奇吉门则有转圜余地。",
    },
    "合作合伙": {
        "label": "合作 / 合伙 / 谈判",
        "yongshen": [
            ("六合", "god", "六合为合作、中介、契约"),
            ("日干", "rigan", "日干为我方"),
            ("时干", "shigan", "时干为对方或事体"),
        ],
        "tips": "日干宫与时干宫相生则合；相克或六合落空，慎签长约。",
    },
    "寻人寻物": {
        "label": "寻人 / 寻物 / 失物",
        "yongshen": [
            ("时干", "shigan", "时干为所寻之人或物"),
            ("日干", "rigan", "日干为寻者"),
            ("玄武", "god", "玄武主遗失、被盗之象"),
        ],
        "tips": "时干宫空亡则物易失难寻；时干落内盘（四正宫）则未远。",
    },
    "综合运势": {
        "label": "综合运势 / 整体判断",
        "yongshen": [
            ("日干", "rigan", "日干为求测人本人"),
            ("时干", "shigan", "时干为所问之事体"),
            ("值符", "god", "值符为主宰、大势"),
        ],
        "tips": "先看日干宫（我）与时干宫（事）的生克，再看值符定大势。",
    },
}

# 内盘（四正宫，主近、主快）／外盘（四隅宫，主远、主慢）
INNER_GONGS = {1, 3, 7, 9}
OUTER_GONGS = {2, 4, 6, 8}


@dataclass
class YongShenHit:
    name: str
    kind: str          # door / star / god / gan / ma
    reason: str
    gong: int
    gong_name: str
    door: str = ""
    star: str = ""
    god: str = ""
    tianpan_gan: str = ""
    dipan_gan: str = ""
    kong_wang: bool = False
    yi_ma: bool = False
    ji_xiong: str = ""
    xiang: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 定位用神
# ---------------------------------------------------------------------------

def _locate(pan, kind: str, value: str) -> dict | None:
    """把一个用神定位到具体宫。返回该宫的 dict。"""
    if kind == "shigan":
        g = pan.shigan_gong
        return pan.palace(gong_for_ring(g) if g == 5 else g)
    if kind == "rigan":
        day_gan = pan.pillars.get("day", "")[:1]
        hit = pan.find_by_gan(day_gan)
        if hit and hit["gong"] == 5:
            return pan.palace(2)
        return hit
    if kind == "ma":
        return pan.palace(pan.yi_ma_gong) if pan.yi_ma_gong else None
    if kind == "door":
        for p in pan.palaces:
            if p.door == value:
                return p.as_dict()
        return None
    if kind == "star":
        for p in pan.palaces:
            if p.star == value:
                return p.as_dict()
        return None
    if kind == "god":
        for p in pan.palaces:
            if p.god == value:
                return p.as_dict()
        return None
    if kind == "gan":
        hit = pan.find_by_gan(value)
        if hit and hit["gong"] == 5:
            return pan.palace(2)
        return hit
    return None


def _jixiong_of(kind: str, value: str, gong: int) -> str:
    if kind == "door":
        return f"门吉凶：{DOOR_JIXIONG.get(value, '中平')}"
    if kind == "star":
        return f"星吉凶：{STAR_JIXIONG.get(value, '中平')}"
    if kind == "god":
        return f"神吉凶：{GOD_JIXIONG.get(value, '中平')}"
    return ""


def _xiang_of(kind: str, value: str) -> str:
    if kind == "door":
        return DOOR_XIANG.get(value, "")
    if kind == "star":
        return STAR_XIANG.get(value, "")
    if kind == "god":
        return GOD_XIANG.get(value, "")
    return ""


def resolve_yongshen(pan, question_type: str) -> list[YongShenHit]:
    """按诉求类型取用神，逐个定位并附上判断依据。"""
    cfg = QUESTION_TYPES.get(question_type) or QUESTION_TYPES["综合运势"]
    hits: list[YongShenHit] = []

    for value, kind, reason in cfg["yongshen"]:
        p = _locate(pan, kind, value)
        if p is None:
            continue
        notes: list[str] = []
        if p["gong"] in INNER_GONGS:
            notes.append("落内盘（四正宫），主事近、应期快")
        elif p["gong"] in OUTER_GONGS:
            notes.append("落外盘（四隅宫），主事远、应期慢")
        if p["kong_wang"]:
            notes.append("⚠ 落旬空：力量虚浮，吉不实、凶减半")
        if p["gong"] == 5:
            notes.append("落中五宫，寄坤二宫看")

        hits.append(YongShenHit(
            name=("驿马" if kind == "ma" else value),
            kind=kind,
            reason=reason,
            gong=p["gong"],
            gong_name=p["gong_name"],
            door=p.get("door", ""),
            star=p.get("star", ""),
            god=p.get("god", ""),
            tianpan_gan=p.get("tianpan_gan", ""),
            dipan_gan=p.get("dipan_gan", ""),
            kong_wang=bool(p.get("kong_wang")),
            yi_ma=bool(p.get("yi_ma")),
            ji_xiong=_jixiong_of(kind, value, p["gong"]),
            xiang=_xiang_of(kind, value),
            notes=notes,
        ))
    return hits


# ---------------------------------------------------------------------------
# 日干宫 ↔ 时干宫 关系（断事主轴）
# ---------------------------------------------------------------------------

def _relation(a_wx: str, b_wx: str, a_name: str, b_name: str) -> str:
    if a_wx == b_wx:
        return f"{a_name}与{b_name}同气（比和）"
    if WUXING_SHENG.get(a_wx) == b_wx:
        return f"{a_name}生{b_name}（我方付出、主动）"
    if WUXING_SHENG.get(b_wx) == a_wx:
        return f"{b_name}生{a_name}（得助、有外力支持）"
    if WUXING_KE.get(a_wx) == b_wx:
        return f"{a_name}克{b_name}（我方占先、可主导）"
    if WUXING_KE.get(b_wx) == a_wx:
        return f"{b_name}克{a_name}（受制、不利）"
    return "关系不明"


def rigan_shigan_relation(pan) -> dict:
    """日干宫（我）与时干宫（事）的关系 —— 断事主轴。"""
    day_gan = pan.pillars.get("day", "")[:1]
    hour_gan = pan.pillars.get("hour", "")[:1]
    d = pan.find_by_gan(day_gan)
    if d and d["gong"] == 5:
        d = pan.palace(2)
    # 时干宫用奇门口径：值符所落之宫（即天盘时干落宫）
    h_gong = pan.shigan_gong
    h_gong = 2 if h_gong == 5 else h_gong
    h = pan.palace(h_gong)

    if not d or not h:
        return {"detail": "日干或时干未能在盘面定位", "relation": "未知"}

    d_wx = GAN_WUXING.get(day_gan, "")
    h_wx = GAN_WUXING.get(hour_gan, "") or GONG_WUXING.get(h_gong, "")
    rel = _relation(d_wx, h_wx, f"日干{day_gan}（我）", f"时干{hour_gan}（事）")
    return {
        "day_gan": day_gan, "day_gong": d["gong"], "day_gong_name": d["gong_name"],
        "day_door": d.get("door", ""), "day_star": d.get("star", ""), "day_god": d.get("god", ""),
        "hour_gan": hour_gan, "hour_gong": h_gong, "hour_gong_name": h["gong_name"],
        "hour_door": h.get("door", ""), "hour_star": h.get("star", ""), "hour_god": h.get("god", ""),
        "relation": rel,
        "detail": (f"求测人（日干{day_gan}）落{d['gong']}宫{d['gong_name']}，"
                   f"临{d.get('door','—')}·{d.get('star','—')}·{d.get('god','—')}；"
                   f"事体（时干{hour_gan}）落{h_gong}宫{h['gong_name']}，"
                   f"临{h.get('door','—')}·{h.get('star','—')}·{h.get('god','—')}。"
                   f"二者关系：{rel}。"),
    }


# ---------------------------------------------------------------------------
# 断语要点（确定性）
# ---------------------------------------------------------------------------

def build_talking_points(pan, patterns, yongshen: list[YongShenHit], qtype: str) -> list[str]:
    """生成必须被解读覆盖的确定性要点。大模型只能在这些点上展开。"""
    cfg = QUESTION_TYPES.get(qtype) or QUESTION_TYPES["综合运势"]
    pts: list[str] = []

    rel = rigan_shigan_relation(pan)
    pts.append(rel["detail"])

    pts.append(
        f"布局为{pan.dun}{pan.ju}局（{pan.ju_method_name}），节气{pan.jieqi}。"
        f"值符{pan.zhi_fu_star}落{pan.zhi_fu_gong}宫，值使{pan.zhi_shi_door}落{pan.zhi_shi_gong}宫。")

    for y in yongshen:
        seg = (f"用神「{y.name}」（{y.reason}）落{y.gong}宫{y.gong_name}，"
               f"临{y.door or '—'}·{y.star or '—'}·{y.god or '—'}")
        if y.ji_xiong:
            seg += f"；{y.ji_xiong}"
        if y.notes:
            seg += "；" + "；".join(y.notes)
        pts.append(seg)

    meaningful = [p for p in patterns if p.level in ("大吉", "吉", "凶", "大凶")]
    for p in meaningful[:8]:
        loc = "全局" if p.gong == 0 else f"{p.gong}宫"
        pts.append(f"格局【{p.name}】（{p.level}，{loc}）：{p.detail} → {p.advice}")

    pts.append(f"取用提示：{cfg['tips']}")
    return pts


def analyze(pan, question_type: str = "综合运势") -> dict:
    """完整分析：格局 + 用神 + 断定要点 + 吉凶倾向。"""
    from ..knowledge.patterns import detect_patterns, summarize

    patterns = detect_patterns(pan)
    summary = summarize(patterns)
    yongshen = resolve_yongshen(pan, question_type)
    points = build_talking_points(pan, patterns, yongshen, question_type)
    cfg = QUESTION_TYPES.get(question_type) or QUESTION_TYPES["综合运势"]

    return {
        "question_type": question_type,
        "question_label": cfg["label"],
        "patterns": [p.as_dict() for p in patterns],
        "summary": summary,
        "yongshen": [y.as_dict() for y in yongshen],
        "rigan_shigan": rigan_shigan_relation(pan),
        "talking_points": points,
    }
