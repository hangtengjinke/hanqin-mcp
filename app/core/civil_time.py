# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""输入参照系：把客户报的出生信息统一转换成「公历日期 + 标准北京时间」。

为什么单独一层
--------------
客户报出生信息时，可能同时用四种不同的参照系：

    · 纪年：公元 / 民国 / （更早的）日本年号、清朝年号
    · 历法：公历 / 农历
    · 地域：中国大陆 / 中国台湾地区（现代同属 UTC+8，但历史时区不同）
    · 夏令时：是否处在实行期间

排盘引擎只认「公历日期 + 某一时刻的标准时间」。这一层转换错了，后面全错 ——
但它**不影响任何排盘口径**，纯粹是输入解析。所以把四种参照系放在一起做，
避免出现"支持了民国纪年却没处理台湾地区夏令时"这种半吊子状态：
客户用一次发现时间差一小时，比不支持更伤信任。

两条铁律
--------
1. **不做静默自动扣减。** 不是每个家庭都按夏令时记录钟表时间，
   自动减反而可能把对的改错。做法是：检测到落在可疑时段就**提示**，
   由从业者确认是否启用扣减，并把结论存进案例库（可复现）。

2. **起止边界日必须标出来。** 夏令时开始/结束当天存在不确定性
   （各地执行细则、家庭记录习惯都可能不同），工具不该假装它是个确定值。

数据来源
--------
· 中国台湾地区夏令时：台北市政府《我国实施夏令时间一览表》
· 中国大陆夏令时：公开资料整理（1935–1979 的多段，与 1986–1991 的六段）
· 台湾地区 1937–1945 的 UTC+9：日据时期"中央标准时间"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# 纪年
# ---------------------------------------------------------------------------

# 公元年 = 基准 + 纪年数。民国元年 = 1912，昭和元年 = 1926，大正元年 = 1912，
# 明治元年 = 1868，宣统元年 = 1909。
ERA_BASE: dict[str, tuple[int, str]] = {
    "ad":       (0,    "公元"),
    "roc":      (1911, "民国"),
    "showa":    (1925, "昭和"),
    "taisho":   (1911, "大正"),
    "meiji":    (1867, "明治"),
    "xuantong": (1908, "宣统"),
}

ERA_LABEL = {k: v[1] for k, v in ERA_BASE.items()}


# ---------------------------------------------------------------------------
# 夏令时（日光节约时间）
# ---------------------------------------------------------------------------
#
# 按「连续年份区间」压缩：区间内每一年使用同一组起止（月, 日）。
# 起止日之后的年份请另起一行 —— 例如中国大陆 1955 年改成 5/1 起，
# 与 1953–1954 的 4/1 起不同，所以必须分段。

# 中国大陆
CN_DST: list[tuple[int, int, tuple[int, int], tuple[int, int], str]] = [
    (1935, 1951, (5, 1),  (9, 30),  ""),
    (1952, 1952, (3, 1),  (10, 31), ""),
    (1953, 1954, (4, 1),  (10, 31), ""),
    (1955, 1956, (5, 1),  (9, 30),  ""),
    (1957, 1959, (4, 1),  (9, 30),  ""),
    (1960, 1961, (6, 1),  (9, 30),  ""),
    (1974, 1975, (4, 1),  (10, 31), ""),
    (1979, 1979, (7, 1),  (9, 30),  ""),
    # 1986 年的起始日，多数资料写 5 月 4 日，也有写 4 月 13 日的 —— 存疑
    (1986, 1986, (5, 4),  (9, 14),  "起始日存疑（另有 4/13 之说）"),
    (1987, 1987, (4, 12), (9, 13),  ""),
    (1988, 1988, (4, 10), (9, 11),  ""),
    (1989, 1989, (4, 16), (9, 17),  ""),
    (1990, 1990, (4, 15), (9, 16),  ""),
    (1991, 1991, (4, 14), (9, 15),  ""),
]

# 中国台湾地区（民国 34–68 年，共 19 个年份段）
TW_DST: list[tuple[int, int, tuple[int, int], tuple[int, int], str]] = [
    (1945, 1951, (5, 1),  (9, 30),  ""),
    (1952, 1952, (3, 1),  (10, 31), ""),
    (1953, 1954, (4, 1),  (10, 31), ""),
    (1955, 1956, (4, 1),  (9, 30),  ""),
    (1957, 1959, (4, 1),  (9, 30),  ""),
    (1960, 1961, (6, 1),  (9, 30),  ""),
    (1974, 1975, (4, 1),  (9, 30),  ""),
    (1979, 1979, (7, 1),  (9, 30),  ""),
]

