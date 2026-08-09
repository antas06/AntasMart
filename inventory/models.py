from django.db import models

class Product(models.Model):
    barcode = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    weight = models.CharField(max_length=50, blank=True, default="N/A")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.weight}) - ${self.price}"


class Sale(models.Model):
    invoice_number = models.CharField(max_length=50, unique=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invoice #{self.invoice_number} - ${self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    item_name = models.CharField(max_length=200)
    item_weight = models.CharField(max_length=50, blank=True, default="N/A")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.item_name} @ ${self.price}"
