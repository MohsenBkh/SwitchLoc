"""Render the reviewed tutorial as a Persian PDF, with vector MathJax formulas.

Dependencies: Python packages typst, pylatexenc, arabic-reshaper, python-bidi;
Node.js and mathjax-full v3 (install in node_modules or set NODE_PATH).
Run: python scripts/build_tutorial_pdf.py
The original TeX remains the source of truth. A temporary directory is used;
the in-app PDF is replaced only after successful rendering and compilation.
"""
import os, re, json, pathlib, subprocess, tempfile, shutil, atexit
from pylatexenc.latexwalker import LatexWalker, LatexCharsNode, LatexMacroNode, LatexGroupNode, LatexEnvironmentNode, LatexMathNode, LatexCommentNode
import typst
import arabic_reshaper
from bidi.algorithm import get_display
ROOT=pathlib.Path(__file__).resolve().parents[1]; source=(ROOT/'SwitchLoc_Feeder_Tutorial_FA.tex').read_text(); source=source[source.index('\\frontmatter'):source.index('\\backmatter')]
ns,_,_=LatexWalker(source).get_latex_nodes()
R={};ch=0;eqno=0
for n in ns:
 if isinstance(n,LatexMacroNode) and n.macroname=='chapter':
  raw=source[n.pos:n.pos+n.len]
  if not raw.startswith('\\chapter*'):ch+=1;eqno=0
 if isinstance(n,LatexEnvironmentNode) and n.environmentname in ('equation','align'):
  raw=source[n.pos:n.pos+n.len]; labels=re.findall(r'\\label\{([^}]+)\}',raw)
  if labels:
   for label in labels: eqno+=1;R[label]=f'{ch}.{eqno}'
  else:eqno+=1
math=[]; unknown=set()
def quote(s):return json.dumps(str(s),ensure_ascii=False)
def text(s):return '#text('+quote(s)+')'
def mathimg(tex,display=False):
 tex=re.sub(r'\\label\{[^}]+\}','',tex).strip()
 tex=re.sub(r'\\text\{([^{}]*[\u0600-\u06ff][^{}]*)\}', lambda m: r'\text{'+get_display(arabic_reshaper.reshape(m.group(1)))+'}', tex)
 ident='m%04d'%len(math);math.append({'id':ident,'tex':tex,'display':display})
 return ('@@DISPLAY:'+ident+'@@' if display else '@@INLINE:'+ident+'@@')
def arg(n):
 if not getattr(n,'nodeargd',None):return None
 return next((x for x in reversed(n.nodeargd.argnlist) if isinstance(x,LatexGroupNode)),None)
def inline(nodes):
 out=[];i=0
 while i<len(nodes):
  n=nodes[i];i+=1
  if isinstance(n,LatexCharsNode):out.append(text(re.sub(r'\s+',' ',n.chars)))
  elif isinstance(n,LatexMathNode):out.append(mathimg(source[n.pos+1:n.pos+n.len-1]))
  elif isinstance(n,LatexGroupNode):out.append(inline(n.nodelist))
  elif isinstance(n,LatexMacroNode):
   m=n.macroname;a=arg(n)
   if m in ('lr','file','code','Rrule','unit'):
    if a is None and i<len(nodes) and isinstance(nodes[i],LatexGroupNode):a=nodes[i];i+=1
    if a:out.append('#text(dir: ltr)['+inline(a.nodelist)+']')
   elif m in ('textbf','texttt','emph'):
    if a:out.append(inline(a.nodelist))
   elif m=='eqref':
    label=source[a.pos+1:a.pos+a.len-1] if a else ''

    if label not in R: raise ValueError('Unresolved equation reference: '+label)
    out.append('#text(dir: ltr)['+text('('+R[label]+')')+']')
   elif m in ('warn','assumption','answer'):out.append(text({'warn':'نکته مهم: ','assumption':'فرض آموزشی: ','answer':'پاسخ: '}[m]))
   elif m in ('allowbreak','noindent','small','centering','label','toprule','midrule','bottomrule','endhead','endfirsthead','par') :pass
   elif m in ('_', '%', '&', '#', '$', '{','}'):out.append(text(m))
   elif m=='verb':out.append(text(source[n.pos:n.pos+n.len].replace('\\verb|','').removesuffix('|')))
   else:unknown.add(m)
 return ''.join(out)
def convert_snippet(s):
 global source
 prev=source;source=s
 try:nodes,_,_=LatexWalker(s).get_latex_nodes();return inline(nodes)
 finally:source=prev
