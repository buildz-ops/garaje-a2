# Garage · buscador privado de motos

Buscador de motos de segunda mano de toda España (Wallapop, Milanuncios y motos.net) para un grupo cerrado.
Solo se entra con un token personal que genera el administrador.

```
GitHub Actions (cron diario) ──► Supabase (PostgreSQL + funciones) ◄── web estática en Vercel
        scraper/                       supabase/schema.sql                  web/
```

- **scraper/**: Python 3 sin dependencias (usa `curl`). `main.py` recorre las tres webs, guarda en Supabase
  y desactiva lo que ya no está publicado. Solo abre la ficha de Wallapop de los anuncios nuevos o modificados.
- **supabase/schema.sql**: tablas, tokens y funciones. Las tablas tienen RLS sin políticas: la clave pública no lee nada.
  La web solo puede llamar a `validar`, `opciones` y `buscar`, y todas exigen un token válido (con límite de consultas por hora).
- **web/**: la página (HTML + JS sin build). `config.js` lleva la URL y la clave *pública* de Supabase.

## Tokens (desde el SQL Editor de Supabase)

```sql
select crear_token('Juan');                 -- 365 días, 300 consultas/hora. Devuelve el token UNA sola vez
select crear_token('Marta', 30, 200);       -- 30 días, 200 consultas/hora
select revocar_token('Juan');               -- corta el acceso
select nombre, creado, caduca, revocado, usos, ultimo_uso from tokens order by creado;
```

El enlace que se reparte es `https://<web>/?t=<token>`. La página guarda el token en ese navegador y lo quita de la barra de direcciones.

## Secretos del repositorio (Settings → Secrets and variables → Actions)

- `SUPABASE_KEY`: la *secret key* (o la `service_role` antigua) de Supabase → Project Settings → API Keys.

## Ejecutar a mano

Actions → «Actualizar anuncios» → Run workflow. Se puede limitar a una fuente (`--solo motosnet`) o
limitar las fichas de Wallapop para probar (`--max-fichas 200`).

```bash
cd scraper && SUPABASE_KEY=... python3 main.py --solo motosnet
```

## Desplegar la web

```bash
VERCEL_TOKEN=... python3 web/deploy.py
```
