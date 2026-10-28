"""知识库页面（检索 + 知识管理）"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from elasticsearch import Elasticsearch


def render():
    st.markdown("## 🔍 知识库")
    st.markdown('<div class="page-subtitle">混合检索 · 语义精排 · 知识沉淀</div>', unsafe_allow_html=True)

    tab_search, tab_manage = st.tabs(["知识检索", "知识管理"])

    with tab_search:
        _render_search()
    with tab_manage:
        _render_manage()


def _render_search():
    query = st.text_input(
        "搜索", placeholder="输入问题，如：服务器502错误怎么处理？",
        label_visibility="collapsed",
    )

    if query:
        with st.spinner("检索中..."):
            try:
                results = _search(query)
            except Exception:
                results = []

            if results:
                st.markdown(f'<div style="font-size:0.85rem; color:#64748b; margin:0.6rem 0;">找到 <b>{len(results)}</b> 条结果</div>', unsafe_allow_html=True)
                for i, r in enumerate(results, 1):
                    score = r.get("score", 0) or 0
                    color = "#10b981" if score > 0.8 else "#f59e0b" if score > 0.5 else "#94a3b8"
                    title = r.get("title") or "（无标题）"
                    content = (r.get("content") or "")[:220]
                    solution = r.get("solution") or ""
                    meta = " · ".join([x for x in [r.get("category"), ", ".join(r.get("tags", []))] if x])

                    st.markdown(
                        f"""
                        <div class="card">
                            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">
                                <div style="flex:1;">
                                    <div class="kb-title">{i}. {title}</div>
                                    <div class="kb-body">{content}</div>
                                </div>
                                <div class="score-chip" style="color:{color}; background:rgba({_hex_rgb(color)},0.12);">
                                    {(score * 100):.0f}%
                                </div>
                            </div>
                            {f'<div class="kb-solution"><b>💡 解决方案：</b>{solution}</div>' if solution else ""}
                            <div class="kb-meta">{meta}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.warning("未找到相关知识，换个关键词试试？")

    # 热门知识
    st.markdown("")
    st.markdown("### 📌 热门知识")
    try:
        hot = _list_knowledge(6)
    except Exception:
        hot = []
    if hot:
        c1, c2 = st.columns(2)
        for i, k in enumerate(hot):
            with c1 if i % 2 == 0 else c2:
                st.markdown(
                    f"""
                    <div class="card" style="padding:0.85rem 1rem;">
                        <div class="kb-title">📄 {k.get('title','')}</div>
                        <div class="kb-meta">{k.get('category','')} · {', '.join(k.get('tags',[]))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.info("暂无知识数据")


def _render_manage():
    st.caption("补充知识条目与 FAQ，自动写入本地知识源并向量化入库")

    CATEGORIES = ["登录问题", "系统故障", "网络异常", "设备故障", "财务问题", "其他"]

    # 新增知识
    with st.expander("➕ 新增知识条目", expanded=False):
        with st.form("add_knowledge_form"):
            title = st.text_input("标题", placeholder="如：502错误通用排查方案")
            c1, c2 = st.columns(2)
            with c1:
                category = st.selectbox("类别", CATEGORIES, key="kb_category")
            with c2:
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

    # 新增 FAQ
    with st.expander("➕ 新增 FAQ", expanded=False):
        with st.form("add_faq_form"):
            question = st.text_input("问题", placeholder="如：忘记密码怎么办？")
            answer = st.text_area("标准答案")
            f1, f2 = st.columns(2)
            with f1:
                category = st.selectbox("类别", CATEGORIES, key="faq_category")
            with f2:
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

    # 当前知识库
    st.markdown("### 📚 当前知识库")
    try:
        items = _list_knowledge(20)
        if items:
            for k in items:
                st.markdown(
                    f"""
                    <div class="card" style="padding:0.7rem 1rem;">
                        <div style="font-weight:700; color:#0f172a;">{k.get('title','')}</div>
                        <div class="kb-meta">{k.get('category','')} · {', '.join(k.get('tags',[]))} · {k.get('kb_id','')}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("知识库为空，请先初始化知识源（python data/ingestion/ingest_docs.py）或在上方补充知识。")
    except Exception:
        st.info("无法连接 ES，请确保 Elasticsearch 已启动。")


def _search(query: str) -> list:
    """调用混合检索管道"""
    from retrieval.hybrid_search import HybridSearchPipeline
    results = HybridSearchPipeline().search(query, top_k=10)
    out = []
    for r in results:
        src = r.get("source", {})
        out.append({
            "title": _title_of(src, r.get("content", "")),
            "content": r.get("content", ""),
            "solution": src.get("solution", "") or src.get("answer", "") or src.get("resolution", ""),
            "category": src.get("category", ""),
            "tags": src.get("tags", []),
            "score": r.get("rerank_score", r.get("score", 0)),
            "index": r.get("index", ""),
        })
    return out


def _title_of(src: dict, content: str) -> str:
    for f in ("title", "question", "description"):
        if src.get(f):
            return src[f]
    return (content or "")[:40]


def _add_knowledge(title, content, solution, category, tags):
    from data.ingestion.ingest_docs import add_knowledge
    return add_knowledge({
        "title": title,
        "content": content,
        "solution": solution,
        "category": category,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    })


def _add_faq(question, answer, category, tags):
    from data.ingestion.ingest_docs import add_faq
    return add_faq({
        "question": question,
        "answer": answer,
        "category": category,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    })


def _list_knowledge(limit: int = 20) -> list:
    es = Elasticsearch(os.getenv("ES_HOST", "http://localhost:9200"))
    resp = es.search(
        index="knowledge_base",
        body={"size": limit, "query": {"match_all": {}}, "sort": [{"create_date": {"order": "desc"}}]},
    )
    return [hit["_source"] for hit in resp["hits"]["hits"]]


def _hex_rgb(hex_color: str) -> str:
    """将 #rrggbb 转为 'r, g, b' 字符串，用于 rgba()"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r}, {g}, {b}"
