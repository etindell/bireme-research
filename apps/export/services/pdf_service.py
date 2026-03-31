import io
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    PageBreak, Image, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas
from django.conf import settings
from django.utils.html import strip_tags
import markdown
import bleach
import re

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
        self.setFont("Helvetica", 8)
        self.drawRightString(7.75 * inch, 0.5 * inch,
            f"Page {self._pageNumber} of {page_count}")
        self.drawString(0.75 * inch, 0.5 * inch, 
            f"Bireme Capital | Confidential Research | {datetime.now().strftime('%Y-%m-%d')}")

def generate_note_pdf(note, user):
    """Generate a professional PDF for a single research note."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=0.75 * inch, leftMargin=0.75 * inch,
        topMargin=0.5 * inch, bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    
    # Custom Styles
    styles.add(ParagraphStyle(
        name='FirmTitle',
        fontSize=14,
        leading=16,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1e293b')
    ))
    styles.add(ParagraphStyle(
        name='FirmSubTitle',
        fontSize=9,
        leading=11,
        fontName='Helvetica',
        textColor=colors.grey
    ))
    styles.add(ParagraphStyle(
        name='NoteTitle',
        fontSize=22,
        leading=26,
        fontName='Helvetica-Bold',
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.black
    ))
    styles.add(ParagraphStyle(
        name='CompanyHeader',
        fontSize=12,
        leading=14,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#2563eb'),
        spaceBefore=0
    ))
    styles.add(ParagraphStyle(
        name='MetaText',
        fontSize=9,
        leading=12,
        fontName='Helvetica',
        textColor=colors.grey
    ))
    styles.add(ParagraphStyle(
        name='NoteContent',
        fontSize=10,
        leading=14,
        fontName='Helvetica',
        spaceBefore=6,
        spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name='BulletContent',
        fontSize=10,
        leading=14,
        fontName='Helvetica',
        leftIndent=20,
        firstLineIndent=-12,
        spaceBefore=3,
        spaceAfter=3
    ))
    styles.add(ParagraphStyle(
        name='SectionHeader',
        fontSize=12,
        leading=14,
        fontName='Helvetica-Bold',
        spaceBefore=15,
        spaceAfter=10,
        textColor=colors.HexColor('#1e293b'),
        borderPadding=5
    ))

    content = []

    # --- 1. HEADER WITH LOGO ---
    logo_path = os.path.join(settings.BASE_DIR, 'apps', 'export', 'Logos', 'Bireme-Logo-Color.png')
    
    header_data = []
    if os.path.exists(logo_path):
        img = Image(logo_path, width=1.8*inch, height=0.45*inch)
        img.hAlign = 'LEFT'
        
        # Table for Logo and Firm Info
        firm_info = [
            [img, Paragraph("<b>BIREME CAPITAL</b>", styles['FirmTitle'])],
            ['', Paragraph("Investment Research | Internal Use Only", styles['FirmSubTitle'])]
        ]
        header_table = Table(firm_info, colWidths=[2*inch, 4.5*inch])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('SPAN', (0,0), (0,1)), # Span logo across two rows
        ]))
        content.append(header_table)
    else:
        content.append(Paragraph("<b>BIREME CAPITAL</b>", styles['FirmTitle']))
        content.append(Paragraph("Investment Research | Internal Use Only", styles['FirmSubTitle']))

    content.append(Spacer(1, 0.1*inch))
    content.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=5, spaceAfter=5))
    content.append(Spacer(1, 0.2*inch))

    # --- 2. NOTE TITLE & META ---
    if note.company:
        content.append(Paragraph(note.company.name.upper(), styles['CompanyHeader']))
    
    content.append(Paragraph(note.title, styles['NoteTitle']))
    
    meta_parts = []
    meta_parts.append(f"<b>Date:</b> {note.display_date.strftime('%B %d, %Y')}")
    if note.created_by:
        meta_parts.append(f"<b>Analyst:</b> {note.created_by.get_full_name()}")
    if note.note_type:
        meta_parts.append(f"<b>Type:</b> {note.note_type.name}")
    
    content.append(Paragraph("  |  ".join(meta_parts), styles['MetaText']))
    content.append(Spacer(1, 0.3*inch))

    # --- 3. NOTE CONTENT (Markdown) ---
    if note.content:
        # Pre-process: convert • bullet lines to standard markdown so the parser recognizes them
        preprocessed = re.sub(r'^[•]\s*', '- ', note.content, flags=re.MULTILINE)
        # Strip {: ... } markdown attribute blocks
        preprocessed = re.sub(r'\{:?[^}]+\}', '', preprocessed)

        # 1. Convert Markdown to HTML
        html_content = markdown.markdown(preprocessed)
        
        # 2. Define allowed tags for ReportLab Paragraphs
        # We keep 'li' temporarily to identify list items
        allowed_tags = ['b', 'i', 'u', 'font', 'br', 'strong', 'em', 'strike', 'img', 'li']
        
        # 3. Pre-process to make splitting easier
        # Wrap the content of LI so we can identify it after splitting
        html_content = html_content.replace('<li>', '<li_item>').replace('</li>', '</li_item>')
        
        # Split by blocks
        parts = re.split(r'(<(?:p|li_item|blockquote|h[1-6])>)', html_content)
        
        current_tag = None
        for part in parts:
            if not part.strip(): continue
            
            # Check if this part is an opening tag
            tag_match = re.match(r'<(p|li_item|blockquote|h[1-6])>', part)
            if tag_match:
                current_tag = tag_match.group(1)
                continue
            
            block = part
            # Handle Images
            img_tags = re.findall(r'<img[^>]+>', block)
            if img_tags:
                for img_tag in img_tags:
                    src_match = re.search(r'src="([^">]+)"', img_tag)
                    if not src_match: continue
                    img_src = src_match.group(1)
                    style_match = re.search(r'style="width:\s*(\d+)px"', img_tag)
                    width_px = int(style_match.group(1)) if style_match else None
                    
                    local_path = ""
                    if img_src.startswith(settings.MEDIA_URL):
                        rel_path = img_src.replace(settings.MEDIA_URL, '', 1)
                        local_path = os.path.join(settings.MEDIA_ROOT, rel_path)
                    
                    if local_path and os.path.exists(local_path):
                        try:
                            rl_img = Image(local_path)
                            max_w, max_h = 6 * inch, 6 * inch
                            w, h = rl_img.drawWidth, rl_img.drawHeight
                            aspect = h / float(w)
                            
                            if width_px:
                                target_w = width_px * 0.75
                                rl_img.drawWidth = min(target_w, max_w)
                                rl_img.drawHeight = rl_img.drawWidth * aspect
                            else:
                                if w > max_w:
                                    rl_img.drawWidth = max_w
                                    rl_img.drawHeight = max_w * aspect
                            
                            rl_img.hAlign = 'LEFT'
                            content.append(Spacer(1, 0.1 * inch))
                            content.append(rl_img)
                            content.append(Spacer(1, 0.1 * inch))
                        except: pass
                
                block = re.sub(r'<img[^>]+>', '', block)

            # Clean and format text
            block = re.sub(r'\{:?[^}]+\}', '', block) # Strip markdown attributes
            clean_text = bleach.clean(block, tags=['b', 'i', 'u', 'font', 'br', 'strong', 'em', 'strike'], strip=True)
            clean_text = clean_text.replace('<strong>', '<b>').replace('</strong>', '</b>')
            clean_text = clean_text.replace('<em>', '<i>').replace('</em>', '</i>')
            
            # Remove any lingering closing tags from the split
            clean_text = re.sub(r'</(?:p|li_item|blockquote|ul|ol|h[1-6]|img)>', '', clean_text).strip()
            
            if not clean_text: continue
            
            try:
                if current_tag == 'li_item':
                    # Explicitly use the bullet character and BulletContent style
                    content.append(Paragraph(f"&bull; {clean_text}", styles['BulletContent']))
                else:
                    content.append(Paragraph(clean_text, styles['NoteContent']))
            except:
                plain_text = strip_tags(clean_text)
                if current_tag == 'li_item':
                    content.append(Paragraph(f"&bull; {plain_text}", styles['BulletContent']))
                else:
                    content.append(Paragraph(plain_text, styles['NoteContent']))

    # --- 4. CASH FLOWS ---
    try:
        cash_flow = note.cash_flow
        content.append(Spacer(1, 0.3*inch))
        content.append(Paragraph("IRR CASH FLOW ASSUMPTIONS", styles['SectionHeader']))
        
        irr_text = f"Calculated IRR: {cash_flow.calculated_irr}%" if cash_flow.calculated_irr else ""
        content.append(Paragraph(f"<b>Basis Price:</b> ${cash_flow.current_price} {f' ({irr_text})' if irr_text else ''}", styles['NoteContent']))
        
        cf_data = [
            ['Year 1', 'Year 2', 'Year 3', 'Year 4', 'Year 5', 'Terminal'],
            [f"${cash_flow.fcf_year_1}", f"${cash_flow.fcf_year_2}", f"${cash_flow.fcf_year_3}", 
             f"${cash_flow.fcf_year_4}", f"${cash_flow.fcf_year_5}", f"${cash_flow.terminal_value}"]
        ]
        
        cf_table = Table(cf_data, colWidths=[1*inch]*6)
        cf_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        content.append(cf_table)
        
        # Optional Revenue/Profitability metrics
        if cash_flow.revenue_year_1 or cash_flow.ebit_ebitda_year_1:
            content.append(Spacer(1, 0.1*inch))
            # ... could add more tables here if needed
            
    except:
        pass

    # --- 5. REFERENCED COMPANIES ---
    if note.referenced_companies.exists():
        content.append(Spacer(1, 0.3*inch))
        refs = ", ".join([c.name for c in note.referenced_companies.all()])
        content.append(Paragraph(f"<b>Related Companies:</b> {refs}", styles['MetaText']))

    # Build PDF
    doc.build(content, canvasmaker=NumberedCanvas)
    pdf_value = buf.getvalue()
    buf.close()
    return pdf_value

def generate_company_pdf(company, notes, user):
    """Generate a professional PDF containing all notes for a specific company."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        rightMargin=0.75 * inch, leftMargin=0.75 * inch,
        topMargin=0.5 * inch, bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    
    # Re-use styles (generalized)
    firm_title_style = ParagraphStyle(name='FirmTitle', fontSize=14, leading=16, fontName='Helvetica-Bold', textColor=colors.HexColor('#1e293b'))
    firm_subtitle_style = ParagraphStyle(name='FirmSubTitle', fontSize=9, leading=11, fontName='Helvetica', textColor=colors.grey)
    company_title_style = ParagraphStyle(name='CompanyTitle', fontSize=24, leading=28, fontName='Helvetica-Bold', spaceBefore=30, spaceAfter=5, textColor=colors.black, alignment=TA_CENTER)
    report_type_style = ParagraphStyle(name='ReportType', fontSize=12, leading=14, fontName='Helvetica', spaceAfter=30, textColor=colors.grey, alignment=TA_CENTER)
    
    note_title_style = ParagraphStyle(name='NoteTitle', fontSize=16, leading=20, fontName='Helvetica-Bold', spaceBefore=15, spaceAfter=5, textColor=colors.HexColor('#2563eb'))
    meta_text_style = ParagraphStyle(name='MetaText', fontSize=9, leading=12, fontName='Helvetica', textColor=colors.grey, spaceAfter=10)
    content_style = ParagraphStyle(name='NoteContent', fontSize=10, leading=14, fontName='Helvetica', spaceBefore=4, spaceAfter=4)
    bullet_style = ParagraphStyle(name='BulletContent', fontSize=10, leading=14, fontName='Helvetica', leftIndent=20, firstLineIndent=-12, spaceBefore=3, spaceAfter=3)

    content = []

    # --- 1. HEADER ---
    logo_path = os.path.join(settings.BASE_DIR, 'apps', 'export', 'Logos', 'Bireme-Logo-Color.png')
    if os.path.exists(logo_path):
        img = Image(logo_path, width=1.8*inch, height=0.45*inch)
        img.hAlign = 'LEFT'
        firm_info = [[img, Paragraph("<b>BIREME CAPITAL</b>", firm_title_style)], ['', Paragraph("Investment Research | Company Report", firm_subtitle_style)]]
        header_table = Table(firm_info, colWidths=[2*inch, 4.5*inch])
        header_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('SPAN', (0,0), (0,1))]))
        content.append(header_table)
    else:
        content.append(Paragraph("<b>BIREME CAPITAL</b>", firm_title_style))

    content.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=5, spaceAfter=5))

    # --- 2. COVER INFO ---
    content.append(Spacer(1, 1*inch))
    content.append(Paragraph(company.name.upper(), company_title_style))
    content.append(Paragraph(f"Research Compilation Report", report_type_style))
    content.append(Spacer(1, 0.5*inch))
    
    stats_data = [
        ["Total Notes:", str(len(notes))],
        ["Report Date:", datetime.now().strftime('%B %d, %Y')],
        ["Primary Ticker:", company.ticker or "N/A"],
        ["Sector:", company.sector or "N/A"]
    ]
    stats_table = Table(stats_data, colWidths=[1.5*inch, 2.5*inch])
    stats_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('ALIGN', (0,0), (0,-1), 'RIGHT'),
        ('TEXTCOLOR', (0,0), (0,-1), colors.grey),
    ]))
    content.append(stats_table)
    content.append(PageBreak())

    # --- 3. NOTES ---
    if not notes:
        content.append(Paragraph("No research notes found for this company.", content_style))
    else:
        for idx, note in enumerate(notes, 1):
            note_elements = []
            note_elements.append(Paragraph(f"{idx}. {note.title}", note_title_style))
            
            meta = [f"Date: {note.display_date.strftime('%Y-%m-%d')}"]
            if note.created_by: meta.append(f"Analyst: {note.created_by.get_full_name()}")
            if note.note_type: meta.append(f"Type: {note.note_type.name}")
            note_elements.append(Paragraph(" | ".join(meta), meta_text_style))

            if note.content:
                # Pre-process: convert • bullet lines to standard markdown
                preprocessed = re.sub(r'^[•]\s*', '- ', note.content, flags=re.MULTILINE)
                preprocessed = re.sub(r'\{:?[^}]+\}', '', preprocessed)

                # 1. Convert Markdown to HTML
                html_content = markdown.markdown(preprocessed)
                
                # 2. Use bleach to strip tags ReportLab doesn't like
                allowed_tags = ['b', 'i', 'u', 'font', 'br', 'strong', 'em', 'strike', 'img']
                
                # Split by blocks but keep the tag so we know if it's a list item
                parts = re.split(r'(<(?:p|li|blockquote|h[1-6])>)', html_content)
                
                current_tag = None
                for part in parts:
                    if not part.strip(): continue
                    
                    if re.match(r'<(?:p|li|blockquote|h[1-6])>', part):
                        current_tag = part
                        continue
                    
                    block = part
                    # Extract image tags
                    img_tags = re.findall(r'<img[^>]+>', block)
                    if img_tags:
                        for img_tag in img_tags:
                            src_match = re.search(r'src="([^">]+)"', img_tag)
                            if not src_match: continue
                            img_src = src_match.group(1)
                            
                            style_match = re.search(r'style="width:\s*(\d+)px"', img_tag)
                            width_px = int(style_match.group(1)) if style_match else None

                            local_path = ""
                            if img_src.startswith(settings.MEDIA_URL):
                                rel_path = img_src.replace(settings.MEDIA_URL, '', 1)
                                local_path = os.path.join(settings.MEDIA_ROOT, rel_path)
                            
                            if local_path and os.path.exists(local_path):
                                try:
                                    rl_img = Image(local_path)
                                    # Scale
                                    max_w, max_h = 6*inch, 6*inch
                                    w, h = rl_img.drawWidth, rl_img.drawHeight
                                    aspect = h / float(w)
                                    
                                    if width_px:
                                        target_w = width_px * 0.75
                                        rl_img.drawWidth = min(target_w, max_w)
                                        rl_img.drawHeight = rl_img.drawWidth * aspect
                                    else:
                                        if w > max_w:
                                            rl_img.drawWidth = max_w
                                            rl_img.drawHeight = max_w * aspect
                                    
                                    rl_img.hAlign = 'LEFT'
                                    note_elements.append(Spacer(1, 0.1*inch))
                                    note_elements.append(rl_img)
                                    note_elements.append(Spacer(1, 0.1*inch))
                                except:
                                    pass
                        
                        # Remove img tags from text
                        block = re.sub(r'<img[^>]+>', '', block)

                    # Clean the block text
                    block = re.sub(r'\{:?[^}]+\}', '', block)
                    clean_text = bleach.clean(block, tags=allowed_tags, strip=True)
                    
                    # Map tags for ReportLab
                    clean_text = clean_text.replace('<strong>', '<b>').replace('</strong>', '</b>')
                    clean_text = clean_text.replace('<em>', '<i>').replace('</em>', '</i>')
                    
                    # Remove closing tags
                    clean_text = re.sub(r'</(?:p|li|blockquote|ul|ol|h[1-6]|img)>', '', clean_text).strip()
                    
                    if not clean_text: continue
                    
                    try:
                        if current_tag == '<li>':
                            note_elements.append(Paragraph(f"&bull; {clean_text}", bullet_style))
                        else:
                            note_elements.append(Paragraph(clean_text, content_style))
                    except:
                        plain_text = strip_tags(clean_text)
                        if current_tag == '<li>':
                            note_elements.append(Paragraph(f"&bull; {plain_text}", bullet_style))
                        else:
                            note_elements.append(Paragraph(plain_text, content_style))

            note_elements.append(Spacer(1, 0.2*inch))
            content.append(KeepTogether(note_elements))
            content.append(HRFlowable(width="80%", thickness=0.5, color=colors.lightgrey, spaceBefore=10, spaceAfter=10))

    # Build PDF
    doc.build(content, canvasmaker=NumberedCanvas)
    pdf_value = buf.getvalue()
    buf.close()
    return pdf_value
