import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from itertools import groupby

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import BarcodeSearchForm, CustomItemForm, ProductForm
from .models import (
    Customer,
    Product,
    ReturnItem,
    ReturnRecord,
    Sale,
    SaleItem,
    UdhaarEntry,
)

PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_cart(session, key="pos_cart"):
    return session.get(key, [])


def save_cart(session, cart, key="pos_cart"):
    session[key] = cart
    session.modified = True


def to_decimal(value):
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def append_product(cart, product):
    """Add one unit of a product to a cart, respecting available stock."""
    for item in cart:
        if item.get("product_id") == product.id:
            new_qty = item["quantity"] + 1
            if new_qty > product.quantity:
                return False, f"Only {product.quantity} unit(s) of '{product.name}' in stock."
            item["quantity"] = new_qty
            item["subtotal"] = float(Decimal(new_qty) * product.price)
            return True, None

    if product.quantity < 1:
        return False, f"'{product.name}' is OUT OF STOCK (0 units). Cannot add to bill."

    cart.append(
        {
            "product_id": product.id,
            "barcode": product.barcode,
            "name": product.name,
            "weight": product.weight,
            "price": float(product.price),
            "quantity": 1,
            "subtotal": float(product.price),
        }
    )
    return True, None


def create_sale(cart, payment_type=Sale.CASH, customer=None):
    """Create a sale, its line items, and deduct stock. Call inside a transaction."""
    total_val = sum(Decimal(str(item["subtotal"])) for item in cart)
    invoice_number = (
        f"INV-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    )
    sale = Sale.objects.create(
        invoice_number=invoice_number,
        total_amount=total_val,
        payment_type=payment_type,
        customer=customer,
    )

    product_ids = [item["product_id"] for item in cart if item.get("product_id")]
    products = Product.objects.in_bulk(product_ids) if product_ids else {}

    for item in cart:
        product = products.get(item["product_id"]) if item.get("product_id") else None
        if product:
            new_qty = max(0, product.quantity - item["quantity"])
            Product.objects.filter(pk=product.pk).update(quantity=new_qty)
            product.quantity = new_qty

        SaleItem.objects.create(
            sale=sale,
            product=product,
            item_name=item["name"],
            item_weight=item["weight"],
            price=Decimal(str(item["price"])),
            quantity=item["quantity"],
            subtotal=Decimal(str(item["subtotal"])),
        )
    return sale


# ---------------------------------------------------------------------------
# POS Billing
# ---------------------------------------------------------------------------

def pos_view(request):
    cart = get_cart(request.session)

    receipt_sale = None
    if "last_sale_id" in request.session:
        sale_id = request.session.pop("last_sale_id")
        receipt_sale = Sale.objects.select_related("customer").filter(id=sale_id).first()

    if request.method == "POST":
        action = request.POST.get("action")

        if action in ("scan", "add_product"):
            product = None
            if action == "scan":
                query = request.POST.get("barcode", "").strip()
                if query:
                    product = Product.objects.filter(barcode=query).first()
                    if not product:
                        product = Product.objects.filter(name__iexact=query).first()
                    if not product:
                        messages.error(request, f"No product found for '{query}'.")
            else:
                product_id = request.POST.get("product_id")
                if product_id:
                    product = Product.objects.filter(id=product_id).first()

            if product:
                ok, error = append_product(cart, product)
                if ok:
                    save_cart(request.session, cart)
                    messages.success(
                        request, f"Added {product.name} ({product.weight}) to bill."
                    )
                else:
                    messages.warning(request, error)
            return redirect("pos_view")

        if action == "add_custom":
            form = CustomItemForm(request.POST)
            if form.is_valid():
                name = form.cleaned_data["name"]
                weight = form.cleaned_data["weight"] or "N/A"
                price = float(form.cleaned_data["price"])
                qty = form.cleaned_data["quantity"]
                cart.append(
                    {
                        "product_id": None,
                        "barcode": "CUSTOM",
                        "name": name,
                        "weight": weight,
                        "price": price,
                        "quantity": qty,
                        "subtotal": float(Decimal(str(qty)) * Decimal(str(price))),
                    }
                )
                save_cart(request.session, cart)
                messages.success(request, f"Added custom item '{name}' to bill.")
            return redirect("pos_view")

        if action == "update_qty":
            index = int(request.POST.get("item_index", -1))
            new_qty = int(request.POST.get("quantity", 1))
            if 0 <= index < len(cart):
                if new_qty > 0:
                    item = cart[index]
                    product = (
                        Product.objects.filter(id=item["product_id"]).first()
                        if item.get("product_id")
                        else None
                    )
                    if product and new_qty > product.quantity:
                        messages.warning(
                            request,
                            f"Only {product.quantity} unit(s) of '{product.name}' in stock.",
                        )
                    else:
                        item["quantity"] = new_qty
                        item["subtotal"] = float(
                            Decimal(str(new_qty)) * Decimal(str(item["price"]))
                        )
                        save_cart(request.session, cart)
                else:
                    cart.pop(index)
                    save_cart(request.session, cart)
            return redirect("pos_view")

        if action == "remove_item":
            index = int(request.POST.get("item_index", -1))
            if 0 <= index < len(cart):
                removed = cart.pop(index)
                save_cart(request.session, cart)
                messages.info(request, f"Removed {removed['name']} from cart.")
            return redirect("pos_view")

        if action == "clear_cart":
            save_cart(request.session, [])
            messages.info(request, "Cart cleared.")
            return redirect("pos_view")

        if action in ("checkout_save", "checkout_print", "checkout_udhaar"):
            if not cart:
                messages.error(request, "Cannot checkout an empty cart.")
                return redirect("pos_view")

            if action == "checkout_udhaar":
                customer_id = request.POST.get("customer_id", "").strip()
                new_name = request.POST.get("new_customer_name", "").strip()
                new_phone = request.POST.get("new_customer_phone", "").strip()

                with transaction.atomic():
                    customer = None
                    if new_name:
                        customer = Customer.objects.create(
                            name=new_name, phone=new_phone
                        )
                    elif customer_id:
                        customer = Customer.objects.filter(id=customer_id).first()

                    if not customer:
                        messages.error(
                            request,
                            "Select an udhaar customer or enter a new customer name.",
                        )
                        return redirect("pos_view")

                    sale = create_sale(cart, Sale.UDHAAR, customer)
                    Customer.objects.filter(pk=customer.pk).update(
                        balance=F("balance") + sale.total_amount
                    )
                    UdhaarEntry.objects.create(
                        customer=customer,
                        entry_type=UdhaarEntry.CREDIT,
                        amount=sale.total_amount,
                        note=f"Invoice {sale.invoice_number}",
                        sale=sale,
                    )

                save_cart(request.session, [])
                request.session["last_sale_id"] = sale.id
                customer.refresh_from_db(fields=["balance"])
                messages.success(
                    request,
                    f"₹{sale.total_amount} sent to udhaar for {customer.name}. "
                    f"Pending balance: ₹{customer.balance}.",
                )
                return redirect("pos_view")

            with transaction.atomic():
                sale = create_sale(cart, Sale.CASH)

            save_cart(request.session, [])
            if action == "checkout_print":
                request.session["last_sale_id"] = sale.id
            messages.success(request, f"Sale completed! Invoice #{sale.invoice_number}")
            return redirect("pos_view")

    total_bill = sum(item["subtotal"] for item in cart)
    context = {
        "cart": cart,
        "total_bill": total_bill,
        "barcode_form": BarcodeSearchForm(),
        "custom_form": CustomItemForm(),
        "receipt_sale": receipt_sale,
        "customers": (
            Customer.objects.only("id", "name", "phone", "balance").order_by("name")
            if cart
            else Customer.objects.none()
        ),
    }
    return render(request, "inventory/pos.html", context)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def inventory_view(request):
    search_query = request.GET.get("q", "").strip()
    scanned_barcode = request.GET.get("scanned_barcode", "").strip()

    scanned_product = None
    new_barcode = None

    if scanned_barcode:
        existing = Product.objects.filter(barcode=scanned_barcode).first()
        if existing:
            scanned_product = existing
        else:
            new_barcode = scanned_barcode

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "add_product":
            form = ProductForm(request.POST)
            if form.is_valid():
                product = form.save()
                messages.success(request, f"Product '{product.name}' added successfully!")
                return redirect("inventory_view")
            messages.error(request, "Error adding product. Please check values.")

        elif form_type == "add_quantity":
            product_id = request.POST.get("product_id")
            qty_add = int(request.POST.get("add_qty", 0))
            if product_id and qty_add > 0:
                product = get_object_or_404(Product, id=product_id)
                Product.objects.filter(pk=product.pk).update(
                    quantity=F("quantity") + qty_add
                )
                product.refresh_from_db(fields=["quantity"])
                messages.success(
                    request,
                    f"Added {qty_add} units to '{product.name}'. "
                    f"New total: {product.quantity}",
                )
                return redirect("inventory_view")

    products = Product.objects.all().order_by("name")
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | Q(barcode__icontains=search_query)
        )

    total_inventory_value = (
        Product.objects.aggregate(total=Sum(F("price") * F("quantity")))["total"] or 0
    )
    paginator = Paginator(products, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "products": page_obj,
        "page_obj": page_obj,
        "total_products": Product.objects.count(),
        "search_query": search_query,
        "scanned_product": scanned_product,
        "new_barcode": new_barcode,
        "product_form": ProductForm(initial={"barcode": new_barcode})
        if new_barcode
        else ProductForm(),
        "total_inventory_value": total_inventory_value,
    }
    return render(request, "inventory/inventory.html", context)


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------

