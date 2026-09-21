"""Small shared helper for generating simple tabular PDF reports
(financial reports, stock reports, purchase reports, ...) with reportlab.

Kept deliberately generic — a title, an optional subtitle/filter summary,
a header row, and a list of row tuples — so every "Exporter en PDF" button
across the app (dépenses, achats/caisse, stock, ...) can share one
implementation instead of each view rolling its own PDF layout.
"""
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone


def render_table_report_pdf(*, filename, title, subtitle, columns, rows, totals_row=None, generated_by=None):
    """Render a simple landscape/portrait tabular PDF report and return it
    as a Django HttpResponse ready to be returned from a view.

    - filename: e.g. "depenses-2024-01.pdf" (used for Content-Disposition)
    - title: report title, e.g. "Rapport des dépenses"
    - subtitle: one line of context, e.g. "Chantier X — du 01/01 au 31/01/2024"
    - columns: list of column header strings
    - rows: list of row tuples/lists, each matching len(columns)
    - totals_row: optional final row (e.g. ["", "", "Total", "1 234.00 $"]),
      rendered in bold with a top border
    - generated_by: optional string, e.g. request.user's display name
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    buffer = BytesIO()
    page_size = landscape(A4) if len(columns) > 5 else A4
    doc = SimpleDocTemplate(
        buffer, pagesize=page_size,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    elements = [Paragraph(title, styles['Title'])]
    if subtitle:
        elements.append(Paragraph(subtitle, styles['Normal']))
    generated_line = f"Généré le {timezone.localtime().strftime('%d/%m/%Y %H:%M')}"
    if generated_by:
        generated_line += f" par {generated_by}"
    elements.append(Paragraph(generated_line, styles['Normal']))
    elements.append(Spacer(1, 0.5 * cm))

    table_data = [list(columns)] + [list(row) for row in rows]
    if totals_row is not None:
        table_data.append(list(totals_row))

    table = Table(table_data, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0b2e59')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d8d8d8')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if totals_row is not None:
        last_row = len(table_data) - 1
        style += [
            ('FONTNAME', (0, last_row), (-1, last_row), 'Helvetica-Bold'),
            ('LINEABOVE', (0, last_row), (-1, last_row), 1, colors.HexColor('#0b2e59')),
        ]
    table.setStyle(TableStyle(style))
    elements.append(table)

    if not rows:
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(Paragraph("Aucune donnée pour cette période.", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
