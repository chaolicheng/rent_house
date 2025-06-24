# your_project_name/your_app_name/bokeh_charts.py

import pandas as pd
import numpy as np
import re
from django.db.models import QuerySet
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, HoverTool, FactorRange, NumeralTickFormatter
from bokeh.transform import factor_cmap, cumsum
from bokeh.palettes import Category10, Spectral6, Viridis
from math import pi

# 數據清洗和預處理函數
def clean_rent_data(df):
    """清理租金數據，將 '7,000 元/月' 轉換為數字"""
    if 'rent' in df.columns:
        df['rent_cleaned'] = df['rent'].astype(str).str.replace('元/月', '').str.replace(',', '').fillna(0).astype(int)
    else:
        df['rent_cleaned'] = 0
    return df

def clean_area_data(df):
    """清理坪數數據，將 '8 坪' 轉換為數字"""
    if 'area' in df.columns:
        df['area_cleaned'] = df['area'].astype(str).str.replace('坪', '').fillna(0).astype(float)
    else:
        df['area_cleaned'] = 0.0
    return df

def extract_room_type(pattern_str):
    """從房型字串中提取房間數，例如 '1房(室)0廳1衛' -> '1房'"""
    if not isinstance(pattern_str, str):
        return '其他'
    match = re.search(r'(\d+房)', pattern_str)
    if match:
        num_rooms = int(match.group(1).replace('房', ''))
        if num_rooms >= 4:
            return '4房以上'
        return match.group(1) # 例如 '1房', '2房', '3房'
    return '其他' # 例如 '整層住家', '獨立套房' 可能沒有明確的「房」

def extract_city_from_address(address):
    """從地址中提取縣市名稱"""
    if not isinstance(address, str):
        return '未知縣市'
    # 常用縣市列表（可以根據實際數據擴展）
    cities = ["臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市",
              "新竹市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣",
              "嘉義市", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣",
              "澎湖縣", "金門縣", "連江縣"]
    for city in cities:
        if address.startswith(city):
            return city
    return '其他縣市'


def prepare_dataframe(queryset: QuerySet):
    """
    將 Django QuerySet 轉換為 Pandas DataFrame 並進行數據清洗。
    同時提取縣市資訊和清洗房數。
    """
    data = list(queryset.values())
    df = pd.DataFrame(data)

    if not df.empty:
        df = clean_rent_data(df)
        df = clean_area_data(df)

        if 'address' in df.columns:
            df['city'] = df['address'].apply(extract_city_from_address)
        else:
            df['city'] = '未知縣市'

        if 'pattern' in df.columns:
            df['room_type'] = df['pattern'].apply(extract_room_type)
            # 提取數字房數，用於散點圖等
            df['room_cleaned'] = df['room_type'].apply(lambda x: int(x.replace('房', '')) if '房' in x else (4 if x == '4房以上' else np.nan))
        else:
            df['room_type'] = '未知'
            df['room_cleaned'] = np.nan

        # 為散點圖提供縣市的數值ID，方便繪圖
        unique_cities = df['city'].unique().tolist()
        city_to_id = {city: i for i, city in enumerate(sorted(unique_cities))}
        df['city_numeric_id'] = df['city'].map(city_to_id)

    return df

# --- Bokeh 圖表繪製函數 ---

def get_hover_tool(fields):
    """通用 HoverTool 配置"""
    hover = HoverTool(tooltips=fields)
    return hover

