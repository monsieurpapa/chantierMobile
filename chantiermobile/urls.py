from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from core.views import HomeView
from django.views.i18n import set_language

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', HomeView.as_view(), name='home'),
    path('finance/', include('finance.urls'), name='finance'),
    path('projects/', include('projects.urls'), name='projects'),
    path('personnel/', include('personnel.urls'), name='personnel'),
    path('materials/', include('materials.urls'), name='materials'),
    path('revenue/', include('revenue.urls'), name='revenue'),
    
    # User accounts
    path('user/', include('accounts.urls')),
    
    # Language switching
    path('i18n/', include('django.conf.urls.i18n')),
    path('set-language/', set_language, name='set_language'),
    
    # Auth (Allauth)
    path('accounts/', include('allauth.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
