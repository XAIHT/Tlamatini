'use strict';
/* global TorrenterTable */
/* exported DeskLayout */
const DeskLayout = (() => {
  const byId = id => document.getElementById(id);
  const header = document.querySelector('#transfer-grid thead tr');
  const cells = Array.from(header.cells);
  const ids = cells.map((_, i) => i);
  const picker = byId('column');
  const columns = TorrenterTable.columns;
  for (const col of columns) picker.add(new Option(col.label,col.id));
  let key='', order=[...ids], widths={}, hidden=[], height=30, sorts=[{key:'name',direction:1}], pageSize=50, compact=false;

  function snapshot() { return {version:3,order,widths,hidden,height,sorts,pageSize,compact}; }
  function save() {
    if (!key) return;
    try {
      localStorage.setItem(key,JSON.stringify(snapshot()));
      byId('view-storage').textContent='View saved for this account in this browser.';
    } catch { byId('view-storage').textContent='Browser storage is unavailable. Your view still works for this session.'; }
  }
  function bounded(value,min,max,fallback) { return Number.isFinite(value)&&value>=min&&value<=max ? value : fallback; }
  function changed() { arrange(); save(); document.dispatchEvent(new CustomEvent('desk-layout-change',{detail:snapshot()})); }
  function visibilityControls() {
    const list=byId('column-visibility');
    list.replaceChildren();
    for (const id of order.filter(id=>id!==0)) {
      const col=columns.find(col=>col.id===id), label=document.createElement('label'), box=document.createElement('input');
      label.className='choice'; box.type='checkbox'; box.checked=!hidden.includes(id); box.dataset.columnToggle=id;
      box.disabled=box.checked && hidden.length===columns.length-1;
      box.onchange=()=>{hidden=box.checked?hidden.filter(value=>value!==id):[...hidden,id];changed();};
      label.append(box,document.createTextNode(col.label));list.append(label);
    }
  }
  function arrange() {
    const focusedHeader=header.contains(document.activeElement)?document.activeElement:null;
    for (const id of order) {
      const cell=cells[id], width=bounded(widths[id],60,500,0);
      cell.dataset.column=id;
      cell.hidden=hidden.includes(id);
      cell.style.minWidth=width?width+'px':'';
      header.append(cell);
    }
    for (const row of byId('rows').rows) {
      const entries=Array.from(row.cells);
      if (entries.length!==ids.length) { if(entries.length===1) entries[0].colSpan=ids.length-hidden.length; continue; }
      entries.forEach((cell,index)=>{if(!cell.dataset.column)cell.dataset.column=index;});
      for (const id of order) {
        const cell=entries.find(cell=>Number(cell.dataset.column)===id);
        cell.hidden=hidden.includes(id);row.append(cell);
      }
    }
    byId('grid-height').value=height;
    document.documentElement.style.setProperty('--details-share',height+'%');
    byId('column-width').value=bounded(widths[picker.value],60,500,88);
    byId('column-width-value').textContent=widths[picker.value]?widths[picker.value]+' px':'Automatic';
    byId('grid-height-value').textContent=height+'%';
    byId('page-size').value=String(pageSize);
    byId('compact-rows').checked=compact;
    for(const box of byId('column-visibility').querySelectorAll('input')) {
      box.checked=!hidden.includes(Number(box.dataset.columnToggle));
      box.disabled=box.checked && hidden.length===columns.length-1;
    }
    document.body.classList.toggle('compact-rows',compact);
    byId('col-left').disabled=order.indexOf(Number(picker.value))<=1;
    byId('col-right').disabled=order.indexOf(Number(picker.value))===order.length-1;
    for (const col of columns) {
      const cell=cells[col.id], button=cell.querySelector('button'), index=sorts.findIndex(rule=>rule.key===col.key), rule=sorts[index];
      cell.setAttribute('aria-sort',index<0?'none':index>0?'other':rule.direction===1?'ascending':'descending');
      button.querySelector('.sort-indicator').textContent=rule?(rule.direction===1?'▲':'▼')+(sorts.length>1?' '+(index+1):''):'↕';
      button.setAttribute('aria-label',col.label+(rule?', '+(rule.direction===1?'ascending':'descending')+', priority '+(index+1):', not sorted')+'. Click to sort; Shift-click to add a sort column.');
      button.title=button.getAttribute('aria-label');
    }
    byId('sort-summary').textContent='Sorted by '+sorts.map(rule=>columns.find(c=>c.key===rule.key).label+' '+(rule.direction===1?'↑':'↓')).join(', ');
    if(focusedHeader&&!focusedHeader.closest('[hidden]'))focusedHeader.focus({preventScroll:true});
  }
  function shift(by) {
    const index=order.indexOf(Number(picker.value)), to=index+by;
    if(to<1||to>=order.length)return;
    [order[index],order[to]]=[order[to],order[index]];
    changed();visibilityControls();
  }
  byId('col-left').onclick=()=>shift(-1);
  byId('col-right').onclick=()=>shift(1);
  picker.onchange=arrange;
  byId('column-width').oninput=e=>{widths[picker.value]=Number(e.target.value);changed();};
  byId('column-auto').onclick=()=>{delete widths[picker.value];changed();};
  byId('grid-height').oninput=e=>{height=Number(e.target.value);changed();};
  byId('compact-rows').onchange=e=>{compact=e.target.checked;changed();};
  byId('page-size').onchange=e=>{pageSize=Number(e.target.value);changed();};
  byId('show-columns').onclick=()=>{visibilityControls();byId('table-options').showModal();};
  byId('show-all-columns').onclick=()=>{hidden=[];changed();visibilityControls();};
  byId('reset-view').onclick=()=>{
    order=[...ids];widths={};hidden=[];height=30;sorts=[{key:'name',direction:1}];pageSize=50;compact=false;
    changed();visibilityControls();
  };
  return {
    load(profile) {
      key='xt.torrenter.layout.'+profile;
      let data={}; try { data=JSON.parse(localStorage.getItem(key))||{}; } catch { /* Usable without storage. */ }
      if(typeof data!=='object')data={};
      order=Array.isArray(data.order)&&data.order.length===ids.length&&ids.every(id=>data.order.includes(id))
        ? [0,...data.order.filter(id=>id!==0)] : [...ids];
      widths=Object.fromEntries(ids.filter(id=>bounded(data.widths?.[id],60,500,0)).map(id=>[id,data.widths[id]]));
      hidden=Array.isArray(data.hidden)?[...new Set(data.hidden.filter(id=>Number.isInteger(id)&&id>0&&id<ids.length))]:[];
      if(hidden.length===columns.length)hidden=hidden.filter(id=>id!==1);
      height=data.version>=2?bounded(data.height,20,60,30):30;
      sorts=TorrenterTable.normalizeSorts(data.sorts||[{key:data.sort,direction:data.direction}]);
      pageSize=[0,25,50,100,250].includes(data.pageSize)?data.pageSize:50;
      compact=data.compact===true;
      arrange();visibilityControls();return snapshot();
    },
    sortBy(value) { sorts=TorrenterTable.normalizeSorts(value); arrange();save(); },
    arrange, snapshot
  };
})();
