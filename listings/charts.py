import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
# Ensure matplotlib supports Chinese characters
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Microsoft YaHei', 'SimHei'] # Add fonts that support Chinese
plt.rcParams['axes.unicode_minus'] = False # Solve the problem of '-' displaying as a square

def plot_bar_chart(data, ylabel):
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = data.plot(kind='bar', ax=ax, color='skyblue', legend=True)
    ax.set_xlabel('縣市')
    ax.set_ylabel(ylabel)
    ax.set_xticklabels(data.index, rotation=45, ha='right')
    # 資料標籤
    for p in ax.patches:
        val = p.get_height()
        if not np.isnan(val):
            ax.annotate(f'{val:.1f}', (p.get_x() + p.get_width() / 2, val),
                                 ha='center', va='bottom', fontsize=8, rotation=0)
    ax.legend([ylabel])
    plt.tight_layout()
    return fig

def plot_avg_area_by_city(df, chinese_cities):
    # Ensure '縣市' column is used for grouping
    data = df.groupby('縣市')['坪數'].mean().reindex(chinese_cities)
    return plot_bar_chart(data, '平均坪數')

def plot_avg_rent_by_city(df, chinese_cities):
    # Ensure '縣市' column is used for grouping
    data = df.groupby('縣市')['租金'].mean().reindex(chinese_cities)
    return plot_bar_chart(data, '平均租金')

def plot_avg_rent_per_area_by_city(df, chinese_cities):
    # Ensure '縣市' column is used for grouping
    data = (df.groupby('縣市').apply(lambda x: (x['租金']/x['坪數']).mean())).reindex(chinese_cities)
    return plot_bar_chart(data, '平均每坪租金')

def plot_count_by_city(df, chinese_cities):
    # Ensure '縣市' column is used for grouping
    data = df.groupby('縣市').size().reindex(chinese_cities, fill_value=0)
    return plot_bar_chart(data, '物件總數')

def plot_room_count_by_city(df, chinese_cities):
    # Ensure '縣市' column is used for grouping
    data = df.groupby('縣市')['房數'].mean().reindex(chinese_cities)
    return plot_bar_chart(data, '平均房數')

def plot_pie_room_type(df, city):
    # 確保 '縣市' 欄位用於篩選
    city_df = df[df['縣市'] == city].copy() # 使用 .copy() 避免SettingWithCopyWarning
    if city_df.empty:
        return None
    
    # 篩除房數 <= 0 的資料
    city_df = city_df[city_df['房數'] > 0]
    if city_df.empty: # 如果篩除後沒有資料了，則返回 None
        return None
    
    # 將房數 >= 4 的歸類為 4
    # 注意：房數是浮點數，所以要先轉換為整數再比較
    city_df['房數_grouped'] = city_df['房數'].apply(lambda x: min(int(x), 4))
    
    room_counts = city_df['房數_grouped'].value_counts().sort_index()

    # 調整標籤以顯示 '4房以上'
    labels = []
    for r in room_counts.index:
        if r == 4:
            labels.append('4房以上')
        else:
            labels.append(f"{int(r)}房")

    fig, ax = plt.subplots(figsize=(6, 6))
    
    wedges, texts, autotexts = ax.pie(
        room_counts, 
        labels=labels, # 使用新的標籤列表
        autopct='%1.1f%%', 
        startangle=90, 
        textprops={'fontsize': 10}, 
        pctdistance=0.8
    )
    ax.set_ylabel('')
    
    # 調整圖例以顯示 '4房以上'
    legend_labels = []
    for r in room_counts.index:
        if r == 4:
            legend_labels.append('4房以上')
        else:
            legend_labels.append(f"{int(r)}房")
            
    ax.legend(wedges, legend_labels, title="房型", loc="best")
    
    plt.tight_layout()
    return fig

def plot_hist_avg_rent_by_area_bin(df, city):
    # Ensure '縣市' column is used for filtering
    city_df = df[df['縣市'] == city]
    if city_df.empty:
        return None
    bins = [0, 10, 20, 30, 50, 100, np.inf]
    labels = ['0-10坪', '10-20坪', '20-30坪', '30-50坪', '50-100坪', '100坪以上']
    city_df['坪數區間'] = pd.cut(city_df['坪數'], bins=bins, labels=labels, right=False)
    avg_rent = city_df.groupby('坪數區間')['租金'].mean()
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = avg_rent.plot(kind='bar', ax=ax, color='orange', legend=True)
    ax.set_xlabel('坪數區間')
    ax.set_ylabel('平均租金')
    for p in ax.patches:
        val = p.get_height()
        if not np.isnan(val):
            ax.annotate(f'{val:.1f}', (p.get_x() + p.get_width() / 2, val),
                                 ha='center', va='bottom', fontsize=8, rotation=0)
    ax.legend(['平均租金'])
    plt.tight_layout()
    return fig