from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import (
    Customer,
    Product,
    ReturnItem,
    ReturnRecord,
    Sale,
    SaleItem,
    UdhaarEntry,
)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name', 'weight', 'price', 'quantity')
    search_fields = ('barcode', 'name')
    list_editable = ('price', 'quantity')

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'balance', 'created_at')
    search_fields = ('name', 'phone')
    readonly_fields = ('balance', 'created_at')

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'total_amount', 'payment_type', 'customer', 'created_at', 'receipt_link')
    list_filter = ('payment_type',)
    search_fields = ('invoice_number', 'customer__name')
    inlines = [SaleItemInline]
    readonly_fields = ('receipt_link',)

    @admin.display(description='Printable receipt')
    def receipt_link(self, obj):
        if not obj or not obj.pk:
            return '-'
        url = reverse('receipt_view', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Open receipt</a>', url)

class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0

@admin.register(ReturnRecord)
class ReturnRecordAdmin(admin.ModelAdmin):
    list_display = ('return_number', 'total_amount', 'created_at')
    inlines = [ReturnItemInline]

@admin.register(UdhaarEntry)
class UdhaarEntryAdmin(admin.ModelAdmin):
    list_display = ('customer', 'entry_type', 'amount', 'note', 'created_at')
    list_filter = ('entry_type',)
    search_fields = ('customer__name', 'note')