def plot_bokeh_bar_chart(df: pd.DataFrame, x_column: str, y_column: str, title: str, x_label: str, y_label: str):
    """
    繪製 Bokeh 長條圖。
    """
    if df.empty or x_column not in df.columns or y_column not in df.columns:
        p = figure(title="資料不足以繪製長條圖。", height=400, width=800)
        p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
        return p

    source = ColumnDataSource(df)

    # 設置 X 軸類別順序
    x_range_categories = list(df[x_column].astype(str).unique())
    # 嘗試保持一些常見的順序，比如租金區間
    if '租金區間' in x_label:
        custom_order = ['<5K', '5K-10K', '10K-15K', '15K-20K', '20K-25K', '25K-30K', '>30K']
        x_range_categories.sort(key=lambda x: custom_order.index(x) if x in custom_order else len(custom_order))
    elif '坪數區間' in x_label:
        custom_order = ['<5坪', '5-10坪', '10-15坪', '15-20坪', '20-25坪', '25-30坪', '>30坪']
        x_range_categories.sort(key=lambda x: custom_order.index(x) if x in custom_order else len(custom_order))
    elif '房型' in x_label:
        custom_order = ['1房', '2房', '3房', '4房以上', '其他', '未知']
        x_range_categories.sort(key=lambda x: custom_order.index(x) if x in custom_order else len(custom_order))
    else:
        x_range_categories.sort()


    p = figure(x_range=FactorRange(factors=x_range_categories), height=400, width=800, title=title,
               x_axis_label=x_label, y_axis_label=y_label, tools="pan,wheel_zoom,box_zoom,reset,save")

    p.vbar(x=x_column, top=y_column, width=0.9, source=source,
           legend_field=x_column, line_color='white',
           fill_color=factor_cmap(x_column, palette=Category10[10], factors=x_range_categories))

    p.xgrid.grid_line_color = None
    p.y_range.start = 0
    p.xaxis.major_label_orientation = pi/4 # 旋轉X軸標籤
    p.legend.orientation = "horizontal"
    p.legend.location = "top_center"
    p.legend.click_policy="hide" # 點擊圖例隱藏/顯示
    p.add_tools(get_hover_tool([
        (x_label, f"@{x_column}"),
        (y_label, f"@{y_column}{{0,0}}")
    ]))
    return p

def plot_bokeh_pie_chart(df: pd.DataFrame, value_column: str, title: str):
    """
    繪製 Bokeh 圓餅圖。
    """
    if df.empty or value_column not in df.columns:
        p = figure(title="資料不足以繪製圓餅圖。", height=400, width=800)
        p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
        return p

    counts = df[value_column].value_counts()
    data = pd.Series(counts).reset_index(name='value').rename(columns={'index': value_column})
    data['angle'] = data['value'] / data['value'].sum() * 2 * pi
    colors = Category10[len(data)] if len(data) <= 10 else Viridis[len(data)]
    data['color'] = colors

    source = ColumnDataSource(data)

    p = figure(height=400, title=title, toolbar_location="right",
               tools="pan,wheel_zoom,reset,save", x_range=(-0.5, 1.0))

    p.wedge(x=0, y=1, radius=0.4,
            start_angle=cumsum('angle', include_zero=True), end_angle=cumsum('angle'),
            line_color="white", fill_color='color', legend_field=value_column, source=source)

    p.axis.visible = False
    p.grid.grid_line_color = None
    p.add_tools(get_hover_tool([
        (value_column, f"@{value_column}"),
        ("數量", "@value"),
        ("百分比", "@value{0,0.0}%") # 這個百分比需要手動計算或用CustomJS處理
    ]))
    return p

def plot_bokeh_histogram(df: pd.DataFrame, data_column: str, title: str, x_label: str, y_label: str, bins=20):
    """
    繪製 Bokeh 直方圖。
    """
    if df.empty or data_column not in df.columns or not pd.api.types.is_numeric_dtype(df[data_column]):
        p = figure(title=f"資料不足或 '{data_column}' 不是數值類型，無法繪製直方圖。", height=400, width=800)
        p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
        return p

    hist, edges = np.histogram(df[data_column].dropna(), bins=bins)
    df_hist = pd.DataFrame({'hist': hist, 'left': edges[:-1], 'right': edges[1:]})
    source = ColumnDataSource(df_hist)

    p = figure(height=400, width=800, title=title,
               x_axis_label=x_label, y_axis_label=y_label,
               tools="pan,wheel_zoom,box_zoom,reset,save")

    p.quad(top='hist', bottom=0, left='left', right='right', source=source,
           fill_color="navy", line_color="white", alpha=0.7)

    p.x_range.end = edges[-1] # 確保X軸範圍完整
    p.y_range.start = 0
    p.add_tools(get_hover_tool([
        (x_label, "@left{0,0.0}-@right{0,0.0}"),
        (y_label, "@hist")
    ]))
    return p

