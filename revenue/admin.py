from django.contrib import admin
from .models import Contract, Invoice, Payment, Devis, DevisLine, SituationTravaux, SituationLine

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


class DevisLineInline(admin.TabularInline):
    model = DevisLine
    extra = 1
    fields = ('order', 'designation', 'unit', 'quantity', 'unit_price_ht', 'total_ht')
    readonly_fields = ('total_ht',)


@admin.register(Devis)
class DevisAdmin(admin.ModelAdmin):
    list_display = ('devis_number', 'site', 'client_name', 'status', 'issue_date', 'total_ht')
    list_filter = ('status',)
    search_fields = ('devis_number', 'client_name', 'site__name')
    inlines = [DevisLineInline]


class SituationLineInline(admin.TabularInline):
    model = SituationLine
    extra = 1
    fields = ('devis_line', 'cumulative_percentage')


@admin.register(SituationTravaux)
class SituationTravauxAdmin(admin.ModelAdmin):
    list_display = ('numero', 'contract', 'status', 'period_end_date', 'total_ht_period')
    list_filter = ('status',)
    search_fields = ('contract__site__name', 'contract__client_name')
    inlines = [SituationLineInline]
