"""Wallapop: toda la categoría Motos (14000) de España, recorrida por tramos de precio con su API de búsqueda.
La búsqueda no trae marca, modelo, km ni año: se abre la ficha (/items/{id}) solo de los anuncios nuevos o modificados.
El tipo de vendedor (particular/tienda) sale del perfil (/users/{id}), que se guarda en caché 60 días."""
import json, re, time, datetime, urllib.parse
from collections import Counter
from red import getjson, pmap, log
import normaliza as N
import db

FUENTE = 'wallapop'
API = 'https://api.wallapop.com/api/v3'
H = {'X-DeviceOS': '0', 'Accept': 'application/json'}
UA = 'Mozilla/5.0'
TRAMOS = [150, 400, 700, 1000, 1300, 1600, 2000, 2400, 2800, 3200, 3600, 4000, 4400, 4800, 5300, 5800, 6500, 7300, 8200, 9500,
          11000, 13000, 15500, 19000, 25000, 1000000]


def wget(u):
    return getjson(u, headers=H, ua=UA, timeout=30, tries=5)


def tramo(ab):
    a, b = ab
    q = dict(source='search_box', category_id=14000, min_sale_price=a, max_sale_price=b, order_by='newest')
    u = f'{API}/search?' + urllib.parse.urlencode(q); out = {}; ok = True; pags = 0
    while u:
        d = wget(u)
        if not d:
            ok = False; break
        its = (((d.get('data') or {}).get('section') or {}).get('payload') or {}).get('items') or []
        for it in its:
            out[it['id']] = it
        np = (d.get('meta') or {}).get('next_page'); pags += 1
        u = f'{API}/search?' + urllib.parse.urlencode({'next_page': np, 'source': 'search_box'}) if np and its else None
    log(FUENTE, f'tramo {a}-{b}', len(out), 'anuncios', pags, 'páginas', '' if ok else 'INCOMPLETO')
    return out, ok


def es_pro(u):
    st = ((u.get('seller_type') or {}).get('type') or '').lower()
    return st in ('shop', 'pro', 'business', 'professional') or (u.get('badge_type') or '').lower() in ('shop', 'pro', 'business')


def perfil(uid):
    d = wget(f'{API}/users/{uid}')
    if not d:
        return None
    pro = es_pro(d)
    nombre = re.sub(r'\s+[A-Z]\.?$', '', (d.get('micro_name') or '').strip()) if pro else None
    return dict(id=uid, profesional=pro, nombre=nombre)


def ts(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).isoformat() if ms else None


def fila(it, d, vend):
    ta = (d or {}).get('type_attributes') or {}
    g = lambda k: (ta.get(k) or {}).get('value')
    titulo = (it.get('title') or '').strip()
    desc = it.get('description') or ''
    texto = titulo + ' \n ' + desc
    marca = N.marca_canon(g('brand')) if g('brand') else N.marca_de(titulo)
    modelo = (g('model') or '').strip() or None
    km = g('km'); anio = g('year')
    km = int(km) if km and str(km).isdigit() else N.km_de(texto)
    anio = int(anio) if anio and str(anio).isdigit() else N.anio_de(texto)
    estilo = g('motorbike_style')
    tipo = N.TIPOS_WP.get(estilo) if estilo else None
    tipo = tipo or N.tipo_de(f'{modelo or ""} {titulo}')
    cc = N.cc_de(texto) or N.cc_modelo(modelo)
    pro = bool(vend and vend[0])
    fin, cuota = N.financiacion_de(texto) if pro else (False, None)
    loc = it.get('location') or {}
    img = None
    if it.get('images'):
        urls = it['images'][0].get('urls') or {}
        img = urls.get('medium') or urls.get('big') or urls.get('small')
    p = (it.get('price') or {}).get('amount') if isinstance(it.get('price'), dict) else it.get('price')
    return dict(id='wp-' + it['id'], fuente=FUENTE, url='https://es.wallapop.com/item/' + it['web_slug'], titulo=titulo,
                descripcion=N.limpia(desc, 250), marca=marca, modelo=modelo, tipo=tipo, anio=anio, km=km, cc=cc, cv=None,
                a2=N.a2_de(None, texto), precio=int(p) if p else None, vendedor='profesional' if pro else 'particular',
                nombre_vendedor=vend[1] if pro else None, financiacion=fin, cuota=cuota,
                garantia=bool((it.get('has_warranty') or {}).get('flag')) or None,
                envio=bool((it.get('shipping') or {}).get('user_allows_shipping')), provincia=loc.get('region2'), ciudad=loc.get('city'),
                lat=round(loc['latitude'], 2) if loc.get('latitude') else None, lon=round(loc['longitude'], 2) if loc.get('longitude') else None,
                imagen=img, publicado=ts(it.get('created_at')), modificado=it.get('modified_at'), grupo=None)


