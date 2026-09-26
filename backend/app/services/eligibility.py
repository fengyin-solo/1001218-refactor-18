"""委托方接单资格：档案列表、委托方详情与下单校验共用同一份判定。

唯一入参是委托方编号查到的三个档案字段：企业类别、信用等级、合同期限。
任何页面或接口都不要再各写一套判断，统一调用这里的结论，避免列表、详情、
下单三处口径不一致。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

CLIENT_MODULE = "client2"
CLIENT_CODE_FIELD = "委托方编号"
CLIENT_NAME_FIELD = "委托方名称"
CATEGORY_FIELD = "企业类别"
CREDIT_FIELD = "信用等级"
CONTRACT_FIELD = "合同期限"

# 接单资格的三种唯一结论。
CAN_ACCEPT = "可接单"
CANNOT_ACCEPT = "不可接单"
PENDING_REVIEW = "待评估"

# 允许承接运输委托的企业类别；不在名单内的不予接单。
ACCEPTED_CATEGORIES = {"生产企业", "贸易企业", "电商企业", "连锁零售"}
# 视为信用良好的等级；其余已评定等级按风险客户处理。
GOOD_CREDIT_LEVELS = {"AAA", "AA", "A", "良好"}
# 信用资料缺失或尚未评定时的占位写法。
UNRATED_CREDIT_LEVELS = {"", "待评估", "未评估", "暂无"}


def _parse_date(value: Any) -> date | None:
    """把档案里的合同期限解析成日期；解析不了返回 None（视为待评估）。"""
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def evaluate_eligibility(client: dict[str, Any] | None) -> dict[str, Any]:
    """依据企业类别、信用等级、合同期限给出唯一接单结论。

    返回 {"eligible", "conclusion", "credit", "reasons"}：
    - 资料缺失或合同期限无法核实时给「待评估」，不直接放行；
    - 类别、信用、合同任一项不达标给「不可接单」并列出原因；
    - 三项全部满足才给「可接单」。
    """
    if client is None:
        return {
            "eligible": False,
            "conclusion": PENDING_REVIEW,
            "credit": PENDING_REVIEW,
            "reasons": ["未按委托方编号查到委托方档案"],
        }

    category = str(client.get(CATEGORY_FIELD) or "").strip()
    credit = str(client.get(CREDIT_FIELD) or "").strip()
    contract_end = _parse_date(client.get(CONTRACT_FIELD))

    if not category or credit in UNRATED_CREDIT_LEVELS or contract_end is None:
        return {
            "eligible": False,
            "conclusion": PENDING_REVIEW,
            "credit": PENDING_REVIEW,
            "reasons": ["企业类别、信用等级或合同期限资料不完整，需先完成评估"],
        }

    reasons: list[str] = []
    if category not in ACCEPTED_CATEGORIES:
        reasons.append(f"企业类别「{category}」不具备接单资质")
    if credit not in GOOD_CREDIT_LEVELS:
        reasons.append(f"信用等级「{credit}」未达良好标准")
    if contract_end < date.today():
        reasons.append(f"合同已于 {contract_end.isoformat()} 到期")

    if reasons:
        return {
            "eligible": False,
            "conclusion": CANNOT_ACCEPT,
            "credit": credit,
            "reasons": reasons,
        }
    return {
        "eligible": True,
        "conclusion": CAN_ACCEPT,
        "credit": credit,
        "reasons": [],
    }


class ClientEligibilityService:
    """按委托方编号取档案并给出接单结论，供三处调用方复用。"""

    def find_by_code(self, client_code: str) -> dict[str, Any] | None:
        """按委托方编号查询；同时兼容历史单据里存委托方名称的写法。"""
        key = str(client_code or "").strip()
        if not key:
            return None
        rows = store.rows(CLIENT_MODULE)
        for row in rows:
            if str(row.get(CLIENT_CODE_FIELD) or "").strip() == key:
                return row
        for row in rows:
            if str(row.get(CLIENT_NAME_FIELD) or "").strip() == key:
                return row
        return None

    def evaluate(self, client_code: str) -> dict[str, Any]:
        """以委托方编号取企业类别、信用等级、合同期限并给唯一结论。"""
        return evaluate_eligibility(self.find_by_code(client_code))

    def attach(self, client: dict[str, Any]) -> dict[str, Any]:
        """在档案副本上补接单结论，供列表/详情返回，不改动仓库原始数据。"""
        result = evaluate_eligibility(client)
        view = dict(client)
        view["接单资格"] = result["conclusion"]
        view["接单资格说明"] = "；".join(result["reasons"]) if result["reasons"] else ""
        return view


eligibility_service = ClientEligibilityService()
