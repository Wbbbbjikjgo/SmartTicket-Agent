"""部门工作台：IT支持组 / 维修工程师 / 财务组 / 客服组

工单经 Kafka 推送到对应部门 Topic，本页面读取 ES 中的「已委派」工单；
人工处理时可调用 AI 生成建议回复，提交后状态变为「已解决」，
由 Kafka 消费者完成向量与知识库沉淀。
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from elasticsearch import Elasticsearch


@st.cache_resource
def _es():
    return Elasticsearch(os.getenv("ES_HOST", "http://localhost:9200"))


def _tickets(skill_group: str, statuses: list, limit: int = 50) -> list:
    from data.ingestion.ticket_service import list_tickets
    return list_tickets(
        skill_group=skill_group,
        statuses=statuses,
        limit=limit,
        es_client=_es(),
    )


def render():
    from data.ingestion.ticket_service import SKILL_GROUPS

    st.markdown("## 🏢 部门工作台")
    st.markdown(
        '<div class="page-subtitle">Kafka 工单分发 · 人工处理 · AI 辅助回复 · 解决后自动沉淀知识</div>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs([f"{g}" for g in SKILL_GROUPS])
    for group, tab in zip(SKILL_GROUPS, tabs):
        with tab:
            _render_group(group)


def _render_group(group: str):
    from data.ingestion.ticket_service import (
        STATUS_ASSIGNED, STATUS_RESOLVED, resolve_ticket, suggest_reply,
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        show_resolved = st.toggle("显示已解决工单", value=False, key=f"show_{group}")
    with col2:
        if st.button("🔄 刷新", key=f"refresh_{group}", use_container_width=True):
            st.rerun()

    statuses = [STATUS_ASSIGNED, STATUS_RESOLVED] if show_resolved else [STATUS_ASSIGNED]
    tickets = _tickets(group, statuses)

    if not tickets:
        st.info(
            f"{group} 暂无{'工单' if not show_resolved else '已解决工单'}。"
            "新工单派发后会通过 Kafka 进入本部门后台。"
        )
        return

    pending = sum(1 for t in tickets if t.get("status") == STATUS_ASSIGNED)
    st.caption(f"共 {len(tickets)} 单 · 待处理 {pending} 单")

    for t in tickets:
        ticket_id = t.get("ticket_id", "")
        status = t.get("status", STATUS_ASSIGNED)
        urgency = t.get("urgency") or t.get("priority") or "中"
        ptype = t.get("problem_type") or t.get("category") or "其他"
        desc = t.get("description") or ""
        icon = "🟡" if status == STATUS_ASSIGNED else "🟢"
        title = f"{icon} {ticket_id} · {ptype} · 紧急度 {urgency} · {desc[:32]}"

        with st.expander(title, expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**状态**：{status}")
            c2.markdown(f"**产品**：{t.get('product') or '未填写'}")
            c3.markdown(f"**创建时间**：{(t.get('created_at') or '')[:19]}")

            st.markdown(f"**问题描述**：{desc}")
            if t.get("assign_reason"):
                st.caption(f"派单理由：{t['assign_reason']}")

            if status == STATUS_ASSIGNED:
                if st.button("✨ AI 生成建议回复", key=f"ai_btn_{ticket_id}"):
                    with st.spinner("AI 正在生成客服回复..."):
                        suggestion = suggest_reply(t)
                    st.session_state[f"res_{ticket_id}"] = suggestion
                    st.rerun()

                resolution = st.text_area(
                    "解决方案（可先由 AI 生成再人工修改）",
                    key=f"res_{ticket_id}",
                    height=150,
                    placeholder="填写处理过程与最终解决方案...",
                )
                satisfaction = st.slider(
                    "客户满意度", 0.0, 1.0, 1.0, 0.1,
                    key=f"sat_{ticket_id}",
                )

                if st.button("✅ 标记已解决并沉淀知识", key=f"ok_{ticket_id}"):
                    if not (resolution or "").strip():
                        st.error("解决方案不能为空")
                    else:
                        with st.spinner("正在提交解决结果..."):
                            result = resolve_ticket(
                                ticket_id,
                                resolution,
                                satisfaction=satisfaction,
                                es_client=_es(),
                            )
                        if result.get("success"):
                            st.success(result.get("message", "已解决"))
                            st.session_state.pop(f"res_{ticket_id}", None)
                            st.rerun()
                        else:
                            st.error(result.get("message", "提交失败"))
            else:
                st.markdown(f"**解决方案**：{t.get('resolution') or '（空）'}")
                vector_state = "已沉淀" if t.get("vector_stored") else "待沉淀"
                kb_state = "已入库" if t.get("knowledge_settled") else "未入库"
                st.caption(
                    f"解决时间：{(t.get('resolved_at') or '')[:19]} · "
                    f"向量：{vector_state} · 知识库：{kb_state}"
                )
