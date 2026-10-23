'use strict';
const $ = id => document.getElementById(id);
const C = window.GARAGE;
const euro = n => n == null ? '—' : new Intl.NumberFormat('es-ES', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0, useGrouping: 'always'}).format(n);
const num = n => new Intl.NumberFormat('es-ES', {useGrouping: 'always'}).format(n);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const paths = {pin: 'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z M15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0', heart: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z', close: 'M6 6l12 12 M6 18L18 6', search: 'M21 21l-4.3-4.3 M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0', filter: 'M4 6h16 M7 12h10 M10 18h4', external: 'M14 4h6v6 M10 14 20 4 M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5', moon: 'M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z', sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z M12 1v2 M12 21v2 M4.2 4.2l1.4 1.4 M18.4 18.4l1.4 1.4 M1 12h2 M21 12h2 M4.2 19.8l1.4-1.4 M18.4 5.6l1.4-1.4', arrow: 'M4 12h16 M14 6l6 6-6 6'};
const icon = n => `<svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="${paths[n] || paths.arrow}"/></svg>`;
const paint = root => root.querySelectorAll('[data-icon]').forEach(e => e.innerHTML = icon(e.dataset.icon));
paint(document);
const store = {get: k => {try {return localStorage.getItem(k)} catch (e) {return null}}, set: (k, v) => {try {v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v)} catch (e) {}}};

/* ── Token: llega en el enlace (?t=…), se guarda en este navegador y se quita de la barra de direcciones ── */
let TOKEN = new URLSearchParams(location.search).get('t') || store.get('garage-token');
if (new URLSearchParams(location.search).has('t')) history.replaceState(null, '', location.pathname + location.hash);

async function rpc(fn, body) {
  const r = await fetch(`${C.url}/rest/v1/rpc/${fn}`, {method: 'POST', headers: {apikey: C.key, 'Content-Type': 'application/json'}, body: JSON.stringify({t: TOKEN, ...body})});
  const j = await r.json().catch(() => null);
  if (!r.ok) {
    const m = (j && j.message) || '';
    const e = new Error(m.includes('token_invalido') ? 'token' : m.includes('limite_superado') ? 'limite' : 'red');
    throw e;
  }
  return j;
}

function showGate(msg) {
  $('gate').hidden = false; $('app').hidden = true; $('topnav').hidden = true;
  $('gateerr').textContent = msg || '';
  $('gatetoken').focus();
}
$('gateform').addEventListener('submit', e => {
  e.preventDefault();
  let v = $('gatetoken').value.trim();
  const m = v.match(/[?&]t=([0-9a-f]+)/i); if (m) v = m[1];
  TOKEN = v; start();
});
$('logout').addEventListener('click', e => {e.preventDefault(); store.set('garage-token', null); TOKEN = null; showGate()});

/* ── Tema ── */
const themeBtn = $('theme');
function paintTheme() {const d = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); themeBtn.innerHTML = icon(d === 'dark' ? 'sun' : 'moon')}
themeBtn.addEventListener('click', () => {const d = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); const n = d === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = n; store.set('garage-theme', n); paintTheme()});
paintTheme();

/* ── Estado de filtros (se refleja en el #hash para poder compartir búsquedas sin el token) ── */
const DEF = {q: '', fin: '', vendedor: '', pmin: '', pmax: '', marca: [], modelo: '', tipo: [], a2: [], kmmax: '', amin: '', amax: '', ccmin: '', ccmax: '', provincia: '', fuente: '', envio: false, orden: '', lat: null, lon: null, radio: ''};
let S = JSON.parse(JSON.stringify(DEF));
try {const h = decodeURIComponent(location.hash.slice(1)); if (h.startsWith('{')) S = {...S, ...JSON.parse(h)}} catch (e) {}
let OPC = null, pag = 1, total = 0, items = [], view = 'all', busy = 0;
let favs = {}; try {favs = JSON.parse(store.get('garage-favs') || '{}')} catch (e) {}
const saveFavs = () => {store.set('garage-favs', JSON.stringify(favs)); $('savecount').textContent = Object.keys(favs).length; $('savecount').classList.toggle('on', Object.keys(favs).length > 0)};

