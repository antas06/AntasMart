import uuid
import socket
from decimal import Decimal
from itertools import groupby
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q
from django.db.models import F, Sum
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.views.decorators.csrf import csrf_exempt
from .models import Product, Sale, SaleItem
from .forms import BarcodeSearchForm, ProductForm, AddQuantityForm, CustomItemForm

# Global in-memory queue for mobile scanned barcodes (offline desktop app)
MOBILE_SCAN_QUEUE = []

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def get_cart(session):
    return session.get('pos_cart', [])

def save_cart(session, cart):
    session['pos_cart'] = cart
    if hasattr(session, 'modified'):
        session.modified = True

def pos_view(request):
    cart = get_cart(request.session)
    barcode_form = BarcodeSearchForm()
    custom_form = CustomItemForm()
    products = Product.objects.all().order_by('name')
    local_ip = get_local_ip()

    receipt_sale = None
    if 'last_sale_id' in request.session:
        sale_id = request.session.pop('last_sale_id')
        receipt_sale = Sale.objects.filter(id=sale_id).first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'scan':
            product_query = request.POST.get('barcode', '').strip()
            if product_query:
                # Barcode scanners submit an exact barcode. Manual entry also accepts
                # an exact product name (case-insensitively).
                product = Product.objects.filter(barcode=product_query).first()
                if not product:
                    product = Product.objects.filter(name__iexact=product_query).first()
                if product:
                    # ── Stock Validation ────────────────────────────
                    if product.quantity <= 0:
                        messages.error(request, f"'{product.name}' is OUT OF STOCK (0 units). Cannot add to bill.")
                        return redirect('pos_view')

                    # Check if already in cart — don't exceed available stock
                    found = False
                    for item in cart:
                        if item.get('product_id') == product.id:
                            new_qty = item['quantity'] + 1
                            if new_qty > product.quantity:
                                messages.warning(request, f"Only {product.quantity} unit(s) of '{product.name}' in stock. Cannot add more.")
                                return redirect('pos_view')
                            item['quantity'] = new_qty
                            item['subtotal'] = float(Decimal(str(new_qty)) * Decimal(str(product.price)))
                            found = True
                            break
                    if not found:
                        cart.append({
                            'product_id': product.id,
                            'barcode': product.barcode,
                            'name': product.name,
                            'weight': product.weight,
                            'price': float(product.price),
                            'quantity': 1,
                            'subtotal': float(product.price),
                        })
                    save_cart(request.session, cart)
                    messages.success(request, f"Added {product.name} ({product.weight}) to bill.")
                else:
                    messages.error(request, f"No product found for '{product_query}'.")
            return redirect('pos_view')

        elif action == 'add_product':
            product_id = request.POST.get('product_id')
            if product_id:
                product = get_object_or_404(Product, id=product_id)

                # ── Stock Validation ────────────────────────────────
                if product.quantity <= 0:
                    messages.error(request, f"'{product.name}' is OUT OF STOCK (0 units). Cannot add to bill.")
                    return redirect('pos_view')

                found = False
                for item in cart:
                    if item.get('product_id') == product.id:
                        new_qty = item['quantity'] + 1
                        if new_qty > product.quantity:
                            messages.warning(request, f"Only {product.quantity} unit(s) of '{product.name}' available. Cannot add more.")
                            return redirect('pos_view')
                        item['quantity'] = new_qty
                        item['subtotal'] = float(Decimal(str(new_qty)) * Decimal(str(product.price)))
                        found = True
                        break
                if not found:
                    cart.append({
                        'product_id': product.id,
                        'barcode': product.barcode,
                        'name': product.name,
                        'weight': product.weight,
                        'price': float(product.price),
                        'quantity': 1,
                        'subtotal': float(product.price),
                    })
                save_cart(request.session, cart)
                messages.success(request, f"Added {product.name} to bill.")
            return redirect('pos_view')

        elif action == 'add_custom':
            c_form = CustomItemForm(request.POST)
            if c_form.is_valid():
                name = c_form.cleaned_data['name']
                weight = c_form.cleaned_data['weight'] or 'N/A'
                price = float(c_form.cleaned_data['price'])
                qty = c_form.cleaned_data['quantity']
                cart.append({
                    'product_id': None,
                    'barcode': 'CUSTOM',
                    'name': name,
                    'weight': weight,
                    'price': price,
                    'quantity': qty,
                    'subtotal': float(Decimal(str(qty)) * Decimal(str(price))),
                })
                save_cart(request.session, cart)
                messages.success(request, f"Added custom item '{name}' to bill.")
            return redirect('pos_view')

        elif action == 'update_qty':
            index = int(request.POST.get('item_index', -1))
            new_qty = int(request.POST.get('quantity', 1))
            if 0 <= index < len(cart):
                if new_qty > 0:
                    cart[index]['quantity'] = new_qty
                    cart[index]['subtotal'] = float(Decimal(str(new_qty)) * Decimal(str(cart[index]['price'])))
                else:
                    cart.pop(index)
                save_cart(request.session, cart)
            return redirect('pos_view')

        elif action == 'remove_item':
            index = int(request.POST.get('item_index', -1))
            if 0 <= index < len(cart):
                removed = cart.pop(index)
                save_cart(request.session, cart)
                messages.info(request, f"Removed {removed['name']} from cart.")
            return redirect('pos_view')

        elif action == 'clear_cart':
            save_cart(request.session, [])
            messages.info(request, "Cart cleared.")
            return redirect('pos_view')

        elif action in ('checkout', 'checkout_save', 'checkout_print'):
            if not cart:
                messages.error(request, "Cannot checkout an empty cart.")
                return redirect('pos_view')

            with transaction.atomic():
                total_val = sum(Decimal(str(item['subtotal'])) for item in cart)
                inv_code = f"INV-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
                sale = Sale.objects.create(
                    invoice_number=inv_code,
                    total_amount=total_val
                )

                for item in cart:
                    p_obj = None
                    if item['product_id']:
                        p_obj = Product.objects.filter(id=item['product_id']).first()
                        if p_obj:
                            p_obj.quantity = max(0, p_obj.quantity - item['quantity'])
                            p_obj.save()

                    SaleItem.objects.create(
                        sale=sale,
                        product=p_obj,
                        item_name=item['name'],
                        item_weight=item['weight'],
                        price=Decimal(str(item['price'])),
                        quantity=item['quantity'],
                        subtotal=Decimal(str(item['subtotal']))
                    )

                save_cart(request.session, [])

                if action in ('checkout', 'checkout_print'):
                    # Save + show receipt modal for printing
                    request.session['last_sale_id'] = sale.id
                    messages.success(request, f"Sale completed! Invoice #{sale.invoice_number}")
                else:
                    # checkout_save: fast save only, no receipt modal
                    messages.success(request, f"Bill saved! Invoice #{sale.invoice_number}")

                return redirect('pos_view')

    total_bill = sum(item['subtotal'] for item in cart)

    context = {
        'cart': cart,
        'total_bill': total_bill,
        'barcode_form': barcode_form,
        'custom_form': custom_form,
        'products': products,
        'receipt_sale': receipt_sale,
        'local_ip': local_ip,
    }
    return render(request, 'inventory/pos.html', context)


