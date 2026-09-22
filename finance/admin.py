from django.contrib import admin
from .models import Budget, ExpenseCategory, Expense, ExpenseApproval, CaisseTransactionCategory

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('site', 'total_amount', 'start_date', 'end_date')

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(CaisseTransactionCategory)
class CaisseTransactionCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)

class ApprovalInline(admin.TabularInline):
    model = ExpenseApproval
    readonly_fields = ('approver', 'status', 'approval_date', 'comments')
    extra = 0
    can_delete = False

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('site', 'category', 'amount', 'status', 'requester')
    list_filter = ('status', 'site', 'category')
    inlines = [ApprovalInline]
