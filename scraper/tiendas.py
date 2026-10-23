"""Webs más pequeñas que los tres portales grandes: Mundimoto, Cüimo, AutoScout24, Flexibike y motor.es.
Todas dan el listado completo por API o JSON incrustado, así que no se abren fichas.
Cada lector devuelve (filas, completo), igual que motosnet.leer()."""
import json, re, datetime
from red import get, getjson, pmap, log
import normaliza as N

# Prefijo del código postal -> provincia (para AutoScout24, que solo da CP y ciudad)
CP = {'01': 'Álava', '02': 'Albacete', '03': 'Alicante', '04': 'Almería', '05': 'Ávila', '06': 'Badajoz', '07': 'Baleares', '08': 'Barcelona',
      '09': 'Burgos', '10': 'Cáceres', '11': 'Cádiz', '12': 'Castellón', '13': 'Ciudad Real', '14': 'Córdoba', '15': 'A Coruña', '16': 'Cuenca',
      '17': 'Girona', '18': 'Granada', '19': 'Guadalajara', '20': 'Guipúzcoa', '21': 'Huelva', '22': 'Huesca', '23': 'Jaén', '24': 'León',
      '25': 'Lleida', '26': 'La Rioja', '27': 'Lugo', '28': 'Madrid', '29': 'Málaga', '30': 'Murcia', '31': 'Navarra', '32': 'Ourense',
      '33': 'Asturias', '34': 'Palencia', '35': 'Las Palmas', '36': 'Pontevedra', '37': 'Salamanca', '38': 'Santa Cruz de Tenerife',
      '39': 'Cantabria', '40': 'Segovia', '41': 'Sevilla', '42': 'Soria', '43': 'Tarragona', '44': 'Teruel', '45': 'Toledo', '46': 'Valencia',
      '47': 'Valladolid', '48': 'Vizcaya', '49': 'Zamora', '50': 'Zaragoza', '51': 'Ceuta', '52': 'Melilla'}
TIPOS = {'NAKED': 'naked', 'SPORT': 'deportiva', 'TRAIL': 'trail', 'SCOOTER': 'scooter', 'CUSTOM': 'custom', 'TOURING': 'touring',
         'OFFROAD': 'campo', 'ENDURO': 'campo', 'CROSS': 'campo', 'CLASSIC': 'clasica', 'NEO_RETRO': 'naked', 'MOPED': 'ciclomotor'}


def base(**k):
    """Fila con todos los campos que espera la ingesta; los que no da la web van a None."""
    f = dict(descripcion=None, modelo=None, tipo=None, anio=None, km=None, cc=None, cv=None, a2=None, vendedor='profesional',
             nombre_vendedor=None, financiacion=False, cuota=None, garantia=None, envio=None, provincia=None, ciudad=None,
             lat=None, lon=None, imagen=None, publicado=None, modificado=None, grupo=None)
    f.update(k)
    for c in ('anio', 'km', 'cc', 'precio'):   # columnas enteras: algunas webs mandan 451.6 cc o '2019'
        f[c] = entero(f.get(c))
    titulo = f'{f["marca"] or ""} {f["modelo"] or ""}'.strip()
    f['titulo'] = f.get('titulo') or titulo
    f['tipo'] = f['tipo'] or N.tipo_de(f['titulo'], f['cc'])
    f['cc'] = f['cc'] or N.cc_de(f['titulo']) or N.cc_modelo(f['modelo'])
    f['a2'] = f['a2'] or N.a2_de(f['cv'], f['titulo'])
    return f


