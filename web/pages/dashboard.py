"""工单看板页面（读取 Elasticsearch 实时数据）"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from elasticsearch import Elasticsearch


def _es():
    return Elasticsearch(os.getenv("ES_HOST", "http://localhost:9200"))


@st.cache_data(ttl=30, show_spinner=False)
def _stats() -> dict:
    """统计各状态工单数量"""
    try:
        es = _es()
        agg = es.search(
            index="tickets",
            body={
                "size": 0,
                "aggs": {
                    "by_status": {"terms": {"field": "status"}},
                    "by_category": {"terms": {"field": "problem_type", "size": 10}},
                },
            },
        )
        by_status = {b["key"]: b["doc_count"] for b in agg["aggregations"]["by_status"]["buckets"]}
        by_category = {b["key"]: b["doc_count"] for b in agg["aggregations"]["by_category"]["buckets"]}
        created = by_status.get("已创建", 0) + by_status.get("open", 0) + by_status.get("created", 0)
        assigned = by_status.get("已委派", 0) + by_status.get("assigned", 0)
        resolved = by_status.get("已解决", 0) + by_status.get("closed", 0) + by_status.get("resolved", 0)
        return {
            "total": created + assigned + resolved,
            "created": created,
            "assigned": assigned,
            "resolved": resolved,
            "by_category": by_category,
        }
    except Exception:
        return {"total": 0, "created": 0, "assigned": 0, "resolved": 0, "by_category": {}}


@st.cache_data(ttl=30, show_spinner=False)
def _recent_tickets(limit: int = 10) -> list:
    """获取最近工单"""
    try:
        es = _es()
        r = es.search(
            index="tickets",
            body={
                "size": limit,
                "query": {"match_all": {}},
                "sort": [{"created_date": {"order": "desc", "missing": "_last"}}],
            },
        )
        return [h["_source"] for h in r["hits"]["hits"]]
    except Exception:
        return []


_STATUS_MAP = {
    "已创建": ("已创建", "open"),
    "已委派": ("已委派", "assigned"),
    "已解决": ("已解决", "closed"),
    "open": ("已创建", "open"),
    "created": ("已创建", "open"),
    "assigned": ("已委派", "assigned"),
    "closed": ("已解决", "closed"),
    "resolved": ("已解决", "closed"),
}
_URGENCY_MAP = {"高": "high", "中": "mid", "低": "low"}


def render():
    st.markdown("## 📊 工单看板")
    st.markdown('<div class="page-subtitle">实时工单概览与处理进度</div>', unsafe_allow_html=True)

    s = _stats()

    # ===== 指标卡 =====
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        (c1, "m-indigo", s["total"], "工单总量", "全部工单"),
        (c2, "m-amber", s["created"], "已创建", "等待派单"),
        (c3, "m-blue", s["assigned"], "已委派", "部门处理中"),
        (c4, "m-emerald", s["resolved"], "已解决", "已沉淀知识"),
    ]
    for col, cls, val, label, foot in cards:
        with col:
            st.markdown(
                f'<div class="metric-card {cls}">'
                f'<div class="m-label">{label}</div>'
                f'<div class="m-value">{val}</div>'
                f'<div class="m-foot">{foot}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("")

    left, right = st.columns([1.6, 1])

    # ===== 最近工单 =====
    with left:
        st.markdown("### 最近工单")
        tickets = _recent_tickets()
        if not tickets:
            st.info("暂无工单数据。可在「智能问答」中提交工单。")
        for t in tickets:
            status = t.get("status", "open")
            s_label, s_cls = _STATUS_MAP.get(status, ("待处理", "open"))
            urgency = t.get("urgency") or t.get("priority") or "中"
            u_cls = _URGENCY_MAP.get(urgency, "mid")
            group = t.get("assigned_to") or "未分配"
            ptype = t.get("problem_type") or t.get("category") or "其他"
            desc = (t.get("description") or "")[:60]

            st.markdown(
                f"""
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="font-weight:700; color:#0f172a; font-size:0.9rem;">{t.get('ticket_id','')}</span>
                            <span class="badge b-muted" style="margin-left:8px;">{ptype}</span>
                        </div>
                        <div>
                            <span class="badge b-{s_cls}"><span class="dot"></span>{s_label}</span>
                            <span class="badge b-{u_cls}" style="margin-left:6px;">{urgency}</span>
                        </div>
                    </div>
                    <div class="kb-body">{desc}</div>
                    <div class="kb-meta">处理组：{group}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ===== 分类分布 =====
    with right:
        st.markdown("### 问题类型分布")
        if s["by_category"]:
            import pandas as pd
            df = pd.DataFrame(
                {"类型": list(s["by_category"].keys()), "数量": list(s["by_category"].values())}
            ).sort_values("数量", ascending=True)
            st.bar_chart(df.set_index("类型"), height=300, color="#6366f1")
        else:
            st.info("暂无分类数据")

        st.markdown("### 处理状态")
        import pandas as pd
        status_df = pd.DataFrame(
            {
                "状态": ["已创建", "已委派", "已解决"],
                "数量": [s["created"], s["assigned"], s["resolved"]],
            }
        )
        st.bar_chart(status_df.set_index("状态"), height=200, color="#8b5cf6")
