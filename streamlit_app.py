import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
import requests
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 页面配置
st.set_page_config(
    page_title="供应链系统使用度分析平台",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Supabase 配置
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://pluynxzhrtndpxdfkoak.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

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


# ============ 数据库操作函数 ============
def get_systems():
    """获取系统列表"""
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/systems?select=*&order=sort_order.asc",
            headers=SUPABASE_HEADERS,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"获取系统列表失败: {e}")
        return []


def get_system_usage_summary(quarter=None):
    """获取系统使用汇总"""
    try:
        systems = get_systems()
        if not systems:
            return []

        if quarter:
            url = f"{SUPABASE_URL}/rest/v1/quarterly_usage?select=system_code,click_count,page_view,menu_name&quarter=eq.{quarter}"
        else:
            url = f"{SUPABASE_URL}/rest/v1/quarterly_usage?select=system_code,click_count,page_view,menu_name"

        response = requests.get(url, headers=SUPABASE_HEADERS, timeout=10)

        if response.status_code != 200:
            return []

        usage_data = response.json()

        usage_dict = {}
        menu_count_dict = {}
        for item in usage_data:
            code = item['system_code']
            if code not in usage_dict:
                usage_dict[code] = {'clicks': 0, 'views': 0}
                menu_count_dict[code] = set()
            usage_dict[code]['clicks'] += item['click_count']
            usage_dict[code]['views'] += item['page_view']
            menu_count_dict[code].add(item['menu_name'])

        result = []
        for system in systems:
            code = system['system_code']
            clicks = usage_dict.get(code, {}).get('clicks', 0)
            views = usage_dict.get(code, {}).get('views', 0)
            cp_ratio = round(clicks / views, 2) if views > 0 else 0
            menu_count = len(menu_count_dict.get(code, set()))
            usage_score = calculate_usage_score(clicks, views)

            result.append({
                'system_code': code,
                'system_name': system['system_name'],
                'category': system['category'],
                'total_clicks': clicks,
                'total_views': views,
                'click_view_ratio': cp_ratio,
                'menu_count': menu_count,
                'usage_score': usage_score['score'],
                'usage_level': usage_score['level'],
                'usage_level_text': usage_score['level_text']
            })

        return result

    except Exception as e:
        st.error(f"获取数据失败: {e}")
        return []


def get_menu_details(system_code, quarter=None):
    """获取菜单详情"""
    try:
        params = [f"system_code=eq.{system_code}"]
        if quarter:
            params.append(f"quarter=eq.{quarter}")

        query = "&".join(params)
        url = f"{SUPABASE_URL}/rest/v1/quarterly_usage?select=menu_name,click_count,page_view&{query}&order=click_count.desc"

        response = requests.get(url, headers=SUPABASE_HEADERS, timeout=10)

        if response.status_code != 200:
            return []

        menu_data = response.json()

        for item in menu_data:
            item['ratio'] = round(item['click_count'] / item['page_view'], 2) if item['page_view'] > 0 else 0

        return menu_data

    except Exception as e:
        st.error(f"获取菜单详情失败: {e}")
        return []


def get_quarters():
    """获取季度列表"""
    try:
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/quarterly_usage?select=quarter",
            headers=SUPABASE_HEADERS,
            timeout=10
        )

        if response.status_code == 200:
            quarters = list(set([item['quarter'] for item in response.json()]))
            quarters.sort()
            return quarters
        return []
    except Exception as e:
        return []


def calculate_usage_score(click_count, page_view):
    """计算使用度评分（简化版）"""
    cp_ratio = click_count / page_view if page_view > 0 else 0

    if cp_ratio >= 3:
        efficiency = 40
    elif cp_ratio >= 2:
        efficiency = 35
    elif cp_ratio >= 1.5:
        efficiency = 30
    elif cp_ratio >= 1:
        efficiency = 25
    elif cp_ratio >= 0.5:
        efficiency = 20
    else:
        efficiency = 10

    if click_count >= 50000:
        frequency = 30
    elif click_count >= 30000:
        frequency = 25
    elif click_count >= 15000:
        frequency = 20
    elif click_count >= 5000:
        frequency = 15
    elif click_count >= 1000:
        frequency = 10
    else:
        frequency = 5

    total = efficiency + frequency + 20 + 10  # 简版评分

    if total >= 80:
        level = "high"
        level_text = "高使用度"
    elif total >= 60:
        level = "medium"
        level_text = "中等使用度"
    elif total >= 40:
        level = "low"
        level_text = "低使用度"
    else:
        level = "very_low"
        level_text = "极低使用度"

    return {'score': total, 'level': level, 'level_text': level_text}


