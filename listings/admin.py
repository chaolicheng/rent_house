from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import RentUser, Listing
from django.utils.html import format_html
from django.db.models import Count
from django.utils import timezone
import logging

# Register your models here.

# 設定日誌
logger = logging.getLogger(__name__)

@admin.register(RentUser)
class RentUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'date_joined', 'last_login', 'is_active', 'is_staff', 'favorites_count')
    list_filter = ('is_active', 'is_staff', 'date_joined', 'last_login')
    search_fields = ('username', 'email')
    ordering = ('-date_joined',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('收藏資訊', {'fields': ('favorites',)}),
    )
    
    def favorites_count(self, obj):
        return obj.favorites.count()
    favorites_count.short_description = '收藏數'

    def save_model(self, request, obj, form, change):
        """記錄管理員的操作"""
        if change:
            logger.info(f'管理員 {request.user.username} 修改了使用者 {obj.username} 的資料')
        else:
            logger.info(f'管理員 {request.user.username} 創建了新使用者 {obj.username}')
        super().save_model(request, obj, form, change)

@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('serial', 'title_link', 'addr', 'rent_display', 'area_display', 
                   'update_time', 'favorited_count')
    list_filter = ('update_time',)
    search_fields = ('serial', 'title', 'addr', 'landlord')
    ordering = ('-update_time',)
    readonly_fields = ('favorited_by_users',)
    
    def title_link(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.url, obj.title)
    title_link.short_description = '標題'
    
    def rent_display(self, obj):
        return obj.rent.replace(',', '')
    rent_display.short_description = '租金'
    
    def area_display(self, obj):
        return obj.area.replace('坪', '')
    area_display.short_description = '坪數'
    
    def favorited_count(self, obj):
        return obj.favorited_by.count()
    favorited_count.short_description = '收藏數'
    
    def favorited_by_users(self, obj):
        users = obj.favorited_by.all()
        return '\n'.join([user.username for user in users])
    favorited_by_users.short_description = '收藏者'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            favorite_count=Count('favorited_by')
        )

# 註冊其他 Admin actions
@admin.action(description='標記為已更新')
def mark_updated(modeladmin, request, queryset):
    queryset.update(update_time=timezone.now())
    logger.info(f'管理員 {request.user.username} 更新了 {queryset.count()} 筆物件資料')

# 註冊 Admin Site 設定
admin.site.site_header = '租屋網站管理系統'
admin.site.site_title = '租屋網站管理'
admin.site.index_title = '後台管理'