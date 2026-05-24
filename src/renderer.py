from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Allow the template directory to be resolved relative to this file's location
# so the module works when called from any working directory.
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / 'templates'

env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(['html', 'xml'])
)


def render_email(config: dict, items: list[dict]) -> str:
    template = env.get_template('email.html.j2')
    return template.render(
        digest_id=config['id'],
        subject=config['email']['subject'],
        intro=config.get('render', {}).get('intro', ''),
        items=items,
    )
