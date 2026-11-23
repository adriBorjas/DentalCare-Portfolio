from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_POST
from datetime import date, datetime, time, timedelta
import calendar

from .models import Cita, HorarioDentista, BloqueoDisponibilidad
from .forms import (
    ReservaCitaPacienteForm,
    CitaDentistaForm,
    HorarioDentistaForm,
    BloqueoDisponibilidadForm
)
from accounts.models import Dentista, Paciente, Usuario
from accounts.decorators import dentista_requerido, paciente_requerido
from treatments.models import Tratamiento
from django.urls import reverse
from django.core.exceptions import ValidationError


def _es_gestion_clinica(user):
    return user.is_superuser or user.is_staff


def _citas_visibles_para_usuario(queryset, user):
    if _es_gestion_clinica(user):
        return queryset
    dentista = getattr(user, 'perfil_dentista', None)
    return queryset.filter(dentista=dentista) if dentista else queryset.none()


def enmascarar_dni(dni):
    """Ofusca parcialmente el DNI para distinguir homónimos protegiendo privacidad."""
    if not dni:
        return ''
    dni_str = str(dni).strip()
    if len(dni_str) <= 4:
        return dni_str
    return f"{dni_str[:2]}***{dni_str[-3:]}"


def enmascarar_telefono(telefono):
    """Ofusca parcialmente el teléfono para privacidad (ej: 655***333)."""
    if not telefono:
        return ''
    tel_str = str(telefono).strip()
    if len(tel_str) <= 5:
        return tel_str
    return f"{tel_str[:3]}***{tel_str[-3:]}"


# ==========================================
# VISTAS PARA EL PACIENTE
# ==========================================

@paciente_requerido
def mis_citas(request):
    """
    Lista las citas asociadas exclusivamente al paciente autenticado.
    No muestra citas eliminadas lógicamente.
    """
    paciente = get_object_or_404(Paciente, user=request.user)
    citas = Cita.objects.filter(
        paciente=paciente,
        is_deleted=False
    ).exclude(
        estado=Cita.Estado.ELIMINADA
    ).order_by('-fecha', '-hora_inicio')

    return render(request, 'appointments/paciente_citas.html', {
        'paciente': paciente,
        'citas': citas,
        'hoy': timezone.localdate(),
    })


@paciente_requerido
def reservar_cita(request):
    """
    Flujo de reserva para el paciente. Selecciona dentista, tratamiento, fecha y hora.
    """
    paciente = get_object_or_404(Paciente, user=request.user)

    if request.method == 'POST':
        form = ReservaCitaPacienteForm(paciente, request.POST)
        if form.is_valid():
            cita = form.save()
            messages.success(
                request,
                f'¡Cita solicitada con éxito para el {cita.fecha.strftime("%d/%m/%Y")} a las {cita.hora_inicio.strftime("%H:%M")}! '
                'Queda registrada en estado Pendiente a la espera de confirmación clínica.'
            )
            return redirect('appointments:mis_citas')
        else:
            messages.error(request, 'No se pudo reservar la cita. Por favor revise los avisos en el formulario.')
    else:
        form = ReservaCitaPacienteForm(paciente)

    return render(request, 'appointments/paciente_reservar.html', {
        'form': form,
        'paciente': paciente
    })


@paciente_requerido
def cancelar_cita_paciente(request, pk):
    """
    Permite al paciente cancelar su propia cita si está pendiente o confirmada.
    """
    paciente = get_object_or_404(Paciente, user=request.user)
    cita = get_object_or_404(Cita, pk=pk, paciente=paciente, is_deleted=False)

    if cita.estado in [Cita.Estado.COMPLETADA, Cita.Estado.CANCELADA, Cita.Estado.ELIMINADA]:
        messages.warning(request, f'La cita seleccionada se encuentra en estado "{cita.get_estado_display()}" y no puede cancelarse.')
        return redirect('appointments:mis_citas')

    if request.method == 'POST':
        motivo = request.POST.get('motivo_cancelacion', 'Cancelada por el paciente.')
        cita.estado = Cita.Estado.CANCELADA
        cita.motivo_cancelacion = motivo
        cita.save(update_fields=['estado', 'motivo_cancelacion'])
        messages.info(request, f'Su cita del {cita.fecha.strftime("%d/%m/%Y")} ha sido cancelada correctamente.')
        return redirect('appointments:mis_citas')

    return render(request, 'appointments/paciente_cancelar_confirmacion.html', {'cita': cita})


# ==========================================
# VISTAS PARA EL DENTISTA / GESTIÓN CLÍNICA
# ==========================================

def _calcular_posicion_cita(cita, hora_base=8, minutos_totales=780):
    """
    Calcula la posición vertical relativa (en píxeles o porcentaje) de una cita
    en la cuadrícula clínica de 08:00 a 21:00 (13 horas = 780 minutos).
    """
    min_inicio = (cita.hora_inicio.hour - hora_base) * 60 + cita.hora_inicio.minute
    min_fin = (cita.hora_fin.hour - hora_base) * 60 + cita.hora_fin.minute

    # Acotar al rango visual
    min_inicio = max(0, min(min_inicio, minutos_totales))
    min_fin = max(0, min(min_fin, minutos_totales))
    duracion = max(15, min_fin - min_inicio)

    return {
        'top_px': min_inicio,
        'height_px': duracion,
        'min_inicio': min_inicio,
        'min_fin': min_fin,
    }


# ==============================================================
# AGENDA PÚBLICA DE DISPONIBILIDAD Y RESERVA SIN CUENTA
# ==============================================================

