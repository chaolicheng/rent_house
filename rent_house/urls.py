"""
URL configuration for rent_house project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from listings import views
# from . import views # 假設你的 views.py 在同一個應用程式下

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('rent_list/', views.rent_list, name='rent_list'),
    path('get_all_rent_list/', views.get_all_rent_list),
    path('search_database/', views.search_database, name='search_database'),
    path('favorite/<serial>', views.add_favorite, name='add_favorite'),
    path('register/', views.register, name='register'),
    path('register_result/', views.register_result, name='register_result'),
    path('data-analysis/', views.data_analysis_view, name='data_analysis'),
    path('update_address/', views.update_address, name='update_address'),
    path('update-user-address/', views.update_user_address, name='update_user_address'),
    path('search-nearby-rentals/', views.search_nearby_rentals, name='search_nearby_rentals'),
    path('change_password/', views.change_password, name='change_password'),
    path('deactivate_account/', views.deactivate_account, name='deactivate_account'),
    path('delete_account/', views.delete_account, name='delete_account'),
    path('remove_favorite/<str:serial>/', views.remove_favorite, name='remove_favorite'),
    path('geocode_missing/', views.geocode_missing_listings, name='geocode_missing_listings'),
    path('get_all_rent_list/', views.get_all_rent_list, name='get_all_rent_list'),
]