def import_data_to_supabase(df, quarter):
    """导入数据到 Supabase"""
    try:
        # 先删除该季度的数据
        requests.delete(
            f"{SUPABASE_URL}/rest/v1/quarterly_usage",
            headers=SUPABASE_HEADERS,
            params={'quarter': f"eq.{quarter}"}
        )

        records = []
        for _, row in df.iterrows():
            records.append({
                'system_code': str(row['system_code']).strip(),
                'quarter': quarter,
                'menu_name': str(row['menu_name']).strip(),
                'click_count': int(row['click_count']),
                'page_view': int(row['page_view'])
            })

        batch_size = 500
        success_count = 0

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            response = requests.post(
                f"{SUPABASE_URL}/rest/v1/quarterly_usage",
                headers=SUPABASE_HEADERS,
                json=batch
            )
            if response.status_code in [200, 201]:
                success_count += len(batch)

        return success_count, len(records) - success_count

    except Exception as e:
        st.error(f"导入失败: {e}")
        return 0, 0


# ============ 页面函数 ============
def login_page():
    st.title("📊 供应链系统使用度分析平台")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 用户登录")
        username = st.text_input("用户名", key="login_username")
        password = st.text_input("密码", type="password", key="login_password")

        if st.button("登录", use_container_width=True, key="login_button"):
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
        selected_quarter = st.selectbox("选择季度", quarter_options, key="quarter_select")

        st.markdown("---")
        st.markdown(f"**当前用户：** {st.session_state.username} ({st.session_state.role})")
        if st.button("🔄 切换账号", key="switch_account_btn"):
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
        st.plotly_chart(fig, use_container_width=True, key="bar_chart")

    with col2:
        st.subheader("📈 使用度评分")
        fig = px.bar(df, x='system_name', y='usage_score', color='usage_level',
                     title="系统使用度评分", range_y=[0, 100])
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True, key="score_chart")

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

    st.dataframe(display_df, use_container_width=True, hide_index=True, key="system_table")

    # 菜单详情
    st.markdown("---")
    st.subheader("📋 菜单使用详情分析")

    systems_list = get_systems()
    if not systems_list:
        st.warning("未找到系统列表，请检查数据库连接")
        return

    system_options = {s['system_code']: f"{s['system_code']} - {s['system_name']}" for s in systems_list}
    selected_system = st.selectbox("选择系统", list(system_options.keys()), format_func=lambda x: system_options[x],
                                   key="system_select")

    if selected_system:
        menu_data = get_menu_details(selected_system, quarter)

        if menu_data:
            col1, col2 = st.columns([1, 3])
            with col1:
                rank_type = st.radio("排名类型", ["前N名", "后N名"], horizontal=True, key="rank_type")
                rank_count = st.slider("显示数量", 5, 30, 10, key="rank_count")

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
                st.plotly_chart(fig, use_container_width=True, key="click_funnel")

            with col2:
                st.markdown("#### 浏览量漏斗图")
                fig = px.funnel(click_df, x='page_view', y='menu_name', title="菜单浏览量分布")
                fig.update_layout(height=450)
                st.plotly_chart(fig, use_container_width=True, key="view_funnel")

            st.markdown("#### 菜单详细数据")
            menu_df = click_df.rename(columns={
                'menu_name': '菜单名称',
                'click_count': '点击量',
                'page_view': '浏览量',
                'ratio': 'C/P值'
            })
            st.dataframe(menu_df, use_container_width=True, hide_index=True, key="menu_table")
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
        quarter = st.text_input("季度标识", placeholder="例: 2025Q1", key="import_quarter")

    with col2:
        uploaded_file = st.file_uploader("选择文件", type=['xlsx', 'xls', 'csv'], key="import_file")

    if uploaded_file and quarter:
        if st.button("开始导入", type="primary", key="import_button"):
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
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_template"
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
    st.dataframe(users_df, use_container_width=True, hide_index=True, key="user_table")


# ============ 自动登录函数 ============
def auto_login_viewer():
    """自动以 viewer 身份登录"""
    if not st.session_state.logged_in:
        st.session_state.logged_in = True
        st.session_state.username = 'viewer'
        st.session_state.role = 'viewer'
        st.session_state.name = '查看者'


# ============ 主函数 ============
def main():
    # 自动以 viewer 登录（首次访问时）
    auto_login_viewer()

    if not st.session_state.logged_in:
        login_page()
    else:
        with st.sidebar:
            st.markdown("# 📊 供应链分析平台")
            st.markdown("---")
            page = st.radio(
                "导航菜单",
                ["📈 仪表板", "📤 数据导入", "👥 账号管理"],
                index=0,
                key="nav_menu"
            )
            st.markdown("---")
            st.caption(f"当前用户: {st.session_state.username} ({st.session_state.role})")

            # 添加切换账号按钮
            if st.button("🔄 切换账号", key="sidebar_switch_account"):
                st.session_state.logged_in = False
                st.rerun()

        if page == "📈 仪表板":
            dashboard_page()
        elif page == "📤 数据导入":
            import_page()
        elif page == "👥 账号管理":
            account_page()


if __name__ == "__main__":
    main()