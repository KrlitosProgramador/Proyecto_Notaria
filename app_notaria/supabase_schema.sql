-- Supabase SQL schema para app_notaria

create extension if not exists pgcrypto;

create table if not exists certificados (
  id uuid primary key default gen_random_uuid(),
  numero_certificado text unique not null,
  usuario text not null,
  fecha_emision timestamp with time zone default now(),
  estado text default 'generado',
  archivo_path text,
  hash_documento text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

create table if not exists recibos (
  id uuid primary key default gen_random_uuid(),
  numero_recibo text unique not null,
  certificado_id uuid references certificados(id),
  monto numeric,
  estado_pago text default 'pendiente',
  email_destinatario text,
  fecha_envio timestamp with time zone,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

create table if not exists devoluciones (
  id uuid primary key default gen_random_uuid(),
  certificado_id uuid references certificados(id),
  motivo text,
  fecha_devolucion timestamp with time zone default now(),
  estado text default 'solicitada',
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

create table if not exists logs (
  id uuid primary key default gen_random_uuid(),
  tipo_operacion text,
  descripcion text,
  usuario text,
  resultado text default 'exitoso',
  timestamp timestamp with time zone default now()
);
