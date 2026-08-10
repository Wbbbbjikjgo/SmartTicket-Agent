"""
Streamlit 主入口
智能工单系统前端
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

# 页面配置
st.set_page_config(
    page_title="智能工单系统",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义样式
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# 侧边栏
st.sidebar.title("🎫 智能工单系统")
st.sidebar.markdown("---")

# 导航
page = st.sidebar.radio(
    "功能导航",
    ["📊 工单看板", "💬 智能问答", "🔍 知识检索"],
)

# 路由
if page == "📊 工单看板":
    from web.pages.dashboard import render
    render()
elif page == "💬 智能问答":
    from web.pages.chat import render
    render()
elif page == "🔍 知识检索":
    from web.pages.knowledge import render
    render()

# 底部信息
st.sidebar.markdown("---")
st.sidebar.caption("基于 DeepSeek + LangGraph + Elasticsearch")
st.sidebar.caption("国产化方案 | DashScope Embedding/Rerank")
