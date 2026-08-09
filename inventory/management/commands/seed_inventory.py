from django.core.management.base import BaseCommand
from inventory.models import Product

class Command(BaseCommand):
    help = "Seed initial supermarket inventory products for Antas Mart"

    def handle(self, *args, **options):
        sample_products = [
            {"barcode": "8901058852312", "name": "Maggi 2-Minute Noodles", "weight": "70g", "price": 14.00, "quantity": 50},
            {"barcode": "8901030825310", "name": "Amul Taaza Toned Milk", "weight": "1 L", "price": 56.00, "quantity": 30},
            {"barcode": "8901207000123", "name": "Fortune Sunflower Oil", "weight": "1 L", "price": 135.00, "quantity": 20},
            {"barcode": "8901725111222", "name": "Aashirvaad Shudh Chakki Atta", "weight": "5 kg", "price": 245.00, "quantity": 15},
            {"barcode": "8901063012015", "name": "Britannia Good Day Biscuits", "weight": "150g", "price": 30.00, "quantity": 40},
            {"barcode": "8901020000451", "name": "Tata Salt Vacuum Evaporated", "weight": "1 kg", "price": 28.00, "quantity": 25},
            {"barcode": "8901491101010", "name": "Lays India's Magic Masala", "weight": "50g", "price": 20.00, "quantity": 4},  # Low stock example
            {"barcode": "8901030030010", "name": "Surf Excel Easy Wash Powder", "weight": "1 kg", "price": 140.00, "quantity": 2}, # Low stock example
            {"barcode": "8901030999001", "name": "Dove Cream Beauty Bathing Bar", "weight": "100g", "price": 55.00, "quantity": 0}, # Out of stock example
        ]

        created_count = 0
        updated_count = 0

        for pdata in sample_products:
            product, created = Product.objects.get_or_create(
                barcode=pdata["barcode"],
                defaults={
                    "name": pdata["name"],
                    "weight": pdata["weight"],
                    "price": pdata["price"],
                    "quantity": pdata["quantity"],
                }
            )
            if created:
                created_count += 1
            else:
                product.name = pdata["name"]
                product.weight = pdata["weight"]
                product.price = pdata["price"]
                product.quantity = pdata["quantity"]
                product.save()
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded Antas Mart inventory! Created: {created_count}, Updated: {updated_count}"
            )
        )
