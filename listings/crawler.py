# app/crawler.py

from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import random
import os # 導入 os 模組
import undetected_chromedriver as uc
import requests
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from .models import Listing
import re

def get_rent_data(county=None, district=None, house_type=None, rent_range=None, max_pages=5):
    """
    爬取租屋資料
    county: 縣市
    district: 區域
    house_type: 房屋類型
    rent_range: 租金範圍
    max_pages: 最大爬取頁數，預設為5
    """
    try:
        # 建構 URL
        base_url = "https://rent.housefun.com.tw/"
        
        # 處理縣市和區域
        if county:
            # 加入 region/ 和編碼後的縣市名稱
            encoded_county = '/'.join(s for s in county.split('/') if s)
            url = f"{base_url}region/{encoded_county}"
            
            # 如果有選擇特定區域且不是「全區」，則加入區域
            if district and district != "全區":
                encoded_district = '/'.join(s for s in district.split('/') if s)
                url += f"_{encoded_district}"
            
            # 加入結尾的斜線
            url += "/"
            
            # 添加查詢參數
            params = []
            if house_type:
                params.append(f"purpid={house_type}")
            if rent_range:
                params.append(f"rpid={rent_range}")
            if params:
                url += "?" + "&".join(params)
        else:
            url = base_url

        print(f"搜尋 URL: {url}")  # 除錯用

        options = uc.ChromeOptions()
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        options.add_argument(f'user-agent={user_agent}')
        options.add_argument('--headless=new')
        driver = uc.Chrome(options=options)
        driver.get(url)
        
        results = []
        current_page = 1
        wait = WebDriverWait(driver, 10)

        while current_page <= max_pages:
            print(f"正在爬取第 {current_page} 頁")
            try:
                # 等待房屋列表載入
                listings = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "DataList,both")))
                if len(listings) == 0: break
                # 處理當前頁面的列表
                for item in listings:
                    try:
                        infos = item.find_elements(By.CLASS_NAME, "infos")
                        itemurl = item.find_element(By.TAG_NAME, 'a').get_attribute('href')
                        data = {
                            'serial': itemurl.rstrip('/').split('/')[-1],
                            'title': item.find_element(By.CLASS_NAME, 'title').text,
                            'addr': item.find_element(By.CLASS_NAME, 'addr').text,
                            'level': item.find_element(By.CLASS_NAME, 'pattern').text,
                            'pattern': item.find_element(By.CLASS_NAME, 'level').text,
                            'rent': '',
                            'parking': '',
                            'area': '',
                            'agent': '',
                            'update_time': '',
                            'url': itemurl
                        }

                        # 根據 infos 長度推測欄位，並安全抓值
                        if len(infos) == 4:
                            data['rent'] = infos[0].text
                            data['area'] = infos[1].text
                            data['agent'] = infos[2].text
                            data['update_time'] = infos[3].text
                        elif len(infos) == 5:
                            data['rent'] = infos[0].text
                            data['parking'] = infos[1].text
                            data['area'] = infos[2].text
                            data['agent'] = infos[3].text
                            data['update_time'] = infos[4].text

                        results.append(data)
                    except Exception as e:
                        print(f"解析列表項目時發生錯誤: {e}")
                        continue
                if len(listings) >= 10:
                    if current_page < max_pages:
                        xpath = f"//ul[@class='m-pagination-bd']/li/a[text()='{current_page+1}']"
                        try:
                            next_button = driver.find_element(By.XPATH, xpath)
                            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", next_button)
                            current_page = current_page + 1
                        except Exception as e:
                            print(f"翻頁失敗：{e}")
                            break
                    else:
                        break
                else:
                    break

            except Exception as e:
                print(f"處理第 {current_page} 頁時發生錯誤: {e}")
                break

        return results

    except Exception as e:
        print(f"爬蟲過程發生錯誤: {e}")
        return []
    
    finally:
        driver.quit()