def plot_bokeh_box_plot(df: pd.DataFrame, data_column: str, title: str, y_label: str, group_column: str = None):
    """
    繪製 Bokeh 箱型圖。
    如果提供了 group_column，則會繪製分組箱型圖。
    """
    if df.empty or data_column not in df.columns or not pd.api.types.is_numeric_dtype(df[data_column]):
        p = figure(title=f"資料不足或 '{data_column}' 不是數值類型，無法繪製箱型圖。", height=400, width=800)
        p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
        return p

    # 計算箱型圖的統計值 (Q1, 中位數, Q3, 鬚線)
    if group_column and group_column in df.columns:
        groups = df[group_column].astype(str).unique().tolist()
        # 排序縣市，確保圖表順序一致
        if group_column == 'city':
            groups.sort(key=lambda x: str(x).replace('臺', '台')) # 對中文排序做一點處理
        else:
            groups.sort() # 其他類別直接排序

        stats = df.groupby(group_column)[data_column].describe(percentiles=[.25, .5, .75]).unstack()
        q1 = stats.loc[:, '25%']
        q2 = stats.loc[:, '50%']
        q3 = stats.loc[:, '75%']
        iqr = q3 - q1
        upper = q3 + 1.5*iqr
        lower = q1 - 1.5*iqr

        # 找出異常值 (outliers)
        outliers = df.groupby(group_column).apply(lambda x: x[(x[data_column] > upper[x.name]) | (x[data_column] < lower[x.name])][data_column])
        if not outliers.empty:
            outliers_df = outliers.reset_index(level=1, drop=True).reset_index()
            outliers_df.columns = [group_column, data_column]
            outlier_source = ColumnDataSource(outliers_df)
        else:
            outlier_source = ColumnDataSource(pd.DataFrame({group_column: [], data_column: []}))

        # 整理繪圖數據
        box_df = pd.DataFrame(dict(
            groups=groups,
            q1=q1[groups],
            q2=q2[groups],
            q3=q3[groups],
            upper=upper[groups],
            lower=lower[groups]
        ))
        source = ColumnDataSource(box_df)

        p = figure(x_range=groups, height=400, width=800, title=title,
                   x_axis_label=group_column, y_axis_label=y_label,
                   tools="pan,wheel_zoom,box_zoom,reset,save")

        # 繪製鬚線 (whiskers)
        p.segment(x0='groups', y0='upper', x1='groups', y1='q3', source=source, line_color="black")
        p.segment(x0='groups', y0='lower', x1='groups', y1='q1', source=source, line_color="black")

        # 繪製箱體 (boxes)
        p.vbar(x='groups', top='q3', bottom='q2', width=0.7, source=source,
               fill_color="#E08B5F", line_color="black")
        p.vbar(x='groups', top='q2', bottom='q1', width=0.7, source=source,
               fill_color="#30A2FF", line_color="black")

        # 繪製異常值
        p.scatter(x=group_column, y=data_column, marker='circle', size=8, alpha=0.4,
                  color="red", source=outlier_source, legend_label="異常值")

        p.xgrid.grid_line_color = None
        p.xaxis.major_label_orientation = pi/4
        p.add_tools(get_hover_tool([
            (group_column, f"@{group_column}"),
            ("Q1", "@q1{0,0}"),
            ("中位數", "@q2{0,0}"),
            ("Q3", "@q3{0,0}"),
            ("上限", "@upper{0,0}"),
            ("下限", "@lower{0,0}")
        ]))

    else: # 單一箱型圖
        data = df[data_column].dropna()
        if data.empty:
            p = figure(title=f"'{data_column}' 欄位沒有有效數據，無法繪製箱型圖。", height=400, width=800)
            p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
            return p

        q1, q2, q3 = data.quantile(0.25), data.quantile(0.5), data.quantile(0.75)
        iqr = q3 - q1
        upper = q3 + 1.5 * iqr
        lower = q1 - 1.5 * iqr

        outliers = data[(data > upper) | (data < lower)]

        p = figure(height=400, width=800, x_range=[''], title=title,
                   x_axis_label="", y_axis_label=y_label,
                   tools="pan,wheel_zoom,box_zoom,reset,save")

        # 繪製鬚線
        p.segment(x0=[''], y0=[upper], x1=[''], y1=[q3], line_color="black")
        p.segment(x0=[''], y0=[lower], x1=[''], y1=[q1], line_color="black")

        # 繪製箱體
        p.vbar(x=[''], top=[q3], bottom=[q2], width=0.2, fill_color="#E08B5F", line_color="black")
        p.vbar(x=[''], top=[q2], bottom=[q1], width=0.2, fill_color="#30A2FF", line_color="black")

        # 繪製異常值
        outlier_source = ColumnDataSource(pd.DataFrame({'x': [''] * len(outliers), 'y': outliers}))
        p.scatter(x='x', y='y', marker='circle', size=8, alpha=0.4,
                  color="red", source=outlier_source, legend_label="異常值")

        p.xgrid.grid_line_color = None
        p.add_tools(get_hover_tool([
            ("Q1", f"{q1:,.0f}"),
            ("中位數", f"{q2:,.0f}"),
            ("Q3", f"{q3:,.0f}"),
            ("上限", f"{upper:,.0f}"),
            ("下限", f"{lower:,.0f}")
        ]))

    return p

