-- Garage A2 · buscador universal. Esquema de Supabase (PostgreSQL 17).
-- Las tablas tienen RLS activado y NINGUNA política: la clave pública (anon) no puede leerlas.
-- La web solo puede llamar a buscar() y opciones(), que exigen un token válido.
-- El scraper escribe con ingesta() y cerrar_pasada(), que exigen la service_role o una clave de ingesta.

create extension if not exists pgcrypto with schema extensions;
create extension if not exists pg_trgm with schema extensions;

create table public.anuncios (
  id              text primary key,             -- wp-<id>, ma-<id>, mn-<id>
  fuente          text not null,                -- wallapop | milanuncios | motosnet
  url             text not null,
  titulo          text not null,
  descripcion     text,                         -- recortada y sin teléfonos
  marca           text,
  modelo          text,
  tipo            text,                         -- naked, deportiva, trail, scooter, custom, touring, campo, clasica, ciclomotor, otra
  anio            int,
  km              int,
  cc              int,
  cv              numeric,                      -- potencia de origen si se conoce
  a2              text,                         -- apta | limitable | no | null (desconocido)
  precio          int,
  vendedor        text,                         -- particular | profesional
  nombre_vendedor text,                         -- solo profesionales
  financiacion    boolean not null default false,
  cuota           numeric,
  garantia        boolean,
  envio           boolean,
  provincia       text,
  ciudad          text,
  lat             numeric(6,3),
  lon             numeric(6,3),
  imagen          text,
  publicado       timestamptz,
  modificado      bigint,                       -- marca de la fuente para no repetir fichas
  grupo           text,                         -- misma moto en varias webs
  visto_primero   timestamptz not null default now(),
  visto_ultimo    timestamptz not null default now(),
  activo          boolean not null default true,
  principal       boolean not null default true,   -- false = copia en otra web de una moto que ya se muestra
  modelo_clave    text generated always as (lower(regexp_replace(coalesce(marca,'') || '|' || coalesce(modelo,''), '[^a-zA-Z0-9|]', '', 'g'))) stored,
  busqueda        tsvector generated always as (
                    to_tsvector('simple', coalesce(marca,'') || ' ' || coalesce(modelo,'') || ' ' || titulo)) stored
);
create index on public.anuncios (activo, principal, precio);
create index on public.anuncios (activo, marca);
create index on public.anuncios (activo, principal, visto_primero desc);
create index on public.anuncios (fuente, visto_ultimo);
create index on public.anuncios (grupo);
create index on public.anuncios (modelo_clave);
create index on public.anuncios using gin (busqueda);
create index anuncios_modelo_clave_trgm on public.anuncios using gin (modelo_clave extensions.gin_trgm_ops);
create index anuncios_texto_ts on public.anuncios using gin (to_tsvector('simple',
  regexp_replace(coalesce(marca, '') || ' ' || coalesce(modelo, '') || ' ' || titulo, '[^[:alnum:]]+', ' ', 'g')));
alter table public.anuncios enable row level security;

create table public.vendedores_wp (               -- caché de perfiles de Wallapop (particular/profesional)
  id text primary key, profesional boolean, nombre text, actualizado timestamptz default now());
alter table public.vendedores_wp enable row level security;

create table public.tokens (
  id        bigint generated always as identity primary key,
  hash      text unique not null,               -- sha256 del token; el token en claro no se guarda
  nombre    text not null,
  creado    timestamptz not null default now(),
  caduca    timestamptz,
  revocado  boolean not null default false,
  max_hora  int not null default 300,           -- consultas por hora
  ultimo_uso timestamptz,
  usos      bigint not null default 0
);
alter table public.tokens enable row level security;

create table public.uso (
  token_id bigint references public.tokens on delete cascade,
  hora timestamptz, n int not null default 0, primary key (token_id, hora));
alter table public.uso enable row level security;

create table public.claves_ingesta (hash text primary key, nota text, creado timestamptz default now());
alter table public.claves_ingesta enable row level security;

