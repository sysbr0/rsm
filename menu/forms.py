from django import forms
from django import forms
from .models import Category, Product, Section

from django import forms
from .models import Category


class CategoryForm(forms.ModelForm):

    class Meta:
        model = Category
        fields = ["name", "description", "display_order", "is_active", "icon"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., Beverages",
                "maxlength": "150",
                "autocomplete": "off",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Short description of the category",
                "rows": 4,
            }),
            "display_order": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0,
                "placeholder": "0",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
                "role": "switch",
            }),
            # ⬇️ Plain FileInput — no Django auto-generated
            # "Currently: <link> Clear Change:" markup.
            "icon": forms.FileInput(attrs={
                "class": "form-control",
                "accept": ".svg,image/svg+xml",
            }),
        }

    def clean_icon(self):
        icon = self.cleaned_data.get("icon")

        # No new file uploaded
        if not icon:
            return icon

        # Cap size at 1 MB
        if icon.size and icon.size > 1 * 1024 * 1024:
            raise forms.ValidationError("Icon must be smaller than 1 MB.")

        # Only SVG allowed
        name = (icon.name or "").lower()
        if not name.endswith(".svg"):
            raise forms.ValidationError("Only .svg files are allowed.")

        return icon

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "sku",
            "name",
            "description",
            "category",
            "section",
            "price",
            "tax_rate",
            "is_active",
            "display_order",
        ]
        widgets = {
            "sku": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., BEV-001",
                "maxlength": "100",
                "autocomplete": "off",
            }),
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g., Coca-Cola 330ml",
                "maxlength": "150",
                "autocomplete": "off",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "placeholder": "Short product description",
                "rows": 4,
            }),
            "category": forms.Select(attrs={
                "class": "form-select",
            }),
            "section": forms.Select(attrs={
                "class": "form-select",
            }),
            "price": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "placeholder": "0.00",
            }),
            "tax_rate": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "max": "100",
                "placeholder": "0.00",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
                "role": "switch",
            }),
            "display_order": forms.NumberInput(attrs={
                "class": "form-control",
                "min": 0,
                "placeholder": "0",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.order_by("display_order", "name")
        self.fields["section"].queryset = Section.objects.order_by("name")
        self.fields["category"].empty_label = "— Select a category —"
        self.fields["section"].empty_label = "— Select a section —"