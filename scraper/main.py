"""Pasada diaria del buscador: lee cada fuente, guarda en Supabase, desactiva lo que ya no está publicado y recalcula filtros.
Uso: python3 main.py [--solo motosnet,wallapop,milanuncios] [--max-fichas N]
Variables: SUPABASE_KEY (service_role) o INGEST_KEY."""
import argparse, datetime, sys, threading, traceback
from red import log
import db, motosnet, wallapop, milanuncios


def ahora():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def pasada(nombre, fn):
    inicio = ahora()
    try:
        r = fn()
        if nombre == 'wallapop':
            leidos, guardados, ok = r
        else:
            filas, ok = r
            leidos = len(filas); guardados = db.guardar(filas)
        # Si la pasada no fue completa no se desactiva nada (mejor un anuncio caducado que perder los buenos)
        des = db.rpc('cerrar_pasada', p_fuente=nombre, p_inicio=inicio, p_leidos=leidos, p_guardados=guardados, p_ok=bool(ok and guardados))
        log(nombre, 'OK' if ok else 'INCOMPLETA', 'leídos', leidos, 'guardados', guardados, 'desactivados', des)
        return bool(guardados)
    except Exception as e:
        traceback.print_exc()
        try:
            db.rpc('cerrar_pasada', p_fuente=nombre, p_inicio=inicio, p_leidos=0, p_guardados=0, p_ok=False, p_nota=str(e)[:500])
        except Exception:
            pass
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--solo', default='motosnet,wallapop,milanuncios')
    ap.add_argument('--max-fichas', type=int, default=None, help='límite de fichas nuevas de Wallapop (para pruebas)')
    ap.add_argument('--minutos', type=int, default=240, help='tiempo máximo abriendo fichas de Wallapop (el resto, mañana)')
    a = ap.parse_args()
    if not db.disponible():
        sys.exit('Falta SUPABASE_KEY o INGEST_KEY')
    solo = set(a.solo.split(','))
    res = {}
    hilos = []
    if 'wallapop' in solo:   # la más larga; va en paralelo con las demás (servidores distintos)
        t = threading.Thread(target=lambda: res.__setitem__('wallapop', pasada('wallapop', lambda: wallapop.leer(a.max_fichas, a.minutos))))
        t.start(); hilos.append(t)
    if 'motosnet' in solo:
        res['motosnet'] = pasada('motosnet', motosnet.leer)
    if 'milanuncios' in solo:   # después de motos.net: usa sus modelos para reconocerlos en títulos libres
        res['milanuncios'] = pasada('milanuncios', milanuncios.leer)
    for t in hilos:
        t.join()
    try:
        op = db.rpc('recalcular')
    except Exception as e:
        log('recalcular falló', e); op = None
    log('RESUMEN', res, 'activos', (op or {}).get('total'), (op or {}).get('fuentes'))
    print('OK' if all(res.values()) else 'FALLO ' + ','.join(k for k, v in res.items() if not v))
    sys.exit(0 if any(res.values()) else 1)


if __name__ == '__main__':
    main()
