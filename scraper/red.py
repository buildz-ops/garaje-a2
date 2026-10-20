"""Descargas con curl (respeta el proxy del entorno), reintentos con espera y ejecución en paralelo."""
import json, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, file=sys.stderr, flush=True)


def get(url, headers=None, data=None, timeout=40, tries=4, ua=UA, method=None, ok=None):
    """Cuerpo de la respuesta (str) o None si falla tras los reintentos (espera 2, 4, 8… s; más si hay 429)."""
    cmd = ['curl', '-sL', '--compressed', '-m', str(timeout), '-A', ua, '-w', '\n%{http_code}']
    for k, v in (headers or {}).items():
        cmd += ['-H', f'{k}: {v}']
    if method:
        cmd += ['-X', method]
    if data is not None:
        cmd += ['--data-binary', '@-']
    for i in range(tries):
        try:
            r = subprocess.run(cmd + [url], input=(data.encode() if data is not None else None), capture_output=True, timeout=timeout + 15)
            body, _, code = r.stdout.decode('utf-8', 'replace').rpartition('\n')
            code = int(code or 0)
            if r.returncode == 0 and 200 <= code < 300 and (ok is None or ok(body)):
                return body
            if code in (400, 401, 403, 404, 410):
                if code in (404, 410):
                    return None
                log('HTTP', code, url[:120], body[:200])
                if code != 403:
                    return None
            time.sleep((30 if code == 429 else 2) * (2 ** i))
        except subprocess.TimeoutExpired:
            time.sleep(2 * (2 ** i))
    return None


def getjson(url, **kw):
    def _ok(b):
        try:
            json.loads(b); return True
        except Exception:
            return False
    kw.setdefault('ok', _ok)
    b = get(url, **kw)
    return json.loads(b) if b else None


def pmap(fn, items, n=6):
    with ThreadPoolExecutor(n) as ex:
        return list(ex.map(fn, items))
