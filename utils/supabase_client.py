import os
import requests
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://pluynxzhrtndpxdfkoak.supabase.co')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}


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
        print(f"获取系统列表失败: {e}")
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

        # 汇总数据
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

            # 计算使用度评分
            usage_score = calculate_usage_score(clicks, views, menu_count)

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
        print(f"获取系统使用汇总异常: {e}")
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
        print(f"获取菜单详情异常: {e}")
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
        print(f"获取季度列表异常: {e}")
        return []


def calculate_usage_score(click_count, page_view, menu_count=None):
    """计算使用度评分"""
    cp_ratio = click_count / page_view if page_view > 0 else 0

    # 操作效率得分 (40分)
    if cp_ratio >= 3:
        efficiency_score = 40
    elif cp_ratio >= 2:
        efficiency_score = 35
    elif cp_ratio >= 1.5:
        efficiency_score = 30
    elif cp_ratio >= 1:
        efficiency_score = 25
    elif cp_ratio >= 0.5:
        efficiency_score = 20
    else:
        efficiency_score = 10

    # 使用频率得分 (30分)
    if click_count >= 50000:
        frequency_score = 30
    elif click_count >= 30000:
        frequency_score = 25
    elif click_count >= 15000:
        frequency_score = 20
    elif click_count >= 5000:
        frequency_score = 15
    elif click_count >= 1000:
        frequency_score = 10
    else:
        frequency_score = 5

    # 覆盖面得分 (20分)
    if menu_count:
        if menu_count >= 20:
            coverage_score = 20
        elif menu_count >= 15:
            coverage_score = 16
        elif menu_count >= 10:
            coverage_score = 12
        elif menu_count >= 5:
            coverage_score = 8
        else:
            coverage_score = 4
    else:
        coverage_score = 10

    # 活跃度得分 (10分)
    if page_view >= 20000:
        activity_score = 10
    elif page_view >= 10000:
        activity_score = 8
    elif page_view >= 5000:
        activity_score = 6
    elif page_view >= 1000:
        activity_score = 4
    else:
        activity_score = 2

    total_score = efficiency_score + frequency_score + coverage_score + activity_score

    if total_score >= 80:
        level = "high"
        level_text = "高使用度"
    elif total_score >= 60:
        level = "medium"
        level_text = "中等使用度"
    elif total_score >= 40:
        level = "low"
        level_text = "低使用度"
    else:
        level = "very_low"
        level_text = "极低使用度"

    return {'score': total_score, 'level': level, 'level_text': level_text}


def import_data_to_supabase(df, quarter):
    """导入数据到 Supabase"""
    try:
        # 先删除该季度的数据
        requests.delete(
            f"{SUPABASE_URL}/rest/v1/quarterly_usage",
            headers=SUPABASE_HEADERS,
            params={'quarter': f"eq.{quarter}"}
        )

        # 批量插入
        records = []
        for _, row in df.iterrows():
            records.append({
                'system_code': str(row['system_code']).strip(),
                'quarter': quarter,
                'menu_name': str(row['menu_name']).strip(),
                'click_count': int(row['click_count']),
                'page_view': int(row['page_view'])
            })

        # 分批插入
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
        print(f"导入失败: {e}")
        return 0, 0