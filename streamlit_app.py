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

    total = efficiency + frequency + 20 + 10

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
        # ========== 数据清理 ==========
        df = df.dropna(subset=['system_code', 'menu_name'])

        if len(df) == 0:
            st.warning("数据为空，请检查文件内容")
            return 0, 0

        # 转换数据类型
        df['system_code'] = df['system_code'].astype(str).str.strip()
        df['menu_name'] = df['menu_name'].astype(str).str.strip()
        df['click_count'] = pd.to_numeric(df['click_count']).astype(int)
        df['page_view'] = pd.to_numeric(df['page_view']).astype(int)

        # 去重
        df = df.sort_values('click_count', ascending=False)
        df = df.drop_duplicates(subset=['system_code', 'menu_name'], keep='first')

        st.write("### 📋 数据预览（清理后）")
        st.dataframe(df.head(10))
        st.write(f"共 {len(df)} 行数据（已去重）")

        # ========== 获取所有系统代码 ==========
        system_codes = df['system_code'].unique().tolist()
        st.write(f"### 📌 涉及系统: {', '.join(system_codes)}")

        # ========== 删除该季度这些系统的旧数据 ==========
        for code in system_codes:
            try:
                delete_url = f"{SUPABASE_URL}/rest/v1/quarterly_usage?quarter=eq.{quarter}&system_code=eq.{code}"
                delete_response = requests.delete(
                    delete_url,
                    headers=SUPABASE_HEADERS,
                    timeout=10
                )
                if delete_response.status_code in [200, 204]:
                    st.info(f"✅ 已删除 {code} 在 {quarter} 的旧数据")
                elif delete_response.status_code == 404:
                    st.info(f"ℹ️ {code} 在 {quarter} 无旧数据")
                else:
                    st.warning(f"⚠️ 删除 {code} 旧数据返回: {delete_response.status_code}")
            except Exception as e:
                st.warning(f"⚠️ 删除 {code} 旧数据时出错: {e}")

        # ========== 准备新数据 ==========
        records = []
        for _, row in df.iterrows():
            records.append({
                'system_code': str(row['system_code']),
                'quarter': quarter,
                'menu_name': str(row['menu_name']),
                'click_count': int(row['click_count']),
                'page_view': int(row['page_view'])
            })

        if not records:
            st.warning("没有有效数据可导入")
            return 0, 0

        # ========== 批量导入 ==========
        batch_size = 500
        success_count = 0
        error_messages = []

        st.write("### ⏳ 正在导入数据...")
        progress_bar = st.progress(0)

        total_batches = (len(records) + batch_size - 1) // batch_size

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            batch_num = i // batch_size + 1

            try:
                response = requests.post(
                    f"{SUPABASE_URL}/rest/v1/quarterly_usage",
                    headers=SUPABASE_HEADERS,
                    json=batch,
                    timeout=30
                )

                if response.status_code in [200, 201]:
                    success_count += len(batch)
                    st.success(f"✅ 批次 {batch_num}/{total_batches} 导入成功 ({len(batch)} 条)")
                else:
                    error_msg = f"批次 {batch_num}: HTTP {response.status_code}"
                    try:
                        error_detail = response.json()
                        error_msg += f" - {error_detail.get('message', error_detail)}"
                    except:
                        error_msg += f" - {response.text[:200]}"
                    error_messages.append(error_msg)
                    st.error(f"❌ {error_msg}")

            except Exception as e:
                error_messages.append(f"批次 {batch_num}: {str(e)}")
                st.error(f"❌ 批次 {batch_num} 异常: {e}")

            progress_bar.progress(min(batch_num / total_batches, 1.0))

        progress_bar.empty()

        if error_messages:
            st.warning("### ⚠️ 部分导入失败")
            for msg in error_messages:
                st.code(msg)

        fail_count = len(records) - success_count

        if success_count > 0:
            st.success(f"### ✅ 导入完成！成功: {success_count} 条, 失败: {fail_count} 条")
            if fail_count == 0:
                st.balloons()
        else:
            st.error("### ❌ 所有数据导入失败，请检查上方错误信息")

        return success_count, fail_count

    except Exception as e:
        st.error(f"### ❌ 导入失败: {e}")
        import traceback
        st.code(traceback.format_exc())
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
            for key in list(st.session_state.keys()):
                del st.session_state[key]
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

    # ========== 菜单详情 ==========
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

    # ========== 下载数据明细 ==========
    st.markdown("---")
    st.subheader("📥 下载数据明细")

    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        system_options_download = {s['system_code']: f"{s['system_code']} - {s['system_name']}" for s in systems_list}
        system_options_download['ALL'] = "全部系统"
        selected_system_download = st.selectbox(
            "选择系统",
            list(system_options_download.keys()),
            format_func=lambda x: system_options_download[x],
            key="download_system"
        )

    with col2:
        quarter_options_download = ["全部季度"] + quarters
        selected_quarter_download = st.selectbox(
            "选择季度",
            quarter_options_download,
            key="download_quarter"
        )

    with col3:
        st.write("")
        st.write("")
        download_btn = st.button(
            "📥 下载数据",
            type="primary",
            key="download_btn",
            use_container_width=True
        )

    if download_btn:
        with st.spinner("正在生成下载文件..."):
            params = []

            if selected_system_download != "ALL":
                params.append(f"system_code=eq.{selected_system_download}")

            if selected_quarter_download != "全部季度":
                params.append(f"quarter=eq.{selected_quarter_download}")

            query = "&".join(params) if params else ""
            url = f"{SUPABASE_URL}/rest/v1/quarterly_usage?select=system_code,quarter,menu_name,click_count,page_view"
            if query:
                url += f"&{query}"

            try:
                response = requests.get(
                    url,
                    headers=SUPABASE_HEADERS,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()

                    if data:
                        df_download = pd.DataFrame(data)

                        system_name_map = {s['system_code']: s['system_name'] for s in systems_list}
                        df_download['system_name'] = df_download['system_code'].map(system_name_map)

                        df_download['cp_ratio'] = df_download.apply(
                            lambda row: round(row['click_count'] / row['page_view'], 2) if row['page_view'] > 0 else 0,
                            axis=1
                        )

                        df_download = df_download[[
                            'system_code', 'system_name', 'quarter', 'menu_name',
                            'click_count', 'page_view', 'cp_ratio'
                        ]].rename(columns={
                            'system_code': '系统代码',
                            'system_name': '系统名称',
                            'quarter': '季度',
                            'menu_name': '菜单名称',
                            'click_count': '点击量',
                            'page_view': '浏览量',
                            'cp_ratio': 'C/P值'
                        })

                        df_download = df_download.sort_values(['系统代码', '点击量'], ascending=[True, False])

                        st.success(f"✅ 共 {len(df_download)} 条数据")
                        st.dataframe(df_download.head(20), use_container_width=True)

                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_download.to_excel(writer, sheet_name='使用明细', index=False)

                            summary = df_download.groupby(['系统代码', '系统名称']).agg({
                                '点击量': 'sum',
                                '浏览量': 'sum',
                                '菜单名称': 'count'
                            }).reset_index()
                            summary['C/P值'] = summary.apply(
                                lambda row: round(row['点击量'] / row['浏览量'], 2) if row['浏览量'] > 0 else 0,
                                axis=1
                            )
                            summary = summary.rename(columns={
                                '系统代码': '系统代码',
                                '系统名称': '系统名称',
                                '点击量': '总点击量',
                                '浏览量': '总浏览量',
                                '菜单名称': '菜单数量',
                                'C/P值': 'C/P值'
                            })
                            summary.to_excel(writer, sheet_name='系统汇总', index=False)

                        system_label = selected_system_download if selected_system_download != "ALL" else "全部系统"
                        quarter_label = selected_quarter_download if selected_quarter_download != "全部季度" else "全部季度"

                        st.download_button(
                            label="📥 下载 Excel 文件",
                            data=output.getvalue(),
                            file_name=f"使用明细_{system_label}_{quarter_label}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_excel",
                            use_container_width=True
                        )
                    else:
                        st.warning("⚠️ 没有找到符合条件的数据")
                else:
                    st.error(f"❌ 获取数据失败: {response.status_code}")

            except Exception as e:
                st.error(f"❌ 下载失败: {e}")
                import traceback
                st.code(traceback.format_exc())


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

                st.write("### 📋 文件读取成功")
                st.write(f"行数: {len(df)}")
                st.write(f"列名: {df.columns.tolist()}")
                st.write("### 原始数据预览:")
                st.dataframe(df.head())

                required_cols = ['system_code', 'menu_name', 'click_count', 'page_view']
                missing_cols = [col for col in required_cols if col not in df.columns]

                if missing_cols:
                    st.error(f"❌ 缺少列: {missing_cols}")
                    st.write("### 当前列名:")
                    st.write(df.columns.tolist())
                    st.write("### 请确保列名完全匹配（区分大小写）:")
                    st.code("system_code | menu_name | click_count | page_view")
                else:
                    st.write("### 数据验证:")

                    null_counts = df[required_cols].isnull().sum()
                    if null_counts.sum() > 0:
                        st.warning(f"⚠️ 存在空值:\n{null_counts}")

                    try:
                        df['click_count'] = pd.to_numeric(df['click_count'])
                        df['page_view'] = pd.to_numeric(df['page_view'])
                        st.success("✅ 数字列转换成功")
                    except Exception as e:
                        st.error(f"❌ 数字列转换失败: {e}")
                        st.stop()

                    valid_codes = ['WMS', 'IMS', 'SCM', 'SRM', 'TMS', 'QMS']
                    invalid_codes = df[~df['system_code'].isin(valid_codes)]['system_code'].unique()
                    if len(invalid_codes) > 0:
                        st.warning(f"⚠️ 发现无效的 system_code: {invalid_codes.tolist()}")
                        st.write(f"有效值: {valid_codes}")

                    with st.spinner("正在导入数据..."):
                        success, fail = import_data_to_supabase(df, quarter)

            except Exception as e:
                st.error(f"❌ 导入失败: {e}")
                import traceback
                st.code(traceback.format_exc())

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


# ============ 主函数 ============
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
                index=0,
                key="nav_menu"
            )
            st.markdown("---")
            st.caption(f"当前用户: {st.session_state.username} ({st.session_state.role})")

            if st.button("🔄 切换账号", key="sidebar_switch_account"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()

        if page == "📈 仪表板":
            dashboard_page()
        elif page == "📤 数据导入":
            import_page()
        elif page == "👥 账号管理":
            account_page()


if __name__ == "__main__":
    main()