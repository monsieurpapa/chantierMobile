from django.contrib import admin
from .models import Contract, Invoice, Payment

class InvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('site', 'client_name', 'total_value', 'signed_date')
    inlines = [InvoiceInline]

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'contract', 'amount', 'status', 'due_date')
    list_filter = ('status',)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount', 'payment_date', 'method')