def entero(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ── Mundimoto: API pública de su web, 100 por página ─────────────────────────
def mundimoto():
    H = {'Origin': 'https://mundimoto.com', 'Referer': 'https://mundimoto.com/'}
    U = 'https://api.mundimoto.com/mundimoto-api/motorbikes?order_by=default&limit=100&offset={}&country=es&flow=SALE'
    d = getjson(U.format(0), headers=H, timeout=60)
    if not d:
        return [], False
    total = d.get('total_count') or 0
    pags = [d] + pmap(lambda o: getjson(U.format(o), headers=H, timeout=60), range(100, total + 100, 100), 4)
    filas = {}
    for p in pags:
        for x in (p or {}).get('motorbikes') or []:
            if x.get('is_reserved') or x.get('invisible') or (x.get('price') or 0) < 300:
                continue
            lic = x.get('driving_license') or ''
            a2 = 'apta' if x.get('is_limited') or ('A2' in lic and not x.get('is_limitable')) else ('limitable' if x.get('is_limitable') else None)
            img = (x.get('thumbnail_images') or [{}])[0].get('detail')
            f = base(id='mm-' + x['id'], fuente='mundimoto', url=f'https://mundimoto.com/es/moto/{x["id"]}?flow=SALE',
                     marca=N.marca_canon(x.get('brand')), modelo=(x.get('model') or '').strip() or None, anio=x.get('year'), km=x.get('kms'),
                     cc=x.get('cc'), a2=a2, precio=entero(x.get('price')), nombre_vendedor='Mundimoto',
                     financiacion=bool(x.get('quota')), cuota=x.get('quota'), garantia=True, envio=True,
                     tipo=TIPOS.get((x.get('motorbike_type') or '').upper()), imagen=img)
            filas[f['id']] = f
    fallos = sum(1 for p in pags if not p)
    log('mundimoto', 'leídos', len(filas), 'de', total, 'páginas fallidas', fallos)
    return list(filas.values()), fallos == 0 and len(filas) > 0


# ── Cüimo: API de su web (todas las marcas a la vez) ──────────────────────────
# OJO: la API incluye ad.leads (datos de otros clientes). Solo se leen los campos de abajo; nada más se guarda.
CUIMO_TIENDA = {'Madrid': ('Madrid', 'Móstoles'), 'Valencia': ('Valencia', 'Alfafar'), 'Málaga': ('Málaga', 'Málaga')}


def cuimo():
    H = {'Content-Type': 'application/json', 'Origin': 'https://www.cuimo.com', 'Referer': 'https://www.cuimo.com/'}
    body = json.dumps({"criteria": {"randomly": False, "home": False}, "taskLavadoPost": False})
    filas, total, pg = {}, None, 1
    while pg < 40:
        d = getjson(f'https://api.cuimo.com/api/v2/motos/getMotos/200/{pg}', headers=H, data=body, timeout=60)
        if not d:
            return list(filas.values()), False
        ms = d['data']['motos']; total = d['data'].get('total')
        for m in ms:
            ad = m.get('ad') or {}
            if ad.get('status') not in (None, 'visible') or (m.get('price') or 0) < 300:
                continue
            ft = m.get('ficha_tecnica') or {}
            img = (m.get('images') or [{}])[0].get('url')
            f = base(id='cu-' + str(m.get('id') or m.get('_id')), fuente='cuimo', url='https://www.cuimo.com/moto/' + m['slug'],
                     marca=N.marca_canon(m.get('brand')), modelo=(m.get('model') or '').strip().title() or None, anio=m.get('year'), km=m.get('km'),
                     cc=ft.get('cc'), precio=entero(m.get('price')), nombre_vendedor='Cüimo', financiacion=bool(m.get('monthly_payment')),
                     cuota=m.get('monthly_payment'), garantia=True, envio=True, imagen=img,
                     a2='apta' if ft.get('license') == 'A2' else None)
            filas[f['id']] = f
        del d
        if len(ms) < 200:
            break
        pg += 1
    log('cuimo', 'leídos', len(filas), 'de', total)
    return list(filas.values()), len(filas) > 0


# ── AutoScout24: JSON de la página (__NEXT_DATA__), 20 por página ─────────────
AS_RX = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
AS_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'


def as_pagina(pg, a=None, b=None):
    q = f'https://www.autoscout24.es/lst-moto?atype=B&cy=E&sort=age&desc=1&page={pg}' + (f'&pricefrom={a}' if a else '') + (f'&priceto={b}' if b else '')
    h = get(q, ua=AS_UA, ok=lambda h: AS_RX.search(h) is not None)
    return json.loads(AS_RX.search(h).group(1))['props']['pageProps'] if h else None


def autoscout24():
    # El listado no pasa de la página 20 (400 anuncios): se parte por precio
    def tramos(a=0, b=None):
        p = as_pagina(1, a, b)
        if not p:
            return None
        if p['numberOfResults'] <= 400 or (b is not None and b - a <= 100):
            return [(a, b, p)]
        m = (a + b) // 2 if b else max(a * 2, 8000)
        i, d = tramos(a, m), tramos(m + 1, b)
        return None if i is None or d is None else i + d
    trs = tramos()
    if not trs:
        return [], False
    trab = [(pg, a, b) for a, b, p in trs for pg in range(2, min(p['numberOfPages'], 20) + 1)]
    res = [p for *_, p in trs] + pmap(lambda t: as_pagina(*t), trab, 3)
    filas = {}
    for p in res:
        for x in (p or {}).get('listings') or []:
            v = x.get('vehicle') or {}; loc = x.get('location') or {}; tr = x.get('tracking') or {}
            precio = entero((x.get('price') or {}).get('priceRaw'))
            if not precio or precio < 300:
                continue
            reg = tr.get('firstRegistration') or ''
            img = (x.get('images') or [None])[0]
            privado = (x.get('seller') or {}).get('type') == 'PrivateSeller'   # del vendedor solo se mira el tipo: nunca teléfonos
            f = base(id='as-' + x['id'], fuente='autoscout24', url='https://www.autoscout24.es' + x['url'],
                     titulo=x.get('title'), marca=N.marca_canon(v.get('make')), modelo=v.get('model'),
                     anio=entero(reg[-4:]) if reg else None, km=entero(tr.get('mileage')), cc=entero(re.sub(r'\D', '', v.get('engineDisplacementInCCM') or '')),
                     precio=precio, vendedor='particular' if privado else 'profesional',
                     provincia=CP.get((loc.get('zip') or '')[:2]), ciudad=loc.get('city'),
                     imagen=img.replace('/250x188.webp', '/720x540.webp') if img else None)
            filas[f['id']] = f
    fallos = sum(1 for p in res if not p)
    log('autoscout24', 'leídos', len(filas), 'de', sum(p['numberOfResults'] for *_, p in trs), 'páginas fallidas', fallos)
    return list(filas.values()), fallos <= len(res) * 0.05 and len(filas) > 0


# ── Flexibike: GraphQL de su web ─────────────────────────────────────────────
def flexibike():
    Q = """query ($first: Int, $offset: Int) { motos(first: $first, offset: $offset) { totalCount edges { node {
      id marca { marca } modelo { modelo } tipoMoto { nombre } anio kmsActuales precioActual imagenPortada urlDetalle } } } }"""
    filas, off, total = {}, 0, None
    while off < 5000:
        d = getjson('https://flexibike.es/graphql', headers={'Content-Type': 'application/json', 'Referer': 'https://flexibike.es/motos-segunda-mano/'},
                    data=json.dumps({"query": Q, "variables": {"first": 100, "offset": off}}))
        if not d or 'errors' in d:
            return list(filas.values()), False
        e = d['data']['motos']['edges']; total = d['data']['motos']['totalCount']
        for n in (x['node'] for x in e):
            precio = entero(n.get('precioActual'))
            if not precio or precio < 300:
                continue
            u = n.get('urlDetalle') or ''
            f = base(id='fb-' + n['id'], fuente='flexibike', url=u if u.startswith('http') else 'https://flexibike.es' + u,
                     marca=N.marca_canon((n.get('marca') or {}).get('marca')), modelo=((n.get('modelo') or {}).get('modelo') or '').title() or None,
                     anio=entero(n.get('anio')), km=n.get('kmsActuales'), precio=precio, nombre_vendedor='Flexibike', garantia=True,
                     tipo=N.tipo_de((n.get('tipoMoto') or {}).get('nombre') or ''), imagen=n.get('imagenPortada'))
            filas[f['id']] = f
        if len(e) < 100:
            break
        off += 100
    log('flexibike', 'leídos', len(filas), 'de', total)
    return list(filas.values()), len(filas) > 0


# ── motor.es (red de concesionarios de Appmoto): datos en el payload de Next.js, 23 por página ──
ME_RX = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)
ME_ITEM = re.compile(r'\{"id":"[0-9a-f-]{36}","nombre"')


