from django.urls import path
from . import views

urlpatterns = [
    path('', views.pos_view, name='pos_view'),
    path('inventory/', views.inventory_view, name='inventory_view'),
    path('returns/', views.returns_view, name='returns_view'),
    path('udhaar/', views.udhaar_view, name='udhaar_view'),
    path('udhaar/<int:pk>/', views.udhaar_detail, name='udhaar_detail'),
    path('sales/', views.sales_history_view, name='sales_history_view'),
    path('receipt/<int:sale_id>/', views.receipt_view, name='receipt_view'),
    path('api/product-suggestions/', views.product_suggestions, name='product_suggestions'),
    path('sales-report/', views.sales_report, name='sales_report'),
]