def agenda_publica(request):
    """
    Agenda pública de disponibilidad accesible para cualquier persona (incluso sin cuenta).
    Muestra únicamente los dentistas, sus horarios de consulta y las franjas disponibles,
    ocupadas o bloqueadas.
    Las franjas ocupadas se muestran como 'No disponible' SIN datos de pacientes,
    tratamientos ni información médica o clínica.
    """
    hoy = timezone.localdate()
    ahora_hora = timezone.localtime().time()

    vista = request.GET.get('vista', 'semana')
    if vista not in ['semana', 'dia']:
        vista = 'semana'

    fecha_str = request.GET.get('fecha', '')
    if fecha_str:
        try:
            fecha_ref = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_ref = hoy
    else:
        fecha_ref = hoy

    filtro_dentista = request.GET.get('dentista', '')
    dentistas_qs = Dentista.objects.filter(activo=True, user__is_superuser=False).select_related('user')
    dentista_seleccionado = None
    if filtro_dentista:
        try:
            dentista_seleccionado = dentistas_qs.get(id=filtro_dentista)
        except Dentista.DoesNotExist:
            dentista_seleccionado = None

    dentistas_en_agenda = [dentista_seleccionado] if dentista_seleccionado else list(dentistas_qs)

    horas_eje = []
    hora_actual = time(8, 0)
    while hora_actual <= time(20, 30):
        horas_eje.append(hora_actual)
        dt = datetime.combine(date.today(), hora_actual) + timedelta(minutes=30)
        hora_actual = dt.time()

    citas_activas = Cita.objects.filter(is_deleted=False).exclude(
        estado__in=[Cita.Estado.CANCELADA, Cita.Estado.ELIMINADA]
    )
    if filtro_dentista:
        citas_activas = citas_activas.filter(dentista_id=filtro_dentista)

    horarios_qs = HorarioDentista.objects.filter(activo=True)
    if filtro_dentista:
        horarios_qs = horarios_qs.filter(dentista_id=filtro_dentista)

    bloqueos_qs = BloqueoDisponibilidad.objects.all()
    if filtro_dentista:
        bloqueos_qs = bloqueos_qs.filter(dentista_id=filtro_dentista)

    contexto = {
        'vista': vista,
        'fecha_ref': fecha_ref,
        'hoy': hoy,
        'dentistas': dentistas_qs,
        'dentistas_en_agenda': dentistas_en_agenda,
        'dentista_seleccionado': dentista_seleccionado,
        'filtro_dentista': filtro_dentista,
        'horas_eje': horas_eje,
    }

    if vista == 'semana':
        inicio_semana = fecha_ref - timedelta(days=fecha_ref.weekday())
        fin_semana = inicio_semana + timedelta(days=6)

        dias_semana = []
        nombres_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        for i in range(7):
            d = inicio_semana + timedelta(days=i)
            dias_semana.append({
                'fecha': d,
                'nombre': nombres_dias[i],
                'es_hoy': (d == hoy),
                'es_pasado': (d < hoy),
                'dia_semana_num': d.weekday(),
            })

        citas_rango = citas_activas.filter(fecha__range=[inicio_semana, fin_semana])
        bloqueos_rango = bloqueos_qs.filter(fecha__range=[inicio_semana, fin_semana])

        matriz_semana = {}
        for dia_info in dias_semana:
            f = dia_info['fecha']
            matriz_semana[f] = {}
            for dnt in dentistas_en_agenda:
                # Ocupaciones anónimas: se omiten por completo nombres, tratamientos y notas
                ocupaciones_celda = []
                for c in citas_rango:
                    if c.fecha == f and c.dentista_id == dnt.id:
                        pos = _calcular_posicion_cita(c)
                        ocupaciones_celda.append({
                            'pos': pos,
                            'hora_inicio': c.hora_inicio.strftime('%H:%M'),
                            'hora_fin': c.hora_fin.strftime('%H:%M'),
                        })

                # Bloqueos anónimos: se ocultan motivos médicos o personales
                bloqueos_celda = []
                for b in bloqueos_rango:
                    if b.fecha == f and b.dentista_id == dnt.id:
                        pos_b = _calcular_posicion_cita(b)
                        bloqueos_celda.append({
                            'pos': pos_b,
                            'hora_inicio': b.hora_inicio.strftime('%H:%M'),
                            'hora_fin': b.hora_fin.strftime('%H:%M'),
                        })

                horarios_dnt_dia = horarios_qs.filter(dentista=dnt, dia_semana=f.weekday())
                trabaja_dia = horarios_dnt_dia.exists()

                matriz_semana[f][dnt.id] = {
                    'ocupaciones': ocupaciones_celda,
                    'bloqueos': bloqueos_celda,
                    'trabaja_dia': trabaja_dia,
                    'horarios': list(horarios_dnt_dia),
                }

        contexto.update({
            'inicio_semana': inicio_semana,
            'fin_semana': fin_semana,
            'dias_semana': dias_semana,
            'matriz_semana': matriz_semana,
            'ant_fecha': (fecha_ref - timedelta(days=7)).strftime('%Y-%m-%d'),
            'sig_fecha': (fecha_ref + timedelta(days=7)).strftime('%Y-%m-%d'),
            'titulo_periodo': f"Semana del {inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}",
        })

    elif vista == 'dia':
        citas_dia = citas_activas.filter(fecha=fecha_ref)
        bloqueos_dia = bloqueos_qs.filter(fecha=fecha_ref)
        horarios_dia_qs = horarios_qs.filter(dia_semana=fecha_ref.weekday())

        columnas_dentistas = []
        for dnt in dentistas_en_agenda:
            ocupaciones_dnt = []
            for c in citas_dia:
                if c.dentista_id == dnt.id:
                    pos = _calcular_posicion_cita(c)
                    ocupaciones_dnt.append({
                        'pos': pos,
                        'hora_inicio': c.hora_inicio.strftime('%H:%M'),
                        'hora_fin': c.hora_fin.strftime('%H:%M'),
                    })

            bloqueos_dnt = []
            for b in bloqueos_dia:
                if b.dentista_id == dnt.id:
                    pos_b = _calcular_posicion_cita(b)
                    bloqueos_dnt.append({
                        'pos': pos_b,
                        'hora_inicio': b.hora_inicio.strftime('%H:%M'),
                        'hora_fin': b.hora_fin.strftime('%H:%M'),
                    })

            horarios_dnt = horarios_dia_qs.filter(dentista=dnt)
            columnas_dentistas.append({
                'dentista': dnt,
                'ocupaciones': ocupaciones_dnt,
                'bloqueos': bloqueos_dnt,
                'trabaja_dia': horarios_dnt.exists(),
                'horarios': list(horarios_dnt),
            })

        nombres_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        dia_nombre = nombres_dias[fecha_ref.weekday()]
        contexto.update({
            'columnas_dentistas': columnas_dentistas,
            'ant_fecha': (fecha_ref - timedelta(days=1)).strftime('%Y-%m-%d'),
            'sig_fecha': (fecha_ref + timedelta(days=1)).strftime('%Y-%m-%d'),
            'titulo_periodo': f"{dia_nombre}, {fecha_ref.strftime('%d de %B de %Y')}",
        })

    return render(request, 'appointments/agenda_publica.html', contexto)


