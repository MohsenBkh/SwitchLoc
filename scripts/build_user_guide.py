"""Build the bundled Persian PDF guide from docs/USER_GUIDE_FA.md."""
from pathlib import Path
from xml.sax.saxutils import escape
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

ROOT = Path(__file__).resolve().parents[1]
pdfmetrics.registerFont(TTFont('Vazir', str(ROOT / 'build_assets/fonts/Vazirmatn-Regular.ttf')))
body = ParagraphStyle('body', fontName='Vazir', fontSize=10, leading=18, alignment=TA_RIGHT, wordWrap='CJK')
heading = ParagraphStyle('heading', parent=body, fontSize=13, leading=22, spaceBefore=12)
blocks = (ROOT / 'docs/USER_GUIDE_FA.md').read_text(encoding='utf-8').split('\n\n')
story = []
for block in blocks:
    text = ' '.join(line.strip().lstrip('#').strip() for line in block.splitlines())
    shaped = get_display(arabic_reshaper.reshape(text))
    story.append(Paragraph(escape(shaped), heading if block.startswith('#') else body))
    story.append(Spacer(1, 5))
output = ROOT / 'build_assets/help/SwitchLoc_Guide_FA.pdf'
output.parent.mkdir(parents=True, exist_ok=True)
SimpleDocTemplate(str(output), pagesize=A4, rightMargin=42, leftMargin=42).build(story)
print(output)
