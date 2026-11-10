from django import forms
from .models import Product

class BarcodeSearchForm(forms.Form):
    barcode = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control barcode-input',
            'placeholder': 'Scan barcode or type product name...',
            'autofocus': 'autofocus',
            'autocomplete': 'off'
        })
    )

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['barcode', 'name', 'weight', 'price', 'quantity']
        widgets = {
            'barcode': forms.TextInput(attrs={'class': 'form-control', 'required': 'required'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'required': 'required', 'placeholder': 'e.g. Rice, Milk, Soap'}),
            'weight': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 500g, 1 kg, 250ml'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'required': 'required'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'required': 'required'}),
        }

class CustomItemForm(forms.Form):
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item Name (e.g. Loose Fruit)'})
    )
    weight = forms.CharField(
        max_length=50,
        required=False,
        initial='N/A',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Weight (e.g. 1kg)'})
    )
    price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Price'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
