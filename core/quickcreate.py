import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views import View

from .mixins import CabinetAccessMixin


class QuickCreateView(CabinetAccessMixin, LoginRequiredMixin, View):
    """
    Generic POST-only JSON endpoint backing a DynamicSelectWidget field.

    Given {"name": "<text typed in the picker>"} (plus whatever extra
    context params a specific field sends, e.g. "site"), creates a minimal
    record and returns {"id": ..., "text": ...} so the picker can select it
    immediately — no page reload, no separate "create X first" detour.

    The record is deliberately minimal: whoever typed it is in the middle
    of filling out an unrelated form (an expense, a purchase order, ...),
    not this record's own create screen. Only what's needed to identify it
    is captured here; anything else gets filled in later from that
    record's own edit screen, progressively, as the codebase's data grows
    through normal use.

    Subclass and set `model`, override `build_instance()`, and optionally
    `display_text()` / `after_create()`. Set `cabinet_scoped = False` for a
    model with no cabinet FK (a genuinely global catalog, e.g. Material).
    """
    model = None
    cabinet_scoped = True

    def build_instance(self, name, request, cabinet, payload):
        raise NotImplementedError

    def display_text(self, instance):
        return str(instance)

    def after_create(self, instance, request, payload):
        """Hook for a side effect once the record is saved — e.g.
        auto-assigning a newly created worker to the site the picker was
        scoped to, so they immediately show up wherever that scoping is
        re-applied (a subsequent reload of the same site-scoped list)."""
        pass

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode('utf-8')) if request.body else {}
        except (ValueError, UnicodeDecodeError):
            payload = request.POST.dict()

        name = (payload.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': _('Un nom est requis.')}, status=400)

        cabinet = None
        if self.cabinet_scoped:
            cabinet = self.get_user_cabinet()
            if cabinet is None:
                return JsonResponse({'error': _("Impossible de déterminer le cabinet actif.")}, status=403)

        try:
            instance = self.build_instance(name, request, cabinet, payload)
            instance.save()
            self.after_create(instance, request, payload)
        except ValidationError as e:
            messages = e.messages if hasattr(e, 'messages') else [str(e)]
            return JsonResponse({'error': ' '.join(messages)}, status=400)
        except IntegrityError:
            return JsonResponse({'error': _('Cet élément existe peut-être déjà.')}, status=400)

        return JsonResponse({'id': instance.pk, 'text': self.display_text(instance)})
