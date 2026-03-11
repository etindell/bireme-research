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
    """Generate professional PDF audit report for all compliance tasks in a year."""
    import io
    from datetime import datetime
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
        PageBreak, Image, KeepTogether
    )
    from reportlab.pdfgen import canvas

    from apps.compliance.models import ComplianceSettings, ComplianceTask

    # --- Helper for Page Numbering ---
    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            canvas.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            """add page info to each page (page x of y)"""
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.draw_page_number(num_pages)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

        def draw_page_number(self, page_count):
            self.setFont("Helvetica", 9)
            self.drawRightString(7.75 * inch, 0.5 * inch,
                f"Page {self._pageNumber} of {page_count}")
            self.drawString(0.75 * inch, 0.5 * inch, 
                f"Generated by {user.email} on {datetime.now().strftime('%Y-%m-%d')}")

    # --- Data Gathering ---
    settings = ComplianceSettings.objects.filter(organization=organization).first()
    firm_name = settings.firm_name if settings else organization.name

    all_tasks = ComplianceTask.objects.filter(
        organization=organization, year=year
    ).select_related('completed_by', 'template').prefetch_related(
        'evidence_items', 'audit_logs', 'audit_logs__user',
        'evidence_items__uploaded_by'
    ).order_by('due_date')

    completed_tasks = all_tasks.filter(status=ComplianceTask.Status.COMPLETED)
    other_tasks = all_tasks.exclude(status=ComplianceTask.Status.COMPLETED)

    # --- Styles ---
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', fontSize=28, spaceAfter=12, alignment=TA_CENTER, textColor=colors.HexColor('#1e293b'), fontName='Helvetica-Bold')
    subtitle_style = ParagraphStyle('Subtitle', fontSize=16, spaceAfter=30, alignment=TA_CENTER, textColor=colors.grey, fontName='Helvetica')
    heading_style = ParagraphStyle('Heading', fontSize=16, spaceBefore=20, spaceAfter=12, textColor=colors.HexColor('#1e293b'), fontName='Helvetica-Bold', borderPadding=5)
    subheading_style = ParagraphStyle('Subheading', fontSize=13, spaceBefore=15, spaceAfter=8, textColor=colors.HexColor('#334155'), fontName='Helvetica-Bold')
    task_title_style = ParagraphStyle('TaskTitle', fontSize=12, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor('#2563eb'), fontName='Helvetica-Bold')
    normal_style = styles['Normal']
    small_style = ParagraphStyle('Small', fontSize=8, textColor=colors.grey, fontName='Helvetica')
    label_style = ParagraphStyle('Label', fontSize=9, textColor=colors.grey, fontName='Helvetica-Bold')
    
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=0.75 * inch, leftMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    )

    content = []

    # --- 1. COVER PAGE ---
    content.append(Spacer(1, 2 * inch))
    content.append(Paragraph("ANNUAL COMPLIANCE", title_style))
    content.append(Paragraph("AUDIT REPORT", title_style))
    content.append(Spacer(1, 0.5 * inch))
    content.append(Paragraph(f"Calendar Year {year}", subtitle_style))
    content.append(Spacer(1, 1 * inch))
    content.append(Paragraph(f"<b>Firm:</b> {firm_name}", subtitle_style))
    content.append(Paragraph(f"<b>Organization:</b> {organization.name}", subtitle_style))
    content.append(Spacer(1, 2 * inch))
    content.append(Paragraph(f"Report Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", normal_style))
    content.append(Paragraph(f"Generated By: {user.email}", normal_style))
    content.append(PageBreak())

    # --- 2. EXECUTIVE SUMMARY ---
    content.append(Paragraph("EXECUTIVE SUMMARY", heading_style))
    content.append(Spacer(1, 0.2 * inch))
    
    total = all_tasks.count()
    comp_count = completed_tasks.count()
    rate = round(comp_count / total * 100, 1) if total else 0
    tasks_with_ev = sum(1 for t in completed_tasks if t.evidence_items.exists())

    summary_data = [
        [Paragraph("<b>Reporting Period:</b>", normal_style), f"Jan 1, {year} - Dec 31, {year}"],
        [Paragraph("<b>Total Compliance Actions:</b>", normal_style), str(total)],
        [Paragraph("<b>Total Completed:</b>", normal_style), str(comp_count)],
        [Paragraph("<b>Completion Rate:</b>", normal_style), f"{rate}%"],
        [Paragraph("<b>Completed with Evidence:</b>", normal_style), str(tasks_with_ev)],
        [Paragraph("<b>Non-Applicable / Deferred:</b>", normal_style), str(all_tasks.filter(status__in=['NOT_APPLICABLE', 'DEFERRED']).count())],
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5 * inch, 3.5 * inch])
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.whitesmoke),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    content.append(summary_table)
    content.append(Spacer(1, 0.4 * inch))

    # --- 3. COMPLETED TASKS ---
    content.append(Paragraph("COMPLETED COMPLIANCE ACTIONS", heading_style))
    content.append(Spacer(1, 0.1 * inch))

    if not completed_tasks.exists():
        content.append(Paragraph("No completed tasks recorded for this period.", normal_style))
    else:
        for idx, task in enumerate(completed_tasks, 1):
            task_elements = []
            
            # Title
            task_elements.append(Paragraph(f"{idx}. {task.title}", task_title_style))
            
            # Metadata Table
            completed_date = task.completed_at.strftime('%b %d, %Y') if task.completed_at else 'N/A'
            comp_by = task.completed_by.email if task.completed_by else 'Unknown'
            
            meta_data = [
                [Paragraph("<b>Due Date:</b>", small_style), task.due_date.strftime('%b %d, %Y'), 
                 Paragraph("<b>Completed On:</b>", small_style), completed_date],
                [Paragraph("<b>Completed By:</b>", small_style), comp_by, 
                 Paragraph("<b>Category:</b>", small_style), task.tags or "Compliance"],
            ]
            meta_table = Table(meta_data, colWidths=[1 * inch, 2 * inch, 1 * inch, 2 * inch])
            meta_table.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            task_elements.append(meta_table)

            # Description & Notes
            if task.description:
                task_elements.append(Spacer(1, 0.05 * inch))
                task_elements.append(Paragraph(f"<b>Description:</b> {task.description}", normal_style))
            if task.notes:
                task_elements.append(Spacer(1, 0.05 * inch))
                task_elements.append(Paragraph(f"<b>Outcome/Notes:</b> {task.notes}", normal_style))

            # Evidence
            evidence = task.evidence_items.all()
            if evidence:
                task_elements.append(Spacer(1, 0.1 * inch))
                task_elements.append(Paragraph("<b>Supporting Evidence:</b>", normal_style))
                for ev in evidence:
                    up_date = ev.created_at.strftime('%b %d, %Y') if ev.created_at else ''
                    desc = f" - {ev.description}" if ev.description else ""
                    
                    if ev.external_link:
                        task_elements.append(Paragraph(f"&bull; External Link: <a href='{ev.external_link}' color='blue'>{ev.external_link}</a>{desc}", small_style))
                    elif ev.text_content:
                        task_elements.append(Paragraph(f"&bull; Text Evidence: {ev.text_content}{desc}", small_style))
                    else:
                        size_kb = round(ev.size_bytes / 1024, 1) if ev.size_bytes else 0
                        task_elements.append(Paragraph(
                            f"&bull; {ev.original_filename} ({size_kb} KB) - uploaded {up_date}{desc}",
                            small_style
                        ))
                        
                        # IMAGE EMBEDDING
                        if ev.mime_type.startswith('image/') and ev.file:
                            try:
                                # Rewind file handle just in case
                                ev.file.open('rb')
                                img_data = io.BytesIO(ev.file.read())
                                img = Image(img_data)
                                
                                # Scale image to fit page width
                                max_w = 6 * inch
                                max_h = 3 * inch
                                w, h = img.drawWidth, img.drawHeight
                                aspect = h / float(w)
                                
                                if w > max_w:
                                    img.drawWidth = max_w
                                    img.drawHeight = max_w * aspect
                                if img.drawHeight > max_h:
                                    img.drawHeight = max_h
                                    img.drawWidth = max_h / aspect
                                
                                img.hAlign = 'LEFT'
                                task_elements.append(Spacer(1, 0.05 * inch))
                                task_elements.append(img)
                                task_elements.append(Spacer(1, 0.1 * inch))
                            except Exception as e:
                                task_elements.append(Paragraph(f"<i>(Image could not be embedded: {str(e)})</i>", small_style))

            # Audit Logs (Summary)
            logs = task.audit_logs.filter(
                action_type__in=['STATUS_CHANGE', 'EVIDENCE_ADD', 'TASK_CREATED']
            ).order_by('created_at')
            if logs.exists():
                task_elements.append(Spacer(1, 0.05 * inch))
                log_lines = []
                for log in logs:
                    ld = log.created_at.strftime('%m/%d/%y')
                    ad = log.description or log.get_action_type_display()
                    log_lines.append(f"{ld}: {ad}")
                task_elements.append(Paragraph(f"<b>Audit History:</b> {'; '.join(log_lines)}", small_style))

            task_elements.append(Spacer(1, 0.2 * inch))
            
            # Keep task details together on one page if possible
            content.append(KeepTogether(task_elements))

    # --- 4. OTHER TASKS (N/A, DEFERRED, etc.) ---
    if other_tasks.exists():
        content.append(PageBreak())
        content.append(Paragraph("OTHER COMPLIANCE ACTIONS", heading_style))
        content.append(Paragraph("Tasks marked as Not Applicable, Deferred, or Incomplete.", small_style))
        content.append(Spacer(1, 0.2 * inch))

        other_data = [['Title', 'Due Date', 'Status', 'Notes']]
        for task in other_tasks:
            other_data.append([
                Paragraph(task.title, normal_style),
                task.due_date.strftime('%Y-%m-%d'),
                task.get_status_display(),
                Paragraph(task.notes or "-", small_style)
            ])
        
        other_table = Table(other_data, colWidths=[2.5 * inch, 1 * inch, 1.5 * inch, 2 * inch])
        other_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.whitesmoke),
        ]))
        content.append(other_table)

    # --- Build PDF ---
    doc.build(content, canvasmaker=NumberedCanvas)
    
    pdf_value = buf.getvalue()
    buf.close()
    return pdf_value
