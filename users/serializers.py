from rest_framework import serializers
from .models import User, UserRole, UserState


class WorkingWaiterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "role",
            "state",
            "is_active",
        ]

    def to_representation(self, instance):
        return super().to_representation(instance)