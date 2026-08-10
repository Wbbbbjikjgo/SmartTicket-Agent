"""
工单看板页面
展示工单统计、列表和详情
"""
import streamlit as st
import json
from datetime import datetime


def render():
    """渲染工单看板"""
    st.markdown('<div class="main-header">📊 工单看板</div>', unsafe_allow_html=True)

    # 统计卡片
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("今日新增工单", "12", "+3")
    with col2:
        st.metric("待处理", "5", "-2")
    with col3:
        st.metric("处理中", "4", "+1")
    with col4:
        st.metric("已关闭", "3", "+1")

    st.markdown("---")

    # 工单列表
    st.subheader("最近工单")

    # 模拟数据（生产环境从 ES 获取）
    sample_tickets = [
        {
            "ticket_id": "GD202604240001",
            "problem_type": "登录问题",
            "description": "用户输入正确密码后仍提示认证失败",
            "urgency": "中",
            "status": "closed",
            "assigned_to": "IT支持组",
            "created_at": "2026-04-24 09:30",
        },
        {
            "ticket_id": "GD202604240002",
            "problem_type": "系统故障",
            "description": "服务器返回502错误，持续约30分钟",
            "urgency": "高",
            "status": "assigned",
            "assigned_to": "IT支持组",
            "created_at": "2026-04-24 10:15",
        },
        {
            "ticket_id": "GD202604240003",
            "problem_type": "设备故障",
            "description": "手环X1充满电后待机不到24小时自动关机",
            "urgency": "中",
            "status": "open",
            "assigned_to": None,
            "created_at": "2026-04-24 11:00",
        },
    ]

    # 状态颜色映射
    status_colors = {"open": "🔴", "assigned": "🟡", "closed": "🟢"}

    for ticket in sample_tickets:
        with st.expander(
            f"{status_colors.get(ticket['status'], '⚪')} "
            f"[{ticket['ticket_id']}] {ticket['problem_type']} - {ticket['description'][:30]}..."
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**工单号**: {ticket['ticket_id']}")
                st.write(f"**问题类型**: {ticket['problem_type']}")
                st.write(f"**紧急程度**: {ticket['urgency']}")
                st.write(f"**状态**: {ticket['status']}")
            with col2:
                st.write(f"**描述**: {ticket['description']}")
                st.write(f"**派发给**: {ticket['assigned_to'] or '未分配'}")
                st.write(f"**创建时间**: {ticket['created_at']}")

    # 工单趋势图
    st.markdown("---")
    st.subheader("工单趋势（近7天）")
    chart_data = {
        "日期": ["04-18", "04-19", "04-20", "04-21", "04-22", "04-23", "04-24"],
        "新增": [8, 12, 6, 15, 10, 9, 12],
        "关闭": [7, 10, 8, 12, 11, 8, 3],
    }
    st.bar_chart(chart_data, x="日期")
