from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('set/<str:set_number>/', views.set_detail, name='set_detail'),
    path("packs/", views.pack_list, name="pack_list"),
    path('account/', views.account, name='account'),
]
