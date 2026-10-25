
from django.urls import path

from . import views


app_name = "chat"

urlpatterns = [
    path("staff/", views.chat_staff_list, name="staff-list"),
    path("", views.chat_page, name="chat-page"),
]
