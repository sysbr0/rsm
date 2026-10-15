
from django.shortcuts import render
from django.shortcuts import get_object_or_404, redirect

from django.shortcuts import render, redirect, get_object_or_404
from .models import Category, Product
from .forms import CategoryForm, ProductForm


def category_list_page(request):
    return render(request, "categories/category_list.html")



def category_create_page(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("category_list")
    else:
        form = CategoryForm()

    return render(request, "categories/category_form.html", {
        "form": form,
        "page_title": "Create Category",
        "is_edit": False,
    })


def category_edit_page(request, pk):
    category = get_object_or_404(Category, pk=pk)

    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return redirect("category_list")
    else:
        form = CategoryForm(instance=category)

    return render(request, "categories/category_form.html", {
        "form": form,
        "object": category,
        "page_title": "Edit Category",
        "is_edit": True,
        "category_id": pk,
    })
def category_delete_page(request, pk):
    return render(request, "categories/category_delete.html", {
        "category_id": pk,
    })



def product_list_page(request):
    return render(request, "product/product_list.html", {
        "categories": Category.objects.order_by("display_order", "name"),
       
    })


def product_create_page(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("product_list")
    else:
        form = ProductForm()
    return render(request, "product/product_form.html", {"form": form})


def product_edit_page(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect("product_list")
    else:
        form = ProductForm(instance=product)
    return render(request, "product/product_form.html", {
        "form": form, "object": product,
    })


def product_delete_page(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()
        return redirect("product_list")
    return render(request, "product/product_delete.html", {"object": product})