const TIPOS = {naked: 'Naked', deportiva: 'Deportiva', trail: 'Trail', scooter: 'Scooter', custom: 'Custom', touring: 'Touring', campo: 'Campo / cross', clasica: 'Clásica', ciclomotor: 'Ciclomotor', electrica: 'Eléctrica', quad: 'Quad', otra: 'Otra'};
const A2 = {apta: ['Apta A2', 'good'], limitable: ['Limitable A2', 'info'], no: ['No apta A2', 'bad'], desconocido: ['A2 sin datos', '']};
const FUENTES = {wallapop: 'Wallapop', milanuncios: 'Milanuncios', motosnet: 'motos.net', mundimoto: 'Mundimoto', autoscout24: 'AutoScout24', cuimo: 'Cüimo', flexibike: 'Flexibike', motores: 'motor.es'};

function seg(id, opts, key, single) {
  const el = $(id);
  el.innerHTML = opts.map(([v, t]) => `<button type="button" data-v="${esc(v)}">${esc(t)}</button>`).join('');
  const paintSeg = () => el.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', single ? String(S[key] === b.dataset.v) : String(S[key].includes(b.dataset.v))));
  el.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    const v = b.dataset.v;
    if (single) S[key] = S[key] === v ? '' : v;
    else S[key] = S[key].includes(v) ? S[key].filter(x => x !== v) : [...S[key], v];
    paintSeg(); changed();
  });
  paintSeg(); el._paint = paintSeg;
}

const inputs = ['pmin', 'pmax', 'modelo', 'kmmax', 'amin', 'amax', 'ccmin', 'ccmax', 'radio'];
function bindInputs() {
  for (const k of inputs) {const el = $('f-' + k); el.value = S[k] ?? ''; el.addEventListener('input', () => {S[k] = el.value.trim(); changed(400)})}
  $('q').value = S.q; $('q').addEventListener('input', () => {S.q = $('q').value; changed(450)});
  $('orden').value = S.orden; $('orden').addEventListener('change', () => {S.orden = $('orden').value; if (S.orden === 'dist' && S.lat == null) locate(); changed()});
  $('f-provincia').addEventListener('change', () => {S.provincia = $('f-provincia').value; changed()});
  $('f-envio').checked = !!S.envio; $('f-envio').addEventListener('change', () => {S.envio = $('f-envio').checked; changed()});
  $('f-marca-otra').addEventListener('change', () => {const v = $('f-marca-otra').value; if (v && !S.marca.includes(v)) S.marca = [...S.marca, v]; $('f-marca-otra').value = ''; buildMarcas(); changed()});
  $('geo').addEventListener('click', locate);
  $('reset').addEventListener('click', () => {S = JSON.parse(JSON.stringify(DEF)); fillFilters(); changed()});
  $('togglefilters').addEventListener('click', () => {
    if (matchMedia('(max-width:980px)').matches) {$('filters').classList.add('open'); $('sheetmask').hidden = false; requestAnimationFrame(() => $('sheetmask').classList.add('show'))}
    else {$('layout').classList.toggle('nofilters'); $('togglefilters').setAttribute('aria-expanded', String(!$('layout').classList.contains('nofilters')))}
  });
  const close = () => {$('filters').classList.remove('open'); $('sheetmask').classList.remove('show'); setTimeout(() => $('sheetmask').hidden = true, 300)};
  $('closefilters').addEventListener('click', close); $('applyfilters').addEventListener('click', close); $('sheetmask').addEventListener('click', close);
  $('more').addEventListener('click', () => {pag++; load(true)});
  document.querySelectorAll('#topnav button').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
  $('grid').addEventListener('click', e => {
    const f = e.target.closest('[data-fav]'); if (!f) return;
    const id = f.dataset.fav, it = items.find(x => x.id === id) || favs[id];
    if (favs[id]) delete favs[id]; else favs[id] = it;
    saveFavs(); f.classList.toggle('on', !!favs[id]); f.setAttribute('aria-pressed', String(!!favs[id]));
    if (view === 'saved') render();
  });
}

function locate() {
  if (!navigator.geolocation) {$('geonote').textContent = 'Este navegador no permite la ubicación.'; return}
  $('geonote').textContent = 'Pidiendo ubicación…';
  navigator.geolocation.getCurrentPosition(p => {
    S.lat = +p.coords.latitude.toFixed(2); S.lon = +p.coords.longitude.toFixed(2); if (!S.radio) S.radio = '50';
    $('f-radio').disabled = false; $('f-radio').value = S.radio;
    $('geonote').textContent = 'Ubicación lista. Solo Wallapop da la posición del anuncio: el radio deja fuera las otras webs.'; changed();
  }, () => {$('geonote').textContent = 'No se ha podido obtener la ubicación.'}, {maximumAge: 600000, timeout: 10000});
}

