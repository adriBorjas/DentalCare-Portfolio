from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from datetime import date, time, timedelta
from decimal import Decimal
import json

from accounts.models import Usuario, Paciente, Dentista
from treatments.models import Tratamiento
from appointments.models import Cita, HorarioDentista, BloqueoDisponibilidad


class AppointmentsTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Dentista 1
        self.u_d1 = Usuario.objects.create_user(
            username='dr_test1',
            password='Password123!',
            role=Usuario.Rol.DENTISTA,
            first_name='Alberto',
            last_name='Ruiz'
        )
        self.dentista1 = self.u_d1.perfil_dentista

        # Dentista 2
        self.u_d2 = Usuario.objects.create_user(
            username='dra_test2',
            password='Password123!',
            role=Usuario.Rol.DENTISTA,
            first_name='Elena',
            last_name='Ramos'
        )
        self.dentista2 = self.u_d2.perfil_dentista

        # Paciente 1
        self.u_p1 = Usuario.objects.create_user(
            username='paciente_test1',
            password='Password123!',
            role=Usuario.Rol.PACIENTE,
            first_name='Carlos',
            last_name='Gómez',
            telefono='600111222'
        )
        self.paciente1 = self.u_p1.perfil_paciente
        self.paciente1.dni = '50123456H'
        self.paciente1.email = 'carlos@test.com'
        self.paciente1.save()

        # Paciente 2
        self.u_p2 = Usuario.objects.create_user(
            username='paciente_test2',
            password='Password123!',
            role=Usuario.Rol.PACIENTE,
            first_name='Laura',
            last_name='Martín',
            telefono='600333444'
        )
        self.paciente2 = self.u_p2.perfil_paciente
        self.paciente2.dni = '52987654K'
        self.paciente2.save()

        # Tratamiento
        self.tratamiento = Tratamiento.objects.create(
            nombre='Limpieza Dental Test',
            precio=Decimal('50.00'),
            duracion_estimada=30,
            activo=True
        )

        # Horarios para Dentista 1 y Dentista 2 (Lunes a Viernes 08:00 - 20:00)
        for d in range(5):
            HorarioDentista.objects.create(
                dentista=self.dentista1,
                dia_semana=d,
                hora_apertura=time(8, 0),
                hora_cierre=time(20, 0),
                activo=True
            )
            HorarioDentista.objects.create(
                dentista=self.dentista2,
                dia_semana=d,
                hora_apertura=time(8, 0),
                hora_cierre=time(20, 0),
                activo=True
            )

        # Fecha de prueba: próximo día laborable para no quedar obsoleta con el tiempo.
        self.fecha_test = timezone.localdate() + timedelta(days=1)
        while self.fecha_test.weekday() >= 5:
            self.fecha_test += timedelta(days=1)

    def test_creacion_cita_exitosa(self):
        """Comprueba que una cita con datos válidos se guarda correctamente."""
        cita = Cita(
            dentista=self.dentista1,
            paciente=self.paciente1,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 0),
            hora_fin=time(10, 30),
            estado=Cita.Estado.CONFIRMADA
        )
        cita.full_clean()
        cita.save()
        self.assertEqual(Cita.objects.count(), 1)
        self.assertEqual(cita.duracion_minutos, 30)

    def test_solapamiento_citas_mismo_dentista(self):
        """Verifica que dos citas que se solapan para el mismo dentista lanzan ValidationError."""
        # Cita existente de 10:00 a 11:00
        Cita.objects.create(
            dentista=self.dentista1,
            paciente=self.paciente1,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 0),
            hora_fin=time(11, 0),
            estado=Cita.Estado.CONFIRMADA
        )

        # Intento de cita solapada (10:30 a 11:30) para el mismo dentista
        cita_solapada = Cita(
            dentista=self.dentista1,
            paciente=self.paciente2,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 30),
            hora_fin=time(11, 30),
            estado=Cita.Estado.PENDIENTE
        )

        with self.assertRaises(ValidationError):
            cita_solapada.full_clean()

    def test_mismo_horario_distinto_dentista_permitido(self):
        """Dos citas a la misma hora para distintos dentistas sí están permitidas."""
        Cita.objects.create(
            dentista=self.dentista1,
            paciente=self.paciente1,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 0),
            hora_fin=time(11, 0),
            estado=Cita.Estado.CONFIRMADA
        )

        cita_d2 = Cita(
            dentista=self.dentista2,
            paciente=self.paciente2,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 0),
            hora_fin=time(11, 0),
            estado=Cita.Estado.CONFIRMADA
        )
        cita_d2.full_clean()
        cita_d2.save()
        self.assertEqual(Cita.objects.count(), 2)

    def test_cita_cancelada_no_bloquea_horario(self):
        """Una cita cancelada o eliminada no debe impedir reservar en ese mismo hueco."""
        Cita.objects.create(
            dentista=self.dentista1,
            paciente=self.paciente1,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 0),
            hora_fin=time(11, 0),
            estado=Cita.Estado.CANCELADA
        )

        nueva_cita = Cita(
            dentista=self.dentista1,
            paciente=self.paciente2,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 0),
            hora_fin=time(11, 0),
            estado=Cita.Estado.CONFIRMADA
        )
        nueva_cita.full_clean()
        nueva_cita.save()
        self.assertEqual(Cita.objects.filter(estado=Cita.Estado.CONFIRMADA).count(), 1)

    def test_bloqueo_disponibilidad_impide_cita(self):
        """Un bloqueo programado de disponibilidad impide fijar una cita en ese rango."""
        BloqueoDisponibilidad.objects.create(
            dentista=self.dentista1,
            fecha=self.fecha_test,
            hora_inicio=time(15, 0),
            hora_fin=time(17, 0),
            motivo='Cirugía de Urgencia'
        )

        cita_en_bloqueo = Cita(
            dentista=self.dentista1,
            paciente=self.paciente1,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(15, 30),
            hora_fin=time(16, 0),
            estado=Cita.Estado.PENDIENTE
        )
        with self.assertRaises(ValidationError):
            cita_en_bloqueo.full_clean()

    def test_borrado_logico_soft_delete(self):
        """Comprueba que el delete de una cita no la borra de la BD, sino que la marca como eliminada."""
        cita = Cita.objects.create(
            dentista=self.dentista1,
            paciente=self.paciente1,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(12, 0),
            hora_fin=time(12, 30),
            estado=Cita.Estado.CONFIRMADA
        )
        cita_id = cita.id
        cita.delete() # Soft delete

        self.assertTrue(Cita.objects.filter(id=cita_id).exists())
        cita_recuperada = Cita.objects.get(id=cita_id)
        self.assertTrue(cita_recuperada.is_deleted)
        self.assertEqual(cita_recuperada.estado, Cita.Estado.ELIMINADA)
        self.assertFalse(Cita.objects.activas().filter(id=cita_id).exists())

    def test_paciente_sin_cuenta_requiere_nombre_y_telefono(self):
        """Las citas de pacientes sin cuenta deben validar que se suministren nombre y teléfono."""
        cita_invitado_valida = Cita(
            dentista=self.dentista1,
            paciente=None,
            paciente_nombre='Juan Nadie',
            paciente_telefono='666777888',
            paciente_email='juan@nadie.com',
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(13, 0),
            hora_fin=time(13, 30),
            estado=Cita.Estado.CONFIRMADA
        )
        cita_invitado_valida.full_clean()
        cita_invitado_valida.save()
        self.assertEqual(cita_invitado_valida.nombre_paciente_display, 'Juan Nadie')

        cita_invitado_invalida = Cita(
            dentista=self.dentista1,
            paciente=None,
            paciente_nombre='',
            paciente_telefono='',
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(14, 0),
            hora_fin=time(14, 30),
            estado=Cita.Estado.CONFIRMADA
        )
        with self.assertRaises(ValidationError):
            cita_invitado_invalida.full_clean()

    # ==========================================================
    # NUEVAS PRUEBAS: AGENDA VISUAL (VISTAS, HISTÓRICO, FILTROS)
    # ==========================================================

    def test_permisos_agenda_y_buscador(self):
        """Un paciente no puede acceder a la agenda clínica ni a la API de búsqueda."""
        self.client.login(username='paciente_test1', password='Password123!')
        res_agenda = self.client.get(reverse('appointments:dentista_agenda'))
        self.assertEqual(res_agenda.status_code, 302) # Redirige a dashboard

        res_search = self.client.get(reverse('appointments:buscar_citas_api') + '?q=Carlos')
        self.assertEqual(res_search.status_code, 302)

        # El dentista sí tiene acceso completo
        self.client.login(username='dr_test1', password='Password123!')
        res_agenda_ok = self.client.get(reverse('appointments:dentista_agenda'))
        self.assertEqual(res_agenda_ok.status_code, 200)

        res_search_ok = self.client.get(reverse('appointments:buscar_citas_api') + '?q=Carlos')
        self.assertEqual(res_search_ok.status_code, 200)

    def test_dentista_solo_ve_sus_citas_en_agenda_busqueda_y_detalle(self):
        Cita.objects.create(
            dentista=self.dentista1,
            paciente=self.paciente1,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(9, 0),
            hora_fin=time(9, 30),
            estado=Cita.Estado.CONFIRMADA,
        )
        cita_otro_dentista = Cita.objects.create(
            dentista=self.dentista2,
            paciente=self.paciente2,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 0),
            hora_fin=time(10, 30),
            estado=Cita.Estado.CONFIRMADA,
        )

        self.client.login(username='dr_test1', password='Password123!')

        detalle = self.client.get(
            reverse('appointments:detalle_cita_api', args=[cita_otro_dentista.pk])
        )
        self.assertEqual(detalle.status_code, 403)

        busqueda = self.client.get(
            reverse('appointments:buscar_citas_api') + '?q=Laura'
        )
        self.assertEqual(busqueda.status_code, 200)
        self.assertEqual(busqueda.json()['total'], 0)

        agenda = self.client.get(reverse('appointments:dentista_agenda') + '?vista=lista')
        self.assertEqual(agenda.status_code, 200)
        self.assertNotIn(cita_otro_dentista, agenda.context['citas_lista'])

        pacientes = self.client.get(reverse('accounts:lista_pacientes'))
        self.assertEqual(pacientes.status_code, 200)
        pacientes_visibles = list(pacientes.context['pacientes'])
        self.assertIn(self.paciente1, pacientes_visibles)
        self.assertNotIn(self.paciente2, pacientes_visibles)

    def test_vistas_semanal_diaria_mensual_lista(self):
        """Comprueba que la agenda responde correctamente a las 4 vistas."""
        self.client.login(username='dr_test1', password='Password123!')

        # Vista Semanal (por defecto)
        r_semana = self.client.get(reverse('appointments:dentista_agenda') + f'?vista=semana&fecha={self.fecha_test}')
        self.assertEqual(r_semana.status_code, 200)
        self.assertEqual(r_semana.context['vista'], 'semana')
        self.assertIn('dias_semana', r_semana.context)
        self.assertIn('matriz_semana', r_semana.context)

        # Vista Diaria
        r_dia = self.client.get(reverse('appointments:dentista_agenda') + f'?vista=dia&fecha={self.fecha_test}')
        self.assertEqual(r_dia.status_code, 200)
        self.assertEqual(r_dia.context['vista'], 'dia')
        self.assertIn('columnas_dentistas', r_dia.context)

        # Vista Mensual
        r_mes = self.client.get(reverse('appointments:dentista_agenda') + f'?vista=mes&fecha={self.fecha_test}')
        self.assertEqual(r_mes.status_code, 200)
        self.assertEqual(r_mes.context['vista'], 'mes')
        self.assertIn('calendario_mes', r_mes.context)

        # Vista Lista (Tabla)
        r_lista = self.client.get(reverse('appointments:dentista_agenda') + f'?vista=lista&fecha={self.fecha_test}')
        self.assertEqual(r_lista.status_code, 200)
        self.assertEqual(r_lista.context['vista'], 'lista')
        self.assertIn('citas_lista', r_lista.context)

    def test_citas_canceladas_y_eliminadas_ocultas_por_defecto(self):
        """
        Las citas canceladas y eliminadas están ocultas por defecto en la agenda
        y solo se muestran si incluir_historico=1.
        """
        self.client.login(username='dr_test1', password='Password123!')

        # Cita activa
        c_activa = Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente1,
            tratamiento=self.tratamiento, fecha=self.fecha_test,
            hora_inicio=time(9, 0), hora_fin=time(9, 30),
            estado=Cita.Estado.CONFIRMADA
        )
        # Cita cancelada
        c_cancelada = Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente1,
            tratamiento=self.tratamiento, fecha=self.fecha_test,
            hora_inicio=time(10, 0), hora_fin=time(10, 30),
            estado=Cita.Estado.CANCELADA
        )
        # Cita eliminada (soft delete)
        c_eliminada = Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente1,
            tratamiento=self.tratamiento, fecha=self.fecha_test,
            hora_inicio=time(11, 0), hora_fin=time(11, 30),
            estado=Cita.Estado.CONFIRMADA
        )
        c_eliminada.delete()

        # 1. Petición por defecto: SIN incluir histórico
        res_def = self.client.get(reverse('appointments:dentista_agenda') + f'?vista=dia&fecha={self.fecha_test}')
        self.assertEqual(res_def.status_code, 200)
        col_d1 = [col for col in res_def.context['columnas_dentistas'] if col['dentista'].id == self.dentista1.id][0]
        citas_visibles = [item['cita'].id for item in col_d1['citas']]

        self.assertIn(c_activa.id, citas_visibles)
        self.assertNotIn(c_cancelada.id, citas_visibles)
        self.assertNotIn(c_eliminada.id, citas_visibles)

        # 2. Petición CON incluir_historico=1
        res_hist = self.client.get(reverse('appointments:dentista_agenda') + f'?vista=dia&fecha={self.fecha_test}&incluir_historico=1')
        self.assertEqual(res_hist.status_code, 200)
        col_d1_hist = [col for col in res_hist.context['columnas_dentistas'] if col['dentista'].id == self.dentista1.id][0]
        citas_hist_visibles = [item['cita'].id for item in col_d1_hist['citas']]

        self.assertIn(c_activa.id, citas_hist_visibles)
        self.assertIn(c_cancelada.id, citas_hist_visibles)
        self.assertIn(c_eliminada.id, citas_hist_visibles)

    def test_crear_cita_preseleccion_parametros(self):
        """
        Al hacer clic en un hueco, el formulario de creación recibe fecha y hora preseleccionadas.
        Si el usuario logueado es dentista, se preselecciona a sí mismo sin importar el parámetro
        GET 'dentista' (un dentista no puede cambiar fácilmente de propietario de cita).
        Si el usuario es administrador, el parámetro GET 'dentista' sí prevalece.
        """
        self.client.login(username='dr_test1', password='Password123!')
        res = self.client.get(reverse('appointments:dentista_crear_cita') + f'?fecha={self.fecha_test}&hora_inicio=11:30&dentista={self.dentista2.id}')
        self.assertEqual(res.status_code, 200)
        form = res.context['form']
        self.assertEqual(str(form.initial.get('fecha')), str(self.fecha_test))
        self.assertEqual(form.initial.get('hora_inicio'), '11:30')
        self.assertEqual(form.initial.get('hora_fin'), '12:00')
        # El dentista logueado (dentista1) se preselecciona, no el dentista2 del GET
        self.assertEqual(form.initial.get('dentista'), self.dentista1)

    # ==========================================================
    # NUEVAS PRUEBAS: BUSCADOR INTEGRADO DE CITAS (FASE 2)
    # ==========================================================

    def test_buscador_citas_por_nombre_dni_telefono_email(self):
        """El buscador permite encontrar citas por nombre, DNI, teléfono o email con ofuscación parcial."""
        Usuario.objects.create_user(
            username='staff_test',
            password='Password123!',
            role=Usuario.Rol.ADMINISTRADOR,
            is_staff=True,
        )
        self.client.login(username='staff_test', password='Password123!')

        # Cita paciente registrado
        cita_carlos = Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente1,
            tratamiento=self.tratamiento, fecha=self.fecha_test,
            hora_inicio=time(9, 0), hora_fin=time(9, 45),
            estado=Cita.Estado.CONFIRMADA
        )

        # Cita paciente invitado sin cuenta
        cita_marta = Cita.objects.create(
            dentista=self.dentista2, paciente=None,
            paciente_nombre='Marta Soler',
            paciente_telefono='677112233',
            paciente_email='marta@soler.com',
            tratamiento=self.tratamiento, fecha=self.fecha_test,
            hora_inicio=time(12, 0), hora_fin=time(12, 30),
            estado=Cita.Estado.PENDIENTE
        )

        # 1. Búsqueda por Nombre
        res_nombre = self.client.get(reverse('appointments:buscar_citas_api') + '?q=Carlos')
        data_nombre = json.loads(res_nombre.content)
        self.assertEqual(data_nombre['total'], 1)
        self.assertEqual(data_nombre['citas'][0]['id'], cita_carlos.id)

        # Comprobación de DNI y teléfono parcialmente ofuscados
        dni_parcial = data_nombre['citas'][0]['dni_parcial']
        self.assertTrue('***' in dni_parcial)
        tel_parcial = data_nombre['citas'][0]['telefono_parcial']
        self.assertTrue('***' in tel_parcial)

        # 2. Búsqueda por DNI
        res_dni = self.client.get(reverse('appointments:buscar_citas_api') + '?q=50123')
        data_dni = json.loads(res_dni.content)
        self.assertEqual(data_dni['total'], 1)
        self.assertEqual(data_dni['citas'][0]['id'], cita_carlos.id)

        # 3. Búsqueda por Teléfono de paciente sin cuenta
        res_tel = self.client.get(reverse('appointments:buscar_citas_api') + '?q=67711')
        data_tel = json.loads(res_tel.content)
        self.assertEqual(data_tel['total'], 1)
        self.assertEqual(data_tel['citas'][0]['id'], cita_marta.id)

        # 4. Comprobar URL de navegación generada con parámetro highlight
        url_nav = data_nombre['citas'][0]['url_navegacion']
        self.assertIn(f'highlight={cita_carlos.id}', url_nav)
        self.assertIn(f'fecha={self.fecha_test}', url_nav)

    def test_buscador_oculta_historico_por_defecto(self):
        """El buscador oculta citas canceladas o eliminadas salvo que se active explícitamente el histórico."""
        self.client.login(username='dr_test1', password='Password123!')

        cita_cancelada = Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente2,
            tratamiento=self.tratamiento, fecha=self.fecha_test,
            hora_inicio=time(16, 0), hora_fin=time(16, 30),
            estado=Cita.Estado.CANCELADA
        )

        # Búsqueda por defecto -> 0 resultados
        res_def = self.client.get(reverse('appointments:buscar_citas_api') + '?q=Laura')
        data_def = json.loads(res_def.content)
        self.assertEqual(data_def['total'], 0)

        # Búsqueda con incluir_historico=1 -> 1 resultado
        res_hist = self.client.get(reverse('appointments:buscar_citas_api') + '?q=Laura&incluir_historico=1')
        data_hist = json.loads(res_hist.content)
        self.assertEqual(data_hist['total'], 1)
        self.assertEqual(data_hist['citas'][0]['id'], cita_cancelada.id)
        self.assertTrue(data_hist['citas'][0]['es_historica'])

    # ==========================================================
    # NUEVAS PRUEBAS: ACCESO PÚBLICO A LA AGENDA Y PRE-RESERVA
    # ==========================================================

    def test_acceso_publico_calendario_sin_autenticacion(self):
        """Cualquier persona sin cuenta puede consultar el calendario público de disponibilidad."""
        # Cliente sin autenticar
        anon_client = Client()
        res = anon_client.get(reverse('appointments:agenda_publica') + f'?vista=semana&fecha={self.fecha_test}')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Disponibilidad y Horarios de Dentistas')
        self.assertContains(res, self.dentista1.nombre_completo)

    def test_ocultacion_estricta_datos_pacientes_en_agenda_publica(self):
        """
        En la agenda pública NO se muestra ningún dato de pacientes, tratamientos,
        motivos de consulta ni información clínica. Las citas ocupadas aparecen como 'No disponible'.
        """
        # Crear paciente y cita con información confidencial
        u_pac_secreto = Usuario.objects.create_user(
            username='pac_secreto',
            password='Password123!',
            role=Usuario.Rol.PACIENTE,
            first_name='Pedro',
            last_name='Marmol Picapiedra',
            telefono='699112233'
        )
        pac_secreto = u_pac_secreto.perfil_paciente
        pac_secreto.dni = '11223344Z'
        pac_secreto.save()

        t_secreto = Tratamiento.objects.create(
            nombre='Cirugía Periodontal Avanzada',
            precio=Decimal('350.00'),
            duracion_estimada=60,
            activo=True
        )

        Cita.objects.create(
            dentista=self.dentista1,
            paciente=pac_secreto,
            tratamiento=t_secreto,
            fecha=self.fecha_test,
            hora_inicio=time(9, 0),
            hora_fin=time(10, 0),
            estado=Cita.Estado.CONFIRMADA,
            notas='Gingivitis severa con sangrado activo'
        )

        anon_client = Client()
        res = anon_client.get(reverse('appointments:agenda_publica') + f'?vista=dia&fecha={self.fecha_test}')
        self.assertEqual(res.status_code, 200)

        contenido_html = res.content.decode('utf-8')

        # Comprobación de estricta privacidad
        self.assertNotIn('Pedro', contenido_html)
        self.assertNotIn('Marmol', contenido_html)
        self.assertNotIn('Picapiedra', contenido_html)
        self.assertNotIn('11223344Z', contenido_html)
        self.assertNotIn('699112233', contenido_html)
        self.assertNotIn('Cirugía Periodontal Avanzada', contenido_html)
        self.assertNotIn('Gingivitis severa', contenido_html)

        # Comprobación de que la franja aparece rotulada como "No disponible"
        self.assertIn('No disponible', contenido_html)

    def test_visualizacion_franjas_ocupadas_y_bloqueadas(self):
        """Los bloqueos de disponibilidad también se muestran como 'No disponible' sin desvelar motivos."""
        BloqueoDisponibilidad.objects.create(
            dentista=self.dentista1,
            fecha=self.fecha_test,
            hora_inicio=time(11, 0),
            hora_fin=time(12, 0),
            motivo='Cirugía confidencial o descanso'
        )

        anon_client = Client()
        res = anon_client.get(reverse('appointments:agenda_publica') + f'?vista=dia&fecha={self.fecha_test}')
        self.assertEqual(res.status_code, 200)
        contenido = res.content.decode('utf-8')

        self.assertNotIn('Cirugía confidencial', contenido)
        self.assertIn('No disponible', contenido)

    def test_solicitar_cita_sin_cuenta_guarda_en_sesion_y_pre_reserva(self):
        """
        Un usuario sin cuenta selecciona una franja y se guarda temporalmente en sesión,
        redirigiéndole a la pantalla de pre-reserva para identificarse o darse de alta.
        """
        anon_client = Client()
        url = reverse('appointments:solicitar_cita_publica') + f'?dentista={self.dentista1.id}&fecha={self.fecha_test}&hora_inicio=10:00'
        res = anon_client.get(url)
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse('appointments:pre_reserva_acceso'), res.url)

        # Verificar sesión
        session = anon_client.session
        self.assertIn('cita_pendiente', session)
        self.assertEqual(session['cita_pendiente']['dentista_id'], self.dentista1.id)
        self.assertEqual(session['cita_pendiente']['hora_inicio'], '10:00')

        # La pantalla de pre-reserva muestra el resumen y opciones de acceso
        res_pre = anon_client.get(reverse('appointments:pre_reserva_acceso'))
        self.assertEqual(res_pre.status_code, 200)
        self.assertContains(res_pre, self.dentista1.nombre_completo)
        self.assertContains(res_pre, 'Crear Cuenta de Paciente')
        self.assertContains(res_pre, 'Iniciar Sesión')

    def test_registro_conserva_seleccion_y_redirige_a_confirmar(self):
        """Al registrarse un nuevo paciente con una cita pendiente en sesión, se le redirige a confirmarla."""
        anon_client = Client()
        # 1. Selecciona franja
        anon_client.get(reverse('appointments:solicitar_cita_publica') + f'?dentista={self.dentista1.id}&fecha={self.fecha_test}&hora_inicio=10:00')

        # 2. Se registra
        res_reg = anon_client.post(reverse('accounts:registro'), {
            'username': 'nuevo_paciente_agenda',
            'first_name': 'Marta',
            'last_name': 'Navarro',
            'email': 'marta.navarro@test.com',
            'telefono': '655778899',
            'password': 'PasswordValida123!',
            'password_confirmacion': 'PasswordValida123!',
        })
        # Debe redirigir a confirmar_cita_pendiente
        self.assertEqual(res_reg.status_code, 302)
        self.assertIn(reverse('appointments:confirmar_cita_pendiente'), res_reg.url)

    def test_revalidacion_horario_disponible_confirma_cita(self):
        """Si la franja sigue disponible, la confirmación guarda la cita y limpia la sesión."""
        # Iniciar sesión con paciente 1
        self.client.login(username='paciente_test1', password='Password123!')

        # Colocar cita_pendiente en sesión
        session = self.client.session
        session['cita_pendiente'] = {
            'dentista_id': self.dentista1.id,
            'dentista_nombre': self.dentista1.nombre_completo,
            'dentista_especialidad': self.dentista1.especialidad,
            'fecha': str(self.fecha_test),
            'hora_inicio': '10:00',
        }
        session.save()

        # Confirmar reserva
        res = self.client.post(reverse('appointments:confirmar_cita_pendiente'), {
            'tratamiento': self.tratamiento.id,
            'notas': 'Cita confirmada tras inicio de sesión'
        })
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse('appointments:mis_citas'), res.url)

        # La cita debe existir en la BD con estado PENDIENTE
        cita = Cita.objects.get(dentista=self.dentista1, fecha=self.fecha_test, hora_inicio=time(10, 0))
        self.assertEqual(cita.paciente, self.paciente1)
        self.assertEqual(cita.estado, Cita.Estado.PENDIENTE)

    def test_transiciones_de_estado_validas(self):
        cita = Cita.objects.create(
            dentista=self.dentista1,
            paciente=self.paciente1,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(9, 0),
            hora_fin=time(9, 30),
            estado=Cita.Estado.PENDIENTE,
        )
        self.client.login(username='dr_test1', password='Password123!')

        confirmar = self.client.post(
            reverse('appointments:cambiar_estado_rapido', args=[cita.pk, Cita.Estado.CONFIRMADA])
        )
        self.assertEqual(confirmar.status_code, 302)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CONFIRMADA)

        transicion_invalida = self.client.post(
            reverse('appointments:cambiar_estado_rapido', args=[cita.pk, Cita.Estado.PENDIENTE])
        )
        self.assertEqual(transicion_invalida.status_code, 302)
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.CONFIRMADA)

        # La sesión debe estar limpia
        self.assertNotIn('cita_pendiente', self.client.session)

    def test_revalidacion_horario_ocupado_rechaza_cita_y_muestra_error(self):
        """
        Si otra persona ocupó la franja antes de que el usuario confirme,
        la cita NO se guarda, se avisa con mensaje de error y se redirige a elegir otro horario.
        """
        self.client.login(username='paciente_test1', password='Password123!')

        session = self.client.session
        session['cita_pendiente'] = {
            'dentista_id': self.dentista1.id,
            'dentista_nombre': self.dentista1.nombre_completo,
            'dentista_especialidad': self.dentista1.especialidad,
            'fecha': str(self.fecha_test),
            'hora_inicio': '10:00',
        }
        session.save()

        # Otra persona reserva la misma franja (10:00 a 10:45)
        Cita.objects.create(
            dentista=self.dentista1,
            paciente=self.paciente2,
            tratamiento=self.tratamiento,
            fecha=self.fecha_test,
            hora_inicio=time(10, 0),
            hora_fin=time(10, 45),
            estado=Cita.Estado.CONFIRMADA
        )

        # Intentar confirmar la cita pendiente
        res = self.client.post(reverse('appointments:confirmar_cita_pendiente'), {
            'tratamiento': self.tratamiento.id,
            'notas': 'Intento tardío'
        }, follow=True)

        # Debe rechazar y redirigir a agenda_publica
        self.assertContains(res, 'Lo sentimos: la franja horaria seleccionada ya no se encuentra disponible')
        # No debe haber ninguna cita creada para paciente 1 a esa hora
        self.assertFalse(Cita.objects.filter(paciente=self.paciente1, fecha=self.fecha_test, hora_inicio=time(10, 0)).exists())

    def test_registro_publico_restringido_estrictamente_a_pacientes(self):
        """El registro público NUNCA permite crear cuentas de dentista ni administrador."""
        anon_client = Client()
        res = anon_client.post(reverse('accounts:registro'), {
            'username': 'intento_hacker',
            'first_name': 'Hacker',
            'last_name': 'Malicioso',
            'email': 'hacker@test.com',
            'telefono': '600000000',
            'password': 'PasswordValida123!',
            'password_confirmacion': 'PasswordValida123!',
            'role': 'DENTISTA',  # Intento de inyección de rol
            'is_staff': True,    # Intento de escalada
            'is_superuser': True
        })
        self.assertEqual(res.status_code, 302)

        usuario_creado = Usuario.objects.get(username='intento_hacker')
        self.assertEqual(usuario_creado.role, Usuario.Rol.PACIENTE)
        self.assertFalse(usuario_creado.is_staff)
        self.assertFalse(usuario_creado.is_superuser)
        self.assertTrue(hasattr(usuario_creado, 'perfil_paciente'))
        self.assertFalse(hasattr(usuario_creado, 'perfil_dentista'))


    # ==========================================================
    # NUEVAS PRUEBAS (Ajustes de agenda - Nov 2026)
    # ==========================================================

    def test_columna_horas_contiene_intervalos_30_minutos(self):
        """
        La vista de agenda devuelve el eje de horas (horas_eje) con entradas
        cada 30 minutos: p. ej. 08:00, 08:30, 09:00, 09:30...
        """
        self.client.login(username='dr_test1', password='Password123!')
        res = self.client.get(reverse('appointments:dentista_agenda') + f'?vista=dia&fecha={self.fecha_test}')
        self.assertEqual(res.status_code, 200)

        horas_eje = res.context['horas_eje']
        # Debe haber entradas cada 30 minutos entre 08:00 y 21:00
        self.assertGreater(len(horas_eje), 0, "horas_eje no puede estar vacío")

        # Comprobar que existen tanto entradas de hora en punto como de media hora
        minutos = [h.minute for h in horas_eje]
        self.assertIn(0, minutos, "Debe haber entradas en la hora en punto (minuto 0)")
        self.assertIn(30, minutos, "Debe haber entradas a y media (minuto 30)")

        # Verificar que la diferencia entre entradas consecutivas es de 30 minutos
        from datetime import datetime, timedelta
        for i in range(1, len(horas_eje)):
            diff = (datetime.combine(self.fecha_test, horas_eje[i]) -
                    datetime.combine(self.fecha_test, horas_eje[i - 1]))
            self.assertEqual(diff, timedelta(minutes=30),
                             f"Intervalo esperado 30 min entre {horas_eje[i-1]} y {horas_eje[i]}")

    def test_columna_horas_agenda_publica_intervalos_30_minutos(self):
        """
        La agenda pública también devuelve el eje de horas cada 30 minutos.
        """
        anon_client = Client()
        res = anon_client.get(reverse('appointments:agenda_publica') + f'?vista=dia&fecha={self.fecha_test}')
        self.assertEqual(res.status_code, 200)

        horas_eje = res.context['horas_eje']
        minutos = [h.minute for h in horas_eje]
        self.assertIn(0, minutos)
        self.assertIn(30, minutos)

    def test_citas_se_posicionan_correctamente(self):
        """
        Las citas aparecen en el contexto con posicionamiento calculado (top_px, height_px > 0).
        """
        self.client.login(username='dr_test1', password='Password123!')
        cita = Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente1,
            tratamiento=self.tratamiento, fecha=self.fecha_test,
            hora_inicio=time(10, 0), hora_fin=time(10, 45),
            estado=Cita.Estado.CONFIRMADA
        )
        res = self.client.get(reverse('appointments:dentista_agenda') + f'?vista=dia&fecha={self.fecha_test}')
        self.assertEqual(res.status_code, 200)

        col_d1 = [col for col in res.context['columnas_dentistas'] if col['dentista'].id == self.dentista1.id][0]
        items_cita = [item for item in col_d1['citas'] if item['cita'].id == cita.id]
        self.assertEqual(len(items_cita), 1, "La cita debe aparecer en la columna del dentista")

        pos = items_cita[0]['pos']
        self.assertGreater(pos['top_px'], 0, "top_px debe ser mayor que 0 para una cita a las 10:00")
        self.assertGreater(pos['height_px'], 0, "height_px debe ser mayor que 0")

    def test_dentista_logueado_preseleccionado_al_crear_cita(self):
        """
        Cuando un dentista logueado accede al formulario de creación de cita,
        el campo 'dentista' debe tener como valor inicial su propio perfil.
        No debe preseleccionarse el primer dentista por orden alfabético.
        """
        self.client.login(username='dr_test1', password='Password123!')
        res = self.client.get(reverse('appointments:dentista_crear_cita'))
        self.assertEqual(res.status_code, 200)

        form = res.context['form']
        dentista_inicial = form.initial.get('dentista')
        self.assertIsNotNone(dentista_inicial,
                             "El campo 'dentista' debe tener un valor inicial cuando el usuario es dentista")
        self.assertEqual(dentista_inicial, self.dentista1,
                         "El dentista preseleccionado debe ser el propio usuario logueado, no otro dentista")
        self.assertNotEqual(dentista_inicial, self.dentista2,
                            "No debe preseleccionarse el dentista 2 si quien está logueado es el dentista 1")

    def test_administrador_no_preseleccionado_como_dentista(self):
        """
        Cuando un administrador (no dentista clínico) accede al formulario de creación de cita,
        el campo 'dentista' NO debe tener preseleccionado al administrador.
        El administrador solo gestiona; no es un profesional clínico.
        """
        # Crear usuario administrador (sin perfil dentista)
        admin_user = Usuario.objects.create_user(
            username='admin_test_agenda',
            password='AdminPass123!',
            role=Usuario.Rol.ADMINISTRADOR,
            is_staff=True
        )
        self.client.login(username='admin_test_agenda', password='AdminPass123!')

        res = self.client.get(reverse('appointments:dentista_crear_cita'))
        self.assertEqual(res.status_code, 200)

        form = res.context['form']
        dentista_inicial = form.initial.get('dentista')
        # El administrador no tiene perfil_dentista → no debe aparecer preseleccionado ningún dentista
        self.assertIsNone(dentista_inicial,
                         "El administrador no es un dentista clínico: el campo 'dentista' no debe preseleccionarse")

    def test_administrador_no_aparece_en_queryset_dentistas(self):
        """
        El queryset de dentistas disponibles en los formularios de cita no debe incluir
        al administrador, aunque tuviese algún perfil lingering en la base de datos.
        """
        from appointments.forms import CitaDentistaForm
        form = CitaDentistaForm()
        dentista_qs = form.fields['dentista'].queryset
        # Ningún dentista del queryset debe tener is_superuser=True o role=ADMINISTRADOR
        for dentista in dentista_qs:
            self.assertFalse(
                dentista.user.is_superuser,
                f"El dentista {dentista} tiene is_superuser=True y no debe aparecer"
            )
            self.assertNotEqual(
                dentista.user.role, Usuario.Rol.ADMINISTRADOR,
                f"El dentista {dentista} tiene role=ADMINISTRADOR y no debe aparecer"
            )

    def test_vista_lista_muestra_todas_las_citas_sin_restriccion_fecha(self):
        """
        La vista lista muestra todas las citas compatibles con los filtros activos,
        sin filtrar automáticamente por la fecha de hoy.
        """
        self.client.login(username='dr_test1', password='Password123!')

        from datetime import date, timedelta
        fecha_pasada = date(2026, 10, 15)
        fecha_futura = date(2026, 12, 20)
        hoy = date.today()

        # Crear citas en distintas fechas (no hoy)
        Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente1,
            tratamiento=self.tratamiento, fecha=fecha_pasada,
            hora_inicio=time(9, 0), hora_fin=time(9, 30),
            estado=Cita.Estado.COMPLETADA
        )
        Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente2,
            tratamiento=self.tratamiento, fecha=fecha_futura,
            hora_inicio=time(14, 0), hora_fin=time(14, 45),
            estado=Cita.Estado.CONFIRMADA
        )

        # Acceder a la vista lista sin filtro de fecha (no se filtra por hoy)
        res = self.client.get(reverse('appointments:dentista_agenda') + '?vista=lista')
        self.assertEqual(res.status_code, 200)

        citas_lista = res.context['citas_lista']
        # Deben aparecer al menos las 2 citas creadas (posiblemente más si hay test data)
        self.assertGreaterEqual(
            citas_lista.count(), 2,
            "La vista lista debe mostrar todas las citas, no solo las de hoy"
        )

    def test_detalle_cita_api_permisos(self):
        """
        El endpoint detalle_cita_api devuelve info completa con puede_editar=True
        para dentistas y deniega acceso a pacientes ajenos a la cita.
        """
        cita = Cita.objects.create(
            dentista=self.dentista1, paciente=self.paciente1,
            tratamiento=self.tratamiento, fecha=self.fecha_test,
            hora_inicio=time(10, 0), hora_fin=time(10, 30),
            estado=Cita.Estado.PENDIENTE
        )

        # Dentista → puede_editar = True
        self.client.login(username='dr_test1', password='Password123!')
        res = self.client.get(reverse('appointments:detalle_cita_api', args=[cita.pk]))
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertTrue(data['puede_editar'])
        self.assertEqual(data['estado'], 'PENDIENTE')

        # Paciente propietario → puede_editar = False (solo lectura)
        self.client.login(username='paciente_test1', password='Password123!')
        res2 = self.client.get(reverse('appointments:detalle_cita_api', args=[cita.pk]))
        self.assertEqual(res2.status_code, 200)
        data2 = json.loads(res2.content)
        self.assertFalse(data2['puede_editar'])

        # Paciente ajeno a la cita → 403 Forbidden
        self.client.login(username='paciente_test2', password='Password123!')
        res3 = self.client.get(reverse('appointments:detalle_cita_api', args=[cita.pk]))
        self.assertEqual(res3.status_code, 403)
