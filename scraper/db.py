"""Acceso a Supabase solo mediante las funciones RPC del esquema (ingesta, tocar, cerrar_pasada…).
Variables: SUPABASE_URL y SUPABASE_KEY (service_role) o INGEST_KEY (clave de ingesta + clave pública)."""
import json, os
from red import get, log

URL = os.environ.get('SUPABASE_URL', 'https://cgqnhkxykulkeljmqqti.supabase.co').rstrip('/')
SERVICE = os.environ.get('SUPABASE_KEY')
INGEST = os.environ.get('INGEST_KEY')
ANON = os.environ.get('SUPABASE_ANON', 'sb_publishable_IZmF4VwLCCkT32BLbmnUDw_kowxf3kp')
KEY = SERVICE or ANON
K = INGEST or ''


def rpc(fn, **args):
    h = {'apikey': KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}
    if SERVICE and not SERVICE.startswith('sb_'):
        h['Authorization'] = 'Bearer ' + SERVICE
    b = get(f'{URL}/rest/v1/rpc/{fn}', headers=h, data=json.dumps({'k': K, **args}, ensure_ascii=False, default=str), timeout=120, method='POST', tries=4)
    if b is None:
        raise RuntimeError(f'RPC {fn} falló')
    return json.loads(b) if b.strip() else None


def guardar(filas, lote=500):
    n = 0
    for i in range(0, len(filas), lote):
        n += rpc('ingesta', filas=filas[i:i + lote])
    return n


def tocar(ids, lote=5000):
    n = 0; ids = list(ids)
    for i in range(0, len(ids), lote):
        n += rpc('tocar', ids=ids[i:i + lote])
    return n


def conocidos(fuente):
    return {r['id']: r['modificado'] for r in rpc('conocidos', p_fuente=fuente) or []}


def disponible():
    return bool(SERVICE or INGEST)
