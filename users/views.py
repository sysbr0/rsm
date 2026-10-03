from django.core.serializers import python
from django.shortcuts import render

# Create your views here.
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.shortcuts import redirect, render


def _login_user(request, allowed_roles, redirect_url, template_name):
    if request.user.is_authenticated:
        return redirect(redirect_url)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:
            messages.error(request, "Invalid username or password.")
            return render(request, template_name)

        if user.role not in allowed_roles:
            messages.error(
                request,
                "You are not allowed to login from this page.",
            )
            return render(request, template_name)

        if not user.is_active:
            messages.error(request, "Your account is inactive.")
            return render(request, template_name)

        login(request, user)
        return redirect(redirect_url)

    return render(request, template_name)


def admin_manager_login(request):
    return _login_user(
        request=request,
        allowed_roles=["ADMIN", "MANAGER"],
        redirect_url="/manager/",
        template_name="users/login_admin.html",
    )


def waiter_login(request):
    return _login_user(
        request=request,
        allowed_roles=["WAITER"],
        redirect_url="/waiter/",
        template_name="users/login_waiter.html",
    )


def employee_login(request):
    return _login_user(
        request=request,
        allowed_roles=["CASHIER", "KITCHEN"],
        redirect_url="/employee/",
        template_name="users/login_employee.html",
    )



from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny


# ============================================================
# NORMAL WEB LOGIN
# ============================================================

def admin_login(request):

    if request.method == "POST":

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:
            return render(
                request,
                "ui/login_admin.html",
                {
                    "error": "Invalid username or password."
                },
            )

        # Allow ADMIN and MANAGER
        if user.role not in ["ADMIN", "MANAGER"]:
            return render(
                request,
                "ui/login_admin.html",
                {
                    "error": (
                        "You do not have permission "
                        "to access this panel."
                    )
                },
            )

        # Create Django session
        login(request, user)

        # Successful login
        return redirect("/manager/tables/")

    return render(
        request,
        "users/login_admin.html"
    )


# ============================================================
# ADMIN LOGIN API
# ============================================================

class AdminLoginAPIView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        username = request.data.get(
            "username",
            ""
        ).strip()

        password = request.data.get(
            "password",
            ""
        )


        # ----------------------------------------
        # Validate input
        # ----------------------------------------

        if not username or not password:

            return Response(
                {
                    "success": False,
                    "message": "Username and password are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


        # ----------------------------------------
        # Authenticate
        # ----------------------------------------

        user = authenticate(
            request,
            username=username,
            password=password,
        )


        # ----------------------------------------
        # Invalid credentials
        # ----------------------------------------

        if user is None:

            return Response(
                {
                    "success": False,
                    "message": "Invalid username or password.",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )


        # ----------------------------------------
        # Check role
        # ----------------------------------------

        if user.role not in [
            "ADMIN",
            "MANAGER",
        ]:

            return Response(
                {
                    "success": False,
                    "message": (
                        "You do not have permission "
                        "to access this panel."
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )


        # ----------------------------------------
        # Login / Django session
        # ----------------------------------------

        login(
            request,
            user
        )


        # ----------------------------------------
        # Success
        # ----------------------------------------

        return Response(
            {
                "success": True,
                "message": "Login successful.",

                "user": {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                },

                "redirect": "/manager/tables/",
            },
            status=status.HTTP_200_OK,
        )