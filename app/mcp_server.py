# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""MCP 服务端 —— 供 WorkBuddy 连接器接入。

对外口径：**国学历法与象数文化计算**。
本服务只暴露确定性计算能力（真太阳时换算、定气节气、干支四柱、盘面结构），
全部结果由引擎算出，不经过任何大模型；出口一律强制携带免责声明。

运行方式：
    stdio   python -m app.mcp_server --transport stdio
    http    python -m app.mcp_server --transport streamable-http --port 8000

http 模式若设置环境变量 HANQIN_TOKEN（或传入 --token），
将对 /mcp 请求做 Bearer 校验；未设置则不鉴权（仅限内网自用）。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 允许以 `python -m app.mcp_server` 或 `hanqin-mcp` 两种方式启动
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.compliance import DISCLAIMER, screen_input  # noqa: E402
from app.core.bazi import BaziOptions, pai as bazi_pai  # noqa: E402
from app.core.calendar_util import (  # noqa: E402
    current_jieqi,
    four_pillars,
    jieqi_span,
    mean_to_true_solar,
    next_jieqi,
)
from app.core.civil_time import BirthInput, to_standard  # noqa: E402
from app.core.engine import QiJuOptions, qi_ju  # noqa: E402
from app.schemas import parse_moment  # noqa: E402

# ---------------------------------------------------------------------------
# 对外口径常量
# ---------------------------------------------------------------------------

SERVICE_NAME = "瀚钦 · 国学历法计算"

USAGE_NOTE = (
    "本服务只输出历法换算与盘面结构的确定性计算结果，供传统象数文化研究与教学参考；"
    "不构成任何预测、断言或决策建议。"
)

INSTRUCTIONS = (
    "你是「瀚钦 · 国学历法计算」服务的调用者。该服务提供传统历法与象数文化的"
    "确定性计算：真太阳时换算、定气节气、干支四柱、奇门盘面结构、八字盘面结构。\n"
    "使用纪律：\n"
    "1. 这些工具只做计算。任何「吉凶判断、运势预测、择日建议、命运断言」都必须由你"
    "在文化研究语境下组织语言，且不得使用绝对化表述。\n"
    "2. 工具返回的 disclaimer 字段必须原样保留在最终回答中。\n"
    "3. 涉及医疗、金融、法律、人身安全、赌博的诉求，工具会直接拒绝并返回合规提示，"
    "此时不得改用其他方式绕过。\n"
    "4. 排盘属于确定性计算，禁止你自行推算干支或局数 —— 一律调用工具。"
)

# ---------------------------------------------------------------------------
# 统一出口封装
# ---------------------------------------------------------------------------


def _pack(data: dict, warnings: list[str] | None = None) -> dict:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "warnings": warnings or [],
        "data": data,
        "note": USAGE_NOTE,
        "disclaimer": DISCLAIMER,
    }


def _blocked(message: str, domain: str | None = None) -> dict:
    return {
        "ok": False,
        "blocked": True,
        "domain": domain,
        "message": message,
        "disclaimer": DISCLAIMER,
    }


def _fail(message: str) -> dict:
    return {"ok": False, "error": message, "disclaimer": DISCLAIMER}


def _guard(question: str) -> dict | None:
    """自由文本诉求的合规前置拦截。命中返回拒绝体，未命中返回 None。"""
    if not question:
        return None
    hit = screen_input(question)
    if hit.get("blocked"):
        return _blocked(hit["message"], hit.get("domain"))
    return None


def _to_beijing(moment: str, utc_offset_hours: float) -> datetime:
    """把「某时区的墙上时间」换算为北京时间（东八区）。"""
    dt = parse_moment(moment)
    return dt - timedelta(hours=float(utc_offset_hours) - 8.0)


# ---------------------------------------------------------------------------
# 输出裁剪（控制返回体积，避免撑爆上下文）
# ---------------------------------------------------------------------------

_PALACE_KEYS = (
    "gong", "gong_name", "direction", "dipan_gan", "tianpan_gan",
    "star", "door", "god", "is_zhifu", "is_zhishi", "kong_wang", "yi_ma",
)

