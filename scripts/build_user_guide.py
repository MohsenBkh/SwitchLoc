"""Build Persian engineering guide and source API index from the current tree.

Requires reportlab, arabic_reshaper and python-bidi. No source file is imported;
AST inspection avoids side effects and includes private module/class members.
"""
from __future__ import annotations
import ast
from pathlib import Path
import re
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'build_assets/help/SwitchLoc_Guide_FA.pdf'
pdfmetrics.registerFont(TTFont('Vazir', str(ROOT / 'build_assets/fonts/Vazirmatn-Regular.ttf')))
pdfmetrics.registerFont(TTFont('VazirBold', str(ROOT / 'build_assets/fonts/Vazirmatn-Bold.ttf')))
PAGE_W, PAGE_H = A4
LEFT, RIGHT, TOP, BOTTOM = 42, 42, 45, 42
canvas = Canvas(str(OUTPUT), pagesize=A4, pageCompression=1)
canvas.setTitle('SwitchLoc Engineering User Guide and Source Reference')
y = PAGE_H - TOP
page = 1


def footer():
    canvas.setFont('Vazir', 8)
    canvas.drawCentredString(PAGE_W / 2, 23, str(page))


def fresh_page():
    global y, page
    footer()
    canvas.showPage()
    page += 1
    y = PAGE_H - TOP


def visual(s):
    try:
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def text_block(text, size=9.1, leading=16, bold=False, rtl=True):
    global y
    font = 'VazirBold' if bold else 'Vazir'
    canvas.setFont(font, size)
    max_width = PAGE_W - LEFT - RIGHT
    for paragraph in text.split('\n'):
        words = paragraph.split()
        line = ''
        for word in words:
            candidate = (line + ' ' + word).strip()
            if line and pdfmetrics.stringWidth(visual(candidate), font, size) > max_width:
                if y < BOTTOM + leading:
                    fresh_page(); canvas.setFont(font, size)
                if rtl: canvas.drawRightString(PAGE_W - RIGHT, y, visual(line))
                else: canvas.drawString(LEFT, y, visual(line))
                y -= leading
                line = word
            else:
                line = candidate
        if line:
            if y < BOTTOM + leading:
                fresh_page(); canvas.setFont(font, size)
            if rtl: canvas.drawRightString(PAGE_W - RIGHT, y, visual(line))
            else: canvas.drawString(LEFT, y, visual(line))
            y -= leading
        else:
            y -= leading * 0.45


def heading(text, level=0):
    global y
    if y < BOTTOM + 60:
        fresh_page()
    y -= 7
    text_block(text, size=13 if level == 0 else 11, leading=19, bold=True)


text_block('راهنمای مهندسی SwitchLoc — روش‌ها، محدودیت‌ها و نمایه کد', 15, 23, True)
text_block('ویرایش ۱.۲۲ — راهنمای کاربرد، مفروضات، روابط محاسبات و نمایه خودکار منبع. داده و خروجی هر پروژه نیاز به تأیید مهندس دارد.', 10, 18)
text_block('فهرست فصل‌ها', 12, 20, True)
manual = (ROOT / 'docs/USER_GUIDE_FA.md').read_text(encoding='utf-8')
for line in manual.splitlines():
    if line.startswith('## '):
        text_block(line[3:], 8.4, 13)
fresh_page()
for block in manual.split('\n\n'):
    if not block.strip(): continue
    if block.startswith('#'):
        heading(block.lstrip('#').strip(), 0 if block.startswith('# ') else 1)
    elif block.startswith('FORMULA:'):
        for formula in block.splitlines():
            text_block(formula.removeprefix('FORMULA:').strip(), size=8.3, leading=15, rtl=False)
        y -= 4
    else:
        text_block(' '.join(x.strip() for x in block.splitlines()))
        y -= 4

fresh_page()
heading('پیوست: نمایه ماژول‌ها، کلاس‌ها و توابع کد')
text_block('این پیوست از درخت کد همین نسخه با AST تولید شده است. خط منبع، امضای تابع و مستندات موجود در کد را نشان می‌دهد. نبود docstring به معنی نبود رفتار نیست. برای منطق کامل، بدنه فایل و آزمون مربوط ملاک است.')
source = ROOT / 'src/switchloc'
module_count = member_count = 0
for path in sorted(source.rglob('*.py')):
    try: tree = ast.parse(path.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeError): continue
    module_count += 1
    heading(str(path.relative_to(ROOT)), 1)
    module_doc = ast.get_docstring(tree)
    if module_doc:
        text_block(' '.join(module_doc.split())[:650], size=8.3, leading=14)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            members = [(node, '')]
            if isinstance(node, ast.ClassDef):
                members += [(n, node.name + '.') for n in node.body
                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for item, prefix in members:
                member_count += 1
                if isinstance(item, ast.ClassDef):
                    label = f'class {item.name}  [line {item.lineno}]'
                else:
                    signature = ast.unparse(item.args)
                    label = f'{prefix}{item.name}({signature})  [line {item.lineno}]'
                text_block(label, size=7.8, leading=12, rtl=False)
                doc = ast.get_docstring(item)
                if doc:
                    text_block(' '.join(doc.split())[:500], size=8, leading=13)
footer()
canvas.save()
print(f'{OUTPUT}: {page} pages, {module_count} modules, {member_count} class/function entries')
