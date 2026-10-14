'use strict';
const $ = id => document.getElementById(id);
const labels = {control:'Control',corrosion:'Corrosion',rotation:'Rotation',spiderweb:'Spiderweb','cross-shadow':'Cross-shadow',strippy:'Strippy',darts:'Darts',combined:'Combined',sampler:'All families'};
let health, items = [], selected = 0, results = new Map(), generating = false, reading = false;
function notice(text, error=false) { $('notice').textContent=text; $('notice').classList.toggle('error',error); }
function severityOptions(preferred) {
  const list = health.families[$('family').value];
  $('severity').replaceChildren(...list.map(value=>{const option=document.createElement('option');option.value=value;option.textContent=value[0].toUpperCase()+value.slice(1);return option;}));
  if (list.includes(preferred)) $('severity').value=preferred;
}
function controls() {
  $('generate').disabled=generating; $('new-seed').disabled=generating;
  $('generate').firstChild.textContent=generating?'Generating… ':'Generate batch ';
  $('read').disabled=!items.length||reading; $('export').disabled=!items.length||generating;
  $('read').firstChild.textContent=reading?'Reading… ':'Run OCR ';
  $('copy-label').disabled=!items.length;
}
async function post(path, data, binary=false) {
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if (!response.ok) {let info;try{info=await response.json();}catch(e){info={error:`Request failed (${response.status})`};}throw new Error(info.error+(info.detail?': '+info.detail:''));}
  return binary ? response.blob() : response.json();
}
function drawBoxes() {
  const canvas=$('boxes'), image=$('preview-image');
  if (!$('show-boxes').checked || !items.length || !image.complete || !image.naturalWidth) {canvas.hidden=true;return;}
  const item=items[selected], rect=image.getBoundingClientRect(), parent=image.parentElement.getBoundingClientRect();
  canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
  canvas.style.width=rect.width+'px';canvas.style.height=rect.height+'px';
  canvas.style.left=(rect.left-parent.left)+'px';canvas.style.top=(rect.top-parent.top)+'px';
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.strokeStyle='#347451';ctx.lineWidth=1.2;
  for (const [x0,x1,y0,y1] of item.char_boxes) ctx.strokeRect(x0,y0,x1-x0,y1-y0);
  canvas.hidden=false;
}
function display() {
  if (!items.length) return;
  const item=items[selected], image=$('preview-image'), result=results.get(item.id);
  if (image.getAttribute('src')!==item.url) {image.src=item.url;image.onload=drawBoxes;}
  image.alt='Synthetic text sample '+(selected+1)+'; '+item.family+', '+item.severity;image.hidden=false;$('placeholder').hidden=true;
  $('sample-tag').textContent=(labels[item.family]||item.family)+' / '+item.severity;
  $('dimensions').textContent=item.width+' × '+item.height+' px';$('truth').textContent=item.label;
  $('sample-counter').textContent=(selected+1)+' / '+items.length;
  $('download-png').href=item.url;$('download-png').download='captcha-'+item.id+'.png';$('download-png').classList.remove('disabled');
  [...$('gallery').children].forEach((button,index)=>{button.classList.toggle('selected',index===selected);button.setAttribute('aria-pressed',String(index===selected));});
  $('recognized').textContent=result ? (result.text||'(empty read)') : 'Select a sample, then run OCR.';
  $('verdict').className='verdict '+(result?(result.exact_match?'match':'miss'):'neutral');
  $('verdict').textContent=result?(result.exact_match?'EXACT MATCH':'NOT EXACT'):'NOT READ';
  $('timing').textContent=result ? 'floor+lex · '+(result.milliseconds/1000).toFixed(2)+' s' : 'Route: baseline → lex projection';
  $('raw-detail').hidden=!result;if(result)$('raw').textContent=result.raw_text||'(empty raw read)';
  controls();drawBoxes();
}
function gallery() {
  $('gallery').replaceChildren(...items.map((item,index)=>{
    const button=document.createElement('button');button.type='button';button.className='thumb';button.setAttribute('aria-label','Select sample '+(index+1)+': '+item.label);
    const image=document.createElement('img');image.src=item.url;image.alt='';
    const text=document.createElement('span');text.textContent=String(index+1).padStart(2,'0')+' · '+item.family;
    button.append(image,text);button.addEventListener('click',()=>{selected=index;display();});return button;
  }));$('batch-count').textContent=items.length;
}
async function generate() {
  if (generating||!health)return;
  generating=true;controls();notice('Generating a reproducible local batch…');
  try {
    const batch=await post('/api/generate',{family:$('family').value,severity:$('severity').value,seed:Number($('seed').value),count:Number($('count').value),text:$('custom-text').value});
    items=batch.items;selected=0;results=new Map();gallery();display();
    notice(items.length+' samples ready · seed '+batch.config.seed+' · '+batch.recipe+'. Export to keep images, exact labels and provenance.');
  } catch(error) {notice(error.message,true);} finally {generating=false;controls();}
}
function download(blob,name) {
  const url=URL.createObjectURL(blob), link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
}
$('generator-form').addEventListener('submit',e=>{e.preventDefault();generate();});
$('family').addEventListener('change',()=>severityOptions());
$('clear-text').addEventListener('click',()=>{$('custom-text').value='';});
$('new-seed').addEventListener('click',()=>{const n=new Uint32Array(1);crypto.getRandomValues(n);$('seed').value=n[0]%2147483648;generate();});
$('show-boxes').addEventListener('change',drawBoxes);window.addEventListener('resize',drawBoxes);
$('copy-label').addEventListener('click',async()=>{if(!items.length)return;try{await navigator.clipboard.writeText(items[selected].label);notice('Exact ground-truth label copied.');}catch(e){const range=document.createRange();range.selectNodeContents($('truth'));const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);notice('Label selected — press Ctrl+C / Cmd+C.');}});
$('export').addEventListener('click',async()=>{try{$('export').disabled=true;const blob=await post('/api/export',{ids:items.map(i=>i.id)},true);download(blob,'captcha-studio-seed-'+items[0].seed+'.zip');notice('Export prepared: PNGs, manifest.jsonl and provenance.json.');}catch(error){notice(error.message,true);}finally{controls();}});
$('read').addEventListener('click',async()=>{if(reading||!items.length)return;const item=items[selected];reading=true;controls();notice('Reading pixels only through the shipping route. First use loads templates and may take a minute…');try{const result=await post('/api/ocr',{id:item.id});results.set(item.id,result);display();notice(items[selected]&&items[selected].id===item.id ? 'OCR completed. '+(result.exact_match?'Exact case-sensitive match.':'The mismatch is kept visible; the reader is never given the label.')+' This sample is not an accuracy benchmark.' : 'OCR completed for an earlier sample; its result does not apply to the currently selected image.');}catch(error){notice(error.message,true);}finally{reading=false;controls();}});
(async()=>{try{const response=await fetch('/api/health');if(!response.ok)throw new Error('Local engine health check failed');health=await response.json();const b=health.build;$('build-info').textContent='Build '+b.revision+' · Python '+b.python+' · Pillow '+b.pillow+' · NumPy '+b.numpy+' · '+b.fonts+' bundled fonts. Studio recipe '+b.recipe+'.';$('app-download').hidden=!health.download_available;severityOptions('medium');await generate();}catch(error){notice(error.message,true);$('generate').disabled=true;$('new-seed').disabled=true;}})();
