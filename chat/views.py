from django.shortcuts import render

# Create your views here.

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

User = get_user_model()


@login_required
def chat_staff_list(request):
    staff = (
        User.objects
        .exclude(pk=request.user.pk)
        .annotate(
            unread_count=Count(
                "chat_messages_sent",
                filter=Q(
                    chat_messages_sent__recipient=request.user,
                    chat_messages_sent__is_read=False,
                ),
            )
        )
        .order_by("id")
    )

    results = [
        {
            "id": user.id,
            "username": user.username,
            "full_name": getattr(user, "full_name", "") or user.username,
            "role": user.role,
            "unread_count": user.unread_count,
        }
        for user in staff
    ]

    return JsonResponse({"results": results})

@login_required
def chat_page(request):
    return render(request, "chat/chat.html")