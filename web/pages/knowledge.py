"""知识检索页面"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st


def render():
    st.markdown("## 🔍 知识检索")

    tab_search, tab_manage = st.tabs(["知识检索", "知识管理"])

    with tab_search:
        _render_search()

    with tab_manage:
        _render_manage()


def _render_search():
    st.caption("BM25 + 向量语义 + RRF融合 + Rerank精排")

    # 搜索框
    query = st.text_input("", placeholder="输入问题，如：服务器502错误怎么处理？", label_visibility="collapsed")

    if query:
        with st.spinner("检索中..."):
            try:
                results = _search(query)
            except Exception:
                results = _fallback_results()

            if results:
                st.success(f"找到 {len(results)} 条结果")
                for i, r in enumerate(results, 1):
                    score = r.get("score", 0)
                    score_color = "#2e7d32" if score > 0.8 else "#f57f17" if score > 0.5 else "#999"

                    st.markdown(f"""
                    <div class="ticket-card">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:600; color:#333;">{i}. {r.get('title','')}</span>
                            <span style="font-size:0.8rem; color:{score_color}; font-weight:600;">{score:.2f}</span>
                        </div>
                        <div style="margin-top:6px; color:#555; font-size:0.9rem;">{r.get('content','')[:200]}</div>
                        {"<div style='margin-top:6px; padding:8px; background:#f0f7ff; border-radius:6px; font-size:0.85rem; color:#1565c0;'><b>💡 解决方案：</b>" + r.get('solution','') + "</div>" if r.get('solution') else ""}
                        <div style="margin-top:6px; font-size:0.75rem; color:#999;">{r.get('category','')} · {', '.join(r.get('tags',[]))}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("未找到相关知识，换个关键词试试？")

    # 热门知识
    st.markdown("")
    st.markdown("### 📌 热门知识")

    hot = [
        ("502错误通用排查方案", "系统故障", 234),
        ("手环X1续航问题排查指南", "设备故障", 189),
        ("忘记密码重置流程", "登录问题", 156),
        ("退款申请处理流程", "财务问题", 98),
    ]
    c1, c2 = st.columns(2)
    for i, (title, cat, views) in enumerate(hot):
        with c1 if i % 2 == 0 else c2:
            st.markdown(f"""
            <div class="ticket-card" style="padding:0.8rem 1rem;">
                <div style="font-weight:600; color:#333; font-size:0.9rem;">{title}</div>
                <div style="font-size:0.75rem; color:#999; margin-top:4px;">{cat} · {views} 次浏览</div>
            </div>
            """, unsafe_allow_html=True)


def _render_manage():
    st.caption("补充知识条目与 FAQ，自动写入本地知识源并向量化入库 ES")

    CATEGORIES = ["登录问题", "系统故障", "网络异常", "设备故障", "财务问题", "其他"]

    # ===== 新增知识 =====
    with st.expander("➕ 新增知识条目", expanded=False):
        with st.form("add_knowledge_form"):
            title = st.text_input("标题", placeholder="如：502错误通用排查方案")
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                category = st.selectbox("类别", CATEGORIES, key="kb_category")
            with c_col2:
                tags = st.text_input("标签（逗号分隔）", placeholder="如：502, Nginx")
            content = st.text_area("问题描述与排查过程", placeholder="问题现象与排查步骤")
            solution = st.text_area("解决方案", placeholder="标准解决方案")
            submitted = st.form_submit_button("提交知识")

        if submitted:
            if not title or not content:
                st.error("标题和问题描述为必填项")
            else:
                try:
                    kb_id = _add_knowledge(title, content, solution, category, tags)
                    st.success(f"知识已入库，编号：{kb_id}")
                except Exception as e:
                    st.error(f"入库失败：{e}")

    # ===== 新增 FAQ =====
    with st.expander("➕ 新增 FAQ", expanded=False):
        with st.form("add_faq_form"):
            question = st.text_input("问题", placeholder="如：忘记密码怎么办？")
            answer = st.text_area("标准答案")
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                category = st.selectbox("类别", CATEGORIES, key="faq_category")
            with f_col2:
                tags = st.text_input("标签（逗号分隔）", key="faq_tags", placeholder="如：密码, 重置")
            submitted = st.form_submit_button("提交 FAQ")

        if submitted:
            if not question or not answer:
                st.error("问题和答案为必填项")
            else:
                try:
                    faq_id = _add_faq(question, answer, category, tags)
                    st.success(f"FAQ 已入库，编号：{faq_id}")
                except Exception as e:
                    st.error(f"入库失败：{e}")

    # ===== 当前知识库列表 =====
    st.markdown("### 📚 当前知识库")
    try:
        items = _list_knowledge()
        if items:
            for k in items:
                st.markdown(f"""
                <div class="ticket-card" style="padding:0.7rem 1rem;">
                    <div style="font-weight:600; color:#333;">{k.get('title','')}</div>
                    <div style="font-size:0.78rem; color:#999; margin-top:4px;">{k.get('category','')} · {', '.join(k.get('tags',[]))}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("知识库为空，请先初始化知识源（python data/ingestion/ingest_docs.py）或在上方补充知识。")
    except Exception:
        st.info("无法连接 ES，请确保 Elasticsearch 已启动。")


def _search(query: str) -> list:
    """调用混合检索管道"""
    from retrieval.hybrid_search import HybridSearchPipeline
    results = HybridSearchPipeline().search(query, top_k=10)
    return [
        {
            "title": r.get("source", {}).get("title", ""),
            "content": r.get("content", ""),
            "solution": r.get("source", {}).get("solution", ""),
            "category": r.get("source", {}).get("category", ""),
            "tags": r.get("source", {}).get("tags", []),
            "score": r.get("rerank_score", r.get("score", 0)),
        }
        for r in results
    ]


def _add_knowledge(title: str, content: str, solution: str, category: str, tags: str) -> str:
    """新增知识条目到本地知识源 + ES"""
    from data.ingestion.ingest_docs import add_knowledge
    return add_knowledge({
        "title": title,
        "content": content,
        "solution": solution,
        "category": category,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    })


def _add_faq(question: str, answer: str, category: str, tags: str) -> str:
    """新增 FAQ 到本地知识源 + ES"""
    from data.ingestion.ingest_docs import add_faq
    return add_faq({
        "question": question,
        "answer": answer,
        "category": category,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    })


def _list_knowledge() -> list:
    """列出 ES 中的知识条目"""
    from elasticsearch import Elasticsearch
    es = Elasticsearch(os.getenv("ES_HOST", "http://localhost:9200"))
    resp = es.search(
        index="knowledge_base",
        body={"size": 20, "query": {"match_all": {}}, "sort": [{"create_date": {"order": "desc"}}]},
    )
    return [hit["_source"] for hit in resp["hits"]["hits"]]


def _fallback_results() -> list:
    """检索服务不可用时的兜底数据"""
    return [
        {"title": "502错误通用排查方案", "content": "502 Bad Gateway 通常由后端服务不可用引起。排查：1.检查后端状态 2.检查Nginx配置 3.检查网络", "solution": "重启后端服务和Nginx，频繁出现需扩容", "category": "系统故障", "tags": ["502","Nginx"], "score": 0.95},
        {"title": "忘记密码重置流程", "content": "点击登录页「忘记密码」链接，通过注册邮箱重置。邮箱无法访问请联系IT支持。", "solution": "通过注册邮箱重置密码", "category": "登录问题", "tags": ["密码","重置"], "score": 0.82},
    ]
