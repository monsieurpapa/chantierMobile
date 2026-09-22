from django.contrib import admin
from .models import Site, ProjectPhase, SiteProgress, ProgressPhoto, ProgressComment

class PhaseInline(admin.TabularInline):
    model = ProjectPhase
    extra = 1

class ProgressPhotoInline(admin.TabularInline):
    model = ProgressPhoto
    extra = 0

class ProgressCommentInline(admin.TabularInline):
    model = ProgressComment
    extra = 0

@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'cabinet', 'location', 'status', 'start_date')
    list_filter = ('status', 'cabinet')
    inlines = [PhaseInline]

@admin.register(ProjectPhase)
class ProjectPhaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'site', 'start_date', 'end_date')
    list_filter = ('site__cabinet',)

@admin.register(SiteProgress)
class SiteProgressAdmin(admin.ModelAdmin):
    list_display = ('phase', 'report_date', 'percentage_complete')
    list_filter = ('phase__site',)
    inlines = [ProgressPhotoInline, ProgressCommentInline]