def leer(limite_fichas=None, minutos=None):
    """Recorre, guarda y devuelve (leídos, guardados, completo). Escribe en la base de datos por lotes.
    minutos: tiempo máximo para abrir fichas; lo que no dé tiempo se abre en la pasada siguiente."""
    t0 = time.time()
    res = pmap(tramo, list(zip([0] + TRAMOS[:-1], TRAMOS)), 4)
    items = {}; completo = all(ok for _, ok in res)
    for out, _ in res:
        items.update(out)
    leidos = len(items)
    items = {i: it for i, it in items.items() if not (it.get('reserved') or {}).get('flag') and not N.no_es_moto(it.get('title'))
             and ((it.get('price') or {}).get('amount') or 0) >= 300}
    log(FUENTE, 'leídos', leidos, 'motos', len(items))
    known = db.conocidos(FUENTE)
    # todo lo que sigue publicado y ya está en la base se marca como visto, haya cambiado o no
    vistos = [('wp-' + i) for i in items if ('wp-' + i) in known]
    nuevos = [it for i, it in items.items() if ('wp-' + i) not in known or known['wp-' + i] != it.get('modified_at')]
    nuevos.sort(key=lambda it: -(it.get('modified_at') or 0))   # primero lo más reciente
    if limite_fichas:
        nuevos = nuevos[:limite_fichas]
    log(FUENTE, 'ya conocidos', len(vistos), 'nuevos o modificados', len(nuevos))
    db.tocar(vistos)
    # Perfil solo de quien tiene 3 o más motos publicadas: los particulares casi nunca; las tiendas, sí.
    por_usuario = Counter(it['user_id'] for it in items.values())
    vend = {k: tuple(v) for k, v in (db.rpc('vendedores') or {}).items()}
    faltan = sorted({it['user_id'] for it in nuevos if por_usuario[it['user_id']] >= 3} - set(vend))
    log(FUENTE, 'perfiles a consultar', len(faltan))
    guardados = 0
    for i in range(0, len(faltan), 2000):
        ps = [p for p in pmap(perfil, faltan[i:i + 2000], 8) if p]
        if ps:
            db.rpc('vendedores', p=ps)
        vend.update({p['id']: (p['profesional'], p['nombre']) for p in ps})
    for i in range(0, len(nuevos), 1000):
        if minutos and time.time() - t0 > minutos * 60:
            log(FUENTE, 'tiempo agotado: quedan', len(nuevos) - i, 'fichas para la próxima pasada')
            break
        bloque = nuevos[i:i + 1000]
        fichas = pmap(lambda it: wget(f"{API}/items/{it['id']}"), bloque, 8)
        filas = [fila(it, d, vend.get(it['user_id'])) for it, d in zip(bloque, fichas) if d]
        guardados += db.guardar(filas)
        log(FUENTE, 'fichas', i + len(bloque), '/', len(nuevos), 'guardadas', guardados)
    return leidos, guardados + len(vistos), completo
