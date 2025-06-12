from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('set/<str:set_number>/', views.set_detail, name='set_detail'),
    path("packs/", views.pack_list, name="pack_list"),
    path('account/', views.account, name='account'),
    path('profile/', views.profile, name='profile'),
    path('i18n/', include('django.conf.urls.i18n')),
]
