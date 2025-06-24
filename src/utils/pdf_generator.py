import os
from pathlib import Path
import markdown
from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime
import logging
import base64
import re
from bs4 import BeautifulSoup

class ProfessionalPDFGenerator:
    """
    Generates a high-quality, professionally styled PDF report from markdown content.
    Features a cover page, table of contents, and rich styling.
    """
    def __init__(self):
        self.template_dir = Path(__file__).parent.parent / 'templates'
        self.template_name = 'report_template.html'
        
        if not self.template_dir.exists():
            os.makedirs(self.template_dir)
            logging.warning(f"Template directory created at {self.template_dir}")
        
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

        self.md = markdown.Markdown(extensions=['extra', 'toc', 'fenced_code', 'codehilite'], extension_configs={'toc': {'anchorlink': True}})

    def _get_logo_base64(self) -> str:
        """Reads the logo file and returns it as a Base64 data URI."""
        logo_path = self.template_dir / 'supervity-logo.png'
        if not logo_path.exists():
            logging.error(f"Logo not found at {logo_path}! PDF will not have a logo.")
            return ""
        try:
            with open(logo_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
            return f"data:image/png;base64,{encoded_string}"
        except Exception as e:
            logging.error(f"Could not encode logo to Base64: {e}")
            return ""

    def _generate_toc_html(self, soup: BeautifulSoup) -> str:
        """Generates a table of contents HTML from h1 and h2 tags."""
        toc_entries = []
        for header in soup.find_all(['h1', 'h2']):
            header_id = header.get('id')
            if not header_id:
                raw_text = header.get_text(strip=True)
                slug = re.sub(r'[^\w\s-]', '', raw_text).strip().lower()
                header_id = re.sub(r'[\s_]+', '-', slug)
                header['id'] = header_id
            
            level = 1 if header.name == 'h1' else 2
            toc_entries.append({'level': level, 'text': header.get_text(strip=True), 'id': header_id})

        if not toc_entries:
            return "<p>No sections found.</p>"

        html = '<ul class="toc-list">'
        for entry in toc_entries:
            html += f'''
            <li class="toc-level-{entry["level"]}">
                <a href="#{entry["id"]}">
                    <span class="toc-text">{entry["text"]}</span>
                    <span class="toc-dots"></span>
                </a>
            </li>'''
        html += '</ul>'
        return html

    def generate_pdf_from_markdown(self, markdown_content: str, report_title: str, user_name: str) -> bytes:
        """
        Main function to generate the PDF byte stream from markdown.
        """
        try:
            template = self.env.get_template(self.template_name)
            
            html_body = self.md.convert(markdown_content)
            toc_html = self.md.toc
            
            if not toc_html or toc_html.strip() == "":
                soup = BeautifulSoup(html_body, 'html.parser')
                toc_html = self._generate_toc_html(soup)
                final_html_body = str(soup)
            else:
                final_html_body = html_body

            context = {
                'report_title': report_title,
                'user_name': user_name,
                'generation_date': datetime.now().strftime('%B %d, %Y'),
                'html_body': final_html_body,
                'toc_html': toc_html,
                'logo_base64': self._get_logo_base64()
            }

            rendered_html = template.render(**context)
            
            report_css = CSS(string="""
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
                
                * {
                    box-sizing: border-box;
                }
                
                body {
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    font-size: 11pt;
                    line-height: 1.6;
                    color: #1a202c;
                    margin: 0;
                    padding: 0;
                    font-weight: 400;
                    -webkit-font-smoothing: antialiased;
                    -moz-osx-font-smoothing: grayscale;
                }

                /* --- Premium Page Setup & Layout --- */
                @page {
                    size: A4;
                    margin: 2cm 2.5cm 2.5cm 2.5cm;
                    @bottom-left {
                        content: "© 2024 Supervity • Market Intelligence Report";
                        font-size: 8pt;
                        color: #9ca3af;
                        font-weight: 400;
                    }
                    @bottom-right {
                        content: "Page " counter(page) " of " counter(pages);
                        font-size: 8pt;
                        color: #9ca3af;
                        font-weight: 500;
                    }
                    @bottom-center {
                        content: "";
                    }
                }
                
                @page:first {
                    margin: 0;
                    @bottom-left { content: none; }
                    @bottom-right { content: none; }
                }
                
                /* --- Premium Cover Page --- */
                .cover-page {
                    page-break-after: always;
                    background: #f8fafc;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    position: relative;
                }
                
                .cover-page::before {
                    content: "";
                    position: absolute;
                    top: 0;
                    right: 0;
                    width: 40%;
                    height: 100%;
                    background: linear-gradient(45deg, rgba(133, 194, 11, 0.05) 0%, rgba(130, 137, 236, 0.08) 100%);
                    clip-path: polygon(30% 0%, 100% 0%, 100% 100%, 0% 100%);
                }
                
                .cover-page .header {
                    padding: 3cm 3cm 2cm 3cm;
                    z-index: 2;
                    position: relative;
                }
                
                .cover-page .logo {
                    width: 180px;
                    height: auto;
                }
                
                .cover-page .main-content {
                    flex-grow: 1;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    padding: 3cm;
                    text-align: left;
                    z-index: 2;
                    position: relative;
                }
                
                .cover-page .report-main-title {
                    font-size: 38pt;
                    color: #0f172a;
                    font-weight: 800;
                    margin: 0 0 0.5cm 0;
                    letter-spacing: -0.025em;
                    line-height: 1.2;
                    word-wrap: break-word;
                }
                
                .cover-page .report-subtitle {
                    font-size: 18pt;
                    color: #475569;
                    margin: 0 0 2cm 0;
                    font-weight: 500;
                    line-height: 1.4;
                    max-width: 80%;
                    letter-spacing: -0.01em;
                }
                
                .cover-page .highlight-bar {
                    width: 80px;
                    height: 6px;
                    background: #85c20b;
                    margin: 1cm 0 1.5cm 0;
                    border-radius: 3px;
                }
                
                .cover-page .footer {
                    padding: 2cm 3cm 3cm 3cm;
                    border-top: 1px solid rgba(226, 232, 240, 0.8);
                    background: rgba(255, 255, 255, 0.9);
                    z-index: 2;
                    position: relative;
                }
                
                .cover-page .footer-content {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .cover-page .client-info {
                    font-size: 12pt;
                    color: #64748b;
                    font-weight: 500;
                }
                
                .cover-page .client-info strong {
                    color: #1e293b;
                    font-weight: 600;
                    display: block;
                    margin-bottom: 0.2cm;
                }
                
                .cover-page .report-meta {
                    text-align: right;
                    font-size: 11pt;
                    color: #64748b;
                    font-weight: 400;
                }

                /* --- Premium Table of Contents --- */
                .toc-page {
                    page-break-after: always;
                    padding-top: 1cm;
                }
                
                .toc-main-title {
                    font-size: 32pt;
                    color: #0f172a;
                    font-weight: 700;
                    margin: 0 0 1.5cm 0;
                    padding-bottom: 0.5cm;
                    border-bottom: 3px solid #85c20b;
                    position: relative;
                    letter-spacing: -0.02em;
                }
                
                .toc-main-title::after {
                    content: "";
                    position: absolute;
                    bottom: -3px;
                    left: 0;
                    width: 60px;
                    height: 3px;
                    background: linear-gradient(90deg, #8289ec 0%, #31b8e1 100%);
                }
                
                .toc-nav {
                    background: rgba(248, 250, 252, 0.6);
                    padding: 1.5cm;
                    border-radius: 12px;
                    border: 1px solid rgba(226, 232, 240, 0.8);
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
                }
                
                .toc-nav ul {
                    list-style-type: none;
                    padding-left: 0;
                    margin: 0;
                }
                
                .toc-nav li {
                    margin: 0.8em 0;
                    position: relative;
                }
                
                .toc-nav a {
                    text-decoration: none;
                    color: #334155;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 0.6em 0;
                    border-bottom: 1px dotted rgba(203, 213, 224, 0.6);
                    transition: all 0.2s ease;
                    font-weight: 500;
                }
                
                .toc-nav a:hover {
                    color: #85c20b;
                    padding-left: 0.5em;
                }
                
                .toc-nav a::after {
                    content: target-counter(attr(href), page);
                    color: #85c20b;
                    font-weight: 600;
                    background: rgba(133, 194, 11, 0.1);
                    padding: 0.2em 0.5em;
                    border-radius: 6px;
                    font-size: 0.9em;
                }
                
                .toc-nav .toc-level-1 {
                    font-size: 14pt;
                    font-weight: 600;
                }
                
                .toc-nav .toc-level-1 a {
                    font-size: 14pt;
                    color: #1e293b;
                    border-bottom: 2px solid rgba(133, 194, 11, 0.2);
                    padding: 0.8em 0;
                }
                
                .toc-nav .toc-level-2 {
                    font-size: 12pt;
                    margin-left: 1.5em;
                    position: relative;
                }
                
                .toc-nav .toc-level-2::before {
                    content: "→";
                    position: absolute;
                    left: -1.2em;
                    color: #85c20b;
                    font-weight: bold;
                }

                /* --- Premium Report Body --- */
                .report-body {
                    padding-top: 0.5cm;
                }
                
                .report-body h1, .report-body h2, .report-body h3, .report-body h4 {
                    color: #0f172a;
                    font-weight: 700;
                    page-break-after: avoid;
                    page-break-inside: avoid;
                    letter-spacing: -0.01em;
                    line-height: 1.2;
                }
                
                .report-body h1 {
                    font-size: 24pt;
                    margin: 2em 0 1em 0;
                    padding: 0.8em 0 0.4em 0;
                    border-bottom: 3px solid #85c20b;
                    position: relative;
                    page-break-before: always;
                }
                
                .report-body h1:first-child {
                    page-break-before: avoid;
                }
                
                .report-body h1::after {
                    content: "";
                    position: absolute;
                    bottom: -3px;
                    left: 0;
                    width: 80px;
                    height: 3px;
                    background: linear-gradient(90deg, #8289ec 0%, #31b8e1 100%);
                }
                
                .report-body h2 {
                    font-size: 18pt;
                    margin: 1.8em 0 0.8em 0;
                    padding: 0.6em 0 0.3em 0;
                    border-bottom: 2px solid rgba(226, 232, 240, 0.8);
                    position: relative;
                }
                
                .report-body h2::before {
                    content: "";
                    position: absolute;
                    left: 0;
                    top: 0;
                    width: 4px;
                    height: 100%;
                    background: linear-gradient(180deg, #85c20b 0%, #22c55e 100%);
                    border-radius: 2px;
                    margin-right: 0.5em;
                }
                
                .report-body h3 {
                    font-size: 15pt;
                    margin: 1.5em 0 0.6em 0;
                    color: #1e293b;
                    font-weight: 600;
                    position: relative;
                    padding-left: 1em;
                }
                
                .report-body h3::before {
                    content: "▶";
                    position: absolute;
                    left: 0;
                    color: #85c20b;
                    font-size: 0.8em;
                }
                
                .report-body h4 {
                    font-size: 13pt;
                    margin: 1.2em 0 0.5em 0;
                    color: #334155;
                    font-weight: 600;
                }
                
                .report-body p {
                    text-align: justify;
                    margin: 0.8em 0;
                    line-height: 1.7;
                    color: #374151;
                    hyphens: auto;
                }
                
                .report-body p:first-of-type {
                    font-size: 12pt;
                    color: #1e293b;
                    font-weight: 500;
                    line-height: 1.6;
                }
                
                /* --- Premium Tables --- */
                .report-body table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 2em 0;
                    page-break-inside: avoid;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
                    border-radius: 8px;
                    overflow: hidden;
                    background: white;
                }
                
                .report-body th {
                    background: linear-gradient(135deg, #85c20b 0%, #22c55e 100%);
                    color: white;
                    padding: 1em 1.2em;
                    text-align: left;
                    font-weight: 600;
                    font-size: 11pt;
                    letter-spacing: 0.025em;
                    text-transform: uppercase;
                    border: none;
                }
                
                .report-body td {
                    padding: 0.9em 1.2em;
                    border-bottom: 1px solid rgba(226, 232, 240, 0.6);
                    color: #374151;
                    font-size: 10.5pt;
                    vertical-align: top;
                }
                
                .report-body tr:nth-child(even) {
                    background: rgba(248, 250, 252, 0.5);
                }
                
                .report-body tr:hover {
                    background: rgba(133, 194, 11, 0.05);
                }
                
                /* --- Premium Lists --- */
                .report-body ul, .report-body ol {
                    padding-left: 1.5em;
                    margin: 1em 0;
                    line-height: 1.7;
                }
                
                .report-body ul li {
                    margin: 0.5em 0;
                    position: relative;
                    color: #374151;
                    padding-left: 0.5em;
                }
                
                .report-body ul li::marker {
                    color: #85c20b;
                    font-weight: bold;
                }
                
                .report-body ol li {
                    margin: 0.5em 0;
                    color: #374151;
                    padding-left: 0.5em;
                }
                
                .report-body ol li::marker {
                    color: #85c20b;
                    font-weight: 600;
                }
                
                /* --- Premium Blockquotes --- */
                .report-body blockquote {
                    margin: 2em 0;
                    padding: 1.5em 2em;
                    background: linear-gradient(135deg, rgba(130, 137, 236, 0.08) 0%, rgba(49, 184, 225, 0.06) 100%);
                    border-left: 6px solid #8289ec;
                    border-radius: 0 8px 8px 0;
                    font-style: italic;
                    font-size: 12pt;
                    color: #1e293b;
                    position: relative;
                    box-shadow: 0 2px 12px rgba(130, 137, 236, 0.15);
                }
                
                .report-body blockquote::before {
                    content: "\"";
                    font-size: 48pt;
                    color: rgba(130, 137, 236, 0.3);
                    position: absolute;
                    top: -0.2em;
                    left: 0.5em;
                    font-family: serif;
                    font-weight: bold;
                }
                
                .report-body blockquote p {
                    margin: 0;
                    position: relative;
                    z-index: 1;
                }
                
                /* --- Premium Links --- */
                .report-body a {
                    color: #85c20b;
                    text-decoration: none;
                    font-weight: 500;
                    border-bottom: 1px solid rgba(133, 194, 11, 0.3);
                    transition: all 0.2s ease;
                }
                
                .report-body a:hover {
                    color: #22c55e;
                    border-bottom-color: #22c55e;
                }
                
                /* --- Premium Code Blocks --- */
                .report-body code {
                    background: rgba(248, 250, 252, 0.8);
                    padding: 0.2em 0.4em;
                    border-radius: 4px;
                    font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace;
                    font-size: 0.9em;
                    color: #be185d;
                    border: 1px solid rgba(226, 232, 240, 0.6);
                }
                
                .report-body pre {
                    background: #1e293b;
                    color: #f1f5f9;
                    padding: 1.5em;
                    border-radius: 8px;
                    overflow-x: auto;
                    margin: 1.5em 0;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
                    border: 1px solid rgba(51, 65, 85, 0.8);
                }
                
                .report-body pre code {
                    background: none;
                    padding: 0;
                    border: none;
                    color: inherit;
                    font-size: 10pt;
                }
                
                /* --- Premium Emphasis --- */
                .report-body strong {
                    color: #1e293b;
                    font-weight: 600;
                }
                
                .report-body em {
                    color: #475569;
                    font-style: italic;
                }
                
                /* --- Print Optimizations --- */
                @media print {
                    .report-body {
                        -webkit-print-color-adjust: exact;
                        print-color-adjust: exact;
                    }
                }
            """)
            
            html = HTML(string=rendered_html, base_url=str(self.template_dir.resolve()))
            pdf_bytes = html.write_pdf(stylesheets=[report_css])
            
            logging.info("Professional PDF generated successfully in memory.")
            return pdf_bytes

        except Exception as e:
            logging.error(f"Error generating professional PDF: {e}", exc_info=True)
            raise

    def _get_asset_path(self, asset_name: str) -> str:
        """Get the file:// URL for an asset in the templates directory."""
        asset_path = self.template_dir / asset_name
        if not asset_path.exists():
            logging.warning(f"Asset {asset_name} not found at {asset_path}")
        return f"file://{asset_path.resolve()}"

# Maintain backward compatibility
SimplifiedPDFGenerator = ProfessionalPDFGenerator 