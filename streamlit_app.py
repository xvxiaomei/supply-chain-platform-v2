import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

# 页面配置
st.set_page_config(
    page_title="供应链系统使用度分析平台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 导入 Supabase 工具
from utils.supabase_client import (
    get_systems, get_system_usage_summary, get_menu_details,
    get_quarters, import_data_to_supabase
)

# 初始化 session state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'role' not in st.session_state:
    st.session_state.role = None

# 用户验证
USERS = {
    'admin': {'password': 'admin123', 'role': 'admin', 'name': '管理员'},
    'viewer': {'password': 'viewer123', 'role': 'viewer', 'name': '查看者'}
}


def login_page():
    st.title("📊 供应链系统使用度分析平台")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 用户登录")
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")

        if st.button("登录", use_container_width=True):
            if username in USERS and USERS[username]['password'] == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = USERS[username]['role']
                st.session_state.name = USERS[username]['name']
                st.rerun()
            else:
                st.error("用户名或密码错误")

        st.markdown("---")
        st.caption("演示账号：admin / admin123  |  viewer / viewer123")


def dashboard_page():
    st.title("📊 供应链系统使用度分析平台")
    st.markdown(f"### 欢迎回来，{st.session_state.name}！")
    st.markdown("以下是各系统使用情况的分析数据")
    st.markdown("---")

    with st.sidebar:
        st.markdown("## 🔍 数据筛选")
        quarters = get_quarters()
        quarter_options = ["全部季度"] + quarters
        selected_quarter = st.selectbox("选择季度", quarter_options)

        st.markdown("---")
        st.markdown(f"**当前用户：** {st.session_state.username}")
        st.markdown(f"**角色：** {st.session_state.role}")
        if st.button("退出登录"):
            st.session_state.logged_in = False
            st.rerun()

    quarter = None if selected_quarter == "全部季度" else selected_quarter
    systems_data = get_system_usage_summary(quarter)

    if not systems_data:
        st.info("暂无数据，请先在数据导入页面导入数据")
        return

    # 关键指标
    col1, col2, col3, col4 = st.columns(4)
    total_clicks = sum(s['total_clicks'] for s in systems_data)
    total_views = sum(s['total_views'] for s in systems_data)
    avg_cp = round(total_clicks / total_views, 2) if total_views > 0 else 0
    high_usage_count = sum(1 for s in systems_data if s['usage_score'] >= 80)

    with col1:
        st.metric("总点击量", f"{total_clicks:,}")
    with col2:
        st.metric("总浏览量", f"{total_views:,}")
    with col3:
        st.metric("平均 C/P 值", avg_cp)
    with col4:
        st.metric("高使用度系统", f"{high_usage_count}/{len(systems_data)}")

    st.markdown("---")

    # 图表
    col1, col2 = st.columns(2)
    df = pd.DataFrame(systems_data)

    with col1:
        st.subheader("📊 各系统点击量对比")
        fig = px.bar(df, x='system_name', y='total_clicks', color='category',
                     title="系统点击量对比", text='total_clicks')
        fig.update_traces(texttemplate='%{text:,}', textposition='outside')
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("📈 使用度评分")
        fig = px.bar(df, x='system_name', y='usage_score', color='usage_level',
                     title="系统使用度评分", range_y=[0, 100])
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    # 数据表格
    st.markdown("---")
    st.subheader("📋 系统详细数据")

    display_df = df[[
        'system_name', 'category', 'total_clicks', 'total_views',
        'click_view_ratio', 'menu_count', 'usage_score', 'usage_level_text'
    ]].rename(columns={
        'system_name': '系统名称',
        'category': '所属领域',
        'total_clicks': '总点击量',
        'total_views': '总浏览量',
        'click_view_ratio': 'C/P值',
        'menu_count': '菜单数量',
        'usage_score': '使用度评分',
        'usage_level_text': '使用度等级'
    })

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # 菜单详情
    st.markdown("---")
    st.subheader("📋 菜单使用详情分析")

    systems_list = get_systems()
    system_options = {s['system_code']: f"{s['system_code']} - {s['system_name']}" for s in systems_list}
    selected_system = st.selectbox("选择系统", list(system_options.keys()), format_func=lambda x: system_options[x])

    if selected_system:
        menu_data = get_menu_details(selected_system, quarter)

        if menu_data:
            col1, col2 = st.columns([1, 3])
            with col1:
                rank_type = st.radio("排名类型", ["前N名", "后N名"], horizontal=True)
                rank_count = st.slider("显示数量", 5, 30, 10)

            sorted_data = sorted(menu_data, key=lambda x: x['click_count'], reverse=True)
            if rank_type == "前N名":
                display_data = sorted_data[:rank_count]
            else:
                display_data = sorted_data[-rank_count:][::-1]

            col1, col2 = st.columns(2)
            click_df = pd.DataFrame(display_data)

            with col1:
                st.markdown("#### 点击量漏斗图")
                fig = px.funnel(click_df, x='click_count', y='menu_name', title="菜单点击量分布")
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("#### 浏览量漏斗图")
                fig = px.funnel(click_df, x='page_view', y='menu_name', title="菜单浏览量分布")
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### 菜单详细数据")
            menu_df = click_df.rename(columns={
                'menu_name': '菜单名称',
                'click_count': '点击量',
                'page_view': '浏览量',
                'ratio': 'C/P值'
            })
            st.dataframe(menu_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"暂无 {system_options[selected_system]} 的菜单数据")


def import_page():
    st.title("📤 数据导入")
    st.markdown("---")

    if st.session_state.role != 'admin':
        st.error("权限不足！只有管理员可以导入数据")
        return

    st.markdown("### 导入说明")
    st.info("""
    **导入格式要求：**
    - 文件格式：Excel (.xlsx, .xls) 或 CSV
    - 必须包含以下列：`system_code`, `menu_name`, `click_count`, `page_view`
    - `system_code` 可选值：WMS, IMS, SCM, SRM, TMS, QMS
    """)

    col1, col2 = st.columns(2)

    with col1:
        quarter = st.text_input("季度标识", placeholder="例: 2025Q1")

    with col2:
        uploaded_file = st.file_uploader("选择文件", type=['xlsx', 'xls', 'csv'])

    if uploaded_file and quarter:
        if st.button("开始导入", type="primary"):
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)

                required_cols = ['system_code', 'menu_name', 'click_count', 'page_view']
                missing_cols = [col for col in required_cols if col not in df.columns]
                if missing_cols:
                    st.error(f"缺少列: {missing_cols}")
                else:
                    with st.spinner("正在导入数据..."):
                        success, fail = import_data_to_supabase(df, quarter)
                        if success > 0:
                            st.success(f"✅ 导入完成！成功: {success}, 失败: {fail}")
                        else:
                            st.error("导入失败，请检查文件格式")
            except Exception as e:
                st.error(f"导入失败: {e}")

    st.markdown("---")
    st.markdown("### 📥 下载导入模板")

    template_data = {
        'system_code': ['WMS', 'WMS', 'SRM', 'TMS', 'QMS'],
        'menu_name': ['入库管理', '出库管理', '订单确认', '在途跟踪', '质量检验'],
        'click_count': [15000, 12000, 8000, 5000, 3000],
        'page_view': [5000, 4000, 3500, 4200, 2500]
    }
    template_df = pd.DataFrame(template_data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        template_df.to_excel(writer, sheet_name='导入模板', index=False)

    st.download_button(
        label="下载模板文件",
        data=output.getvalue(),
        file_name="数据导入模板.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def account_page():
    st.title("👥 账号管理")
    st.markdown("---")

    if st.session_state.role != 'admin':
        st.error("权限不足！只有管理员可以管理账号")
        return

    st.info("当前为演示版本，账号管理功能后续完善")

    st.markdown("### 当前用户列表")
    users_df = pd.DataFrame([
        {"用户名": "admin", "角色": "管理员", "状态": "激活"},
        {"用户名": "viewer", "角色": "查看者", "状态": "激活"}
    ])
    st.dataframe(users_df, use_container_width=True, hide_index=True)


def main():
    if not st.session_state.logged_in:
        login_page()
    else:
        with st.sidebar:
            st.markdown("# 📊 供应链分析平台")
            st.markdown("---")
            page = st.radio(
                "导航菜单",
                ["📈 仪表板", "📤 数据导入", "👥 账号管理"],
                index=0
            )
            st.markdown("---")
            st.caption(f"当前用户: {st.session_state.username}")
            st.caption(f"角色: {st.session_state.role}")

        if page == "📈 仪表板":
            dashboard_page()
        elif page == "📤 数据导入":
            import_page()
        elif page == "👥 账号管理":
            account_page()


if __name__ == "__main__":
    main()