create table public.pasadas (
  id bigint generated always as identity primary key, fuente text, inicio timestamptz, fin timestamptz,
  leidos int, guardados int, desactivados int, ok boolean, nota text);
alter table public.pasadas enable row level security;

create table public.opciones_cache (id int primary key default 1, datos jsonb, actualizado timestamptz);
alter table public.opciones_cache enable row level security;

revoke all on all tables in schema public from anon, authenticated;

-- ── Tokens ────────────────────────────────────────────────────────────────
create or replace function public._sha(t text) returns text language sql immutable
set search_path = '' as $$ select encode(extensions.digest(t, 'sha256'), 'hex') $$;

-- Valida el token y aplica el límite por hora. Devuelve el id o lanza error.
create or replace function public._token(t text) returns bigint language plpgsql security definer
set search_path = '' as $$
declare tk public.tokens; h timestamptz := date_trunc('hour', now()); n int;
begin
  select * into tk from public.tokens where hash = public._sha(coalesce(t,''));
  if tk.id is null or tk.revocado or (tk.caduca is not null and tk.caduca < now()) then
    raise exception 'token_invalido' using errcode = '28000';
  end if;
  insert into public.uso as u (token_id, hora, n) values (tk.id, h, 1)
    on conflict (token_id, hora) do update set n = u.n + 1 returning u.n into n;
  if n > tk.max_hora then raise exception 'limite_superado' using errcode = '53400'; end if;
  update public.tokens set ultimo_uso = now(), usos = usos + 1 where id = tk.id;
  return tk.id;
end $$;

-- Crea un token y lo devuelve en claro UNA sola vez. Solo desde el SQL editor (no expuesto a la web).
create or replace function public.crear_token(nombre text, dias int default 365, max_hora int default 300)
returns text language plpgsql security definer set search_path = '' as $$
declare t text := encode(extensions.gen_random_bytes(16), 'hex');
begin
  insert into public.tokens (hash, nombre, caduca, max_hora)
  values (public._sha(t), nombre, case when dias is null then null else now() + make_interval(days => dias) end, max_hora);
  return t;
end $$;

create or replace function public.revocar_token(p_nombre text) returns int language sql security definer
set search_path = '' as $$
  with r as (update public.tokens set revocado = true where nombre = p_nombre and not revocado returning 1) select count(*)::int from r $$;

-- ── Lectura para la web ──────────────────────────────────────────────────
create or replace function public.validar(t text) returns jsonb language plpgsql security definer
set search_path = '' as $$
declare tid bigint := public._token(t);
begin
  return (select jsonb_build_object('nombre', tk.nombre, 'caduca', tk.caduca) from public.tokens tk where tk.id = tid);
end $$;

create or replace function public.opciones(t text) returns jsonb language plpgsql security definer
set search_path = '' as $$
begin
  perform public._token(t);
  return (select datos from public.opciones_cache where id = 1);
end $$;

-- f: {q, marca:[...], modelo, tipo:[...], pmin, pmax, kmmax, amin, amax, ccmin, ccmax, a2:[...], vendedor, fin ('con'|'sin'),
--     provincia:[...], lat, lon, radio, envio, orden ('nuevos'|'precio'|'-precio'|'km'|'-anio'), pag, por}
create or replace function public.buscar(t text, f jsonb default '{}') returns jsonb language plpgsql security definer
set search_path = '' as $$
declare
  por int := least(greatest(coalesce((f->>'por')::int, 48), 1), 96);
  pag int := greatest(coalesce((f->>'pag')::int, 1), 1);
  w text := 'a.activo and a.principal';
  dist text := 'null::numeric';
  ord text;
  res jsonb;
  lat numeric := (f->>'lat')::numeric;
  lon numeric := (f->>'lon')::numeric;
  tsq text;
  qk text := lower(regexp_replace(coalesce(f->>'q', ''), '[^[:alnum:]]+', '', 'g'));
  mk text := lower(regexp_replace(coalesce(f->>'modelo', ''), '[^[:alnum:]]+', '', 'g'));
