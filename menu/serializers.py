from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import *


class CategorySerializer(serializers.ModelSerializer):
    total_products = serializers.IntegerField(read_only=True)
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "description",
            "display_order",
            "is_active",
            "icon",
            "icon_url",
            "total_products",
        ]
        read_only_fields = ["id", "total_products", "icon_url"]

    def get_icon_url(self, obj):
        if not obj.icon:
            return None

        request = self.context.get("request")
        try:
            url = obj.icon.url
        except ValueError:
            return None

        if request:
            return request.build_absolute_uri(url)
        return url

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Category name is required.")
        return value

    def validate_display_order(self, value):
        if value < 0:
            raise serializers.ValidationError("Display order cannot be negative.")
        return value

    def validate_icon(self, value):
        if not value:
            return value

        if hasattr(value, "size") and value.size > 1 * 1024 * 1024:
            raise serializers.ValidationError("Icon must be smaller than 1 MB.")

        name = (getattr(value, "name", "") or "").lower()
        if not name.endswith(".svg"):
            raise serializers.ValidationError("Only .svg files are allowed.")

        return value

    def _validate_model(self, instance):
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict)
            raise serializers.ValidationError(exc.messages)

    def create(self, validated_data):
        category = Category(**validated_data)
        self._validate_model(category)
        category.save()
        return category

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)

        self._validate_model(instance)
        instance.save()
        return instance



# ... your existing CategorySerializer ...


class ProductSerializer(serializers.ModelSerializer):
    # Read-only computed fields
    category_name = serializers.CharField(source="category.name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    category_icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "category",
            "category_name",
            "category_icon_url",
            "section",
            "section_name",
            "price",
            "tax_rate",
            "is_active",
            "display_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "category_name",
            "category_icon_url",
            "section_name",
        ]

    def get_category_icon_url(self, obj):
        if not obj.category or not obj.category.icon:
            return None
        request = self.context.get("request")
        try:
            url = obj.category.icon.url
        except ValueError:
            return None
        return request.build_absolute_uri(url) if request else url

    def validate_sku(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("SKU is required.")
        return value

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Product name is required.")
        return value

    def validate_price(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value

    def validate_tax_rate(self, value):
        if value is None:
            return value
        if value < 0 or value > 100:
            raise serializers.ValidationError("Tax rate must be between 0 and 100.")
        return value

    def _validate_model(self, instance):
        try:
            instance.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise serializers.ValidationError(exc.message_dict)
            raise serializers.ValidationError(exc.messages)

    def create(self, validated_data):
        product = Product(**validated_data)
        self._validate_model(product)
        product.save()
        return product

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)

        self._validate_model(instance)
        instance.save()
        return instance