def objetos(s, rx):
    """Objetos JSON completos que empiezan donde casa rx (se cierra contando llaves, respetando cadenas)."""
    for m in rx.finditer(s):
        d, cad, esc = 0, False, False
        for k in range(m.start(), len(s)):
            c = s[k]
            if cad:
                esc = c == '\\' and not esc
                if c == '"' and not esc:
                    cad = False
                continue
            if c == '"':
                cad = True
            elif c == '{':
                d += 1
            elif c == '}':
                d -= 1
                if d == 0:
                    try:
                        yield json.loads(s[m.start():k + 1])
                    except ValueError:
                        pass
                    break


def me_pagina(pg):
    h = get(f'https://www.motor.es/motos/segunda-mano/?pagina={pg}', ok=lambda h: '__next_f' in h)
    if h is None:
        return None
    ps = ME_RX.findall(h)
    return list(objetos(json.loads('"' + max(ps, key=len) + '"'), ME_ITEM)) if ps else []


def motores():
    filas, vacias, fallos, pg = {}, 0, 0, 1
    while pg <= 400 and vacias < 2:
        lote = pmap(me_pagina, range(pg, pg + 12), 4)
        for its in lote:
            if its is None:
                fallos += 1; continue
            vacias = vacias + 1 if not its else 0
            for x in its:
                precio = entero((x.get('precio') or {}).get('venta'))
                if not precio or precio < 300:
                    continue
                v = x.get('vendedor') or {}
                u = (x.get('url_externa') or '').split('?')[0].split('#')[0] or 'https://www.motor.es/motos/segunda-mano/'
                f = base(id='me-' + x['id'], fuente='motores', url=u, titulo=re.sub(r'\s+', ' ', x.get('nombre') or '').strip(),
                         marca=N.marca_canon((x.get('marca') or {}).get('nombre')), modelo=((x.get('modelo') or {}).get('nombre') or '').strip() or None,
                         anio=(x.get('matriculacion') or {}).get('anno'), km=x.get('kilometros'), cc=x.get('cilindrada'), precio=precio,
                         provincia=v.get('provincia'), ciudad=v.get('poblacion'), imagen=x.get('imagen'),
                         publicado=datetime.datetime.fromtimestamp(x['publicado'], datetime.timezone.utc).isoformat() if x.get('publicado') else None)
                filas[f['id']] = f
        pg += 12
    log('motores', 'leídos', len(filas), 'páginas', pg - 1, 'fallidas', fallos)
    return list(filas.values()), fallos <= 3 and len(filas) > 0


LECTORES = {'mundimoto': mundimoto, 'cuimo': cuimo, 'autoscout24': autoscout24, 'flexibike': flexibike, 'motores': motores}