begin
  perform public._token(t);
  -- texto libre: todas las palabras como prefijo («tene» encuentra «tenere»), o el texto junto dentro del modelo («mt07»)
  select string_agg(x || ':*', ' & ') into tsq
  from regexp_split_to_table(lower(regexp_replace(coalesce(f->>'q', ''), '[^[:alnum:]]+', ' ', 'g')), ' ') x where x <> '';
  if tsq is not null then
    w := w || ' and (to_tsvector(''simple'', regexp_replace(coalesce(a.marca,'''') || '' '' || coalesce(a.modelo,'''') || '' '' || a.titulo, ''[^[:alnum:]]+'', '' '', ''g''))'
           || ' @@ to_tsquery(''simple'', $4) or (length($5) >= 3 and a.modelo_clave like ''%'' || $5 || ''%''))';
  end if;
  if jsonb_array_length(coalesce(f->'marca', '[]')) > 0 then w := w || ' and a.marca = any (array(select jsonb_array_elements_text($1->''marca'')))'; end if;
  if jsonb_array_length(coalesce(f->'tipo', '[]')) > 0 then w := w || ' and a.tipo = any (array(select jsonb_array_elements_text($1->''tipo'')))'; end if;
  if jsonb_array_length(coalesce(f->'provincia', '[]')) > 0 then w := w || ' and a.provincia = any (array(select jsonb_array_elements_text($1->''provincia'')))'; end if;
  if jsonb_array_length(coalesce(f->'a2', '[]')) > 0 then w := w || ' and coalesce(a.a2, ''desconocido'') = any (array(select jsonb_array_elements_text($1->''a2'')))'; end if;
  if mk <> '' then w := w || ' and a.modelo_clave like ''%'' || $6 || ''%'''; end if;
  if f ? 'pmin'  then w := w || ' and a.precio >= ($1->>''pmin'')::int'; end if;
  if f ? 'pmax'  then w := w || ' and a.precio <= ($1->>''pmax'')::int'; end if;
  if f ? 'kmmax' then w := w || ' and a.km <= ($1->>''kmmax'')::int'; end if;
  if f ? 'amin'  then w := w || ' and a.anio >= ($1->>''amin'')::int'; end if;
  if f ? 'amax'  then w := w || ' and a.anio <= ($1->>''amax'')::int'; end if;
  if f ? 'ccmin' then w := w || ' and a.cc >= ($1->>''ccmin'')::int'; end if;
  if f ? 'ccmax' then w := w || ' and a.cc <= ($1->>''ccmax'')::int'; end if;
  if f ? 'vendedor' then w := w || ' and a.vendedor = $1->>''vendedor'''; end if;
  if f->>'fin' = 'con' then w := w || ' and a.financiacion'; elsif f->>'fin' = 'sin' then w := w || ' and not a.financiacion'; end if;
  if (f->>'envio')::boolean then w := w || ' and a.envio'; end if;
  if f ? 'fuente' then w := w || ' and a.fuente = $1->>''fuente'''; end if;
  if lat is not null and lon is not null then
    dist := '(2 * 6371 * asin(sqrt(power(sin(radians(a.lat - $2) / 2), 2) + cos(radians($2)) * cos(radians(a.lat)) * power(sin(radians(a.lon - $3) / 2), 2))))';
    if f ? 'radio' then w := w || ' and a.lat is not null and ' || dist || ' <= ($1->>''radio'')::numeric'; end if;
  end if;
  ord := case f->>'orden'
    when 'precio' then 'a.precio asc nulls last, '
    when '-precio' then 'a.precio desc nulls last, '
    when 'km' then 'a.km asc nulls last, '
    when '-anio' then 'a.anio desc nulls last, '
    when 'dist' then (case when dist <> 'null::numeric' then dist || ' asc nulls last, ' else '' end)
    else '' end || 'a.visto_primero desc, a.id';
  execute format($q$
    with pagina as (
      select a.*, %1$s as dist, row_number() over (order by %3$s) rn from public.anuncios a where %2$s order by %3$s limit %4$s offset %5$s)
    select jsonb_build_object(
      'total', (select count(*) from public.anuncios a where %2$s),
      'pag', %6$s, 'por', %4$s,
      'items', coalesce((select jsonb_agg(jsonb_build_object(
          'id', p.id, 'fuente', p.fuente, 'url', p.url, 'titulo', p.titulo, 'descripcion', left(p.descripcion, 300),
          'marca', p.marca, 'modelo', p.modelo, 'tipo', p.tipo, 'anio', p.anio, 'km', p.km, 'cc', p.cc, 'cv', p.cv, 'a2', p.a2,
          'precio', p.precio, 'vendedor', p.vendedor, 'nombre_vendedor', p.nombre_vendedor, 'financiacion', p.financiacion,
          'cuota', p.cuota, 'garantia', p.garantia, 'envio', p.envio, 'provincia', p.provincia, 'ciudad', p.ciudad,
          'imagen', p.imagen, 'publicado', p.publicado, 'visto_primero', p.visto_primero, 'dist', round(p.dist),
          'tambien', (select jsonb_agg(jsonb_build_object('fuente', o.fuente, 'url', o.url, 'precio', o.precio))
                      from public.anuncios o where p.grupo is not null and o.grupo = p.grupo and o.id <> p.id and o.activo)
        ) order by p.rn) from pagina p), '[]'::jsonb))
  $q$, dist, w, ord, por, (pag - 1) * por, pag)
  into res using f, lat, lon, tsq, qk, mk;
  return res;