def solicitar_cita_publica(request):
    """
    Inicia la solicitud de cita desde el calendario público.
    Guarda dentista, fecha y hora en la sesión del usuario.
    Si el usuario ya está autenticado como paciente, va directo a confirmación.
    Si no tiene cuenta, le muestra la pantalla para registrarse o iniciar sesión.
    """
    dentista_id = request.GET.get('dentista') or request.POST.get('dentista')
    fecha_str = request.GET.get('fecha') or request.POST.get('fecha')
    hora_str = request.GET.get('hora_inicio') or request.POST.get('hora_inicio')

    if not (dentista_id and fecha_str and hora_str):
        messages.warning(request, 'Debe seleccionar un profesional, fecha y hora en el calendario.')
        return redirect('appointments:agenda_publica')

    dentista = get_object_or_404(Dentista, pk=dentista_id, activo=True)
    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        hora_obj = datetime.strptime(hora_str, '%H:%M').time()
    except ValueError:
        messages.error(request, 'Parámetros de fecha u hora no válidos.')
        return redirect('appointments:agenda_publica')

    if fecha_obj < timezone.localdate():
        messages.error(request, 'No es posible solicitar citas en fechas pasadas.')
        return redirect('appointments:agenda_publica')

    # Guardar en sesión de forma persistente
    request.session['cita_pendiente'] = {
        'dentista_id': dentista.id,
        'dentista_nombre': dentista.nombre_completo,
        'dentista_especialidad': dentista.especialidad,
        'fecha': fecha_str,
        'hora_inicio': hora_str,
    }
    request.session.modified = True

    if request.user.is_authenticated:
        if request.user.es_paciente:
            return redirect('appointments:confirmar_cita_pendiente')
        elif request.user.es_dentista:
            return redirect(f"{reverse('appointments:dentista_crear_cita')}?dentista={dentista.id}&fecha={fecha_str}&hora_inicio={hora_str}")

    return redirect('appointments:pre_reserva_acceso')


def pre_reserva_acceso(request):
    """
    Muestra al usuario no autenticado los datos de la cita que ha seleccionado
    y las opciones para Crear Cuenta de Paciente o Iniciar Sesión para confirmarla.
    """
    cita_pendiente = request.session.get('cita_pendiente')
    if not cita_pendiente:
        return redirect('appointments:agenda_publica')

    dentista = get_object_or_404(Dentista, pk=cita_pendiente['dentista_id'])
    fecha_obj = datetime.strptime(cita_pendiente['fecha'], '%Y-%m-%d').date()

    return render(request, 'appointments/pre_reserva_acceso.html', {
        'cita_pendiente': cita_pendiente,
        'dentista': dentista,
        'fecha_obj': fecha_obj,
    })


