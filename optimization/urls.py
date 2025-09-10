from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_view, name='upload'),
    path('get_container_sizes/<str:container_type>/', views.get_container_sizes, name='get_container_sizes'),
]