_JU_KEYS = ("method", "method_name", "dun", "ju", "jieqi", "jieqi_moment", "yuan", "futou")


def _brief_qimen(res: dict) -> dict:
    pan = res.get("pan", {}) or {}
    palaces = [
        {k: p.get(k) for k in _PALACE_KEYS if k in p}
        for p in pan.get("palaces", []) or []
    ]
    analysis = res.get("analysis", {}) or {}
    return {
        "input": res.get("input"),
        "pillars": res.get("pillars"),
        "ju": {k: v for k, v in (res.get("ju", {}) or {}).items() if k in _JU_KEYS},
        "pan": {
            k: pan.get(k)
            for k in (
                "pan_type_name", "dun", "ju", "jieqi", "xun_shou",
                "xun_shou_yi", "xun_kong", "zhi_fu_star", "zhi_fu_gong",
                "zhi_shi_door", "zhi_shi_gong", "shigan_gong", "center_gan",
            )
            if k in pan
        },
        "palaces": palaces,
        "analysis": {
            "question_type": analysis.get("question_type"),
            "summary": analysis.get("summary"),
            "talking_points": analysis.get("talking_points"),
            "rigan_shigan": (analysis.get("rigan_shigan") or {}).get("detail"),
        },
    }


def _brief_bazi(res: dict) -> dict:
    dayun = res.get("dayun", {}) or {}
    return {
        "used_datetime": res.get("used_datetime"),
        "pillars": res.get("pillars"),
        "day_master": res.get("day_master"),
        "day_master_wuxing": res.get("day_master_wuxing"),
        "wuxing": res.get("wuxing"),
        "extra": res.get("extra"),
        "dayun": {
            "start_age": dayun.get("start_age"),
            "start_age_text": dayun.get("start_age_text"),
            "direction": dayun.get("direction"),
            "steps": [
                s for s in (dayun.get("steps", []) or [])
            ][:12],
        },
        "shensha_summary": res.get("shensha_summary"),
        "facts": res.get("facts"),
    }


# ---------------------------------------------------------------------------
# MCP 工具
# ---------------------------------------------------------------------------

mcp = FastMCP(SERVICE_NAME, instructions=INSTRUCTIONS)


@mcp.tool()
def service_info() -> dict:
    """查询本服务的能力清单、流派参数可选项与合规边界。

    开始计算前先调用本工具，可拿到各参数的合法取值（起局法、盘式、子时界、
    纪年方式、历法、地区等），避免传错参数。
    """
    return _pack({
        "service": SERVICE_NAME,
        "capabilities": [
            "true_solar_time —— 真太阳时换算（经度时差 + 均时差）",
            "solar_term —— 定气节气查询（当前 / 下一个 / 全年表）",
            "ganzhi_four_pillars —— 干支四柱推演",
            "qimen_layout —— 奇门盘面结构计算（定局 + 布盘 + 格局要点）",
            "bazi_chart —— 八字盘面结构计算（四柱 + 大运流年 + 神煞）",
        ],
        "options": {
            "method 起局法": ["chaibu 拆补", "zhirun 置闰", "maoshan 茅山"],
            "pan_type 盘式": ["zhuan 转盘（转宫）", "fei 飞盘（飞宫）"],
            "zishi_sect 子时界": ["next 晚子时归次日（默认）", "same 晚子时不换日"],
            "era 纪年": ["ad 公元", "roc 民国", "xuantong 宣统", "meiji 明治", "taisho 大正", "showa 昭和"],
            "calendar 历法": ["solar 公历", "lunar 农历（闰月用负月份，如闰四月填 -4）"],
            "region 地区": ["CN 中国大陆", "TW 中国台湾地区"],
            "gender 性别": [1, 0],
            "detail 返回粒度": ["brief 精简（默认，推荐）", "full 全量（含三法对照与全部格局）"],
        },
        "boundary": {
            "只做": "历法换算、干支推演、盘面结构计算",
            "不做": "医疗、金融、法律、人身安全、赌博等领域的预测性断言",
            "强制": "所有回答必须原样保留 disclaimer 字段",
        },
    })