DST_TABLES: dict[str, list] = {"CN": CN_DST, "TW": TW_DST}

REGION_LABEL = {"CN": "中国大陆", "TW": "中国台湾地区"}

# 中国台湾地区 1937-10-01 ~ 1945-09-21 使用 UTC+9（日据时期"中央标准时间"）。
# 这批人现在 81 岁以上，极罕见，但技术上要知道。
TW_UTC9 = (date(1937, 10, 1), date(1945, 9, 21))


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class BirthInput:
    """客户报的出生信息（原始参照系，未做任何换算）。"""
    year: int
    month: int
    day: int
    hour: int = 0
    minute: int = 0

    era: str = "ad"            # ad / roc / showa / taisho / meiji / xuantong
    calendar: str = "solar"    # solar 公历 / lunar 农历（闰月用负月份表示）
    region: str = "CN"         # CN 中国大陆 / TW 中国台湾地区

    # 夏令时：None = 未指定（由工具检测并提示）；True = 确认按夏令时扣减；False = 确认不是
    is_dst: bool | None = None
    # 是否启用检测提示（关掉后既不提示也不扣减）
    detect_dst: bool = True


@dataclass
class StandardTime:
    """转换结果：公历日期 + 标准北京时间，以及一路上产生的提示。"""
    dt: datetime                     # 标准北京时间（已按需扣减夏令时）
    solar_date: tuple[int, int, int]
    era_year: int                    # 原始纪年数字（如「民国 75 年」的 75）
    era_label: str                   # 如「民国」
    era_text: str                    # 如「民国 75 年 3 月 20 日」
    calendar_in: str                 # 输入历法
    lunar_text: str = ""             # 对应的农历表述
    dst_applied_hours: int = 0       # 实际扣减的小时数
    dst_in_window: bool = False      # 原始时间是否落在夏令时区间内
    dst_boundary: bool = False       # 是否恰好在起止边界日
    dst_confirmed: bool = False      # 从业者是否已就夏令时口径表过态
    tz_offset: float = 8.0           # 该地该日的标准时区偏移
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def needs_dst_confirm(self) -> bool:
        """是否需要从业者确认夏令时口径（用于界面弹提示）。

        注意「确认过、答案为否」也算确认 —— 否则界面上会反复追问同一个问题。
        """
        return self.dst_in_window and not self.dst_confirmed


# ---------------------------------------------------------------------------
# 纪年
# ---------------------------------------------------------------------------

def resolve_era(year: int, era: str) -> tuple[int, str]:
    """纪年 → 公元年。

    公元年 = 基准 + 纪年数。例如民国 75 年 → 1911 + 75 = 1986。
    """
    key = (era or "ad").strip().lower()
    if key not in ERA_BASE:
        raise ValueError(f"不支持的纪年方式「{era}」，可用：{'、'.join(ERA_BASE)}")
    base, label = ERA_BASE[key]
    if key == "ad":
        return year, label
    return base + year, label


def to_era_text(solar_year: int, era: str) -> str:
    """公元年 → 纪年表述（用于结果页显示对照）。"""
    key = (era or "ad").strip().lower()
    base, label = ERA_BASE.get(key, (0, "公元"))
    if key == "ad":
        return f"{solar_year} 年"
    return f"{label} {solar_year - base} 年"


# ---------------------------------------------------------------------------
# 夏令时
# ---------------------------------------------------------------------------

def dst_window(year: int, region: str) -> tuple[date, date, str] | None:
    """返回该年该地的夏令时区间 (开始日, 结束日, 备注)。未实行则 None。"""
    for y0, y1, start, end, note in DST_TABLES.get(region, []):
        if y0 <= year <= y1:
            try:
                return date(year, *start), date(year, *end), note
            except ValueError:
                return None
    return None


def check_dst(d: date, region: str) -> dict:
    """检查某日是否落在夏令时期间。

    返回 {in_window, boundary, note}。`boundary` 表示恰好在起止当天 ——
    边界日的口径本身存在不确定性，工具应当提示而不是假装确定。
    """
    win = dst_window(d.year, region)
    if win is None:
        return {"in_window": False, "boundary": False, "note": ""}
    start, end, note = win
    if not (start <= d <= end):
        return {"in_window": False, "boundary": False, "note": ""}
    return {
        "in_window": True,
        "boundary": d in (start, end),
        "note": note or (f"该地该年夏令时为 {start:%m-%d} 至 {end:%m-%d}"),
    }


