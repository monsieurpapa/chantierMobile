"""
Automatic capture for the superadmin audit journal (core.AuditLogEntry).

Nothing in the business apps calls this module: it listens instead.

- AuditContextMiddleware remembers the current request (in a contextvar)
  so a model signal fired deep inside a view or form knows who is acting,
  from which IP, on which URL.
- pre_save / post_save / post_delete receivers record CREATE, UPDATE (with
  a field-by-field before/after diff), soft DELETE / RESTORE (the
  is_deleted flag of core.models.SoftDeleteModel flipping) and real
  HARD_DELETE on every model of the TRACKED_APPS.
- The auth signals record LOGIN, LOGOUT and LOGIN_FAILED.
- A superadmin's cabinet switch (accounts.CabinetContextLog) is recorded
  as CABINET_SWITCH.

What is NOT captured: QuerySet.update() / bulk_create() (Django sends no
per-row signals for those), and raw fixture loading. Writing to the
journal never breaks the action being journaled: any error is logged and
swallowed inside its own savepoint.
"""
import contextvars
import datetime
import decimal
import ipaddress
import logging

from django.apps import apps as global_apps
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import timezone

from chantiermobile.constants import AuditAction

logger = logging.getLogger(__name__)

# Apps whose models are journaled. core is left out on purpose: its models
# are themselves logs / notifications (journaling them would be noise, and
# journaling AuditLogEntry would recurse).
TRACKED_APPS = {
    'accounts', 'projects', 'finance', 'personnel', 'materials',
    'revenue', 'pricing', 'procurement', 'tasks',
}
# Models handled specially (CabinetContextLog) or pure bookkeeping.
EXCLUDED_MODELS = {'accounts.cabinetcontextlog'}

# Fields never shown in a diff: bookkeeping the journal already records in
# its own columns (who/when), or noise that changes on every login.
IGNORED_FIELDS = {
    'id', 'created_at', 'updated_at', 'created_by', 'updated_by',
    'deleted_at', 'is_deleted', 'unique_id', 'last_login',
}
# Fields whose value must never be written to the journal.
SECRET_FIELDS = {'password'}
SECRET_PLACEHOLDER = '••••••'

MAX_VALUE_LENGTH = 300
SYSTEM_LABEL = 'Système'

_current_request = contextvars.ContextVar('audit_current_request', default=None)


# ---------------------------------------------------------------------------
# Request context
# ---------------------------------------------------------------------------

class AuditContextMiddleware:
    """Makes the current request available to the audit signal receivers.
    Must sit after AuthenticationMiddleware (it reads request.user lazily,
    at the time a change is journaled)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_request.set(request)
        try:
            return self.get_response(request)
        finally:
            _current_request.reset(token)


def get_current_request():
    return _current_request.get()


def _client_ip(request):
    """First address of X-Forwarded-For (Railway / Cloud Run sit behind a
    proxy), else REMOTE_ADDR. Anything that isn't a valid IP is dropped
    rather than stored — the header is client-controlled."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    candidate = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '')
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def _request_fields(request):
    if request is None:
        return {}
    return {
        'ip_address': _client_ip(request),
        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:255],
        'request_method': (request.method or '')[:10],
        'request_path': request.path[:255],
    }


def _user_label(user):
    if user is None:
        return SYSTEM_LABEL
    full_name = user.get_full_name() if hasattr(user, 'get_full_name') else ''
    return (f"{full_name} ({user.username})" if full_name else user.username)[:255]


def _current_actor(request):
    user = getattr(request, 'user', None) if request is not None else None
    if user is not None and getattr(user, 'is_authenticated', False):
        return user
    return None


# ---------------------------------------------------------------------------
# Writing entries
# ---------------------------------------------------------------------------

def _enabled():
    return getattr(settings, 'AUDIT_LOG_ENABLED', True)


def record(action, *, instance=None, actor=None, actor_label=None, changes=None,
           cabinet_id=None, request=None, object_repr=None, use_request_actor=True):
    """Write one journal entry. Safe to call from anywhere: failures are
    logged, never raised, and never poison the caller's transaction."""
    if not _enabled():
        return None
    from django.contrib.contenttypes.models import ContentType
    from core.models import AuditLogEntry

    if request is None:
        request = get_current_request()
    if actor is None and use_request_actor:
        actor = _current_actor(request)

    try:
        with transaction.atomic():
            fields = {
                'action': action,
                'actor': actor,
                'actor_label': actor_label if actor_label is not None else _user_label(actor),
                'changes': changes or {},
                'cabinet_id': cabinet_id,
                **_request_fields(request),
            }
            if instance is not None:
                # _meta.model, not type(): on logout Django hands over
                # request.user, a SimpleLazyObject whose type() is the wrapper.
                fields['content_type'] = ContentType.objects.get_for_model(instance._meta.model)
                fields['object_id'] = str(instance.pk)[:64]
                fields['object_repr'] = (object_repr if object_repr is not None else _safe_str(instance))[:255]
            elif object_repr is not None:
                fields['object_repr'] = object_repr[:255]
            return AuditLogEntry.objects.create(**fields)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Could not write audit journal entry (%s)", action)
        return None


