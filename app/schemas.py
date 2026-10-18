# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""API 数据契约（Pydantic）。

对应方案文档 12.1 的三个核心接口：
    POST /v1/qimen/qi      入参 时间、经纬度、起局法、盘式 → 出参 局数、值符值使、九宫布盘、门星神仪
    POST /v1/interpret     入参 排盘结果、从业者角色、诉求、口径 → 出参 结构化解读文本
    POST /v1/qimen/report  上面两者的一步式封装（Web 演示页用）
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MethodT = Literal["chaibu", "zhirun", "maoshan"]
PanT = Literal["zhuan", "fei"]
ZishiT = Literal["next", "same"]
# 用 Literal 而不是 str：audience 拼错（client→clinet）若静默降级成从业者版，
# 会产出一份带术语的报告被当成白话版转给客户 —— 这种错误必须 422 报错，不能兜底。
AudienceT = Literal["practitioner", "client"]

DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
    "%Y-%m-%d", "%Y/%m/%d",
)


def parse_moment(v: str | datetime) -> datetime:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    s = str(v).strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"无法解析时间「{v}」，请使用 2026-10-11 12:15 或 2026-10-11T12:15 格式"
    )


class TZAdjust(BaseModel):
    """把某个时区的墙上时间换算为北京时间（东八区）。"""
    utc_offset_hours: float = Field(
        8.0, ge=-12.0, le=14.0,
        description="输入时间所属时区相对 UTC 的偏移。中国大陆填 8（默认）。",
    )


class QiRequest(BaseModel):
    moment: str | datetime = Field(..., description="起局时间（默认按北京时间/东八区）")
    longitude: float = Field(120.0, ge=-180.0, le=180.0, description="经度，东经为正")
    latitude: float | None = Field(None, ge=-90.0, le=90.0, description="纬度（仅作记录）")
    place: str = Field("", description="地点名称（仅作记录与展示）")
    method: MethodT = Field("chaibu", description="起局法：chaibu 拆补 / zhirun 置闰 / maoshan 茅山")
    pan_type: PanT = Field("zhuan", description="盘式：zhuan 转盘 / fei 飞盘")
    zishi_sect: ZishiT = Field("next", description="子时界：next 晚子时归次日 / same 不换日")
    use_true_solar_time: bool = Field(True, description="是否做真太阳时修正")
    use_eot: bool = Field(True, description="真太阳时是否叠加均时差")
    utc_offset_hours: float = Field(8.0, ge=-12.0, le=14.0, description="输入时间所属时区偏移")
    include_compare: bool = Field(True, description="是否返回三法对照")
    question_type: str = Field("综合运势", description="诉求分类（影响用神取用），见 /v1/meta")

    @field_validator("moment")
    @classmethod
    def _check_moment(cls, v):
        return parse_moment(v)

    def beijing_dt(self) -> datetime:
        dt = parse_moment(self.moment)
        if abs(self.utc_offset_hours - 8.0) > 1e-9:
            dt = dt - timedelta(hours=self.utc_offset_hours - 8.0)
        return dt


class QiResponse(BaseModel):
    ok: bool = True
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any]


class InterpretRequest(BaseModel):
    question: str = Field("", description="用户的诉求原话")
    question_type: str = Field("综合运势", description="诉求分类，见 /v1/meta")
    role: str = Field("", description="从业者角色/口径要求，如「客户是企业主，关注现金流」")
    style: str = Field("", description="语气要求，如「简短直白」「书面正式」")
    allow_llm: bool = Field(True, description="是否允许调用大模型")
    audience: AudienceT = Field(
        "practitioner",
        description="输出对象：practitioner=从业者版六段式；client=客户版白话说明"
                    "（无术语、300–500 字、必带免责声明，供从业者编辑后转发）",
    )
    # 二选一：直接给排盘结果，或给时间由服务重算
    qi_result: dict[str, Any] | None = Field(None, description="上游 /v1/qimen/qi 的完整返回")
    qi_request: QiRequest | None = Field(None, description="或直接给排盘入参，由本接口重算")

    @model_validator(mode="after")
    def _need_one(self):
        if self.qi_result is None and self.qi_request is None:
            raise ValueError("必须提供 qi_result 或 qi_request 之一")
        return self


class InterpretResponse(BaseModel):
    ok: bool = True
    mode: str
    blocked: bool = False
    model: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    text: str
    # 一段话级专业断语。供案例详情页「我的断语」对话框上方的
    # 「系统自动推演」区域展示。从业者可以一键采纳到 verdict。
    verdict_short: str = ""
    disclaimer: str
    audience: AudienceT = "practitioner"


class ReportRequest(QiRequest):
    question: str = ""
    question_type: str = "综合运势"
    role: str = ""
    style: str = ""
    allow_llm: bool = True
    audience: AudienceT = Field(
        "practitioner",
        description="输出对象：practitioner=从业者版；client=客户版白话说明",
    )


class ReportResponse(BaseModel):
    ok: bool = True
    warnings: list[str] = Field(default_factory=list)
    qi: dict[str, Any]
    interpret: dict[str, Any]
    # 自动落库后的案例 id。前端拿它就能直接回填客户名/断语/应验，
    # 不必再按时间去找「刚存的那条」。
    case_id: int | None = None
    # 本次落库时同步写入 verdict_draft 的简断语。
    verdict_short: str = ""