def returns_view(request):
    cart = get_cart(request.session, "return_cart")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "scan":
            query = request.POST.get("barcode", "").strip()
            product = None
            if query:
                product = Product.objects.filter(barcode=query).first()
                if not product:
                    product = Product.objects.filter(name__iexact=query).first()

            if not product:
                messages.error(request, f"No product found for '{query}'.")
            else:
                for item in cart:
                    if item.get("product_id") == product.id:
                        item["quantity"] += 1
                        item["subtotal"] = float(
                            Decimal(item["quantity"]) * product.price
                        )
                        break
                else:
                    cart.append(
                        {
                            "product_id": product.id,
                            "barcode": product.barcode,
                            "name": product.name,
                            "weight": product.weight,
                            "price": float(product.price),
                            "quantity": 1,
                            "subtotal": float(product.price),
                        }
                    )
                save_cart(request.session, cart, "return_cart")
                messages.success(
                    request, f"Added {product.name} ({product.weight}) to return."
                )
            return redirect("returns_view")

        if action == "update_qty":
            index = int(request.POST.get("item_index", -1))
            new_qty = int(request.POST.get("quantity", 1))
            if 0 <= index < len(cart):
                if new_qty > 0:
                    cart[index]["quantity"] = new_qty
                    cart[index]["subtotal"] = float(
                        Decimal(new_qty) * Decimal(str(cart[index]["price"]))
                    )
                    save_cart(request.session, cart, "return_cart")
                else:
                    cart.pop(index)
                    save_cart(request.session, cart, "return_cart")
            return redirect("returns_view")

        if action == "remove_item":
            index = int(request.POST.get("item_index", -1))
            if 0 <= index < len(cart):
                removed = cart.pop(index)
                save_cart(request.session, cart, "return_cart")
                messages.info(request, f"Removed {removed['name']} from return.")
            return redirect("returns_view")

        if action == "clear_cart":
            save_cart(request.session, [], "return_cart")
            messages.info(request, "Return list cleared.")
            return redirect("returns_view")

        if action == "confirm":
            if not cart:
                messages.error(request, "There are no items to return.")
                return redirect("returns_view")

            with transaction.atomic():
                total_val = sum(Decimal(str(item["subtotal"])) for item in cart)
                return_number = (
                    f"RET-{timezone.now().strftime('%Y%m%d')}-"
                    f"{uuid.uuid4().hex[:6].upper()}"
                )
                record = ReturnRecord.objects.create(
                    return_number=return_number,
                    total_amount=total_val,
                    note=request.POST.get("note", "").strip()[:255],
                )

                product_ids = [
                    item["product_id"] for item in cart if item.get("product_id")
                ]
                products = (
                    Product.objects.in_bulk(product_ids) if product_ids else {}
                )

                for item in cart:
                    product = (
                        products.get(item["product_id"])
                        if item.get("product_id")
                        else None
                    )
                    if product:
                        Product.objects.filter(pk=product.pk).update(
                            quantity=F("quantity") + item["quantity"]
                        )
                    ReturnItem.objects.create(
                        return_record=record,
                        product=product,
                        item_name=item["name"],
                        item_weight=item["weight"],
                        price=Decimal(str(item["price"])),
                        quantity=item["quantity"],
                        subtotal=Decimal(str(item["subtotal"])),
                    )

            save_cart(request.session, [], "return_cart")
            messages.success(
                request,
                f"Return {record.return_number} saved. ₹{record.total_amount} "
                "deducted from today's sales and stock restored.",
            )
            return redirect("returns_view")

    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    context = {
        "cart": cart,
        "total_return": sum(item["subtotal"] for item in cart),
        "barcode_form": BarcodeSearchForm(),
        "recent_returns": ReturnRecord.objects.prefetch_related("items").order_by(
            "-created_at"
        )[:25],
        "today_return_total": (
            ReturnRecord.objects.filter(
                created_at__gte=day_start, created_at__lt=day_end
            ).aggregate(total=Sum("total_amount"))["total"]
            or 0
        ),
    }
    return render(request, "inventory/returns.html", context)


