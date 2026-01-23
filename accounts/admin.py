from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Cabinet, UserCabinetRole

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')

@admin.register(Cabinet)
class CabinetAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'created_at')

@admin.register(UserCabinetRole)
class UserCabinetRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'cabinet', 'role')
    list_filter = ('cabinet', 'role')
