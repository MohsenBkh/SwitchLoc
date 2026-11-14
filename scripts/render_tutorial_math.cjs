const fs=require('fs'),path=require('path');
const {mathjax}=require('mathjax-full/js/mathjax.js'), {TeX}=require('mathjax-full/js/input/tex.js'), {SVG}=require('mathjax-full/js/output/svg.js'), {liteAdaptor}=require('mathjax-full/js/adaptors/liteAdaptor.js'), {RegisterHTMLHandler}=require('mathjax-full/js/handlers/html.js'), {AllPackages}=require('mathjax-full/js/input/tex/AllPackages.js');
const a=liteAdaptor(); RegisterHTMLHandler(a);
const doc=mathjax.document('', {InputJax:new TeX({packages:AllPackages,macros:{unit:['\\,\\mathrm{#1}',1],bm:['\\boldsymbol{#1}',1]}}),OutputJax:new SVG({fontCache:'local'})});
let eqs=JSON.parse(fs.readFileSync(process.argv[2]));let errors=[];
for(let e of eqs){let node=doc.convert(e.tex,{display:e.display});let html=a.innerHTML(node); if(html.includes('data-mjx-error'))errors.push([e.id,e.tex,html.match(/data-mjx-error="([^"]+)/)?.[1]]); fs.writeFileSync(path.join(process.argv[3],e.id+'.svg'),html)}
if(errors.length){console.error(JSON.stringify(errors,null,2));process.exit(1)}
console.log('Rendered',eqs.length,'equations');
