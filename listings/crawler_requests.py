import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_rent_data():
    url = 'https://rent.housefun.com.tw/'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    results = []
    try:
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        listings = soup.select('.DataList.both > li')

        for item in listings:
            try:
                a_tag = item.find('a', href=True)
                itemurl = a_tag['href'] if a_tag else ''
                serial = itemurl.rstrip('/').split('/')[-1] if itemurl else ''
                title = item.find(class_='title').get_text(strip=True) if item.find(class_='title') else ''
                addr = item.find(class_='addr').get_text(strip=True) if item.find(class_='addr') else ''
                level = item.find(class_='level').get_text(strip=True) if item.find(class_='level') else ''
                pattern = item.find(class_='pattern').get_text(strip=True) if item.find(class_='pattern') else ''
                infos = item.find_all(class_='infos')
                # 預設空字串
                rent = parking = area = landlord = update_time = ''
                # 根據 infos 長度推測欄位
                if len(infos) == 4:
                    rent = infos[0].get_text(strip=True)
                    area = infos[1].get_text(strip=True)
                    landlord = infos[2].get_text(strip=True)
                    update_time = infos[3].get_text(strip=True)
                elif len(infos) == 5:
                    rent = infos[0].get_text(strip=True)
                    parking = infos[1].get_text(strip=True)
                    area = infos[2].get_text(strip=True)
                    landlord = infos[3].get_text(strip=True)
                    update_time = infos[4].get_text(strip=True)

                data = {
                    'serial': serial,
                    'title': title,
                    'addr': addr,
                    'level': level,
                    'pattern': pattern,
                    'rent': rent,
                    'parking': parking,
                    'area': area,
                    'landlord': landlord,
                    'update_time': update_time,
                    'url': itemurl
                }
                results.append(data)
            except Exception as e:
                print(f"Error parsing listing: {e}")
                continue
        return results
    except Exception as e:
        print(f"Error: {e}")
        return []