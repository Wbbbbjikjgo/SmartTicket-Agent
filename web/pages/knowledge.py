"""知识检索页面"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st


def render():
    st.markdown("## 🔍 知识检索")
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


def _fallback_results() -> list:
    """检索服务不可用时的兜底数据"""
    return [
        {"title": "502错误通用排查方案", "content": "502 Bad Gateway 通常由后端服务不可用引起。排查：1.检查后端状态 2.检查Nginx配置 3.检查网络", "solution": "重启后端服务和Nginx，频繁出现需扩容", "category": "系统故障", "tags": ["502","Nginx"], "score": 0.95},
        {"title": "忘记密码重置流程", "content": "点击登录页「忘记密码」链接，通过注册邮箱重置。邮箱无法访问请联系IT支持。", "solution": "通过注册邮箱重置密码", "category": "登录问题", "tags": ["密码","重置"], "score": 0.82},
    ]