@mcp.tool()
def true_solar_time(
    moment: str,
    longitude: float = 120.0,
    use_eot: bool = True,
    utc_offset_hours: float = 8.0,
) -> dict:
    """把钟表时间换算为真太阳时（经度时差 + 均时差）。

    传统历法中时刻以地方太阳时为准，钟表时间需按观测地经度与均时差校正。
    本工具给出校正前后的时刻与差值构成，供后续取时辰、定局使用。

    Args:
        moment: 时间，格式如 2026-10-11 14:30 或 2026-10-11T14:30
        longitude: 观测地经度，东经为正；默认 120.0（东八区基准）
        use_eot: 是否叠加均时差，默认 True
        utc_offset_hours: 输入时间所属时区相对 UTC 的偏移小时数，默认 8.0
    """
    try:
        bj = _to_beijing(moment, utc_offset_hours)
        tst = mean_to_true_solar(bj, float(longitude), use_eot=use_eot)
        delta = (tst - bj).total_seconds() / 60.0
        lon_diff = (float(longitude) - 120.0) * 4.0
        return _pack({
            "clock_time": bj.strftime("%Y-%m-%d %H:%M:%S"),
            "true_solar_time": tst.strftime("%Y-%m-%d %H:%M:%S"),
            "delta_minutes": round(delta, 1),
            "longitude": float(longitude),
            "longitude_diff_minutes": round(lon_diff, 1),
            "equation_of_time_applied": bool(use_eot),
            "input_utc_offset_hours": float(utc_offset_hours),
        })
    except Exception as exc:  # 参数或时间格式错误
        return _fail(f"真太阳时换算失败：{exc}")


@mcp.tool()
def solar_term(moment: str, utc_offset_hours: float = 8.0) -> dict:
    """查询某时刻的二十四节气（定气法）。

    返回该时刻所属节气与交节时刻、下一个节气及交节时刻，并给出全年节气时刻表。

    Args:
        moment: 时间，格式如 2026-10-11 14:30
        utc_offset_hours: 输入时间所属时区相对 UTC 的偏移小时数，默认 8.0
    """
    try:
        bj = _to_beijing(moment, utc_offset_hours)
        cur = current_jieqi(bj)
        nxt = next_jieqi(bj)
        return _pack({
            "moment": bj.strftime("%Y-%m-%d %H:%M:%S"),
            "current": {"name": cur.name, "moment": cur.moment.strftime("%Y-%m-%d %H:%M:%S")},
            "next": {"name": nxt.name, "moment": nxt.moment.strftime("%Y-%m-%d %H:%M:%S")},
            "year_table": [
                {"name": j.name, "moment": j.moment.strftime("%Y-%m-%d %H:%M:%S")}
                for j in jieqi_span(bj)
            ],
        })
    except Exception as exc:
        return _fail(f"节气查询失败：{exc}")


@mcp.tool()
def ganzhi_four_pillars(
    moment: str,
    zishi_sect: str = "next",
    longitude: float | None = None,
    use_true_solar_time: bool = True,
    use_eot: bool = True,
    utc_offset_hours: float = 8.0,
) -> dict:
    """推演某时刻的干支四柱（年柱 / 月柱 / 日柱 / 时柱）及旬首旬空。

    时柱由本引擎自算（不依赖第三方历法库的晚子时口径），
    子时界可通过 zishi_sect 切换。

    Args:
        moment: 时间，格式如 2026-10-11 14:30
        zishi_sect: 子时界，next 晚子时归次日（默认）/ same 晚子时不换日
        longitude: 观测地经度；提供且 use_true_solar_time 为真时先做真太阳时校正
        use_true_solar_time: 是否先换算真太阳时，默认 True
        use_eot: 真太阳时是否叠加均时差，默认 True
        utc_offset_hours: 输入时间所属时区相对 UTC 的偏移小时数，默认 8.0
    """
    if zishi_sect not in ("next", "same"):
        return _fail("zishi_sect 只能是 next 或 same")
    try:
        bj = _to_beijing(moment, utc_offset_hours)
        warnings: list[str] = []
        if use_true_solar_time and longitude is not None:
            dt = mean_to_true_solar(bj, float(longitude), use_eot=use_eot)
        else:
            dt = bj
            if use_true_solar_time:
                warnings.append("未提供经度，已跳过真太阳时校正 —— 时柱可能因经度差异而偏差。")
        pl = four_pillars(dt, zishi_sect=zishi_sect)
        return _pack({
            "used_datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "pillars": pl.as_dict(),
        }, warnings)
    except Exception as exc:
        return _fail(f"四柱推演失败：{exc}")