def plot_bokeh_scatter_plot(df: pd.DataFrame, x_column: str, y_column: str, title: str, x_label: str, y_label: str):
    """
    繪製 Bokeh 散點圖。
    """
    df_cleaned = df[[x_column, y_column]].dropna()
    if df_cleaned.empty:
        p = figure(title=f"資料不足或包含缺失值，無法繪製散點圖。", height=400, width=800)
        p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
        return p

    source = ColumnDataSource(df_cleaned)

    p = figure(height=400, width=800, title=title,
               x_axis_label=x_label, y_axis_label=y_label,
               tools="pan,wheel_zoom,box_zoom,reset,save")

    p.scatter(x=x_column, y=y_column, source=source, size=8, alpha=0.6,
              color=Category10[1][0] if len(Category10) > 0 else 'blue') # 使用單一顏色

    p.add_tools(get_hover_tool([
        (x_label, f"@{x_column}"),
        (y_label, f"@{y_column}{{0,0}}")
    ]))
    p.xaxis.formatter = NumeralTickFormatter(format="0,0")
    p.yaxis.formatter = NumeralTickFormatter(format="0,0")
    return p

def plot_bokeh_multiple_cities_bar(df: pd.DataFrame, group_column: str, value_column: str, title: str, x_label: str, y_label: str, agg_func='mean'):
    """
    繪製多縣市比較長條圖 (例如各縣市平均租金/坪數)。
    """
    if df.empty or group_column not in df.columns or value_column not in df.columns:
        p = figure(title="資料不足以繪製多縣市長條圖。", height=400, width=800)
        p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
        return p

    # 計算每個縣市的平均值
    if agg_func == 'mean':
        agg_data = df.groupby(group_column)[value_column].mean().reset_index()
    elif agg_func == 'count':
        agg_data = df.groupby(group_column)[value_column].count().reset_index() # 或者 .size()
        agg_data.rename(columns={value_column: 'count'}, inplace=True)
        value_column = 'count'
    else: # default to mean
        agg_data = df.groupby(group_column)[value_column].mean().reset_index()

    # 對縣市進行排序，確保圖表順序一致
    categories = agg_data[group_column].astype(str).unique().tolist()
    categories.sort(key=lambda x: str(x).replace('臺', '台')) # 對中文排序做一點處理

    source = ColumnDataSource(agg_data)

    p = figure(x_range=FactorRange(factors=categories), height=400, width=800, title=title,
               x_axis_label=x_label, y_axis_label=y_label, tools="pan,wheel_zoom,box_zoom,reset,save")

    # 使用 factor_cmap 為每個縣市分配顏色
    p.vbar(x=group_column, top=value_column, width=0.9, source=source,
           legend_field=group_column, line_color='white',
           fill_color=factor_cmap(group_column, palette=Category10[10], factors=categories))

    p.xgrid.grid_line_color = None
    p.y_range.start = 0
    p.xaxis.major_label_orientation = pi/4
    p.legend.orientation = "horizontal"
    p.legend.location = "top_center"
    p.legend.click_policy="hide"

    p.add_tools(get_hover_tool([
        (x_label, f"@{group_column}"),
        (y_label, f"@{value_column}{{0,0}}")
    ]))
    return p


