"""Pruebas del motor y la persistencia. Ejecutar: python -m unittest discover -s tests -v"""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from lfpa import CalendarioLFPA


class TestPlanificador(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patch1 = patch.object(server, 'DATA_DIR', Path(self.temp.name))
        self.patch2 = patch.object(server, 'DB_PATH', Path(self.temp.name) / 'test.sqlite3')
        self.patch1.start()
        self.patch2.start()
        server.setup()

    def tearDown(self):
        self.patch2.stop()
        self.patch1.stop()
        self.temp.cleanup()

    def payload(self, tipo='plazo_lfpa'):
        p = dict(titulo='Oficio CRT', responsable='Dirección', area='Planeación',
                 tipo=tipo, fecha_inicio='2026-09-15',
                 prioridad='alta', estado='pendiente', detalle='Prueba')
        if tipo == 'plazo_lfpa':
            p['dias_habiles'] = 1
        else:
            p['fecha_vencimiento'] = '2026-09-16'
        return p

    def test_ley_16_septiembre(self):
        x=server.motor().consultar_fecha('2026-09-16')
        self.assertFalse(x['habil'])
        self.assertEqual(x['clasificacion'],'INHABIL_LFPA')
        self.assertIn('diputados.gob.mx',x['fuenteUrl'])

    def test_lunes_trasladado_no_es_inhabil_lfpa(self):
        self.assertTrue(server.motor().es_dia_habil('2026-02-02'))
        self.assertFalse(server.motor().es_dia_habil('2026-02-05'))

    def test_calendario_2026(self):
        cal=server.motor()
        self.assertEqual(len(cal.calendario_anual(2026)),365)
        self.assertEqual(len(cal.dias_inhabiles(2026)),112)

    def test_vencimiento_dia_despues_16(self):
        self.assertEqual(server.motor().sumar_dias_habiles('2026-09-15',1),'2026-09-17')

    def test_insert_edit_remove_task(self):
        task=server.create_task(self.payload())
        self.assertEqual(task['fecha_vencimiento'],'2026-09-17')
        self.assertEqual(len(server.list_tasks()),1)
        changed=self.payload('interna')
        changed['titulo']='Revisión interna'
        task=server.update_task(task['id'],changed)
        self.assertEqual(task['fecha_vencimiento'],'2026-09-16')
        self.assertEqual(task['tipo'],'interna')
        server.delete_task(task['id'])
        self.assertEqual(server.list_tasks(),[])

    def test_internal_task_keeps_inhabil_day(self):
        task=server.create_task(self.payload('interna'))
        self.assertEqual(task['fecha_vencimiento'],'2026-09-16')
        self.assertFalse(task['vencimiento_lfpa']['habil'])

    def test_invalid_dates(self):
        with self.assertRaises(ValueError):
            server.create_task({**self.payload(), 'fecha_inicio':'2026-02-30'})

    def test_invalid_plazo_type(self):
        with self.assertRaises(ValueError):
            server.create_task({**self.payload(), 'dias_habiles':'10'})

    def test_invalid_status(self):
        with self.assertRaises(ValueError):
            server.create_task({**self.payload(), 'estado':'completada'})

    def test_exception_requires_approval(self):
        with self.assertRaises(ValueError):
            server.add_exception({'fecha':'2026-09-17','tipo':'inhabil','motivo':'Acuerdo ejemplo',
             'fuenteUrl':'https://sidof.segob.gob.mx/notas/999','confirmado':False})

    def test_exception_requires_official_url(self):
        with self.assertRaises(ValueError):
            server.add_exception({'fecha':'2026-09-17','tipo':'inhabil','motivo':'Acuerdo ejemplo',
             'fuenteUrl':'https://example.com/sin-validar','confirmado':True})

    def test_exception_preview_and_approval(self):
        task=server.create_task(self.payload())
        ex=server.add_exception({'fecha':'2026-09-17','tipo':'inhabil','motivo':'Supuesto de prueba',
             'fuenteUrl':'https://sidof.segob.gob.mx/notas/999','confirmado':True})
        row=server.get_task(task['id'])
        self.assertTrue(row['necesita_revision'])
        self.assertEqual(row['fecha_vencimiento'],'2026-09-17')
        self.assertEqual(row['fecha_sugerida'],'2026-09-18')
        approved=server.approve_recalc(task['id'])
        self.assertEqual(approved['fecha_vencimiento'],'2026-09-18')
        self.assertFalse(approved['necesita_revision'])
        server.delete_exception(ex['id'])
        self.assertTrue(server.get_task(task['id'])['necesita_revision'])

    def test_export_csv_bom(self):
        s=server.as_csv(['fecha','motivo'],[['2026-09-16','Independencia']])
        self.assertTrue(s.startswith('\ufefffecha,motivo'))


if __name__=='__main__': unittest.main()
