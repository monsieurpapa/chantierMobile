from django.contrib import admin
from .models import Supplier, StockItem, PurchaseOrder, PurchaseOrderLine, StockMovement


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'cabinet', 'contact_name', 'phone', 'email')
    list_filter = ('cabinet',)
    search_fields = ('name', 'contact_name', 'email')


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'site', 'quantity_on_hand', 'unit', 'reorder_threshold')
    list_filter = ('site',)
    search_fields = ('name', 'site__name')
    readonly_fields = ('quantity_on_hand',)


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1
    fields = ('stock_item', 'quantity', 'quantity_received', 'unit_price', 'line_total')
    readonly_fields = ('line_total',)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'site', 'supplier', 'status', 'order_date', 'total_ht')
    list_filter = ('status', 'supplier')
    search_fields = ('order_number', 'site__name', 'supplier__name')
    inlines = [PurchaseOrderLineInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('stock_item', 'movement_type', 'quantity', 'movement_date', 'moved_by')
    list_filter = ('movement_type', 'movement_date')
    search_fields = ('stock_item__name',)
    readonly_fields = ('stock_item', 'movement_type', 'quantity', 'purchase_order_line')