def table(n):
 raw=source[n.pos:n.pos+n.len]
 cap=re.search(r'\\caption\{([^}]*)\}',raw)
 caption=convert_snippet(cap.group(1)) if cap else ''
 sub=re.search(r'\\begin\{tabularx?\}[^\n]*\n(.*?)\\end\{tabularx?\}',raw,re.S)
 if sub:raw=sub.group(1)
 else:
  raw=raw.split('\n',1)[1];raw=raw.rsplit('\\end{longtable}',1)[0]
  raw=re.sub(r'^.*?\\endfirsthead', '', raw, flags=re.S) if '\\endfirsthead' in raw else raw
  raw=raw.replace('\\endhead', '')
 raw=re.sub(r'\\caption\{[^}]*\}|\\label\{[^}]*\}|\\(?:toprule|midrule|bottomrule|endhead|endfirsthead|centering|small)','',raw)
 rows=[]
 for r in re.split(r'\\\\(?:\[[^]]+\])?',raw):
  r=r.strip()
  if not r:continue
  cells=[x.strip() for x in r.split('&')]
  rows.append(cells)
 if not rows:return ''
 cols=max(len(row) for row in rows)
 # Put the original first column at the right in an RTL document.
 weights=[]
 for j in range(cols):
  size=max((len(re.sub(r'\\\w+','',row[j])) for row in rows if j<len(row)),default=5)
  weights.append(max(1,min(5,size/15)))
 weights=list(reversed(weights))
 cells=[]
 for row in rows:
  row=(row+['']*cols)[:cols]
  for c in reversed(row):cells.append('['+convert_snippet(c)+']')
 return '\n#block(breakable: true)[\n#align(center)[#text(size: 9pt, weight: "bold")['+caption+']]\n#set text(size: '+('6.7pt' if cols>=7 else '8pt')+')\n#table(columns: ('+', '.join(f'{x:.2f}fr' for x in weights)+',), inset: 3pt, stroke: 0.3pt + gray, '+', '.join(cells)+')\n]\n'
def body(nodes):
 out=[]; para=[];chapter=0;section=0
 def flush():
  if para:
   out.append(''.join(para)+'\n\n');para.clear()
 i=0
 while i < len(nodes):
  n=nodes[i];i+=1
  if isinstance(n,LatexCharsNode):
   chunks=re.split(r'(\n\s*\n)',n.chars)
   for c in chunks:
    if re.fullmatch(r'\n\s*\n',c):flush()
    elif c:para.append(text(re.sub(r'\s+',' ',c)))
  elif isinstance(n,LatexMathNode):para.append(mathimg(source[n.pos+1:n.pos+n.len-1]))
  elif isinstance(n,LatexGroupNode):para.append(inline(n.nodelist))
  elif isinstance(n,LatexMacroNode):
   name=n.macroname
   if name in ('lr','file','code','Rrule','unit') and arg(n) is None and i<len(nodes) and isinstance(nodes[i],LatexGroupNode):
    para.append('#text(dir: ltr)['+inline(nodes[i].nodelist)+']'); i+=1
   elif name in ('chapter','section','subsection'):
    flush();a=arg(n);raw=source[n.pos:n.pos+n.len];star=raw.startswith('\\'+name+'*')
    if name=='chapter' and not star:chapter+=1;section=0
    if name=='section':section+=1
    prefix= ('فصل '+str(chapter)+' ـ ' if name=='chapter' and not star else str(chapter)+'.'+str(section)+' ـ ' if name=='section' else '')
    out.append('\n#block(above: 16pt, below: 8pt, breakable: false)[#text(size: '+('15pt' if name=='chapter' else '12pt')+', weight: "bold", fill: rgb("#123a59"))['+text(prefix)+(inline(a.nodelist) if a else '')+']]\n\n')
   elif name=='summary':
    flush();a=arg(n)
    if a is None and i<len(nodes) and isinstance(nodes[i],LatexGroupNode):a=nodes[i];i+=1
    value=source[a.pos+1:a.pos+a.len-1] if a else ''
    out.append('\n#text(weight: "bold", fill: rgb("#123a59"))['+text('جمع‌بندی فصل '+value)+']\n\n')
   elif name=='exercise':flush();out.append('\n#text(weight: "bold")['+text('تمرین کوتاه و پاسخ')+']\n\n')
   elif name in ('tableofcontents','listoftables','mainmatter','frontmatter'):pass
   elif name=='item':flush();para.append(text('• '))
   else:
    # Custom one-argument macros have an adjacent group at this level;
    # their group is emitted on the next iteration.
    para.append(inline([n]))
  elif isinstance(n,LatexEnvironmentNode):
   flush();env=n.environmentname
   if env in ('equation','align'):
    raw=source[n.pos:n.pos+n.len];expr=raw.split('}',1)[1].rsplit('\\end{',1)[0]
    labs=re.findall(r'\\label\{([^}]+)\}',expr);expr=re.sub(r'\\label\{[^}]+\}','',expr)
    if 'eq:binary' in labs:
     # MathJax cannot shape RTL text inside an SVG formula. The surrounding
     # paragraph gives the Persian definition; use equivalent English labels.
     expr=r'x_j=\begin{cases}1,&\text{installed at }j,\\0,&\text{otherwise.}\end{cases}'
    if env=='align':expr='\\begin{aligned}'+expr+'\\end{aligned}'
    img=mathimg(expr,True);refs=', '.join(R[x] for x in labs)
    out.append('\n#align(center)['+img+']\n'+('#align(center)[#text(dir: ltr)['+text('('+refs+')')+']]\n' if refs else '')+'\n')
   elif env in ('table','longtable'):out.append(table(n))
   elif env in ('itemize','enumerate'):out.append(body(n.nodelist))
   else:unknown.add('ENV:'+env)
 flush();return ''.join(out)
