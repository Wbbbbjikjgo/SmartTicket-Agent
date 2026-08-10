"""智能问答页面"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st


def render():
    st.markdown("## 💬 智能问答")
    st.caption("报告问题自动创建工单 · 查询进度 · 搜索解决方案")
    
    # 初始化会话状态
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "你好！我是智能工单助手。\n\n你可以：\n- 📝 **报告问题** — 自动创建工单并派发\n- 🔍 **查询工单** — 查看处理进度\n- 📚 **搜索知识** — 查找历史解决方案\n- 👤 **转人工** — 转接专业工程师"}
        ]
    
    # 显示历史
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    # 输入框
    if prompt := st.chat_input("描述你的问题..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                try:
                    from agents.graph import MultiAgentOrchestrator
                    result = MultiAgentOrchestrator().run(prompt)
                    response = result.get("response", "已收到您的请求。")
                except ImportError:
                    response = f"收到：「{prompt}」\n\n> Agent 依赖未安装，请运行 `pip install -r requirements.txt`"
                except Exception as e:
                    response = f"处理出错：{e}"
            
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
    
    # 清空按钮
    if st.sidebar.button("🗑️ 清空对话"):
        st.session_state.messages = st.session_state.messages[:1]
        st.rerun()
