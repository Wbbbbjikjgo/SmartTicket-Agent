"""工单看板页面"""
import streamlit as st


def render():
    st.markdown("## 📊 工单看板")
    
    # ===== 统计卡片 =====
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        ("12", "今日新增", ""),
        ("5", "待处理", "orange"),
        ("4", "处理中", "blue"),
        ("3", "已关闭", "green"),
    ]
    for col, (val, label, color) in zip([c1, c2, c3, c4], cards):
        with col:
            cls = f" {color}" if color else ""
            st.markdown(f'<div class="metric-card{cls}"><div class="value">{val}</div><div class="label">{label}</div></div>', unsafe_allow_html=True)
    
    st.markdown("")  # 间距
    
    # ===== 工单列表 =====
    st.markdown("### 最近工单")
    
    tickets = [
        {"id": "GD202604240001", "type": "登录问题", "desc": "用户输入正确密码后仍提示认证失败", "urgency": "中", "status": "closed", "group": "IT支持组", "time": "09:30"},
        {"id": "GD202604240002", "type": "系统故障", "desc": "服务器返回502错误，持续约30分钟", "urgency": "高", "status": "assigned", "group": "IT支持组", "time": "10:15"},
        {"id": "GD202604240003", "type": "设备故障", "desc": "手环X1充满电后待机不到24小时自动关机", "urgency": "中", "status": "open", "group": None, "time": "11:00"},
    ]
    
    status_map = {"open": ("待处理", "open"), "assigned": ("处理中", "assigned"), "closed": ("已关闭", "closed")}
    urgency_map = {"高": "high", "中": "mid", "低": "low"}
    
    for t in tickets:
        s_label, s_cls = status_map[t["status"]]
        u_cls = urgency_map.get(t["urgency"], "mid")
        
        st.markdown(f"""
        <div class="ticket-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="font-weight:600; color:#333;">[{t['id']}]</span>
                    <span style="margin-left:8px; color:#555;">{t['desc']}</span>
                </div>
                <div>
                    <span class="tag tag-{s_cls}">{s_label}</span>
                    <span class="tag tag-{u_cls}" style="margin-left:6px;">{t['urgency']}</span>
                </div>
            </div>
            <div style="margin-top:8px; font-size:0.8rem; color:#999;">
                {t['type']} · {t['group'] or '未分配'} · {t['time']}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ===== 趋势图 =====
    st.markdown("")
    st.markdown("### 近 7 天趋势")
    import pandas as pd
    df = pd.DataFrame({
        "日期": ["04-18","04-19","04-20","04-21","04-22","04-23","04-24"],
        "新增": [8, 12, 6, 15, 10, 9, 12],
        "关闭": [7, 10, 8, 12, 11, 8, 3],
    })
    st.bar_chart(df.set_index("日期"), color=["#667eea", "#38ef7d"], height=250)