@paciente_requerido
def confirmar_cita_pendiente(request):
    """
    Paso final para confirmar la cita guardada en sesión:
    1. El paciente elige el tratamiento.
    2. Django revalida que la franja siga 100% disponible.
    3. Si ya fue ocupada o bloqueada, rechaza el guardado con aviso claro.
    4. Si está libre, crea la cita y limpia la sesión.
    """
    cita_pendiente = request.session.get('cita_pendiente')
    if not cita_pendiente:
        messages.info(request, 'No tiene ninguna solicitud de cita pendiente de confirmación.')
        return redirect('appointments:agenda_publica')

    dentista = get_object_or_404(Dentista, pk=cita_pendiente['dentista_id'], activo=True)
    fecha_obj = datetime.strptime(cita_pendiente['fecha'], '%Y-%m-%d').date()
    hora_inicio_obj = datetime.strptime(cita_pendiente['hora_inicio'], '%H:%M').time()
    paciente = get_object_or_404(Paciente, user=request.user)

    tratamientos = Tratamiento.objects.filter(activo=True)

    if request.method == 'POST':
        tratamiento_id = request.POST.get('tratamiento')
        notas = request.POST.get('notas', '').strip()

        if not tratamiento_id:
            messages.error(request, 'Debe seleccionar un tratamiento para completar la cita.')
            return render(request, 'appointments/confirmar_reserva.html', {
                'cita_pendiente': cita_pendiente,
                'dentista': dentista,
                'fecha_obj': fecha_obj,
                'tratamientos': tratamientos,
            })

        tratamiento = get_object_or_404(Tratamiento, pk=tratamiento_id, activo=True)
        duracion = tratamiento.duracion_estimada or 30
        dt_ini = datetime.combine(fecha_obj, hora_inicio_obj)
        dt_fin = dt_ini + timedelta(minutes=duracion)
        hora_fin_obj = dt_fin.time()

        # Instanciar modelo Cita para aplicar TODAS las validaciones de negocio en Django
        cita = Cita(
            dentista=dentista,
            paciente=paciente,
            tratamiento=tratamiento,
            fecha=fecha_obj,
            hora_inicio=hora_inicio_obj,
            hora_fin=hora_fin_obj,
            estado=Cita.Estado.PENDIENTE,
            notas=notas
        )

        try:
            cita.full_clean()
        except ValidationError:
            # La franja ya fue ocupada por otra persona o colisiona con un bloqueo
            request.session.pop('cita_pendiente', None)
            request.session.modified = True
            messages.error(
                request,
                'Lo sentimos: la franja horaria seleccionada ya no se encuentra disponible '
                '(ha sido reservada por otro paciente o bloqueada por la clínica). '
                'Por favor, seleccione otro horario disponible en el calendario.'
            )
            return redirect(f"{reverse('appointments:agenda_publica')}?dentista={dentista.id}&fecha={fecha_obj.strftime('%Y-%m-%d')}")

        cita.save()
        request.session.pop('cita_pendiente', None)
        request.session.modified = True
        messages.success(
            request,
            f'¡Cita solicitada con éxito para el {cita.fecha.strftime("%d/%m/%Y")} a las {cita.hora_inicio.strftime("%H:%M")}! '
            'Ha quedado registrada en estado Pendiente a la espera de confirmación clínica.'
        )
        return redirect('appointments:mis_citas')

    # En GET comprobamos preventivamente si sigue libre
    dt_estimado_fin = (datetime.combine(fecha_obj, hora_inicio_obj) + timedelta(minutes=30)).time()
    solapadas = Cita.objects.filter(
        dentista=dentista,
        fecha=fecha_obj,
        is_deleted=False
    ).exclude(
        estado__in=[Cita.Estado.CANCELADA, Cita.Estado.ELIMINADA]
    ).filter(
        hora_inicio__lt=dt_estimado_fin,
        hora_fin__gt=hora_inicio_obj
    )

    if solapadas.exists():
        request.session.pop('cita_pendiente', None)
        request.session.modified = True
        messages.warning(
            request,
            'La franja horaria que seleccionó acaba de ser ocupada. Por favor, elija otro horario libre.'
        )
        return redirect(f"{reverse('appointments:agenda_publica')}?dentista={dentista.id}&fecha={fecha_obj.strftime('%Y-%m-%d')}")

    return render(request, 'appointments/confirmar_reserva.html', {
        'cita_pendiente': cita_pendiente,
        'dentista': dentista,
        'fecha_obj': fecha_obj,
        'tratamientos': tratamientos,
    })