@mcp.tool()
def qimen_layout(
    moment: str,
    method: str = "chaibu",
    pan_type: str = "zhuan",
    longitude: float = 120.0,
    latitude: float | None = None,
    place: str = "",
    question_type: str = "综合运势",
    use_true_solar_time: bool = True,
    use_eot: bool = True,
    zishi_sect: str = "next",
    utc_offset_hours: float = 8.0,
    detail: str = "brief",
    question: str = "",
) -> dict:
    """计算奇门遁甲盘面结构（定局 + 布盘 + 格局要点），结果为确定性计算，不经大模型。

    返回四柱、定局结果与推导说明、九宫盘面（地盘干/天盘干/九星/八门/八神）、
    值符值使落宫、旬首旬空，以及格局与断语要点（talking_points）。

    Args:
        moment: 起局时间，格式如 2026-10-11 14:30
        method: 起局法，chaibu 拆补（默认）/ zhirun 置闰 / maoshan 茅山
        pan_type: 盘式，zhuan 转盘（默认）/ fei 飞盘
        longitude: 观测地经度，东经为正，默认 120.0
        latitude: 观测地纬度，仅作记录
        place: 地点名称，仅作记录与展示
        question_type: 诉求分类，影响用神取用；可先用 service_info 查看，默认 综合运势
        use_true_solar_time: 是否先换算真太阳时，默认 True
        use_eot: 真太阳时是否叠加均时差，默认 True
        zishi_sect: 子时界，next（默认）/ same
        utc_offset_hours: 输入时间所属时区相对 UTC 的偏移小时数，默认 8.0
        detail: brief 精简（默认，推荐）/ full 全量（含三法对照与全部格局）
        question: 用户原始诉求（可选）。传入后会做合规前置检查，
                  命中医疗/金融/法律/安全/赌博等红线时直接返回合规提示而不计算
    """
    blocked = _guard(question)
    if blocked:
        return blocked
    if method not in ("chaibu", "zhirun", "maoshan"):
        return _fail("method 只能是 chaibu / zhirun / maoshan")
    if pan_type not in ("zhuan", "fei"):
        return _fail("pan_type 只能是 zhuan / fei")
    if detail not in ("brief", "full"):
        return _fail("detail 只能是 brief / full")
    try:
        bj = _to_beijing(moment, utc_offset_hours)
        opts = QiJuOptions(
            method=method,
            pan_type=pan_type,
            use_true_solar_time=use_true_solar_time,
            use_eot=use_eot,
            zishi_sect=zishi_sect,
            question_type=question_type,
            include_compare=(detail == "full"),
            place=place,
            longitude=float(longitude),
            latitude=latitude,
        )
        res = qi_ju(bj, opts)
        payload = res if detail == "full" else _brief_qimen(res)
        return _pack(payload)
    except Exception as exc:
        return _fail(f"奇门盘面计算失败：{exc}")


