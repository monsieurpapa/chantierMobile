from django.contrib import admin
from .models import PriceLibraryItem


@admin.register(PriceLibraryItem)
class PriceLibraryItemAdmin(admin.ModelAdmin):
    list_display = ('code', 'designation', 'item_type', 'unit', 'unit_price', 'cabinet', 'is_active')
    list_filter = ('item_type', 'is_active', 'cabinet')
    search_fields = ('code', 'designation')
