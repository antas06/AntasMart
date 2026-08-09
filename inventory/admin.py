from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Product, Sale, SaleItem

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'weight', 'price', 'quantity')
    search_fields = ('barcode', 'name')
    list_editable = ('price', 'quantity')

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'total_amount', 'created_at', 'receipt_link')
    inlines = [SaleItemInline]
    readonly_fields = ('receipt_link',)

    @admin.display(description='Printable receipt')
    def receipt_link(self, obj):
        if not obj or not obj.pk:
            return '-'
        url = reverse('receipt_view', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Open receipt</a>', url)