def inventory_view(request):
    search_query = request.GET.get('q', '').strip()
    scanned_barcode = request.GET.get('scanned_barcode', '').strip()
    local_ip = get_local_ip()

    scanned_product = None
    new_barcode = None

    if scanned_barcode:
        existing = Product.objects.filter(barcode=scanned_barcode).first()
        if existing:
            scanned_product = existing
        else:
            new_barcode = scanned_barcode

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'scan_barcode':
            b_code = request.POST.get('barcode', '').strip()
            if b_code:
                return redirect(f"/inventory/?scanned_barcode={b_code}")

        elif form_type == 'add_product':
            form = ProductForm(request.POST)
            if form.is_valid():
                p = form.save()
                messages.success(request, f"Product '{p.name}' added successfully!")
                return redirect('inventory_view')
            else:
                messages.error(request, "Error adding product. Please check values.")

        elif form_type == 'add_quantity':
            p_id = request.POST.get('product_id')
            qty_add = int(request.POST.get('add_qty', 0))
            if p_id and qty_add > 0:
                product = get_object_or_404(Product, id=p_id)
                product.quantity += qty_add
                product.save()
                messages.success(request, f"Added {qty_add} units to '{product.name}'. New Total: {product.quantity}")
                return redirect('inventory_view')

    products = Product.objects.all().order_by('name')

    total_value_query = products.aggregate(
        total=Sum(F("price") * F("quantity"))
    )
    total_inventory_value = total_value_query["total"] or 0

    if search_query:
        products = products.filter(name__icontains=search_query) | products.filter(barcode__icontains=search_query)

    context = {
        'products': products,
        'search_query': search_query,
        'scanned_product': scanned_product,
        'new_barcode': new_barcode,
        'product_form': ProductForm(initial={'barcode': new_barcode}) if new_barcode else ProductForm(),
        'scan_form': BarcodeSearchForm(),
        'local_ip': local_ip,
        'total_inventory_value': total_inventory_value,
    }
    return render(request, 'inventory/inventory.html', context)


