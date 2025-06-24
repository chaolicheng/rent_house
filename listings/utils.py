# your_app/utils.py (或直接在 views.py 中)
import requests
from django.conf import settings
from django.contrib.gis.geos import Point

def geocode_address(address):
    api_key = settings.MAPS_API_KEY
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        'address': address,
        'key': api_key,
        'language': 'zh-TW' # 設定中文結果
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status() # 對於 4xx/5xx 錯誤拋出異常
        data = response.json()

        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            latitude = location['lat']
            longitude = location['lng']
            return Point(longitude, latitude, srid=4326) # 注意：Point 是 (經度, 緯度)
        elif data['status'] == 'ZERO_RESULTS':
            print(f"No results found for address: {address}")
            return None
        else:
            print(f"Geocoding error for {address}: {data['status']}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network error during geocoding: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None