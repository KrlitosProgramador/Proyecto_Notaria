create table if not exists liq (
  id uuid primary key default gen_random_uuid(),
  escritura text,
  correo text,
  gobernacion text,
  nir text,
  notificacion text,
  pago text,
  estado_ctl text,
  devolucion text,
  escritura_str text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
