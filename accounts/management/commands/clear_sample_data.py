"""
Management command to clear all sample data from the database.
This is useful for resetting the database to a clean state.

Usage:
    python manage.py clear_sample_data
"""

from django.core.management.base import BaseCommand
from accounts.models import Cabinet, UserCabinetRole, User
from projects.models import Site, ProjectPhase, SiteProgress
from personnel.models import Skill, Personnel, SiteAssignment
from materials.models import Material, MaterialRequest, MaterialRequestItem
from finance.models import Budget, ExpenseCategory, Expense
from revenue.models import Contract, Invoice


class Command(BaseCommand):
    help = 'Clears all sample/demo data from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion without prompting',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            response = input(
                '⚠️  This will delete all data from the database (except superusers).\n'
                'Are you sure you want to continue? (yes/no): '
            )
            if response.lower() != 'yes':
                self.stdout.write(self.style.WARNING('❌ Operation cancelled'))
                return

        self.stdout.write('🗑️  Clearing sample data...')
        
        models_to_clear = [
            (Invoice, 'Invoices'),
            (Contract, 'Contracts'),
            (Expense, 'Expenses'),
            (ExpenseCategory, 'Expense Categories'),
            (Budget, 'Budgets'),
            (MaterialRequestItem, 'Material Request Items'),
            (MaterialRequest, 'Material Requests'),
            (Material, 'Materials'),
            (SiteAssignment, 'Site Assignments'),
            (Personnel, 'Personnel'),
            (SiteProgress, 'Progress Reports'),
            (ProjectPhase, 'Project Phases'),
            (Site, 'Sites'),
            (Skill, 'Skills'),
            (UserCabinetRole, 'User Cabinet Roles'),
            (Cabinet, 'Cabinets'),
        ]
        
        total_deleted = 0
        for model, name in models_to_clear:
            count, _ = model.objects.all().delete()
            total_deleted += count
            self.stdout.write(f'✅ Deleted {count} {name}')
        
        # Clear non-superuser users
        non_superuser_count = User.objects.filter(is_superuser=False).count()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write(f'✅ Deleted {non_superuser_count} users')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'🎉 Successfully deleted {total_deleted + non_superuser_count} records!'
            )
        )
