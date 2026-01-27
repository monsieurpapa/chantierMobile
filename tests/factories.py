"""
Factory classes for creating test data using Factory Boy.
"""

import factory
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import (
    UserRoles, ApprovalStatus, SiteStatus, ExpenseStatus, 
    MaterialRequestStatus, InvoiceStatus, PaymentMethod
)

# User Factory
class UserFactory(factory.django.DjangoModelFactory):
    """Factory for creating User objects."""
    
    class Meta:
        model = 'auth.User'
    
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    is_staff = False
    is_superuser = False
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override to use create_user method."""
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, **kwargs)

class SuperUserFactory(UserFactory):
    """Factory for creating superusers."""
    
    is_staff = True
    is_superuser = True
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override to use create_superuser method."""
        manager = cls._get_manager(model_class)
        return manager.create_superuser(*args, **kwargs)

# Cabinet Factory
class CabinetFactory(factory.django.DjangoModelFactory):
    """Factory for creating Cabinet objects."""
    
    class Meta:
        model = Cabinet
    
    name = factory.Faker('company')
    address = factory.Faker('address')
    tax_id = factory.Faker('bothify', text='??????')
    phone = factory.Faker('phone_number')
    email = factory.Faker('company_email')

# User Cabinet Role Factory
class UserCabinetRoleFactory(factory.django.DjangoModelFactory):
    """Factory for creating UserCabinetRole objects."""
    
    class Meta:
        model = UserCabinetRole
    
    user = factory.SubFactory(UserFactory)
    cabinet = factory.SubFactory(CabinetFactory)
    role = factory.Iterator(UserRoles.values)
    status = ApprovalStatus.APPROVED
    created_at = factory.LazyFunction(timezone.now)

# Site Factory
class SiteFactory(factory.django.DjangoModelFactory):
    """Factory for creating Site objects."""
    
    class Meta:
        model = 'projects.Site'
    
    name = factory.Faker('sentence', nb_words=3)
    location = factory.Faker('address')
    status = SiteStatus.PLANNING
    start_date = factory.LazyFunction(date.today)
    expected_end_date = factory.LazyAttribute(
        lambda obj: obj.start_date + timedelta(days=factory.Faker('random_int', min=30, max=365).generate())
    )
    cabinet = factory.SubFactory(CabinetFactory)
    created_at = factory.LazyFunction(timezone.now)

# Project Phase Factory
class ProjectPhaseFactory(factory.django.DjangoModelFactory):
    """Factory for creating ProjectPhase objects."""
    
    class Meta:
        model = 'projects.ProjectPhase'
    
    site = factory.SubFactory(SiteFactory)
    name = factory.Faker('sentence', nb_words=2)
    start_date = factory.LazyFunction(date.today)
    end_date = factory.LazyAttribute(
        lambda obj: obj.start_date + timedelta(days=factory.Faker('random_int', min=7, max=90).generate())
    )
    created_at = factory.LazyFunction(timezone.now)

# Site Progress Factory
class SiteProgressFactory(factory.django.DjangoModelFactory):
    """Factory for creating SiteProgress objects."""
    
    class Meta:
        model = 'projects.SiteProgress'
    
    phase = factory.SubFactory(ProjectPhaseFactory)
    report_date = factory.LazyFunction(date.today)
    percentage_complete = factory.Faker('random_int', min=0, max=100)
    description = factory.Faker('paragraph', nb_sentences=3)
    created_at = factory.LazyFunction(timezone.now)

# Expense Category Factory
class ExpenseCategoryFactory(factory.django.DjangoModelFactory):
    """Factory for creating ExpenseCategory objects."""
    
    class Meta:
        model = 'finance.ExpenseCategory'
    
    name = factory.Faker('word')
    description = factory.Faker('sentence', nb_words=5)

# Expense Factory
class ExpenseFactory(factory.django.DjangoModelFactory):
    """Factory for creating Expense objects."""
    
    class Meta:
        model = 'finance.Expense'
    
    site = factory.SubFactory(SiteFactory)
    requester = factory.SubFactory(UserFactory)
    category = factory.SubFactory(ExpenseCategoryFactory)
    amount = factory.Faker('pydecimal', left_digits=4, right_digits=2, positive=True)
    description = factory.Faker('paragraph', nb_sentences=2)
    status = ExpenseStatus.PENDING
    receipt_image = factory.django.ImageField()
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)

