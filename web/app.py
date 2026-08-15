"""
智能工单系统 - Streamlit 前端主入口
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载 .env 环境变量（API Key 等），必须在导入业务模块之前执行
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st

# ========== 页面配置 ==========
st.set_page_config(page_title="智能工单系统", page_icon="🎫", layout="wide")

# ========== 全局样式 ==========
st.markdown("""
<style>
    /* 隐藏 Streamlit 默认元素 */
    #MainMenu, footer, header {visibility: hidden;}
    
    /* 主容器 */
    .main .block-container {padding-top: 2rem; max-width: 1100px;}
    
    /* 标题 */
    h1 {font-size: 1.8rem !important; font-weight: 700; color: #1a1a2e; margin-bottom: 0.5rem;}
    h2 {font-size: 1.3rem !important; font-weight: 600; color: #16213e;}
    
    /* 指标卡片 */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px; padding: 1.2rem; color: white; text-align: center;
        box-shadow: 0 4px 15px rgba(102,126,234,0.3);
    }
    .metric-card .value {font-size: 2rem; font-weight: 700;}
    .metric-card .label {font-size: 0.85rem; opacity: 0.9;}
    
    .metric-card.green {background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); box-shadow: 0 4px 15px rgba(17,153,142,0.3);}
    .metric-card.orange {background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); box-shadow: 0 4px 15px rgba(245,87,108,0.3);}
    .metric-card.blue  {background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); box-shadow: 0 4px 15px rgba(79,172,254,0.3);}
    
    /* 工单卡片 */
    .ticket-card {
        background: #fff; border: 1px solid #e8e8e8; border-radius: 10px;
        padding: 1rem 1.2rem; margin: 0.5rem 0;
        transition: all 0.2s; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .ticket-card:hover {box-shadow: 0 4px 16px rgba(0,0,0,0.1); transform: translateY(-1px);}
    
    /* 状态标签 */
    .tag {display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;}
    .tag-open {background: #fff3e0; color: #e65100;}
    .tag-assigned {background: #e3f2fd; color: #1565c0;}
    .tag-closed {background: #e8f5e9; color: #2e7d32;}
    .tag-high {background: #fce4ec; color: #c62828;}
    .tag-mid {background: #fff8e1; color: #f57f17;}
    .tag-low {background: #f1f8e9; color: #558b2f;}
    
    /* 侧边栏 */
    .css-1d391kg {background: #f8f9fa;}
    div[data-testid="stSidebar"] {background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);}
    div[data-testid="stSidebar"] * {color: #e0e0e0 !important;}
    
    /* 聊天消息 */
    .stChatMessage {padding: 0.5rem 0;}
</style>
""", unsafe_allow_html=True)

# ========== 侧边栏导航 ==========
with st.sidebar:
    st.markdown("## 🎫 智能工单系统")
    st.markdown("---")
    page = st.radio(
        "导航",
        ["📊 工单看板", "💬 智能问答", "🔍 知识检索"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("DeepSeek · LangGraph · Elasticsearch")

# ========== 路由 ==========
if page == "📊 工单看板":
    from web.pages.dashboard import render; render()
elif page == "💬 智能问答":
    from web.pages.chat import render; render()
elif page == "🔍 知识检索":
    from web.pages.knowledge import render; render()