# ---------------------------------------------------------------------------
# Udhaar (customer credit)
# ---------------------------------------------------------------------------

def udhaar_view(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_customer":
            name = request.POST.get("name", "").strip()
            phone = request.POST.get("phone", "").strip()
            if name:
                Customer.objects.create(name=name, phone=phone)
                messages.success(request, f"Customer '{name}' added.")
            else:
                messages.error(request, "Customer name is required.")
            return redirect("udhaar_view")

    context = {
        "customers": Customer.objects.all().order_by("name"),
        "total_outstanding": (
            Customer.objects.aggregate(total=Sum("balance"))["total"] or 0
        ),
    }
    return render(request, "inventory/udhaar_list.html", context)


def udhaar_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        amount = to_decimal(request.POST.get("amount", "0"))
        note = request.POST.get("note", "").strip()[:255]

        if action in ("increase", "decrease", "settle"):
            if action == "settle":
                amount = customer.balance

            if amount <= 0:
                messages.error(request, "Enter an amount greater than zero.")
            elif action == "increase":
                with transaction.atomic():
                    Customer.objects.filter(pk=customer.pk).update(
                        balance=F("balance") + amount
                    )
                    UdhaarEntry.objects.create(
                        customer=customer,
                        entry_type=UdhaarEntry.CREDIT,
                        amount=amount,
                        note=note,
                    )
                messages.success(
                    request, f"Udhaar increased by ₹{amount} for {customer.name}."
                )
            elif amount > customer.balance:
                messages.error(
                    request,
                    f"Payment ₹{amount} is more than the pending balance "
                    f"₹{customer.balance}.",
                )
            else:
                with transaction.atomic():
                    Customer.objects.filter(pk=customer.pk).update(
                        balance=F("balance") - amount
                    )
                    UdhaarEntry.objects.create(
                        customer=customer,
                        entry_type=UdhaarEntry.PAYMENT,
                        amount=amount,
                        note=note,
                    )
                messages.success(
                    request,
                    f"Payment of ₹{amount} received from {customer.name}.",
                )
            return redirect("udhaar_detail", pk=customer.pk)

    customer.refresh_from_db()
    context = {
        "customer": customer,
        "entries": customer.entries.select_related("sale").order_by("-created_at")[:100],
        "sales": customer.sales.order_by("-created_at")[:50],
    }
    return render(request, "inventory/udhaar_detail.html", context)


# ---------------------------------------------------------------------------
# Sales history & report
# ---------------------------------------------------------------------------

def sales_history_view(request):
    sales = (
        Sale.objects.select_related("customer")
        .annotate(item_count=Count("items"))
        .order_by("-created_at")
    )
    paginator = Paginator(sales, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    context = {
        "sales": page_obj,
        "page_obj": page_obj,
        "payments": (
            UdhaarEntry.objects.filter(entry_type=UdhaarEntry.PAYMENT)
            .select_related("customer")
            .order_by("-created_at")[:100]
        ),
    }
    return render(request, "inventory/sales_history.html", context)


def sales_report(request):
    now = timezone.now()
    today = now.date()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    cash_today = (
        Sale.objects.filter(
            payment_type=Sale.CASH,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0")
    )
    udhaar_today = (
        UdhaarEntry.objects.filter(
            entry_type=UdhaarEntry.PAYMENT,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    returns_today = (
        ReturnRecord.objects.filter(
            created_at__gte=day_start, created_at__lt=day_end
        ).aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0")
    )
    today_sales_total = cash_today + udhaar_today - returns_today

    cash_month = (
        Sale.objects.filter(
            payment_type=Sale.CASH,
            created_at__gte=month_start,
            created_at__lt=month_end,
        ).aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0")
    )
    udhaar_month = (
        UdhaarEntry.objects.filter(
            entry_type=UdhaarEntry.PAYMENT,
            created_at__gte=month_start,
            created_at__lt=month_end,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0")
    )
    returns_month = (
        ReturnRecord.objects.filter(
            created_at__gte=month_start, created_at__lt=month_end
        ).aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0")
    )
    month_sales_total = cash_month + udhaar_month - returns_month

    daily = {}

    def add_rows(rows, sign=1, count_orders=True):
        for row in rows:
            if not row["date"]:
                continue
            entry = daily.setdefault(
                row["date"],
                {
                    "date": row["date"],
                    "total_revenue": Decimal("0"),
                    "total_orders": 0,
                },
            )
            entry["total_revenue"] += sign * (row["total"] or Decimal("0"))
            if count_orders:
                entry["total_orders"] += row["orders"] or 0

    add_rows(
        Sale.objects.filter(payment_type=Sale.CASH)
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(total=Sum("total_amount"), orders=Count("id"))
    )
    add_rows(
        UdhaarEntry.objects.filter(entry_type=UdhaarEntry.PAYMENT)
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(total=Sum("amount"), orders=Count("id"))
    )
    add_rows(
        ReturnRecord.objects.annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(total=Sum("total_amount"), orders=Count("id")),
        sign=-1,
        count_orders=False,
    )

    daily_sales = [daily[day] for day in sorted(daily, reverse=True)]

    monthly_sales = []
    for month_name, items in groupby(
        daily_sales, key=lambda row: row["date"].strftime("%B %Y")
    ):
        items_list = list(items)
        month_total = sum((item["total_revenue"] or 0) for item in items_list)
        monthly_sales.append(
            {
                "month_name": month_name,
                "month_total": month_total,
                "days": items_list,
            }
        )

    context = {
        "today_sales_total": today_sales_total,
        "cash_today": cash_today,
        "udhaar_today": udhaar_today,
        "returns_today": returns_today,
        "month_sales_total": month_sales_total,
        "monthly_sales": monthly_sales,
        "current_month_name": today.strftime("%B %Y"),
        "udhaar_outstanding": (
            Customer.objects.aggregate(total=Sum("balance"))["total"] or 0
        ),
    }
    return render(request, "inventory/sales_report.html", context)


def receipt_view(request, sale_id):
    sale = get_object_or_404(
        Sale.objects.select_related("customer").prefetch_related("items"), id=sale_id
    )
    return render(request, "inventory/receipt.html", {"sale": sale})


def product_suggestions(request):
    """Return catalog matches for the POS/Returns scan input."""
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"products": []})

    matches = Product.objects.filter(
        Q(barcode__icontains=query) | Q(name__icontains=query)
    ).order_by("name")[:8]
    return JsonResponse(
        {
            "products": [
                {
                    "barcode": product.barcode,
                    "name": product.name,
                    "weight": product.weight,
                    "price": str(product.price),
                    "quantity": product.quantity,
                }
                for product in matches
            ]
        }
    )
