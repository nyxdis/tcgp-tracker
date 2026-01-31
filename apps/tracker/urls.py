# pylint: disable=no-member
"""Tracker app urls."""

from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("health/", views.health_check, name="health_check"),
    path("set/<str:set_number>/", views.set_detail, name="set_detail"),
    path("packs/", views.pack_list, name="pack_list"),
    path("account/", views.account, name="account"),
    path("profile/", views.profile, name="profile"),
    path("i18n/", include("django.conf.urls.i18n")),
    path("users/search/", views.user_search, name="user_search"),
    path(
        "users/send_friend_request/<int:user_id>/",
        views.send_friend_request,
        name="send_friend_request",
    ),
    path(
        "friends/accept/<int:request_id>/",
        views.accept_friend_request,
        name="accept_friend_request",
    ),
    path("profile/<str:username>/", views.public_profile, name="public_profile"),
]
