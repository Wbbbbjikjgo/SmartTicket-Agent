"""智能问答页面"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st


@st.cache_resource
def _get_backend():
    """缓存 ES 客户端 / 检索管道，避免每次消息重复初始化"""
    from elasticsearch import Elasticsearch
    from retrieval.hybrid_search import HybridSearchPipeline

    es_client = Elasticsearch(os.getenv("ES_HOST", "http://localhost:9200"))
    search_pipeline = HybridSearchPipeline()
    return es_client, search_pipeline


def _run_agent(user_input: str) -> str:
    """运行多 Agent 协同流程（接入 ES 与检索管道）"""
    from agents.graph import MultiAgentOrchestrator
    es_client, search_pipeline = _get_backend()
    orchestrator = MultiAgentOrchestrator(
        es_client=es_client,
        search_pipeline=search_pipeline,
    )
    result = orchestrator.run(user_input)
    return result.get("response", "已收到您的请求。")


WELCOME = (
    "你好，我是智能工单助手 👋\n\n"
    "我可以帮你：\n"
    "- 📝 **报告问题** — 自动创建工单并派发\n"
    "- 🔍 **查询工单** — 查看处理进度\n"
    "- 📚 **搜索知识** — 查找历史解决方案\n"
    "- 👤 **转人工** — 转接专业工程师\n\n"
    "点击下方快捷入口，或直接描述你的问题。"
)

SUGGESTIONS = [
    "报告一个问题",
    "查询工单进度",
    "查找解决方案",
    "转接专业工程师",
]


def render():
    st.markdown("## 💬 智能问答")
    st.markdown('<div class="page-subtitle">报告问题 · 查询进度 · 搜索方案</div>', unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": WELCOME}]

    # 历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 快捷入口
    if len(st.session_state.messages) <= 1:
        cols = st.columns(len(SUGGESTIONS))
        for i, s in enumerate(SUGGESTIONS):
            if cols[i].button(s, use_container_width=True, key=f"sug_{i}"):
                st.session_state.messages.append({"role": "user", "content": s})
                with st.chat_message("user"):
                    st.markdown(s)
                with st.chat_message("assistant"):
                    with st.spinner("思考中..."):
                        response = _run_agent(s)
                    st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()

    # 输入框
    if prompt := st.chat_input("描述你的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    response = _run_agent(prompt)
                except ImportError:
                    response = f"收到：「{prompt}」\n\n> Agent 依赖未安装，请运行 `pip install -r requirements.txt`"
                except Exception as e:
                    response = f"处理出错：{e}"

            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

    # 清空
    if st.sidebar.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = [{"role": "assistant", "content": WELCOME}]
        st.rerun()
