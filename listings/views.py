from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, IntegerField, FloatField, Value, Avg, Count, Max, Min, QuerySet
from django.db.models.functions import Cast, Replace, ExtractYear, ExtractMonth
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.views.decorators.http import require_POST
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.forms import UserCreationForm
from django.conf import settings
from django.contrib.gis.measure import D # 用於距離計算
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance # 用於 ORM 距離計算
from .models import Listing, RentUser
from .crawler import get_rent_data
from .utils import geocode_address # 引入地理編碼函數
import os
import re
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from io import BytesIO
import matplotlib.pyplot as plt
import base64
from . import charts
import googlemaps # 導入 googlemaps 庫
import time # 用於 API 請求間的延遲，避免超速
import logging as logger

# Create your views here.


# 檢查用戶是否為超級用戶的輔助函數
def is_superuser(user):
    return user.is_authenticated and user.is_superuser

# @login_required
def index(request):
    """
    Home page view that redirects to the rent list.
    """
    return render(request, 'index.html')

@login_required # 確保用戶已登入
@user_passes_test(is_superuser) # 確保用戶是管理員
@require_POST # 只接受 POST 請求
def geocode_missing_listings(request):
    """
    管理員觸發，對資料庫中沒有經緯度的房源進行地理編碼。
    """
    password = request.POST.get('password') # 從 POST 數據中獲取密碼

    # 1. 驗證管理員密碼
    user = request.user
    if not user.check_password(password):
        return JsonResponse({'status': 'error', 'message': '密碼錯誤，請重新輸入。'}, status=403) # 403 Forbidden

    # 2. 獲取沒有經緯度的房源
    # 注意：使用 .iterator() 處理大量數據時更高效，避免一次性加載所有數據到記憶體
    listings_to_geocode = Listing.objects.filter(location__isnull=True).iterator()
    
    geocoded_count = 0
    failed_count = 0
    total_to_process = Listing.objects.filter(location__isnull=True).count() # 為了前端顯示總數

    Maps_api_key = os.environ.get('Maps_API_KEY') or getattr(settings, 'MAPS_API_KEY', None)

    if not Maps_api_key:
        return JsonResponse({'status': 'error', 'message': '伺服器未配置 Google Maps API 金鑰。'}, status=500)

    print(f"總共有 {total_to_process} 筆資料需要處理。\n開始地理編碼...")
    for listing in listings_to_geocode:
        print(f"正在處理 {geocoded_count + failed_count + 1} / {total_to_process}")
        address = listing.addr
        if not address:
            failed_count += 1
            # 可以記錄日誌，例如 logger.warning(f"Listing {listing.pk} has no address to geocode.")
            continue

        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={settings.MAPS_API_KEY}"

        try:
            response = requests.get(geocode_url)
            data = response.json()

            if data['status'] == 'OK':
                location = data['results'][0]['geometry']['location']
                lat = location['lat']
                lng = location['lng']
                
                # 將經緯度儲存為 Point 物件
                listing.location = Point(lng, lat, srid=4326)
                listing.save()
                geocoded_count += 1
            elif data['status'] == 'ZERO_RESULTS':
                failed_count += 1
                # 可以將此類別的地址標記，避免未來重複嘗試，例如設置一個 is_geocoding_attempted = True 欄位
                # 或將地址存入一個「無法解析地址」的列表/模型
                print(f"無法解析地址: {address}")
            else:
                failed_count += 1
                print(f"地理編碼 API 錯誤 (地址: {address}): {data['status']} - {data.get('error_message', '')}")
            
            # API 速率限制：Google Maps Geocoding API 有 QPS (Queries Per Second) 限制
            # 免費層通常為 50 QPS，但穩妥起見，可以稍微慢一點，例如每秒 5 次請求
            time.sleep(0.2) # 延遲 200 毫秒

        except requests.exceptions.RequestException as e:
            failed_count += 1
            print(f"網絡請求失敗 (地址: {address}): {e}")
        except Exception as e:
            failed_count += 1
            print(f"處理地理編碼響應時發生未知錯誤 (地址: {address}): {e}")

    message = f"地理編碼完成。成功處理 {geocoded_count} 筆，失敗 {failed_count} 筆。總待處理：{total_to_process} 筆。"
    return JsonResponse({'status': 'success', 'message': message, 'geocoded_count': geocoded_count, 'failed_count': failed_count})

