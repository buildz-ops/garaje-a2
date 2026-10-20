"""Normalización común a todas las fuentes: marca, modelo, tipo, cilindrada, A2, financiación y limpieza de texto."""
import re, unicodedata

# Marca canónica a partir de variantes escritas por la gente (clave: texto normalizado sin espacios ni guiones)
MARCAS = {
    'honda': 'Honda', 'yamaha': 'Yamaha', 'kawasaki': 'Kawasaki', 'suzuki': 'Suzuki', 'bmw': 'BMW', 'ktm': 'KTM', 'ducati': 'Ducati',
    'triumph': 'Triumph', 'harleydavidson': 'Harley-Davidson', 'harley': 'Harley-Davidson', 'aprilia': 'Aprilia', 'piaggio': 'Piaggio',
    'vespa': 'Vespa', 'kymco': 'Kymco', 'sym': 'SYM', 'husqvarna': 'Husqvarna', 'benelli': 'Benelli', 'cfmoto': 'CFMoto', 'cf': 'CFMoto',
    'royalenfield': 'Royal Enfield', 'motoguzzi': 'Moto Guzzi', 'guzzi': 'Moto Guzzi', 'mvagusta': 'MV Agusta', 'gasgas': 'GasGas',
    'beta': 'Beta', 'sherco': 'Sherco', 'rieju': 'Rieju', 'derbi': 'Derbi', 'peugeot': 'Peugeot', 'voge': 'Voge', 'zontes': 'Zontes',
    'macbor': 'Macbor', 'mash': 'Mash', 'hanway': 'Hanway', 'keeway': 'Keeway', 'qj': 'QJMotor', 'qjmotor': 'QJMotor', 'brixton': 'Brixton',
    'daelim': 'Daelim', 'hyosung': 'Hyosung', 'indian': 'Indian', 'montesa': 'Montesa', 'bultaco': 'Bultaco', 'ossa': 'Ossa', 'sanglas': 'Sanglas',
    'mondial': 'Mondial', 'fbmondial': 'Mondial', 'bajaj': 'Bajaj', 'tvs': 'TVS', 'super73': 'Super73', 'surron': 'Sur-Ron', 'silence': 'Silence',
    'niu': 'NIU', 'zero': 'Zero', 'energica': 'Energica', 'mutt': 'Mutt', 'swm': 'SWM', 'fantic': 'Fantic', 'malaguti': 'Malaguti', 'italjet': 'Italjet',
    'lambretta': 'Lambretta', 'gilera': 'Gilera', 'cagiva': 'Cagiva', 'bimota': 'Bimota', 'buell': 'Buell', 'tm': 'TM', 'yamasaki': 'Yamasaki',
    'orcal': 'Orcal', 'lexmoto': 'Lexmoto', 'ural': 'Ural', 'kove': 'Kove', 'colove': 'Kove', 'morbidelli': 'Morbidelli', 'wottan': 'Wottan',
    'motron': 'Motron', 'vmoto': 'Vmoto', 'askoll': 'Askoll', 'segway': 'Segway', 'horwin': 'Horwin', 'kawa': 'Kawasaki', 'bmv': 'BMW',
    'polaris': 'Polaris', 'canam': 'Can-Am', 'linhai': 'Linhai', 'goes': 'Goes', 'tgb': 'TGB', 'access': 'Access', 'masai': 'Masai',
    'ajp': 'AJP', 'husaberg': 'Husaberg', 'vent': 'Vent', 'nacional': 'Nacional Motor', 'puch': 'Puch', 'mobylette': 'Mobylette',
}
_MK = sorted(MARCAS, key=len, reverse=True)


def clave(s):
    s = unicodedata.normalize('NFKD', (s or '').lower()).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', s)


def marca_de(texto):
    """Marca canónica si el texto empieza por (o contiene como palabra) una marca conocida."""
    t = unicodedata.normalize('NFKD', (texto or '').lower()).encode('ascii', 'ignore').decode()
    palabras = re.findall(r'[a-z0-9]+', t)
    for n in (3, 2, 1):  # «harley davidson», «royal enfield», «moto guzzi»…
        for i in range(len(palabras) - n + 1):
            k = ''.join(palabras[i:i + n])
            if k in MARCAS and (n > 1 or len(k) > 2 or i == 0):
                return MARCAS[k]
    return None


def marca_canon(m):
    k = clave(m)
    return MARCAS.get(k) or (m.strip().title() if m and m.strip() else None)


