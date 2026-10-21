"""
Phone numbers stored in international (E.164) form, ready for WhatsApp —
added 2026-10-21. Most of the client's communication and site reporting
happens on WhatsApp, and its API (like a wa.me link) wants "+243…" with
no spaces or leading zero.

People type numbers every possible way ("0991 234 567", "+243 991-234-567",
"00243991234567", "991234567"); `normalize_phone` turns them all into
"+243991234567". A number without a country code is taken as Congolese
(DRC, +243) unless it starts with "+" or "00".
"""
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

DEFAULT_COUNTRY_CODE = '243'  # RD Congo
_SEPARATORS = re.compile(r'[\s\-.()/]')


def normalize_phone(value, default_country_code=DEFAULT_COUNTRY_CODE):
    """Return `value` as "+<country><number>", or raise ValidationError.
    Blank stays blank."""
    if value is None:
        return value
    raw = _SEPARATORS.sub('', str(value).strip())
    if not raw:
        return ''
    if raw.startswith('00'):
        raw = '+' + raw[2:]
    if raw.startswith('+'):
        digits = raw[1:]
    elif raw.startswith('0'):
        digits = default_country_code + raw[1:]
    elif raw.startswith(default_country_code) and len(raw) > 10:
        digits = raw
    else:
        digits = default_country_code + raw
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise ValidationError(
            _("Numéro de téléphone invalide : « %(value)s ». Exemple : +243 991 234 567 ou 0991 234 567."),
            code='invalid_phone', params={'value': value},
        )
    return '+' + digits


def whatsapp_url(phone):
    """https://wa.me/243991234567 — opens a WhatsApp chat with `phone`."""
    if not phone:
        return ''
    return 'https://wa.me/' + phone.lstrip('+')


class PhoneNumberField(models.CharField):
    """A CharField that stores numbers in E.164 form. Normalised when a
    form or full_clean() validates it, and again on save for numbers
    assigned in code."""
    description = _('Numéro de téléphone (format international)')

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 20)
        kwargs.setdefault('verbose_name', _('Téléphone (WhatsApp)'))
        kwargs.setdefault('help_text', _("Format international, ex. +243 991 234 567 — utilisé pour WhatsApp."))
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        return normalize_phone(super().to_python(value))

    def pre_save(self, model_instance, add):
        value = getattr(model_instance, self.attname)
        if value:
            try:
                value = normalize_phone(value)
            except ValidationError:
                pass  # keep what was typed; full_clean() reports it
            setattr(model_instance, self.attname, value)
        return value

    def formfield(self, **kwargs):
        from django import forms
        kwargs.setdefault('widget', forms.TextInput(attrs={
            'class': 'form-control', 'type': 'tel', 'inputmode': 'tel', 'autocomplete': 'tel',
            'placeholder': '+243 991 234 567',
        }))
        return super().formfield(**kwargs)
