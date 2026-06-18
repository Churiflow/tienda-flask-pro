import unittest
from app import app

class TestFlaskTienda(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_pagina_inicio_carga(self):
        respuesta = self.client.get('/')
        self.assertEqual(respuesta.status_code, 200)

    def test_ruta_invalida_da_404(self):
        respuesta = self.client.get('/esta_ruta_no_existe_en_la_tienda')
        self.assertEqual(respuesta.status_code, 404)

    def test_login_exitoso(self):
        # Usamos 'usuario' y 'clave' con tus credenciales reales
        respuesta = self.client.post('/login', data={
            'usuario': 'admin',
            'clave': '12345'
        }, follow_redirects=True)
        self.assertEqual(respuesta.status_code, 200)

    def test_login_incorrecto(self):
            # Enviamos comillas para que la función de sanitización actúe y salte la alerta
            respuesta = self.client.post('/login', data={
                'usuario': "admin' OR '1'='1",
                'clave': 'clave_falsa_999'
            }, follow_redirects=True)
            self.assertIn(b'Entrar', respuesta.data)

    def test_pago_criptografico_directo(self):
                    respuesta = self.client.post('/procesar_pago_directo', data={
                        'nombre_titular': 'Tester Cripto',
                        'numero_tarjeta': '4512345678901234',
                        'vencimiento': '12/29',
                        'cvv': '852',
                        'monto': '36990'
                    }, follow_redirects=True)
                    self.assertEqual(respuesta.status_code, 200)       
if __name__ == '__main__':
    unittest.main()
