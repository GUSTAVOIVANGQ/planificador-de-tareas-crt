'use strict';
/* Interfaz local: la clasificación LFPA se obtiene únicamente del motor Python. */
const $ = id => document.getElementById(id);
const LFPA_LINK = 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPA.pdf';
const DOW = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const STATES = {pendiente:'Pendiente', en_proceso:'En proceso', concluida:'Concluida', cancelada:'Cancelada'};
const dateNow = new Date();
const localToday = `${dateNow.getFullYear()}-${String(dateNow.getMonth()+1).padStart(2,'0')}-${String(dateNow.getDate()).padStart(2,'0')}`;
const state = {year:dateNow.getFullYear(), month:dateNow.getMonth()+1, selected:localToday, days:[], tasks:[], exceptions:[], editing:null};
const pad = n => String(n).padStart(2,'0');
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = date => {
  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return '—';
  const [y,m,d] = date.split('-').map(Number);
  return new Date(y,m-1,d).toLocaleDateString('es-MX',{day:'numeric',month:'long',year:'numeric'});
};
const fmtShort = date => {
  if (!date) return '—';
  const [y,m,d] = date.split('-').map(Number);
  return new Date(y,m-1,d).toLocaleDateString('es-MX',{day:'numeric',month:'short',year:'numeric'});
};
const sameMonth = date => date && date.slice(0,7) === `${state.year}-${pad(state.month)}`;
const api = async (url, options={}) => {
  let response;
  try { response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options}); }
  catch { throw new Error('No se pudo conectar al servidor local. Inícialo con INICIAR_WINDOWS.bat o python server.py.'); }
  let payload;
  try { payload = await response.json(); }
  catch { throw new Error('El servidor devolvió una respuesta inesperada.'); }
  if(!response.ok) throw new Error(payload.error || 'Error en la solicitud');
  return payload;
};
let msgTimer;
function toast(message, error=false) {
  const node = $('globalMessage');
  node.textContent=message; node.hidden=false; node.classList.toggle('error',error);
  clearTimeout(msgTimer); msgTimer=setTimeout(()=>{node.hidden=true},6500);
}
const getDay = date => state.days.find(d=>d.fecha===date);
function classify(day) {
  if(day.clasificacion==='INHABIL_ADICIONAL_VALIDADO'||day.clasificacion==='HABILITADO_EXCEPCIONALMENTE') return 'custom';
  if(day.clasificacion==='INHABIL_LFPA') return 'official';
  if(day.clasificacion==='INHABIL_FIN_DE_SEMANA') return 'weekend';
  return 'work';
}
async function refreshMonth() {
  const yy=state.year, mm=state.month;
  const [month,year]=await Promise.all([
    api(`/api/month?year=${yy}&month=${mm}`), api(`/api/year?year=${yy}`)
  ]);
  if(yy!==state.year||mm!==state.month) return;
  state.days=month.dias;
  $('statOff').textContent=year.inhabiles;
  $('statWork').textContent=year.habiles;
  $('statYear').textContent=yy;
  $('holidayYear').textContent=yy;
  $('holidayList').innerHTML=year.festivos.length?year.festivos.map(d=>`<div class="holiday-row"><span>${esc(fmtShort(d.fecha))}</span><strong>${esc(d.motivo)}</strong><a href="${esc(d.fuenteUrl)}" target="_blank" rel="noopener noreferrer" aria-label="Fundamento de ${esc(d.fecha)}">↗</a></div>`).join(''):'<div class="empty">No hay fechas específicas registradas.</div>';
  $('calendarHeading').textContent=new Date(yy,mm-1,1).toLocaleDateString('es-MX',{month:'long',year:'numeric'});
  renderCalendar(); updateDay();
}
function renderCalendar(){
  const start = (new Date(state.year,state.month-1,1).getDay()+6)%7;
  let html = DOW.map(w=>`<div class="weekday">${w}</div>`).join('');
  for(let i=0;i<start;i++) html+='<div aria-hidden="true"></div>';
  for(const day of state.days){
    const number=Number(day.fecha.slice(-2));
    const tasks=state.tasks.filter(t=>t.fecha_vencimiento===day.fecha && t.estado!=='cancelada');
    const cl=classify(day);
    const selected=state.selected===day.fecha ? ' selected':'';
    const today=localToday===day.fecha ? ' today':'';
    html+=`<button type="button" class="datecell ${cl}${selected}${today}" data-date="${day.fecha}" aria-pressed="${selected?'true':'false'}" title="${esc(day.fecha+' · '+day.motivo)}"><span class="dayno">${number}</span><span class="date-bottom">${day.habil?'': '<span class="dot"></span>'}${tasks.length?`<span class="task-badge">${tasks.length}</span>`:''}</span></button>`;
  }
  $('calendar').innerHTML=html;
}
async function updateDay(){
  const selected=state.selected;
  $('dayHeading').textContent=fmt(selected);
  let day=getDay(selected);
  if(!day){
    try { day=await api(`/api/day?date=${selected}`); }
    catch(e){toast(e.message,true);return;}
  }
  if(selected!==state.selected) return;
  let cls=day.habil?'habil':'inhabil';
  if(['INHABIL_ADICIONAL_VALIDADO','HABILITADO_EXCEPCIONALMENTE'].includes(day.clasificacion)) cls='exception';
  $('dateResult').className='result '+cls;
  $('resultStatus').textContent=day.habil?'DÍA HÁBIL — BASE LFPA':'DÍA INHÁBIL — BASE LFPA';
  if(cls==='exception') $('resultStatus').textContent=day.habil?'HABILITACIÓN REGISTRADA':'INHÁBIL ADICIONAL REGISTRADO';
  $('resultDetail').textContent=day.motivo;
  $('resultNext').textContent=day.fundamento+(day.habil?' · Sujeto a acuerdos adicionales y reglas especiales.':'');
  $('resultSources').innerHTML=`<a href="${esc(day.fuenteUrl)}" target="_blank" rel="noopener noreferrer">Consultar fundamento oficial ↗</a>`;
  const tasks=state.tasks.filter(t=>t.fecha_vencimiento===selected && t.estado!=='cancelada');
  $('dayTasks').innerHTML=tasks.length ? tasks.map(t=>`<div class="daytask"><div><strong>${esc(t.titulo)}</strong><small>${esc(t.responsable || (t.tipo==='plazo_lfpa'?'Plazo LFPA':'Actividad interna'))} · ${esc(STATES[t.estado])}</small></div><button class="btn tiny outline" data-edit="${t.id}" type="button">Editar</button></div>`).join('') : '<div class="empty small-empty">No hay tareas que venzan en esta fecha.</div>';
}
async function changeMonth(delta){
  const d=new Date(state.year,state.month-1+delta,1);
  state.year=d.getFullYear();state.month=d.getMonth()+1;
  state.selected=`${state.year}-${pad(state.month)}-01`;
  try{await refreshMonth();}catch(e){toast(e.message,true)}
}
function chooseDate(date){
  state.selected=date;
  if(!sameMonth(date)){const [y,m]=date.split('-').map(Number);state.year=y;state.month=m;refreshMonth().catch(e=>toast(e.message,true));}
  else {renderCalendar();updateDay()}
}
async function reloadAll(){
  const [taskData,excData]=await Promise.all([api('/api/tasks'),api('/api/exceptions')]);
  state.tasks=taskData.tareas;state.exceptions=excData.excepciones;
  renderMetrics();renderTasks();renderExceptions();await refreshMonth();
}
function renderMetrics(){
  const pending=state.tasks.filter(t=>t.estado==='pendiente'||t.estado==='en_proceso');
  $('metricTotal').textContent=state.tasks.length;
  $('metricPending').textContent=pending.length;
  $('metricOverdue').textContent=pending.filter(t=>t.fecha_vencimiento<localToday).length;
  $('metricReview').textContent=state.tasks.filter(t=>t.necesita_revision).length;
}
function renderTasks(){
  const search=$('searchTask').value.trim().toLowerCase();
  const st=$('filterStatus').value, ty=$('filterType').value;
  const arr=state.tasks.filter(t=> (st==='todos'||t.estado===st) && (ty==='todos'||t.tipo===ty) && [t.titulo,t.responsable,t.area].join(' ').toLowerCase().includes(search));
  $('taskCountLabel').textContent=`${arr.length} de ${state.tasks.length} tareas`;
  if(!arr.length){$('taskRows').innerHTML='<tr><td class="empty" colspan="6">No hay tareas con estos filtros. Pulsa «Nueva tarea» para empezar.</td></tr>';return;}
  $('taskRows').innerHTML=arr.map(t=>{
    const overdue=(t.estado==='pendiente'||t.estado==='en_proceso') && t.fecha_vencimiento<localToday;
    return `<tr>
     <td><strong>${esc(t.titulo)}</strong><small>${esc(t.area||'Sin área')}${t.prioridad==='alta'?' · Prioridad alta':''}</small></td>
     <td>${esc(t.responsable||'Por asignar')}</td>
     <td><b>${esc(fmtShort(t.fecha_vencimiento))}</b>${overdue?'<small class="warn">Vencida</small>':''}${t.necesita_revision?`<small class="warn">Revisar: ${esc(fmtShort(t.fecha_sugerida))}</small>`:''}</td>
     <td><span class="type-pill ${t.tipo==='plazo_lfpa'?'legal':''}">${t.tipo==='plazo_lfpa'?'Plazo LFPA':'Interna'}</span></td>
     <td><span class="status-badge ${esc(t.estado)}">${esc(STATES[t.estado])}</span></td>
     <td><div class="actionbar"><button type="button" class="btn tiny outline" data-edit="${t.id}">Editar</button>${t.necesita_revision?`<button type="button" class="btn tiny secondary" data-recalc="${t.id}" title="Aprobar el cambio de fecha propuesto">Aplicar fecha</button>`:''}<button type="button" class="btn tiny danger" data-delete="${t.id}">Eliminar</button></div></td>
    </tr>`;
  }).join('');
}
function renderExceptions(){
  $('exceptionList').innerHTML=state.exceptions.length ? state.exceptions.map(x=>`<div class="entry"><div><strong>${esc(fmtShort(x.fecha))} · ${x.tipo==='inhabil'?'Inhábil adicional':'Fecha habilitada'}</strong><div>${esc(x.motivo)}</div><small><a href="${esc(x.fuenteUrl)}" target="_blank" rel="noopener noreferrer">Fundamento oficial ↗</a></small></div><div class="entry-actions"><button type="button" class="btn tiny danger" data-exc-delete="${x.id}">Quitar</button></div></div>`).join('') : '<div class="empty">No hay excepciones. Se aplica únicamente la LFPA base.</div>';
}
function openTask(t=null,preDate=state.selected){
  state.editing=t?.id||null;
  $('dialogTitle').textContent=t?'Editar tarea':'Nueva tarea';
  $('taskTitle').value=t?.titulo||'';
  $('taskType').value=t?.tipo||'interna';
  $('taskPriority').value=t?.prioridad||'media';
  $('taskOwner').value=t?.responsable||'';
  $('taskArea').value=t?.area||'';
  $('taskStart').value=t?.fecha_inicio||preDate;
  $('taskDue').value=t?.fecha_vencimiento||preDate;
  $('taskDays').value=t?.dias_habiles||10;
  $('taskStatus').value=t?.estado||'pendiente';
  $('taskDetail').value=t?.detalle||'';
  switchType();
  $('taskDialog').showModal();
  $('taskTitle').focus();
}
function switchType(){
  const legal=$('taskType').value==='plazo_lfpa';
  $('daysBox').hidden=!legal; $('dueBox').hidden=legal;
  $('taskDue').required=!legal; $('taskDays').required=legal;
  $('dueNotice').textContent=legal
    ? 'El vencimiento se calculará desde el día siguiente al inicio según la LFPA. Revisa si el procedimiento tiene reglas especiales.'
    : 'La fecha de una actividad interna se conserva aunque caiga en día inhábil para plazos administrativos.';
}
async function saveTask(e){
  e.preventDefault();
  const legal=$('taskType').value==='plazo_lfpa';
  const data={titulo:$('taskTitle').value,responsable:$('taskOwner').value,area:$('taskArea').value,
    tipo:$('taskType').value,prioridad:$('taskPriority').value,estado:$('taskStatus').value,
    fecha_inicio:$('taskStart').value,detalle:$('taskDetail').value,
    ...(legal?{dias_habiles:Number($('taskDays').value)}:{fecha_vencimiento:$('taskDue').value})};
  const id=state.editing;
  try{
    await api(id?`/api/tasks/${id}`:'/api/tasks', {method:id?'PUT':'POST',body:JSON.stringify(data)});
    $('taskDialog').close();toast(id?'Tarea actualizada.':'Tarea creada correctamente.');
    await reloadAll();
  }catch(e){toast(e.message,true)}
}
async function deleteTask(id){
  const t=state.tasks.find(t=>t.id===id);
  if(!t||!confirm(`¿Eliminar la tarea «${t.titulo}»?`))return;
  try{await api(`/api/tasks/${id}`,{method:'DELETE'});toast('Tarea eliminada.');await reloadAll()}catch(e){toast(e.message,true)}
}
async function applyRecalc(id){
  const t=state.tasks.find(t=>t.id===id);
  if(!t||!t.necesita_revision)return;
  if(!confirm(`La fecha actual es ${fmtShort(t.fecha_vencimiento)}. El calendario propone ${fmtShort(t.fecha_sugerida)}. ¿Aprobar y actualizar?`))return;
  try{await api(`/api/tasks/${id}/recalculate`,{method:'POST',body:'{}'});toast('Nueva fecha aprobada y registrada en auditoría.');await reloadAll()}catch(e){toast(e.message,true)}
}
async function calculate(e){
  e.preventDefault();
  try{
    const result=await api(`/api/calculate?start=${encodeURIComponent($('startDate').value)}&days=${encodeURIComponent($('daysCount').value)}`);
    $('calcOutput').classList.add('visible');
    $('calcOutput').innerHTML=`<span class="small">Vencimiento estimado · ${result.dias_habiles} días hábiles</span><div class="big-date">${esc(fmt(result.vencimiento))}</div><div class="small">${esc(result.regla)}</div><button class="btn tiny secondary" id="goCalculated" data-date="${result.vencimiento}" type="button" style="margin-top:10px">Ver en calendario ↗</button>`;
  }catch(e){toast(e.message,true)}
}
async function addException(e){
  e.preventDefault();
  const data={fecha:$('exceptionDate').value,tipo:$('exceptionType').value,motivo:$('exceptionReason').value,
    fuenteUrl:$('exceptionSource').value,confirmado:$('exceptionConfirm').checked};
  try{
    await api('/api/exceptions',{method:'POST',body:JSON.stringify(data)});
    $('exceptionForm').reset();toast('Excepción agregada; revisa las tareas que requieren recálculo.');await reloadAll();
  }catch(e){toast(e.message,true)}
}
async function removeException(id){
  if(!confirm('¿Quitar esta excepción? Las tareas con plazo podrían requerir recálculo.'))return;
  try{await api(`/api/exceptions/${id}`,{method:'DELETE'});toast('Excepción retirada.');await reloadAll();}catch(e){toast(e.message,true)}
}
function bind(){
  $('prevMonth').addEventListener('click',()=>changeMonth(-1));
  $('nextMonth').addEventListener('click',()=>changeMonth(1));
  $('currentMonth').addEventListener('click',()=>chooseDate(localToday));
  $('calendar').addEventListener('click',e=>{const el=e.target.closest('[data-date]');if(el)chooseDate(el.dataset.date)});
  $('newTask').addEventListener('click',()=>openTask(null,localToday));
  $('newTaskTop').addEventListener('click',()=>openTask(null,localToday));
  $('addForDay').addEventListener('click',()=>openTask(null,state.selected));
  $('taskType').addEventListener('change',switchType);
  $('taskForm').addEventListener('submit',saveTask);
  $('closeDialog').addEventListener('click',()=>$('taskDialog').close());
  $('cancelDialog').addEventListener('click',()=>$('taskDialog').close());
  $('taskDialog').addEventListener('click',e=>{if(e.target===$('taskDialog'))$('taskDialog').close()});
  $('calcForm').addEventListener('submit',calculate);
  $('calcOutput').addEventListener('click',e=>{const el=e.target.closest('#goCalculated');if(el)chooseDate(el.dataset.date)});
  $('searchTask').addEventListener('input',renderTasks);
  $('filterStatus').addEventListener('change',renderTasks);
  $('filterType').addEventListener('change',renderTasks);
  $('taskRows').addEventListener('click',e=>handleTaskAction(e));
  $('dayTasks').addEventListener('click',e=>handleTaskAction(e));
  $('exceptionForm').addEventListener('submit',addException);
  $('exceptionList').addEventListener('click',e=>{const el=e.target.closest('[data-exc-delete]');if(el)removeException(Number(el.dataset.excDelete))});
  $('exportTasks').addEventListener('click',()=>{location.href='/api/export/tasks.csv'});
  $('exportCalendar').addEventListener('click',()=>{location.href=`/api/export/calendar.csv?year=${state.year}`});
}
function handleTaskAction(e){
  const ed=e.target.closest('[data-edit]'), del=e.target.closest('[data-delete]'), rec=e.target.closest('[data-recalc]');
  if(ed){const t=state.tasks.find(t=>t.id===Number(ed.dataset.edit));if(t)openTask(t)}
  if(del)deleteTask(Number(del.dataset.delete));
  if(rec)applyRecalc(Number(rec.dataset.recalc));
}
async function start(){
  bind();$('startDate').value=localToday;$('exceptionDate').value=localToday;
  try{await reloadAll()}catch(e){toast(e.message,true);$('taskRows').innerHTML='<tr><td colspan="6" class="empty">No fue posible cargar el planificador. Revisa la terminal de Python.</td></tr>'}
}
start();