def tz_offset_at(d: date, region: str) -> float:
    """该地该日的标准时区偏移（不含夏令时）。

    中国台湾地区在 1937-10-01 ~ 1945-09-21 使用 UTC+9（日据时期中央标准时间），
    其余时间与大陆同为 UTC+8。
    """
    if region == "TW":
        lo, hi = TW_UTC9
        if lo <= d <= hi:
            return 9.0
    return 8.0


def dst_years_summary(region: str) -> list[tuple[int, int]]:
    """列出该地实行过夏令时的年份区间（供界面展示与文档生成）。"""
    return [(y0, y1) for y0, y1, _, _, _ in DST_TABLES.get(region, [])]


# ---------------------------------------------------------------------------
# 主转换
# ---------------------------------------------------------------------------

def to_standard(inp: BirthInput) -> StandardTime:
    """把出生信息统一转换成「公历日期 + 标准北京时间」。

    步骤：纪年 → 公历 → （农历换算）→ 时区/夏令时。
    """
    warnings: list[str] = []
    notes: list[str] = []

    # ---- 1. 纪年 → 公元 ----
    solar_year, era_label = resolve_era(inp.year, inp.era)
    # month/day 会被农历换算覆盖，所以后续一律用这两个变量，
    # 不要回头去取 inp.month / inp.day（那会把农历月日当成公历用）。
    month, day = inp.month, inp.day
    era_text = f"{era_label} {inp.year} 年 {inp.month} 月 {inp.day} 日" if inp.era != "ad" \
        else f"{solar_year} 年 {inp.month} 月 {inp.day} 日"

    # ---- 2. 农历 → 公历 ----
    lunar_text = ""
    if inp.calendar == "lunar":
        solar_year, month, day, lunar_text = _lunar_to_solar(
            solar_year, month, day, inp.hour, inp.minute, warnings
        )
        notes.append(f"输入为农历，已换算为公历 {solar_year}-{month:02d}-{day:02d}")
    else:
        lunar_text = _solar_to_lunar_text(solar_year, month, day, inp.hour, inp.minute)

    try:
        d = date(solar_year, month, day)
    except ValueError as exc:
        raise ValueError(f"日期无效：{solar_year}-{month}-{day}（{exc}）") from exc

    # ---- 3. 时区历史 ----
    tz = tz_offset_at(d, inp.region)
    region_label = REGION_LABEL.get(inp.region, inp.region)
    if tz != 8.0:
        warnings.append(
            f"{region_label}在 {TW_UTC9[0]} 至 {TW_UTC9[1]} 期间使用 UTC+9"
            f"（日据时期中央标准时间），与北京时间相差 {tz - 8:+.0f} 小时 —— "
            f"已按 UTC+{tz:.0f} 处理。"
        )
        notes.append(f"原标准时区 UTC+{tz:.0f}")

    # ---- 4. 夏令时 ----
    dst_hours = 0
    dst_confirmed = False
    dst_info = {"in_window": False, "boundary": False, "note": ""}
    if inp.detect_dst:
        dst_info = check_dst(d, inp.region)
        if dst_info["in_window"]:
            # 只要从业者表过态（无论按不按夏令时），就不再追问
            dst_confirmed = inp.is_dst is not None
            if inp.is_dst is True:
                dst_hours = 1
                notes.append("已按夏令时扣减 1 小时")
            elif inp.is_dst is False:
                notes.append("已确认为非夏令时记录，未做扣减")
            else:
                y0, y1 = dst_window(d.year, inp.region)[:2]  # type: ignore[misc]
                warnings.append(
                    f"该出生日期落在 {region_label} {d.year} 年夏令时期间"
                    f"（{y0:%m-%d} 至 {y1:%m-%d}）。请与客户确认：家里记录的是"
                    f"当时的钟表时间，还是已换算过的标准时间？"
                    f"若为钟表时间，请开启「按夏令时处理」以减去 1 小时。"
                    + ("（该日为起止边界日，口径本身存在不确定性）" if dst_info["boundary"] else "")
                )
            if dst_info["note"]:
                notes.append(dst_info["note"])

    # ---- 5. 组装 ----
    dt = datetime(solar_year, month, day, inp.hour, inp.minute) - timedelta(hours=dst_hours)

    return StandardTime(
        dt=dt,
        solar_date=(dt.year, dt.month, dt.day),
        era_year=inp.year,
        era_label=era_label,
        era_text=era_text,
        calendar_in=inp.calendar,
        lunar_text=lunar_text,
        dst_applied_hours=dst_hours,
        dst_in_window=dst_info["in_window"],
        dst_boundary=dst_info["boundary"],
        dst_confirmed=dst_confirmed,
        tz_offset=tz,
        warnings=warnings,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 历法换算（复用 lunar_python）
# ---------------------------------------------------------------------------

def _lunar_to_solar(year: int, month: int, day: int,
                    hour: int, minute: int, warnings: list[str]) -> tuple[int, int, int, str]:
    """农历 → 公历。闰月用负月份表示（lunar_python 的约定）。"""
    try:
        from lunar_python import Lunar
        lu = Lunar.fromYmdHms(year, month, day, hour, minute, 0)
        so = lu.getSolar()
        leap = "闰" if month < 0 else ""
        return so.getYear(), so.getMonth(), so.getDay(), \
            f"农历{year}年{leap}{abs(month)}月{day}日"
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"农历 {year} 年 {month} 月 {day} 日无法换算（{type(exc).__name__}）。"
            f"若为闰月，请用负数表示月份（如闰四月填 -4）。"
        ) from exc


