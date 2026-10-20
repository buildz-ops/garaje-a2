"""Milanuncios: categoría Motos (14) de toda España con su API de búsqueda (searchapi.gw.milanuncios.com).
La API corta en 10.000 resultados por consulta, así que se parte por tramos de precio hasta que cada tramo cabe.
El listado ya trae km, año, cilindrada, descripción y tipo de vendedor: no se abren fichas."""
import re, datetime, urllib.parse
from red import getjson, pmap, log
import normaliza as N
import db

FUENTE = 'milanuncios'
API = 'https://searchapi.gw.milanuncios.com/v3/classifieds?'
NO_MOTO = {'Recambios y despieces', 'Accesorios para motos', 'Ropa para motos', 'Cascos', 'Accesorios', 'Recambios'}
SUBCAT = {'Motos de cross': 'campo', 'Motos de enduro': 'campo', 'Motos de trial': 'campo', 'Scooters': 'scooter', 'Motos clásicas': 'clasica',
          'Ciclomotores': 'ciclomotor', 'Quads': 'quad', 'Motos custom': 'custom', 'Motos eléctricas': 'electrica'}


def q(a, b, off=0, limit=50):
    return getjson(API + urllib.parse.urlencode({'category': 14, 'priceFrom': a, 'priceTo': b, 'limit': limit, 'offset': off,
                                                 'transaction': 'supply'}),
                   headers={'Accept': 'application/json'}, ua='Mozilla/5.0', tries=5)


def total(a, b):
    d = q(a, b, limit=1)
    if not d:
        return None
    t = d['pagination']['totalHits']
    return t['value'] + (1 if t.get('relation') == 'gte' else 0)


def tramos(a=300, b=1000000):
    """Parte [a, b] hasta que cada tramo tiene menos de 9.500 anuncios."""
    t = total(a, b)
    if t is None:
        return [(a, b, None)]
    if t < 9500 or b - a <= 10:
        return [(a, b, t)]
    m = (a + b) // 2 if b < 1000000 else 20000
    return tramos(a, m) + tramos(m + 1, b)


def leer_tramo(tr):
    a, b, t = tr
    out = {}; ok = t is not None
    for off in range(0, min(t or 0, 10000), 50):
        d = q(a, b, off)
        if not d:
            ok = False; continue
        for x in d.get('ads') or []:
            out[x['id']] = x
    log(FUENTE, f'tramo {a}-{b}', t, '->', len(out), '' if ok else 'INCOMPLETO')
    return out, ok


def attr(x, k):
    for a in x.get('attributes') or []:
        if a['field']['raw'] == k:
            try:
                return int(float(a['value']['raw']))
            except Exception:
                return None


def modelo_de(titulo, marca, conocidos):
    """Modelo: el modelo conocido más largo de esa marca que aparece en el título; si no, lo que va tras la marca."""
    ct = N.clave(titulo)
    for m in conocidos.get(marca, []):
        k = N.clave(m)
        if len(k) >= 2 and k in ct:
            return m
    t = re.sub(r'^\s*(?:vendo|se vende|moto)\s+', '', titulo, flags=re.I)
    if ' - ' in t:
        t = t.split(' - ', 1)[1]
    elif marca:
        t = re.sub(r'^.*?\b' + re.escape(marca.split()[0]) + r'\b\s*', '', t, flags=re.I)
    if marca:
        t = re.sub(r'^\s*' + re.escape(marca.split()[0]) + r'\b[\s-]*', '', t, flags=re.I)
    t = re.sub(r'\b(?:19|20)\d\d\b.*$', '', t).strip(' -,.')
    return t[:40] or None


def tipo_de(sub, anio, modelo, titulo, cc):
    t = SUBCAT.get(sub)
    if t == 'clasica' and anio and anio >= 1995:   # mucha gente publica motos modernas en «clásicas»
        t = None
    return t or N.tipo_de(f'{modelo or ""} {titulo}', cc)


def leer():
    trs = tramos()
    log(FUENTE, 'tramos', len(trs), 'total aprox.', sum(t or 0 for _, _, t in trs))
    res = pmap(leer_tramo, trs, 3)
    ads = {}; completo = all(ok for _, ok in res)
    for out, _ in res:
        ads.update(out)
    conocidos = {}
    for marca, ms in (db.rpc('modelos') or {}).items():
        conocidos[marca] = sorted(ms, key=lambda m: len(N.clave(m)), reverse=True)
    filas = []
    for x in ads.values():
        if x.get('transaction') != 'supply':
            continue
        sub = (x.get('categories') or [{}])[-1].get('name') or ''
        titulo = (x.get('title') or '').strip(); desc = x.get('description') or ''
        if sub in NO_MOTO or N.no_es_moto(titulo):
            continue
        p = ((x.get('price') or {}).get('cash') or {}).get('value')
        if not p or p < 300:
            continue
        texto = titulo + ' \n ' + desc
        anio = attr(x, 'year') or N.anio_de(texto)
        marca = N.marca_de(titulo) or N.marca_de(desc[:80])
        modelo = modelo_de(titulo, marca, conocidos) if marca else None
        cc = attr(x, 'cc') or N.cc_de(texto)
        pro = x.get('type') != 'private'
        fin, cuota = N.financiacion_de(texto) if pro else (False, None)
        loc = x.get('location') or {}
        img = None
        for k in ('images', 'pictures', 'photos'):
            if x.get(k):
                i = x[k][0]; img = i if isinstance(i, str) else (i.get('src') or i.get('url') or i.get('imageUrl'))
                break
        upd = x.get('updateDate') or x.get('publicationDate')
        try:
            mod = int(datetime.datetime.fromisoformat(upd.replace('Z', '+00:00')).timestamp() * 1000)
        except Exception:
            mod = None
        u = x.get('url') or ''
        filas.append(dict(id='ma-' + str(x['id']), fuente=FUENTE, url='https://www.milanuncios.com' + u if u.startswith('/') else u,
                          titulo=titulo, descripcion=N.limpia(desc, 250), marca=marca, modelo=modelo,
                          tipo=tipo_de(sub, anio, modelo, titulo, cc), anio=anio,
                          km=attr(x, 'kilometers'), cc=cc, cv=None, a2=N.a2_de(None, texto), precio=int(p),
                          vendedor='profesional' if pro else 'particular', nombre_vendedor=(x.get('authorName') or None) if pro else None,
                          financiacion=fin, cuota=cuota, garantia=None, envio=bool((x.get('shipping') or {}).get('shippable')),
                          provincia=(loc.get('province') or {}).get('name'), ciudad=(loc.get('city') or {}).get('name'), lat=None, lon=None,
                          imagen=img, publicado=x.get('publicationDate'), modificado=mod, grupo=None))
    log(FUENTE, 'leídos', len(ads), 'motos', len(filas))
    return filas, completo
