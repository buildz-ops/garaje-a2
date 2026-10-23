'use strict';
const $ = id => document.getElementById(id);
const C = window.GARAGE;
const num = n => new Intl.NumberFormat('es-ES', {useGrouping: 'always'}).format(n || 0);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const paths = {search: 'M21 21l-4.3-4.3 M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0', moon: 'M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z', sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z M12 1v2 M12 21v2 M4.2 4.2l1.4 1.4 M18.4 18.4l1.4 1.4 M1 12h2 M21 12h2 M4.2 19.8l1.4-1.4 M18.4 5.6l1.4-1.4', plus: 'M12 5v14 M5 12h14', copy: 'M9 9h10v10H9z M5 15V5h10', share: 'M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7 M12 3v12 M7 8l5-5 5 5', send: 'M22 2 11 13 M22 2l-7 20-4-9-9-4 20-7Z', arrow: 'M4 12h16 M14 6l6 6-6 6'};
const icon = n => `<svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="${paths[n] || paths.arrow}"/></svg>`;
document.querySelectorAll('[data-icon]').forEach(e => e.innerHTML = icon(e.dataset.icon));
const store = {get: k => {try {return localStorage.getItem(k)} catch (e) {return null}}, set: (k, v) => {try {v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v)} catch (e) {}}};
const BASE = location.origin + location.pathname.replace(/admin(\.html)?$/, '');

/* El código de admin es distinto del de búsqueda y se guarda aparte: el enlace del buscador nunca abre el panel */
let TOKEN = new URLSearchParams(location.search).get('t') || store.get('garage-admin');
if (new URLSearchParams(location.search).has('t')) history.replaceState(null, '', location.pathname);

const ERR = {token_invalido: 'token', limite_superado: 'limite', no_admin: 'admin', no_puedes_revocarte: 'yo', nombre_vacio: 'nombre'};
async function rpc(fn, body) {
  const r = await fetch(`${C.url}/rest/v1/rpc/${fn}`, {method: 'POST', headers: {apikey: C.key, 'Content-Type': 'application/json'}, body: JSON.stringify({t: TOKEN, ...body})});
  const j = await r.json().catch(() => null);
  if (!r.ok) {const m = (j && j.message) || ''; throw new Error(Object.entries(ERR).find(([k]) => m.includes(k))?.[1] || 'red')}
  return j;
}
const MSG = {limite: 'Demasiadas consultas en la última hora. Espera un poco.', yo: 'No puedes revocar tu propio acceso.', nombre: 'Pon un nombre.', red: 'No se ha podido conectar. Inténtalo de nuevo.'};
function toast(m) {const t = $('toast'); t.textContent = m; t.classList.remove('hidden'); clearTimeout(t._t); t._t = setTimeout(() => t.classList.add('hidden'), 3500)}

function showGate(msg) {
  $('gate').hidden = false; $('app').hidden = true;
  $('gateerr').textContent = msg || ''; $('gatetoken').focus();
}
$('gateform').addEventListener('submit', e => {
  e.preventDefault();
  let v = $('gatetoken').value.trim(); const m = v.match(/[?&]t=([0-9a-f]+)/i); if (m) v = m[1];
  TOKEN = v; start();
});
$('logout').addEventListener('click', e => {e.preventDefault(); store.set('garage-admin', null); TOKEN = null; showGate()});

const themeBtn = $('theme');
const curTheme = () => document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
const paintTheme = () => themeBtn.innerHTML = icon(curTheme() === 'dark' ? 'sun' : 'moon');
themeBtn.addEventListener('click', () => {const n = curTheme() === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = n; store.set('garage-theme', n); paintTheme()});
paintTheme();

/* ── Fechas ── */
const fecha = d => d ? new Date(d).toLocaleDateString('es-ES', {day: 'numeric', month: 'short', year: 'numeric'}) : '—';
function hace(d) {
  if (!d) return 'nunca';
  const s = (Date.now() - new Date(d)) / 1000;
  if (s < 90) return 'ahora mismo';
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  const dd = Math.round(s / 86400); return dd === 1 ? 'ayer' : `hace ${dd} días`;
}
function estado(t) {
  if (t.revocado) return ['Revocado', 'bad'];
  if (t.caduca && new Date(t.caduca) < new Date()) return ['Caducado', 'warn'];
  return ['Activo', 'good'];
}

