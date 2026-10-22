-- ── Panel de administración ──────────────────────────────────────────────
-- Un token con admin = true puede crear, renovar y revocar tokens desde admin.html.
-- Todo pasa por estas funciones: la clave pública sigue sin poder leer ninguna tabla.
alter table public.tokens add column if not exists admin boolean not null default false;
alter table public.tokens add column if not exists nota text;

create or replace function public._admin(t text) returns bigint language plpgsql security definer
set search_path = '' as $$
declare tid bigint := public._token(t);
begin
  if not exists (select 1 from public.tokens where id = tid and admin) then
    raise exception 'no_admin' using errcode = '42501';
  end if;
  return tid;
end $$;

create or replace function public.validar(t text) returns jsonb language plpgsql security definer
set search_path = '' as $$
declare tid bigint := public._token(t);
begin
  return (select jsonb_build_object('nombre', tk.nombre, 'caduca', tk.caduca, 'admin', tk.admin) from public.tokens tk where tk.id = tid);
end $$;

create or replace function public.admin_tokens(t text) returns jsonb language plpgsql security definer
set search_path = '' as $$
declare tid bigint := public._admin(t);
begin
  return jsonb_build_object(
    'yo', tid,
    'tokens', coalesce((select jsonb_agg(jsonb_build_object(
        'id', tk.id, 'nombre', tk.nombre, 'nota', tk.nota, 'creado', tk.creado, 'caduca', tk.caduca,
        'revocado', tk.revocado, 'max_hora', tk.max_hora, 'usos', tk.usos, 'ultimo_uso', tk.ultimo_uso, 'admin', tk.admin,
        'usos_24h', (select coalesce(sum(u.n), 0) from public.uso u where u.token_id = tk.id and u.hora > now() - interval '24 hours'))
      order by tk.revocado, tk.creado desc) from public.tokens tk), '[]'::jsonb),
    'datos', (select jsonb_build_object('total', c.datos->'total', 'fuentes', c.datos->'fuentes', 'actualizado', c.actualizado)
              from public.opciones_cache c where c.id = 1),
    'pasadas', coalesce((select jsonb_agg(p order by p.fuente) from (
        select distinct on (fuente) fuente, fin, ok, leidos, guardados, desactivados from public.pasadas
        order by fuente, inicio desc) p), '[]'::jsonb));
end $$;

-- Devuelve el token en claro UNA sola vez; solo se guarda su hash.
create or replace function public.admin_crear(t text, p_nombre text, p_dias int default 365, p_max_hora int default 300, p_nota text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare nuevo text := encode(extensions.gen_random_bytes(16), 'hex'); nid bigint;
begin
  perform public._admin(t);
  if coalesce(trim(p_nombre), '') = '' then raise exception 'nombre_vacio' using errcode = '22023'; end if;
  insert into public.tokens (hash, nombre, caduca, max_hora, nota)
  values (public._sha(nuevo), left(trim(p_nombre), 60),
          case when p_dias is null or p_dias <= 0 then null else now() + make_interval(days => least(p_dias, 3650)) end,
          least(greatest(coalesce(p_max_hora, 300), 10), 5000), nullif(left(trim(p_nota), 200), ''))
  returning id into nid;
  return jsonb_build_object('id', nid, 'token', nuevo);
end $$;

-- Revocar o reactivar. No deja revocarte a ti mismo (te quedarías fuera).
create or replace function public.admin_revocar(t text, p_id bigint, p_revocado boolean default true) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare tid bigint := public._admin(t);
begin
  if p_id = tid and p_revocado then raise exception 'no_puedes_revocarte' using errcode = '22023'; end if;
  update public.tokens set revocado = p_revocado where id = p_id;
  return jsonb_build_object('ok', found);
end $$;

-- Cambia caducidad (días desde hoy; 0 o null = sin caducidad) y límite por hora.
create or replace function public.admin_editar(t text, p_id bigint, p_dias int default null, p_max_hora int default null, p_nota text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  perform public._admin(t);
  update public.tokens set
    caduca = case when p_dias is null then caduca when p_dias <= 0 then null else now() + make_interval(days => least(p_dias, 3650)) end,
    max_hora = case when p_max_hora is null then max_hora else least(greatest(p_max_hora, 10), 5000) end,  -- greatest() ignora null
    nota = coalesce(nullif(left(trim(p_nota), 200), ''), nota)
  where id = p_id;
  return jsonb_build_object('ok', found);
end $$;

revoke execute on function public._admin(text), public.admin_tokens(text), public.admin_crear(text, text, int, int, text),
  public.admin_revocar(text, bigint, boolean), public.admin_editar(text, bigint, int, int, text) from public;
grant execute on function public.admin_tokens(text), public.admin_crear(text, text, int, int, text),
  public.admin_revocar(text, bigint, boolean), public.admin_editar(text, bigint, int, int, text) to anon, authenticated;
grant execute on function public.validar(text) to anon, authenticated;

update public.tokens set admin = true where id = 1;  -- Ayoub
