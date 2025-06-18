import os
from pathlib import Path
import markdown
from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime
import logging
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

        self.md = markdown.Markdown(extensions=['extra', 'toc', 'fenced_code', 'codehilite'])

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
            
            # Convert markdown to HTML and generate TOC
            html_body = self.md.convert(markdown_content)
            soup = BeautifulSoup(html_body, 'html.parser')
            toc_html = self._generate_toc_html(soup)
            
            # The body needs to be a string for the template
            final_html_body = str(soup)

            context = {
                'report_title': report_title,
                'user_name': user_name,
                'generation_date': datetime.now().strftime('%B %d, %Y'),
                'html_body': final_html_body,
                'toc_html': toc_html,
                'logo_path': f"file://{(self.template_dir / 'supervity-logo.png').resolve()}"
            }

            rendered_html = template.render(**context)
            
            # Professional CSS for styling
            report_css = CSS(string="""
                @font-face {
                    font-family: 'Inter';
                    src: url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
                }
                body {
                    font-family: 'Inter', sans-serif;
                    font-size: 10.5pt;
                    line-height: 1.5;
                    color: #2D3748; /* Gray 700 */
                }

                /* --- Page Setup & Footers --- */
                @page {
                    size: A4;
                    margin: 1.5cm;
                    @bottom-center {
                        content: "Page " counter(page) " of " counter(pages);
                        font-size: 9pt;
                        color: #A0AEC0; /* Gray 400 */
                        width: 100%;
                        text-align: center;
                    }
                }
                @page:first {
                    margin: 0;
                    @bottom-center { content: none; }
                }
                
                /* --- Cover Page --- */
                .cover-page {
                    page-break-after: always;
                    background: #F7FAFC; /* Gray 100 */
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    text-align: center;
                }
                .cover-page .header {
                    padding: 1.5cm;
                    text-align: left;
                }
                .cover-page .logo {
                    width: 150px;
                }
                .cover-page .main-content {
                    flex-grow: 1;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    padding: 2cm;
                }
                .cover-page .report-main-title {
                    font-size: 28pt;
                    color: #1A202C; /* Gray 900 */
                    font-weight: 700;
                    margin: 0;
                }
                .cover-page .report-subtitle {
                    font-size: 16pt;
                    color: #4A5568; /* Gray 600 */
                    margin: 0.5cm 0;
                    font-weight: 400;
                    line-height: 1.4;
                }
                .cover-page .footer {
                    padding: 1.5cm;
                    font-size: 11pt;
                    color: #718096; /* Gray 500 */
                    border-top: 1px solid #E2E8F0; /* Gray 200 */
                }

                /* --- Table of Contents Page --- */
                .toc-page {
                    page-break-after: always;
                }
                .toc-main-title {
                    font-size: 24pt;
                    color: #1A202C;
                    border-bottom: 3px solid #85c20b; /* Supervity Lime */
                    padding-bottom: 0.25cm;
                    margin-bottom: 1cm;
                }
                .toc-nav .toc-list {
                    list-style-type: none;
                    padding-left: 0;
                }
                .toc-nav a {
                    text-decoration: none;
                    color: #2D3748;
                    display: flex;
                    justify-content: space-between;
                }
                .toc-nav a::after {
                    content: target-counter(attr(href), page);
                    color: #718096;
                }
                .toc-nav .toc-level-1 {
                    font-size: 14pt;
                    font-weight: 600;
                    margin: 0.8em 0;
                    border-bottom: 1px dotted #CBD5E0; /* Gray 300 */
                    padding-bottom: 0.8em;
                }
                .toc-nav .toc-level-2 {
                    font-size: 11pt;
                    margin: 0.6em 0 0.6em 1.5em;
                }

                /* --- Report Body --- */
                .report-body h1, .report-body h2, .report-body h3 {
                    color: #1A202C;
                    font-weight: 700;
                    page-break-after: avoid;
                    margin-top: 1.5em;
                }
                .report-body h1 {
                    font-size: 20pt;
                    border-bottom: 2px solid #85c20b;
                    padding-bottom: 8px;
                    margin-bottom: 1em;
                }
                .report-body h2 {
                    font-size: 15pt;
                    border-bottom: 1px solid #E2E8F0;
                    padding-bottom: 6px;
                }
                .report-body h3 {
                    font-size: 13pt;
                }
                .report-body p {
                    text-align: justify;
                }
                .report-body table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 1.5em 0;
                    page-break-inside: avoid;
                }
                .report-body th, .report-body td {
                    border: 1px solid #E2E8F0;
                    padding: 10px 14px;
                    text-align: left;
                }
                .report-body th {
                    background-color: #F7FAFC;
                    font-weight: 600;
                }
                .report-body blockquote {
                    margin: 1em 0;
                    padding: 0.8em 1.2em;
                    background-color: #f0f7ff;
                    border-left: 4px solid #8289ec; /* Supervity Soft Blue */
                    font-style: italic;
                }
                .report-body a {
                    color: #65a30d; /* Supervity Lime Dark */
                    text-decoration: none;
                }
                .report-body ul, .report-body ol {
                    padding-left: 2em;
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