@login_required
def rent_list(request):
    """爬蟲搜尋結果頁面"""
    try:
        context = {
            'data': [],
            'error_message': None
        }
        
        # 取得搜尋參數
        county = request.GET.get('county')
        district = request.GET.get('district')
        house_type = request.GET.get('house_type')
        rent_range = request.GET.get('rent_range')

        if county:  # 只有當選擇了縣市才執行搜尋
            # 房屋類型對照表
            house_type_map = {
                '1': '整層住家',
                '2': '獨立套房',
                '3': '分租套房',
                '4': '雅房',
                '5': '店面/住店',
                '6': '辦公/住辦',
                '9': '車位/土地/其他',
                '10': '廠房/廠辦/倉庫'
            }
            
            # 租金範圍對照表
            rent_range_map = {
                'RP7': '10,000 以下',
                'RP3': '10,000 ~ 15,000',
                'RP4': '15,000 ~ 20,000',
                'RP8': '20,000 ~ 25,000',
                'RP9': '25,000 以上'
            }

            # 執行爬蟲
            crawler_data = get_rent_data(
                county=county,
                district=district,
                house_type=house_type,
                rent_range=rent_range,
                max_pages=5
            )
            
            # 將爬蟲資料存入資料庫，並記錄新資料數
            current_listings = []
            new_listings_count = 0
            for item in crawler_data:
                try:
                    defaults_dict = {
                        'title': item['title'],
                        'addr': item['addr'],
                        'level': item['level'],
                        'pattern': item['pattern'],
                        'rent': item['rent'],
                        'parking': item.get('parking', ''),
                        'area': item['area'],
                        'agent': item.get('agent', ''),
                        'update_time': item.get('update_time', ''),
                        'url': item['url']
                    }

                    listing, created = Listing.objects.update_or_create(
                        serial=item['serial'],
                        defaults=defaults_dict # 使用更新後的字典
                    )
                    
                    if created:  # 如果是新建立的資料
                        new_listings_count += 1
                    current_listings.append(listing)
                except Exception as e:
                    print(f"Error saving or geocoding listing {item.get('serial', 'N/A')}: {e}")
                    continue

            context.update({
                'data': current_listings,
                'county': county,
                'district': district,
                'house_type': house_type_map.get(house_type, ''),
                'rent_range': rent_range_map.get(rent_range, ''),
                'total_count': len(current_listings),
                'new_count': new_listings_count  # 添加新資料數量
            })
        
        return render(request, 'crawler_results.html', context)

    except Exception as e:
        return render(request, 'crawler_results.html', {
            'data': [],
            'error_message': f"發生錯誤：{str(e)}"
        })
    
@login_required # 確保用戶已登入
@user_passes_test(is_superuser) # 確保用戶是超級用戶
@require_POST # 確保只接受 POST 請求
def get_all_rent_list(request): # 僅管理員可使用
    """一次爬取所有縣市資料。"""
    # 密碼驗證（與 geocode_missing_listings 相同）
    password = request.POST.get('password')
    user = request.user
    if not user.check_password(password):
        return JsonResponse({'status': 'error', 'message': '密碼錯誤，請重新輸入。'}, status=403)

    TAIWAN_CITIES = {
        "台北市":"Taipei City", "新北市":"New Taipei City", "桃園市":"Taoyuan City", "台中市":"Taichung City",
        "台南市":"Tainan City", "高雄市":"Kaohsiung City", "基隆市":"Keelung City", "新竹市":"Hsinchu City",
        "嘉義市":"Chiayi City", "新竹縣":"Hsinchu County", "苗栗縣":"Miaoli County", "彰化縣":"Changhua County",
        "南投縣":"Nantou County", "雲林縣":"Yunlin County","嘉義縣":"Chiayi County", "屏東縣":"Pingtung County",
        "澎湖縣":"Penghu County", "金門縣":"Kinmen County", "連江縣":"Lienchiang County", "宜蘭縣":"Yilan County",
        "花蓮縣":"Hualien County", "台東縣":"Taitung County"
    }
    # chinese_cities = list(TAIWAN_CITIES.keys())
    chinese_cities = ["澎湖縣","金門縣","連江縣","宜蘭縣","花蓮縣","台東縣"] # 如果你只想爬取特定縣市，可以在這裡定義

    total_new_listings = 0
    total_errors = 0
    
    try:
        counter = 1
        print("開始爬取所有縣市資料")
        for county in chinese_cities:
            print(f"正在爬取第 {counter}/{len(chinese_cities)} 個縣市: {county}")
            try:
                crawler_data = get_rent_data(
                    county=county,
                    district=None,
                    house_type=None,
                    rent_range=None,
                    max_pages=3
                )
            except Exception as e:
                print(f"爬取 {county} 資料時發生錯誤: {e}")
                total_errors += 1
                continue # 如果爬取失敗，則跳到下一個縣市

            for item in crawler_data:
                try:
                    listing, created = Listing.objects.update_or_create(
                        serial=item['serial'],
                        defaults={
                            'title': item['title'],
                            'addr': item['addr'],
                            'level': item['level'],
                            'pattern': item['pattern'],
                            'rent': item['rent'],
                            'parking': item.get('parking', ''),
                            'area': item['area'],
                            'agent': item.get('agent', ''),
                            'update_time': item.get('update_time', ''),
                            'url': item['url']
                        }
                    )
                    if created:  # 如果是新建立的資料
                        total_new_listings += 1
                except Exception as e:
                    print(f"儲存房源 {item.get('serial', 'N/A')} 時發生錯誤: {e}")
                    total_errors += 1
                    continue
            
            # 可選：在城市之間增加短暫延遲，以對伺服器更友善
            time.sleep(1) 
            counter += 1
        message = f"所有縣市資料爬取完成。新增 {total_new_listings} 筆資料，處理中發生 {total_errors} 筆錯誤。"
        return JsonResponse({'status': 'success', 'message': message, 'new_listings_count': total_new_listings, 'error_count': total_errors})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f"發生錯誤：{str(e)}"}, status=500)