def plot_bokeh_multiple_cities_box(df: pd.DataFrame, group_column: str, value_column: str, title: str, x_label: str, y_label: str):
    """
    繪製多縣市分組箱型圖。
    """
    if df.empty or group_column not in df.columns or value_column not in df.columns or not pd.api.types.is_numeric_dtype(df[value_column]):
        p = figure(title=f"資料不足或 '{value_column}' 不是數值類型，無法繪製分組箱型圖。", height=400, width=800)
        p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
        return p

    groups = df[group_column].astype(str).unique().tolist()
    groups.sort(key=lambda x: str(x).replace('臺', '台')) # 對中文排序做一點處理

    # 計算每個分組的統計值
    stats = df.groupby(group_column)[value_column].describe(percentiles=[.25, .5, .75]).unstack()
    q1 = stats.loc[:, '25%']
    q2 = stats.loc[:, '50%']
    q3 = stats.loc[:, '75%']
    iqr = q3 - q1
    upper = q3 + 1.5*iqr
    lower = q1 - 1.5*iqr

    # 找出異常值 (outliers)
    # 使用 apply 結合 lambda 函數來處理每個組的異常值
    outliers_data = []
    for g in groups:
        group_df = df[df[group_column] == g]
        group_data = group_df[value_column].dropna()
        if not group_data.empty:
            group_upper = upper[g]
            group_lower = lower[g]
            group_outliers = group_data[(group_data > group_upper) | (group_data < group_lower)]
            for outlier_val in group_outliers:
                outliers_data.append({'group': g, 'value': outlier_val})
    
    outlier_source = ColumnDataSource(pd.DataFrame(outliers_data)) if outliers_data else ColumnDataSource(pd.DataFrame({'group': [], 'value': []}))


    # 整理繪圖數據
    box_df = pd.DataFrame(dict(
        groups=groups,
        q1=[q1[g] for g in groups],
        q2=[q2[g] for g in groups],
        q3=[q3[g] for g in groups],
        upper=[upper[g] for g in groups],
        lower=[lower[g] for g in groups]
    ))
    source = ColumnDataSource(box_df)

    p = figure(x_range=groups, height=400, width=800, title=title,
               x_axis_label=x_label, y_axis_label=y_label,
               tools="pan,wheel_zoom,box_zoom,reset,save")

    # 繪製鬚線 (whiskers)
    p.segment(x0='groups', y0='upper', x1='groups', y1='q3', source=source, line_color="black")
    p.segment(x0='groups', y0='lower', x1='groups', y1='q1', source=source, line_color="black")

    # 繪製箱體 (boxes)
    p.vbar(x='groups', top='q3', bottom='q2', width=0.7, source=source,
           fill_color="#E08B5F", line_color="black")
    p.vbar(x='groups', top='q2', bottom='q1', width=0.7, source=source,
           fill_color="#30A2FF", line_color="black")

    # 繪製異常值
    if not outlier_source.data['group'].empty: # 檢查是否有異常值數據
        p.scatter(x='group', y='value', marker='circle', size=8, alpha=0.4,
                  color="red", source=outlier_source, legend_label="異常值")

    p.xgrid.grid_line_color = None
    p.xaxis.major_label_orientation = pi/4
    
    hover_tooltips = [
        (x_label, "@groups"),
        ("Q1", "@q1{0,0}"),
        ("中位數", "@q2{0,0}"),
        ("Q3", "@q3{0,0}"),
        ("上限", "@upper{0,0}"),
        ("下限", "@lower{0,0}")
    ]
    p.add_tools(get_hover_tool(hover_tooltips))

    return p