function buildMarcas() {
  const top = (OPC.marcas || []).slice(0, 14).map(([m]) => m);
  const extra = S.marca.filter(m => !top.includes(m));
  seg('f-marca', [...top, ...extra].map(m => [m, m]), 'marca', false);
  $('f-marca-otra').innerHTML = '<option value="">Otra marca…</option>' + (OPC.marcas || []).slice(14).map(([m, n]) => `<option value="${esc(m)}">${esc(m)} (${num(n)})</option>`).join('');
}

function fillFilters() {
  seg('f-fin', [['con', 'Con financiación'], ['sin', 'Sin financiación']], 'fin', true);
  seg('f-vendedor', [['particular', 'Particular'], ['profesional', 'Profesional']], 'vendedor', true);
  seg('f-fuente', Object.entries(FUENTES), 'fuente', true);
  seg('f-tipo', (OPC.tipos || []).map(([t]) => [t, TIPOS[t] || t]), 'tipo', false);
  seg('f-a2', Object.entries(A2).map(([k, [t]]) => [k, t]), 'a2', false);
  buildMarcas();
  $('f-provincia').innerHTML = '<option value="">Toda España</option>' + (OPC.provincias || []).map(p => `<option>${esc(p)}</option>`).join('');
  $('f-provincia').value = S.provincia;
  for (const k of inputs) $('f-' + k).value = S[k] ?? '';
  $('f-radio').disabled = S.lat == null;
  $('q').value = S.q; $('orden').value = S.orden; $('f-envio').checked = !!S.envio;
}

let timer = null;
function changed(delay = 0) {
  clearTimeout(timer);
  timer = setTimeout(() => {pag = 1; history.replaceState(null, '', '#' + encodeURIComponent(JSON.stringify(diff()))); load(false)}, delay);
}
const diff = () => Object.fromEntries(Object.entries(S).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(DEF[k])));

function query() {
  const f = {pag, por: 48};
  const n = k => S[k] !== '' && S[k] != null && !isNaN(+S[k]) ? +S[k] : undefined;
  if (S.q.trim()) f.q = S.q.trim();
  for (const k of ['pmin', 'pmax', 'kmmax', 'amin', 'amax', 'ccmin', 'ccmax']) if (n(k) !== undefined) f[k] = n(k);
  for (const k of ['marca', 'tipo', 'a2']) if (S[k].length) f[k] = S[k];
  if (S.modelo.trim()) f.modelo = S.modelo.trim();
  if (S.provincia) f.provincia = [S.provincia];
  for (const k of ['fin', 'vendedor', 'fuente', 'orden']) if (S[k]) f[k] = S[k];
  if (S.envio) f.envio = true;
  if (S.lat != null) {f.lat = S.lat; f.lon = S.lon; if (n('radio')) f.radio = n('radio')}
  return f;
}

async function load(append) {
  const my = ++busy;
  $('grid').classList.add('loading');
  try {
    const r = await rpc('buscar', {f: query()});
    if (my !== busy) return;
    total = r.total; items = append ? items.concat(r.items) : r.items;
    render();
  } catch (e) {
    if (e.message === 'token') return showGate('Ese código no es válido o ha caducado.');
    toast(e.message === 'limite' ? 'Has hecho muchas búsquedas en la última hora. Espera un poco.' : 'No se ha podido buscar. Revisa la conexión.');
  } finally {if (my === busy) $('grid').classList.remove('loading')}
}

function setView(v) {
  view = v;
  document.querySelectorAll('#topnav button').forEach(b => b.setAttribute('aria-current', b.dataset.view === v ? 'page' : 'false'));
  movePill(); $('toolbar').hidden = v === 'saved'; $('filters').hidden = v === 'saved'; $('layout').classList.toggle('nofilters', v === 'saved');
  render();
}
function movePill() {const b = document.querySelector('#topnav button[aria-current="page"]'); if (!b) return; $('navpill').style.width = b.offsetWidth + 'px'; $('navpill').style.transform = `translateX(${b.offsetLeft - 4}px)`}

function ago(d) {
  const h = (Date.now() - new Date(d)) / 36e5;
  return h < 24 ? 'hoy' : h < 48 ? 'ayer' : `hace ${Math.floor(h / 24)} días`;
}

