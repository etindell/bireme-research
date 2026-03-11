import csv
import io
import json
import zipfile
from datetime import datetime

from apps.compliance.models import ComplianceTask


def _task_rows(tasks):
    """Yield CSV rows for tasks."""
    for task in tasks:
        evidence_files = ', '.join(
            e.original_filename for e in task.evidence_items.all()
        )
        yield [
            task.id,
            task.title,
            task.description or '',
            task.due_date.isoformat(),
            task.status,
            task.completed_at.isoformat() if task.completed_at else '',
            task.completed_by.email if task.completed_by else '',
            task.notes or '',
            task.tags or '',
            task.evidence_items.count(),
            evidence_files,
        ]


CSV_HEADER = [
    'ID', 'Title', 'Description', 'Due Date', 'Status',
    'Completed At', 'Completed By', 'Notes', 'Tags',
    'Evidence Count', 'Evidence Files',
]


def export_csv(organization, year):
    """Return CSV string of all tasks for the year."""
    tasks = ComplianceTask.objects.filter(
        organization=organization, year=year
    ).select_related('completed_by').prefetch_related('evidence_items').order_by('due_date')

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADER)
    for row in _task_rows(tasks):
        writer.writerow(row)
    return output.getvalue()


def export_zip(organization, year):
    """Return bytes of a ZIP containing CSV + evidence files + manifest."""
    tasks = ComplianceTask.objects.filter(
        organization=organization, year=year
    ).select_related('completed_by').prefetch_related('evidence_items').order_by('due_date')

    zip_buffer = io.BytesIO()
    manifest = {'year': year, 'exported_at': datetime.now().isoformat(), 'tasks': []}

    csv_output = io.StringIO()
    writer = csv.writer(csv_output)
    writer.writerow(CSV_HEADER)

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for task in tasks:
            evidence_files = []
            folder = f"{year}/{task.due_date.month:02d}/{task.title[:50].replace('/', '-').replace(':', '-')}"

            for evidence in task.evidence_items.all():
                if evidence.file and evidence.file.name:
                    try:
                        zip_path = f"{folder}/{evidence.original_filename}"
                        zf.writestr(zip_path, evidence.file.read())
                        evidence_files.append(evidence.original_filename)
                    except Exception:
                        pass

            writer.writerow([
                task.id, task.title, task.description or '',
                task.due_date.isoformat(), task.status,
                task.completed_at.isoformat() if task.completed_at else '',
                task.completed_by.email if task.completed_by else '',
                task.notes or '', task.tags or '',
                task.evidence_items.count(),
                ', '.join(evidence_files),
            ])

            manifest['tasks'].append({
                'id': task.id,
                'title': task.title,
                'due_date': task.due_date.isoformat(),
                'status': task.status,
                'evidence_folder': folder if evidence_files else None,
                'evidence_files': evidence_files,
            })

        zf.writestr(f'bireme_compliance_{year}.csv', csv_output.getvalue())
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))

    return zip_buffer.getvalue()