def _safe_str(obj):
    try:
        return str(obj)
    except Exception:
        return f"{type(obj).__name__} #{getattr(obj, 'pk', '?')}"


# ---------------------------------------------------------------------------
# Model change capture
# ---------------------------------------------------------------------------

def _is_tracked(sender):
    # Historical models used inside data migrations live in their own app
    # registry — never journal those.
    if getattr(sender._meta, 'apps', None) is not global_apps:
        return False
    if sender._meta.app_label not in TRACKED_APPS:
        return False
    return sender._meta.label_lower not in EXCLUDED_MODELS


def _tracked_fields(model):
    return [
        f for f in model._meta.concrete_fields
        if f.name not in IGNORED_FIELDS and not f.primary_key
    ]


def _normalize(field, value):
    if value is None or value == '':
        return None
    try:
        return field.to_python(value)
    except Exception:
        return value


def _display(field, raw):
    """Human-readable string for a raw field value, as shown in the journal."""
    if field.name in SECRET_FIELDS:
        return SECRET_PLACEHOLDER if raw not in (None, '') else None
    if raw is None or raw == '':
        return None
    if field.is_relation and field.related_model is not None:
        related = field.related_model._base_manager.filter(pk=raw).first()
        text = _safe_str(related) if related is not None else f"#{raw}"
    elif field.choices:
        text = str(dict(field.flatchoices).get(raw, raw))
    elif isinstance(raw, bool):
        text = 'Oui' if raw else 'Non'
    elif isinstance(raw, datetime.datetime):
        text = timezone.localtime(raw).strftime('%d/%m/%Y %H:%M') if timezone.is_aware(raw) else raw.strftime('%d/%m/%Y %H:%M')
    elif isinstance(raw, datetime.date):
        text = raw.strftime('%d/%m/%Y')
    elif isinstance(raw, decimal.Decimal):
        text = format(raw.normalize(), 'f') if raw == raw.to_integral() else str(raw)
    elif isinstance(field, models.FileField):
        text = str(getattr(raw, 'name', raw) or '')
    else:
        text = str(raw)
    if len(text) > MAX_VALUE_LENGTH:
        text = text[:MAX_VALUE_LENGTH - 1] + '…'
    return text


def _change(field, old, new):
    return {
        'label': str(field.verbose_name).capitalize(),
        'old': _display(field, old),
        'new': _display(field, new),
    }


def _current_values(instance):
    return {f.attname: getattr(instance, f.attname, None) for f in _tracked_fields(type(instance))}


def resolve_cabinet_id(obj, depth=0, _seen=None):
    """The Cabinet a record belongs to, found by walking its foreign keys
    (Site → cabinet, Invoice → contract → site → cabinet, …). Prefers a
    direct `cabinet`, then `site`, then any other FK. None when the record
    isn't cabinet-scoped (a User, a global catalogue item)."""
    from accounts.models import Cabinet
    if obj is None:
        return None
    if isinstance(obj, Cabinet):
        return obj.pk
    cabinet_id = getattr(obj, 'cabinet_id', None)
    if cabinet_id:
        return cabinet_id
    if depth >= 3:
        return None
    _seen = _seen or set()
    key = (type(obj), obj.pk)
    if key in _seen:
        return None
    _seen.add(key)

    user_model = global_apps.get_model(settings.AUTH_USER_MODEL)
    fks = [
        f for f in obj._meta.concrete_fields
        if f.is_relation and (f.many_to_one or f.one_to_one)
        and f.related_model not in (None, user_model)
        and f.related_model._meta.app_label in TRACKED_APPS
    ]
    fks.sort(key=lambda f: 0 if f.name == 'site' else 1)
    for f in fks:
        if getattr(obj, f.attname, None) is None:
            continue
        try:
            parent = getattr(obj, f.name)
        except Exception:
            continue
        found = resolve_cabinet_id(parent, depth + 1, _seen)
        if found:
            return found
    return None


def _safe_cabinet_id(instance):
    try:
        return resolve_cabinet_id(instance)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Could not resolve cabinet for audit entry")
        return None


def _on_pre_save(sender, instance, raw=False, **kwargs):
    if raw or not _enabled() or not _is_tracked(sender) or instance.pk is None:
        return
    fields = _tracked_fields(sender)
    attnames = [f.attname for f in fields]
    if issubclass(sender, _soft_delete_model()):
        attnames.append('is_deleted')
    try:
        instance._audit_old = sender._base_manager.filter(pk=instance.pk).values(*attnames).first()
    except Exception:  # pragma: no cover - defensive
        instance._audit_old = None


