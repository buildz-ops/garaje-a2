"""motos.net (motos.coches.net): todo el listado de segunda mano, con el JSON que va incrustado en cada página (__INITIAL_PROPS__).
Del listado sale todo lo necesario (marca, modelo, km, año, CV, precio, profesional, financiación), así que no se abren fichas."""
import json, re, datetime
from red import get, pmap, log
import normaliza as N

FUENTE = 'motosnet'
BASE = 'https://motos.coches.net/segunda-mano/'
RX = re.compile(r'window\.__INITIAL_PROPS__\s*=\s*JSON\.parse\("(.*?)"\);', re.S)


def pagina(pg, a=None, b=None):
    q = f'?pg={pg}' + (f'&MinPrice={a}' if a else '') + (f'&MaxPrice={b}' if b else '')
    b = get(f'{BASE}{q}', headers={'Accept-Language': 'es-ES'}, ok=lambda b: RX.search(b) is not None, tries=4)
    if not b:
        return None
    return json.loads(json.loads('"' + RX.search(b).group(1) + '"'))['initialResults']


def ts(s):
    try:
        return datetime.datetime.fromisoformat(s.replace('Z', '+00:00')).isoformat()
    except Exception:
        return None


def fila(x):
    marca = N.marca_canon(x.get('make'))
    titulo = re.sub(r'\s+', ' ', x.get('title') or '').strip()
    modelo = re.sub(r'^' + re.escape(x.get('make') or '') + r'\s*', '', titulo, flags=re.I)
    modelo = re.split(r'\s+Versi[oó]n\b', modelo)[0].strip() or None
    cv = x.get('hp') or None
    loc = x.get('location') or {}
    url = x.get('url') or ''
    return dict(id='mn-' + str(x['id']), fuente=FUENTE, url='https://motos.coches.net' + url if url.startswith('/') else url,
                titulo=titulo, descripcion=None, marca=marca, modelo=modelo, tipo=N.tipo_de(titulo), anio=x.get('year') or None,
                km=x.get('km') if x.get('km') is not None else None, cc=N.cc_de(titulo) or N.cc_modelo(modelo), cv=cv, a2=N.a2_de(cv, titulo),
                precio=x.get('price') or None, vendedor='profesional' if x.get('isProfessional') else 'particular', nombre_vendedor=None,
                financiacion=bool(x.get('isFinanced')), cuota=None, garantia=bool(x.get('hasWarranty')), envio=None,
                provincia=loc.get('mainProvince'), ciudad=loc.get('cityLiteral'), lat=None, lon=None,
                imagen=x.get('img'), publicado=ts(x.get('publicationDate') or x.get('creationDate') or ''), modificado=None, grupo=None)


def tramos(a=0, b=None):
    """El listado deja de dar anuncios nuevos pasada la página 500 (10.000): se parte por precio hasta que cada tramo cabe."""
    r = pagina(1, a, b)
    if not r:
        return None
    if r['totalResults'] < 9500 or (b is not None and b - a <= 50):
        return [(a, b, r['totalPages'], r)]
    m = (a + b) // 2 if b else max(a * 2, 6000)
    izq, der = tramos(a, m), tramos(m + 1, b)
    return None if izq is None or der is None else izq + der


def leer():
    """Devuelve (filas, completo)."""
    trs = tramos()
    if not trs:
        return [], False
    log(FUENTE, 'tramos', [(a, b, n) for a, b, n, _ in trs])
    trabajos = [(pg, a, b) for a, b, n, _ in trs for pg in range(2, n + 1)]
    res = [r for *_, r in trs] + pmap(lambda t: pagina(*t), trabajos, 6)
    fallos = sum(1 for r in res if r is None)
    filas = {}
    for r in res:
        for x in (r or {}).get('items') or []:
            if (x.get('price') or 0) < 300:   # precios de reclamo (1 €, la cuota mensual…)
                continue
            f = fila(x)
            filas[f['id']] = f
    log(FUENTE, 'leídos', len(filas), 'de', trs and sum(r['totalResults'] for *_, r in trs), 'páginas fallidas', fallos)
    return list(filas.values()), fallos <= len(res) * 0.02
