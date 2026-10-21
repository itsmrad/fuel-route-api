from django.contrib import admin
from django.urls import path

from routing import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/route/', views.route_api, name='route_api'),
    path('api/route/map/', views.route_map, name='route_map'),
    path('api/openapi.yaml', views.openapi, name='openapi'),
]

handler404 = views.not_found
handler500 = views.server_error