function card(b, i) {
  const [a2t, a2c] = A2[b.a2 || 'desconocido'];
  const fav = !!favs[b.id];
  const specs = [b.anio ?? 'Año ¿?', b.km != null ? num(b.km) + ' km' : '¿? km', b.cc ? b.cc + ' cc' : null, b.cv ? Math.round(b.cv) + ' CV' : null].filter(Boolean);
  const lugar = [b.ciudad, b.provincia].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(', ');
  return `<article class="card" data-id="${esc(b.id)}" style="--i:${Math.min(i % 48, 12)}">
  <div class="media">${b.imagen ? `<img src="${esc(b.imagen)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ''}<div class="ph" ${b.imagen ? 'style="z-index:-1"' : ''}><div>${esc(b.marca || 'Moto')}<span>Foto en el anuncio</span></div></div><div class="shade"></div>
   <div class="flag">${b.tipo ? `<span>${esc(TIPOS[b.tipo] || b.tipo)}</span>` : ''}<span>${ago(b.visto_primero)}</span></div>
   <button class="fav ${fav ? 'on' : ''}" data-fav="${esc(b.id)}" aria-label="${fav ? 'Quitar de' : 'Guardar en'} favoritas" aria-pressed="${fav}">${icon('heart')}</button>
   <div class="pricetag num">${euro(b.precio)}<small>${b.vendedor === 'profesional' ? 'profesional' + (b.nombre_vendedor ? ' · ' + esc(b.nombre_vendedor) : '') : 'particular'}</small></div></div>
  <div class="body">
   <div class="titlerow"><div><div class="make">${esc(b.marca || '¿Marca?')} · ${esc(FUENTES[b.fuente] || b.fuente)}${b.tambien ? ' +' + b.tambien.length : ''}</div><h3>${esc(b.modelo || b.titulo)}</h3></div></div>
   ${b.modelo ? `<p class="desc">${esc(b.titulo)}${b.descripcion ? ' · ' + esc(b.descripcion) : ''}</p>` : (b.descripcion ? `<p class="desc">${esc(b.descripcion)}</p>` : '')}
   <div class="specs">${specs.map(s => `<span>${esc(s)}</span>`).join('')}</div>
   <div class="badges"><span class="badge ${a2c}">${a2t}</span>${b.financiacion ? `<span class="badge good">Financiación${b.cuota ? ' · ' + euro(b.cuota) + '/mes' : ''}</span>` : ''}${b.garantia ? '<span class="badge info">Garantía</span>' : ''}${b.envio ? '<span class="badge">Envío</span>' : ''}</div>
   <div class="place">${icon('pin')}<span>${esc(lugar || 'Ubicación en el anuncio')}${b.dist != null ? ' · ' + num(b.dist) + ' km' : ''}</span></div>
   ${b.tambien ? `<div class="tambien">También en: ${b.tambien.map(o => `<a href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${esc(FUENTES[o.fuente] || o.fuente)} (${euro(o.precio)})</a>`).join(' ')}</div>` : ''}
   <div class="cardfoot"><a class="btn primary" href="${esc(b.url)}" target="_blank" rel="noopener noreferrer">Ver anuncio ${icon('external')}</a></div>
  </div></article>`;
}

function render() {
  const list = view === 'saved' ? Object.values(favs) : items;
  $('viewtitle').textContent = view === 'saved' ? 'Tus favoritas' : 'Motos';
  $('resultcount').textContent = view === 'saved' ? `${num(list.length)} guardadas en este navegador` : `${total > 2000 ? 'Más de 2.000' : num(total)} anuncios${total > items.length ? ` · mostrando ${num(items.length)}` : ''}`;
  $('grid').innerHTML = list.length ? list.map(card).join('') : `<div class="empty"><h3>${view === 'saved' ? 'Aún no tienes favoritas' : 'Ninguna moto con estos filtros'}</h3><p>${view === 'saved' ? 'Pulsa el corazón de una moto para guardarla aquí.' : 'Prueba a quitar algún filtro.'}</p></div>`;
  $('more').hidden = view === 'saved' || items.length >= total;
  const n = Object.keys(diff()).filter(k => !['q', 'orden', 'lat', 'lon'].includes(k)).length;
  $('filtercount').hidden = !n; $('filtercount').textContent = n;
  chips();
}

function chips() {
  const c = [];
  if (S.fin) c.push(['fin', S.fin === 'con' ? 'Con financiación' : 'Sin financiación']);
  if (S.vendedor) c.push(['vendedor', S.vendedor === 'particular' ? 'Particular' : 'Profesional']);
  if (S.pmin || S.pmax) c.push(['precio', `${S.pmin ? euro(+S.pmin) : '0 €'} – ${S.pmax ? euro(+S.pmax) : '∞'}`]);
  S.marca.forEach(m => c.push(['marca:' + m, m]));
  if (S.modelo) c.push(['modelo', 'Modelo: ' + S.modelo]);
  S.tipo.forEach(t => c.push(['tipo:' + t, TIPOS[t] || t]));
  S.a2.forEach(t => c.push(['a2:' + t, A2[t][0]]));
  if (S.kmmax) c.push(['kmmax', '≤ ' + num(+S.kmmax) + ' km']);
  if (S.amin || S.amax) c.push(['anio', `Año ${S.amin || '…'}–${S.amax || '…'}`]);
  if (S.ccmin || S.ccmax) c.push(['cc', `${S.ccmin || 0}–${S.ccmax || '∞'} cc`]);
  if (S.provincia) c.push(['provincia', S.provincia]);
  if (S.fuente) c.push(['fuente', FUENTES[S.fuente]]);
  if (S.envio) c.push(['envio', 'Con envío']);
  if (S.lat != null && S.radio) c.push(['geo', `A ≤ ${S.radio} km`]);
  $('activechips').innerHTML = c.map(([k, t]) => `<button data-k="${esc(k)}">${esc(t)} ${icon('close')}</button>`).join('');
}
$('activechips').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  const [k, v] = b.dataset.k.split(/:(.*)/s);
  if (v !== undefined) S[k] = S[k].filter(x => x !== v);
  else if (k === 'precio') {S.pmin = S.pmax = ''}
  else if (k === 'anio') {S.amin = S.amax = ''}
  else if (k === 'cc') {S.ccmin = S.ccmax = ''}
  else if (k === 'geo') {S.lat = S.lon = null; S.radio = ''}
  else S[k] = DEF[k];
  fillFilters(); changed();
});

function toast(m) {const t = $('toast'); t.textContent = m; t.classList.remove('hidden'); clearTimeout(t._t); t._t = setTimeout(() => t.classList.add('hidden'), 3500)}

let bound = false;
async function start() {
  if (!TOKEN) return showGate();
  try {
    const v = await rpc('validar', {});
    store.set('garage-token', TOKEN);
    OPC = await rpc('opciones', {}) || {};
    $('gate').hidden = true; $('app').hidden = false; $('topnav').hidden = false;
    $('who').textContent = v && v.nombre ? 'Hola, ' + v.nombre : '';
    $('adminlink').hidden = !store.get('garage-admin');  // solo en navegadores donde ya se entró al panel
    const act = OPC.actualizado ? new Date(OPC.actualizado) : null;
    $('eyebrow').textContent = act ? `Actualizado el ${act.toLocaleDateString('es-ES', {day: 'numeric', month: 'long'})} a las ${act.toLocaleTimeString('es-ES', {hour: '2-digit', minute: '2-digit'})}` : 'Sin datos todavía';
    const F = OPC.fuentes || {};
    $('stats').innerHTML = [['Anuncios', num(OPC.total || 0), 'activos ahora'], ['Wallapop', num(F.wallapop || 0), 'anuncios'], ['Milanuncios', num(F.milanuncios || 0), 'anuncios'], ['motos.net y otras', num(Object.entries(F).filter(([k]) => k !== 'wallapop' && k !== 'milanuncios').reduce((t, [, n]) => t + n, 0)), `${Object.keys(F).length - 2} webs más`]]
      .map(([a, b, c]) => `<div class="stat"><small>${a}</small><strong class="num">${b}</strong><span>${c}</span></div>`).join('');
    fillFilters();
    if (!bound) {bindInputs(); bound = true}
    saveFavs(); setView('all'); movePill(); load(false);
  } catch (e) {
    if (e.message === 'token') {store.set('garage-token', null); return showGate(TOKEN ? 'Ese código no es válido o ha caducado.' : '')}
    showGate(e.message === 'limite' ? 'Demasiadas consultas en la última hora. Prueba más tarde.' : 'No se ha podido conectar. Revisa la conexión e inténtalo de nuevo.');
  }
}
addEventListener('resize', movePill);
addEventListener('scroll', () => $('topbar').classList.toggle('scrolled', scrollY > 8), {passive: true});
start();
