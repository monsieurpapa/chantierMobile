from django.contrib import admin
from .models import Material, MaterialRequest, MaterialRequestItem

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'unit', 'estimated_cost_per_unit')
    search_fields = ('name',)
    list_filter = ('unit',)

class MaterialRequestItemAdmin(admin.TabularInline):
    model = MaterialRequestItem
    fields = ('material', 'quantity', 'estimated_cost')
    readonly_fields = ('estimated_cost',)
    extra = 1

@admin.register(MaterialRequest)
class MaterialRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'site', 'get_items_count', 'status', 'requested_by', 'created_at')
    list_filter = ('status', 'site', 'created_at')
    search_fields = ('site__name', 'requested_by__username', 'id')
    readonly_fields = ('requested_by', 'created_at', 'updated_at', 'total_items', 'total_estimated_cost')
    fieldsets = (
        ('Request Info', {
            'fields': ('site', 'requested_by', 'status')
        }),
        ('Details', {
            'fields': ('notes',)
        }),
        ('Summary', {
            'fields': ('total_items', 'total_estimated_cost'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_items_count(self, obj):
        return obj.total_items
    get_items_count.short_description = 'Items'
    
    # Inline editing for items
    inlines = [MaterialRequestItemAdmin]

