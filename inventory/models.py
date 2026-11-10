from django.db import models


class Product(models.Model):
    barcode = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    weight = models.CharField(max_length=50, blank=True, default="N/A")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=0)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.weight}) - ₹{self.price}"


class Customer(models.Model):
    """A customer who can take goods on udhaar (credit)."""

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, default="")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["name"])]

    def __str__(self):
        return self.name


class Sale(models.Model):
    CASH = "cash"
    UDHAAR = "udhaar"
    PAYMENT_CHOICES = [
        (CASH, "Cash"),
        (UDHAAR, "Udhaar"),
    ]

    invoice_number = models.CharField(max_length=50, unique=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_type = models.CharField(
        max_length=10, choices=PAYMENT_CHOICES, default=CASH, db_index=True
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["payment_type", "created_at"])]

    def __str__(self):
        return f"Invoice #{self.invoice_number} - ₹{self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    item_name = models.CharField(max_length=200)
    item_weight = models.CharField(max_length=50, blank=True, default="N/A")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.item_name} @ ₹{self.price}"


class ReturnRecord(models.Model):
    """A customer return. Stock goes back up and revenue goes down."""

    return_number = models.CharField(max_length=50, unique=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["created_at"])]

    def __str__(self):
        return f"Return #{self.return_number} - ₹{self.total_amount}"


class ReturnItem(models.Model):
    return_record = models.ForeignKey(
        ReturnRecord, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    item_name = models.CharField(max_length=200)
    item_weight = models.CharField(max_length=50, blank=True, default="N/A")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.item_name} @ ₹{self.price}"


class UdhaarEntry(models.Model):
    """Ledger entry for a customer's udhaar balance.

    credit  -> customer owes more money (goods taken on udhaar)
    payment -> customer paid money back (this counts as revenue)
    """

    CREDIT = "credit"
    PAYMENT = "payment"
    ENTRY_CHOICES = [
        (CREDIT, "Udhaar given"),
        (PAYMENT, "Payment received"),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="entries"
    )
    entry_type = models.CharField(max_length=10, choices=ENTRY_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=255, blank=True, default="")
    sale = models.ForeignKey(
        Sale,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="udhaar_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["entry_type", "created_at"])]

    def __str__(self):
        return f"{self.get_entry_type_display()} - ₹{self.amount} - {self.customer.name}"