end $$;

-- ── Escritura para el scraper ────────────────────────────────────────────
create or replace function public._ingesta_ok(k text) returns boolean language sql stable security definer
set search_path = '' as $$
  select session_user in ('postgres', 'supabase_admin')   -- SQL editor / administración
      or coalesce(current_setting('request.jwt.claims', true)::jsonb->>'role', '') = 'service_role'
      or exists (select 1 from public.claves_ingesta where hash = public._sha(coalesce(k,'')))
$$;

-- filas: array de objetos con las columnas de anuncios (sin visto_*/activo). Devuelve cuántas se guardaron.
create or replace function public.ingesta(k text, filas jsonb) returns int language plpgsql security definer
set search_path = '' as $$
declare n int;
begin
  if not public._ingesta_ok(k) then raise exception 'sin_permiso' using errcode = '42501'; end if;
  insert into public.anuncios as a (id, fuente, url, titulo, descripcion, marca, modelo, tipo, anio, km, cc, cv, a2, precio, vendedor,
      nombre_vendedor, financiacion, cuota, garantia, envio, provincia, ciudad, lat, lon, imagen, publicado, modificado, grupo)
  select r.id, r.fuente, r.url, r.titulo, r.descripcion, r.marca, r.modelo, r.tipo, r.anio, r.km, r.cc, r.cv, r.a2, r.precio, r.vendedor,
      r.nombre_vendedor, coalesce(r.financiacion, false), r.cuota, r.garantia, r.envio, r.provincia, r.ciudad, r.lat, r.lon, r.imagen,
      r.publicado, r.modificado, r.grupo
  from jsonb_populate_recordset(null::public.anuncios, filas) r
  on conflict (id) do update set
      url = excluded.url, titulo = excluded.titulo, descripcion = excluded.descripcion, marca = excluded.marca, modelo = excluded.modelo,
      tipo = excluded.tipo, anio = excluded.anio, km = excluded.km, cc = excluded.cc, cv = excluded.cv, a2 = excluded.a2,
      precio = excluded.precio, vendedor = excluded.vendedor, nombre_vendedor = excluded.nombre_vendedor,
      financiacion = excluded.financiacion, cuota = excluded.cuota, garantia = excluded.garantia, envio = excluded.envio,
      provincia = excluded.provincia, ciudad = excluded.ciudad, lat = excluded.lat, lon = excluded.lon, imagen = excluded.imagen,
      publicado = excluded.publicado, modificado = excluded.modificado, grupo = excluded.grupo,
      visto_ultimo = now(), activo = true;
  get diagnostics n = row_count;
  return n;
end $$;