@dentista_requerido
def dentista_agenda(request):
    """
    Agenda clínica interactiva con vistas Semanal (por defecto), Diaria, Mensual y Lista.
    Soporta cuadrícula horaria vertical, columnas por dentista, ajuste de duración real,
    colores por estado y filtro explícito de histórico para canceladas/eliminadas.
    """
    hoy = timezone.localdate()
    vista = request.GET.get('vista', 'semana')
    if vista not in ['semana', 'dia', 'mes', 'lista']:
        vista = 'semana'

    # Fecha de referencia
    fecha_str = request.GET.get('fecha', '')
    if fecha_str:
        try:
            fecha_ref = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_ref = hoy
    else:
        fecha_ref = hoy

    filtro_estado = request.GET.get('estado', '')
    incluir_historico = request.GET.get('incluir_historico', '') in ['1', 'true', 'True', 'on']
    highlight_id = request.GET.get('highlight', '')

    dentistas_qs = Dentista.objects.filter(activo=True, user__is_superuser=False).select_related('user')
    if not _es_gestion_clinica(request.user):
        dentista_usuario = getattr(request.user, 'perfil_dentista', None)
        dentistas_qs = dentistas_qs.filter(pk=getattr(dentista_usuario, 'pk', None))
    # Cada dentista solo recibe su propia agenda. Los usuarios de gestión
    # pueden consultar el conjunto completo de dentistas autorizados.
    dentistas_en_agenda = list(dentistas_qs)

    # Base query de citas
    citas_base = Cita.objects.select_related(
        'dentista__user', 'paciente__user', 'tratamiento'
    )
    citas_base = _citas_visibles_para_usuario(citas_base, request.user)

    if filtro_estado:
        citas_base = citas_base.filter(estado=filtro_estado)

    # REGLA FUNDAMENTAL: Citas canceladas y eliminadas ocultas por defecto
    if not incluir_historico:
        citas_base = citas_base.filter(is_deleted=False).exclude(
            estado__in=[Cita.Estado.CANCELADA, Cita.Estado.ELIMINADA]
        )

    # Cuadrícula horaria de 08:00 a 20:30 (intervalos de 30 minutos)
    horas_eje = []
    hora_actual = time(8, 0)
    while hora_actual <= time(20, 30):
        horas_eje.append(hora_actual)
        dt = datetime.combine(date.today(), hora_actual) + timedelta(minutes=30)
        hora_actual = dt.time()

    contexto_vista = {
        'vista': vista,
        'fecha_ref': fecha_ref,
        'hoy': hoy,
        'dentistas': dentistas_qs,
        'dentistas_en_agenda': dentistas_en_agenda,
        'filtro_estado': filtro_estado,
        'incluir_historico': incluir_historico,
        'highlight_id': highlight_id,
        'estados': Cita.Estado.choices,
        'horas_eje': horas_eje,
    }

    # ---------------------------------------------
    # VISTA SEMANAL (Por defecto)
    # ---------------------------------------------
    if vista == 'semana':
        inicio_semana = fecha_ref - timedelta(days=fecha_ref.weekday()) # Lunes
        fin_semana = inicio_semana + timedelta(days=6) # Domingo

        dias_semana = []
        nombres_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        for i in range(7):
            d = inicio_semana + timedelta(days=i)
            dias_semana.append({
                'fecha': d,
                'nombre': nombres_dias[i],
                'es_hoy': (d == hoy),
                'dia_semana_num': d.weekday(),
            })

        citas_semana = citas_base.filter(fecha__range=[inicio_semana, fin_semana])

        # Obtener bloqueos de disponibilidad de la semana
        bloqueos_semana = BloqueoDisponibilidad.objects.filter(
            fecha__range=[inicio_semana, fin_semana]
        )
        # Horarios configurados para los dentistas
        horarios_dentistas = HorarioDentista.objects.filter(activo=True)

        # Organizar citas y bloqueos por (día, dentista)
        matriz_semana = {}
        for dia_info in dias_semana:
            f = dia_info['fecha']
            matriz_semana[f] = {}
            for dnt in dentistas_en_agenda:
                # Citas para este día y dentista
                citas_celda = []
                for c in citas_semana:
                    if c.fecha == f and c.dentista_id == dnt.id:
                        pos = _calcular_posicion_cita(c)
                        citas_celda.append({'cita': c, 'pos': pos})

                # Bloqueos para este día y dentista
                bloqueos_celda = []
                for b in bloqueos_semana:
                    if b.fecha == f and b.dentista_id == dnt.id:
                        pos_b = _calcular_posicion_cita(b)
                        bloqueos_celda.append({'bloqueo': b, 'pos': pos_b})

                # Determinar si el dentista trabaja este día de la semana
                horarios_dnt_dia = horarios_dentistas.filter(dentista=dnt, dia_semana=f.weekday())
                trabaja_dia = horarios_dnt_dia.exists()

                matriz_semana[f][dnt.id] = {
                    'citas': citas_celda,
                    'bloqueos': bloqueos_celda,
                    'trabaja_dia': trabaja_dia,
                    'horarios': list(horarios_dnt_dia),
                }

        contexto_vista.update({
            'inicio_semana': inicio_semana,
            'fin_semana': fin_semana,
            'dias_semana': dias_semana,
            'matriz_semana': matriz_semana,
            'ant_fecha': (fecha_ref - timedelta(days=7)).strftime('%Y-%m-%d'),
            'sig_fecha': (fecha_ref + timedelta(days=7)).strftime('%Y-%m-%d'),
            'titulo_periodo': f"Semana del {inicio_semana.strftime('%d/%m/%Y')} al {fin_semana.strftime('%d/%m/%Y')}",
        })

    # ---------------------------------------------
    # VISTA DIARIA
    # ---------------------------------------------
    elif vista == 'dia':
        citas_dia = citas_base.filter(fecha=fecha_ref)
        bloqueos_dia = BloqueoDisponibilidad.objects.filter(fecha=fecha_ref)

        horarios_dia_qs = HorarioDentista.objects.filter(activo=True, dia_semana=fecha_ref.weekday())

        columnas_dentistas = []
        for dnt in dentistas_en_agenda:
            citas_dnt = []
            for c in citas_dia:
                if c.dentista_id == dnt.id:
                    pos = _calcular_posicion_cita(c)
                    citas_dnt.append({'cita': c, 'pos': pos})

            bloqueos_dnt = []
            for b in bloqueos_dia:
                if b.dentista_id == dnt.id:
                    pos_b = _calcular_posicion_cita(b)
                    bloqueos_dnt.append({'bloqueo': b, 'pos': pos_b})

            horarios_dnt = horarios_dia_qs.filter(dentista=dnt)

            columnas_dentistas.append({
                'dentista': dnt,
                'citas': citas_dnt,
                'bloqueos': bloqueos_dnt,
                'trabaja_dia': horarios_dnt.exists(),
                'horarios': list(horarios_dnt),
            })

        nombres_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        dia_nombre = nombres_dias[fecha_ref.weekday()]

        contexto_vista.update({
            'columnas_dentistas': columnas_dentistas,
            'ant_fecha': (fecha_ref - timedelta(days=1)).strftime('%Y-%m-%d'),
            'sig_fecha': (fecha_ref + timedelta(days=1)).strftime('%Y-%m-%d'),
            'titulo_periodo': f"{dia_nombre}, {fecha_ref.strftime('%d de %B de %Y')}",
        })

    # ---------------------------------------------
    # VISTA MENSUAL
    # ---------------------------------------------
    elif vista == 'mes':
        año = fecha_ref.year
        mes = fecha_ref.month
        cal = calendar.Calendar(firstweekday=0) # 0 = Lunes
        semanas_mes = cal.monthdatescalendar(año, mes)

        primer_dia_mes = date(año, mes, 1)
        ultimo_dia_mes = date(año, mes, calendar.monthrange(año, mes)[1])

        citas_mes = citas_base.filter(fecha__range=[primer_dia_mes, ultimo_dia_mes])

        # Matriz de días con sus citas agrupadas
        calendario_mes = []
        for sem in semanas_mes:
            dias_fila = []
            for d in sem:
                citas_dia = [c for c in citas_mes if c.fecha == d]
                dias_fila.append({
                    'fecha': d,
                    'es_mes_actual': (d.month == mes),
                    'es_hoy': (d == hoy),
                    'citas': citas_dia,
                    'total_citas': len(citas_dia),
                })
            calendario_mes.append(dias_fila)

        # Mes anterior y siguiente
        if mes == 1:
            ant_mes_date = date(año - 1, 12, 1)
        else:
            ant_mes_date = date(año, mes - 1, 1)

        if mes == 12:
            sig_mes_date = date(año + 1, 1, 1)
        else:
            sig_mes_date = date(año, mes + 1, 1)

        nombres_meses = [
            '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ]

        contexto_vista.update({
            'calendario_mes': calendario_mes,
            'ant_fecha': ant_mes_date.strftime('%Y-%m-%d'),
            'sig_fecha': sig_mes_date.strftime('%Y-%m-%d'),
            'titulo_periodo': f"{nombres_meses[mes]} de {año}",
        })

    # ---------------------------------------------
    # VISTA LISTA / TABLA ALTERNATIVA
    # ---------------------------------------------
    elif vista == 'lista':
        # En vista lista mostramos todas las citas visibles y compatibles con el filtro de estado.
        # Si se especifica una fecha explícita en 'fecha_filtro', filtramos por dicha jornada.
        citas_lista = citas_base.order_by('-fecha', 'hora_inicio')
        filtro_fecha_exacta = request.GET.get('fecha_filtro', '').strip()
        if filtro_fecha_exacta:
            try:
                f_exacta = datetime.strptime(filtro_fecha_exacta, '%Y-%m-%d').date()
                citas_lista = citas_lista.filter(fecha=f_exacta)
            except ValueError:
                pass

        contexto_vista.update({
            'citas_lista': citas_lista,
            'filtro_fecha_filtro': filtro_fecha_exacta,
            'ant_fecha': (fecha_ref - timedelta(days=1)).strftime('%Y-%m-%d'),
            'sig_fecha': (fecha_ref + timedelta(days=1)).strftime('%Y-%m-%d'),
            'titulo_periodo': f"Listado Clínico ({citas_lista.count()} citas registradas)",
        })

    return render(request, 'appointments/dentista_agenda.html', contexto_vista)


@dentista_requerido
def buscar_citas_api(request):
    """
    Endpoint del buscador de citas integrado en la agenda.
    Permite buscar por:
      - Nombre y apellidos del paciente (o paciente sin cuenta).
      - DNI / NIE.
      - Teléfono.
      - Email.
    Por defecto muestra únicamente citas activas.
    Si se marca 'incluir_historico', incluye citas canceladas y eliminadas.
    Ofusca parcialmente DNI y teléfono para resguardo de privacidad.
    """
    termino = request.GET.get('q', '').strip()
    incluir_historico = request.GET.get('incluir_historico', '') in ['1', 'true', 'True', 'on']

    if not termino or len(termino) < 2:
        return JsonResponse({'citas': [], 'total': 0})

    filtro_q = (
        Q(paciente__nombre__icontains=termino) |
        Q(paciente__apellidos__icontains=termino) |
        Q(paciente__dni__icontains=termino) |
        Q(paciente__telefono__icontains=termino) |
        Q(paciente__email__icontains=termino) |
        Q(paciente_nombre__icontains=termino) |
        Q(paciente_telefono__icontains=termino) |
        Q(paciente_email__icontains=termino)
    )

    citas = Cita.objects.filter(filtro_q).select_related(
        'dentista__user', 'paciente__user', 'tratamiento'
    ).order_by('-fecha', 'hora_inicio')
    citas = _citas_visibles_para_usuario(citas, request.user)

    # Por defecto, solo citas activas
    if not incluir_historico:
        citas = citas.filter(is_deleted=False).exclude(
            estado__in=[Cita.Estado.CANCELADA, Cita.Estado.ELIMINADA]
        )

    resultados = []
    for c in citas[:30]:
        dni_display = enmascarar_dni(c.paciente.dni) if c.paciente and c.paciente.dni else ''
        telefono_display = enmascarar_telefono(c.telefono_paciente_display)

        # URL para navegar directamente a la cita en la agenda
        nav_url = f"/citas/agenda/?fecha={c.fecha.strftime('%Y-%m-%d')}&vista=dia&dentista={c.dentista_id}&highlight={c.id}"
        if incluir_historico:
            nav_url += "&incluir_historico=1"

        resultados.append({
            'id': c.id,
            'paciente_nombre': c.nombre_paciente_display,
            'dni_parcial': dni_display,
            'telefono_parcial': telefono_display,
            'fecha': c.fecha.strftime('%Y-%m-%d'),
            'fecha_formateada': c.fecha.strftime('%d/%m/%Y'),
            'hora_inicio': c.hora_inicio.strftime('%H:%M'),
            'hora_fin': c.hora_fin.strftime('%H:%M'),
            'duracion': c.duracion_minutos,
            'dentista': c.dentista.nombre_completo,
            'dentista_id': c.dentista_id,
            'tratamiento': c.tratamiento.nombre,
            'estado': c.estado,
            'estado_display': c.get_estado_display(),
            'is_deleted': c.is_deleted,
            'es_historica': (c.estado in [Cita.Estado.CANCELADA, Cita.Estado.ELIMINADA] or c.is_deleted),
            'url_navegacion': nav_url,
        })

    return JsonResponse({'citas': resultados, 'total': len(resultados)})


@login_required
def detalle_cita_api(request, pk):
    """
    Devuelve los datos completos de una cita para el panel lateral (offcanvas).
    Respeta estrictamente los permisos:
      - Personal clínico y de gestión: acceso a la información y acciones según estado.
      - Pacientes: solo acceden a sus propias citas en modo consulta.
    """
    cita = get_object_or_404(
        Cita.objects.select_related('dentista__user', 'paciente__user', 'tratamiento'),
        pk=pk
    )

    if not _es_gestion_clinica(request.user):
        dentista_usuario = getattr(request.user, 'perfil_dentista', None)
        if not dentista_usuario or cita.dentista_id != dentista_usuario.pk:
            if not hasattr(request.user, 'perfil_paciente') or cita.paciente != request.user.perfil_paciente:
                return JsonResponse({'error': 'No tiene permisos para consultar esta cita.'}, status=403)

    es_personal_clinico = (request.user.role == Usuario.Rol.DENTISTA or request.user.is_superuser or request.user.is_staff)

    if not es_personal_clinico:
        if not hasattr(request.user, 'perfil_paciente') or cita.paciente != request.user.perfil_paciente:
            return JsonResponse({'error': 'No tiene permisos para consultar esta cita.'}, status=403)

    puede_editar = es_personal_clinico and (not cita.is_deleted) and (cita.estado != Cita.Estado.ELIMINADA)

    data = {
        'id': cita.id,
        'paciente_nombre': cita.nombre_paciente_display,
        'paciente_telefono': cita.telefono_paciente_display,
        'paciente_email': cita.email_paciente_display,
        'paciente_dni': (cita.paciente.dni if cita.paciente and cita.paciente.dni else ''),
        'es_paciente_registrado': bool(cita.paciente),
        'dentista_id': cita.dentista_id,
        'dentista_nombre': cita.dentista.nombre_completo,
        'dentista_especialidad': cita.dentista.especialidad,
        'tratamiento_nombre': cita.tratamiento.nombre,
        'tratamiento_precio': str(cita.tratamiento.precio),
        'tratamiento_duracion': cita.tratamiento.duracion_estimada,
        'fecha': cita.fecha.strftime('%d/%m/%Y'),
        'fecha_iso': cita.fecha.strftime('%Y-%m-%d'),
        'hora_inicio': cita.hora_inicio.strftime('%H:%M'),
        'hora_fin': cita.hora_fin.strftime('%H:%M'),
        'duracion_minutos': cita.duracion_minutos,
        'estado': cita.estado,
        'estado_display': cita.get_estado_display(),
        'is_deleted': cita.is_deleted,
        'notas': cita.notas or '',
        'motivo_cancelacion': cita.motivo_cancelacion or '',
        'puede_editar': puede_editar,
        'url_editar': reverse('appointments:dentista_editar_cita', args=[cita.id]) if puede_editar else '',
        'url_eliminar': reverse('appointments:dentista_eliminar_cita', args=[cita.id]) if puede_editar else '',
        'url_confirmar': reverse('appointments:cambiar_estado_rapido', args=[cita.id, 'CONFIRMADA']) if puede_editar else '',
        'url_completar': reverse('appointments:cambiar_estado_rapido', args=[cita.id, 'COMPLETADA']) if puede_editar else '',
        'url_cancelar': reverse('appointments:cambiar_estado_rapido', args=[cita.id, 'CANCELADA']) if puede_editar else '',
    }
    return JsonResponse(data)


@dentista_requerido
def dentista_crear_cita(request):
    """
    Creación de citas desde recepción/dentista, con soporte para preselección
    desde la cuadrícula (doble clic o clic en hueco) con fecha, hora y dentista.
    """
    if request.method == 'POST':
        form = CitaDentistaForm(request.POST, user=request.user)
        if form.is_valid():
            cita = form.save()
            messages.success(request, f'Cita creada con éxito para {cita.nombre_paciente_display} el {cita.fecha.strftime("%d/%m/%Y")}.')
            return redirect(f"{redirect('appointments:dentista_agenda').url}?fecha={cita.fecha.strftime('%Y-%m-%d')}&highlight={cita.id}")
        else:
            messages.error(request, 'Revise los errores en el formulario.')
    else:
        # Preselección basada en parámetros GET del calendario
        initial = {}

        # Prioridad 1: si el usuario logueado es dentista, se preselecciona a sí mismo
        # Los administradores no son dentistas clínicos, no se preseleccionan
        if hasattr(request.user, 'perfil_dentista') and request.user.es_dentista:
            initial['dentista'] = request.user.perfil_dentista

        # Prioridad 2: si se pasa un dentista por GET (p. ej. al hacer clic en un hueco),
        # prevalece sobre la preselección automática solo si el usuario no es dentista
        # (para que un administrador pueda elegir cualquier dentista desde la cuadrícula)
        get_dentista = request.GET.get('dentista')
        if get_dentista:
            if not (hasattr(request.user, 'perfil_dentista') and request.user.es_dentista):
                initial['dentista'] = get_dentista

        get_fecha = request.GET.get('fecha')
        if get_fecha:
            initial['fecha'] = get_fecha
        else:
            initial['fecha'] = timezone.localdate()

        get_hora_inicio = request.GET.get('hora_inicio')
        if get_hora_inicio:
            initial['hora_inicio'] = get_hora_inicio
            # Por defecto estimar 30 minutos más si no se indica hora_fin
            try:
                dt_ini = datetime.strptime(get_hora_inicio, '%H:%M')
                dt_fin = dt_ini + timedelta(minutes=30)
                initial['hora_fin'] = dt_fin.strftime('%H:%M')
            except ValueError:
                pass

        get_hora_fin = request.GET.get('hora_fin')
        if get_hora_fin:
            initial['hora_fin'] = get_hora_fin

        get_paciente = request.GET.get('paciente_id')
        if get_paciente:
            initial['paciente'] = get_paciente

        form = CitaDentistaForm(initial=initial, user=request.user)

    return render(request, 'appointments/dentista_form_cita.html', {
        'form': form,
        'titulo': 'Agendar Nueva Cita Clínica'
    })


@dentista_requerido
def dentista_editar_cita(request, pk):
    """
    Edición de una cita por parte del dentista (modificar duración real, horario, estado, notas).
    """
    citas_visibles = _citas_visibles_para_usuario(Cita.objects.all(), request.user)
    cita = get_object_or_404(citas_visibles, pk=pk)
    if request.method == 'POST':
        form = CitaDentistaForm(request.POST, instance=cita, user=request.user)
        if form.is_valid():
            cita = form.save()
            messages.success(request, f'Cita #{cita.id} actualizada con éxito.')
            return redirect(f"{redirect('appointments:dentista_agenda').url}?fecha={cita.fecha.strftime('%Y-%m-%d')}&highlight={cita.id}")
        else:
            messages.error(request, 'No se pudo actualizar la cita. Verifique solapamientos u horarios.')
    else:
        form = CitaDentistaForm(instance=cita, user=request.user)

    return render(request, 'appointments/dentista_form_cita.html', {
        'form': form,
        'titulo': f'Modificar Cita #{cita.id}',
        'cita': cita
    })


@dentista_requerido
def dentista_eliminar_cita(request, pk):
    """
    Borrado lógico de la cita: se marca como ELIMINADA y is_deleted=True sin suprimirla de BD.
    """
    citas_visibles = _citas_visibles_para_usuario(Cita.objects.all(), request.user)
    cita = get_object_or_404(citas_visibles, pk=pk)
    fecha_cita = cita.fecha
    if request.method == 'POST':
        cita.delete() # Ejecuta el soft delete definido en el modelo
        messages.info(request, f'La cita #{cita.id} ha sido eliminada lógicamente del sistema.')
        return redirect(f"{redirect('appointments:dentista_agenda').url}?fecha={fecha_cita.strftime('%Y-%m-%d')}")

    return render(request, 'appointments/dentista_eliminar_confirmacion.html', {'cita': cita})


@dentista_requerido
@require_POST
def dentista_cambiar_estado_rapido(request, pk, nuevo_estado):
    """
    Cambio rápido de estado para agilizar la gestión clínica (confirmar, completar, cancelar).
    """
    citas_visibles = _citas_visibles_para_usuario(Cita.objects.all(), request.user)
    cita = get_object_or_404(citas_visibles, pk=pk)
    transiciones = Cita.TRANSICIONES_ESTADO.get(cita.estado, set())
    if nuevo_estado in transiciones:
        cita.estado = nuevo_estado
        cita.save(update_fields=['estado'])
        messages.success(request, f'Cita #{cita.id} actualizada a estado: {cita.get_estado_display()}.')
    elif nuevo_estado in dict(Cita.Estado.choices):
        messages.error(request, f'No se puede pasar una cita de "{cita.get_estado_display()}" a ese estado.')
    else:
        messages.error(request, 'Estado no válido.')
    return redirect(f"{redirect('appointments:dentista_agenda').url}?fecha={cita.fecha.strftime('%Y-%m-%d')}&highlight={cita.id}")


# ==========================================
# GESTIÓN DE HORARIOS Y BLOQUEOS DEL DENTISTA
# ==========================================

@dentista_requerido
def gestion_disponibilidad(request):
    """
    Panel para configurar horarios semanales de atención y bloqueos puntuales de disponibilidad.
    """
    dentista = None
    if hasattr(request.user, 'perfil_dentista'):
        dentista = request.user.perfil_dentista
    else:
        dentista = Dentista.objects.filter(activo=True, user__is_superuser=False).first()

    dentista_id = request.GET.get('dentista_id')
    if dentista_id and (request.user.is_superuser or request.user.is_staff):
        dentista = get_object_or_404(Dentista, pk=dentista_id, activo=True, user__is_superuser=False)

    horarios = HorarioDentista.objects.filter(dentista=dentista).order_by('dia_semana', 'hora_apertura') if dentista else []
    bloqueos = BloqueoDisponibilidad.objects.filter(dentista=dentista, fecha__gte=timezone.localdate()).order_by('fecha', 'hora_inicio') if dentista else []

    horario_form = HorarioDentistaForm()
    bloqueo_form = BloqueoDisponibilidadForm()

    return render(request, 'appointments/gestion_disponibilidad.html', {
        'dentista': dentista,
        'todos_dentistas': Dentista.objects.filter(activo=True, user__is_superuser=False),
        'horarios': horarios,
        'bloqueos': bloqueos,
        'horario_form': horario_form,
        'bloqueo_form': bloqueo_form,
    })


@dentista_requerido
def crear_horario(request):
    if request.method == 'POST':
        dentista = getattr(request.user, 'perfil_dentista', None) or Dentista.objects.filter(activo=True, user__is_superuser=False).first()
        form = HorarioDentistaForm(request.POST)
        if form.is_valid():
            horario = form.save(commit=False)
            horario.dentista = dentista
            horario.save()
            messages.success(request, f'Franja horaria añadida para el {horario.get_dia_semana_display()}.')
        else:
            messages.error(request, 'Error al guardar el horario.')
    return redirect('appointments:gestion_disponibilidad')


@dentista_requerido
@require_POST
def eliminar_horario(request, pk):
    horario = get_object_or_404(HorarioDentista, pk=pk)
    horario.delete()
    messages.info(request, 'Horario eliminado con éxito.')
    return redirect('appointments:gestion_disponibilidad')


@dentista_requerido
def crear_bloqueo(request):
    if request.method == 'POST':
        dentista = getattr(request.user, 'perfil_dentista', None) or Dentista.objects.filter(activo=True, user__is_superuser=False).first()
        form = BloqueoDisponibilidadForm(request.POST)
        if form.is_valid():
            bloqueo = form.save(commit=False)
            bloqueo.dentista = dentista
            bloqueo.save()
            messages.success(request, f'Bloqueo de disponibilidad programado para el {bloqueo.fecha}.')
        else:
            messages.error(request, 'Error al guardar el bloqueo de disponibilidad.')
    return redirect('appointments:gestion_disponibilidad')


@dentista_requerido
@require_POST
def eliminar_bloqueo(request, pk):
    bloqueo = get_object_or_404(BloqueoDisponibilidad, pk=pk)
    bloqueo.delete()
    messages.info(request, 'Bloqueo cancelado y disponibilidad reabierta.')
    return redirect('appointments:gestion_disponibilidad')
