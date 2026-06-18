begin;

-- 1) Migrar el dato en personas.tags (2.792 filas aprox.)
update personas
set tags = array_replace(tags, 'GENERACIÓN PLATEADA', 'LIBERTAD PLATEADA')
where 'GENERACIÓN PLATEADA' = any(tags);

-- 2) Overload A: fn_importar_personas(p_rows jsonb, p_tags_extra text[])
create or replace function public.fn_importar_personas(p_rows jsonb, p_tags_extra text[] default '{}'::text[])
 returns jsonb
 language plpgsql
as $function$
declare
  r jsonb; v_dni text; v_nombre text; v_tel text; v_comuna_raw text;
  v_comuna smallint; v_origen text; v_tags text[]; v_dni_num bigint;
  v_status text; v_motivo text; v_inserted int := 0; v_exists int := 0;
  v_rejected int := 0; v_results jsonb := '[]'::jsonb;
begin
  for r in select value from jsonb_array_elements(p_rows)
  loop
    v_motivo := null; v_status := null;
    v_nombre := nullif(trim(coalesce(r->>'nombre_apellido','')), '');
    v_dni := nullif(regexp_replace(coalesce(r->>'dni',''), '\D', '', 'g'), '');
    v_tel := nullif(trim(coalesce(r->>'telefono','')), '');
    v_origen := nullif(trim(coalesce(r->>'de_donde_salio','')), '');
    v_comuna_raw := nullif(regexp_replace(coalesce(r->>'comuna_id',''), '\D', '', 'g'), '');
    v_comuna := case when v_comuna_raw is null then null else v_comuna_raw::smallint end;

    if v_nombre is null then v_motivo := 'sin nombre';
    elsif v_dni is null then v_motivo := 'sin dni';
    elsif v_comuna is null or v_comuna not between 1 and 15 then v_motivo := 'comuna invalida';
    end if;

    if v_motivo is not null then
      v_rejected := v_rejected + 1;
      v_results := v_results || jsonb_build_object('dni', r->>'dni', 'status', 'rechazado', 'motivo', v_motivo);
      continue;
    end if;

    v_dni_num := v_dni::bigint;
    v_tags := '{}'::text[];
    if v_dni_num < 10000000 then
      v_tags := array['LIBERTAD PLATEADA'];
    elsif v_dni_num > 90000000 then
      v_tags := array['MIGRANTE'];
    elsif v_dni_num > 42000000 then
      v_tags := array['JUVENTUD'];
    end if;

    if p_tags_extra is not null and array_length(p_tags_extra, 1) is not null then
      v_tags := array(select distinct e from unnest(v_tags || p_tags_extra) e where e is not null and e <> '');
    end if;

    insert into public.personas (dni, nombre_apellido, telefono, comuna_id, de_donde_salio, tags)
    values (v_dni, v_nombre, v_tel, v_comuna, v_origen, v_tags)
    on conflict (dni) do nothing;

    if found then v_inserted := v_inserted + 1; v_status := 'insertado';
    else v_exists := v_exists + 1; v_status := 'existente'; end if;

    v_results := v_results || jsonb_build_object('dni', v_dni, 'status', v_status, 'motivo', null);
  end loop;

  return jsonb_build_object(
    'resumen', jsonb_build_object('insertados', v_inserted, 'existentes', v_exists, 'rechazados', v_rejected),
    'filas', v_results);
end;
$function$;

-- 3) Overload B: fn_importar_personas(p_rows jsonb, p_origen text, p_extra_tags text[]) SECURITY DEFINER
create or replace function public.fn_importar_personas(p_rows jsonb, p_origen text default null::text, p_extra_tags text[] default '{}'::text[])
 returns jsonb
 language plpgsql
 security definer
 set search_path to 'public'
as $function$
declare
  r jsonb; v_ref text; v_nombre text; v_dni text; v_dni_int bigint; v_tel text;
  v_comuna int; v_origen text; v_tags text[]; v_rc integer;
  out_arr jsonb := '[]'::jsonb; n_ins int := 0; n_dup int := 0; n_omit int := 0;
begin
  for r in select value from jsonb_array_elements(p_rows)
  loop
    v_ref := r->>'ref';
    v_nombre := nullif(btrim(r->>'nombre_apellido'), '');
    v_dni := nullif(regexp_replace(coalesce(r->>'dni',''), '\D', '', 'g'), '');
    v_tel := nullif(btrim(r->>'telefono'), '');
    v_comuna := nullif((regexp_match(coalesce(r->>'comuna',''), '\d+'))[1], '')::int;
    v_origen := coalesce(nullif(btrim(r->>'de_donde_salio'), ''), p_origen);

    if v_nombre is null then
      out_arr := out_arr || jsonb_build_array(jsonb_build_object('ref',v_ref,'status','omitido','motivo','sin nombre'));
      n_omit := n_omit + 1; continue;
    end if;
    if v_dni is null then
      out_arr := out_arr || jsonb_build_array(jsonb_build_object('ref',v_ref,'status','omitido','motivo','sin dni'));
      n_omit := n_omit + 1; continue;
    end if;
    if v_comuna is null or v_comuna not between 1 and 15 then
      out_arr := out_arr || jsonb_build_array(jsonb_build_object('ref',v_ref,'status','omitido','motivo','comuna invalida'));
      n_omit := n_omit + 1; continue;
    end if;

    v_dni_int := v_dni::bigint;
    v_tags := p_extra_tags;
    if v_dni_int < 10000000 then
      v_tags := array_append(v_tags, 'LIBERTAD PLATEADA');
    elsif v_dni_int > 90000000 then
      v_tags := array_append(v_tags, 'MIGRANTE');
    elsif v_dni_int > 42000000 and v_dni_int < 90000000 then
      v_tags := array_append(v_tags, 'JUVENTUD');
    end if;
    v_tags := array(select distinct t from unnest(v_tags) t where nullif(btrim(t),'') is not null);

    insert into personas (nombre_apellido, dni, telefono, comuna_id, de_donde_salio, tags)
    values (v_nombre, v_dni, v_tel, v_comuna::smallint, v_origen, v_tags)
    on conflict (dni) do nothing;

    get diagnostics v_rc = row_count;
    if v_rc = 1 then
      out_arr := out_arr || jsonb_build_array(jsonb_build_object('ref',v_ref,'status','insertado','tags',to_jsonb(v_tags)));
      n_ins := n_ins + 1;
    else
      out_arr := out_arr || jsonb_build_array(jsonb_build_object('ref',v_ref,'status','duplicado'));
      n_dup := n_dup + 1;
    end if;
  end loop;

  return jsonb_build_object(
    'resumen', jsonb_build_object('insertados',n_ins,'duplicados',n_dup,'omitidos',n_omit,'total',n_ins+n_dup+n_omit),
    'filas', out_arr);
end;
$function$;

-- 4) Verificación (deben dar 0 y ~2792 respectivamente)
-- select count(*) from personas where 'GENERACIÓN PLATEADA' = any(tags);          -- esperado: 0
-- select count(*) from personas where 'LIBERTAD PLATEADA'  = any(tags);           -- esperado: ~2792

commit;
