"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
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

from django.urls import path ,include

from ui.views import admin_table_detail, admin_tables , test
from users.views import manager_attendance_page

urlpatterns = [

   
    path("tables/<int:table_id>/", admin_table_detail, name="admin_table_detail"),
    path("test/",test, name="test"),

    path("licensing/", include("licensing.urls")),
    path("tables/", include("tables.urls")),
     path("online/", include("online_cloud.urls")),
     path("menu/", include("menu.urls")),
    path(
        "attendance/",
        manager_attendance_page,
        name="manager_attendance",
    ),
]


