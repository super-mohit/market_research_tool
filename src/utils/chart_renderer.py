# File: src/utils/chart_renderer.py (NEW FILE)

import json
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

# A simple, robust Jinja2 environment setup
template_dir = Path(__file__).parent.parent / 'templates'
env = Environment(loader=FileSystemLoader(template_dir))

# --- Chart Colors (to match the frontend) ---
COLORS = ['#85c20b', '#8289ec', '#31b8e1', '#ff9a5a']

def render_radar_chart_html(data: dict) -> str:
    """Renders data for a competitive radar chart into a self-contained HTML file string."""
    template = env.get_template('charts/radar_chart.html')
    
    # Prepare data for Chart.js
    chart_data = {
        "labels": data.get("labels", []),
        "datasets": [
            {
                "label": competitor.get("name"),
                "data": competitor.get("scores"),
                "backgroundColor": f'{COLORS[i % len(COLORS)]}33',  # e.g., #85c20b33 for 20% opacity
                "borderColor": COLORS[i % len(COLORS)],
                "borderWidth": 2,
                "pointBackgroundColor": COLORS[i % len(COLORS)],
            }
            for i, competitor in enumerate(data.get("competitors", []))
        ]
    }
    
    return template.render(
        chart_title="Competitive Landscape",
        chart_data_json=json.dumps(chart_data)
    )

def render_swot_html(data: dict) -> str:
    """Renders SWOT data into a self-contained HTML file string."""
    template = env.get_template('charts/swot_analysis.html')
    return template.render(
        chart_title="Strategic Analysis (SWOT)",
        swot_data=data
    )

# You can add more functions here for other charts like the Hype Cycle in the future
# def render_hype_cycle_html(data: list) -> str: ... 