def plot_bokeh_multiple_cities_scatter(df: pd.DataFrame, x_column: str, y_column: str, color_column: str, title: str, x_label: str, y_label: str):
    """
    繪製多縣市散點圖，不同縣市以不同顏色區分。
    """
    df_cleaned = df[[x_column, y_column, color_column]].dropna()
    if df_cleaned.empty:
        p = figure(title=f"資料不足或包含缺失值，無法繪製散點圖。", height=400, width=800)
        p.text(x=0.5, y=0.5, text=["無數據"], text_align="center", text_baseline="middle", text_font_size="20px")
        return p

    # 確保 color_column 的類別是因子 (factor)
    categories = df_cleaned[color_column].astype(str).unique().tolist()
    categories.sort(key=lambda x: str(x).replace('臺', '台')) # 對中文排序做一點處理

    source = ColumnDataSource(df_cleaned)

    # 根據類別數量選擇調色板
    palette = Category10[min(len(categories), 10)] if len(categories) <= 10 else Viridis[len(categories)]

    p = figure(height=400, width=800, title=title,
               x_axis_label=x_label, y_axis_label=y_label,
               tools="pan,wheel_zoom,box_zoom,reset,save")

    p.scatter(x=x_column, y=y_column, source=source, size=8, alpha=0.6,
              legend_field=color_column,
              color=factor_cmap(color_column, palette=palette, factors=categories))

    p.add_tools(get_hover_tool([
        (x_label, f"@{x_column}"),
        (y_label, f"@{y_column}{{0,0}}"),
        ("縣市", f"@{color_column}")
    ]))

    p.legend.orientation = "horizontal"
    p.legend.location = "top_left"
    p.legend.click_policy="hide"

    # 如果 X 軸是縣市的數值 ID，顯示縣市名稱
    if x_column == 'city_numeric_id' and 'city' in df.columns:
        # 創建一個映射，將數值 ID 對應回縣市名稱
        # 這裡需要傳入正確的縣市列表作為 x_range 的標籤
        # 由於 bokeh.plotting.figure 無法直接設置 x_range 為映射，
        # 可以在前端進行處理，或者使用 bokeh.models.FactorRange 配合 CustomJS
        # 簡化處理：HoverTool 已經顯示了縣市名稱，X軸保持數值，或者直接用 Categorical x_range
        
        # 為了散點圖 X 軸為分類數據，需要將其轉換為字符串，Bokeh 才能正確處理
        # 假設 'city_numeric_id' 只是為了內部計算，實際繪圖應使用 'city' 作為分類軸
        if 'city' in df.columns:
            # 如果是縣市對應租金/坪數的散點圖，X軸應該是分類的縣市
            # 這會改變散點圖的性質，使其更像分組散點圖
            # 如果希望 X 軸仍為數值，但 HoverTool 顯示縣市，則保留 'city_numeric_id'
            # 這裡為了符合「縣市與X間的關聯」的散點圖描述，假設X軸應為分類的縣市
            # 這就需要調整調用 scatter 的方式，讓 X 軸是分類的
            # 由於之前設計的 x_column 是數值，這裡先保持數值，並在 HoverTool 補充
            pass # 保持現有邏輯，依靠 HoverTool 顯示縣市名稱

    p.xaxis.formatter = NumeralTickFormatter(format="0,0")
    p.yaxis.formatter = NumeralTickFormatter(format="0,0")
    
    return p