"""Shared PDF building blocks for every document the app generates.

Layout and branding follow the client's own "DEVIS GLOBAL" sheet (ATGC
Congo, 2026-10-20):

- letterhead: the cabinet's legal name in blue serif italic, then its logo,
  legal mentions (agrément, RCCM, ID. NAT.) in blue and its contacts;
- a boxed title with label/value rows (Adresse, Maître d'ouvrage, ...);
- tables with a peach header row, blue étape rows, pale-green sub-section
  rows, pale-blue totals and a peach grand total;
- the amount in words, "Fait à <ville>, le <date>" and signature boxes when
  the document needs an approval trail (DQE, devis);
- page numbers and the generation date in the footer of every page.

The letterhead comes from the cabinet (Cabinet.legal_name, short_name,
legal_mentions, phone, email, city, logo), so each cabinet's documents carry
its own branding.

Entry points:
- render_table_report_pdf(): any tabular report (expenses, caisse, stock,
  payroll, invoices...). Signatures optional.
- render_bordereau_pdf(): a priced bill of quantities grouped by étape (DQE,
  devis), with totals, amount in words and signatures.
- bordereau_sections(): turns DQE/devis lines into the étape structure that
  render_bordereau_pdf() expects.
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from typing import List, Optional
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone

# Colours sampled from the reference sheet.
BRAND_BLUE = '#0070C0'
HEADER_PEACH = '#FAC090'
SECTION_BLUE = '#95B3D7'
GROUP_GREEN = '#EBF1DE'
TOTAL_BLUE = '#DCE6F2'
ZEBRA = '#F7F9FC'
GRID = '#808080'

# The standard PDF fonts only cover Windows-1252; map the few characters
# that show up in this app's data and fall outside it.
_CHAR_FALLBACKS = {'ϕ': 'Ø', 'φ': 'Ø', 'Φ': 'Ø', '≤': '<=', '≥': '>=', '×': 'x', '→': '->', '←': '<-',
                   '\u202f': '\xa0', '\u2009': ' '}


def plain_text(value):
    """Keep to characters the standard PDF fonts can draw (no escaping)."""
    text = '' if value is None else str(value)
    for char, repl in _CHAR_FALLBACKS.items():
        text = text.replace(char, repl)
    return text.encode('cp1252', errors='replace').decode('cp1252')


def pdf_text(value):
    """plain_text(), escaped for ReportLab paragraphs."""
    return escape(plain_text(value))


def fmt_amount(value, decimals=2):
    """French grouping: 51 900,10 (non-breaking space between thousands)."""
    if value is None or value == '':
        return ''
    amount = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    sign = '-' if amount < 0 else ''
    whole, _, frac = f'{abs(amount):.{decimals}f}'.partition('.')
    groups = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    text = '\xa0'.join(groups) or '0'
    return f'{sign}{text},{frac}' if decimals else f'{sign}{text}'


def fmt_quantity(value):
    if value is None or value == '':
        return ''
    q = Decimal(str(value))
    return fmt_amount(q, 0) if q == q.to_integral_value() else fmt_amount(q, 2)


def montant_en_lettres(amount, currency_singular='dollar américain', currency_plural='dollars américains'):
    """51900.10 -> "cinquante et un mille neuf cents dollars américains et
    dix cents" (French, as written under a devis total)."""
    from num2words import num2words
    amount = Decimal(str(amount or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    whole = int(abs(amount))
    cents = int((abs(amount) - whole) * 100)
    words = num2words(whole, lang='fr')
    # "un million de dollars", "deux milliards de dollars" (but "mille dollars").
    de = ' de' if whole and whole % 1_000_000 == 0 else ''
    unit = currency_singular if whole <= 1 else currency_plural
    text = f'{words}{de} {unit}'
    if cents:
        text += f" et {num2words(cents, lang='fr')} cent{'s' if cents > 1 else ''}"
    if amount < 0:
        text = 'moins ' + text
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def _styles():
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    base = dict(fontName='Helvetica', fontSize=8.5, leading=10.5, textColor=colors.black)
    return {
        'brand': ParagraphStyle('brand', fontName='Times-BoldItalic', fontSize=19, leading=23,
                                textColor=colors.HexColor(BRAND_BLUE), alignment=TA_CENTER),
        'mentions': ParagraphStyle('mentions', fontName='Helvetica', fontSize=8.5, leading=11,
                                   textColor=colors.HexColor(BRAND_BLUE)),
        'contacts': ParagraphStyle('contacts', fontName='Helvetica', fontSize=8.5, leading=11),
        'box_title': ParagraphStyle('box_title', fontName='Helvetica-Bold', fontSize=12.5, leading=15, alignment=TA_CENTER),
        'box_label': ParagraphStyle('box_label', fontName='Helvetica', fontSize=9, leading=11, alignment=TA_RIGHT),
        'box_value': ParagraphStyle('box_value', fontName='Helvetica', fontSize=9, leading=11),
        'cell': ParagraphStyle('cell', **base),
        'cell_bold': ParagraphStyle('cell_bold', **{**base, 'fontName': 'Helvetica-Bold'}),
        'cell_right': ParagraphStyle('cell_right', **{**base, 'alignment': TA_RIGHT}),
        'cell_center': ParagraphStyle('cell_center', **{**base, 'alignment': TA_CENTER}),
        'head': ParagraphStyle('head', fontName='Helvetica-Bold', fontSize=9.5, leading=11.5, alignment=TA_CENTER),
        'section': ParagraphStyle('section', fontName='Helvetica-Bold', fontSize=10.5, leading=13, alignment=TA_CENTER),
        'total_label': ParagraphStyle('total_label', fontName='Helvetica-Bold', fontSize=9.5, leading=12, alignment=TA_CENTER),
        'subtotal_label': ParagraphStyle('subtotal_label', fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=TA_RIGHT),
        'amount_bold': ParagraphStyle('amount_bold', fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=TA_RIGHT),
        'text': ParagraphStyle('text', fontName='Helvetica', fontSize=9, leading=12),
        'text_right': ParagraphStyle('text_right', fontName='Helvetica', fontSize=9, leading=12, alignment=TA_RIGHT),
        'sig_title': ParagraphStyle('sig_title', fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=TA_CENTER),
        'sig_sub': ParagraphStyle('sig_sub', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_CENTER,
                                  textColor=colors.HexColor('#404040')),
        'sig_line': ParagraphStyle('sig_line', fontName='Helvetica', fontSize=8, leading=13, alignment=TA_LEFT),
        'stamp': ParagraphStyle('stamp', fontName='Helvetica-Oblique', fontSize=7.5, leading=9, alignment=TA_CENTER,
                                textColor=colors.HexColor('#2E7D32')),
    }


def _logo_flowable(cabinet, max_w, max_h):
    from reportlab.platypus import Image
    from reportlab.lib.utils import ImageReader
    if cabinet is None or not getattr(cabinet, 'logo', None):
        return None
    try:
        with cabinet.logo.open('rb') as fh:
            data = BytesIO(fh.read())
        iw, ih = ImageReader(data).getSize()
        data.seek(0)
        scale = min(max_w / iw, max_h / ih)
        return Image(data, width=iw * scale, height=ih * scale)
    except Exception:
        return None  # a missing/unreachable logo must never break a document


def letterhead(cabinet, width):
    """The cabinet's header block, as a list of flowables."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
    from reportlab.platypus.flowables import HRFlowable
    st = _styles()
    name = (getattr(cabinet, 'legal_name', '') or getattr(cabinet, 'name', '') or 'ChantierMobile') if cabinet else 'ChantierMobile'
    elements = [Paragraph(pdf_text(name), st['brand']), Spacer(1, 0.15 * cm)]
    if cabinet is None:
        elements.append(HRFlowable(width='100%', thickness=1.2, color=colors.HexColor(BRAND_BLUE), spaceAfter=0.3 * cm))
        return elements

    mentions = [pdf_text(l.strip()) for l in (getattr(cabinet, 'legal_mentions', '') or '').splitlines() if l.strip()]
    if not mentions and cabinet.tax_id:
        mentions = [f'NIF : {pdf_text(cabinet.tax_id)}']
    contacts = []
    if getattr(cabinet, 'phone', ''):
        contacts.append(f'<b>Contact :</b> {pdf_text(cabinet.phone)}')
    if getattr(cabinet, 'email', ''):
        contacts.append(f'<b>Email :</b> {pdf_text(cabinet.email)}')
    if cabinet.address:
        contacts.append(pdf_text(' '.join(cabinet.address.split())))

    logo = _logo_flowable(cabinet, 4.2 * cm, 2.4 * cm)
    logo_w = 4.6 * cm if logo else 0.01 * cm
    contact_w = 6.4 * cm
    row = [logo or '', Paragraph('<br/>'.join(mentions), st['mentions']), Paragraph('<br/>'.join(contacts), st['contacts'])]
    table = Table([row], colWidths=[logo_w, width - logo_w - contact_w, contact_w])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements += [table, Spacer(1, 0.1 * cm),
                 HRFlowable(width='100%', thickness=1.2, color=colors.HexColor(BRAND_BLUE), spaceAfter=0.35 * cm)]
    return elements


def title_box(title, rows, width):
    """Boxed title with label/value rows, like the reference's
    "PROJET DE ..." / Adresse / Maître d'ouvrage block."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle
    st = _styles()
    label_w = 4.2 * cm
    data = [[Paragraph(pdf_text(title), st['box_title']), '']]
    for label, value in rows:
        data.append([Paragraph(pdf_text(label) + ' :', st['box_label']), Paragraph(pdf_text(value), st['box_value'])])
    table = Table(data, colWidths=[label_w, width - label_w])
    style = [
        ('SPAN', (0, 0), (1, 0)),
        ('BOX', (0, 0), (-1, -1), 1.2, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 6), ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
    ]
    if rows:
        style += [('INNERGRID', (0, 1), (-1, -1), 0.5, colors.black)]
    table.setStyle(TableStyle(style))
    return table


@dataclass
class Signatory:
    """One signature box: role title, optional subtitle (e.g. the cabinet's
    "Pour l'A.T.G.C."), the person's name if known, and an optional stamp
    line recorded by the app (e.g. "Approuvé le 20/10/2026")."""
    title: str
    subtitle: str = ''
    name: str = ''
    stamp: str = ''


def signature_section(signatories, width, *, place=None, date=None, amount=None):
    """Amount in words, "Fait à ..., le ..." and the signature boxes, kept
    together on one page."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle, Spacer, KeepTogether
    st = _styles()
    parts = []
    if amount is not None:
        parts.append(Paragraph(f'<b>Nous disons en toute lettre :</b> {pdf_text(montant_en_lettres(amount))}.', st['text']))
        parts.append(Spacer(1, 0.25 * cm))
    date = date or timezone.localdate()
    parts.append(Paragraph(f'Fait à {pdf_text(place) if place else "................................"}, le {date.strftime("%d/%m/%Y")}', st['text_right']))
    parts.append(Spacer(1, 0.3 * cm))
    if signatories:
        cells = []
        for s in signatories:
            inner = [
                Paragraph(pdf_text(s.title), st['sig_title']),
                Paragraph(pdf_text(s.subtitle) if s.subtitle else '&nbsp;', st['sig_sub']),
                Spacer(1, 1.6 * cm),
                Paragraph(f'Nom : {pdf_text(s.name) if s.name else "...................................."}', st['sig_line']),
                Paragraph('Date : ....../....../...........', st['sig_line']),
            ]
            if s.stamp:
                inner.append(Paragraph(pdf_text(s.stamp), st['stamp']))
            cells.append(inner)
        col_w = width / len(cells)
        table = Table([cells], colWidths=[col_w] * len(cells))
        table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor(GRID)),
            ('INNERGRID', (0, 0), (-1, -1), 0.8, colors.HexColor(GRID)),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        parts.append(table)
    return KeepTogether(parts)


def _numbered_canvas_class(footer_left):
    """A canvas that writes "Page n / N" and a short footer on every page."""
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_pages = []

        def showPage(self):
            self._saved_pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_pages)
            for state in self._saved_pages:
                self.__dict__.update(state)
                w, _h = self._pagesize
                self.setFont('Helvetica', 7.5)
                self.setFillColor(colors.HexColor('#606060'))
                self.drawString(1.5 * cm, 0.9 * cm, footer_left)
                self.drawRightString(w - 1.5 * cm, 0.9 * cm, f'Page {self._pageNumber} / {total}')
                super().showPage()
            super().save()

    return NumberedCanvas


def _build(elements, *, pagesize, footer_left):
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=pagesize, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.6 * cm)
    doc.build(elements, canvasmaker=_numbered_canvas_class(footer_left))
    return buffer.getvalue()


def _footer_text(cabinet, generated_by):
    who = f' par {generated_by}' if generated_by else ''
    org = (getattr(cabinet, 'short_name', '') or getattr(cabinet, 'name', '')) if cabinet else ''
    prefix = f'{org} — ' if org else ''
    return plain_text(f"{prefix}Document généré par ChantierMobile le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')}{who}")


def pdf_response(content, filename):
    response = HttpResponse(content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def cabinet_for_request(request):
    """The cabinet whose letterhead a report should carry: the superadmin's
    active cabinet, else the user's only approved cabinet. None when it's
    ambiguous (several cabinets) — the report then gets a neutral header."""
    from core.mixins import get_session_cabinet
    cabinet = get_session_cabinet(request)
    if cabinet is not None:
        return cabinet
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return None
    roles = getattr(user, 'approved_cabinet_roles', None)
    if roles is None:
        return None
    cabinets = {r.cabinet for r in roles.select_related('cabinet')}
    return cabinets.pop() if len(cabinets) == 1 else None


# ---------------------------------------------------------------------------
# Tabular reports
# ---------------------------------------------------------------------------

def render_table_report_pdf(*, filename, title, subtitle, columns, rows, totals_row=None, generated_by=None,
                            cabinet=None, info_rows=None, signatories=None, place=None, amount_in_words=None,
                            col_widths=None):
    """Render a tabular report with the cabinet's letterhead and return it
    as an HttpResponse.

    - filename: e.g. "depenses-2024-01.pdf" (Content-Disposition)
    - title: e.g. "Rapport des dépenses"; subtitle: one line of context
    - columns: header strings; rows: row tuples matching len(columns)
    - totals_row: optional final row, rendered bold on the totals colour
    - generated_by: shown in the footer
    - cabinet: whose letterhead to use (None -> neutral header)
    - info_rows: optional [(label, value)] shown under the title
    - signatories: optional list of Signatory -> signature boxes at the end
    - amount_in_words: optional amount written out ("Nous disons...")
    - col_widths: optional column widths as fractions of the page width
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle, Spacer

    st = _styles()
    pagesize = landscape(A4) if len(columns) > 5 else A4
    width = pagesize[0] - 3 * cm
    box_rows = list(info_rows or [])
    if subtitle:
        box_rows.insert(0, ('Objet', subtitle))
    elements = letterhead(cabinet, width) + [title_box(title, box_rows, width), Spacer(1, 0.4 * cm)]

    def cell(v, style='cell'):
        return v if hasattr(v, 'wrap') else Paragraph(pdf_text(v), st[style])

    data = [[Paragraph(pdf_text(c), st['head']) for c in columns]]
    data += [[cell(v) for v in row] for row in rows]
    if totals_row is not None:
        data.append([cell(v, 'cell_bold') for v in totals_row])

    widths = [width * f for f in col_widths] if col_widths else None
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(HEADER_PEACH)),
        ('BOX', (0, 0), (-1, -1), 0.9, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 0.9, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor(GRID)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    body_end = len(data) - (2 if totals_row is not None else 1)
    if body_end >= 1:
        style.append(('ROWBACKGROUNDS', (0, 1), (-1, body_end), [colors.white, colors.HexColor(ZEBRA)]))
    if totals_row is not None:
        last = len(data) - 1
        style += [('BACKGROUND', (0, last), (-1, last), colors.HexColor(TOTAL_BLUE)),
                  ('LINEABOVE', (0, last), (-1, last), 0.9, colors.black)]
    table.setStyle(TableStyle(style))
    elements.append(table)
    if not rows:
        elements += [Spacer(1, 0.4 * cm), Paragraph('Aucune donnée pour cette période.', st['text'])]
    if signatories or amount_in_words is not None:
        elements += [Spacer(1, 0.8 * cm), signature_section(signatories or [], width,
                                                             place=place or getattr(cabinet, 'city', '') or None,
                                                             amount=amount_in_words)]
    return pdf_response(_build(elements, pagesize=pagesize, footer_left=_footer_text(cabinet, generated_by)), filename)


# ---------------------------------------------------------------------------
# Bordereaux (DQE, devis)
# ---------------------------------------------------------------------------

@dataclass
class BordereauLine:
    designation: str
    unit: str
    quantity: Optional[Decimal]
    unit_price: Optional[Decimal]
    total: Decimal


@dataclass
class BordereauGroup:
    """A sous-étape with its lines and subtotal."""
    title: str
    lines: List[BordereauLine] = field(default_factory=list)

    @property
    def total(self):
        return sum((l.total for l in self.lines), Decimal('0'))


@dataclass
class BordereauSection:
    """An étape (A, B, C...): its own lines and sous-étape groups, in the
    order they first appear."""
    title: str
    items: list = field(default_factory=list)  # BordereauLine | BordereauGroup

    @property
    def total(self):
        return sum((i.total for i in self.items), Decimal('0'))


def bordereau_sections(lines, *, phase_of, designation_of, unit_of, quantity_of, unit_price_of, total_of,
                       other_title='AUTRES TRAVAUX'):
    """Group DQE/devis lines by étape (top-level ProjectPhase) and
    sous-étape, keeping the order lines appear in. Lines with no étape go
    in a final "AUTRES TRAVAUX" section."""
    sections = {}
    order = []
    for line in lines:
        phase = phase_of(line)
        top = phase.parent_phase if (phase is not None and phase.parent_phase_id) else phase
        key = top.pk if top is not None else None
        if key not in sections:
            sections[key] = BordereauSection(title=(top.name if top is not None else other_title))
            order.append(key)
        section = sections[key]
        entry = BordereauLine(designation_of(line), unit_of(line), quantity_of(line), unit_price_of(line), total_of(line))
        if phase is not None and phase.parent_phase_id:
            group = next((g for g in section.items if isinstance(g, BordereauGroup) and g.title == phase.name), None)
            if group is None:
                group = BordereauGroup(title=phase.name)
                section.items.append(group)
            group.lines.append(entry)
        else:
            section.items.append(entry)
    if None in sections and len(order) > 1:  # "AUTRES TRAVAUX" last
        order.remove(None)
        order.append(None)
    return [sections[k] for k in order]


def _letter(i):
    letters = ''
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def render_bordereau_pdf(*, filename, cabinet, title, info_rows, sections, total_label='TOTAL GÉNÉRAL',
                         extra_totals=None, signatories=None, place=None, date=None, generated_by=None,
                         amount_in_words=True, note=None):
    """A priced bill of quantities in the reference layout:

    N° | Désignation | Uté | Qté | P.U. ($) | P.T. ($)
    A  | ÉTAPE (blue)
       | A1 line                                   ...
       | A2 sous-étape (green)
       |    line ...
       |                              Sous-total A2 ...
    TOTAL ÉTAPE (pale blue)                         ...
    ...
    TOTAL GÉNÉRAL (peach)                           ...

    then the amount in words, "Fait à ..., le ...", and signature boxes.
    `extra_totals` = [(label, amount)] rows printed after the grand total
    (e.g. a margin or fees). Returns an HttpResponse.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle, Spacer

    st = _styles()
    width = A4[0] - 3 * cm
    col_w = [1.0 * cm, None, 1.3 * cm, 1.8 * cm, 2.3 * cm, 2.7 * cm]
    col_w[1] = width - sum(w for w in col_w if w)

    def P(text, style='cell'):
        return Paragraph(text, st[style])

    data = [[P('N°', 'head'), P('Désignation', 'head'), P('Uté', 'head'), P('Qté', 'head'),
             P('P.U. ($)', 'head'), P('P.T. ($)', 'head')]]
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(HEADER_PEACH)),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor(GRID)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]

    def line_row(code, line, indent=False):
        designation = pdf_text(line.designation)
        if indent:
            designation = '&nbsp;&nbsp;&nbsp;&nbsp;' + designation
        return [P(pdf_text(code), 'cell_center'), P(designation), P(pdf_text(line.unit), 'cell_center'),
                P(fmt_quantity(line.quantity), 'cell_right'), P(fmt_amount(line.unit_price), 'cell_right'),
                P(fmt_amount(line.total), 'cell_right')]

    grand_total = Decimal('0')
    for s_index, section in enumerate(sections):
        letter = _letter(s_index)
        r = len(data)
        data.append([P(letter, 'section'), P(pdf_text(section.title.upper()), 'section'), '', '', '', ''])
        style += [('SPAN', (1, r), (5, r)), ('BACKGROUND', (1, r), (5, r), colors.HexColor(SECTION_BLUE)),
                  ('LINEABOVE', (0, r), (-1, r), 0.9, colors.black)]
        for i_index, item in enumerate(section.items, start=1):
            code = f'{letter}{i_index}'
            if isinstance(item, BordereauGroup):
                r = len(data)
                data.append(['', P(f'<b>{pdf_text(code)}</b>&nbsp;&nbsp;{pdf_text(item.title)}'), '', '', '', ''])
                style += [('SPAN', (1, r), (5, r)), ('BACKGROUND', (1, r), (5, r), colors.HexColor(GROUP_GREEN))]
                for line in item.lines:
                    data.append(line_row('', line, indent=True))
                r = len(data)
                data.append(['', P(f'Sous-total {pdf_text(code)}', 'subtotal_label'), '', '', '', P(fmt_amount(item.total), 'amount_bold')])
                style += [('SPAN', (1, r), (4, r))]
            else:
                data.append(line_row(code, item))
        r = len(data)
        data.append([P(f'TOTAL {pdf_text(section.title.upper())}', 'total_label'), '', '', '', '', P(fmt_amount(section.total), 'amount_bold')])
        style += [('SPAN', (0, r), (4, r)), ('BACKGROUND', (0, r), (-1, r), colors.HexColor(TOTAL_BLUE)),
                  ('LINEABOVE', (0, r), (-1, r), 0.9, colors.black), ('LINEBELOW', (0, r), (-1, r), 0.9, colors.black)]
        grand_total += section.total

    final = grand_total
    r = len(data)
    data.append([P(pdf_text(total_label), 'total_label'), '', '', '', '', P(fmt_amount(grand_total), 'amount_bold')])
    style += [('SPAN', (0, r), (4, r)), ('BACKGROUND', (0, r), (-1, r), colors.HexColor(HEADER_PEACH)),
              ('LINEABOVE', (0, r), (-1, r), 1.2, colors.black)]
    for label, amount in (extra_totals or []):
        r = len(data)
        data.append([P(pdf_text(label), 'total_label'), '', '', '', '', P(fmt_amount(amount), 'amount_bold')])
        style += [('SPAN', (0, r), (4, r)), ('BACKGROUND', (0, r), (-1, r), colors.HexColor(HEADER_PEACH))]
        final = amount

    table = Table(data, colWidths=col_w, repeatRows=1)
    table.setStyle(TableStyle(style))

    elements = letterhead(cabinet, width) + [title_box(title, info_rows, width), Spacer(1, 0.4 * cm), table]
    if note:
        elements += [Spacer(1, 0.25 * cm), Paragraph(pdf_text(note), st['sig_sub'])]
    elements += [Spacer(1, 0.6 * cm),
                 signature_section(signatories or [], width, place=place or getattr(cabinet, 'city', '') or None,
                                   date=date, amount=final if amount_in_words else None)]
    return pdf_response(_build(elements, pagesize=A4, footer_left=_footer_text(cabinet, generated_by)), filename)


def status_stamp(obj, new_status, verb):
    """"<verb> le 20/10/2026 par Jean K." from the object's latest
    StatusChangeLog entry to `new_status`, or '' if there is none."""
    from django.contrib.contenttypes.models import ContentType
    from core.models import StatusChangeLog
    entry = (StatusChangeLog.objects
             .filter(content_type=ContentType.objects.get_for_model(type(obj)), object_id=obj.pk, new_status=new_status)
             .select_related('changed_by').order_by('-changed_at').first())
    if entry is None:
        return ''
    who = ''
    if entry.changed_by is not None:
        who = ' par ' + (entry.changed_by.get_full_name() or entry.changed_by.get_username())
    return f"{verb} dans ChantierMobile le {timezone.localtime(entry.changed_at).strftime('%d/%m/%Y')}{who}"


def pour_label(cabinet):
    """"Pour l'A.T.G.C." / "Pour ACME" — who signs on the cabinet's behalf."""
    short = (getattr(cabinet, 'short_name', '') or getattr(cabinet, 'name', '') or '') if cabinet else ''
    if not short:
        return "Pour l'entreprise"
    return f"Pour l'{short}" if short[:1].upper() in 'AEIOUYHÉÈ' else f'Pour {short}'


def person_name(user):
    if user is None:
        return ''
    return user.get_full_name() or user.get_username()
