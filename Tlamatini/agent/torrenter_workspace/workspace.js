'use strict';
/* global DeskLayout, TorrenterTable */
const el = id => document.getElementById(id);
const make = (tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; };
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const bytes = n => typeof n !== 'number' || !Number.isFinite(n) ? '—' : n >= 1073741824 ? (n / 1073741824).toFixed(2) + ' GiB' : n >= 1048576 ? (n / 1048576).toFixed(1) + ' MiB' : n >= 1024 ? (n / 1024).toFixed(1) + ' KiB' : n + ' B';
let identity = null, jobs = [], selected = '', sorts = [{key:'name',direction:1}], tab = 'general', inspection = null, refreshed = false, renderedJobs = null;
let currentPage = 1, pageCount = 1, visibleRows = [];
const checked = new Set();
let policy;
let refreshError = false;
function message(text, error = false) { el('message').textContent = text; el('message').classList.toggle('error', error); }
async function readSession() {
  // A truncated read must not strand the owner heading or prevent recovery
  // controls from starting. Retry only this read, never a torrent mutation.
  for(let attempt=0; attempt<3; attempt++) {
    const response=await fetch('session/', {cache:'no-store',credentials:'same-origin'});
    if(!response.ok)throw new Error('Sign in to Tlamatini, then reload the workspace.');
    try {
      const data=await response.json();
      if(typeof data.username==='string'&&typeof data.profile==='string'&&typeof data.csrf==='string')return data;
    } catch(error) { if(!(error instanceof SyntaxError))throw error; }
    if(attempt<2)await wait(200);
  }
  throw new Error('The local session response was incomplete. Reload the workspace to reconnect.');
}
async function api(route, method = 'GET', body, job, key) {
  const headers = {};
  if (!identity) throw new Error('Sign in to Tlamatini.');
  headers['X-Torrenter-Profile'] = identity.profile;
  if (method !== 'GET') {
    const session = await readSession();
    headers['X-CSRFToken'] = session.csrf;
  }
  if (job) headers['If-Match'] = '"' + job.revision + '"';
  if (key) headers['Idempotency-Key'] = key;
  let data = body;
  if (body !== undefined && !(body instanceof FormData)) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(body); }
  const reply = await fetch('api/v1/' + route, {method, headers, body:data, cache:'no-store', redirect:'error'});
  const result = (reply.headers.get('Content-Type') || '').includes('application/json') ? await reply.json() : {};
  if (!reply.ok) {
    if (reply.status === 401 || (reply.status === 403 && result.code === 'account_changed')) {
      identity=null; jobs=[]; selected=''; checked.clear(); el('workspace').hidden=true;
      el('workspace-owner').textContent=''; el('workspace-owner').parentElement.hidden=true;
      el('rows').replaceChildren(); el('details').replaceChildren();
      for (const dialog of document.querySelectorAll('dialog[open]')) dialog.close();
      el('connection').textContent='Session changed · reload to sign in';
    }
    throw Object.assign(new Error(result.error || 'HTTP ' + reply.status), {status:reply.status});
  }
  return result;
}
function handle(button, action) {
  button.addEventListener('click', async event => {
    event.preventDefault(); button.disabled = true;
    try { await action(); } catch (err) { message(err.message, true); if (el('admit').open) el('admit-message').textContent = err.message; }
    finally { button.disabled = false; updateActions(); }
  });
}
function options(id,items,label) {
  const select=el(id), current=select.value;
  select.replaceChildren(new Option(label,''));
  for (const item of [...new Set(items.filter(Boolean))].sort()) select.add(new Option(item,item));
  if(current && ![...select.options].some(o=>o.value===current)) select.add(new Option(current+' (0)',current));
  select.value=current;
}
function selectionSummary() {
  const visibleSelected=visibleRows.filter(job=>checked.has(job.job_id)).length;
  el('select-page').checked=visibleRows.length>0 && visibleSelected===visibleRows.length;
  el('select-page').indeterminate=visibleSelected>0 && visibleSelected<visibleRows.length;
  el('select-page').disabled=!visibleRows.length;
  el('selection-summary').hidden=!checked.size;
  el('selection-count').textContent=checked.size+' selected'+(checked.size>visibleSelected?' · '+(checked.size-visibleSelected)+' outside this page':'');
  updateActions();
}
function updateActions() {
  const targets=jobs.filter(job=>checked.size?checked.has(job.job_id):job.job_id===selected);
  for(const button of document.querySelectorAll('[data-action]')) {
    const count=targets.filter(job=>TorrenterTable.canAction(job,button.dataset.action)).length;
    button.disabled=!count;
    button.title=count?'Applies to '+count+' eligible download(s).':'Not available for the selected download state.';
  }
}
function filters() {
  return {search:el('search').value,status:el('filter').value,category:el('category').value,tag:el('tag').value,
    tracker:el('tracker').value,activity:el('activity').value,minProgress:el('progress-min').value,maxProgress:el('progress-max').value};
}
function grid() {
  options('filter',jobs.map(TorrenterTable.status),'All states');
  options('category',jobs.map(x=>x.category),'All categories');
  options('tag',jobs.flatMap(x=>x.tags),'All tags');
  options('tracker',jobs.flatMap(j=>j.tracker_hosts||[]),'All trackers');
  const query=filters();
  const invalidRange=!el('progress-min').validity.valid||!el('progress-max').validity.valid||
    (query.minProgress!==''&&query.maxProgress!==''&&Number(query.minProgress)>Number(query.maxProgress));
  el('filter-error').textContent=invalidRange?'Use 0–100%, with From no greater than To.':'';
  const rows=TorrenterTable.sorted(invalidRange?[]:jobs.filter(job=>TorrenterTable.matches(job,query)),sorts);
  const page=TorrenterTable.paginate(rows,currentPage,DeskLayout.snapshot().pageSize);
  currentPage=page.page;pageCount=page.pages;visibleRows=page.rows;
  const focused=document.activeElement, focusJob=focused.closest('#rows tr')?.dataset.jobId, focusKind=focused.dataset.focus;
  const list=el('rows'); list.replaceChildren(); el('count').textContent=rows.length+' of '+jobs.length+' downloads';
  el('page-summary').textContent=page.first+'–'+page.last+' of '+rows.length;
  el('page-number').textContent=currentPage+' / '+pageCount;
  el('page-first').disabled=el('page-prev').disabled=currentPage===1;
  el('page-last').disabled=el('page-next').disabled=currentPage===pageCount;
  for (const job of page.rows) {
    const row=make('tr'), box=make('input'); box.type='checkbox'; box.checked=checked.has(job.job_id); box.setAttribute('aria-label','Select '+job.name);
    row.dataset.jobId=job.job_id;row.tabIndex=0;row.dataset.focus='row';row.setAttribute('aria-label',job.name);
    box.dataset.focus='checkbox';
    box.onchange=()=>{if(box.checked) checked.add(job.job_id); else checked.delete(job.job_id);selectionSummary();};
    box.onclick=e=>e.stopPropagation();
    row.append(make('td')); row.cells[0].append(box);
    const title=make('button',job.name); title.title=job.name; title.onclick=()=>{selected=job.job_id;grid(); reportDetails();};
    title.dataset.focus='title';
    row.onclick=event=>{if(event.target.closest('button,input'))return;selected=job.job_id;grid();reportDetails();};
    row.onkeydown=event=>{if(event.target===row&&event.key==='Enter'){event.preventDefault();selected=job.job_id;grid();reportDetails();}};
    row.append(make('td')); row.cells[1].append(title);
    row.append(make('td',bytes(job.selected_bytes)));
    const pct=TorrenterTable.progress(job);
    const meter=make('progress');meter.max=100;meter.value=pct;meter.setAttribute('aria-label','Download progress for '+job.name);
    const progress=make('td');progress.append(meter,' '+pct.toFixed(1)+'%');row.append(progress);
    for (const value of [TorrenterTable.status(job),(job.seeds??'—')+' / '+(job.peers??'—'),bytes(job.download_rate_bps)+'/s',bytes(job.upload_rate_bps)+'/s',job.eta_seconds==null||job.eta_seconds<0?'—':Math.ceil(job.eta_seconds/60)+' min',job.ratio==null?'—':job.ratio.toFixed(2),job.availability==null?'—':job.availability.toFixed(2),job.queue_position==null?'—':job.queue_position+1,job.completed_at?new Date(job.completed_at*1000).toLocaleString():'—']) row.append(make('td',value));
    row.setAttribute('aria-selected',String(selected===job.job_id));list.append(row);
  }
  if (!rows.length) { const td=make('td',jobs.length?'No matching downloads.':'No downloads yet. Use Add torrent to inspect a file or magnet.');td.colSpan=13;const tr=make('tr');tr.append(td);list.append(tr); }
  DeskLayout.arrange();
  selectionSummary();
  if(focusJob) {
    const replacement=[...list.rows].find(row=>row.dataset.jobId===focusJob);
    if(replacement)(focusKind==='row'?replacement:replacement.querySelector('[data-focus="'+focusKind+'"]'))?.focus({preventScroll:true});
  }
  el('rates').textContent='↓ '+bytes(jobs.reduce((v,j)=>v+j.download_rate_bps,0))+'/s · ↑ '+bytes(jobs.reduce((v,j)=>v+j.upload_rate_bps,0))+'/s · '+new Date().toLocaleTimeString();
}
async function refresh() {
  if (!identity||refreshed) return;
  refreshed=true;
  try {
    // Collect the entire owned queue before replacing it. A later-page failure
    // leaves the last complete snapshot intact, never a silently truncated list.
    const account=identity.profile, page=await api('torrents?limit=250');
    const all=[...page.items], seen=new Set(); let cursor=page.next_cursor;
    while(cursor!=null) {
      if(!Number.isSafeInteger(cursor)||cursor<0||seen.has(cursor)||seen.size>=2000)throw new Error('Invalid queue pagination. Keeping the previous complete view.');
      seen.add(cursor);
      const next=await api('torrents?limit=250&cursor='+cursor);
      all.push(...next.items);cursor=next.next_cursor;
    }
    if(!identity||identity.profile!==account)return;
    jobs=[...new Map(all.map(job=>[job.job_id,job])).values()];
    const liveIds=new Set(jobs.map(job=>job.job_id));
    for(const id of checked)if(!liveIds.has(id))checked.delete(id);
    const waiting = Number(page.resolving_metadata) || 0;
    el('pending-metadata').hidden = !waiting;
    el('pending-metadata').textContent = waiting ? waiting + ' magnet inspection(s) awaiting a file list.' : '';
    const roots = new Set(jobs.filter(j=>j.saved_to && j.delivery_state==='saved').map(j=>
      (j.delivery_location==='content_generated' ? 'content_generated · ' : 'Windows Downloads · ')+
      j.saved_to.replace(/[\\/][^\\/]+$/, '')));
    el('save-location').textContent=roots.size ? [...roots].join(' | ') :
      (jobs.find(j=>j.delivery_error)?.delivery_error || (jobs.some(j=>!j.delivery_state || j.delivery_state==='service_store') ? 'Update Tlachihuani Jobs to save verified files in Windows Downloads.' : ''));
    if (!jobs.some(j=>j.job_id===selected)) selected='';
    const version=JSON.stringify(jobs);
    if(version!==renderedJobs){grid();renderedJobs=version;}
    if (!el('details').contains(document.activeElement)) await details();
    if (refreshError) { message('Connected.'); refreshError = false; }
    return page.event_cursor; }
  finally { refreshed=false; }
}
for(const id of ['filter','search','category','tag','tracker','activity','progress-min','progress-max']) el(id).addEventListener('input',()=>{currentPage=1;grid();});
el('clear-filters').onclick=()=>{for(const id of ['filter','search','category','tag','tracker','activity','progress-min','progress-max'])el(id).value='';currentPage=1;grid();};
document.querySelectorAll('[data-sort]').forEach(button=>button.onclick=event=>{
  const key=button.dataset.sort, old=sorts.find(rule=>rule.key===key);
  const rule={key,direction:old?-old.direction:1};
  sorts=event.shiftKey?(old?sorts.map(item=>item.key===key?rule:item):[...sorts,rule]):[rule];
  currentPage=1;DeskLayout.sortBy(sorts);grid();
});
el('reset-sort').onclick=()=>{sorts=[{key:'name',direction:1}];currentPage=1;DeskLayout.sortBy(sorts);grid();};
document.addEventListener('desk-layout-change',event=>{sorts=event.detail.sorts;currentPage=1;grid();});
for(const [id,value] of [['page-first',()=>1],['page-prev',()=>currentPage-1],['page-next',()=>currentPage+1],['page-last',()=>pageCount]])el(id).onclick=()=>{currentPage=value();grid();el('transfer-grid').scrollTop=0;};
el('select-page').onchange=event=>{for(const job of visibleRows){if(event.target.checked)checked.add(job.job_id);else checked.delete(job.job_id);}grid();};
el('clear-selection').onclick=()=>{checked.clear();grid();};
function targetJobs() {
  const ids=checked.size?checked:new Set([selected]);
  const matches=jobs.filter(j=>ids.has(j.job_id)); if(!matches.length) throw new Error('Select a download first.');return matches;
}
async function applyToJobs(operation) {
  const all=targetJobs(), targets=all.filter(job=>TorrenterTable.canAction(job,operation));
  const skipped=all.length-targets.length, suffix=skipped?' · '+skipped+' ineligible download(s) unchanged.':'';
  if(!targets.length)throw new Error('This action is not available for the selected download state.');
  if ((operation==='cancel'||operation==='remove')&&!confirm(operation+' '+targets.length+' download record(s)? Files will be retained.')) return;
  if(targets.length>1 && ['pause','resume','stop','start'].includes(operation)){
    const result=await api('batch-operations','POST',{action:operation,jobs:targets.map(j=>({job_id:j.job_id,revision:j.revision}))},null,crypto.randomUUID());
    const failed=result.items.filter(x=>!x.ok); await refresh(); message((targets.length-failed.length)+' accepted · '+failed.map(x=>x.job_id+': '+x.error).join(' · ')+suffix,!!failed.length); return;
  }
  const errors=[];
  for (const job of targets) {
    try {
      const path='torrents/'+job.job_id;
      if(operation==='remove') await api(path,'DELETE',undefined,job,crypto.randomUUID());
      else await api(path+'/actions','POST',{action:operation},job,crypto.randomUUID());
    } catch(err){errors.push(job.name+': '+err.message);}
  }
  await refresh(); message((errors.length?errors.join(' · '):'Request recorded for '+targets.length+' download(s).')+suffix,!!errors.length);
}
document.querySelectorAll('[data-action]').forEach(b=>handle(b,()=>applyToJobs(b.dataset.action)));
handle(el('move'),async()=>{const targets=targetJobs();if(targets.length!==1)throw new Error('Select one stopped download.');const job=targets[0];const destination=job.destination_root_id==='archive'?'downloads':'archive';if(!confirm('Move '+job.name+' to '+destination+'?'))return;const receipt=await api('torrents/'+job.job_id+'/actions','POST',{action:'move',destination_root_id:destination},job,crypto.randomUUID());message('Move receipt '+receipt.operation_id);await refresh();});
handle(el('prefs'),async()=>{policy=await api('settings');const d=policy.defaults;el('down-default').value=d.download_limit;el('up-default').value=d.upload_limit;el('resume-default').checked=d.resume_on_boot;el('seed-default').checked=d.seed_after_completion;el('preferences').showModal();});
handle(el('save-defaults'),async()=>{await api('settings','PATCH',{download_limit:Number(el('down-default').value),upload_limit:Number(el('up-default').value),resume_on_boot:el('resume-default').checked,seed_after_completion:el('seed-default').checked},policy,crypto.randomUUID());el('preferences').close();message('Profile preferences saved.');});
handle(el('remove'),()=>applyToJobs('remove'));
handle(el('erase'),async()=>{
  const targets=targetJobs();if(targets.length!==1) throw new Error('Select exactly one stopped download to review its files.');
  const job=targets[0], pr=await api('content-deletion-previews','POST',{job_id:job.job_id},job);
  if(!pr.files.length) throw new Error('This job has no owned files to delete.');
  message('Review deletion '+pr.preview_id+' in XT → Services → Review erasure. Waiting for approval…');
  const key=crypto.randomUUID();
  for(let i=0;i<55;i++){
    await wait(2000);
    try {const receipt=await api('content-deletions','POST',{preview_id:pr.preview_id},job,key);message('Deletion receipt '+receipt.operation_id);return;}
    catch(err){if(err.status!==403) throw err;}
  }
  throw new Error('File erasure approval expired.');
});
function filePriority(id,level,disabled){
  const select=make('select');select.dataset.file=id;select.disabled=disabled;select.setAttribute('aria-label','Priority for file '+id);
  for(let n=1;n<=7;n++)select.add(new Option(n===1?'1 · Low':n===4?'4 · Normal':n===7?'7 · High':String(n),String(n)));
  select.value=String(level||4);return select;
}
function priorities(list){return Object.fromEntries([...list.querySelectorAll('input:checked')].map(box=>[box.value,Number(list.querySelector('[data-file="'+box.value+'"]').value)]));}
function reportDetails(){details().catch(e=>message(e.message,true));}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;reportDetails();});
async function details(){
  const area=el('details'), id=selected, view=tab, job=jobs.find(j=>j.job_id===id);
  document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===view)));
  document.body.classList.toggle('detail-open',Boolean(job));
  el('selected').textContent=job?job.name:'Transfer details';
  if(!job){area.textContent='Select a transfer.';return;}
  const editable=job.desired_state==='stopped'&&['stopped','completed'].includes(job.phase);
  if(view==='general'){
    const dl=make('dl');
    for(const [label,value] of Object.entries({'Job ID':id,'Desired':job.desired_state,'Observed':TorrenterTable.status(job),'Verified':bytes(job.verified_bytes)+' / '+bytes(job.selected_bytes),'Queue position':job.queue_position+1,'Saved to':job.saved_to || job.destination_root_id,'Delivery':job.delivery_state || 'service_store','Delivery error':job.delivery_error || '—','Revision':job.revision,'Category':job.category||'Uncategorized','Tags':job.tags.join(', ')||'Untagged','Reason':job.completed_at&&['completed','stopped','paused'].includes(job.phase)?'—':job.error||'—','Recovery':job.recovery_note||(job.queue_reason==='stalled_retry'?'Yielded a stalled slot; retry is automatic.':job.phase==='waiting_for_peers'?'No connected peers. Reported seeds do not guarantee availability.':job.completed_at?'Download finished. Start is unnecessary; use Recheck only to verify the retained files.':'—')})){dl.append(make('dt',label),make('dd',value));}
    const edit=make('button','Edit labels and limits');
    handle(edit,async()=>{const cat=prompt('Category',job.category);if(cat===null)return;const tags=prompt('Comma-separated tags',job.tags.join(', '));if(tags===null)return;const limit=prompt('Download limit in bytes/second (0 = unlimited)',String(job.download_limit));if(limit===null)return;const up=prompt('Upload limit in bytes/second (0 = unlimited)',String(job.upload_limit));if(up===null)return;const position=prompt('Queue position (1 = first)',String(job.queue_position+1));if(position===null)return;await api('torrents/'+id,'PATCH',{category:cat,tags:tags.split(',').map(x=>x.trim()).filter(Boolean),download_limit:Number(limit),upload_limit:Number(up),queue_position:Number(position)-1},job,crypto.randomUUID());await refresh();});
    area.replaceChildren(dl,edit);return;
  }
  const data=await api('torrents/'+id+'/'+view);if(id!==selected||view!==tab)return;
  const list=make('div');list.className='listing';
  if(view==='manifest'){
    list.append(make('p',data.verified?'Saved to: '+data.output_root:data.delivery_error || (data.download_verified?'Download verified. Saving to Windows Downloads…':'Available after the selected files have been verified.')));
    if(data.verified && data.delivery_location==='content_generated')
      list.append(make('p','Saved in content_generated because Windows Downloads was unavailable: '+(data.downloads_error || '—')));
    for(const file of data.files) list.append(make('p',file.path+' · '+file.sha256));
  } else if(view==='files'){
    for(const file of data.items){const label=make('label');label.className='choice';const box=make('input');box.type='checkbox';box.checked=file.selected;box.value=file.id;box.disabled=!editable;label.append(box,file.path+' · '+bytes(file.size));label.append(filePriority(file.id,file.priority,!editable));list.append(label);}
    const save=make('button','Save file selection');save.disabled=!editable;
    handle(save,async()=>{const ids=[...list.querySelectorAll('input:checked')].map(b=>Number(b.value));await api('torrents/'+id+'/files','PATCH',{selected_file_ids:ids,priorities:priorities(list)},job,crypto.randomUUID());await refresh();});list.append(save);
  } else {for(const item of data.items) list.append(make('p',Object.entries(item).map(([k,v])=>k+': '+v).join(' · ')));if(!data.items.length)list.textContent='No entries in the current snapshot.';}
  if((view==='trackers'||view==='web-seeds') && editable){const edit=make('button','Replace source list…');handle(edit,async()=>{const raw=prompt('Enter complete replacement URLs on separate lines. An empty list clears these sources.');if(raw===null)return;await api('torrents/'+id+'/'+view,'PATCH',{urls:raw.split(/\s+/).filter(Boolean)},job,crypto.randomUUID());await refresh();});list.append(edit);}
  area.replaceChildren(list);
}
el('add').onclick=async()=>{try{const {defaults}=await api('settings');el('resume-boot').checked=defaults.resume_on_boot;el('seed').checked=defaults.seed_after_completion;}catch(err){message(err.message,true);return;}inspection=null;el('files').replaceChildren();el('submit').disabled=true;el('admit-message').textContent='';el('admit').showModal();};
handle(el('inspect'),async()=>{
  inspection=null;el('submit').disabled=true;const file=el('torrent').files[0];let body;
  if(file){body=new FormData();body.append('file',file);}else{body={magnet:el('magnet').value.trim()};}
  let result=await api('inspections','POST',body);
  while(result.phase==='resolving_metadata' && el('admit').open){
    el('admit-message').textContent=result.lookup_state==='queued' ? 'Magnet queued. Waiting for a metadata slot…' : 'Waiting for magnet metadata…';
    await wait(1500);result=await api('inspections/'+result.inspection_id);
  }
  if(!el('admit').open)return;if(result.phase!=='ready')throw new Error('Metadata lookup expired.');
  inspection=result;const list=el('files');list.replaceChildren(make('h2',result.name));list.className='listing';
  for(const file of result.files){const row=make('label');row.className='choice';const box=make('input');box.type='checkbox';box.checked=true;box.value=file.id;row.append(box,file.path+' · '+bytes(file.size),filePriority(file.id,4,false));list.append(row);}
  el('submit').disabled=false;el('admit-message').textContent='Review the file selection before submitting.';
});
handle(el('submit'),async()=>{
  const ids=[...el('files').querySelectorAll('input:checked')].map(b=>Number(b.value));
  if(!inspection||!ids.length)throw new Error('Inspect a torrent and select files first.');
  const result=await api('torrents','POST',{inspection_id:inspection.inspection_id,metadata_revision:inspection.metadata_revision,selected_file_ids:ids,resume_on_boot:el('resume-boot').checked,seed_after_completion:el('seed').checked,destination_root_id:el('root').value,priorities:priorities(el('files'))},null,inspection.key||(inspection.key=crypto.randomUUID()));
  selected=result.job_id;el('admit').close();await refresh();message('Download accepted · '+result.job_id);
});
async function openWorkspace() {
  identity=await readSession();
  const spanish = identity.edition?.startsWith('es');
  el('owner-label').textContent=spanish ? 'Usuario conectado' : 'Signed-in user';
  el('workspace-owner').textContent=identity.username;
  el('workspace-owner').parentElement.hidden=false;
  el('connection').textContent=spanish ? 'Sesión local' : 'Local session';
  ({sorts}=DeskLayout.load(identity.profile));
  el('workspace').hidden=false;
  await refresh(); message('Connected.');
}
openWorkspace().catch(e=>message(e.message,true));
setInterval(()=>refresh().catch(e=>{
  refreshError = true;
  message(e instanceof TypeError ? 'Connection interrupted. Retrying…' : e.message,true);
}),2000);
