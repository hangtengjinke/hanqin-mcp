# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""排盘（计算核心层）—— 转盘奇门 与 飞盘奇门。

方案文档 6.3 要求"转盘与飞盘亦应分开"，本模块以 pan_type 参数切换。

转盘五步法（与公开算例逐步对齐，见 tests/test_pan.py）：

    一 布地盘三奇六仪：戊在局数之宫，戊己庚辛壬癸丁丙乙 依次排布（阳遁顺行、阴遁逆行）。
    二 定值符值使：时柱旬首（六仪）所落之宫，其本位九星为值符、本位八门为值使。
    三 布天盘九星：值符随时干——值符星落到时干所在之宫，其余八星循洛书顺时针随之旋转。
    四 布人盘八门：值使随时宫——从旬首宫按阳顺阴逆数至时支，所到之宫即值使落宫，
                    其余七门循洛书顺时针排布。
    五 布神盘八神：小值符随大值符——值符神落到时干宫，其余七神
                 依"值符螣蛇太阴六合白虎玄武九地九天"之序，阳遁顺时针、阴遁逆时针。

飞盘则在三、四、五步改为"按宫飞"（阳遁顺宫飞、阴遁逆宫飞）：九星飞九宫（含中宫），
八门、八神飞八宫（中五宫无门无神，寄坤二宫）。

中五宫的处理：转盘排星排门排神时中宫不参与，一律寄坤二宫；地盘三奇六仪则九宫皆布。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .calendar_util import Pillars
from .constants import (
    CHONG,
    DOOR_BENWEI,
    DOOR_RING,
    GAN_ALIAS,
    GODS,
    GONG_DIRECTION,
    GONG_NAME,
    GONG_WUXING,
    JIAZI_INDEX,
    RING,
    RING_INDEX,
    STAR_BENWEI,
    STAR_RING,
    STAR_TO_BENWEI,
    XUN_SHOU_YI,
    YIQI_ORDER,
    YIMA,
    ZHI_GONG,
    gong_for_ring,
)
from .ju import JuResult

TRAIL_PAN_TYPES = {"zhuan": "转盘（转宫）", "fei": "飞盘（飞宫）"}


@dataclass
class Palace:
    """单宫盘面。"""
    gong: int
    gong_name: str
    direction: str
    wuxing: str
    dipan_gan: str = ""        # 地盘三奇六仪
    tianpan_gan: str = ""      # 天盘干（随星而转）
    star: str = ""             # 天盘九星
    door: str = ""             # 人盘八门
    god: str = ""              # 神盘八神
    star_with_qin: bool = False   # 转盘时天禽随天芮同宫
    is_zhifu: bool = False     # 值符（星）所在宫
    is_zhishi: bool = False    # 值使（门）所在宫
    kong_wang: bool = False    # 旬空（时旬空亡落宫）
    yi_ma: bool = False        # 驿马

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class QimenPan:
    """完整盘面。"""
    pan_type: str
    pan_type_name: str
    dun: str
    ju: int
    jieqi: str
    jieqi_moment: str
    ju_reason: str
    ju_method: str
    ju_method_name: str
    pillars: dict
    xun_shou: str              # 时柱旬首，如 甲辰
    xun_shou_yi: str           # 旬首所遁之仪，如 壬
    xun_kong: str              # 旬空两支，如 戌亥
    xun_kong_gongs: list = field(default_factory=list)
    yi_ma_zhi: str = ""        # 驿马地支
    yi_ma_gong: int = 0
    xun_shou_gong: int = 0     # 旬首之仪所落宫
    shigan_gong: int = 0       # 时干所落宫（天盘值符落宫）
    zhi_fu_star: str = ""      # 值符（九星）
    zhi_fu_gong: int = 0
    zhi_shi_door: str = ""     # 值使（八门）
    zhi_shi_gong: int = 0
    palaces: list = field(default_factory=list)     # 按 GONG_ORDER 排序的九宫
    center_gan: str = ""       # 中五宫地盘干（寄坤二宫参考）

    def as_dict(self) -> dict:
        d = asdict(self)
        d["palaces"] = [p.as_dict() if hasattr(p, "as_dict") else p for p in self.palaces]
        return d

    # ---- 便捷查询 ----
    def palace(self, gong: int) -> dict:
        for p in self.palaces:
            pd = p.as_dict() if hasattr(p, "as_dict") else p
            if pd["gong"] == gong:
                return pd
        raise KeyError(gong)

    def find_by_door(self, door: str) -> dict | None:
        return next((p.as_dict() for p in self.palaces if p.door == door), None)

    def find_by_star(self, star: str) -> dict | None:
        return next((p.as_dict() for p in self.palaces if p.star == star), None)

    def find_by_gan(self, gan: str) -> dict | None:
        """按天盘干找宫（三奇六仪落宫）。找不到天盘再找地盘。"""
        hit = next((p.as_dict() for p in self.palaces if p.tianpan_gan == gan), None)
        if hit:
            return hit
        return next((p.as_dict() for p in self.palaces if p.dipan_gan == gan), None)


