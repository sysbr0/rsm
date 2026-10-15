
from django.db.models import Count, Q

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category
from .serializers import CategorySerializer


class CategoryPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CategoryPagination

    def get_queryset(self):
        queryset = Category.objects.annotate(
            total_products=Count("products", distinct=True)
        )

        search = self.request.query_params.get("q", "").strip()
        status_filter = self.request.query_params.get(
            "status", ""
        ).strip().lower()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
            )

        if status_filter == "active":
            queryset = queryset.filter(is_active=True)
        elif status_filter == "inactive":
            queryset = queryset.filter(is_active=False)

        return queryset.order_by("display_order", "name")

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()

        product_count = category.products.count()

        if product_count:
            return Response(
                {
                    "detail": (
                        f"Cannot delete '{category.name}' because it "
                        f"contains {product_count} associated product(s)."
                    ),
                    "product_count": product_count,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        category.delete()

        return Response(
            {"detail": "Category deleted successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        category = self.get_object()

        category.is_active = not category.is_active
        category.save()

        return Response(
            CategorySerializer(
                category,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )


class CategoryStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Category.objects.all()

        return Response(
            {
                "total_categories": queryset.count(),
                "active_categories": queryset.filter(
                    is_active=True
                ).count(),
                "inactive_categories": queryset.filter(
                    is_active=False
                ).count(),
            }
        )

from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer


# ---------- PRODUCT ----------

class ProductPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ProductPagination

    def get_queryset(self):
        queryset = Product.objects.select_related("category", "section")

        search = self.request.query_params.get("q", "").strip()
        status_filter = self.request.query_params.get("status", "").strip().lower()
        category_filter = self.request.query_params.get("category", "").strip()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(sku__icontains=search)
                | Q(description__icontains=search)
            )
        if status_filter == "active":
            queryset = queryset.filter(is_active=True)
        elif status_filter == "inactive":
            queryset = queryset.filter(is_active=False)
        if category_filter:
            try:
                queryset = queryset.filter(category_id=int(category_filter))
            except (TypeError, ValueError):
                pass

        return queryset.order_by("category__display_order", "display_order", "name")

    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        product.delete()
        return Response(
            {"detail": "Product deleted successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def toggle(self, request, pk=None):
        product = self.get_object()
        product.is_active = not product.is_active
        product.save()
        return Response(
            ProductSerializer(product, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )


class ProductStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Product.objects.all()
        return Response({
            "total_products": qs.count(),
            "active_products": qs.filter(is_active=True).count(),
            "inactive_products": qs.filter(is_active=False).count(),
        })