/* ── Datos ── */
let D = null, filtro = 'activos';
async function cargar() {
  D = await rpc('admin_tokens', {});
  const activos = D.tokens.filter(t => estado(t)[0] === 'Activo');
  const usos24 = D.tokens.reduce((a, t) => a + (+t.usos_24h || 0), 0);
  const act = D.datos && D.datos.actualizado ? new Date(D.datos.actualizado) : null;
  $('stats').innerHTML = [
    ['Accesos activos', num(activos.length), `${num(D.tokens.length)} creados`],
    ['Búsquedas', num(usos24), 'últimas 24 h'],
    ['Motos', num(D.datos && D.datos.total), 'visibles ahora'],
    ['Anuncios', act ? hace(act) : '—', 'última actualización'],
  ].map(([a, b, c]) => `<div class="stat"><small>${a}</small><strong class="num">${b}</strong><span>${c}</span></div>`).join('');
  pintarTokens(); pintarPasadas();
}

function pintarTokens() {
  const L = D.tokens.filter(t => filtro === 'todos' || estado(t)[0] === 'Activo');
  if (!L.length) {$('tokens').innerHTML = `<div class="empty"><h3>Sin accesos ${filtro === 'activos' ? 'activos' : ''}</h3><p>Crea el primero con el formulario.</p></div>`; return}
  $('tokens').innerHTML = L.map(t => {
    const [e, c] = estado(t), yo = t.id === D.yo;
    return `<article class="tk" data-id="${t.id}">
      <div class="tk-main">
        <div class="tk-name"><b>${esc(t.nombre)}</b>${yo ? '<span class="badge both">Tú</span>' : ''}${t.admin ? '<span class="badge info">Admin</span>' : ''}<span class="badge ${c}">${e}</span></div>
        ${t.nota ? `<p class="tk-nota">${esc(t.nota)}</p>` : ''}
        <dl class="tk-kv">
          <div><dt>Creado</dt><dd>${fecha(t.creado)}</dd></div>
          <div><dt>Caduca</dt><dd>${t.caduca ? fecha(t.caduca) : 'Nunca'}</dd></div>
          <div><dt>Último uso</dt><dd>${hace(t.ultimo_uso)}</dd></div>
          <div><dt>Búsquedas</dt><dd class="num">${num(t.usos_24h)} hoy · ${num(t.usos)} total</dd></div>
          <div><dt>Límite</dt><dd class="num">${num(t.max_hora)}/hora</dd></div>
        </dl>
      </div>
      <div class="tk-acts">
        <select class="select sm" data-act="dias" aria-label="Cambiar caducidad de ${esc(t.nombre)}">
          <option value="">Caducidad…</option><option value="30">30 días desde hoy</option><option value="90">3 meses desde hoy</option><option value="365">1 año desde hoy</option><option value="0">Sin caducidad</option></select>
        <select class="select sm" data-act="max" aria-label="Cambiar límite de ${esc(t.nombre)}">
          <option value="">Límite…</option><option value="100">100/hora</option><option value="300">300/hora</option><option value="1000">1.000/hora</option></select>
        ${yo ? '' : t.revocado
          ? `<button class="btn sm" data-act="reactivar" type="button">Reactivar</button>`
          : `<button class="btn sm danger" data-act="revocar" type="button">Revocar</button>`}
      </div>
    </article>`;
  }).join('');
}

function pintarPasadas() {
  const N = {wallapop: 'Wallapop', milanuncios: 'Milanuncios', motosnet: 'motos.net', mundimoto: 'Mundimoto', autoscout24: 'AutoScout24', cuimo: 'Cüimo', flexibike: 'Flexibike', motores: 'motor.es', mundimotoparticulares: 'Mundimoto Particulares', motick: 'Motick'};
  const F = (D.datos && D.datos.fuentes) || {};
  if (!D.pasadas.length) {$('pasadas').innerHTML = '<p>Todavía no hay ninguna actualización registrada.</p>'; return}
  $('pasadas').innerHTML = `<div class="scrollx"><table class="tbl"><thead><tr><th>Web</th><th>Estado</th><th>Cuándo</th><th>Leídos</th><th>Retirados</th><th>Activos</th></tr></thead><tbody>${
    D.pasadas.map(p => `<tr><td><b>${N[p.fuente] || esc(p.fuente)}</b></td><td><span class="badge ${p.ok ? 'good' : 'bad'}">${p.ok ? 'Correcta' : 'Con fallos'}</span></td><td>${hace(p.fin)}</td><td class="num">${num(p.leidos)}</td><td class="num">${num(p.desactivados)}</td><td class="num">${num(F[p.fuente])}</td></tr>`).join('')
  }</tbody></table></div>`;
}