-- Marca como vistos (sin reescribir) los anuncios que siguen publicados y no han cambiado.
create or replace function public.tocar(k text, ids text[]) returns int language plpgsql security definer
set search_path = '' as $$
declare n int;
begin
  if not public._ingesta_ok(k) then raise exception 'sin_permiso' using errcode = '42501'; end if;
  update public.anuncios set visto_ultimo = now(), activo = true where id = any(ids);
  get diagnostics n = row_count; return n;
end $$;

-- Datos que el scraper ya tiene, para no volver a pedir fichas que no han cambiado.
create or replace function public.conocidos(k text, p_fuente text) returns jsonb language plpgsql security definer
set search_path = '' as $$
begin
  if not public._ingesta_ok(k) then raise exception 'sin_permiso' using errcode = '42501'; end if;
  return (select coalesce(jsonb_object_agg(a.id, a.modificado), '{}') from public.anuncios a where a.fuente = p_fuente);
end $$;

-- Modelos conocidos por marca (de motos.net y Wallapop, que los dan estructurados) para reconocerlos en títulos libres.
create or replace function public.modelos(k text) returns jsonb language plpgsql security definer
set search_path = '' as $$
begin
  if not public._ingesta_ok(k) then raise exception 'sin_permiso' using errcode = '42501'; end if;
  return (select coalesce(jsonb_object_agg(marca, ms), '{}') from (
    select marca, jsonb_agg(modelo order by n desc) ms from (
      select marca, modelo, count(*) n from public.anuncios
      where fuente in ('motosnet', 'wallapop') and marca is not null and modelo is not null and length(modelo) between 2 and 40
      group by marca, modelo having count(*) >= 2) x group by marca) y);
end $$;

create or replace function public.vendedores(k text, p jsonb default null) returns jsonb language plpgsql security definer
set search_path = '' as $$
begin
  if not public._ingesta_ok(k) then raise exception 'sin_permiso' using errcode = '42501'; end if;
  if p is not null then
    insert into public.vendedores_wp (id, profesional, nombre)
    select x.id, x.profesional, x.nombre from jsonb_to_recordset(p) as x(id text, profesional boolean, nombre text)
    on conflict (id) do update set profesional = excluded.profesional, nombre = excluded.nombre, actualizado = now();
    return null;
  end if;
  return (select coalesce(jsonb_object_agg(id, jsonb_build_array(profesional, nombre)), '{}') from public.vendedores_wp
          where actualizado > now() - interval '60 days');
end $$;

-- Cierra la pasada de una fuente: lo que no se ha visto desde "inicio" deja de estar activo,
-- y lo que lleva 14 días sin verse se borra. Solo si la pasada fue completa (ok).
create or replace function public.cerrar_pasada(k text, p_fuente text, p_inicio timestamptz, p_leidos int, p_guardados int, p_ok boolean, p_nota text default null)
returns int language plpgsql security definer set search_path = '' as $$
declare n int := 0;
begin
  if not public._ingesta_ok(k) then raise exception 'sin_permiso' using errcode = '42501'; end if;
  if p_ok then
    update public.anuncios set activo = false where fuente = p_fuente and activo and visto_ultimo < p_inicio;
    get diagnostics n = row_count;
    delete from public.anuncios where fuente = p_fuente and visto_ultimo < now() - interval '14 days';
  end if;
  insert into public.pasadas (fuente, inicio, fin, leidos, guardados, desactivados, ok, nota)
  values (p_fuente, p_inicio, now(), p_leidos, p_guardados, n, p_ok, p_nota);
  return n;
end $$;