def search_database(request):
    """資料庫搜尋結果頁面"""
    queryset = Listing.objects.all()
    listings = queryset  # 用於分頁的原始查詢集

    # 取得搜尋參數
    serial = request.GET.get('serial', '').strip()
    title = request.GET.get('title', '').strip()
    address = request.GET.get('address', '').strip()
    rooms = request.GET.get('rooms', '').strip()
    price_min = request.GET.get('price_min', '').strip()
    price_max = request.GET.get('price_max', '').strip()
    area_min = request.GET.get('area_min', '').strip()
    area_max = request.GET.get('area_max', '').strip()
    agent = request.GET.get('agent', '').strip()

    # 先決定是否需要 annotate
    need_rent_num = any([price_min, price_max, request.GET.get('sort') == 'rent'])
    need_area_num = any([area_min, area_max, request.GET.get('sort') == 'area'])

    if need_rent_num:
        queryset = queryset.annotate(
            rent_clean=Replace('rent', Value(','), Value('')),
            rent_clean2=Replace('rent_clean', Value('元/月'), Value('')),
            rent_num=Cast('rent_clean2', output_field=IntegerField())
        )
    if need_area_num:
        queryset = queryset.annotate(
            area_clean=Replace('area', Value('坪'), Value('')),
            area_num=Cast('area_clean', output_field=FloatField())
        )

    # 套用搜尋條件
    if serial:
        queryset = queryset.filter(serial__icontains=serial)
    if title:
        queryset = queryset.filter(title__icontains=title)
    if address:
        queryset = queryset.filter(addr__icontains=address)
    if agent:
        queryset = queryset.filter(agent__icontains=agent)
    if rooms:
        if rooms == '4+':
            pattern_query = Q(pattern__regex=r'[4-9]\d*房(?:\(室\))?')
        else:
            pattern_query = Q(pattern__regex=rf'{rooms}\s*房(?:\s*\(室\))?')
        queryset = queryset.filter(pattern_query)
    if price_min:
        queryset = queryset.filter(rent_num__gte=int(price_min))
    if price_max:
        queryset = queryset.filter(rent_num__lte=int(price_max))
    if area_min:
        queryset = queryset.filter(area_num__gte=float(area_min))
    if area_max:
        queryset = queryset.filter(area_num__lte=float(area_max))

    # 排序
    sort = request.GET.get('sort', 'serial')
    order = request.GET.get('order', 'asc')
    if sort not in ['serial', 'title', 'addr', 'level', 'pattern', 'rent', 'parking', 'area', 'agent']:
        sort = 'serial'
    if order not in ['asc', 'desc']:
        order = 'asc'
    order_prefix = '' if order == 'asc' else '-'

    if sort == 'serial':
        queryset = queryset.annotate(
            serial_num=Cast('serial', output_field=IntegerField())
        ).order_by(f'{order_prefix}serial_num')
    elif sort == 'rent':
        queryset = queryset.order_by(f'{order_prefix}rent_num')
    elif sort == 'area':
        queryset = queryset.order_by(f'{order_prefix}area_num')
    else:
        queryset = queryset.order_by(f'{order_prefix}{sort}')

    has_ungeocoded_data = False
    # 注意：這裡應該是篩選過後的 listings，而不是所有 Listing.objects.filter
    # 如果你是對所有數據判斷，那就用 Listing.objects.filter(location__isnull=True).exists()
    # 如果是針對當前篩選出來的數據判單，就用 listings.filter(location__isnull=True).exists()
    if listings.filter(location__isnull=True).exists(): # 確保 listings 是 QuerySet
        has_ungeocoded_data = True

    # 分頁
    page = request.GET.get('page', 1)
    paginator = Paginator(queryset, 50)
    listings = paginator.get_page(page)

    # 構建搜尋參數，移除 page 參數
    search_params = request.GET.copy()
    if 'page' in search_params:
        search_params.pop('page')

    context = {
        'data': listings,
        'has_ungeocoded_data': has_ungeocoded_data, # 將這個布林值傳遞給模板
        'search_params': search_params.urlencode(),
        'search_criteria': {
            'serial': serial,
            'title': title,
            'address': address,
            'rooms': rooms,
            'price_min': price_min,
            'price_max': price_max,
            'area_min': area_min,
            'area_max': area_max,
            'agent': agent,
        },
        'total_count': queryset.count()
    }
    return render(request, 'database_results.html', context)