# ---------------------------------------------------------------------------
# 一、地盘
# ---------------------------------------------------------------------------

def build_dipan(ju: int, dun: str) -> dict[int, str]:
    """布地盘三奇六仪：戊在局数宫，其余依序阳顺阴逆排布。"""
    dipan: dict[int, str] = {}
    for i, gan in enumerate(YIQI_ORDER):
        if dun == "阳遁":
            g = ((ju - 1 + i) % 9) + 1
        else:
            g = ((ju - 1 - i) % 9) + 1
        dipan[g] = gan
    return dipan


# ---------------------------------------------------------------------------
# 二、值符值使定位
# ---------------------------------------------------------------------------

def resolve_zhi_fu_shi(pan: Pillars, dipan: dict[int, str]) -> tuple[int, int, str, str]:
    """返回 (旬首宫, 时干宫, 值符星, 值使门)。

    时干为甲时，甲遁于旬首之仪，直接取旬首仪之落宫。
    """
    assert pan.xun_shou in XUN_SHOU_YI, f"非法旬首：{pan.xun_shou}"
    xun_yi = XUN_SHOU_YI[pan.xun_shou]
    xun_gong = next(g for g, gan in dipan.items() if gan == xun_yi)

    shigan = pan.hour_gan
    if shigan == "甲":
        shigan_yi = xun_yi            # 甲不独现，遁于旬首之仪
    else:
        shigan_yi = shigan
    shigan_gong = next(g for g, gan in dipan.items() if gan == shigan_yi)

    # 旬首若在中五宫则寄坤二宫：本位星取天芮（天禽同宫），本位门取死门
    ring_g = gong_for_ring(xun_gong)
    zhi_fu_star = STAR_BENWEI[ring_g]
    zhi_shi_door = DOOR_BENWEI[ring_g]
    return xun_gong, shigan_gong, zhi_fu_star, zhi_shi_door


def resolve_zhi_shi_gong(pan: Pillars, xun_gong: int, dun: str) -> int:
    """值使随时宫：从旬首宫按阳顺阴逆数至时支所对应的步数。"""
    k = JIAZI_INDEX[pan.hour] - JIAZI_INDEX[pan.xun_shou]   # 旬内第几个时辰（0–9）
    if dun == "阳遁":
        g = ((xun_gong - 1 + k) % 9) + 1
    else:
        g = ((xun_gong - 1 - k) % 9) + 1
    return gong_for_ring(g)


# ---------------------------------------------------------------------------
# 三、转盘布星 / 门 / 神
# ---------------------------------------------------------------------------

def _ring_idx(g: int) -> int:
    return RING_INDEX[gong_for_ring(g)]


def spin(sipan_gong: int, benwei_gong: int, ring_items: list[str]) -> dict[int, str]:
    """转盘核心：第 i 个环位 RING[i] 落 ring_items[(i - delta) % 8]。

    delta = 值符/值使 实际落宫的环序 − 其本位宫的环序。
    这样"值"必落于目标宫，其余 7 项循洛书顺时针随之旋转。
    """
    delta = _ring_idx(sipan_gong) - _ring_idx(benwei_gong)
    return {RING[i]: ring_items[(i - delta) % 8] for i in range(8)}


# ---------------------------------------------------------------------------
# 四、飞盘布星 / 门 / 神
# ---------------------------------------------------------------------------

# 飞盘参与飞布的八宫序号（中五宫无门无神）
FLY_8 = [1, 2, 3, 4, 6, 7, 8, 9]


def fly_9(benwei_gong: int, steps: int, yang: bool) -> int:
    """九宫飞泊（含中宫）。"""
    if yang:
        return ((benwei_gong - 1 + steps) % 9) + 1
    return ((benwei_gong - 1 - steps) % 9) + 1


# ---------------------------------------------------------------------------
# 五、主入口
# ---------------------------------------------------------------------------

