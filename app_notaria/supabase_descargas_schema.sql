-- Tabla para guardar archivos (certificados y recibos)
CREATE TABLE public.descargas (
  id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  tipo TEXT NOT NULL CHECK (tipo IN ('recibo', 'certificado')),
  escritura TEXT NOT NULL,
  email TEXT,
  archivo_nombre TEXT NOT NULL,
  archivo_contenido BYTEA NOT NULL,
  enviado BOOLEAN DEFAULT FALSE,
  fecha_descarga TIMESTAMP DEFAULT NOW(),
  fecha_envio TIMESTAMP,
  creado_at TIMESTAMP DEFAULT NOW()
);

-- Índices para búsquedas rápidas
CREATE INDEX idx_descargas_escritura ON public.descargas(escritura);
CREATE INDEX idx_descargas_tipo ON public.descargas(tipo);
CREATE INDEX idx_descargas_enviado ON public.descargas(enviado);

-- Política de seguridad (lectura pública, escritura controlada)
ALTER TABLE public.descargas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Lectura pública de descargas" ON public.descargas
FOR SELECT USING (true);

CREATE POLICY "Inserción con service role" ON public.descargas
FOR INSERT WITH CHECK (true);

CREATE POLICY "Actualización con service role" ON public.descargas
FOR UPDATE USING (true);