# ---------------------------------------------------------------------------
# 案例库
# ---------------------------------------------------------------------------

class CaseUpdate(BaseModel):
    """案例回填。全部可选，只传要改的字段。

    `verdict`（从业者断语）与 `outcome`（应验结果）是这张表里最有价值的两列 ——
    它们是方案第十一章所说的「盘到断语对齐数据」，别人抄不走。
    """
    querent: str | None = Field(None, description="求测人（客户名/称呼）")
    question: str | None = Field(None, description="诉求原话")
    question_type: str | None = Field(None, description="诉求分类")
    role: str | None = Field(None, description="从业者口径要求")
    summary: str | None = Field(None, description="盘面一句话摘要")
    verdict: str | None = Field(None, description="从业者断语（这张盘断了什么）")
    outcome: str | None = Field(None, description="事后应验结果")
    outcome_at: str | None = Field(None, description="应验记录时间；留空则自动填当前时间")
    notes: str | None = Field(None, description="复盘笔记")
    tags: str | None = Field(None, description="标签，逗号分隔")
    starred: bool | None = Field(None, description="是否标记为重点案例")


# ---------------------------------------------------------------------------
# 八字
# ---------------------------------------------------------------------------

class BaziRequest(BaseModel):
    """八字排盘入参。

    **出生信息用「原始参照系」给**（客户怎么说就怎么填），纪年、历法、时区、
    夏令时的换算全部由服务端在这一层完成 —— 前端不该重复实现这套规则。
    """
    year: int = Field(..., description="出生年（按 era 指定的纪年方式填写）")
    month: int = Field(..., description="月；农历闰月用负数表示，如闰四月填 -4")
    day: int = Field(..., ge=1, le=31)
    hour: int = Field(0, ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)

    era: Literal["ad", "roc", "showa", "taisho", "meiji", "xuantong"] = Field(
        "ad", description="纪年方式：ad 公元 / roc 民国 / showa 昭和 / taisho 大正 / meiji 明治 / xuantong 宣统")
    calendar: Literal["solar", "lunar"] = Field(
        "solar", description="历法：solar 公历 / lunar 农历")
    region: Literal["CN", "TW"] = Field(
        "CN", description="地域：CN 中国大陆 / TW 中国台湾地区（影响夏令时表与历史时区）")

    is_dst: bool | None = Field(
        None, description="该时间是否为夏令时钟表时间：true 扣减 1 小时 / false 不扣 / 留空则由服务端检测并提示")
    detect_dst: bool = Field(True, description="是否启用夏令时检测提示")

    gender: int = Field(1, ge=0, le=1, description="1 男 / 0 女")
    longitude: float | None = Field(None, ge=-180.0, le=180.0,
                                    description="出生地经度（真太阳时用），东经为正")
    latitude: float | None = Field(None, ge=-90.0, le=90.0, description="纬度（仅作记录）")
    place: str = Field("", description="出生地名称（仅作记录与展示）")

    zishi_sect: ZishiT = Field(
        "next", description="子时界：next 晚子时归次日（默认，与奇门一致）/ same 晚子时不换日")
    use_true_solar_time: bool = Field(True, description="是否做真太阳时修正")
    use_eot: bool = Field(True, description="真太阳时是否叠加均时差")
    dayun_count: int = Field(10, ge=1, le=12, description="输出几步大运")

    include_shensha: bool = Field(True, description="是否计算神煞")
    tianyi_variant: Literal["geng", "jian"] = Field(
        "geng", description="天乙贵人口诀：geng 甲戊庚牛羊（主流）/ jian 甲戊兼牛羊")
    yangren_variant: Literal["yang_only", "both"] = Field(
        "yang_only", description="羊刃取法：yang_only 只论阳干（主流）/ both 阴阳干都论")


class BaziResponse(BaseModel):
    ok: bool = True
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any]


class BaziReportRequest(BaziRequest):
    question: str = Field("", description="诉求原话")
    question_type: str = Field("综合运势", description="诉求分类")
    role: str = Field("", description="从业者角色/口径要求")
    style: str = Field("", description="语气要求")
    allow_llm: bool = Field(True, description="是否允许调用大模型")
    audience: AudienceT = Field(
        "practitioner",
        description="输出对象：practitioner=从业者版；client=客户版白话说明",
    )


class BaziReportResponse(BaseModel):
    ok: bool = True
    warnings: list[str] = Field(default_factory=list)
    bazi: dict[str, Any]
    interpret: dict[str, Any]
    case_id: int | None = None
    # 本次落库时同步写入 verdict_draft 的简断语。
    verdict_short: str = ""


class BaziInterpretRequest(BaseModel):
    """对已有八字盘重新解读（不重排）。"""
    bazi_result: dict[str, Any] = Field(..., description="上游 /v1/bazi/pai 的完整返回")
    question: str = ""
    question_type: str = "综合运势"
    role: str = ""
    style: str = ""
    allow_llm: bool = True
    audience: AudienceT = Field(
        "practitioner",
        description="输出对象：practitioner=从业者版；client=客户版白话说明",
    )

