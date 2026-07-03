import unittest
from types import SimpleNamespace

import supabase_client
from supabase_client import (
    get_pending_liq,
    get_pending_certificados_liq,
    normalize_escritura,
    normalize_estado_ctl_value,
    extract_escritura_from_filename,
    is_row_pending_for_certificados,
    is_row_pending_for_recibos,
)


class EstadoCtlLogicTests(unittest.TestCase):
    def test_normalize_estado_ctl_value_handles_case_and_spaces(self):
        self.assertEqual(normalize_estado_ctl_value(" Enviado "), "Enviado")
        self.assertEqual(normalize_estado_ctl_value("enviado"), "Enviado")
        self.assertEqual(normalize_estado_ctl_value("Descargado"), "Descargado")
        self.assertEqual(normalize_estado_ctl_value(None), "")

    def test_normalize_escritura_handles_whitespace_and_punctuation(self):
        self.assertEqual(normalize_escritura(" 00123 "), "123")
        self.assertEqual(normalize_escritura("00123.0"), "123")
        self.assertEqual(normalize_escritura(""), None)

    def test_is_row_pending_for_recibos_ignores_estado_ctl(self):
        self.assertTrue(is_row_pending_for_recibos({"notificacion": "Pendiente", "estado_ctl": "Enviado"}))
        self.assertTrue(is_row_pending_for_recibos({"notificacion": "Por enviar", "estado_ctl": "Enviado"}))
        self.assertTrue(is_row_pending_for_recibos({"notificacion": "Pendiente por enviar", "estado_ctl": "Enviado"}))
        self.assertFalse(is_row_pending_for_recibos({"notificacion": "Enviado", "estado_ctl": "Pendiente"}))

    def test_is_row_pending_for_certificados_requires_pago_ingresado_and_pending_estado(self):
        self.assertTrue(is_row_pending_for_certificados({"estado_ctl": "Pendiente", "pago": "Ingresado"}))
        self.assertFalse(is_row_pending_for_certificados({"estado_ctl": "Enviado", "pago": "Ingresado"}))
        self.assertFalse(is_row_pending_for_certificados({"estado_ctl": "Pendiente", "pago": "Pendiente"}))

    def test_get_pending_liq_can_include_rows_with_estado_ctl_enviado_for_recibos(self):
        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def select(self, *args, **kwargs):
                return self

            def filter(self, *args, **kwargs):
                return self

            def execute(self):
                return SimpleNamespace(data=self.rows)

        class FakeSupabase:
            def table(self, name):
                return FakeQuery([
                    {"escritura": "123", "notificacion": "Pendiente", "estado_ctl": "Enviado"},
                    {"escritura": "456", "notificacion": "Enviado", "estado_ctl": "Pendiente"},
                ])

        original_supabase = supabase_client.supabase
        supabase_client.supabase = FakeSupabase()
        try:
            res = get_pending_liq(limit=10, page=1, sort_by="escritura", desc=False, require_estado_ctl_pending=False)
        finally:
            supabase_client.supabase = original_supabase

        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["escritura"], "123")

    def test_get_pending_certificados_liq_uses_pago_ingresado_and_pending_estado(self):
        class FakeQuery:
            def __init__(self, rows):
                self.rows = rows

            def select(self, *args, **kwargs):
                return self

            def filter(self, *args, **kwargs):
                return self

            def execute(self):
                return SimpleNamespace(data=self.rows)

        class FakeSupabase:
            def table(self, name):
                return FakeQuery([
                    {"escritura": "123", "pago": "Ingresado", "estado_ctl": "Pendiente"},
                    {"escritura": "456", "pago": "Ingresado", "estado_ctl": "Enviado"},
                    {"escritura": "789", "pago": "Pendiente", "estado_ctl": "Pendiente"},
                ])

        original_supabase = supabase_client.supabase
        supabase_client.supabase = FakeSupabase()
        try:
            res = get_pending_certificados_liq(limit=10, page=1, sort_by="escritura", desc=False)
        finally:
            supabase_client.supabase = original_supabase

        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["escritura"], "123")

    def test_extract_escritura_from_filename(self):
        self.assertEqual(extract_escritura_from_filename("00123 Certificado.pdf"), "123")
        self.assertEqual(extract_escritura_from_filename("123_Certificado.pdf"), "123")
        self.assertEqual(extract_escritura_from_filename("  1234 - recibo.pdf"), "1234")
        self.assertEqual(extract_escritura_from_filename("abc123.pdf"), None)

    def test_update_liq_estado_by_escritura_skips_auto_move_for_cert_download(self):
        class FakeQuery:
            def __init__(self):
                self._data = [{'id': 1}]
            def update(self, payload):
                self.payload = payload
                return self
            def eq(self, field, value):
                self.field = field
                self.value = value
                return self
            def execute(self):
                return SimpleNamespace(data=self._data)

        class FakeSupabase:
            def table(self, name):
                return FakeQuery()

        original_supabase = supabase_client.supabase
        original_check = supabase_client._check_and_move_if_complete
        supabase_client.supabase = FakeSupabase()
        called = []
        supabase_client._check_and_move_if_complete = lambda escritura: called.append(escritura)
        try:
            res = supabase_client.update_liq_estado_by_escritura("123", "Descargado", activity_type='cert_download')
        finally:
            supabase_client.supabase = original_supabase
            supabase_client._check_and_move_if_complete = original_check

        self.assertEqual(len(called), 0)
        self.assertTrue(hasattr(res, 'data'))
        self.assertEqual(res.data[0]['id'], 1)


if __name__ == "__main__":
    unittest.main()