@login_required
def add_favorite(request, serial):
    listing = get_object_or_404(Listing, serial=serial)
    if listing not in request.user.favorites.all():
        request.user.favorites.add(listing)
        messages.success(request, '已加入收藏！')
    return redirect('search_database')

def login_view(request):
    context = {}
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        try:
            # 先檢查用戶是否存在
            user = RentUser.objects.get(username=username)
            
            # 檢查帳號是否已停用
            if not user.is_active:
                context['error_message'] = '帳號已停用，重新啟用請聯繫管理員'
                return render(request, 'login.html', context)
            
            # 驗證密碼
            user = authenticate(request, username=username, password=password)
            if user is not None:
                auth_login(request, user)
                next_url = request.GET.get('next', 'search_database')
                return redirect(next_url)
            else:
                context['error_message'] = '密碼錯誤'
        
        except RentUser.DoesNotExist:
            context['error_message'] = '帳號不存在'
    
    return render(request, 'login.html', context)

def register(request):
    error_message = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        address = request.POST.get('address', '').strip()
        password1 = request.POST.get('password1', '').strip()
        password2 = request.POST.get('password2', '').strip()
        location_point = geocode_address(address) if address else None

        if not username or not password1 or not password2:
            error_message = "請填寫所有欄位"
        elif password1 != password2:
            error_message = "兩次輸入的密碼不一致"
        elif RentUser.objects.filter(username=username).exists():
            error_message = "帳號已存在"
        else:
            # 使用 create_user 方法而不是 create
            user = RentUser.objects.create_user(
                username=username,
                address=address,
                password=password1,  # create_user 會自動處理密碼加密
                location=location_point  # 如果有地址，則儲存地理位置
            )
            messages.success(request, '註冊成功！請登入')
            return redirect('register_result')
            
    return render(request, 'register.html', {'error_message': error_message})

def register_result(request):
    return render(request, "register_result.html")
    
def logout_view(request):
    auth_logout(request)
    messages.success(request, '您已成功登出')
    return redirect('login')

def data_analysis(request):
    """資料分析頁面"""
    return render(request, 'data_analysis.html')

class RentUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = RentUser
        fields = UserCreationForm.Meta.fields + ('email',)

@login_required
def edit_profile(request):
    if request.method == 'POST':
        user = request.user
        username = request.POST.get('username')
        email = request.POST.get('email')
        new_password = request.POST.get('new_password')

        if username and username != user.username:
            if not RentUser.objects.filter(username=username).exists():
                user.username = username
            else:
                messages.error(request, '使用者名稱已存在')
                return redirect('search_database')

        if email:
            user.email = email

        if new_password:
            user.set_password(new_password)

        user.save()
        messages.success(request, '資料已更新')
        return redirect('search_database')

