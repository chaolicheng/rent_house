from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.gis.db import models as gis_models # 引入 gis_models
from simple_history.models import HistoricalRecords  # 引入歷史記錄模型
from auditlog.registry import auditlog
from django.utils import timezone
import re


class RentUser(AbstractUser):
    """租屋網站使用者模型，繼承 Django 內建的使用者功能"""
    address = models.CharField(max_length=255, blank=True, null=True, verbose_name="地址")
    # PointField 用於儲存經緯度座標
    # srid=4326 表示使用 WGS84 座標系統，這是 GPS 和 Google Maps 普遍使用的標準
    location = gis_models.PointField(blank=True, null=True, srid=4326, verbose_name="地理位置")
    favorites = models.ManyToManyField(
        'Listing',
        related_name='favorited_by',
        blank=True,
        verbose_name='收藏房源'
    )
    
    def __str__(self):
        return self.username

    class Meta:
        verbose_name = '使用者'
        verbose_name_plural = '使用者'

    def get_activity_stats(self):
        """獲取使用者活動統計"""
        return {
            'favorites_count': self.favorites.count(),
            'last_login': self.last_login,
            'date_joined': self.date_joined,
        }
    
    history = HistoricalRecords()

class Listing(models.Model):
    serial = models.CharField(max_length=20, unique=True)  # 流水號，唯一
    title = models.CharField(max_length=255)
    addr = models.CharField(max_length=255)
    level = models.CharField(max_length=100)
    pattern = models.CharField(max_length=100)
    rent = models.CharField(max_length=50, blank=True, null=True) # 原始租金字符串
    PARKING_CHOICES = [
        ("", "無"),
        ("(含車位)", "含車位"),
    ]
    parking = models.CharField(max_length=20, choices=PARKING_CHOICES, blank=True)  # 停車位，允許空值
    area = models.CharField(max_length=50, blank=True, null=True) # 原始坪數字符串
    agent = models.CharField(max_length=100, blank=True)
    update_time = models.CharField(max_length=100, blank=True)
    url = models.URLField(max_length=200, unique=True)  # 房源網址，唯一
    # 房源的地理位置
    location = gis_models.PointField(srid=4326, blank=True, null=True, verbose_name="地理位置")
    created_at = models.DateTimeField(auto_now_add=True)   # 新增時自動填入
    updated_at = models.DateTimeField(auto_now=True)  # 更新時自動填入
    class Meta:
        verbose_name = '租屋物件'
        verbose_name_plural = '租屋物件'
        ordering = ['-update_time']  # 改回使用 update_time 而不是 updated_at

    def __str__(self):
        return f"{self.title} - {self.addr}"
    
    def clean_rent(self):
        """移除租金中的貨幣符號和逗號"""
        return self.rent.replace('元/月', '').replace(',', '')
    
    def clean_area(self):
        """移除坪數單位"""
        return self.area.replace('坪', '')

    def clean_pattern(self):
        """擷取房間數量"""
        match = re.search(r'(\d+)房', self.pattern)
        return match.group(1) if match else ''
    
    def get_listing_stats(self):
        """獲取物件統計資訊"""
        return {
            'favorited_count': self.favorited_by.count(),
            'update_time': self.update_time,  # 改回使用原有的 update_time
        }
    
    history = HistoricalRecords()  # 添加歷史記錄功能

auditlog.register(RentUser)
auditlog.register(Listing)