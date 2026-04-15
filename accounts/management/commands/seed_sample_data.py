"""
Management command to populate the database with sample data in French.
This command creates a complete demo setup with users, cabinets, sites, and related data.

Usage:
    python manage.py seed_sample_data
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from accounts.models import User, Cabinet, UserCabinetRole, CabinetContextLog
from chantiermobile.constants import UserRoles, ApprovalStatus
from projects.models import Site, ProjectPhase, SiteProgress
from personnel.models import Skill, Personnel, SiteAssignment
from materials.models import Material, MaterialRequest, MaterialRequestItem
from finance.models import Budget, ExpenseCategory, Expense
from revenue.models import Contract, Invoice


class Command(BaseCommand):
    help = 'Populates the database with sample data in French'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing data before creating sample data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.clear_data()
        
        self.stdout.write(self.style.SUCCESS('🚀 Starting sample data generation...'))
        
        # Create users
        users = self.create_users()
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(users)} users'))
        
        # Create cabinets
        cabinets = self.create_cabinets()
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(cabinets)} cabinets'))
        
        # Assign users to cabinets
        self.assign_users_to_cabinets(users, cabinets)
        self.stdout.write(self.style.SUCCESS('✅ Assigned users to cabinets'))
        
        # Create skills
        skills = self.create_skills()
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(skills)} skills'))
        
        # Create personnel
        personnel = self.create_personnel(cabinets, skills)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(personnel)} personnel'))
        
        # Create sites
        sites = self.create_sites(cabinets)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(sites)} sites'))
        
        # Create project phases
        phases = self.create_project_phases(sites)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(phases)} project phases'))
        
        # Create site progress
        progress = self.create_site_progress(phases)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(progress)} progress reports'))
        
        # Create site assignments
        assignments = self.create_site_assignments(personnel, sites)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(assignments)} personnel assignments'))
        
        # Create materials
        materials = self.create_materials()
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(materials)} materials'))
        
        # Create material requests
        mat_requests = self.create_material_requests(sites, users, materials)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(mat_requests)} material requests'))
        
        # Create budgets
        budgets = self.create_budgets(sites)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(budgets)} budgets'))
        
        # Create expense categories
        categories = self.create_expense_categories()
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(categories)} expense categories'))
        
        # Create expenses
        expenses = self.create_expenses(sites, users, categories)
        self.stdout.write(self.style.SUCCESS(f'✅ Created {len(expenses)} expenses'))
        
        # Create contracts and invoices
        contracts = self.create_contracts_and_invoices(sites)
        self.stdout.write(self.style.SUCCESS(f'✅ Created contracts and invoices'))
        
        self.stdout.write(self.style.SUCCESS('🎉 Sample data generation complete!'))

    def clear_data(self):
        """Clear existing data"""
        self.stdout.write('🗑️  Clearing existing data...')
        CabinetContextLog.objects.all().delete()
        Invoice.objects.all().delete()
        Contract.objects.all().delete()
        Expense.objects.all().delete()
        ExpenseCategory.objects.all().delete()
        Budget.objects.all().delete()
        MaterialRequestItem.objects.all().delete()
        MaterialRequest.objects.all().delete()
        Material.objects.all().delete()
        SiteAssignment.objects.all().delete()
        Personnel.objects.all().delete()
        SiteProgress.objects.all().delete()
        ProjectPhase.objects.all().delete()
        Site.objects.all().delete()
        Skill.objects.all().delete()
        UserCabinetRole.objects.all().delete()
        Cabinet.objects.all().delete()
        User.objects.all().filter(is_superuser=False).delete()

    def create_users(self):
        """Create sample users"""
        users_data = [
            {
                'username': 'directeur_001',
                'email': 'directeur@construction.sn',
                'first_name': 'Jean',
                'last_name': 'Diallo',
                'password': 'password123',
                'phone_number': '+221 77 123 4567'
            },
            {
                'username': 'ingenieur_chef_001',
                'email': 'chef_ingenieur@construction.sn',
                'first_name': 'Marie',
                'last_name': 'Sow',
                'password': 'password123',
                'phone_number': '+221 77 234 5678'
            },
            {
                'username': 'ingenieur_001',
                'email': 'ingenieur1@construction.sn',
                'first_name': 'Ahmed',
                'last_name': 'Ba',
                'password': 'password123',
                'phone_number': '+221 77 345 6789'
            },
            {
                'username': 'comptable_001',
                'email': 'comptable@construction.sn',
                'first_name': 'Fatou',
                'last_name': 'Ndiaye',
                'password': 'password123',
                'phone_number': '+221 77 456 7890'
            },
            {
                'username': 'caissier_001',
                'email': 'caissier@construction.sn',
                'first_name': 'Moussa',
                'last_name': 'Gueye',
                'password': 'password123',
                'phone_number': '+221 77 567 8901'
            },
        ]
        
        users = []
        for user_data in users_data:
            user, created = User.objects.get_or_create(
                username=user_data['username'],
                defaults={
                    'email': user_data['email'],
                    'first_name': user_data['first_name'],
                    'last_name': user_data['last_name'],
                    'phone_number': user_data['phone_number'],
                }
            )
            if created:
                user.set_password(user_data['password'])
                user.save()
            users.append(user)
        
        return users

    def create_cabinets(self):
        """Create sample construction companies"""
        cabinets_data = [
            {
                'name': 'BTP Solutions Sénégal',
                'address': '123 Avenue Cheikh Anta Diop, Dakar',
                'tax_id': 'SN123456789'
            },
            {
                'name': 'Constructions Modernes SARL',
                'address': '456 Boulevard de l\'Indépendance, Dakar',
                'tax_id': 'SN987654321'
            },
        ]
        
        cabinets = []
        for cabinet_data in cabinets_data:
            cabinet, created = Cabinet.objects.get_or_create(
                name=cabinet_data['name'],
                defaults={
                    'address': cabinet_data['address'],
                    'tax_id': cabinet_data['tax_id'],
                }
            )
            cabinets.append(cabinet)
        
        return cabinets

    def assign_users_to_cabinets(self, users, cabinets):
        """Assign users to cabinets with roles"""
        role_assignments = [
            (users[0], cabinets[0], UserRoles.DIRECTOR, ApprovalStatus.APPROVED),
            (users[1], cabinets[0], UserRoles.CHIEF_ENGINEER, ApprovalStatus.APPROVED),
            (users[2], cabinets[0], UserRoles.ENGINEER, ApprovalStatus.APPROVED),
            (users[3], cabinets[0], UserRoles.ACCOUNTANT, ApprovalStatus.APPROVED),
            (users[4], cabinets[0], UserRoles.CASHIER, ApprovalStatus.APPROVED),
            (users[0], cabinets[1], UserRoles.DIRECTOR, ApprovalStatus.APPROVED),
            (users[1], cabinets[1], UserRoles.CHIEF_ENGINEER, ApprovalStatus.APPROVED),
        ]
        
        for user, cabinet, role, status in role_assignments:
            UserCabinetRole.objects.get_or_create(
                user=user,
                cabinet=cabinet,
                defaults={'role': role, 'status': status}
            )

    def create_skills(self):
        """Create job skills"""
        skills_data = [
            'Maçon',
            'Ferrailleur',
            'Électricien',
            'Plombier',
            'Peintre',
            'Menuisier',
            'Conducteur d\'équipe',
            'Chef de chantier',
        ]
        
        skills = []
        for skill_name in skills_data:
            skill, created = Skill.objects.get_or_create(name=skill_name)
            skills.append(skill)
        
        return skills

    def create_personnel(self, cabinets, skills):
        """Create personnel for cabinets"""
        personnel_data = [
            {'first_name': 'Samba', 'last_name': 'Sane', 'skills': [0], 'rate': 15000},  # Maçon
            {'first_name': 'Ibrahima', 'last_name': 'Toure', 'skills': [1], 'rate': 18000},  # Ferrailleur
            {'first_name': 'Moustapha', 'last_name': 'Camara', 'skills': [2], 'rate': 20000},  # Électricien
            {'first_name': 'Amadou', 'last_name': 'Kone', 'skills': [3], 'rate': 19000},  # Plombier
            {'first_name': 'Lamine', 'last_name': 'Diallo', 'skills': [4, 6], 'rate': 16000},  # Peintre + Chef d'équipe
            {'first_name': 'Kofi', 'last_name': 'Mensah', 'skills': [5], 'rate': 17000},  # Menuisier
        ]
        
        personnel = []
        for person_data in personnel_data:
            person = Personnel.objects.create(
                cabinet=cabinets[0],
                first_name=person_data['first_name'],
                last_name=person_data['last_name'],
                default_daily_rate=Decimal(person_data['rate'])
            )
            for skill_idx in person_data['skills']:
                person.skills.add(skills[skill_idx])
            personnel.append(person)
        
        return personnel

    def create_sites(self, cabinets):
        """Create construction sites"""
        today = date.today()
        sites_data = [
            {
                'name': 'Immeuble Residential Plateau',
                'location': 'Plateau, Dakar',
                'status': Site.Status.ACTIVE,
                'start_date': today - timedelta(days=120),
                'expected_end_date': today + timedelta(days=180),
                'cabinet': cabinets[0]
            },
            {
                'name': 'Centre Commercial Point E',
                'location': 'Point E, Dakar',
                'status': Site.Status.PLANNING,
                'start_date': today + timedelta(days=30),
                'expected_end_date': today + timedelta(days=480),
                'cabinet': cabinets[0]
            },
            {
                'name': 'Rénovation École Secondaire Malick Sy',
                'location': 'Médina, Dakar',
                'status': Site.Status.ACTIVE,
                'start_date': today - timedelta(days=60),
                'expected_end_date': today + timedelta(days=120),
                'cabinet': cabinets[1]
            },
        ]
        
        sites = []
        for site_data in sites_data:
            site = Site.objects.create(**site_data)
            sites.append(site)
        
        return sites

    def create_project_phases(self, sites):
        """Create project phases for sites"""
        phases_data = [
            # Site 1
            {
                'site': sites[0],
                'phases': [
                    {'name': 'Terrassement et Fondation', 'start_offset': 0, 'end_offset': 30},
                    {'name': 'Structure Béton', 'start_offset': 30, 'end_offset': 90},
                    {'name': 'Cloisons et Finitions', 'start_offset': 90, 'end_offset': 150},
                ]
            },
            # Site 2
            {
                'site': sites[1],
                'phases': [
                    {'name': 'Étude et Préparation', 'start_offset': 0, 'end_offset': 30},
                    {'name': 'Fondations', 'start_offset': 30, 'end_offset': 80},
                ]
            },
            # Site 3
            {
                'site': sites[2],
                'phases': [
                    {'name': 'Démolition Sélective', 'start_offset': 0, 'end_offset': 20},
                    {'name': 'Reconstruction', 'start_offset': 20, 'end_offset': 80},
                ]
            },
        ]
        
        phases = []
        today = date.today()
        
        for site_phases in phases_data:
            for phase_data in site_phases['phases']:
                phase = ProjectPhase.objects.create(
                    site=site_phases['site'],
                    name=phase_data['name'],
                    start_date=today + timedelta(days=phase_data['start_offset']),
                    end_date=today + timedelta(days=phase_data['end_offset']),
                )
                phases.append(phase)
        
        return phases

    def create_site_progress(self, phases):
        """Create progress reports for phases"""
        progress_reports = []
        today = date.today()
        
        for phase in phases[:3]:  # Add progress to first 3 phases
            progress = SiteProgress.objects.create(
                phase=phase,
                report_date=today,
                percentage_complete=45,
                description='Travaux en cours selon le planning prévu. Aucun retard à signaler.',
            )
            progress_reports.append(progress)
        
        return progress_reports

    def create_site_assignments(self, personnel, sites):
        """Create site assignments for personnel — only within the same cabinet."""
        today = date.today()
        assignments = []

        # All personnel belong to cabinets[0]; sites[0] and sites[1] also belong to cabinets[0].
        for person in personnel[:4]:
            assignment = SiteAssignment.objects.create(
                personnel=person,
                site=sites[0],
                role='Ouvrier Qualifié',
                start_date=today - timedelta(days=60),
                end_date=today + timedelta(days=120),
                daily_rate=person.default_daily_rate
            )
            assignments.append(assignment)

        for person in personnel[2:5]:
            assignment = SiteAssignment.objects.create(
                personnel=person,
                site=sites[1],
                role='Ouvrier',
                start_date=today - timedelta(days=30),
                end_date=today + timedelta(days=90),
                daily_rate=person.default_daily_rate
            )
            assignments.append(assignment)

        return assignments

    def create_materials(self):
        """Create materials"""
        materials_data = [
            {'name': 'Ciment CEM II/A 42.5', 'unit': 'sacs', 'cost': 8500},
            {'name': 'Sable Construction', 'unit': 'm³', 'cost': 35000},
            {'name': 'Gravier', 'unit': 'm³', 'cost': 40000},
            {'name': 'Acier HA500', 'unit': 'kg', 'cost': 950},
            {'name': 'Brique de Construction', 'unit': 'unité', 'cost': 350},
            {'name': 'Tuiles de Toiture', 'unit': 'm²', 'cost': 5500},
            {'name': 'Peinture Intérieure', 'unit': 'litre', 'cost': 12000},
            {'name': 'Fenêtres Aluminium', 'unit': 'unité', 'cost': 85000},
        ]
        
        materials = []
        for mat_data in materials_data:
            material, created = Material.objects.get_or_create(
                name=mat_data['name'],
                defaults={
                    'unit': mat_data['unit'],
                    'estimated_cost_per_unit': Decimal(mat_data['cost'])
                }
            )
            materials.append(material)
        
        return materials

    def create_material_requests(self, sites, users, materials):
        """Create material requests"""
        today = date.today()
        requests = []
        
        for i, site in enumerate(sites[:2]):
            request = MaterialRequest.objects.create(
                site=site,
                requested_by=users[2],  # Engineer user
                status=MaterialRequest.Status.PENDING if i == 0 else MaterialRequest.Status.APPROVED,
                notes=f'Matériaux nécessaires pour la phase {i+1} du chantier'
            )
            
            # Add items to request
            for j, material in enumerate(materials[:4]):
                MaterialRequestItem.objects.create(
                    request=request,
                    material=material,
                    quantity=Decimal((j + 1) * 10),
                    notes='Qualité standard - Livraison rapide souhaitée'
                )
            
            requests.append(request)
        
        return requests

    def create_budgets(self, sites):
        """Create budgets for sites"""
        budgets = []
        today = date.today()
        
        budget_amounts = [
            Decimal('150000000'),  # 150 million FCFA
            Decimal('200000000'),  # 200 million FCFA
            Decimal('50000000'),   # 50 million FCFA
        ]
        
        for site, amount in zip(sites, budget_amounts):
            budget, created = Budget.objects.get_or_create(
                site=site,
                defaults={
                    'total_amount': amount,
                    'start_date': site.start_date or today,
                    'end_date': site.expected_end_date or today + timedelta(days=365),
                }
            )
            budgets.append(budget)
        
        return budgets

    def create_expense_categories(self):
        """Create expense categories"""
        categories_data = [
            'Matériaux de Construction',
            'Main d\'œuvre',
            'Transport et Logistique',
            'Équipements et Outils',
            'Permis et Autorisations',
            'Assurance',
            'Frais Administratifs',
        ]
        
        categories = []
        for cat_name in categories_data:
            category, created = ExpenseCategory.objects.get_or_create(name=cat_name)
            categories.append(category)
        
        return categories

    def create_expenses(self, sites, users, categories):
        """Create sample expenses"""
        today = date.today()
        expenses = []
        
        # All expenses use sites from cabinets[0] only (sites[0] and sites[1]).
        # sites[2] belongs to cabinets[1] — using Cabinet A users against it would
        # violate tenant isolation in demo data.
        expense_data = [
            {'site': 0, 'category': 0, 'amount': 5000000, 'description': 'Achat de ciment et sable pour les fondations'},
            {'site': 0, 'category': 1, 'amount': 2500000, 'description': 'Salaires des ouvriers - janvier'},
            {'site': 0, 'category': 2, 'amount': 800000, 'description': 'Transport des matériaux vers le chantier'},
            {'site': 1, 'category': 3, 'amount': 1200000, 'description': 'Équipements de sécurité et outils'},
            {'site': 1, 'category': 4, 'amount': 300000, 'description': 'Demande de permis de construction'},
        ]
        
        for exp_data in expense_data:
            expense = Expense.objects.create(
                site=sites[exp_data['site']],
                requester=users[2],  # Engineer
                category=categories[exp_data['category']],
                amount=Decimal(exp_data['amount']),
                description=exp_data['description'],
                status=Expense.Status.APPROVED,
                created_at=today - timedelta(days=5)
            )
            expenses.append(expense)
        
        return expenses

    def create_contracts_and_invoices(self, sites):
        """Create contracts and invoices for sites"""
        today = date.today()
        
        for site in sites[:2]:
            contract, created = Contract.objects.get_or_create(
                site=site,
                defaults={
                    'client_name': f'Client - {site.name}',
                    'total_value': Decimal('100000000'),
                    'signed_date': site.start_date or today,
                }
            )
            
            # Create invoices
            invoice_amount = Decimal('20000000')
            for i in range(3):
                Invoice.objects.get_or_create(
                    contract=contract,
                    invoice_number=f'INV-{site.unique_id[:8]}-{i+1:03d}',
                    defaults={
                        'amount': invoice_amount,
                        'issued_date': today - timedelta(days=30-i*10),
                        'due_date': today + timedelta(days=60-i*10),
                        'status': Invoice.Status.PAID if i > 0 else Invoice.Status.DRAFT,
                    }
                )
