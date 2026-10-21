"""Existing phone numbers into "+243…" form, and each linked worker's
login number onto their Personnel record (2026-10-21, WhatsApp-ready)."""
from django.db import migrations


def forwards(apps, schema_editor):
    from django.core.exceptions import ValidationError
    from core.phone import normalize_phone
    User = apps.get_model('accounts', 'User')
    Personnel = apps.get_model('personnel', 'Personnel')
    for user in User.objects.exclude(phone_number__isnull=True).exclude(phone_number=''):
        try:
            normalized = normalize_phone(user.phone_number)
        except ValidationError:
            continue  # leave an unreadable number as typed; the form will flag it
        if normalized != user.phone_number:
            User.objects.filter(pk=user.pk).update(phone_number=normalized)
    for person in Personnel.objects.filter(phone_number='', user__isnull=False).select_related('user'):
        try:
            number = normalize_phone(person.user.phone_number or '')
        except ValidationError:
            continue
        if number:
            Personnel.objects.filter(pk=person.pk).update(phone_number=number)


class Migration(migrations.Migration):
    dependencies = [
        ('personnel', '0018_whatsapp_phone'),
        ('accounts', '0015_whatsapp_phone'),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
