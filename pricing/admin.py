from django.contrib import admin
from .models import PriceLibraryItem, DQE, DQELine


@admin.register(PriceLibraryItem)
class PriceLibraryItemAdmin(admin.ModelAdmin):
    list_display = ('code', 'designation', 'item_type', 'unit', 'unit_price', 'cabinet', 'is_active')
    list_filter = ('item_type', 'is_active', 'cabinet')
    search_fields = ('code', 'designation')


class DQELineInline(admin.TabularInline):
    model = DQELine
    fields = ('price_item', 'designation', 'quantity', 'unit_price', 'order')
    extra = 1


@admin.register(DQE)
class DQEAdmin(admin.ModelAdmin):
    list_display = ('reference', 'title', 'site', 'status', 'cabinet', 'total_amount', 'created_at')
    list_filter = ('status', 'cabinet')
    search_fields = ('reference', 'title')
    inlines = [DQELineInline]