# Budget Factory
class BudgetFactory(factory.django.DjangoModelFactory):
    """Factory for creating Budget objects."""
    
    class Meta:
        model = 'finance.Budget'
    
    site = factory.SubFactory(SiteFactory)
    total_amount = factory.Faker('pydecimal', left_digits=5, right_digits=2, positive=True)
    start_date = factory.LazyFunction(date.today)
    end_date = factory.LazyAttribute(
        lambda obj: obj.start_date + timedelta(days=factory.Faker('random_int', min=30, max=365).generate())
    )
    created_at = factory.LazyFunction(timezone.now)

# Material Factory
class MaterialFactory(factory.django.DjangoModelFactory):
    """Factory for creating Material objects."""
    
    class Meta:
        model = 'materials.Material'
    
    name = factory.Faker('word')
    description = factory.Faker('sentence', nb_words=4)
    unit = factory.Iterator(['kg', 'm', 'l', 'pieces', 'boxes'])
    estimated_cost_per_unit = factory.Faker('pydecimal', left_digits=3, right_digits=2, positive=True)
    created_at = factory.LazyFunction(timezone.now)

# Material Request Factory
class MaterialRequestFactory(factory.django.DjangoModelFactory):
    """Factory for creating MaterialRequest objects."""
    
    class Meta:
        model = 'materials.MaterialRequest'
    
    site = factory.SubFactory(SiteFactory)
    requested_by = factory.SubFactory(UserFactory)
    status = MaterialRequestStatus.PENDING
    notes = factory.Faker('paragraph', nb_sentences=2)
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)

# Material Request Item Factory
class MaterialRequestItemFactory(factory.django.DjangoModelFactory):
    """Factory for creating MaterialRequestItem objects."""
    
    class Meta:
        model = 'materials.MaterialRequestItem'
    
    request = factory.SubFactory(MaterialRequestFactory)
    material = factory.SubFactory(MaterialFactory)
    quantity = factory.Faker('pydecimal', left_digits=3, right_digits=2, positive=True)
    notes = factory.Faker('sentence', nb_words=3)
    created_at = factory.LazyFunction(timezone.now)

# Personnel Factory
class PersonnelFactory(factory.django.DjangoModelFactory):
    """Factory for creating Personnel objects."""
    
    class Meta:
        model = 'personnel.Personnel'
    
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    default_daily_rate = factory.Faker('pydecimal', left_digits=3, right_digits=2, positive=True)
    user = factory.SubFactory(UserFactory)
    created_at = factory.LazyFunction(timezone.now)

# Site Assignment Factory
class SiteAssignmentFactory(factory.django.DjangoModelFactory):
    """Factory for creating SiteAssignment objects."""
    
    class Meta:
        model = 'personnel.SiteAssignment'
    
    personnel = factory.SubFactory(PersonnelFactory)
    site = factory.SubFactory(SiteFactory)
    role = factory.Faker('job')
    start_date = factory.LazyFunction(date.today)
    end_date = factory.LazyAttribute(
        lambda obj: obj.start_date + timedelta(days=factory.Faker('random_int', min=30, max=365).generate())
    )
    daily_rate = factory.Faker('pydecimal', left_digits=3, right_digits=2, positive=True)
    created_at = factory.LazyFunction(timezone.now)

# Skill Factory
class SkillFactory(factory.django.DjangoModelFactory):
    """Factory for creating Skill objects."""
    
    class Meta:
        model = 'personnel.Skill'
    
    name = factory.Faker('job')
    description = factory.Faker('paragraph', nb_sentences=2)
    created_at = factory.LazyFunction(timezone.now)

# Contract Factory
class ContractFactory(factory.django.DjangoModelFactory):
    """Factory for creating Contract objects."""
    
    class Meta:
        model = 'revenue.Contract'
    
    site = factory.SubFactory(SiteFactory)
    client_name = factory.Faker('name')
    client_email = factory.Faker('email')
    client_phone = factory.Faker('phone_number')
    total_value = factory.Faker('pydecimal', left_digits=5, right_digits=2, positive=True)
    signed_date = factory.LazyFunction(date.today)
    created_at = factory.LazyFunction(timezone.now)

