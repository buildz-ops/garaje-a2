#!/usr/bin/env python3
# deploy.py — sube la carpeta web/ al proyecto Vercel «garage-buscador» en producción.
# Necesita VERCEL_TOKEN en el entorno (nunca se imprime). Uso: python3 web/deploy.py
import os, sys, time, json, hashlib, urllib.request, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
TEAM = os.environ.get('VERCEL_TEAM', 'ayoubs-projects-2ddf4279')
PROJECT = os.environ.get('VERCEL_PROJECT', 'garage-buscador')
FILES = ['index.html', 'app.js', 'admin.html', 'admin.js', 'config.js', 'garage.css', 'vercel.json', 'robots.txt']
tok = os.environ.get('VERCEL_TOKEN')
if not tok:
    sys.exit('NO_TOKEN')
Q = '?' + urllib.parse.urlencode({'slug': TEAM})


def call(method, path, body=None, headers=None, intentos=5):
    # reintenta errores de red/TLS (p. ej. SSL EOF del proxy) y HTTP 429/5xx con espera 2, 4, 8, 16 s
    h = {'Authorization': 'Bearer ' + tok}
    h.update(headers or {})
    for n in range(intentos):
        req = urllib.request.Request('https://api.vercel.com' + path + Q, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                t = r.read().decode() or '{}'
                return r.status, json.loads(t)
        except urllib.error.HTTPError as e:
            t = e.read().decode(errors='replace')
            try:
                st, j = e.code, json.loads(t)
            except Exception:
                st, j = e.code, {'raw': t[:500]}
            if e.code != 429 and e.code < 500:
                return st, j
            err = f'HTTP {e.code}'
        except (urllib.error.URLError, OSError, ValueError) as e:  # ssl.SSLError y timeouts son OSError
            st, j, err = 0, {'error': repr(e)[:300]}, repr(e)[:200]
        if n < intentos - 1:
            print(f'reintento {n + 1}/{intentos - 1} de {method} {path} tras {err}', flush=True)
            time.sleep(2 ** (n + 1))
    return st, j

man = []
for f in FILES:
    data = open(os.path.join(HERE, f), 'rb').read()
    sha = hashlib.sha1(data).hexdigest()
    st, j = call('POST', '/v2/files', data, {'Content-Type': 'application/octet-stream', 'x-vercel-digest': sha, 'Content-Length': str(len(data))})
    if st not in (200, 201):
        sys.exit(f"subida de {f} falló: HTTP {st} {json.dumps(j)[:300]}")
    man.append({'file': f, 'sha': sha, 'size': len(data)})
    print('subido', f, len(data))
body = json.dumps({'name': PROJECT, 'project': PROJECT, 'target': 'production', 'files': man, 'projectSettings': {'framework': None}}).encode()
st, j = call('POST', '/v13/deployments', body, {'Content-Type': 'application/json'})
if st not in (200, 201):
    sys.exit(f'despliegue falló: HTTP {st} {json.dumps(j)[:500]}')
print('desplegado:', j.get('id'), 'https://' + (j.get('url') or ''), 'estado', j.get('readyState'), 'alias', j.get('alias'))