def _solar_to_lunar_text(year: int, month: int, day: int, hour: int, minute: int) -> str:
    """公历 → 农历表述（仅用于显示对照）。失败时返回空串，不影响主流程。"""
    try:
        from lunar_python import Solar
        lu = Solar.fromYmdHms(year, month, day, hour, minute, 0).getLunar()
        return f"农历{lu.getYearInChinese()}年{lu.getMonthInChinese()}月{lu.getDayInChinese()}"
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("═" * 62)
    print("一、纪年换算")
    print("═" * 62)
    for y, era in ((75, "roc"), (1, "roc"), (100, "roc"), (10, "showa"),
                   (1, "showa"), (1, "taisho"), (45, "meiji"), (3, "xuantong")):
        ad, label = resolve_era(y, era)
        print(f"  {label} {y} 年 → 公元 {ad} 年")

    print()
    print("═" * 62)
    print("二、夏令时区间覆盖")
    print("═" * 62)
    for region in ("CN", "TW"):
        spans = dst_years_summary(region)
        total = sum(b - a + 1 for a, b in spans)
        print(f"  {REGION_LABEL[region]}：{len(spans)} 段，共 {total} 个年份")
        print(f"    {', '.join(f'{a}–{b}' if a != b else str(a) for a, b in spans)}")

    print()
    print("═" * 62)
    print("三、典型场景")
    print("═" * 62)

    cases = [
        ("中国大陆 · 1988 年夏令时期间（未确认）",
         BirthInput(1988, 6, 15, 14, 30, region="CN")),
        ("中国大陆 · 同年同月，确认为夏令时记录",
         BirthInput(1988, 6, 15, 14, 30, region="CN", is_dst=True)),
        ("中国台湾地区 · 1955 年夏令时期间（未确认）",
         BirthInput(1955, 6, 15, 14, 30, region="TW")),
        ("中国台湾地区 · 1940 年（UTC+9 时期）",
         BirthInput(1940, 6, 15, 14, 30, region="TW")),
        ("民国纪年 + 农历输入",
         BirthInput(75, 4, 12, 8, 0, era="roc", calendar="lunar", region="TW", detect_dst=False)),
        ("现代 · 无任何特殊情况",
         BirthInput(1995, 3, 20, 10, 0)),
    ]

    for title, bi in cases:
        st = to_standard(bi)
        print(f"\n  【{title}】")
        if bi.era != "ad":
            print(f"    输入纪年：{st.era_text}")
        print(f"    标准北京时间：{st.dt:%Y-%m-%d %H:%M}")
        if st.lunar_text:
            print(f"    农历对照：{st.lunar_text}")
        if st.dst_applied_hours:
            print(f"    夏令时扣减：{st.dst_applied_hours} 小时")
        if st.tz_offset != 8.0:
            print(f"    时区：UTC+{st.tz_offset:.0f}")
        for n in st.notes:
            print(f"    · {n}")
        for w in st.warnings:
            print(f"    ⚠ {w}")
        if st.needs_dst_confirm:
            print("    → 需要从业者确认夏令时口径")