def build_pan(pan: Pillars, ju: JuResult, pan_type: str = "zhuan") -> QimenPan:
    """由四柱与定局结果排出完整盘面。

    Args:
        pan: 四柱（Pillars）
        ju: 定局结果（JuResult）
        pan_type: "zhuan" 转盘（默认）/ "fei" 飞盘
    """
    if pan_type not in TRAIL_PAN_TYPES:
        raise ValueError(f"不支持的盘式：{pan_type}，可选 {list(TRAIL_PAN_TYPES)}")
    yang = ju.dun == "阳遁"
    dipan = build_dipan(ju.ju, ju.dun)

    xun_gong, shigan_gong, zhi_fu_star, zhi_shi_door = resolve_zhi_fu_shi(pan, dipan)
    zhi_shi_gong = resolve_zhi_shi_gong(pan, xun_gong, ju.dun)
    shigan_gong_r = gong_for_ring(shigan_gong)
    xun_gong_r = gong_for_ring(xun_gong)

    star_at: dict[int, str] = {}
    door_at: dict[int, str] = {}
    god_at: dict[int, str] = {}
    tianpan_gan: dict[int, str] = {}

    if pan_type == "zhuan":
        # 天盘九星 + 天盘干：值符随时干，整体顺时针旋转
        star_at = spin(shigan_gong, xun_gong, STAR_RING)
        delta = _ring_idx(shigan_gong) - _ring_idx(xun_gong)
        for i, g in enumerate(RING):
            src = RING[(i - delta) % 8]
            tianpan_gan[g] = dipan[src]
        tianpan_gan[5] = dipan[5]

        # 人盘八门：值使随时宫，整体顺时针旋转
        door_at = spin(zhi_shi_gong, xun_gong, DOOR_RING)

        # 神盘八神：小值符随大值符（值符神落时干宫），阳顺阴逆
        direction = 1 if yang else -1
        j = _ring_idx(shigan_gong)
        god_at = {RING[(j + i * direction) % 8]: GODS[i] for i in range(len(GODS))}

    else:  # 飞盘
        steps = (shigan_gong - xun_gong) % 9 if yang else (xun_gong - shigan_gong) % 9
        for benwei, star in STAR_BENWEI.items():
            g = fly_9(benwei, steps, yang)
            star_at[g] = star
            tianpan_gan[g] = dipan[benwei]

        seq = list(FLY_8) if yang else list(reversed(FLY_8))
        idx0 = seq.index(zhi_shi_gong)
        shift0 = DOOR_RING.index(zhi_shi_door)
        for i, door in enumerate(DOOR_RING):
            door_at[seq[(idx0 + (i - shift0)) % 8]] = door

        jj = seq.index(shigan_gong_r)
        god_at = {seq[(jj + i) % 8]: GODS[i] for i in range(len(GODS))}

    # 旬空与驿马
    kong_zhi = [z for z in pan.xun_kong]
    kong_gongs = sorted({ZHI_GONG[z] for z in kong_zhi})
    ma_zhi = YIMA.get(pan.hour_zhi, "")
    ma_gong = ZHI_GONG.get(ma_zhi, 0)

    palaces: list[Palace] = []
    for g in [4, 9, 2, 3, 5, 7, 8, 1, 6]:
        star = star_at.get(g, "")
        door = door_at.get(g, "")
        god = god_at.get(g, "")
        is_center = g == 5
        palaces.append(Palace(
            gong=g,
            gong_name=GONG_NAME[g],
            direction=GONG_DIRECTION[g],
            wuxing=GONG_WUXING[g],
            dipan_gan=dipan.get(g, ""),
            tianpan_gan=tianpan_gan.get(g, ""),
            star=star,
            door=door,
            god=god,
            star_with_qin=(pan_type == "zhuan" and star == "天芮"),
            is_zhifu=(not is_center and gong_for_ring(g) == shigan_gong_r),
            is_zhishi=(not is_center and gong_for_ring(g) == gong_for_ring(zhi_shi_gong)),
            kong_wang=(g in kong_gongs),
            yi_ma=(ma_gong != 0 and g == ma_gong),
        ))

    return QimenPan(
        pan_type=pan_type,
        pan_type_name=TRAIL_PAN_TYPES[pan_type],
        dun=ju.dun, ju=ju.ju,
        jieqi=ju.jieqi, jieqi_moment=ju.jieqi_moment,
        ju_reason=ju.reason, ju_method=ju.method, ju_method_name=ju.method_name,
        pillars=pan.as_dict(),
        xun_shou=pan.xun_shou,
        xun_shou_yi=XUN_SHOU_YI[pan.xun_shou],
        xun_kong=pan.xun_kong,
        xun_kong_gongs=kong_gongs,
        yi_ma_zhi=ma_zhi,
        yi_ma_gong=ma_gong,
        xun_shou_gong=xun_gong,
        shigan_gong=shigan_gong,
        zhi_fu_star=zhi_fu_star,
        zhi_fu_gong=shigan_gong_r,     # 值符随时干；时干落中五宫时寄坤二宫
        zhi_shi_door=zhi_shi_door,
        zhi_shi_gong=zhi_shi_gong,
        palaces=palaces,
        center_gan=dipan.get(5, ""),
    )


# ---------------------------------------------------------------------------
# 六、反吟判定（供格局层复用）
# ---------------------------------------------------------------------------

def is_fanyin(pan: QimenPan) -> tuple[bool, str]:
    """反吟判定：天盘值符星落入其本位宫的对冲宫（主反复、去而复返）。"""
    benwei = STAR_TO_BENWEI.get(pan.zhi_fu_star)
    if benwei is None or pan_type_is_center(benwei):
        return False, ""
    hit = gong_for_ring(pan.zhi_fu_gong) == gong_for_ring(CHONG[benwei])
    return hit, ("天盘九星反吟（星落对冲本位宫，主反复、去而复返）" if hit else "")


def pan_type_is_center(gong: int) -> bool:
    return gong == 5