# Invoice Factory
class InvoiceFactory(factory.django.DjangoModelFactory):
    """Factory for creating Invoice objects."""
    
    class Meta:
        model = 'revenue.Invoice'
    
    contract = factory.SubFactory(ContractFactory)
    invoice_number = factory.Faker('bothify', text='INV-????-###')
    amount = factory.Faker('pydecimal', left_digits=4, right_digits=2, positive=True)
    issued_date = factory.LazyFunction(date.today)
    due_date = factory.LazyAttribute(
        lambda obj: obj.issued_date + timedelta(days=factory.Faker('random_int', min=15, max=60).generate())
    )
    status = InvoiceStatus.DRAFT
    created_at = factory.LazyFunction(timezone.now)

# Payment Factory
class PaymentFactory(factory.django.DjangoModelFactory):
    """Factory for creating Payment objects."""
    
    class Meta:
        model = 'revenue.Payment'
    
    invoice = factory.SubFactory(InvoiceFactory)
    amount = factory.Faker('pydecimal', left_digits=4, right_digits=2, positive=True)
    payment_date = factory.LazyFunction(date.today)
    method = factory.Iterator(PaymentMethod.values)
    reference = factory.Faker('bothify', text='PAY-????-###')
    created_at = factory.LazyFunction(timezone.now)

# Pre-configured factories for common scenarios
class CompleteProjectFactory:
    """Factory for creating complete project scenarios."""
    
    @staticmethod
    def create_project_with_all_components():
        """Create a complete project with all related objects."""
        cabinet = CabinetFactory()
        user = UserFactory()
        
        # Create user with director role
        UserCabinetRoleFactory(
            user=user,
            cabinet=cabinet,
            role=UserRoles.DIRECTOR
        )
        
        # Create site
        site = SiteFactory(cabinet=cabinet)
        
        # Create project phase
        phase = ProjectPhaseFactory(site=site)
        
        # Create progress
        SiteProgressFactory(phase=phase)
        
        # Create expense category and expense
        category = ExpenseCategoryFactory()
        expense = ExpenseFactory(site=site, requester=user, category=category)
        
        # Create material and request
        material = MaterialFactory()
        material_request = MaterialRequestFactory(site=site, requested_by=user)
        MaterialRequestItemFactory(request=material_request, material=material)
        
        # Create personnel and assignment
        personnel = PersonnelFactory()
        SiteAssignmentFactory(personnel=personnel, site=site)
        
        # Create contract and invoice
        contract = ContractFactory(site=site)
        invoice = InvoiceFactory(contract=contract)
        PaymentFactory(invoice=invoice)
        
        return {
            'cabinet': cabinet,
            'user': user,
            'site': site,
            'phase': phase,
            'expense': expense,
            'material_request': material_request,
            'personnel': personnel,
            'contract': contract,
            'invoice': invoice
        }


# Test data generators
class TestDataGenerator:
    """Utility class for generating test data."""
    
    @staticmethod
    def create_multiple_sites(count=5, **kwargs):
        """Create multiple sites."""
        return SiteFactory.create_batch(count, **kwargs)
    
    @staticmethod
    def create_multiple_expenses(count=10, **kwargs):
        """Create multiple expenses."""
        return ExpenseFactory.create_batch(count, **kwargs)
    
    @staticmethod
    def create_site_with_expenses(site=None, expense_count=5):
        """Create site with multiple expenses."""
        if not site:
            site = SiteFactory()
        
        expenses = ExpenseFactory.create_batch(expense_count, site=site)
        return site, expenses
    
    @staticmethod
    def create_user_with_role(role=UserRoles.ENGINEER, **kwargs):
        """Create user with specific role."""
        user = UserFactory(**kwargs)
        cabinet = CabinetFactory()
        
        UserCabinetRoleFactory(
            user=user,
            cabinet=cabinet,
            role=role
        )
        
        return user, cabinet
