'use strict';
const DeskLayout = (() => {
  const byId = id => document.getElementById(id);
  const header = document.querySelector('thead tr');
  const cells = Array.from(header.cells);
  const identity = cells.map((_, i) => i);
  const picker = byId('column');
  cells.forEach((cell, i) => picker.add(new Option(cell.textContent, i)));
  let key = '', order = [...identity], widths = {}, height = 30, sort = 'name', direction = 1;

  function save() {
    if (key) try { localStorage.setItem(key, JSON.stringify({version:2,order,widths,height,sort,direction})); } catch {}
  }
  function bounded(value, min, max, fallback) {
    return Number.isFinite(value) && value >= min && value <= max ? value : fallback;
  }
  function arrange() {
    for (const id of order) {
      const cell = cells[id];
      // Let the table fit its data unless the user explicitly widened a column.
      const width = bounded(widths[id],60,500,0);
      cell.style.minWidth = width ? width + 'px' : '';
      header.append(cell);
    }
    byId('grid-height').value = height;
    document.documentElement.style.setProperty('--details-share', height + '%');
    byId('column-width').value = bounded(widths[picker.value],60,500,88);
    for (const row of byId('rows').rows) {
      const columns = Array.from(row.cells);
      if (columns.length !== order.length) continue;
      // Cell identity survives preference edits until the next queue snapshot.
      for (const [index,cell] of columns.entries()) if (!cell.dataset.column) cell.dataset.column = String(index);
      for (const id of order) row.append(columns.find(cell => cell.dataset.column === String(id)));
    }
  }
  function shift(by) {
    const index = order.indexOf(Number(picker.value)), to = index + by;
    if (to < 0 || to >= order.length) return;
    [order[index],order[to]] = [order[to],order[index]];
    arrange(); save();
  }
  byId('col-left').onclick = () => shift(-1);
  byId('col-right').onclick = () => shift(1);
  picker.onchange = arrange;
  byId('column-width').oninput = e => { widths[picker.value] = Number(e.target.value); arrange(); save(); };
  byId('grid-height').oninput = e => { height = Number(e.target.value); arrange(); save(); };
  return {
    load(profile) {
      key='xt.torrenter.layout.'+profile;
      let data={}; try { data=JSON.parse(localStorage.getItem(key)) || {}; } catch {}
      order = Array.isArray(data.order) && data.order.length===identity.length && identity.every(i=>data.order.includes(i)) ? data.order : [...identity];
      widths = data.widths && typeof data.widths === 'object' ? data.widths : {};
      // Legacy grid heights left unused viewport space. Keep columns/sort, migrate sizing.
      height = data.version === 2 ? bounded(data.height,20,60,30) : 30;
      sort = [...document.querySelectorAll('[data-sort]')].some(b=>b.dataset.sort===data.sort) ? data.sort : 'name';
      direction = data.direction===-1 ? -1 : 1;
      arrange();return {sort,direction};
    },
    sortBy(field,sign) { sort=field;direction=sign;save(); },
    arrange
  };
})();
