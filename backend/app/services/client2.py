"""委托方管理业务规则：状态流转、字段校验与筛选口径都收在这里。

档案列表与详情里的接单资格都取自 services.client_eligibility 的唯一结论，
本模块只做挂载，不另写判断。
"""
from __future__ import annotations

from typing import Any

from app.services.client_eligibility import assess_client
from app.store import store

MODULE = "client2"
REQUIRED_FIELDS = ["委托方编号", "委托方名称", "企业类别"]
STATUS_ORDER = ["潜在客户", "合作中", "合同到期", "已终止"]
ACTION_RULES = {"签订合约": "合作中", "续约": "合作中", "终止合作": "已终止"}
NEGATIVE_ACTIONS = []


def with_eligibility(row: dict[str, Any]) -> dict[str, Any]:
    """在档案副本上挂载共用的接单结论；只挂展示字段，绝不回写档案数据。"""
    view = dict(row)
    result = assess_client(str(row.get("委托方编号") or ""))
    view["接单结论"] = result["接单结论"]
    view["可接单"] = result["可接单"]
    view["判定原因"] = result["判定原因"]
    return view


class Client2Service:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("委托方编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [with_eligibility(row) for row in page_rows], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return with_eligibility(row)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"委托方 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于委托方管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"委托方已{action}"
