
from django.urls import path

from . import views

urlpatterns = [
    path(
        "login/",
        views.restaurant_login,
        name="restaurant_login",
    ),
    path(
        "dashboard/",
        views.restaurant_dashboard,
        name="restaurant_dashboard",
    ),
    path(
        "logout/",
        views.restaurant_logout,
        name="restaurant_logout",
    ),
     path(
        "online/profile/save/",
        views.restaurant_profile_update,
        name="restaurant_profile_update",
    ),
]
