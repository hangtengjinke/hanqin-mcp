# -*- coding: utf-8 -*-
# 瀚钦术数排盘系统 V1.0 (c) 2026 瀚钦（丹东）智能科技有限公司. All rights reserved.
"""合规拦截（对应方案文档第十章）。

命理行业的最高风险是政策合规。本模块负责三层拦截：

    第一层  输入拦截：用户诉求里出现医疗、金融、赌博、生死等预测性断言时，
            直接拒绝生成对应结论，改为引导至合规表述。
    第二层  输出护栏：拼装系统提示词时，把红线写死在提示里，
            大模型必须在这些约束内组织语言。
    第三层  输出复检：生成的文本再过一遍红线词表，命中则降级为
            模板化的合规表述并附免责声明。

免责声明为强制项，任何出口都必须携带。
"""

from __future__ import annotations

import re

DISCLAIMER = (
    "【免责声明】本结果为传统术数文化研究与娱乐性质参考，不构成任何医疗、"
    "金融、投资、法律、安全或人生决策建议。请勿据此作出实际决策，"
    "亦不得用于替代专业机构意见。请理性、批判地对待术数文化。"
)

BANNED_DOMAINS: dict[str, tuple[str, ...]] = {
    "医疗": ("能不能治好", "能治好吗", "能活多久", "寿命", "癌症", "绝症", "吃什么药",
             "诊断", "病能不能好", "手术成功", "会不会死", "什么时候死", "病情"),
    "金融": ("买哪只股", "哪只股票", "股票代码", "期货", "稳赚", "一定涨", "必涨",
             "会不会涨", "投资哪个", "理财收益", "加密货币", "彩票号码", "中奖号码"),
    "赌博": ("赌球", "下注", "押哪边", "六合彩", "开奖", "博彩", "买彩票"),
    # 「能不能赢官司」与「官司能不能赢」是同一诉求的两种语序，必须都覆盖
    "法律": ("会不会判刑", "判几年", "能不能赢官司", "官司能不能赢", "会不会败诉",
             "量刑", "胜诉概率"),
    "安全": ("会不会出车祸", "会不会被", "能不能活下来", "有无血光", "血光之灾"),
}

# 输出复检用：命中即降级
OUTPUT_RED_FLAGS = (
    "一定能好", "必然痊愈", "必定上涨", "稳赚不赔", "包治", "必死", "死期",
    "一定能赢", "必胜诉", "保证收益", "绝对安全",
)

_REJECT_TEMPLATE = (
    "您所询问的内容涉及{domain}领域的预测性断言，这超出了本产品的服务边界。\n\n"
    "本产品定位为传统术数文化的**研究工具与参考示例**，只对奇门遁甲盘面结构本身"
    "（局数、值符值使、九宫门星神仪、格局组合）作结构性说明，"
    "不对{domain}结果作任何预测或建议。\n\n"
    "如需{domain}相关意见，请咨询对应的专业机构或执业人员。\n\n"
    + DISCLAIMER
)


def screen_input(text: str) -> dict:
    """输入拦截：判断用户诉求是否触碰红线。"""
    if not text:
        return {"blocked": False, "domain": None, "matched": []}
    for domain, words in BANNED_DOMAINS.items():
        matched = [w for w in words if w in text]
        if matched:
            return {
                "blocked": True,
                "domain": domain,
                "matched": matched,
                "message": _REJECT_TEMPLATE.format(domain=domain),
            }
    return {"blocked": False, "domain": None, "matched": []}


def red_flag_prompt() -> str:
    """给大模型的硬约束（拼进 system prompt）。"""
    return (
        "【合规红线｜必须遵守，违反即视为回答失败】\n"
        "1. 不得对医疗、疾病、生死、寿命作任何断言或暗示。\n"
        "2. 不得对股票、基金、期货、加密货币、彩票等作涨跌或收益预测。\n"
        "3. 不得对赌博、开奖、下注作任何预测。\n"
        "4. 不得对诉讼胜负、量刑、判刑结果作预测。\n"
        "5. 不得对人身安全、车祸、血光、意外作断言。\n"
        "6. 所有结论必须限定为「盘面结构说明」与「传统象意参考」，"
        "不得使用「一定」「必然」「必定」「保证」「包」等绝对化表述。\n"
        "7. 结尾必须原样附上免责声明。\n"
        "8. 不得输出涉及政治敏感、民族宗教争议的内容。\n"
    )


def guard_output(text: str) -> tuple[str, bool]:
    """输出复检：命中绝对化/越界表述则降级。

    Returns:
        (最终文本, 是否触发降级)
    """
    if not text:
        return text, False
    hit = [w for w in OUTPUT_RED_FLAGS if w in text]
    if hit:
        text += (
            "\n\n（注：原回答中的绝对化表述已按合规要求移除。"
            "传统术数仅供文化研究参考，请勿据此作出实际决策。）"
        )
    for domain, words in BANNED_DOMAINS.items():
        for w in words:
            text = re.sub(re.escape(w), "［已按合规要求隐去］", text)
    if DISCLAIMER not in text:
        text = text.rstrip() + "\n\n" + DISCLAIMER
    return text, bool(hit)


def wrap_with_disclaimer(text: str) -> str:
    if DISCLAIMER in text:
        return text
    return text.rstrip() + "\n\n" + DISCLAIMER