/* ── Acciones ── */
$('filtro').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  filtro = b.dataset.f; $('filtro').querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
  pintarTokens();
});

$('tokens').addEventListener('click', async e => {
  const b = e.target.closest('button[data-act]'); if (!b) return;
  const card = b.closest('.tk'), id = +card.dataset.id, t = D.tokens.find(x => x.id === id);
  const rev = b.dataset.act === 'revocar';
  if (rev && !confirm(`¿Revocar el acceso de ${t.nombre}? Dejará de poder entrar al momento. Puedes reactivarlo después.`)) return;
  b.disabled = true;
  try {await rpc('admin_revocar', {p_id: id, p_revocado: rev}); toast(rev ? `Acceso de ${t.nombre} revocado` : `Acceso de ${t.nombre} reactivado`); await cargar()}
  catch (err) {fallo(err); b.disabled = false}
});

$('tokens').addEventListener('change', async e => {
  const s = e.target.closest('select[data-act]'); if (!s || s.value === '') return;
  const id = +s.closest('.tk').dataset.id, t = D.tokens.find(x => x.id === id);
  const body = {p_id: id}; if (s.dataset.act === 'dias') body.p_dias = +s.value; else body.p_max_hora = +s.value;
  s.disabled = true;
  try {await rpc('admin_editar', body); toast(`${t.nombre}: ${s.options[s.selectedIndex].text.toLowerCase()}`); await cargar()}
  catch (err) {fallo(err); s.disabled = false; s.value = ''}
});

$('crear').addEventListener('submit', async e => {
  e.preventDefault();
  const nombre = $('c-nombre').value.trim(); if (!nombre) return toast(MSG.nombre);
  $('c-btn').disabled = true;
  try {
    const r = await rpc('admin_crear', {p_nombre: nombre, p_dias: +$('c-dias').value, p_max_hora: +$('c-max').value, p_nota: $('c-nota').value.trim() || null});
    const link = `${BASE}?t=${r.token}`;
    $('ok-nombre').textContent = nombre; $('ok-link').value = link;
    const texto = `Hola ${nombre}, aquí tienes tu acceso a Garage, el buscador de motos: ${link}`;
    $('ok-wa').href = 'https://wa.me/?text=' + encodeURIComponent(texto);
    $('ok-share').hidden = !navigator.share; $('ok-share').onclick = () => navigator.share({title: 'Garage', text: texto}).catch(() => {});
    $('crear').hidden = true; $('ok').hidden = false; $('ok-link').select();
    $('crear').reset();
    await cargar();
  } catch (err) {fallo(err)}
  $('c-btn').disabled = false;
});
$('ok-copy').addEventListener('click', async () => {
  try {await navigator.clipboard.writeText($('ok-link').value)} catch (e) {$('ok-link').select(); document.execCommand('copy')}
  toast('Enlace copiado');
});
$('ok-close').addEventListener('click', () => {$('ok').hidden = true; $('crear').hidden = false; $('ok-link').value = ''; $('c-nombre').focus()});

function fallo(err) {
  if (err.message === 'token' || err.message === 'admin') return start();
  toast(MSG[err.message] || MSG.red);
}

/* ── Arranque ── */
async function start() {
  if (!TOKEN) return showGate();
  try {
    const v = await rpc('validar', {});
    if (!v || !v.admin) {
      store.set('garage-admin', null);
      return showGate('Este código sirve para el buscador, pero no es de administrador.');
    }
    store.set('garage-admin', TOKEN);
    $('who').textContent = 'Hola, ' + v.nombre;
    $('gate').hidden = true; $('app').hidden = false;
    await cargar();
  } catch (e) {
    if (e.message === 'token') {store.set('garage-admin', null); return showGate(TOKEN ? 'Ese código no es válido o ha caducado.' : '')}
    showGate(MSG[e.message] || MSG.red);
  }
}
addEventListener('scroll', () => $('topbar').classList.toggle('scrolled', scrollY > 8), {passive: true});
start();