chapter_titles=[]
for n in ns:
 if isinstance(n,LatexMacroNode) and n.macroname=='chapter':
  a=arg(n)
  if a:
   chapter_titles.append(inline(a.nodelist))
content=body(ns)
print('Unsupported macros:', sorted(unknown), 'labels:', len(R), 'math expressions:', len(math))
if unknown: raise ValueError('Unsupported LaTeX constructs: '+', '.join(sorted(unknown)))
work=pathlib.Path(tempfile.mkdtemp(prefix='switchloc-tutorial-'));atexit.register(shutil.rmtree, work, ignore_errors=True)
(work/'math.json').write_text(json.dumps(math,ensure_ascii=False));subprocess.run(['node',str(ROOT/'scripts/render_tutorial_math.cjs'),str(work/'math.json'),str(work)],check=True)
template='''#set page(paper: "a4", margin: (x: 20mm, y: 20mm), footer: align(center)[#context counter(page).display()])
#set text(font: "Vazirmatn", size: 10pt, lang: "fa", dir: rtl)
#set par(justify: true, leading: 0.7em)
#align(center)[#text(size: 19pt, weight: "bold", fill: rgb("#123a59"))[راهنمای آموزشی مهندسی SwitchLoc]]
#align(center)[#text(size: 13pt)[تحلیل قابلیت اطمینان و جایابی تجهیزات شبکه توزیع]]
#align(center)[#text(size: 10pt)[متن آموزشی و مطالعه موردی ـ نسخه بازبینی‌شده ۱٫۲۳]]
#pagebreak()
'''
for e in math:
 svg=(work/(e['id']+'.svg')).read_text()
 found=re.search(r'width=\"([0-9.]+)ex\"',svg)
 width=min(465.0, float(found.group(1))*4.5) if found else 200.0
 if e['display']:
  content=content.replace('@@DISPLAY:'+e['id']+'@@', '#image('+quote(e['id']+'.svg')+', width: '+str(round(width,2))+'pt)')
 else:
  width=min(width, 250.0)
  content=content.replace('@@INLINE:'+e['id']+'@@', '#box(baseline: 20%, image('+quote(e['id']+'.svg')+', width: '+str(round(width,2))+'pt))')
toc='#text(size: 16pt, weight: \"bold\")[فهرست فصل‌ها]\n\n' + ''.join('#block(below: 7pt)['+title+']\n' for title in chapter_titles) + '#pagebreak()\n'
(work/'guide.typ').write_text(template+toc+content)
try:typst.compile(str(work/'guide.typ'),output=str(work/'guide.pdf'),root=str(work),font_paths=[str(ROOT/'build_assets/fonts')]);print('compiled',work/'guide.pdf')
except Exception as e:print('TYPST ERROR',e);raise

output=ROOT/'build_assets/help/SwitchLoc_Guide_FA.pdf'
output.parent.mkdir(parents=True,exist_ok=True)
shutil.copyfile(work/'guide.pdf',output)
print('installed',output)
