from datetime import date, time, timedelta
from decimal import Decimal
import secrets
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import Dentista, Paciente, Usuario
from appointments.models import BloqueoDisponibilidad, Cita, HorarioDentista
from treatments.models import Tratamiento


class Command(BaseCommand):
    help = 'Puebla la base de datos con datos iniciales ficticios para DentalCare.'

    def _create_user(self, username, email, first_name, last_name, role, **flags):
        user, created = Usuario.objects.get_or_create(username=username, defaults={'email': email, 'first_name': first_name, 'last_name': last_name, 'role': role, **flags})
        if created:
            user.set_password(secrets.token_urlsafe(16))
            user.save()
        else:
            changed = False
            for field, value in {'email': email, 'role': role, **flags}.items():
                if getattr(user, field) != value:
                    setattr(user, field, value)
                    changed = True
            if changed:
                user.save(update_fields=['email', 'role', *flags.keys()])
        return user

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Iniciando carga de datos ficticios para DentalCare...'))
        admin_user = self._create_user('admin.demo', 'admin@demo.example.test', 'Admin', 'Demo', Usuario.Rol.ADMINISTRADOR, is_staff=True, is_superuser=True, must_change_password=False)
        Dentista.objects.filter(user=admin_user).delete()
        u_dentista1 = self._create_user('dentista.demo1', 'dentista1@demo.example.test', 'Doctora', 'Demo Uno', Usuario.Rol.DENTISTA, telefono='+34 000 000 001')
        d1, _ = Dentista.objects.get_or_create(user=u_dentista1, defaults={'numero_colegiado': 'COLEGIO-DEMO-001', 'especialidad': 'Odontología General y Prótesis', 'telefono': '+34 000 000 002'})
        u_dentista2 = self._create_user('dentista.demo2', 'dentista2@demo.example.test', 'Doctor', 'Demo Dos', Usuario.Rol.DENTISTA, telefono='+34 000 000 003')
        d2, _ = Dentista.objects.get_or_create(user=u_dentista2, defaults={'numero_colegiado': 'COLEGIO-DEMO-002', 'especialidad': 'Ortodoncia y Estética Dental', 'telefono': '+34 000 000 004'})
        u_paciente1 = self._create_user('paciente.demo1', 'paciente1@demo.example.test', 'Paciente', 'Demo Uno', Usuario.Rol.PACIENTE, telefono='+34 000 000 005')
        p1, _ = Paciente.objects.get_or_create(user=u_paciente1, defaults={'nombre': 'Paciente', 'apellidos': 'Demo Uno', 'telefono': '+34 000 000 006', 'email': 'paciente1@demo.example.test', 'dni': 'DNI-DEMO-001', 'fecha_nacimiento': date(1988, 5, 14), 'direccion': 'Calle Ejemplo 1, 00000 Ciudad Ficticia'})
        u_paciente2 = self._create_user('paciente.demo2', 'paciente2@demo.example.test', 'Paciente', 'Demo Dos', Usuario.Rol.PACIENTE, telefono='+34 000 000 007')
        p2, _ = Paciente.objects.get_or_create(user=u_paciente2, defaults={'nombre': 'Paciente', 'apellidos': 'Demo Dos', 'telefono': '+34 000 000 008', 'email': 'paciente2@demo.example.test', 'dni': 'DNI-DEMO-002', 'fecha_nacimiento': date(1995, 11, 23), 'direccion': 'Avenida Muestra 2, 00000 Ciudad Ficticia'})
        tratamientos_data = [('Limpieza Dental Completa', 'Profilaxis dental con ultrasonidos y pulido.', Decimal('50.00'), 30), ('Empaste Simple (Composite)', 'Restauración dental directa con resina estética.', Decimal('65.00'), 45), ('Endodoncia Unirradicular', 'Tratamiento de conducto para pieza unirradicular.', Decimal('140.00'), 60), ('Blanqueamiento Dental LED', 'Sesión intensiva en clínica con luz fría y gel de peróxido.', Decimal('210.00'), 50), ('Extracción Simple', 'Extracción quirúrgica menor de pieza dental.', Decimal('60.00'), 30), ('Revisión y Diagnóstico General', 'Inspección bucodental y radiografía digital básica.', Decimal('30.00'), 20), ('Consulta de Ortodoncia Invisible', 'Estudio preliminar y simulación 3D.', Decimal('40.00'), 30)]
        tratamientos = {}
        for nombre, descripcion, precio, duracion in tratamientos_data:
            tratamiento, _ = Tratamiento.objects.get_or_create(nombre=nombre, defaults={'descripcion': descripcion, 'precio': precio, 'duracion_estimada': duracion, 'activo': True})
            tratamientos[nombre] = tratamiento
        for dentista in (d1, d2):
            for dia in range(5):
                for apertura, cierre in ((time(9, 0), time(14, 0)), (time(16, 0), time(20, 0))):
                    HorarioDentista.objects.get_or_create(dentista=dentista, dia_semana=dia, hora_apertura=apertura, hora_cierre=cierre, defaults={'activo': True})
        fecha_bloqueo = timezone.localdate() + timedelta(days=7)
        while fecha_bloqueo.weekday() >= 5:
            fecha_bloqueo += timedelta(days=1)
        BloqueoDisponibilidad.objects.get_or_create(dentista=d1, fecha=fecha_bloqueo, hora_inicio=time(9, 0), hora_fin=time(11, 0), defaults={'motivo': 'Reunión de demostración'})
        hoy = timezone.localdate()
        dia_cita = hoy + timedelta(days=1)
        while dia_cita.weekday() >= 5:
            dia_cita += timedelta(days=1)
        Cita.objects.get_or_create(dentista=d1, fecha=dia_cita, hora_inicio=time(10, 0), defaults={'hora_fin': time(10, 45), 'paciente': p1, 'tratamiento': tratamientos['Limpieza Dental Completa'], 'estado': Cita.Estado.CONFIRMADA, 'notas': 'Cita de demostración para revisión general.'})
        Cita.objects.get_or_create(dentista=d2, fecha=dia_cita, hora_inicio=time(11, 0), defaults={'hora_fin': time(11, 30), 'paciente': p1, 'tratamiento': tratamientos['Consulta de Ortodoncia Invisible'], 'estado': Cita.Estado.PENDIENTE, 'notas': 'Reserva de demostración pendiente.'})
        Cita.objects.get_or_create(dentista=d1, fecha=dia_cita, hora_inicio=time(16, 30), defaults={'hora_fin': time(17, 15), 'paciente': None, 'paciente_nombre': 'Paciente Invitado Demo', 'paciente_telefono': '+34 000 000 009', 'paciente_email': 'invitado@demo.example.test', 'tratamiento': tratamientos['Empaste Simple (Composite)'], 'estado': Cita.Estado.CONFIRMADA, 'notas': 'Cita de demostración sin cuenta.'})
        dia_pasado = hoy - timedelta(days=3)
        while dia_pasado.weekday() >= 5:
            dia_pasado -= timedelta(days=1)
        Cita.objects.get_or_create(dentista=d1, fecha=dia_pasado, hora_inicio=time(12, 0), defaults={'hora_fin': time(12, 30), 'paciente': p2, 'tratamiento': tratamientos['Revisión y Diagnóstico General'], 'estado': Cita.Estado.COMPLETADA, 'notas': 'Revisión de demostración completada.'})
        self.stdout.write(self.style.SUCCESS('Datos ficticios, horarios y citas inicializados correctamente.'))
