const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = s => s == null ? 'Нет данных' : new Intl.NumberFormat('ru-RU', {minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(s));
const labels = {confirmed:'Подтверждено документами',mismatch:'Расхождение',unverified:'Не проверено',included:'Учтён',excluded:'Исключён',review:'Нужно уточнить',error:'Ошибка чтения'};
let current = null, selectedKey = null, selectedTerm = 0, polling = null;
async function api(url, data) {
  const response = await fetch(url, data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {});
  const body = await response.json(); if (!response.ok) throw Error(body.error || 'Ошибка запроса'); return body;
}
function error(message) { $('#error').hidden=false; $('#error').textContent=message; $('#error').scrollIntoView({block:'nearest'}); }
function show(section) { for (const id of ['start','loading','result']) $('#'+id).hidden=id!==section; $('#error').hidden=true; }
function asset(path) { return '/files/'+current.id+'/'+path.split('/').map(encodeURIComponent).join('/'); }
async function upload(file) {
  const bytes=new Uint8Array(await file.arrayBuffer()); if(bytes.length>20000000) throw Error('Один файл не должен превышать 20 МБ');
  let text=''; for(let i=0;i<bytes.length;i+=32768) text+=String.fromCharCode(...bytes.subarray(i,i+32768)); return {name:file.name,data:btoa(text)};
}
$('#report').addEventListener('change',()=>$('#reportHint').textContent=$('#report').files[0]?.name||'Выбери один файл');
$('#documents').addEventListener('change',()=>$('#docsHint').textContent=`Выбрано файлов: ${$('#documents').files.length}`);
$('#uploadForm').addEventListener('submit',async event=>{
  event.preventDefault(); $('#submit').disabled=true; $('#error').hidden=true;
  try {
    const report=await upload($('#report').files[0]), documents=await Promise.all([...$('#documents').files].map(upload));
    const response=await api('/api/cases',{report,documents,config:{target:$('#target').value,contract:$('#contract').value.trim()||null,start:$('#startDate').value,end:$('#endDate').value,incomplete_policy:$('#policy').value}});
    selectedKey=null; selectedTerm=0; location.hash=response.id; await openCase(response.id);
  } catch(e) { error(e.message); } finally { $('#submit').disabled=false; }
});
async function history() {
  try { const checks=await api('/api/cases'); $('#history').innerHTML=checks.length?checks.map(c=>`<button data-check="${c.id}">${esc(new Date(c.created).toLocaleString('ru-RU'))}<small>${esc(c.message)}</small></button>`).join(''):'<p class="muted">Пока нет сохранённых проверок.</p>';
    $('#history').querySelectorAll('[data-check]').forEach(b=>b.onclick=()=>{selectedKey=null;location.hash=b.dataset.check;openCase(b.dataset.check);});
  } catch(e) { error(e.message); }
}
async function openCase(id) {
  if(polling) clearTimeout(polling);
  try { current=await api('/api/cases/'+id);
    if(current.state==='failed') {show('start');error(current.message);return;}
    if(current.state!=='done') {show('loading');$('#progressText').textContent=current.message;polling=setTimeout(()=>openCase(id),1000);return;}
    render();
  } catch(e) {show('start');error(e.message);}
}
function render() {
  show('result');
  $('#exportHtml').href=`/api/cases/${current.id}/report`;$('#exportJson').href=`/api/cases/${current.id}/json`;
  BukhReport.render($('#reportHost'),current,{asset,decision:async(target,value)=>{
    current=await api(`/api/cases/${current.id}/decisions`,{target,value});return current;
  }});
}
$('#newCheck').onclick=()=>{selectedKey=null;selectedTerm=0;location.hash='';show('start');history();};
if(/^[a-f0-9]{32}$/.test(location.hash.slice(1)))openCase(location.hash.slice(1));else history();