def _soft_delete_model():
    from core.models import SoftDeleteModel
    return SoftDeleteModel


def _on_post_save(sender, instance, created, raw=False, **kwargs):
    if raw or not _enabled():
        return
    if sender._meta.label_lower == 'accounts.cabinetcontextlog':
        if created:
            _record_cabinet_switch(instance)
        return
    if not _is_tracked(sender):
        return

    fields = _tracked_fields(sender)
    old = getattr(instance, '_audit_old', None)
    instance._audit_old = None

    if created or old is None:
        changes = {}
        for f in fields:
            value = getattr(instance, f.attname, None)
            if value in (None, ''):
                continue
            changes[f.name] = _change(f, None, value)
        record(AuditAction.CREATE, instance=instance, changes=changes,
               cabinet_id=_safe_cabinet_id(instance))
        return

    changes = {}
    for f in fields:
        before, after = old.get(f.attname), getattr(instance, f.attname, None)
        if _normalize(f, before) != _normalize(f, after):
            changes[f.name] = _change(f, before, after)

    action = AuditAction.UPDATE
    if 'is_deleted' in old:
        was_deleted, is_deleted = bool(old['is_deleted']), bool(getattr(instance, 'is_deleted', False))
        if is_deleted and not was_deleted:
            action = AuditAction.DELETE
        elif was_deleted and not is_deleted:
            action = AuditAction.RESTORE

    if action == AuditAction.UPDATE and not changes:
        return  # a save that changed nothing worth journaling
    record(action, instance=instance, changes=changes, cabinet_id=_safe_cabinet_id(instance))


def _on_post_delete(sender, instance, **kwargs):
    if not _enabled() or not _is_tracked(sender):
        return
    record(AuditAction.HARD_DELETE, instance=instance, cabinet_id=_safe_cabinet_id(instance))


def _record_cabinet_switch(log):
    cabinet = log.cabinet
    record(
        AuditAction.CABINET_SWITCH,
        instance=cabinet,
        actor=log.switched_by,
        object_repr=_safe_str(cabinet) if cabinet is not None else 'Tous les cabinets',
        cabinet_id=cabinet.pk if cabinet is not None else None,
    )


# ---------------------------------------------------------------------------
# Links to a record's history (superadmin only)
# ---------------------------------------------------------------------------

def history_url_for(user, obj):
    """URL of the journal filtered to `obj`'s history, or '' when `user`
    isn't a superuser (the journal is superadmin-only)."""
    if obj is None or getattr(obj, 'pk', None) is None or not getattr(user, 'is_superuser', False):
        return ''
    from django.contrib.contenttypes.models import ContentType
    from django.urls import reverse
    from django.utils.http import urlencode

    ct = ContentType.objects.get_for_model(obj._meta.model)
    return reverse('audit_log_list') + '?' + urlencode({'model': ct.pk, 'object_id': obj.pk})


def history_header_actions(request, obj):
    """PageHeaderMixin header action(s) for a record's "Historique" button:
    a one-item list for a superuser, [] for anyone else. Usage in a view:
    `return [...own actions] + history_header_actions(self.request, self.object)`."""
    from django.utils.translation import gettext_lazy as _
    url = history_url_for(getattr(request, 'user', None), obj)
    if not url:
        return []
    return [{
        'label': _("Historique"),
        'url': url,
        'icon': 'history',
        'class': 'btn-falcon-default',
    }]


# ---------------------------------------------------------------------------
# Authentication capture
# ---------------------------------------------------------------------------

def _on_login(sender, request, user, **kwargs):
    record(AuditAction.LOGIN, instance=user, actor=user, request=request)


def _on_logout(sender, request, user, **kwargs):
    if user is None or not getattr(user, 'is_authenticated', False):
        return
    record(AuditAction.LOGOUT, instance=user, actor=user, request=request)


def _on_login_failed(sender, credentials, request=None, **kwargs):
    # credentials is already cleansed by Django (password masked); only the
    # identifier the person typed is kept.
    attempted = ''
    for key in ('username', 'login', 'email'):
        if credentials.get(key):
            attempted = str(credentials[key])[:150]
            break
    record(
        AuditAction.LOGIN_FAILED,
        request=request,
        actor_label=attempted or '(inconnu)',
        object_repr=attempted,
        use_request_actor=False,
    )


def connect_signals():
    pre_save.connect(_on_pre_save, dispatch_uid='core.audit.pre_save')
    post_save.connect(_on_post_save, dispatch_uid='core.audit.post_save')
    post_delete.connect(_on_post_delete, dispatch_uid='core.audit.post_delete')
    user_logged_in.connect(_on_login, dispatch_uid='core.audit.login')
    user_logged_out.connect(_on_logout, dispatch_uid='core.audit.logout')
    user_login_failed.connect(_on_login_failed, dispatch_uid='core.audit.login_failed')
