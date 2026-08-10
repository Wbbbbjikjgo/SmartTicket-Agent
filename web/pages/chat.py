"""
智能问答页面
对话式工单处理（创建/查询/知识检索）
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st


def render():
    """渲染智能问答页面"""
    st.markdown('<div class="main-header">💬 智能问答</div>', unsafe_allow_html=True)
    st.caption("输入您的问题，AI 将自动识别意图并处理（创建工单/查询状态/检索知识）")

    # 初始化会话状态
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "您好！我是智能工单助手。请问有什么可以帮您？\n\n您可以：\n- 📝 报告问题（自动创建工单）\n- 🔍 查询工单状态\n- 📚 搜索解决方案\n- 👤 转接人工客服",
            }
        ]

    # 显示历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 用户输入
    if prompt := st.chat_input("请输入您的问题..."):
        # 添加用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 调用 Agent 处理
        with st.chat_message("assistant"):
            with st.spinner("正在处理..."):
                try:
                    response = _process_input(prompt)
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                except Exception as e:
                    error_msg = f"抱歉，处理您的请求时出现错误：{e}"
                    st.markdown(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})

    # 侧边功能
    st.sidebar.markdown("---")
    if st.sidebar.button("🗑️ 清空对话"):
        st.session_state.messages = []
        st.rerun()


def _process_input(user_input: str) -> str:
    """处理用户输入，调用多 Agent 编排"""
    try:
        from agents.graph import MultiAgentOrchestrator
        orchestrator = MultiAgentOrchestrator()
        result = orchestrator.run(user_input)
        return result.get("response", "已收到您的请求。")
    except ImportError:
        # 如果依赖未安装，返回提示
        return (
            f"已收到您的输入：「{user_input}」\n\n"
            "⚠️ Agent 系统依赖尚未安装，请先运行 `pip install -r requirements.txt`"
        )
    except Exception as e:
        return f"处理出错：{e}"