def low_stock_view(request):
    threshold = int(request.GET.get('threshold', 5))
    low_products = Product.objects.filter(quantity__lte=threshold).order_by('quantity', 'name')

    if request.method == 'POST':
        p_id = request.POST.get('product_id')
        qty_add = int(request.POST.get('add_qty', 0))
        if p_id and qty_add > 0:
            product = get_object_or_404(Product, id=p_id)
            product.quantity += qty_add
            product.save()
            messages.success(request, f"Restocked {qty_add} units for '{product.name}'. Current Stock: {product.quantity}")
            return redirect('low_stock_view')

    context = {
        'low_products': low_products,
        'threshold': threshold,
        'local_ip': get_local_ip(),
    }
    return render(request, 'inventory/low_stock.html', context)


def sales_history_view(request):
    sales = Sale.objects.all().order_by('-created_at')
    context = {
        'sales': sales,
        'local_ip': get_local_ip(),
    }
    return render(request, 'inventory/sales_history.html', context)

def sales_report(request):
    today = timezone.now().date()

    #Today's Total
    today_sales_total = (
        Sale.objects.filter(created_at__date=today).aggregate(
            total=Sum("total_amount")
        )["total"]
        or 0
    )

    #Current Active Month Total
    month_sales_total = (
        Sale.objects.filter(
            created_at__year=today.year, created_at__month=today.month
        ).aggregate(total=Sum("total_amount"))["total"]
        or 0
    )

    #Get all daily totals ordered by newest date first
    daily_sales = (
        Sale.objects.annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(
            total_orders=Count("id"), total_revenue=Sum("total_amount")
        )
        .order_by("-date")
    )

    # Group daily records by Month
    monthly_sales = []
    for month_name, items in groupby(
        daily_sales, key=lambda x: x["date"].strftime("%B %Y")
    ):
        items_list = list(items)
        month_total = sum(item["total_revenue"] or 0 for item in items_list)
        monthly_sales.append(
            {
                "month_name": month_name,
                "month_total": month_total,
                "days": items_list,
            }
        )

    context = {
        "today_sales_total": today_sales_total,
        "month_sales_total": month_sales_total,
        "monthly_sales": monthly_sales,
        "current_month_name": today.strftime("%B %Y"),
    }

    return render(request, "inventory/sales_report.html", context)


def receipt_view(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    context = {
        'sale': sale,
    }
    return render(request, 'inventory/receipt.html', context)


def product_suggestions(request):
    """Return catalog matches for the POS scan/add input."""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'products': []})

    matches = Product.objects.filter(
        Q(barcode__icontains=query) | Q(name__icontains=query)
    ).order_by('name')[:10]
    return JsonResponse({'products': [
        {
            'barcode': product.barcode,
            'name': product.name,
            'weight': product.weight,
            'price': str(product.price),
            'quantity': product.quantity,
        }
        for product in matches
    ]})
