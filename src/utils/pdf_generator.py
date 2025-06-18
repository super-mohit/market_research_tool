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

        self.md = markdown.Markdown(extensions=[
            'extra', 'toc', 'fenced_code', 'codehilite', 'tables'
        ])

    def _generate_toc_html(self, soup: BeautifulSoup) -> str:
        """Generates a table of contents HTML from h1 and h2 tags."""
        toc_entries = []
        for header in soup.find_all(['h1', 'h2']):
            header_id = header.get('id')
            if not header_id:
                # Create a slug for the ID if it doesn't exist
                header_text = header.get_text(strip=True)
                header_id = re.sub(r'[^\w\s-]', '', header_text).strip()
                header_id = re.sub(r'[-\s]+', '-', header_id).lower()
                header['id'] = header_id
            
            level = 1 if header.name == 'h1' else 2
            toc_entries.append({
                'level': level,
                'text': header.get_text(strip=True),
                'id': header_id
            })

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
                'logo_path': self._get_asset_path('supervity-logo.png')
            }

            rendered_html = template.render(**context)
            
            # Create HTML object and generate PDF
            html = HTML(string=rendered_html, base_url=str(self.template_dir.resolve()))
            pdf_bytes = html.write_pdf()
            
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