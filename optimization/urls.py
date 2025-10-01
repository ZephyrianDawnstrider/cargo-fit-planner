from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_view, name='upload'),
    path('get_container_sizes/<int:categorytypeid>/', views.get_container_sizes, name='get_container_sizes'),
    path('download/<str:format_type>/', views.download_plan, name='download_plan'),
]