def generate_audit_pdf(organization, year, user):
    """Generate PDF audit report using reportlab. Returns bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    from apps.compliance.models import ComplianceSettings

    settings = ComplianceSettings.objects.filter(organization=organization).first()
    firm_name = settings.firm_name if settings else 'Bireme Capital'

    all_tasks = ComplianceTask.objects.filter(organization=organization, year=year)
    completed_tasks = all_tasks.filter(
        status=ComplianceTask.Status.COMPLETED
    ).select_related('completed_by').prefetch_related(
        'evidence_items', 'audit_logs', 'audit_logs__user',
        'evidence_items__uploaded_by'
    ).order_by('due_date')

    total = all_tasks.count()
    completed_count = completed_tasks.count()
    tasks_with_evidence = sum(1 for t in completed_tasks if t.evidence_items.exists())

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=0.75 * inch, leftMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=24, spaceAfter=6, alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('S', parent=styles['Normal'], fontSize=14, spaceAfter=20, alignment=TA_CENTER, textColor=colors.grey)
    heading_style = ParagraphStyle('H', parent=styles['Heading2'], fontSize=14, spaceBefore=20, spaceAfter=10, textColor=colors.HexColor('#1e293b'))
    task_title_style = ParagraphStyle('TT', parent=styles['Heading3'], fontSize=11, spaceBefore=15, spaceAfter=4, textColor=colors.HexColor('#2563eb'))
    normal_style = styles['Normal']
    small_style = ParagraphStyle('Sm', parent=styles['Normal'], fontSize=9, textColor=colors.grey)

    content = []
    content.append(Paragraph('COMPLIANCE AUDIT REPORT', title_style))
    content.append(Paragraph(f'{firm_name} - Calendar Year {year}', subtitle_style))
    content.append(Paragraph(
        f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')} by {user.email}",
        small_style
    ))
    content.append(Spacer(1, 0.3 * inch))

    # Executive summary
    content.append(Paragraph('EXECUTIVE SUMMARY', heading_style))
    rate = round(completed_count / total * 100, 1) if total else 0
    summary = [
        ['Total Tasks:', str(total)],
        ['Completed:', str(completed_count)],
        ['Completion Rate:', f'{rate}%'],
        ['With Evidence:', str(tasks_with_evidence)],
        ['Without Evidence:', str(completed_count - tasks_with_evidence)],
    ]
    t = Table(summary, colWidths=[2.5 * inch, 1.5 * inch])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    content.append(t)
    content.append(Spacer(1, 0.3 * inch))

    # Completed tasks detail
    content.append(Paragraph('COMPLETED COMPLIANCE ACTIONS', heading_style))
    if not completed_tasks.exists():
        content.append(Paragraph('No completed tasks for this year.', normal_style))
    else:
        for idx, task in enumerate(completed_tasks, 1):
            content.append(Paragraph(f'{idx}. {task.title}', task_title_style))
            cd = task.completed_at.strftime('%b %d, %Y') if task.completed_at else 'N/A'
            cb = task.completed_by.email if task.completed_by else 'Unknown'
            dt = [
                ['Due Date:', task.due_date.strftime('%b %d, %Y'), 'Completed:', cd],
                ['Completed By:', cb, '', ''],
            ]
            dt_table = Table(dt, colWidths=[1 * inch, 1.5 * inch, 1 * inch, 1.5 * inch])
            dt_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
                ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            content.append(dt_table)
            if task.description:
                content.append(Spacer(1, 0.1 * inch))
                content.append(Paragraph(f'<b>Description:</b> {task.description}', normal_style))
            if task.notes:
                content.append(Spacer(1, 0.05 * inch))
                content.append(Paragraph(f'<b>Notes:</b> {task.notes}', normal_style))
            evidence = task.evidence_items.all()
            if evidence:
                content.append(Spacer(1, 0.1 * inch))
                content.append(Paragraph('<b>Evidence:</b>', normal_style))
                for ev in evidence:
                    up_date = ev.created_at.strftime('%b %d, %Y') if ev.created_at else ''
                    up_by = ev.uploaded_by.email if ev.uploaded_by else 'Unknown'
                    desc = f' - "{ev.description}"' if ev.description else ''
                    if ev.external_link:
                        content.append(Paragraph(f'  - External Link: {ev.external_link}{desc}', small_style))
                    else:
                        size_kb = round(ev.size_bytes / 1024, 1) if ev.size_bytes else 0
                        content.append(Paragraph(
                            f'  - {ev.original_filename} ({size_kb} KB){desc} - uploaded {up_date} by {up_by}',
                            small_style
                        ))
            logs = task.audit_logs.order_by('created_at')
            if logs.exists():
                content.append(Spacer(1, 0.1 * inch))
                content.append(Paragraph('<b>Audit Trail:</b>', normal_style))
                for log in logs:
                    ld = log.created_at.strftime('%b %d, %Y %I:%M %p') if log.created_at else ''
                    un = log.user.email if log.user else 'System'
                    ad = log.description or log.action_type.replace('_', ' ').title()
                    content.append(Paragraph(f'  - {ld}: {ad} (by {un})', small_style))
            content.append(Spacer(1, 0.15 * inch))

    doc.build(content)
    buf.seek(0)
    return buf.getvalue()
