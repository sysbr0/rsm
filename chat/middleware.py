
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from channels.auth import AuthMiddlewareStack


class TokenAuthMiddleware:
    def __init__(self, app):
        self.app = app
        self.session_app = AuthMiddlewareStack(app)

    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }

        authorization = headers.get("authorization", "")
        parts = authorization.split(None, 1)

        if len(parts) == 2 and parts[0].lower() in ("bearer", "token"):
            scheme, token = parts[0].lower(), parts[1].strip()

            if not token:
                scope["user"] = AnonymousUser()
            else:
                scope["user"] = await self.get_token_user(scheme, token)

            return await self.app(scope, receive, send)

        # Fall back to normal Django session authentication.
        return await self.session_app(scope, receive, send)

    @database_sync_to_async
    def get_token_user(self, scheme, token):
        try:
            if scheme == "bearer":
                from rest_framework_simplejwt.authentication import (
                    JWTAuthentication,
                )

                auth = JWTAuthentication()
                validated_token = auth.get_validated_token(token)
                user = auth.get_user(validated_token)

            else:
                from rest_framework.authtoken.models import Token

                token_obj = (
                    Token.objects.select_related("user")
                    .filter(key=token)
                    .first()
                )
                user = token_obj.user if token_obj else None

            if user is not None and user.is_active:
                return user

        except Exception:
            # Invalid, expired, or unsupported tokens are unauthenticated.
            pass

        return AnonymousUser()
