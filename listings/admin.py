from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.admin import SimpleListFilter
from .models import RentUser, Listing
from django.utils.html import format_html
from django.db.models import Count
from django.utils import timezone
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from auditlog.models import LogEntry
import logging

# Register your models here.

# 設定日誌
logger = logging.getLogger(__name__)

class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('actor', 'action', 'content_type', 'object_repr', 'timestamp')
    search_fields = ('actor__username', 'object_repr')
    list_filter = ('action', 'content_type', 'timestamp')

@receiver(m2m_changed, sender=RentUser.favorites.through)
def log_favorite_change(sender, instance, action, pk_set, **kwargs):
    if action in ['post_add', 'post_remove']:
        for pk in pk_set:
            print(f"User {instance.username} {action} favorite listing {pk}")
            # 你可以在這裡寫入自訂日誌或資料表

@admin.register(RentUser)
class RentUserAdmin(UserAdmin):
    list_display = ('username', 'address',  'date_joined', 'last_login', 'is_active', 'is_staff', 'favorites_count')
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

class CityFilter(SimpleListFilter):
    title = '縣市'
    parameter_name = 'city'

    def lookups(self, request, model_admin):
        # 取得所有不同的前三字（縣市）
        cities = set(obj.addr[:3] for obj in model_admin.model.objects.all() if obj.addr)
        return [(city, city) for city in cities]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(addr__startswith=self.value())
        return queryset

@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('serial', 'title', 'addr', 'rent', 'area', 'favorited_count', 'created_at', 'updated_at')
    list_filter = (CityFilter,)
    search_fields = ('serial', 'title', 'addr', 'agent')
    ordering = ('addr',)
    readonly_fields = ('favorited_by_users',)
    
    def title_link(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.url, obj.title)
    title_link.short_description = '標題'
    
    def rent_display(self, obj):
        # 確保 rent 欄位存在且為字串類型，再進行替換
        return obj.rent.replace(',', '') if obj.rent else ''
    rent_display.short_description = '租金'
    
    def area_display(self, obj):
        # 確保 area 欄位存在且為字串類型，再進行替換
        return obj.area.replace('坪', '') if obj.area else ''
    area_display.short_description = '坪數'
    
    def favorited_count(self, obj):
        return obj.favorited_by.count()
    favorited_count.short_description = '收藏數'
    
    def favorited_by_users(self, obj):
        users = obj.favorited_by.all()
        return format_html('<br>'.join([user.username for user in users])) # 使用 <br> 讓每個用戶名換行顯示
    favorited_by_users.short_description = '收藏者'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            favorite_count=Count('favorited_by')
        )

    # --- 新增：自動帶入預設資料的方法 ---
    def get_changeform_initial_data(self, request):
        """
        在新增資料時，自動帶入預設值。
        """
        initial_data = super().get_changeform_initial_data(request)
        
        # 只有在新增模式下才設定預設值
        if 'add' in request.resolver_match.url_name:
            # 假設 'level' 和 'pattern' 是你的 Listing 模型中的欄位名稱
            initial_data['level'] = '樓層：--'
            initial_data['pattern'] = '--房(室)--廳--衛'
            
            # 你也可以根據需要，為其他欄位設定預設值，例如
            initial_data['rent'] = '1,001 元/月'
            initial_data['area'] = '1.1 坪'
            initial_data['title'] = '新房屋物件'
            initial_data['url'] = 'https://rent.housefun.com.tw/rent/house/serial/'
        
        return initial_data


# 註冊其他 Admin actions
@admin.action(description='標記為已更新')
def mark_updated(modeladmin, request, queryset):
    updated_count = queryset.update(update_time=timezone.now())
    logger.info(f'管理員 {request.user.username} 更新了 {updated_count} 筆物件資料')
    modeladmin.message_user(request, f'成功更新了 {updated_count} 筆物件資料。') # 顯示成功訊息

# 將自定義 action 加入到 ListingAdmin
admin.site.add_action(mark_updated, 'mark_updated')


# 註冊 Admin Site 設定
admin.site.site_header = '租屋網站管理系統'
admin.site.site_title = '租屋網站管理'
admin.site.index_title = '後台管理'