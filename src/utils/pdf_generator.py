import os
from pathlib import Path
import markdown
from weasyprint import HTML, CSS
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime
import logging

class SimplifiedPDFGenerator:
    """
    A simplified PDF generator that takes markdown content and renders it
    into a styled PDF using a Jinja2 template.
    """
    def __init__(self):
        # The template directory is now relative to this file
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
            'extra', 'meta', 'codehilite', 'admonition', 'attr_list', 'toc'
        ])

    def generate_pdf_from_markdown(self, markdown_content: str, report_title: str, user_name: str) -> bytes:
        """
        Generates a PDF from a single markdown string.

        Args:
            markdown_content: The full markdown content of the report.
            report_title: The title for the report cover page.
            user_name: The name of the user who generated the report.

        Returns:
            bytes: The generated PDF content as a byte stream.
        """
        try:
            # Check for and create the template if it doesn't exist
            self._ensure_template_exists()

            self.template = self.env.get_template(self.template_name)

            html_body = self.md.convert(markdown_content)

            context = {
                'report_title': report_title,
                'user_name': user_name,
                'generation_date': datetime.now().strftime('%B %d, %Y'),
                'html_body': html_body,
                'logo_path': self._get_asset_path('supervity-logo.png')
            }

            html_string = self.template.render(**context)
            
            # For debugging, you can save the intermediate HTML
            # with open("debug_report.html", "w", encoding="utf-8") as f:
            #     f.write(html_string)

            base_css = CSS(string="""
                @page { size: A4; margin: 2cm; }
                body { font-family: sans-serif; line-height: 1.6; color: #333; }
                h1, h2, h3 { color: #000b37; }
                h1 { font-size: 24pt; page-break-before: always; }
                h2 { font-size: 18pt; border-bottom: 2px solid #85c20b; padding-bottom: 5px; margin-top: 1.5em; }
                table { border-collapse: collapse; width: 100%; margin: 1em 0; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
                .cover { page-break-after: always; text-align: center; padding-top: 4cm; }
                .cover img { max-width: 200px; margin-bottom: 2cm; }
            """)
            
            html = HTML(string=html_string, base_url=str(self.template_dir))
            pdf_bytes = html.write_pdf(stylesheets=[base_css])
            
            logging.info("PDF generated successfully in memory.")
            return pdf_bytes

        except Exception as e:
            logging.error(f"Error generating PDF: {e}", exc_info=True)
            raise

    def _get_asset_path(self, asset_name: str) -> str:
        asset_path = self.template_dir / asset_name
        return f"file://{asset_path.resolve()}"

    def _ensure_template_exists(self):
        template_file = self.template_dir / self.template_name
        if not template_file.exists():
            logging.info(f"Template not found. Creating a default at {template_file}")
            default_template_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{{ report_title }}</title>
</head>
<body>
    <div class="cover">
        <img src="{{ logo_path }}" alt="Supervity Logo">
        <h1>Market Intelligence Report</h1>
        <h2>{{ report_title }}</h2>
        <p>Prepared for: {{ user_name }}</p>
        <p>Date: {{ generation_date }}</p>
    </div>
    {{ html_body | safe }}
</body>
</html>
"""
            with open(template_file, "w", encoding="utf-8") as f:
                f.write(default_template_html)
            
            # Also create a dummy logo if it doesn't exist
            logo_file = self.template_dir / 'supervity-logo.png'
            if not logo_file.exists():
                # You should copy your actual logo here. This is a placeholder.
                logging.warning("supervity-logo.png not found. Please place it in the src/templates/ directory.") 