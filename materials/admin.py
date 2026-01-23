from django.contrib import admin
from .models import Material, MaterialRequest

@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'unit', 'estimated_cost_per_unit')

@admin.register(MaterialRequest)
class MaterialRequestAdmin(admin.ModelAdmin):
    list_display = ('site', 'material', 'quantity', 'status', 'requested_by')
    list_filter = ('status', 'site')
