"""
One-off bootstrap command:

  1. Promotes a given email to superuser/staff (default:
     dieudonneishara@gmail.com).
  2. Creates one default demo account per cabinet role (DIRECTOR,
     CHIEF_ENGINEER, ENGINEER, ACCOUNTANT, CASHIER, WORKER), each with a
     random temporary password that MUST be changed on first login
     (enforced by core.middleware.ForcePasswordChangeMiddleware).

Safe to re-run: existing accounts are left untouched (their password is
NOT reset), only their cabinet role is (re)synced.

Usage:
    python manage.py bootstrap_admin_and_roles
    python manage.py bootstrap_admin_and_roles --superuser-email someone@example.com --cabinet "My Cabinet"
"""
import secrets
import string

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import ApprovalStatus, UserRoles

User = get_user_model()

DEFAULT_SUPERUSER_EMAIL = 'dieudonneishara@gmail.com'
DEFAULT_CABINET_NAME = 'Cabinet Principal'


def _generate_temp_password():
    alphabet = string.ascii_letters + string.digits
    return 'Cm-' + ''.join(secrets.choice(alphabet) for _ in range(10)) + '!'


class Command(BaseCommand):
    help = (
        'Promotes a user to superuser and seeds one default account per '
        'cabinet role, each forced to change its temporary password on '
        'first login.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--superuser-email', default=DEFAULT_SUPERUSER_EMAIL)
        parser.add_argument('--cabinet', default=DEFAULT_CABINET_NAME)

    @transaction.atomic
    def handle(self, *args, **options):
        superuser_email = options['superuser_email']
        cabinet_name = options['cabinet']

        # 1. Promote the target account to superuser/staff.
        user = User.objects.filter(email__iexact=superuser_email).first()
        if user is None:
            self.stdout.write(self.style.WARNING(
                f'No existing user with email {superuser_email!r} -- skipping superuser promotion.'
            ))
        else:
            user.is_superuser = True
            user.is_staff = True
            user.save(update_fields=['is_superuser', 'is_staff'])
            self.stdout.write(self.style.SUCCESS(f'{superuser_email} is now a superuser/staff.'))

        # 2. Make sure there is a cabinet to attach the role accounts to.
        cabinet, created = Cabinet.objects.get_or_create(name=cabinet_name)
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created cabinet "{cabinet_name}".'))

        # 3. One default demo account per role.
        created_accounts = []
        for role_value, role_label in UserRoles.choices:
            username = f'{role_value.lower()}_demo'
            email = f'{role_value.lower()}@chantiermobile.local'

            account_user = User.objects.filter(username=username).first()
            if account_user is not None:
                self.stdout.write(f'{username} already exists -- leaving its password untouched.')
            else:
                temp_password = _generate_temp_password()
                account_user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=temp_password,
                    first_name=str(role_label),
                )
                account_user.must_change_password = True
                account_user.save(update_fields=['must_change_password'])
                created_accounts.append((username, email, role_value, temp_password))

            UserCabinetRole.objects.update_or_create(
                user=account_user,
                cabinet=cabinet,
                defaults={'role': role_value, 'status': ApprovalStatus.APPROVED},
            )

        if created_accounts:
            self.stdout.write(self.style.SUCCESS(
                '\nDefault accounts created (temporary password -- must be changed on first login):'
            ))
            self.stdout.write(self.style.SUCCESS(f'{"USERNAME":<20}{"EMAIL":<32}{"ROLE":<18}PASSWORD'))
            for username, email, role, pwd in created_accounts:
                self.stdout.write(f'{username:<20}{email:<32}{role:<18}{pwd}')
        else:
            self.stdout.write('No new accounts created (they already existed).')
