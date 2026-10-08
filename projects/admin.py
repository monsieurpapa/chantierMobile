"""Django admin registrations for the `projects` app — operator-facing
only; everyday CRUD goes through projects/views.py's role/cabinet-gated
views instead."""
from django.contrib import admin
from .models import Site, ProjectPhase, SiteProgress, ProgressPhoto, ProgressComment, SiteLevel

class PhaseInline(admin.TabularInline):
    model = ProjectPhase
    extra = 1

class SiteLevelInline(admin.TabularInline):
    # Rows are managed by Site.sync_levels(), not by hand here — extra=0
    # and no add/delete through this inline avoids fighting that.
    model = SiteLevel
    extra = 0
    can_delete = False
    fields = (
        'level_index', 'height_m', 'floor_area_m2', 'wall_length_m', 'opening_area_m2',
        'beam_count', 'beam_total_length_m', 'column_count', 'slab_thickness_m',
    )

    def has_add_permission(self, request, obj=None):
        return False

class ProgressPhotoInline(admin.TabularInline):
    model = ProgressPhoto
    extra = 0

class ProgressCommentInline(admin.TabularInline):
    model = ProgressComment
    extra = 0

@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'cabinet', 'location', 'status', 'start_date', 'floor_count', 'basement_count')
    list_filter = ('status', 'cabinet')
    inlines = [PhaseInline, SiteLevelInline]

@admin.register(ProjectPhase)
class ProjectPhaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'site', 'start_date', 'end_date')
    list_filter = ('site__cabinet',)

@admin.register(SiteProgress)
class SiteProgressAdmin(admin.ModelAdmin):
    list_display = ('phase', 'report_date', 'percentage_complete')
    list_filter = ('phase__site',)
    inlines = [ProgressPhotoInline, ProgressCommentInline]
