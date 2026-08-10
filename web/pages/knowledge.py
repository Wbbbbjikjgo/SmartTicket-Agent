"""
知识检索页面
搜索知识库中的历史解决方案和 FAQ
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st


def render():
    """渲染知识检索页面"""
    st.markdown('<div class="main-header">🔍 知识检索</div>', unsafe_allow_html=True)
    st.caption("混合检索：BM25 关键词匹配 + 向量语义检索 + RRF 融合 + Rerank 精排")

    # 搜索框
    query = st.text_input("搜索知识", placeholder="输入问题描述，如：服务器502错误怎么处理？")

    if query:
        with st.spinner("正在检索..."):
            try:
                results = _search_knowledge(query)
                if results:
                    st.success(f"找到 {len(results)} 条相关知识")
                    for i, r in enumerate(results, 1):
                        with st.expander(f"[{i}] {r.get('title', '无标题')} (相关度: {r.get('score', 0):.3f})"):
                            st.markdown(f"**类别**: {r.get('category', '-')}")
                            st.markdown(f"**标签**: {', '.join(r.get('tags', []))}")
                            st.markdown(f"**内容**:\n{r.get('content', '')}")
                            if r.get("solution"):
                                st.markdown(f"**解决方案**:\n{r.get('solution', '')}")
                else:
                    st.warning("未找到相关知识，请尝试其他关键词。")
            except Exception as e:
                st.error(f"检索出错：{e}")

    # 热门知识
    st.markdown("---")
    st.subheader("📌 热门知识")

    hot_topics = [
        {"title": "502错误通用排查方案", "category": "系统故障", "views": 234},
        {"title": "手环X1续航问题排查指南", "category": "设备故障", "views": 189},
        {"title": "忘记密码重置流程", "category": "登录问题", "views": 156},
        {"title": "退款申请处理流程", "category": "财务问题", "views": 98},
    ]

    cols = st.columns(2)
    for i, topic in enumerate(hot_topics):
        with cols[i % 2]:
            st.markdown(f"**{topic['title']}**")
            st.caption(f"类别: {topic['category']} | 浏览: {topic['views']}次")


def _search_knowledge(query: str) -> list:
    """调用混合检索"""
    try:
        from retrieval.hybrid_search import HybridSearchPipeline
        pipeline = HybridSearchPipeline()
        results = pipeline.search(query, top_k=10)
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
    except ImportError:
        return [
            {
                "title": "502错误通用排查方案",
                "content": "502 Bad Gateway 通常由后端服务不可用引起。排查步骤：1.检查后端服务状态 2.检查Nginx配置 3.检查网络连接",
                "solution": "重启后端服务和Nginx，如频繁出现需考虑扩容",
                "category": "系统故障",
                "tags": ["502", "Nginx"],
                "score": 0.95,
            }
        ]
    except Exception as e:
        raise e
