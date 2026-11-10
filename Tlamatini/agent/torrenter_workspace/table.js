/* Torrenter workspace — Angela López Mendoza · XAIHT.
 * Pure queue/view operations, shared by the browser and regression tests.
 * Sort source values, never rounded/formatted cell text. Unknowns stay last.
 */
'use strict';
const TorrenterTable = (() => {
  const collator = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});
  const number = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
  function progress(job) {
    return job.selected_bytes > 0 ? Math.max(0, Math.min(100, 100 * (number(job.verified_bytes) || 0) / job.selected_bytes)) : 0;
  }
  function status(job) {
    if (!job.completed_at) return job.queue_reason === 'stalled_retry' ? 'queued · retry scheduled' : job.phase || 'Unknown';
    if (!job.delivery_state || job.delivery_state === 'service_store') return 'Service update required';
    if (job.delivery_state === 'failed') return 'Download verified · saving failed';
    if (job.delivery_state === 'pending') return 'Saving to Downloads…';
    return ['stopped','paused'].includes(job.phase) ? 'completed' : job.phase || 'Unknown';
  }
  function canAction(job, action) {
    const done=Boolean(job.completed_at), desired=job.desired_state;
    if(action==='start')return !done&&desired==='stopped';
    if(action==='resume')return !done&&desired==='paused';
    if(action==='pause')return !done&&desired==='running';
    if(action==='stop')return ['running','paused'].includes(desired);
    if(action==='cancel')return !done&&desired!=='cancelled';
    if(action==='recheck')return desired!=='cancelled'&&!['checking','verifying'].includes(job.phase);
    if(action==='reseed')return done&&desired!=='cancelled';
    if(action==='remove')return done||['stopped','cancelled'].includes(desired);
    return false;
  }
  const columns = [
    {key:'name', label:'Name', value:j=>j.name || ''},
    {key:'selected_bytes', label:'Size', value:j=>number(j.selected_bytes)},
    {key:'progress', label:'Progress', value:progress},
    {key:'phase', label:'Status', value:status},
    {key:'seeds', label:'Seeds / peers', value:j=>[number(j.seeds), number(j.peers)]},
    {key:'download_rate_bps', label:'↓ Speed', value:j=>number(j.download_rate_bps)},
    {key:'upload_rate_bps', label:'↑ Speed', value:j=>number(j.upload_rate_bps)},
    {key:'eta_seconds', label:'ETA', value:j=>j.eta_seconds >= 0 ? number(j.eta_seconds) : null},
    {key:'ratio', label:'Ratio', value:j=>number(j.ratio)},
    {key:'availability', label:'Availability', value:j=>number(j.availability)},
    {key:'queue_position', label:'Queue', value:j=>number(j.queue_position)},
    {key:'completed_at', label:'Completed', value:j=>j.completed_at > 0 ? number(j.completed_at) : null},
  ].map((column, index)=>({...column, id:index + 1}));
  const byKey = new Map(columns.map(column=>[column.key,column]));
  function normalizeSorts(value) {
    const seen = new Set();
    const valid = Array.isArray(value) ? value.filter(item=>{
      if (!item || !byKey.has(item.key) || seen.has(item.key)) return false;
      seen.add(item.key); return true;
    }).map(item=>({key:item.key,direction:item.direction === -1 ? -1 : 1})) : [];
    return valid.length ? valid : [{key:'name',direction:1}];
  }
  function compare(a, b, direction) {
    if (Array.isArray(a)) {
      for (let i=0; i<a.length; i++) { const result=compare(a[i],b[i],direction); if(result) return result; }
      return 0;
    }
    if (a == null || b == null) return a == null ? (b == null ? 0 : 1) : -1;
    return direction * (typeof a === 'number' ? a-b : collator.compare(a,b));
  }
  function sorted(rows, sorting) {
    const keys=normalizeSorts(sorting);
    return [...rows].sort((a,b)=>{
      for (const rule of keys) { const col=byKey.get(rule.key); const result=compare(col.value(a),col.value(b),rule.direction); if(result) return result; }
      return collator.compare(String(a.job_id),String(b.job_id));
    });
  }
  const fold = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase();
  function matches(job, filters) {
    const terms=fold(filters.search).trim().split(/\s+/).filter(Boolean);
    const text=fold([job.name,job.category,...(job.tags || []),...(job.tracker_hosts || []),job.saved_to,job.job_id,status(job)].join(' '));
    const rate=(number(job.download_rate_bps)||0)+(number(job.upload_rate_bps)||0);
    return terms.every(term=>text.includes(term)) && (!filters.status || status(job) === filters.status) &&
      (!filters.category || job.category === filters.category) && (!filters.tag || (job.tags || []).includes(filters.tag)) &&
      (!filters.tracker || (job.tracker_hosts || []).includes(filters.tracker)) &&
      (!filters.activity || (filters.activity === 'running' ? job.desired_state === 'running' : filters.activity === 'active' ? rate>0 : rate===0)) &&
      (filters.minProgress == null || filters.minProgress === '' || progress(job) >= Number(filters.minProgress)) &&
      (filters.maxProgress == null || filters.maxProgress === '' || progress(job) <= Number(filters.maxProgress));
  }
  function paginate(rows, page, size) {
    const limit=[25,50,100,250].includes(size) ? size : rows.length || 1;
    const pages=Math.max(1,Math.ceil(rows.length/limit));
    const current=Math.max(1,Math.min(pages,Number.isInteger(page)?page:1));
    return {rows:rows.slice((current-1)*limit,current*limit), page:current, pages,
      first:rows.length?(current-1)*limit+1:0, last:Math.min(rows.length,current*limit)};
  }
  return {columns, progress, status, canAction, normalizeSorts, sorted, matches, paginate};
})();
if (typeof module !== 'undefined' && module.exports) module.exports = TorrenterTable;