@login_required
def remove_favorite(request, serial):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            listing = get_object_or_404(Listing, serial=serial)
            request.user.favorites.remove(listing)
            return JsonResponse({
                'success': True,
                'message': '已從收藏移除',
                'favorites_count': request.user.favorites.count()
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    else:
        listing = get_object_or_404(Listing, serial=serial)
        request.user.favorites.remove(listing)
        messages.success(request, '已從收藏移除')
        return redirect('search_database')

@login_required
def update_address(request):
    if request.method == 'POST':
        new_address = request.POST.get('new_address')
        current_password = request.POST.get('current_password')
        location_point = geocode_address(new_address) if new_address else None

        # 驗證密碼
        if not request.user.check_password(current_password):
            return JsonResponse({
                'success': False,
                'message': '密碼錯誤，請重新輸入'
            })

        if new_address:
            request.user.address = new_address
            request.user.location = location_point  # 更新地理位置
            request.user.save()
            return JsonResponse({
                'success': True,
                'message': '地址已更新'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': '請提供有效的地址'
            })
    return JsonResponse({
        'success': False,
        'message': '無效的請求方法'
    })

@login_required
def update_user_address(request): #待確認
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_address = request.POST.get('new_address')

        user = request.user
        if user.check_password(current_password):
            user.address = new_address
            if new_address: # 只有當地址非空時才進行地理編碼
                user.location = geocode_address(new_address)
            else:
                user.location = None # 地址清空時，位置也清空
            user.save()
            messages.success(request, '地址更新成功！')
        else:
            messages.error(request, '密碼不正確，地址更新失敗。')
        return redirect('search_database') # 假設你的資料庫搜尋頁面是這個 URL 名稱
    return redirect('search_database') # 或者返回錯誤頁面

# your_app/views.py
@login_required
def search_nearby_rentals(request):
    user = request.user
    total_count = 0
    error_message = None
    search_criteria = {}
    processed_listings_for_template = [] # 用於表格和地圖的處理後數據

    # 檢查使用者是否設定了地址
    if not user.address:
        messages.warning(request, '您尚未設定地址，請先修改您的地址。')
        return redirect('search_database') # 假設你的資料庫搜尋頁面是這個 URL 名稱
    
    # 取得滑桿值，預設為 5
    radius_km = request.GET.get('nearby', '5')
    try:
        radius_km = float(radius_km)
    except ValueError:
        radius_km = 5

    search_criteria['nearby'] = radius_km

    try:
        # 在 ORM 查詢中直接計算距離，使用 spheroid=True 進行更精確的球面距離計算
        # 假設你的 Listing.location 是 PointField (SRID=4326)
        nearby_listings_query = Listing.objects.annotate(
            distance_from_user=Distance('location', user.location, spheroid=True)
        ).filter(
            distance_from_user__lte=D(km=radius_km)
        ).order_by('distance_from_user') # 按距離排序

        total_count = nearby_listings_query.count()

        paginator = Paginator(nearby_listings_query, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # 遍歷分頁後的房源，為模板和地圖準備數據
        for listing_item in page_obj.object_list:
            item_data = {
                'serial': listing_item.serial,
                'title': listing_item.title,
                'addr': listing_item.addr,
                'rent': str(listing_item.rent), # 確保為字串以防 json.dumps 出錯
                'level': listing_item.level,
                'pattern': listing_item.pattern,
                'parking': listing_item.parking,
                'area': listing_item.area,
                'agent': listing_item.agent,
                'url': listing_item.url,
                'pk': listing_item.pk,
            }
            # 計算並添加距離 (已在 annotate 中處理)
            if listing_item.distance_from_user:
                item_data['distance_km'] = round(listing_item.distance_from_user.km, 2)
            else:
                item_data['distance_km'] = None # 如果沒有距離信息，則為 None

            # 處理地圖所需的地理位置信息
            if listing_item.location:
                item_data['location'] = {
                    'type': 'Point',
                    'coordinates': [listing_item.location.x, listing_item.location.y] # 經度, 緯度
                }
            else:
                item_data['location'] = None
            processed_listings_for_template.append(item_data)

    except Exception as e:
        error_message = f"查詢附近房源時發生錯誤: {e}"
        messages.error(request, error_message)
        # 錯誤時清空數據
        processed_listings_for_template = []
        # 仍創建一個空的 page_obj 以便模板處理分頁 (如果需要)
        # 或者直接讓 page_obj 保持原樣（一個空的 Paginator 結果）
        # 此處保留 page_obj 讓模板中的分頁導航結構不受影響，儘管內容為空
        page_obj = Paginator([], 10).get_page(1)


    # 為收藏按鈕優化：預先獲取用戶收藏的 serial 列表
    user_favorite_serials = set(user.favorites.values_list('serial', flat=True)) if user.is_authenticated else set()

    # 將用戶位置轉為 JSON 格式
    user_lat_json = json.dumps(user.location.y) if user.location else 'null'
    user_lng_json = json.dumps(user.location.x) if user.location else 'null'

    # 為了分頁連結能夠保留搜尋參數
    search_params = request.GET.urlencode()

    context = {
        'data': page_obj, # 傳遞 page_obj 以便模板中處理分頁導航
        'processed_listings': processed_listings_for_template, # 傳遞給表格和地圖渲染的數據
        'search_criteria': search_criteria,
        'total_count': total_count,
        'error_message': error_message,
        'search_params': search_params,
        'rental_data_for_map_json': json.dumps(processed_listings_for_template), # 地圖數據現在也直接使用 processed_listings_for_template
        'Maps_api_key': settings.MAPS_API_KEY,
        'user_location_lat_json': user_lat_json,
        'user_location_lng_json': user_lng_json,
        'user_favorite_serials': user_favorite_serials, # 傳遞預先獲取的收藏列表
    }
    return render(request, 'nearby_rentals.html', context)

@login_required
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        # 驗證舊密碼
        if not request.user.check_password(old_password):
            return JsonResponse({
                'success': False,
                'message': '舊密碼錯誤'
            })
        
        # 驗證新密碼是否與舊密碼相同
        if new_password1 == old_password:
            return JsonResponse({
                'success': False,
                'message': '新密碼不得與舊密碼相同'
            })

        # 驗證新密碼
        if new_password1 != new_password2:
            return JsonResponse({
                'success': False,
                'message': '兩次輸入的新密碼不一致'
            })
            
        # 更新密碼
        try:
            request.user.set_password(new_password1)
            request.user.save()
            # 登出用戶
            auth_logout(request)
            return JsonResponse({
                'success': True,
                'message': '密碼已更新成功'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            })
    
    return JsonResponse({
        'success': False,
        'message': '無效的請求方法'
    })

@login_required
def deactivate_account(request):
    if request.method == 'POST':
        password = request.POST.get('confirm_password')
        user = request.user
        
        # 驗證密碼
        if not user.check_password(password):
            return JsonResponse({
                'success': False,
                'message': '密碼錯誤'
            })
        
        # 檢查是否為管理員帳號
        if user.is_staff or user.is_superuser:
            return JsonResponse({
                'success': False,
                'message': '管理員帳號不能被停用'
            })
            
        try:
            # 停用帳號
            user.is_active = False
            user.save()
            
            # 記錄停用時間（如果你的 User 模型有這個欄位）
            # user.deactivated_at = timezone.now()
            # user.save(update_fields=['deactivated_at'])
            
            # 登出用戶
            auth_logout(request)
            
            return JsonResponse({
                'success': True,
                'message': '帳號已成功停用，請聯繫管理員重新啟用'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'停用帳號時發生錯誤：{str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'message': '無效的請求方法'
    })

@login_required
def delete_account(request):
    if request.method == 'POST':
        password = request.POST.get('confirm_password')
        user = request.user
        
        # 驗證密碼
        if not user.check_password(password):
            return JsonResponse({
                'success': False,
                'message': '密碼錯誤'
            })
            
        try:
            # 先移除所有收藏
            user.favorites.clear()
            # 刪除帳號
            user.delete()
            # 登出用戶
            auth_logout(request)
            
            return JsonResponse({
                'success': True,
                'message': '帳號已成功刪除'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'刪除帳號時發生錯誤：{str(e)}'
            })
    
    return JsonResponse({
        'success': False,
        'message': '無效的請求方法'
    })

TAIWAN_CITIES = {"台北市":"Taipei City", "新北市":"New Taipei City", "桃園市":"Taoyuan City", "台中市":"Taichung City",
                  "台南市":"Tainan City", "高雄市":"Kaohsiung City", "基隆市":"Keelung City", "新竹市":"Hsinchu City",
                  "嘉義市":"Chiayi City", "新竹縣":"Hsinchu County", "苗栗縣":"Miaoli County", "彰化縣":"Changhua County",
                  "南投縣":"Nantou County", "雲林縣":"Yunlin County","嘉義縣":"Chiayi County", "屏東縣":"Pingtung County",
                  "澎湖縣":"Penghu County", "金門縣":"Kinmen County", "連江縣":"Lienchiang County", "宜蘭縣":"Yilan County",
                  "花蓮縣":"Hualien County", "台東縣":"Taitung County"}

chinese_cities = list(TAIWAN_CITIES.keys())
english_cities = list(TAIWAN_CITIES.values())

# Sort cities by length in descending order to prioritize longer (more specific) matches
# 例如，"新北市" 在 "新" 之前，"新竹縣" 在 "新竹市" 之前
# 這樣可以避免 "新竹市" 匹配到 "新竹縣" 的地址
sorted_chinese_cities = sorted(chinese_cities, key=len, reverse=True)

# 資料預處理函數
def preprocess_listing_data(listings):
    data = []
    for listing in listings:
        city_zh = '其他'
        found_city = False

        for city in sorted_chinese_cities:
            if listing.addr.startswith(city):
                city_zh = city
                found_city = True
                break

        if not found_city:
            for city in chinese_cities:
                if city in listing.addr:
                    city_zh = city
                    break

        try:
            rent = float(listing.clean_rent())
        except (ValueError, TypeError):
            rent = np.nan
        try:
            area = float(listing.clean_area())
        except (ValueError, TypeError):
            area = np.nan
        try:
            pattern_cleaned = listing.clean_pattern()
            room_count = int(pattern_cleaned) if pattern_cleaned.isdigit() else np.nan
        except (ValueError, TypeError, AttributeError):
            room_count = np.nan

        data.append({
            '流水號': listing.serial,
            '標題': listing.title,
            '地址': listing.addr,
            '縣市': city_zh,
            '租金': rent,
            '坪數': area,
            '房數': room_count,
            '更新時間': listing.update_time,
            '網址': listing.url
        })

    df = pd.DataFrame(data)

    # 1. 將非數值轉換為 NaN (errors='coerce' 會自動將無法轉換的變成 NaN)
    df['租金'] = pd.to_numeric(df['租金'], errors='coerce')
    df['坪數'] = pd.to_numeric(df['坪數'], errors='coerce')
    df['房數'] = pd.to_numeric(df['房數'], errors='coerce')

    # 2. 填充 NaN 值
    # 計算中位數時，Pandas 會自動忽略 NaN 值，所以可以在填充前計算
    median_rent = df['租金'].median()
    median_area = df['坪數'].median()
    median_room_count = df['房數'].median()

    # 如果所有值都是 NaN，median() 可能返回 NaN，這時需要提供一個默認值
    # 例如，如果沒有任何有效租金，就用 0 或其他合理值填充
    median_rent = 0 if pd.isna(median_rent) else median_rent
    median_area = 0 if pd.isna(median_area) else median_area
    median_room_count = 0 if pd.isna(median_room_count) else median_room_count


    df['租金'].fillna(median_rent, inplace=True)
    df['坪數'].fillna(median_area, inplace=True)
    df['房數'].fillna(median_room_count, inplace=True)

    # --- 新增：移除租金與坪數極端值的邏輯 ---
    initial_rows = len(df)
    # logger.info(f"在極端值處理前，DataFrame 行數: {initial_rows}")

    # 3. 定義極端值範圍 (使用 IQR 方法，更穩健)
    # 租金極端值處理
    Q1_rent = df['租金'].quantile(0.05) # 可以調整下限，例如 0.01 或 0.05
    Q3_rent = df['租金'].quantile(0.95) # 可以調整上限，例如 0.95 或 0.99
    IQR_rent = Q3_rent - Q1_rent
    # 通常會用 Q1 - 1.5*IQR 和 Q3 + 1.5*IQR，但這裡我們直接用分位數來定義合理範圍
    # 這樣更直接，也避免負值或過高值
    lower_bound_rent = max(0, Q1_rent - 1.5 * IQR_rent) # 租金不應小於 0
    upper_bound_rent = Q3_rent + 1.5 * IQR_rent

    # 坪數極端值處理
    Q1_area = df['坪數'].quantile(0.05)
    Q3_area = df['坪數'].quantile(0.95)
    IQR_area = Q3_area - Q1_area
    lower_bound_area = max(0, Q1_area - 1.5 * IQR_area) # 坪數不應小於 0
    upper_bound_area = Q3_area + 1.5 * IQR_area

    # 篩選掉極端值
    df_cleaned = df[
        (df['租金'] >= lower_bound_rent) & (df['租金'] <= upper_bound_rent) &
        (df['坪數'] >= lower_bound_area) & (df['坪數'] <= upper_bound_area)
    ].copy() # 使用 .copy() 避免 SettingWithCopyWarning

    removed_rows = initial_rows - len(df_cleaned)
    # logger.info(f"極端值處理後，DataFrame 行數: {len(df_cleaned)}，移除了 {removed_rows} 行極端值。")

    return df_cleaned


@login_required
def data_analysis_view(request):
    user = request.user
    selected_data_source = request.GET.get('data_source', 'all_data')
    selected_bar_metric = request.GET.get('bar_metric', 'count')  # 預設物件總數
    selected_pie_city = request.GET.get('pie_city', '台北市') # Default to a Chinese city
    selected_hist_city = request.GET.get('hist_city', '台北市') # Default to a Chinese city

    # 取得資料
    listings = user.favorites.all() if selected_data_source == 'my_collection' else Listing.objects.all()
    df = preprocess_listing_data(listings)

    # --- 長條圖 ---
    bar_metric_map_zh = {
        'count': '各縣市物件總數',
        'avg_rent': '各縣市平均租金',
        'avg_rent_per_area': '各縣市平均每坪租金',
        'avg_area': '各縣市平均坪數'
    }

    bar_chart = None
    bar_title = bar_metric_map_zh[selected_bar_metric] # Initialize with default title

    if df is not None and not df.empty:
        # Pass the DataFrame and chinese_cities to the charting functions
        if selected_bar_metric == 'count':
            fig = charts.plot_count_by_city(df, chinese_cities)
        elif selected_bar_metric == 'avg_rent':
            fig = charts.plot_avg_rent_by_city(df, chinese_cities)
        elif selected_bar_metric == 'avg_rent_per_area':
            fig = charts.plot_avg_rent_per_area_by_city(df, chinese_cities)
        elif selected_bar_metric == 'avg_area':
            fig = charts.plot_avg_area_by_city(df, chinese_cities)
        else:
            fig = charts.plot_count_by_city(df, chinese_cities) # Fallback

        if fig:
            buf = BytesIO()
            fig.savefig(buf, format='png')
            buf.seek(0)
            bar_chart = base64.b64encode(buf.read()).decode()
            plt.close(fig)
        else:
            bar_chart = None
    else:
        bar_chart = None # No data to plot

    # --- 圓餅圖 ---
    pie_chart = None
    pie_title_zh = f"{selected_pie_city}房型占比圓餅圖"
    if df is not None and not df.empty and selected_pie_city in df['縣市'].values: # Check against '縣市'
        fig = charts.plot_pie_room_type(df, selected_pie_city)
        if fig:
            buf = BytesIO()
            fig.savefig(buf, format='png')
            buf.seek(0)
            pie_chart = base64.b64encode(buf.read()).decode()
            plt.close(fig)

    # --- 直方圖 ---
    hist_chart = None
    hist_title_zh = f"{selected_hist_city}各坪數區間平均租金直方圖"
    if df is not None and not df.empty and selected_hist_city in df['縣市'].values: # Check against '縣市'
        fig = charts.plot_hist_avg_rent_by_area_bin(df, selected_hist_city)
        if fig:
            buf = BytesIO()
            fig.savefig(buf, format='png')
            buf.seek(0)
            hist_chart = base64.b64encode(buf.read()).decode()
            plt.close(fig)

    favorites_count = user.favorites.count() if user.is_authenticated else 0

    context = {
        'bar_chart': bar_chart, # Changed to singular as only one bar chart is generated
        'bar_title_zh': bar_title, # Changed to singular to reflect the single chart
        'bar_metric': selected_bar_metric,
        'bar_metric_map_zh': bar_metric_map_zh,
        'pie_chart': pie_chart,
        'pie_title_zh': pie_title_zh,
        'pie_city': selected_pie_city,
        'hist_chart': hist_chart,
        'hist_title_zh': hist_title_zh,
        'hist_city': selected_hist_city,
        'chinese_cities': chinese_cities,
        'selected_data_source': selected_data_source,
        'favorites_count': favorites_count,
    }
    return render(request, 'data_analysis.html', context)