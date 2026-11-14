/* One result presentation for the live application and the standalone HTML export. */
(function(){
'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>{if(v==null)return 'Нет данных';let [a,b='']=String(v).split('.');return a.replace(/\B(?=(\d{3})+(?!\d))/g,'\u00a0')+','+b.padEnd(2,'0').slice(0,2);};
const names={5:'0200 · Затраты на оплату труда',10:'0300 · Страховые взносы',15:'0800 · Общепроизводственные затраты',16:'0900 · Общехозяйственные затраты',17:'Общий итог'};
const main=[5,10,15,16,17];
const sum=terms=>{if(!terms.length||terms.some(t=>t.value==null))return null;const cents=terms.reduce((a,t)=>{const [x,y='']=String(t.value).split('.');return a+BigInt(x.replace('-',''))*100n*(x.startsWith('-')?-1n:1n)+BigInt(y.padEnd(2,'0'))*(x.startsWith('-')?-1n:1n);},0n);const v=cents<0n?-cents:cents;return (cents<0n?'-':'')+(v/100n)+'.'+String(v%100n).padStart(2,'0');};
function label(row){if(row.key==='combined:13,14'&&row.expected==null)return 'Недостаточно подтверждающих документов';return row.status==='confirmed'?(row.source_label==='Расчёт'?'Арифметика верна':'Подтверждено'):row.status==='mismatch'?(row.source_label==='Расчёт'?'Ошибка арифметики':'Расхождение'):row.requires_review?'Подтвердите число':row.expected==null?'Недостаточно данных':'Не проверено';}
function explanation(row,r){
 if(row.status==='unverified')return [...new Set(row.reasons)].join('; ');
 if(row.column===17){const roots=r.rows.filter(v=>[5,10,15,16].includes(v.column)&&v.status==='mismatch');if(roots.length===1&&roots[0].delta===row.delta)return `Расхождение относится к статье ${names[roots[0].column].slice(0,4)} и учтено один раз.`;return row.status==='confirmed'?'Общая сумма совпадает с суммой четырёх статей по документам. Отдельные статьи и их разбивка проверяются самостоятельно.':'Итог не совпадает с суммой статей по документам. См. расшифровки статей и арифметическую проверку.';}
 if(row.status==='mismatch')return `В КФЗ на ${fmt(String(row.delta).replace('-',''))} руб. ${String(row.delta).startsWith('-')?'меньше':'больше'}, чем подтверждено документами по этой статье.`;
 if(row.column===5)return `Начисления по ${row.terms.length} ведомостям совпадают с КФЗ. Зарплата и резерв учтены вместе.`;
 if(row.column===10)return `Сумма ${row.terms.length} расчетов страховых взносов совпадает с КФЗ.`;
 if(row.column===16)return 'Сумма включённых документов совпадает с КФЗ. Исключения перечислены ниже.';
 return row.reasons.join('; ');
}
function render(host,data,options={}){
 const same=host.dataset.case===data.id, opened=same?[...host.querySelectorAll('details[data-state][open]')].map(d=>d.dataset.state):[];
 const scroll=window.scrollY;host.dataset.case=data.id;let r=data.result;
 const asset=options.asset||(()=>''),q=s=>host.querySelector(s),docs=new Map(r.documents.map(d=>[d.id,d])),cols=new Map(r.columns.map(c=>[c.number,c]));
 const all=[...r.rows,...r.arithmetic],rows=new Map(all.map(v=>[v.key,v]));
 const badge=row=>`<span class="status ${row.status}">${esc(label(row))}</span>`;
 function terms(row){
  if(row.column===17){return `<ul class="articles">${main.slice(0,4).map(n=>{const v=r.rows.find(x=>x.column===n);return `<li><a href="#check-kfz-${n}" data-article="${n}">${esc(names[n])}</a><span class="num">${fmt(v.expected)} руб.</span></li>`;}).join('')}</ul><div class="source-total">Ожидаемый итог по документам <strong>${fmt(row.expected)} руб.</strong></div>`;}
  const total=sum(row.terms);
  return `<ul class="documents">${row.terms.map((t,i)=>`<li><span class="doc-name">${esc(t.label)}<small>${esc(t.locator||'')}</small></span><span class="num">${fmt(t.value)}</span><button class="link" data-view="${esc(row.key)}" data-term="${i}">Показать подтверждающий фрагмент</button></li>`).join('')}</ul>${!row.terms.length?'<p class="partial-warning">Нет включённых подтверждающих значений для этого показателя.</p>':`<div class="source-total">Сумма включённых значений <strong>${fmt(total)} руб.</strong></div>`}${row.expected==null?'<p class="partial-warning">Полная ожидаемая сумма не установлена. Причина указана в пояснении; отсутствующее значение не считается нулём.</p>':''}`;
 }
 const mainRows=main.map(n=>r.rows.find(v=>v.column===n)).filter(Boolean);
 let html=`<div class="report-head"><h1>Результат проверки КФЗ</h1>${options.readonly?'<span class="export-notice">Сохранённый HTML-отчёт</span>':''}</div><p class="meta">Договор ${esc(r.config.contract||'не определён')} · ${esc(r.config.target)} · ${esc(date(r.config.start))} — ${esc(date(r.config.end))} · суммы в рублях</p><div class="table-container"><table><thead><tr><th>Показатель КФЗ</th><th class="num">Значение в КФЗ</th><th class="num">Ожидаемое<br>по документам</th><th class="num">Расхождение</th><th>Статус</th><th>Пояснение</th></tr></thead><tbody>`;
 for(const row of mainRows){html+=`<tr id="check-kfz-${row.column}" class="main-row ${row.column===17?'total-row':''}"><th scope="row">${esc(names[row.column])}<br><button class="link" data-kfz="${esc(row.key)}">${row.requires_review?'Уточнить число КФЗ':'Показать значение в КФЗ'}</button></th><td class="num">${fmt(row.reported)}</td><td class="num">${fmt(row.expected)}</td><td class="num ${row.status==='mismatch'?'difference':''}">${fmt(row.delta)}</td><td>${badge(row)}</td><td class="explanation">${esc(explanation(row,r))}</td></tr><tr class="details-row"><td colspan="6"><details data-state="sources:${esc(row.key)}"><summary>${row.column===17?'Состав общего итога — 4 статьи':`Первичные и расчетные документы — ${row.terms.length}`}</summary>${terms(row)}</details></td></tr>`;}
 html+='</tbody></table></div><p class="footnote">Расхождение = значение КФЗ − ожидаемое по документам. Подтверждение общей суммы не подтверждает каждую внутреннюю составляющую.</p>';
 const excluded=r.documents.filter(d=>d.state==='excluded');html+=`<section class="section"><h2>Исключённые документы</h2><ul class="excluded">${excluded.length?excluded.map(d=>`<li><span>${esc(d.name)}</span><span class="excluded-reason">${esc(d.excluded_reason||'Не является расчетным документом')}</span></li>`).join(''):'<li>Исключённых документов нет.</li>'}</ul></section>`;
 const unknown=r.rows.filter(v=>v.status==='unverified'&&v.key!=='combined:5,10,15,16');
 const review=r.documents.filter(d=>['review','error'].includes(d.state));
 html+=`<section class="section"><h2>Требуется дополнительная проверка</h2><ul class="limits">${unknown.map(v=>`<li><b>${esc(v.name)}.</b> ${esc(v.reasons.join('; '))} <button class="link" data-kfz="${esc(v.key)}">Показать КФЗ</button></li>`).join('')}${review.map(d=>`<li><b>${esc(d.name)}.</b> ${esc(d.error||d.review_reasons?.join('; '))}${!d.error?` <button class="link" data-doc="${d.id}">Показать и уточнить</button>`:''}</li>`).join('')}${!unknown.length&&!review.length?'<li>Открытых вопросов нет в пределах этой проверки.</li>':''}</ul>`;
 html+=`<details class="advanced" data-state="details"><summary>Подробные показатели КФЗ</summary><div class="details-list">${r.rows.filter(v=>!main.includes(v.column)&&v.key!=='combined:5,10,15,16').map(v=>`<details class="detail-item" data-state="detail:${esc(v.key)}"><summary><span>${esc(v.name)}</span><span>КФЗ: ${fmt(v.reported)} · ожидаемое: ${fmt(v.expected)} · разница: ${fmt(v.delta)}</span>${badge(v)}</summary><p class="explain">${esc(v.reasons.join('; '))}</p><button class="link" data-kfz="${esc(v.key)}">Показать значение в КФЗ</button>${terms(v)}</details>`).join('')}</div></details>`;
 html+=`<details class="advanced" data-state="arithmetic"><summary>Арифметика КФЗ — ${r.arithmetic.length} проверок</summary><p class="explain">Источник: Расчёт. Проверяется сложение в отчёте. Успешная арифметика не подтверждает сумму документами.</p><ul class="formula-list">${r.arithmetic.map(v=>`<li id="check-arithmetic-${v.column}"><button class="link" data-kfz="${esc(v.key)}">Столбцы ${esc(v.formula)}</button><span>${esc(v.formula_values)}<br><small>${esc(v.reasons.join('; '))}</small></span>${badge(v)}</li>`).join('')}</ul></details></section>`;
 html+=`<section class="section conclusion"><h2>Итоговое заключение</h2><p><strong>${esc(r.conclusion.title)}</strong></p><p>${esc(r.conclusion.text)}</p><p class="note">Статей с расхождениями: ${r.summary.mismatch}. Ошибок арифметики: ${r.summary.arithmetic_mismatch}. Переход расхождения статьи в общий итог не считается повторной ошибкой.</p></section>`;
 html+=`<details class="section" data-state="documents"><summary>Документы комплекта — ${r.documents.length}</summary><ul class="excluded">${r.documents.map(d=>`<li><span>${esc(d.name)}</span><span>${esc({included:'Учтён',excluded:'Исключён',review:'Нужно уточнить',error:'Ошибка чтения'}[d.state]||d.state)} ${d.role==='primary'&&!d.error?`<button class="link" data-doc="${d.id}">Показать и уточнить</button>`:''}</span></li>`).join('')}</ul></details>`;
 html+=`<details class="section" data-state="audit"><summary>История пользовательских уточнений — ${r.decisions.length}</summary><div class="audit-list">${r.decisions.map(d=>`<p>${esc(d.created)} · ${esc(d.target)} → ${esc(d.value)} ${esc(d.note||'')}</p>`).join('')||'<p>Уточнений пока нет.</p>'}</div></details><dialog class="result-viewer"><div class="viewer-head"><h2></h2><button class="close">Закрыть и вернуться к таблице</button></div><div class="viewer-body"></div></dialog>`;
 host.innerHTML=html;opened.forEach(key=>{const d=[...host.querySelectorAll('[data-state]')].find(x=>x.dataset.state===key);if(d)d.open=true;});
 const viewer=q('dialog'),body=q('.viewer-body');let context=null;
 q('.close').onclick=()=>viewer.close();
 host.querySelectorAll('[data-article]').forEach(a=>a.onclick=()=>{const row=q('#check-kfz-'+a.dataset.article);row.nextElementSibling.querySelector('details').open=true;});
 host.querySelectorAll('[data-kfz]').forEach(b=>b.onclick=()=>open({row:b.dataset.kfz,selection:'kfz:'+rows.get(b.dataset.kfz).columns[0]}));
 host.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>open({row:b.dataset.view,selection:'doc:'+b.dataset.term}));
 host.querySelectorAll('[data-doc]').forEach(b=>b.onclick=()=>open({doc:b.dataset.doc,selection:'document'}));
 function reportView(numbers){return r.report_views?.[numbers[0]]||{kind:'image',image:r.report_source.image,highlights:numbers.map(n=>cols.get(n)?.source_bbox).filter(Boolean)};}
 function open(ctx){
  context=ctx;const row=rows.get(ctx.row),doc=docs.get(ctx.doc);
  const choices=row?[...row.columns.map(n=>({id:'kfz:'+n,label:'Значение КФЗ: столбец '+n})),...(row.column===17&&row.source_label!=='Расчёт'?[]:row.terms).map((t,i)=>({id:row.source_label==='Расчёт'?'kfz:'+t.column:'doc:'+i,label:row.source_label==='Расчёт'?'Слагаемое: столбец '+t.column:t.label+' — '+fmt(t.value)}))]:[{id:'document',label:doc.name}];
  q('.viewer-head h2').textContent=row?(names[row.column]||row.name):doc.name;
  body.innerHTML=`${row?`<p class="fragment-meta">КФЗ: <strong>${fmt(row.reported)}</strong> · ожидаемое: <strong>${fmt(row.expected)}</strong> · расхождение: <strong>${fmt(row.delta)}</strong> ${badge(row)}</p><p class="explain">${esc(row.reasons.join('; '))}</p>`:''}<label>Источник фрагмента<select class="doc-input">${choices.map(c=>`<option value="${esc(c.id)}" ${c.id===ctx.selection?'selected':''}>${esc(c.label)}</option>`).join('')}</select></label><div class="selected-fragment"></div><div class="viewer-error" hidden></div>`;
  if(!viewer.open)viewer.showModal();viewer.scrollTop=0;body.querySelector('select').onchange=e=>open({...ctx,selection:e.target.value});
  const out=body.querySelector('.selected-fragment');
  if(ctx.selection.startsWith('kfz:')){
   const n=Number(ctx.selection.split(':')[1]),c=cols.get(n);
   out.innerHTML=`<p>Строка «${esc(r.config.target)}» · столбец ${n}: ${esc(c.name)} · <b>${fmt(c.effective_value)}</b></p><div class="preview"></div><div class="correction"></div>`;
   mountPreview(out.querySelector('.preview'),reportView([n]),asset);const control=out.querySelector('.correction');
   control.innerHTML=`${c.reading_reasons.length?`<p>${esc(c.reading_reasons.join('; '))}.</p>`:''}<p class="explain">Значение в отчёте: ${esc(c.raw_text||'не определено')}. Для сверки используется: ${fmt(c.effective_value)}.</p>${options.readonly?'<p>Подтвердить или исправить значение можно в приложении.</p>':`<label>Значение в выделенном поле КФЗ<input inputmode="decimal" value="${esc(c.effective_value??'')}"></label><button>Подтвердить значение</button><p class="explain">Сравни число с выделенным полем отчёта. После подтверждения или исправления результаты пересчитаются.</p>`}`;
   if(!options.readonly)control.querySelector('button').onclick=()=>save('kfz:'+n,control.querySelector('input').value);
  }else{
   const term=row?.terms[Number(ctx.selection.split(':')[1])],d=doc||docs.get(term.document_id),view=d.views?.[term?.component||'total'];
   out.innerHTML=`<p class="source-name">${esc(d.name)}</p><p>Включённое значение: <b>${fmt(term?term.value:d.effective_amount)} руб.</b></p><p class="locator">${esc(term?.locator||d.locator||'')}</p>${d.amount_decision?'<p class="explain">Сумма уточнена пользователем; источник показывает исходное значение.</p>':''}<div class="preview"></div>`;
   mountPreview(out.querySelector('.preview'),view,asset);
   if(!options.readonly&&d.role==='primary'&&!d.error){
    const edit=document.createElement('details');edit.className='correction';edit.innerHTML=`<summary>Уточнить реквизиты или назначение документа</summary><select class="doc-field"><option value="article">Статья расходов</option><option value="amount">Сумма документа</option><option value="date">Дата / начало месяца</option><option value="contract">Договор</option></select><div class="doc-value"></div><button>Сохранить решение</button>`;out.append(edit);
    const update=()=>{const field=edit.querySelector('select').value;edit.querySelector('.doc-value').innerHTML=field==='article'?`<select class="doc-input"><option value="">Выбери статью</option>${Object.entries({'0200':'Оплата труда','0300':'Страховые взносы','0800':'Общепроизводственные','0900':'Общехозяйственные'}).map(([v,t])=>`<option value="${v}" ${d.effective_article===v?'selected':''}>${v} · ${t}</option>`).join('')}</select>`:`<input class="doc-input" type="${field==='date'?'date':'text'}" value="${esc(d['effective_'+field]??'')}">`;};edit.querySelector('select').onchange=update;update();edit.querySelector('button').onclick=()=>save(`doc:${d.id}:${edit.querySelector('select').value}`,edit.querySelector('.doc-value .doc-input').value);
   }
  }
 }
 async function save(target,value){try{const next=await options.decision(target,value);render(host,next,{...options,reopen:context});}catch(e){const box=q('.viewer-error');box.hidden=false;box.textContent=e.message;}}
 if(same)window.scrollTo(0,scroll);if(options.reopen)open(options.reopen);
}
function date(v){return /^\d{4}-\d{2}-\d{2}$/.test(v||'')?v.split('-').reverse().join('.'):v;}
function mountPreview(el,view,asset) {
  if(!view) {el.innerHTML='<p class="muted">Точный фрагмент для этого слагаемого недоступен. Нельзя подменять его общей суммой документа.</p>';return;}
  let mode='fragment',zoom=1;
  el.innerHTML='<div class="preview-tools"><button class="secondary" data-mode="fragment">Фрагмент</button><button class="secondary" data-mode="context">Контекст</button><button class="secondary" data-zoom="out" aria-label="Уменьшить">−</button><button class="secondary" data-zoom="in" aria-label="Увеличить">+</button><span class="zoom-label"></span></div><div class="preview-viewport" tabindex="0"></div>';
  const viewport=el.querySelector('.preview-viewport');
  const draw=()=>{
    el.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));el.querySelector('.zoom-label').textContent=`${Math.round(zoom*100)}%`;
    if(view.kind==='image') {
      viewport.innerHTML=`<div class="image-stage"><img alt="Документ с выделенным проверяемым фрагментом" src="${asset(view.image)}">${(view.header_highlights||[]).map((b,i)=>`<span class="image-header-highlight" data-header-highlight="${i}" aria-label="Заголовок выбранного поля"></span>`).join('')}${(view.highlights||[]).map((b,i)=>`<span class="image-highlight" data-highlight="${i}" aria-label="Проверяемое значение"></span>`).join('')}</div>`;
      const img=viewport.querySelector('img'),stage=viewport.querySelector('.image-stage');
      img.onload=()=>{
        const w=img.naturalWidth,h=img.naturalHeight,boxes=view.highlights||[];
        const bounds=mode==='fragment'&&view.focus_bbox?view.focus_bbox:boxes.length?[Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))]:[0,0,w,h];
        const framed=mode==='fragment'&&view.focus_bbox;
        const region=mode==='fragment'?Math.min(w,bounds[2]-bounds[0]+(framed?0:120)):w;
        const widthScale=(viewport.clientWidth-24)/region;
        const scale=Math.max(0.1,framed?Math.min(widthScale,(viewport.clientHeight-24)/(bounds[3]-bounds[1])):widthScale)*zoom;
        stage.style.width=`${w*scale}px`;stage.style.height=`${h*scale}px`;
        stage.querySelectorAll('.image-highlight').forEach((mark,i)=>{const b=boxes[i];mark.style.left=`${b[0]/w*100}%`;mark.style.top=`${b[1]/h*100}%`;mark.style.width=`${(b[2]-b[0])/w*100}%`;mark.style.height=`${(b[3]-b[1])/h*100}%`;});
        stage.querySelectorAll('.image-header-highlight').forEach((mark,i)=>{const b=view.header_highlights[i];mark.style.left=`${b[0]/w*100}%`;mark.style.top=`${b[1]/h*100}%`;mark.style.width=`${(b[2]-b[0])/w*100}%`;mark.style.height=`${(b[3]-b[1])/h*100}%`;});
        viewport.scrollLeft=Math.max(0,(bounds[0]+bounds[2])/2*scale-viewport.clientWidth/2);
        viewport.scrollTop=mode==='fragment'?Math.max(0,(bounds[1]+bounds[3])/2*scale-viewport.clientHeight/2):0;
      };
    } else if(view.kind==='workbook') {
      viewport.innerHTML=view.sheets.map(sheet=>{
        const highlights=view.highlights.filter(c=>c.sheet===sheet.name),addresses=new Set(highlights.map(c=>c.address));
        if(mode==='fragment'&&!highlights.length)return '';
        const selectedRows=highlights.map(c=>Number(c.address.match(/\d+/)[0]));
        const rows=sheet.rows.filter(row=>mode==='context'||selectedRows.some(n=>Math.abs(n-row.row)<=1));
        return `<div class="sheet" style="font-size:${13*zoom}px"><h4>Лист «${esc(sheet.name)}»</h4><table>${rows.map(row=>`<tr><th>${row.row}</th>${row.cells.map(c=>`<td data-cell="${esc(sheet.name)}!${c.address}" class="${addresses.has(c.address)?'cell-highlight':''}"><small>${c.address}</small>${esc(c.text)}</td>`).join('')}</tr>`).join('')}</table></div>`;
      }).join('');
      viewport.querySelector('.cell-highlight')?.scrollIntoView({block:'nearest',inline:'nearest'});
    } else if(view.kind==='document') {
      const p=para=>`<p data-paragraph="${para.number}" class="${para.number===view.paragraph?'paragraph-highlight':''}"><small>Абзац ${para.number}</small>${highlightText(para.text,para.number===view.paragraph?view.highlight_text:null)}</p>`;
      viewport.innerHTML=`<div class="word-document" style="font-size:${15*zoom}px">${view.blocks.map(block=>{
        if(block.kind==='paragraph')return mode==='context'||Math.abs(block.number-(view.paragraph||1))<=1?p(block):'';
        const relevant=block.rows.some(row=>row.some(cell=>cell.some(para=>para.number===view.paragraph)));
        return mode==='context'||relevant?`<h4>Таблица ${block.number}</h4><table>${block.rows.map(row=>`<tr>${row.map(cell=>`<td>${cell.map(p).join('')}</td>`).join('')}</tr>`).join('')}</table>`:'';
      }).join('')}</div>`;
    }
  };
  el.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;zoom=1;draw();});
  el.querySelectorAll('[data-zoom]').forEach(b=>b.onclick=()=>{zoom=Math.min(4,Math.max(.5,zoom*(b.dataset.zoom==='in'?1.25:.8)));draw();});draw();
}
function highlightText(text,needle) { if(!needle||!text.includes(needle))return esc(text);const i=text.indexOf(needle);return esc(text.slice(0,i))+'<mark>'+esc(needle)+'</mark>'+esc(text.slice(i+needle.length)); }

window.BukhReport={render};
})();