# Tipo de moto. Valores: naked, deportiva, trail, scooter, custom, touring, campo, clasica, ciclomotor, electrica, quad, otra
TIPOS_WP = {'naked': 'naked', 'sportbike': 'deportiva', 'sport': 'deportiva', 'scooter': 'scooter', 'custom': 'custom', 'chopper': 'custom',
            'touring': 'touring', 'road_bike': 'touring', 'trail': 'trail', 'adventure': 'trail', 'enduro': 'campo', 'off_road': 'campo',
            'motocross': 'campo', 'trial': 'campo', 'supermotard': 'campo', 'classic': 'clasica', 'vintage': 'clasica', 'moped': 'ciclomotor',
            'quad': 'quad', 'atv': 'quad', 'electric': 'electrica', 'maxi_scooter': 'scooter', 'supermoto': 'campo',
            'cruiser': 'custom', 'trike': 'otra', 'naked_sport': 'naked', 'café_racer': 'clasica', 'cafe_racer': 'clasica',
            'scrambler': 'naked', 'big_trail': 'trail', 'sport_touring': 'touring', 'minimoto': 'otra', 'pit_bike': 'campo'}
_TIPO_RX = [
    ('scooter', r'\b(?:t-?max|x-?max|n-?max|x-?city|majesty|pcx|forza|sh\s?\d|scoopy|burgman|address|agility|people|dink|downtown|x-?town|xciting|'
                r'liberty|beverly|medley|zip|typhoon|mp3|x-?evo|vespa|gts|primavera|sprint|lambretta|c\s?400|c\s?650|xadv|x-adv|adv\s?350|'
                r'symphony|jet\s?\d|cruisym|maxsym|joymax|fiddle|orbit|ak\s?550|scooter|lead\s?\d|vision|cityline|kisbee|tweet|django|metropolis)\b'),
    ('ciclomotor', r'\b(?:ciclomotor|49\s?cc|50\s?cc|mobylette|vespino|booster|aerox|ovetto|neo\'?s|sr\s?50|senda|drd|mrt|rs\s?50|rx\s?50|tzr\s?50)\b'),
    ('campo', r'\b(?:enduro|motocross|cross|trial|supermotard|supermoto|exc|sx-?f|yz\s?\d|yzf\s?2[05]0|crf\s?\d{3}\s?(?:r|rx|f)\b|kx\s?\d|rmz|'
              r'smc|te\s?\d|fe\s?\d|tc\s?\d|ec\s?\d|mc\s?\d|cota|evo\s?\d|rr\s?\d{3}|wr\s?\d{3}|smr|sm\s?\d)\b'),
    ('trail', r'\b(?:gs\b|adventure|africa\s?twin|transalp|tenere|t[eé]n[eé]r[eé]|v-?strom|dl\s?\d{3}|tiger|versys|multistrada|desert\s?x|'
              r'tracer|nc\s?7[05]0\s?x|cb\s?500\s?x|crf\s?1[01]00|crf\s?300\s?l|himalayan|norden|trail|tuareg|stelvio|varadero|'
              r'xt\s?\d{3}|klr|dr\s?\d{3}|ktm\s?\d{3}\s?adv|super\s?adventure|ruta)\b'),
    ('custom', r'\b(?:custom|chopper|bobber|cruiser|drag\s?star|virago|shadow|rebel|intruder|boulevard|vulcan|marauder|v-?star|'
               r'sportster|softail|dyna|fat\s?boy|street\s?bob|iron\s?883|bolt|xv\s?\d{3}|vn\s?\d{3}|meteor|super\s?meteor|bonneville\s?bobber)\b'),
    ('deportiva', r'\b(?:cbr|gsx-?r|yzf-?r|r\s?[1367]\b|r\s?125\b|ninja|zx-?\d+r?|panigale|rsv4|rs\s?660|rs\s?125|rc\s?\d{3}|daytona|'
                  r'sv\s?650\s?s|gsx\s?650\s?f|fazer|deportiva|hayabusa|s\s?1000\s?rr|vfr)\b'),
    ('touring', r'\b(?:goldwing|gold\s?wing|gtr|fjr|rt\b|k\s?1[26]00\s?gt|pan\s?european|deauville|electra\s?glide|road\s?king|'
                r'street\s?glide|road\s?glide|ultra|tourer|touring|nt\s?1100)\b'),
    ('clasica', r'\b(?:cl[aá]sica|vintage|restaurad|bultaco|ossa|sanglas|montesa\s+impala|lambretta|años\s?[5-8]0)\b'),
    ('naked', r'\b(?:naked|mt-?\d{2}|z\s?\d{3,4}|cb\s?\d{3}\s?(?:r|f|n|hornet)|hornet|duke|monster|street\s?triple|speed\s?triple|'
              r'trident|sv\s?650|gladius|bandit|gsx-?s|gsx-?8s|xj\s?6|er-?6n|fz\s?\d|s\s?1000\s?r|f\s?900\s?r|tuono|shiver|'
              r'brutale|streetfighter|speed\s?four|cb\s?1000|cb\s?650|cb\s?750|xsr|street\s?scrambler|scrambler|svartpilen|vitpilen|cbf|naked)\b'),
]


