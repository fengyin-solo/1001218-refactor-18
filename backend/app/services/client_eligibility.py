"""委托方接单资格：档案列表、委托方详情、运输委托下单三处共用的唯一判断口径。

判断只依据委托方档案（client2）里的三项：

- 企业类别：黑名单/失信企业直接否决，类别缺失暂缓、需补录；
- 信用等级：良好可接单，一般/关注暂缓，较差/失信否决，空白或无法认定时按待评估暂缓；
- 合同期限：取合同到期日，已到期否决，长期合同不设到期日，缺失或无法认定暂缓。

任何调用方都只能拿 ``assess_client`` 返回的同一份结论，不允许再各写一遍规则。
历史接单记录里委托方可能只留了名称，所以编号查不到时按委托方名称兜底，
但不改写任何已有档案数据。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

CLIENT_MODULE = "client2"

# 三档唯一结论：可接单 / 暂缓接单 / 不可接单。
DECISION_ACCEPT = "可接单"
DECISION_HOLD = "暂缓接单"
DECISION_REJECT = "不可接单"

BLOCKED_CATEGORIES = {"黑名单企业", "失信企业"}
GOOD_CREDITS = {"AAA", "AA", "A", "良好", "信用良好"}
WATCH_CREDITS = {"BBB", "BB", "B", "一般", "信用一般", "关注"}
BAD_CREDITS = {"CCC", "CC", "C", "D", "较差", "差", "失信", "黑名单"}
PENDING_CREDITS = {"", "待评估", "未评估", "未评级", "暂无", "-", "—", "/"}
OPEN_ENDED_TERMS = {"长期", "永久", "无固定期限", "不限"}
TERM_SPLITTERS = ("~", "～", "至", "到")

ACCEPT_REASON = "企业类别、信用等级与合同期限均满足接单条件"
MISSING_CLIENT_REASON = "委托方档案不存在，无法核实接单资质"


def find_client(client_code: str) -> dict[str, Any] | None:
    """按委托方编号取档案；编号取不到时再按委托方名称兜底（历史接单记录只留了名称）。"""
    code = str(client_code or "").strip()
    if not code:
        return None
    rows = store.rows(CLIENT_MODULE)
    for row in rows:
        if str(row.get("委托方编号") or "").strip() == code:
            return row
    for row in rows:
        if str(row.get("委托方名称") or "").strip() == code:
            return row
    return None


def _parse_contract_term(raw_term: Any) -> tuple[date | None, str]:
    """识别合同到期日。

    返回 ``(到期日, 状态)``，状态取值：

    - ``ok``：识别出具体到期日（区间取最后一个日期）；
    - ``open``：长期/无固定期限合同；
    - ``missing``：合同期限未登记；
    - ``invalid``：写了值但认不出到期日。
    """
    text = str(raw_term or "").strip()
    if not text:
        return None, "missing"
    if text in OPEN_ENDED_TERMS:
        return None, "open"
    token = text
    for splitter in TERM_SPLITTERS:
        if splitter in token:
            token = token.split(splitter)[-1].strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(token, fmt).date(), "ok"
        except ValueError:
            continue
    return None, "invalid"


def assess_client(client_code: str) -> dict[str, Any]:
    """按委托方编号评估接单资格，返回唯一结论。

    返回字段固定为：委托方编号、档案存在、企业类别、信用等级、合同期限、
    接单结论（可接单/暂缓接单/不可接单）、可接单（布尔）、判定原因。
    三处调用方只读这份结果，不得在结果之外再补判断。
    """
    code = str(client_code or "").strip()
    client = find_client(code)

    result: dict[str, Any] = {
        "委托方编号": code,
        "档案存在": client is not None,
        "企业类别": None,
        "信用等级": None,
        "合同期限": None,
        "接单结论": DECISION_REJECT,
        "可接单": False,
        "判定原因": MISSING_CLIENT_REASON,
    }
    if client is None:
        return result

    category = str(client.get("企业类别") or "").strip()
    credit = str(client.get("信用等级") or "").strip()
    raw_term = client.get("合同期限")
    result["企业类别"] = category or None
    result["信用等级"] = credit or None
    result["合同期限"] = str(raw_term or "").strip() or None

    hard_blocks: list[str] = []
    soft_holds: list[str] = []

    # 企业类别
    if category in BLOCKED_CATEGORIES:
        hard_blocks.append(f"企业类别「{category}」属于禁入范围")
    elif not category:
        soft_holds.append("企业类别未填写，需先核实")

    # 信用等级
    if credit in BAD_CREDITS:
        hard_blocks.append(f"信用等级「{credit}」不符合接单要求")
    elif credit in WATCH_CREDITS:
        soft_holds.append(f"信用等级「{credit}」需人工复核")
    elif credit in GOOD_CREDITS:
        pass
    elif credit in PENDING_CREDITS:
        soft_holds.append("信用等级待评估")
    else:
        soft_holds.append(f"信用等级「{credit}」无法认定，按待评估处理")

    # 合同期限
    end_date, term_status = _parse_contract_term(raw_term)
    if term_status == "ok":
        assert end_date is not None
        if end_date < date.today():
            hard_blocks.append(f"合同已于 {end_date.isoformat()} 到期")
    elif term_status == "missing":
        soft_holds.append("合同期限未登记，需先核实")
    elif term_status == "invalid":
        soft_holds.append(f"合同期限「{result['合同期限']}」无法认定到期日")
    # open（长期合同）不产生限制。

    if hard_blocks:
        result["接单结论"] = DECISION_REJECT
        result["判定原因"] = hard_blocks[0]
    elif soft_holds:
        result["接单结论"] = DECISION_HOLD
        result["判定原因"] = soft_holds[0]
    else:
        result["接单结论"] = DECISION_ACCEPT
        result["可接单"] = True
        result["判定原因"] = ACCEPT_REASON
    return result
