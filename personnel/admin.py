from django.contrib import admin
from .models import Skill, Personnel, SiteAssignment

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Personnel)
class PersonnelAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'personnel_type', 'cabinet', 'default_daily_rate')
    list_filter = ('cabinet', 'personnel_type', 'skills')

@admin.register(SiteAssignment)
class SiteAssignmentAdmin(admin.ModelAdmin):
    list_display = ('personnel', 'site', 'role', 'start_date', 'daily_rate')
    list_filter = ('site', 'personnel__cabinet')