-- Recalcula grupos (misma moto en varias webs) y las listas de opciones de los filtros.
create or replace function public.recalcular(k text) returns jsonb language plpgsql security definer
set search_path = '' as $$
begin
  if not public._ingesta_ok(k) then raise exception 'sin_permiso' using errcode = '42501'; end if;
  -- misma marca, año, km y precio en webs distintas = la misma moto
  with g as (
    select lower(marca) || '|' || anio || '|' || km || '|' || precio as gk from public.anuncios
    where activo and marca is not null and anio is not null and km > 100 and precio > 0
    group by 1 having count(distinct fuente) > 1)
  update public.anuncios a set grupo = g.gk from g
  where a.activo and a.marca is not null and a.anio is not null and a.km > 100 and a.precio > 0
    and lower(a.marca) || '|' || a.anio || '|' || a.km || '|' || a.precio = g.gk and a.grupo is distinct from g.gk;
  update public.anuncios a set grupo = null where a.grupo is not null and not exists (
    select 1 from public.anuncios o where o.grupo = a.grupo and o.activo and o.fuente <> a.fuente);
  -- una ficha por moto: la de motos.net, si no la de Wallapop; las demás se listan como «también en»
  update public.anuncios a set principal = (a.id = r.id) from (
    select distinct on (grupo) grupo, id from public.anuncios where activo and grupo is not null
    order by grupo, case fuente when 'motosnet' then 1 when 'wallapop' then 2 else 3 end, id) r
  where a.grupo = r.grupo and a.principal is distinct from (a.id = r.id);
  update public.anuncios set principal = true where grupo is null and not principal;
  -- completar potencia, cilindrada y tipo con lo que dicen otros anuncios del mismo modelo
  update public.anuncios a set cv = m.cv from (
    select modelo_clave, percentile_cont(0.5) within group (order by cv) cv from public.anuncios
    where cv > 0 and fuente = 'motosnet' group by modelo_clave having count(*) >= 2) m
  where a.cv is null and a.modelo_clave = m.modelo_clave and a.modelo is not null;
  update public.anuncios set a2 = case when cv <= 48 then 'apta' when cv <= 95.2 then 'limitable' else 'no' end
  where a2 is null and cv is not null;
  update public.anuncios a set cc = m.cc from (
    select modelo_clave, percentile_cont(0.5) within group (order by cc)::int cc from public.anuncios
    where cc between 45 and 2500 and fuente = 'milanuncios' group by modelo_clave having count(*) >= 2) m
  where a.cc is null and a.modelo_clave = m.modelo_clave and a.modelo is not null;
  update public.anuncios a set tipo = m.tipo from (
    select distinct on (modelo_clave) modelo_clave, tipo from public.anuncios where tipo is not null and modelo is not null
    group by modelo_clave, tipo having count(*) >= 2 order by modelo_clave, count(*) desc) m
  where a.tipo is null and a.modelo_clave = m.modelo_clave and a.modelo is not null;
  insert into public.opciones_cache (id, datos, actualizado) values (1, jsonb_build_object(
      'marcas', (select jsonb_agg(jsonb_build_array(marca, n) order by n desc) from
                  (select marca, count(*) n from public.anuncios where activo and marca is not null group by marca having count(*) >= 3) m),
      'tipos', (select jsonb_agg(jsonb_build_array(tipo, n) order by n desc) from
                  (select tipo, count(*) n from public.anuncios where activo and tipo is not null group by tipo) m),
      'provincias', (select jsonb_agg(provincia order by provincia) from
                  (select distinct provincia from public.anuncios where activo and provincia is not null) m),
      'total', (select count(*) from public.anuncios where activo and principal),
      'fuentes', (select jsonb_object_agg(fuente, n) from (select fuente, count(*) n from public.anuncios where activo group by fuente) m),
      'actualizado', now()), now())
  on conflict (id) do update set datos = excluded.datos, actualizado = now();
  return (select datos from public.opciones_cache where id = 1);
end $$;

-- Permisos: la web (anon) solo puede validar, buscar y pedir opciones; el scraper usa las de ingesta.
revoke execute on all functions in schema public from public, anon, authenticated;
grant execute on function public.validar(text), public.opciones(text), public.buscar(text, jsonb) to anon, authenticated;
grant execute on function public.ingesta(text, jsonb), public.tocar(text, text[]), public.conocidos(text, text), public.modelos(text),
  public.vendedores(text, jsonb), public.cerrar_pasada(text, text, timestamptz, int, int, boolean, text),
  public.recalcular(text) to anon, service_role;
