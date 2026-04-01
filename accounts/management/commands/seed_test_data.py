"""
Management command that seeds a complete, realistic dataset for manual QA testing.

Covers every status state for every entity, every user role, multi-tenant isolation,
and the full approval/payment workflow chains.

Usage:
    python manage.py seed_test_data           # Add data (idempotent)
    python manage.py seed_test_data --clear   # Wipe first, then seed

Credentials printed at the end of the run.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Cabinet, User, UserCabinetRole
from chantiermobile.constants import (
    ApprovalStatus, ExpenseStatus, InvoiceStatus, MaterialRequestStatus,
    PaymentMethod, SiteStatus, UserRoles,
)
from finance.models import Budget, Expense, ExpenseApproval, ExpenseCategory
from materials.models import Material, MaterialRequest, MaterialRequestItem
from personnel.models import Personnel, SiteAssignment, Skill
from projects.models import ProjectPhase, Site, SiteProgress
from revenue.models import Contract, Invoice, Payment

TODAY = date.today()
PASSWORD = 'Test1234!'


class Command(BaseCommand):
    help = 'Seeds the DB with realistic test data covering every status and workflow'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete all existing data before seeding',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            self._clear_all()

        self.stdout.write('\nSeeding test data...\n')

        superuser = self._create_superuser()
        users_a, cabinet_a = self._setup_cabinet_a()
        users_b, cabinet_b = self._setup_cabinet_b()

        skills = self._create_skills()
        categories = self._create_expense_categories()
        materials = self._create_materials()

        # ---- Cabinet A sites (all 5 statuses) --------------------------------
        site_planning = self._create_site(
            cabinet_a, 'Résidence Les Baobabs',
            'Gombe, Kinshasa', SiteStatus.PLANNING,
            TODAY + timedelta(days=60), TODAY + timedelta(days=540),
        )
        site_active = self._create_site(
            cabinet_a, 'Immeuble de Bureaux Centre-Ville',
            'Plateau, Kinshasa', SiteStatus.ACTIVE,
            TODAY - timedelta(days=90), TODAY + timedelta(days=270),
        )
        site_paused = self._create_site(
            cabinet_a, 'Centre Médical de Référence',
            'Limete, Kinshasa', SiteStatus.PAUSED,
            TODAY - timedelta(days=150), TODAY + timedelta(days=180),
        )
        site_completed = self._create_site(
            cabinet_a, 'École Primaire Publique Quartier 9',
            'Ndjili, Kinshasa', SiteStatus.COMPLETED,
            TODAY - timedelta(days=365), TODAY - timedelta(days=30),
        )
        site_cancelled = self._create_site(
            cabinet_a, 'Pont Routier Kimbangu',
            'Kinkole, Kinshasa', SiteStatus.CANCELLED,
            TODAY - timedelta(days=200), TODAY + timedelta(days=400),
        )

        # ---- Cabinet B site (tenant-isolation testing) -----------------------
        site_b = self._create_site(
            cabinet_b, 'Villa Résidentielle Gombe',
            'Gombe, Kinshasa', SiteStatus.ACTIVE,
            TODAY - timedelta(days=45), TODAY + timedelta(days=135),
        )

        self.stdout.write(self.style.SUCCESS('  Sites created (all 5 statuses + 1 tenant-B site)'))

        # ---- Personnel & skills (Cabinet A) ----------------------------------
        personnel = self._create_personnel(cabinet_a, skills)
        self._create_assignments(personnel, site_active, site_paused)
        self.stdout.write(self.style.SUCCESS('  Personnel and assignments created'))

        # ---- Phases & progress -----------------------------------------------
        self._create_phases_and_progress(site_active, site_planning)
        self.stdout.write(self.style.SUCCESS('  Phases and progress reports created'))

        # ---- Budgets ---------------------------------------------------------
        self._create_budgets(
            site_planning, site_active, site_paused,
            site_completed, site_b,
        )
        self.stdout.write(self.style.SUCCESS('  Budgets created'))

        # ---- Expenses (all 4 statuses) on site_active -----------------------
        director = users_a['director']
        engineer = users_a['engineer']
        accountant = users_a['accountant']

        self._create_expenses(site_active, engineer, director, categories)
        self._create_expenses_completed(site_completed, engineer, director, categories)
        self.stdout.write(self.style.SUCCESS('  Expenses created (PENDING / APPROVED / PAID / REJECTED)'))

        # ---- Material requests (all 5 statuses) on site_active ---------------
        self._create_material_requests(site_active, engineer, director, materials)
        self.stdout.write(self.style.SUCCESS('  Material requests created (all 5 statuses)'))

        # ---- Revenue: contracts + invoices + payments -------------------------
        self._create_revenue(
            site_active, site_completed, site_b,
            users_a['accountant'], users_b['director'],
        )
        self.stdout.write(self.style.SUCCESS('  Contracts / invoices / payments created (all 5 invoice statuses)'))

        self._print_summary(superuser, users_a, users_b, cabinet_a, cabinet_b)

    # -------------------------------------------------------------------------
    # CLEAR
    # -------------------------------------------------------------------------

    def _clear_all(self):
        self.stdout.write('Clearing existing data...')
        Payment.objects.all().delete()
        Invoice.objects.all().delete()
        Contract.objects.all().delete()
        ExpenseApproval.objects.all().delete()
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
        Site.all_objects.all().delete()
        Skill.objects.all().delete()
        UserCabinetRole.objects.all().delete()
        Cabinet.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    # -------------------------------------------------------------------------
    # USERS
    # -------------------------------------------------------------------------

    def _create_superuser(self):
        user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@chantier.cd',
                'first_name': 'Super',
                'last_name': 'Admin',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if created:
            user.set_password('Admin1234!')
            user.save()
        return user

    def _make_user(self, username, first, last, email, role_label):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'first_name': first,
                'last_name': last,
            },
        )
        if created:
            user.set_password(PASSWORD)
            user.save()
        return user

    def _setup_cabinet_a(self):
        cabinet, _ = Cabinet.objects.get_or_create(
            name='BTP Congo SARL',
            defaults={
                'address': '12 Avenue de la Paix, Gombe, Kinshasa',
                'tax_id': 'CD-BTP-001234',
            },
        )
        specs = [
            ('directeur_a', 'Jean-Pierre', 'Kabila', 'directeur@btpcongo.cd', UserRoles.DIRECTOR),
            ('chef_ing_a', 'Marie', 'Lukeba', 'chef.ing@btpcongo.cd', UserRoles.CHIEF_ENGINEER),
            ('ing_a', 'Ahmed', 'Mwamba', 'ing@btpcongo.cd', UserRoles.ENGINEER),
            ('comptable_a', 'Fatou', 'Nzuzi', 'comptable@btpcongo.cd', UserRoles.ACCOUNTANT),
            ('caissier_a', 'Moussa', 'Tshilombo', 'caissier@btpcongo.cd', UserRoles.CASHIER),
            ('ouvrier_a', 'Samba', 'Lufungula', 'ouvrier@btpcongo.cd', UserRoles.WORKER),
        ]
        users = {}
        role_map = {
            UserRoles.DIRECTOR: 'director',
            UserRoles.CHIEF_ENGINEER: 'chief_engineer',
            UserRoles.ENGINEER: 'engineer',
            UserRoles.ACCOUNTANT: 'accountant',
            UserRoles.CASHIER: 'cashier',
            UserRoles.WORKER: 'worker',
        }
        for username, first, last, email, role in specs:
            u = self._make_user(username, first, last, email, role)
            UserCabinetRole.objects.get_or_create(
                user=u, cabinet=cabinet,
                defaults={'role': role, 'status': ApprovalStatus.APPROVED},
            )
            users[role_map[role]] = u
        return users, cabinet

    def _setup_cabinet_b(self):
        cabinet, _ = Cabinet.objects.get_or_create(
            name='Constructions Modernes RDC',
            defaults={
                'address': '88 Boulevard du 30 Juin, Kinshasa',
                'tax_id': 'CD-CM-009876',
            },
        )
        specs = [
            ('directeur_b', 'Alain', 'Mbuyamba', 'directeur@constmod.cd', UserRoles.DIRECTOR),
            ('ing_b', 'Cécile', 'Kasongo', 'ing@constmod.cd', UserRoles.ENGINEER),
        ]
        users = {}
        for username, first, last, email, role in specs:
            u = self._make_user(username, first, last, email, role)
            UserCabinetRole.objects.get_or_create(
                user=u, cabinet=cabinet,
                defaults={'role': role, 'status': ApprovalStatus.APPROVED},
            )
            key = 'director' if role == UserRoles.DIRECTOR else 'engineer'
            users[key] = u
        return users, cabinet

    # -------------------------------------------------------------------------
    # REFERENCE DATA
    # -------------------------------------------------------------------------

    def _create_skills(self):
        names = [
            'Maçon', 'Ferrailleur', 'Électricien', 'Plombier',
            'Peintre', 'Menuisier', "Chef d'équipe", 'Chef de chantier',
            'Carreleur', 'Soudeur',
        ]
        skills = []
        for name in names:
            skill, _ = Skill.objects.get_or_create(name=name)
            skills.append(skill)
        return skills

    def _create_expense_categories(self):
        cats = [
            ("Matériaux de Construction", "Ciment, sable, acier, briques…"),
            ("Main-d'œuvre", "Salaires et indemnités des ouvriers"),
            ("Transport et Logistique", "Livraison de matériaux, déplacements"),
            ("Équipements et Outils", "Location ou achat d'engins et outillage"),
            ("Permis et Autorisations", "Frais administratifs de permis"),
            ("Assurance Chantier", "Primes d'assurance tous risques"),
            ("Frais Administratifs", "Fournitures de bureau, communications"),
        ]
        result = []
        for name, desc in cats:
            cat, _ = ExpenseCategory.objects.get_or_create(
                name=name, defaults={'description': desc}
            )
            result.append(cat)
        return result

    def _create_materials(self):
        items = [
            ('Ciment CEM II/A 42.5', 'sacs', '8500'),
            ('Sable Construction 0-4mm', 'm³', '35000'),
            ('Gravier 4-6mm', 'm³', '40000'),
            ('Acier HA500 Ø12mm', 'kg', '950'),
            ('Brique de Construction 20×10×5', 'unité', '350'),
            ('Bloc Parpaing 20×20×40', 'unité', '800'),
            ('Tuiles Béton Ondulées', 'm²', '5500'),
            ('Peinture Intérieure Blanche', 'litre', '12000'),
            ('Fenêtre Aluminium 120×140', 'unité', '85000'),
            ('Porte Métallique 90×210', 'unité', '120000'),
            ('Câble Électrique 2.5mm² (rouleau)', 'rouleau', '45000'),
            ('Tuyau PVC Ø110mm (6m)', 'barre', '9500'),
        ]
        result = []
        for name, unit, cost in items:
            mat, _ = Material.objects.get_or_create(
                name=name,
                defaults={'unit': unit, 'estimated_cost_per_unit': Decimal(cost)},
            )
            result.append(mat)
        return result

    # -------------------------------------------------------------------------
    # SITES
    # -------------------------------------------------------------------------

    def _create_site(self, cabinet, name, location, status, start, end):
        site, _ = Site.objects.get_or_create(
            name=name,
            defaults={
                'cabinet': cabinet,
                'location': location,
                'status': status,
                'start_date': start,
                'expected_end_date': end,
            },
        )
        return site

    # -------------------------------------------------------------------------
    # PERSONNEL
    # -------------------------------------------------------------------------

    def _create_personnel(self, cabinet, skills):
        specs = [
            ('Samba', 'Sané', 15000, [0]),          # Maçon
            ('Ibrahima', 'Touré', 18000, [1]),       # Ferrailleur
            ('Moustapha', 'Camara', 20000, [2]),     # Électricien
            ('Amadou', 'Koné', 19000, [3]),          # Plombier
            ('Lamine', 'Diallo', 16000, [4, 6]),     # Peintre + Chef d'équipe
            ('Kofi', 'Mensah', 17000, [5]),          # Menuisier
            ('Pascal', 'Mutombo', 22000, [7, 9]),    # Chef de chantier + Soudeur
            ('Clémentine', 'Ngoma', 15500, [8]),     # Carreleur
        ]
        people = []
        for first, last, rate, skill_indices in specs:
            person, created = Personnel.objects.get_or_create(
                cabinet=cabinet,
                first_name=first,
                last_name=last,
                defaults={'default_daily_rate': Decimal(rate)},
            )
            if created:
                for idx in skill_indices:
                    person.skills.add(skills[idx])
            people.append(person)
        return people

    def _create_assignments(self, personnel, site_active, site_paused):
        pairs = [
            (personnel[0], site_active, 'Maçon Principal', TODAY - timedelta(days=80), TODAY + timedelta(days=200)),
            (personnel[1], site_active, 'Ferrailleur', TODAY - timedelta(days=75), TODAY + timedelta(days=200)),
            (personnel[2], site_active, 'Électricien', TODAY - timedelta(days=60), TODAY + timedelta(days=180)),
            (personnel[3], site_active, 'Plombier', TODAY - timedelta(days=60), TODAY + timedelta(days=180)),
            (personnel[6], site_active, "Chef de Chantier", TODAY - timedelta(days=90), TODAY + timedelta(days=270)),
            (personnel[4], site_paused, 'Peintre', TODAY - timedelta(days=100), TODAY + timedelta(days=80)),
            (personnel[7], site_paused, 'Carreleur', TODAY - timedelta(days=80), TODAY + timedelta(days=80)),
        ]
        for person, site, role, start, end in pairs:
            SiteAssignment.objects.get_or_create(
                personnel=person,
                site=site,
                defaults={
                    'role': role,
                    'start_date': start,
                    'end_date': end,
                    'daily_rate': person.default_daily_rate,
                },
            )

    # -------------------------------------------------------------------------
    # PHASES & PROGRESS
    # -------------------------------------------------------------------------

    def _create_phases_and_progress(self, site_active, site_planning):
        active_phases = [
            ('Terrassement et Fondations', -90, -30, 100),
            ('Structure Béton (RDC + R+1)', -30, 90, 60),
            ('Cloisons, Menuiserie, Finitions', 90, 210, 0),
        ]
        for name, s_off, e_off, pct in active_phases:
            phase, _ = ProjectPhase.objects.get_or_create(
                site=site_active,
                name=name,
                defaults={
                    'start_date': TODAY + timedelta(days=s_off),
                    'end_date': TODAY + timedelta(days=e_off),
                },
            )
            if pct > 0:
                SiteProgress.objects.get_or_create(
                    phase=phase,
                    report_date=TODAY - timedelta(days=2),
                    defaults={
                        'percentage_complete': pct,
                        'description': f'Avancement phase "{name}": {pct}% réalisé.',
                    },
                )

        planning_phases = [
            ('Étude et Conception', 60, 100),
            ('Obtention des Permis', 100, 150),
            ('Terrassement', 150, 210),
        ]
        for name, s_off, e_off in planning_phases:
            ProjectPhase.objects.get_or_create(
                site=site_planning,
                name=name,
                defaults={
                    'start_date': TODAY + timedelta(days=s_off),
                    'end_date': TODAY + timedelta(days=e_off),
                },
            )

    # -------------------------------------------------------------------------
    # BUDGETS
    # -------------------------------------------------------------------------

    def _create_budgets(self, site_planning, site_active, site_paused, site_completed, site_b):
        entries = [
            (site_planning, '180000000', TODAY + timedelta(days=60), TODAY + timedelta(days=540)),
            (site_active, '250000000', TODAY - timedelta(days=90), TODAY + timedelta(days=270)),
            (site_paused, '95000000', TODAY - timedelta(days=150), TODAY + timedelta(days=180)),
            (site_completed, '60000000', TODAY - timedelta(days=365), TODAY - timedelta(days=30)),
            (site_b, '75000000', TODAY - timedelta(days=45), TODAY + timedelta(days=135)),
        ]
        for site, amount, start, end in entries:
            Budget.objects.get_or_create(
                site=site,
                defaults={
                    'total_amount': Decimal(amount),
                    'start_date': start,
                    'end_date': end,
                },
            )

    # -------------------------------------------------------------------------
    # EXPENSES  (all 4 statuses + ExpenseApproval records)
    # -------------------------------------------------------------------------

    def _create_expenses(self, site, requester, approver, categories):
        # 2 × PENDING — awaiting approval
        for i, (cat_idx, amount, desc) in enumerate([
            (0, '3500000', 'Achat ciment et sable pour le RDC'),
            (1, '1800000', 'Salaires ouvriers — semaine du ' + str(TODAY - timedelta(days=7))),
        ]):
            Expense.objects.get_or_create(
                site=site,
                description=desc,
                defaults={
                    'requester': requester,
                    'category': categories[cat_idx],
                    'amount': Decimal(amount),
                    'expense_date': TODAY - timedelta(days=3 + i),
                    'status': ExpenseStatus.PENDING,
                },
            )

        # 2 × APPROVED — approved, waiting for payment
        for cat_idx, amount, desc, days_ago in [
            (2, '950000', 'Transport matériaux depuis dépôt Limete', 15),
            (3, '2100000', 'Location bétonnière 7 jours', 20),
        ]:
            exp, created = Expense.objects.get_or_create(
                site=site,
                description=desc,
                defaults={
                    'requester': requester,
                    'category': categories[cat_idx],
                    'amount': Decimal(amount),
                    'expense_date': TODAY - timedelta(days=days_ago),
                    'status': ExpenseStatus.APPROVED,
                },
            )
            if created:
                ExpenseApproval.objects.create(
                    expense=exp,
                    approver=approver,
                    status=ExpenseApproval.Status.APPROVED,
                    comments='Approuvé — conforme au budget.',
                )

        # 2 × PAID — approved and disbursed
        for cat_idx, amount, desc, days_ago in [
            (0, '6200000', 'Commande acier HA500 — lot 1', 45),
            (1, '4100000', 'Main-d\'œuvre fondations', 50),
        ]:
            exp, created = Expense.objects.get_or_create(
                site=site,
                description=desc,
                defaults={
                    'requester': requester,
                    'category': categories[cat_idx],
                    'amount': Decimal(amount),
                    'expense_date': TODAY - timedelta(days=days_ago),
                    'status': ExpenseStatus.PAID,
                },
            )
            if created:
                ExpenseApproval.objects.create(
                    expense=exp,
                    approver=approver,
                    status=ExpenseApproval.Status.APPROVED,
                    comments='Approuvé et mis en paiement.',
                )

        # 1 × REJECTED
        exp, created = Expense.objects.get_or_create(
            site=site,
            description='Achat climatiseurs bureau de chantier — luxe injustifié',
            defaults={
                'requester': requester,
                'category': categories[6],
                'amount': Decimal('850000'),
                'expense_date': TODAY - timedelta(days=10),
                'status': ExpenseStatus.REJECTED,
            },
        )
        if created:
            ExpenseApproval.objects.create(
                expense=exp,
                approver=approver,
                status=ExpenseApproval.Status.REJECTED,
                comments='Rejeté — hors budget opérationnel approuvé.',
            )

    def _create_expenses_completed(self, site, requester, approver, categories):
        """A handful of fully paid expenses on the completed site."""
        for cat_idx, amount, desc, days_ago in [
            (0, '8500000', 'Matériaux finitions — lot final', 60),
            (1, '3200000', 'Main-d\'œuvre toiture', 65),
            (4, '450000', 'Permis de réception des travaux', 35),
        ]:
            exp, created = Expense.objects.get_or_create(
                site=site,
                description=desc,
                defaults={
                    'requester': requester,
                    'category': categories[cat_idx],
                    'amount': Decimal(amount),
                    'expense_date': TODAY - timedelta(days=days_ago),
                    'status': ExpenseStatus.PAID,
                },
            )
            if created:
                ExpenseApproval.objects.create(
                    expense=exp,
                    approver=approver,
                    status=ExpenseApproval.Status.APPROVED,
                    comments='Validé avant clôture du chantier.',
                )

    # -------------------------------------------------------------------------
    # MATERIAL REQUESTS  (all 5 statuses)
    # -------------------------------------------------------------------------

    def _create_material_requests(self, site, requester, approver, materials):
        requests_spec = [
            (
                MaterialRequestStatus.PENDING,
                'Matériaux pour démarrage phase 2 — structure béton',
                [(materials[0], 200, 'Qualité CEM II obligatoire'),
                 (materials[1], 50, None),
                 (materials[3], 1500, 'Diamètre 12mm uniquement')],
            ),
            (
                MaterialRequestStatus.APPROVED,
                'Équipements sanitaires et plomberie',
                [(materials[11], 30, 'Ø110mm'),
                 (materials[9], 4, 'Dimensions standard 90×210')],
            ),
            (
                MaterialRequestStatus.REJECTED,
                'Carrelage marbre importé — série prestige',
                [(materials[7], 100, 'Marque Italgres uniquement')],
            ),
            (
                MaterialRequestStatus.ORDERED,
                'Menuiserie aluminium — fenêtres R+1',
                [(materials[8], 12, 'Couleur anthracite, double vitrage')],
            ),
            (
                MaterialRequestStatus.DELIVERED,
                'Électricité — câblage intérieur complet',
                [(materials[10], 20, 'Câble 2.5mm² rouge + bleu + vert'),
                 (materials[11], 25, 'Tuyaux PVC Ø110mm pour évacuations')],
            ),
        ]

        for status, notes, items in requests_spec:
            req, created = MaterialRequest.objects.get_or_create(
                site=site,
                notes=notes,
                defaults={
                    'requested_by': requester,
                    'status': status,
                },
            )
            if created:
                for material, qty, item_notes in items:
                    MaterialRequestItem.objects.create(
                        request=req,
                        material=material,
                        quantity=Decimal(qty),
                        notes=item_notes or '',
                    )

    # -------------------------------------------------------------------------
    # REVENUE: contracts + invoices (all 5 statuses) + payments
    # -------------------------------------------------------------------------

    def _create_revenue(self, site_active, site_completed, site_b, accountant_a, director_b):
        # --- Cabinet A: active site -------------------------------------------
        contract_a, _ = Contract.objects.get_or_create(
            site=site_active,
            defaults={
                'client_name': 'Ministère de l\'Urbanisme et Habitat',
                'total_value': Decimal('320000000'),
                'signed_date': TODAY - timedelta(days=95),
            },
        )

        invoices_spec = [
            # (number_suffix, amount, issued_offset, due_offset, status)
            ('001', '32000000', -80, 10, InvoiceStatus.DRAFT),
            ('002', '48000000', -65, -5, InvoiceStatus.SENT),
            ('003', '64000000', -50, -20, InvoiceStatus.PAID),
            ('004', '48000000', -45, -15, InvoiceStatus.OVERDUE),
            ('005', '32000000', -30, 30, InvoiceStatus.CANCELLED),
        ]

        contract_tag = str(site_active.unique_id)[:8].upper()
        for suffix, amount, i_off, d_off, status in invoices_spec:
            inv_number = f'INV-{contract_tag}-{suffix}'
            inv, created = Invoice.objects.get_or_create(
                invoice_number=inv_number,
                defaults={
                    'contract': contract_a,
                    'amount': Decimal(amount),
                    'issued_date': TODAY + timedelta(days=i_off),
                    'due_date': TODAY + timedelta(days=d_off),
                    'status': status,
                },
            )
            # Attach a payment to the PAID invoice
            if created and status == InvoiceStatus.PAID:
                Payment.objects.create(
                    invoice=inv,
                    amount=Decimal(amount),
                    payment_date=TODAY - timedelta(days=18),
                    method=PaymentMethod.BANK_TRANSFER,
                    reference='VIR-BCC-20240315-0042',
                )

        # --- Cabinet A: completed site ----------------------------------------
        contract_done, _ = Contract.objects.get_or_create(
            site=site_completed,
            defaults={
                'client_name': 'Mairie de Ndjili',
                'total_value': Decimal('75000000'),
                'signed_date': TODAY - timedelta(days=370),
            },
        )
        contract_done_tag = str(site_completed.unique_id)[:8].upper()
        for i, (amount, pdate, method, ref) in enumerate([
            ('25000000', TODAY - timedelta(days=240), PaymentMethod.BANK_TRANSFER, 'VIR-MAIRIE-001'),
            ('25000000', TODAY - timedelta(days=150), PaymentMethod.CHECK, 'CHQ-00123'),
            ('25000000', TODAY - timedelta(days=45), PaymentMethod.MOBILE_MONEY, 'MM-MPESA-88901'),
        ], start=1):
            inv_num = f'INV-{contract_done_tag}-{i:03d}'
            inv, created = Invoice.objects.get_or_create(
                invoice_number=inv_num,
                defaults={
                    'contract': contract_done,
                    'amount': Decimal(amount),
                    'issued_date': TODAY - timedelta(days=260 - i * 70),
                    'due_date': TODAY - timedelta(days=230 - i * 70),
                    'status': InvoiceStatus.PAID,
                },
            )
            if created:
                Payment.objects.create(
                    invoice=inv,
                    amount=Decimal(amount),
                    payment_date=pdate,
                    method=method,
                    reference=ref,
                )

        # --- Cabinet B: active site -------------------------------------------
        contract_b, _ = Contract.objects.get_or_create(
            site=site_b,
            defaults={
                'client_name': 'M. Alain Mbuyamba (Promoteur privé)',
                'total_value': Decimal('90000000'),
                'signed_date': TODAY - timedelta(days=50),
            },
        )
        contract_b_tag = str(site_b.unique_id)[:8].upper()
        inv_b, created = Invoice.objects.get_or_create(
            invoice_number=f'INV-{contract_b_tag}-001',
            defaults={
                'contract': contract_b,
                'amount': Decimal('18000000'),
                'issued_date': TODAY - timedelta(days=30),
                'due_date': TODAY + timedelta(days=15),
                'status': InvoiceStatus.SENT,
            },
        )

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------

    def _print_summary(self, superuser, users_a, users_b, cabinet_a, cabinet_b):
        sep = '=' * 64
        self.stdout.write('\n' + self.style.SUCCESS(sep))
        self.stdout.write(self.style.SUCCESS('  TEST DATA READY — LOGIN CREDENTIALS'))
        self.stdout.write(self.style.SUCCESS(sep))

        self.stdout.write('\n  SUPERUSER (Django admin + all cabinets)')
        self.stdout.write(f'    username : admin')
        self.stdout.write(f'    password : Admin1234!')
        self.stdout.write(f'    url      : /admin/')

        self.stdout.write(f'\n  CABINET A — {cabinet_a.name}')
        role_users = [
            ('DIRECTOR',        users_a['director'],        'directeur_a'),
            ('CHIEF_ENGINEER',  users_a['chief_engineer'],  'chef_ing_a'),
            ('ENGINEER',        users_a['engineer'],        'ing_a'),
            ('ACCOUNTANT',      users_a['accountant'],      'comptable_a'),
            ('CASHIER',         users_a['cashier'],         'caissier_a'),
            ('WORKER',          users_a['worker'],          'ouvrier_a'),
        ]
        for role, user, uname in role_users:
            self.stdout.write(f'    {role:<16} username: {uname:<18} password: {PASSWORD}')

        self.stdout.write(f'\n  CABINET B — {cabinet_b.name}  (tenant isolation)')
        self.stdout.write(f'    DIRECTOR         username: directeur_b      password: {PASSWORD}')
        self.stdout.write(f'    ENGINEER         username: ing_b            password: {PASSWORD}')

        self.stdout.write('\n' + self.style.SUCCESS(sep))
        self.stdout.write(self.style.SUCCESS('  WHAT IS IN THE DATABASE'))
        self.stdout.write(self.style.SUCCESS(sep))
        self.stdout.write('  Sites     : PLANNING / ACTIVE / PAUSED / COMPLETED / CANCELLED')
        self.stdout.write('  Expenses  : 2×PENDING  2×APPROVED  2×PAID  1×REJECTED')
        self.stdout.write('  Mat.Req.  : PENDING / APPROVED / REJECTED / ORDERED / DELIVERED')
        self.stdout.write('  Invoices  : DRAFT / SENT / PAID / OVERDUE / CANCELLED')
        self.stdout.write('  Payments  : bank transfer, cheque, mobile money examples')
        self.stdout.write('  Personnel : 8 workers with skills, assigned to 2 sites')
        self.stdout.write('  Cabinet B : isolated data — not visible to Cabinet A users')
        self.stdout.write(self.style.SUCCESS(sep) + '\n')