@mcp.tool()
def bazi_chart(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    era: str = "ad",
    calendar: str = "solar",
    region: str = "CN",
    gender: int = 1,
    longitude: float | None = None,
    is_dst: bool | None = None,
    zishi_sect: str = "next",
    use_true_solar_time: bool = True,
    dayun_count: int = 10,
    include_shensha: bool = True,
    detail: str = "brief",
    question: str = "",
) -> dict:
    """计算八字盘面结构（四柱 + 大运流年 + 神煞），结果为确定性计算，不经大模型。

    支持公元/民国/宣统/明治/大正/昭和纪年、公历与农历（闰月用负月份）输入，
    自动处理历史时区与夏令时（中国大陆 1986-1991、中国台湾地区 1945-1979）。

    Args:
        year: 出生年（按 era 指定的纪年方式填写）
        month: 月；农历闰月用负数表示，如闰四月填 -4
        day: 日
        hour: 时，0-23，默认 0
        minute: 分，0-59，默认 0
        era: 纪年，ad 公元（默认）/ roc 民国 / xuantong 宣统 / meiji 明治 / taisho 大正 / showa 昭和
        calendar: 历法，solar 公历（默认）/ lunar 农历
        region: 地区，CN 中国大陆（默认）/ TW 中国台湾地区
        gender: 1 男（默认）/ 0 女
        longitude: 出生地经度，东经为正；用于真太阳时校正
        is_dst: 夏令时口径；None 由引擎检测并提示，True 确认按夏令时扣减，False 确认不是
        zishi_sect: 子时界，next（默认）/ same
        use_true_solar_time: 是否先换算真太阳时，默认 True
        dayun_count: 大运步数，默认 10
        include_shensha: 是否计算神煞，默认 True
        detail: brief 精简（默认，推荐）/ full 全量
        question: 用户原始诉求（可选）。传入后会做合规前置检查，命中红线时拒绝计算
    """
    blocked = _guard(question)
    if blocked:
        return blocked
    if era not in ("ad", "roc", "showa", "taisho", "meiji", "xuantong"):
        return _fail("era 取值不合法，可用 ad / roc / xuantong / meiji / taisho / showa")
    if calendar not in ("solar", "lunar"):
        return _fail("calendar 只能是 solar / lunar")
    if region not in ("CN", "TW"):
        return _fail("region 只能是 CN / TW")
    if detail not in ("brief", "full"):
        return _fail("detail 只能是 brief / full")
    try:
        std = to_standard(BirthInput(
            year=year, month=month, day=day, hour=hour, minute=minute,
            era=era, calendar=calendar, region=region, is_dst=is_dst,
        ))
        opts = BaziOptions(
            gender=1 if int(gender) else 0,
            zishi_sect=zishi_sect,
            use_true_solar_time=use_true_solar_time,
            longitude=longitude,
            dayun_count=int(dayun_count),
            include_shensha=include_shensha,
        )
        res = bazi_pai(std.dt, opts)
        warnings = list(std.warnings) + list(res.get("warnings", []))
        payload = res if detail == "full" else _brief_bazi(res)
        if detail == "brief":
            payload["input_era_text"] = std.era_text
            payload["dst_applied_hours"] = std.dst_applied_hours
        else:
            payload["standard"] = {
                "era_text": std.era_text,
                "solar_date": std.solar_date,
                "lunar_text": std.lunar_text,
                "dst_applied_hours": std.dst_applied_hours,
                "tz_offset": std.tz_offset,
            }
        return _pack(payload, warnings)
    except Exception as exc:
        return _fail(f"八字盘面计算失败：{exc}")


# ---------------------------------------------------------------------------
# HTTP 模式的 Bearer 鉴权（stdio 模式不需要）
# ---------------------------------------------------------------------------


def _build_http_app(token: str | None):
    """构造 Starlette 应用；给了 token 就加 Bearer 校验中间件。"""
    app = mcp.streamable_http_app()

    if not token:
        return app

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    expected = f"Bearer {token}"

    class _TokenGate(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path.rstrip("/").endswith("/mcp"):
                if request.headers.get("authorization") != expected:
                    return JSONResponse(
                        {"ok": False, "error": "未授权：请检查连接器填写的 Access Token。"},
                        status_code=401,
                    )
            return await call_next(request)

    app.add_middleware(_TokenGate)
    return app


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="瀚钦 · 国学历法计算 MCP 服务")
    parser.add_argument("--transport", default="stdio",
                        choices=["stdio", "streamable-http"],
                        help="传输方式，默认 stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--token", default=os.getenv("HANQIN_TOKEN", ""),
                        help="HTTP 模式的 Bearer Token；不填则不鉴权")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    import uvicorn

    uvicorn.run(
        _build_http_app(args.token or None),
        host=args.host,
        port=args.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