def tipo_de(texto, cc=None):
    t = (texto or '').lower()
    if re.search(r'el[eé]ctric', t):
        return 'electrica'
    for tipo, rx in _TIPO_RX:
        if re.search(rx, t):
            return tipo
    if cc and cc <= 50:
        return 'ciclomotor'
    return None


def cc_de(texto):
    """Cilindrada explícita («650 cc», «cc: 649») o, si no, el número de modelo plausible (Z900 -> 900)."""
    t = (texto or '').lower()
    m = re.search(r'(\d{2,4})\s*(?:cc|cm3|c\.c\.)\b', t)
    if m and 45 <= int(m.group(1)) <= 2500:
        return int(m.group(1))
    return None


def cc_modelo(modelo):
    for n in re.findall(r'(?<![\d.,])(\d{2,4})(?![\d.,])', modelo or ''):
        n = int(n)
        if n in (49, 50) or 100 <= n <= 1950:
            return n
    return None


def a2_de(cv, texto=''):
    """apta: ≤ 35 kW (47,6 CV) o declara limitada; limitable: potencia de origen ≤ 70 kW (95 CV); no: más de 70 kW."""
    t = (texto or '').lower()
    limitada = re.search(r'(?<!no )(?<!sin )limitad[ao]\s*(?:para|a|al|en)?\s*(?:el\s*)?(?:carnet\s*)?(?:a2|35\s*kw)|versi[oó]n\s*a2|\b35\s*kw\b|47[,.]\d\s*cv', t)
    if cv is None:
        return 'apta' if limitada else None
    if cv <= 48:
        return 'apta'
    if cv <= 95.2:
        return 'apta' if limitada else 'limitable'
    return 'no'


_TEL = re.compile(r'(?:\+?34[\s.-]?)?(?:[6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}|[6789]\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2})')
_MAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')


def limpia(texto, n=600):
    """Recorta la descripción y quita teléfonos y correos (datos personales que no hacen falta para buscar)."""
    t = _MAIL.sub('[email]', _TEL.sub('[tel]', texto or ''))
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:n] or None


def financiacion_de(texto):
    """(True, cuota mensual o None) si el anuncio ofrece financiación."""
    tl = (texto or '').lower()
    if not re.search(r'financ|cuota|€\s*/\s*mes|eur\s*/\s*mes|al mes\b|\b\d+\s*meses', tl) or re.search(r'no\s+(?:se\s+)?financi|sin\s+financi', tl):
        return False, None
    m = re.search(r'(?:desde|cuota[s]?\s*(?:de|desde)?)\s*(\d{2,3}(?:[.,]\d{1,2})?)\s*(?:€|eur|euros)\s*(?:/|al|por)?\s*mes', tl) \
        or re.search(r'(\d{2,3}(?:[.,]\d{1,2})?)\s*(?:€|eur)\s*/\s*mes', tl)
    cuota = float(m.group(1).replace(',', '.')) if m else None
    return bool(re.search(r'financ', tl) or cuota), cuota


def anio_de(texto):
    m = re.search(r'(?:a[ñn]o|matriculad[ao][^0-9]{0,20}|del)\s*:?\s*((?:19[5-9]|20[0-2])\d)\b', (texto or '').lower())
    return int(m.group(1)) if m else None


def km_de(texto):
    v = []
    for m in re.finditer(r'(\d{1,3}(?:[.,]\d{3})+|\d{2,6})\s*(?:km|kms|kil[oó]metros)\b', (texto or ''), re.I):
        x = int(re.sub(r'[.,]', '', m.group(1)))
        if 10 <= x <= 300000:
            v.append(x)
    return max(v) if v else None


def no_es_moto(titulo, desc=''):
    """Recambios, accesorios y ropa que la gente publica en la categoría de motos."""
    t = (titulo or '').lower()
    return bool(re.search(r'\b(?:ba[uú]l|casco|chaqueta|cazadora|guantes|botas|mono\b|pantal[oó]n|maleta|alforja|top\s?case|escape|tubo de escape|'
                          r'llanta|neum[aá]tico|rueda|carenado|faro|piloto trasero|intermitente|espejo|manillar|asiento|sill[ií]n|'
                          r'despiece|recambio|piezas|motor de|centralita|bater[ií]a|cargador|funda|soporte|caballete|portamatr|'
                          r'remolque|portamotos|cupula|c[uú]pula|defensas|kit de|juego de|horquilla|amortiguador|disco de freno|pastillas|'
                          r'cadena|pi[nñ][oó]n|corona|carburador|radiador|dep[oó]sito|guardabarros|protector|alarma|candado|intercomunicador|'
                          r'cardo|sena|gopro|puños|maneta|retrovisor|matr[ií]cula|silenciador|akrapovic)\b', t)) \
        and not re.search(r'\b(?:vendo|moto|motocicleta)\s+(?:honda|yamaha|kawasaki|suzuki|bmw|ktm|ducati|triumph)\b', t)
