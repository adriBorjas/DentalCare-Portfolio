from django.test import TestCase, Client
from django.urls import reverse
from .models import Usuario, Paciente, Dentista


class AccountsTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Paciente de prueba
        self.paciente_user = Usuario.objects.create_user(
            username='paciente_test',
            password='Password123!',
            email='paciente@test.com',
            role=Usuario.Rol.PACIENTE,
            first_name='Carlos',
            last_name='Prueba',
            must_change_password=False
        )
        # Dentista de prueba
        self.dentista_user = Usuario.objects.create_user(
            username='dentista_test',
            password='Password123!',
            email='dentista@test.com',
            role=Usuario.Rol.DENTISTA,
            first_name='Dra. Laura',
            last_name='García',
            must_change_password=False
        )
        # Paciente con clave temporal
        self.temporal_user = Usuario.objects.create_user(
            username='temporal_test',
            password='TempPassword123!',
            email='temporal@test.com',
            role=Usuario.Rol.PACIENTE,
            must_change_password=True
        )

    def test_registro_paciente(self):
        """Prueba que un nuevo paciente puede auto-registrarse correctamente."""
        response = self.client.post(reverse('accounts:registro'), {
            'username': 'nuevo_paciente',
            'first_name': 'Ana',
            'last_name': 'López',
            'email': 'ana@test.com',
            'telefono': '600999888',
            'password': 'MiPasswordSegura123!',
            'password_confirmacion': 'MiPasswordSegura123!',
        })
        self.assertEqual(response.status_code, 302)
        nuevo_user = Usuario.objects.get(username='nuevo_paciente')
        self.assertEqual(nuevo_user.role, Usuario.Rol.PACIENTE)
        self.assertFalse(nuevo_user.must_change_password)
        self.assertTrue(hasattr(nuevo_user, 'perfil_paciente'))
        self.assertEqual(nuevo_user.perfil_paciente.telefono, '600999888')

    def test_dentista_crear_paciente_con_clave_temporal(self):
        """Prueba que un dentista puede crear un paciente con clave temporal y must_change_password=True."""
        self.client.login(username='dentista_test', password='Password123!')
        response = self.client.post(reverse('accounts:crear_paciente'), {
            'username': 'paciente_creado_por_dentista',
            'first_name': 'Pedro',
            'last_name': 'Sánchez',
            'email': 'pedro@test.com',
            'telefono': '611222444',
            'password_temporal': 'ClaveTemp123!',
        })
        self.assertEqual(response.status_code, 200) # Muestra plantilla de confirmación con credenciales
        paciente_creado = Usuario.objects.get(username='paciente_creado_por_dentista')
        self.assertTrue(paciente_creado.must_change_password)
        self.assertEqual(paciente_creado.role, Usuario.Rol.PACIENTE)

    def test_forzar_cambio_password_middleware(self):
        """Prueba que un usuario con must_change_password=True es redirigido a la vista de cambio de clave."""
        self.client.login(username='temporal_test', password='TempPassword123!')
        # Intentar acceder al dashboard o catálogo
        response = self.client.get(reverse('treatments:lista'), follow=True)
        # Debe haber sido redirigido a cambiar_password_temporal
        self.assertTemplateUsed(response, 'accounts/cambiar_password.html')

    def test_permiso_paciente_no_puede_acceder_agenda_dentista(self):
        """Un paciente no debe poder acceder a la agenda clínica del dentista."""
        self.client.login(username='paciente_test', password='Password123!')
        response = self.client.get(reverse('appointments:dentista_agenda'))
        # Redirige a dashboard por falta de permisos
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('core:dashboard'), response.url)

    def test_dentista_puede_acceder_agenda(self):
        """Un dentista sí puede acceder a la agenda clínica."""
        self.client.login(username='dentista_test', password='Password123!')
        response = self.client.get(reverse('appointments:dentista_agenda'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'appointments/dentista_agenda.html')

    def test_logout_requiere_post(self):
        self.client.login(username='paciente_test', password='Password123!')
        response_get = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response_get.status_code, 405)

        response_post = self.client.post(reverse('accounts:logout'))
        self.assertEqual(response_post.status_code, 302)
        self.assertFalse(response_post.wsgi_request.user.is_authenticated)

    def test_login_rechaza_redireccion_externa(self):
        response = self.client.post(
            reverse('accounts:login') + '?next=https://example.com/',
            {'username': 'paciente_test', 'password': 'Password123!'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('core:dashboard'))
