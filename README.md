# AntasMart

Django supermarket POS and inventory management.

## Features

- Fast barcode-based POS billing (scan or type a barcode/product name)
- Inventory catalog with restocking and product search
- Returns: scan an item, add it back to stock, and deduct it from today's sales
- Udhaar (customer credit): send a bill to a customer's udhaar, track pending
  balance, add credit, receive payments, or settle in full
- Sales report: cash sales + udhaar payments − returns
- Thermal receipt printing for 58mm and 80mm paper rolls

## Run

```powershell
python manage.py migrate
python manage.py seed_inventory
python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in. Admin panel: http://127.0.0.1:8000/admin/

To create a login:

```powershell
python manage.py createsuperuser
```
