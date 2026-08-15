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

st.set_page_config(
    page_title="智能工单系统",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== 全局样式 ==========
st.markdown("""
<style>
    /* ---------- 基础 ---------- */
    :root {
        --brand: #6366f1;
        --brand2: #8b5cf6;
        --ink: #1e293b;
        --muted: #64748b;
        --line: #e2e8f0;
        --bg: #f8fafc;
    }
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                     "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    }
    #MainMenu, footer, header[data-testid="stHeader"] {visibility: hidden; height: 0;}

    /* 主内容区 */
    .main .block-container {
        padding-top: 1.6rem;
        padding-bottom: 3rem;
        max-width: 1180px;
    }

    /* ---------- 标题 ---------- */
    h1 {font-size: 1.7rem !important; font-weight: 800; color: var(--ink); letter-spacing: -0.02em;}
    h2 {font-size: 1.25rem !important; font-weight: 700; color: var(--ink); letter-spacing: -0.01em;}
    h3 {font-size: 1.02rem !important; font-weight: 700; color: var(--ink);}

    .page-subtitle {color: var(--muted); font-size: 0.9rem; margin-top: -0.5rem; margin-bottom: 1.2rem;}

    /* ---------- 侧边栏 ---------- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e1b4b 100%);
        border-right: none;
    }
    section[data-testid="stSidebar"] * {color: #cbd5e1 !important;}
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 {color: #fff !important;}

    .brand {
        display: flex; align-items: center; gap: 0.55rem;
        padding: 0.35rem 0.2rem 0.9rem;
        font-size: 1.12rem; font-weight: 800; color: #fff !important; letter-spacing: -0.01em;
    }
    .brand .logo {
        width: 34px; height: 34px; border-radius: 10px;
        background: linear-gradient(135deg, #6366f1, #a855f7);
        display: inline-flex; align-items: center; justify-content: center; font-size: 1.05rem;
        box-shadow: 0 6px 16px rgba(99,102,241,0.45);
    }

    /* 导航 radio 美化 */
    section[data-testid="stSidebar"] [data-testid="stRadio"] > label {
        display: flex; align-items: center;
        padding: 0.62rem 0.8rem; border-radius: 11px; margin: 0.18rem 0;
        transition: background 0.18s ease; cursor: pointer;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] > label:hover {
        background: rgba(255,255,255,0.07);
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] > label:has(input:checked) {
        background: rgba(99,102,241,0.28);
        box-shadow: inset 0 0 0 1px rgba(139,92,246,0.55);
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stMarkdownContainer"] p {
        font-weight: 600;
    }

    /* ---------- 卡片 ---------- */
    .card {
        background: #fff; border: 1px solid var(--line); border-radius: 16px;
        padding: 1.1rem 1.3rem; margin: 0.55rem 0;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 8px 24px rgba(15,23,42,0.04);
        transition: transform 0.16s ease, box-shadow 0.16s ease;
    }
    .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(15,23,42,0.06), 0 18px 40px rgba(15,23,42,0.09);
    }

    /* ---------- 指标卡 ---------- */
    .metric-card {
        border-radius: 16px; padding: 1.15rem 1.25rem; color: #fff;
        box-shadow: 0 10px 24px rgba(15,23,42,0.14);
        min-height: 108px; display: flex; flex-direction: column; justify-content: space-between;
    }
    .metric-card .m-label {font-size: 0.8rem; opacity: 0.92; font-weight: 600; letter-spacing: 0.02em;}
    .metric-card .m-value {font-size: 2.1rem; font-weight: 800; line-height: 1.1; letter-spacing: -0.02em;}
    .metric-card .m-foot {font-size: 0.72rem; opacity: 0.85; margin-top: 0.3rem;}
    .m-indigo {background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);}
    .m-blue   {background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%);}
    .m-amber  {background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);}
    .m-emerald{background: linear-gradient(135deg, #10b981 0%, #22c55e 100%);}

    /* ---------- 状态徽章 ---------- */
    .badge {
        display: inline-flex; align-items: center; gap: 0.3rem;
        padding: 2px 11px; border-radius: 999px; font-size: 0.72rem; font-weight: 700;
    }
    .badge .dot {width: 6px; height: 6px; border-radius: 50%; background: currentColor;}
    .b-open    {background: #fef3c7; color: #b45309;}
    .b-assigned{background: #dbeafe; color: #1d4ed8;}
    .b-closed  {background: #d1fae5; color: #047857;}
    .b-high    {background: #fee2e2; color: #b91c1c;}
    .b-mid     {background: #fef3c7; color: #b45309;}
    .b-low     {background: #d1fae5; color: #047857;}
    .b-muted   {background: #f1f5f9; color: #64748b;}

    /* ---------- 知识卡片 ---------- */
    .kb-title {font-weight: 700; color: var(--ink); font-size: 0.98rem;}
    .kb-body  {color: #475569; font-size: 0.88rem; margin-top: 6px; line-height: 1.55;}
    .kb-solution {margin-top: 8px; padding: 10px 12px; background: #eef2ff; border-radius: 10px;
                   font-size: 0.85rem; color: #4338ca; line-height: 1.5;}
    .kb-solution b {color: #3730a3;}
    .kb-meta {font-size: 0.72rem; color: var(--muted); margin-top: 8px;}
    .score-chip {
        font-weight: 800; font-size: 0.78rem; padding: 2px 9px; border-radius: 999px;
    }

    /* ---------- 聊天 ---------- */
    [data-testid="stChatMessage"] {
        background: #fff; border: 1px solid var(--line); border-radius: 16px;
        padding: 0.75rem 1rem; margin: 0.5rem 0; box-shadow: 0 1px 2px rgba(15,23,42,0.03);
    }
    [data-testid="stChatInput"] textarea {border-radius: 14px;}

    /* ---------- 表单/按钮 ---------- */
    .stButton > button, .stFormSubmitButton > button {
        border-radius: 10px; font-weight: 600; border: none;
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        color: #fff; padding: 0.5rem 1.2rem;
        box-shadow: 0 6px 16px rgba(99,102,241,0.3);
        transition: all 0.16s ease;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover {
        transform: translateY(-1px); box-shadow: 0 10px 22px rgba(99,102,241,0.4);
    }
    [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
    [data-testid="stSelectbox"] [data-baseweb="select"] {
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# ========== 侧边栏导航 ==========
with st.sidebar:
    st.markdown('<div class="brand"><span class="logo">🎫</span>智能工单系统</div>', unsafe_allow_html=True)
    st.markdown("---")
    page = st.radio(
        "导航",
        ["📊 工单看板", "💬 智能问答", "🔍 知识库"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.markdown(
        '<div style="font-size:0.72rem; opacity:0.6; line-height:1.6;">'
        'DeepSeek · LangGraph<br>Elasticsearch · Kafka</div>',
        unsafe_allow_html=True,
    )

# ========== 路由 ==========
if page == "📊 工单看板":
    from web.pages.dashboard import render; render()
elif page == "💬 智能问答":
    from web.pages.chat import render; render()
elif page == "🔍 知识库":
    from web.pages.knowledge import render; render()
