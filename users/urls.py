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

from django.contrib.auth import views
from django.urls import path ,include
from users.views import *
from api.views import employee_attendance_page

urlpatterns = [
    path("login/as/admin/",admin_login, name="admin_login"),
       path(
        "attendance/<int:user_id>/",
        employee_attendance_page,
        name="employee_attendance_page",
    ),
    path(
    "waiters/",
    waiter_dashboard,
    name="waiter_dashboard",
),
 path(
        "day-off/",
        day_off_dashboard,
        name="day_off_dashboard",
    ),

        path(
        "attendance/",
        manager_attendance_dashboard,
        name="manager_attendance_dashboard",
    ),

  

]



