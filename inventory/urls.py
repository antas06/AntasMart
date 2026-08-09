from django.urls import path
from . import views

urlpatterns = [
    path('', views.pos_view, name='pos_view'),
    path('inventory/', views.inventory_view, name='inventory_view'),
    path('low-stock/', views.low_stock_view, name='low_stock_view'),
    path('sales/', views.sales_history_view, name='sales_history_view'),
    path('receipt/<int:sale_id>/', views.receipt_view, name='receipt_view'),
    path('api/product-suggestions/', views.product_suggestions, name='product_suggestions'),
    path('sales-report/', views.sales_report, name='sales_report'),
]
