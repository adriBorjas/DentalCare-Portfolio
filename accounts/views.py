from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib import messages
from django.db.models import Q
from .forms import (
    LoginForm,
    RegistroPacienteForm,
    CrearPacientePorDentistaForm,
    CambiarPasswordTemporalForm
)
from .models import Usuario, Paciente, Dentista
from .decorators import dentista_requerido


def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'¡Bienvenido a DentalCare, {user.first_name or user.username}!')

            if user.must_change_password:
                messages.warning(request, 'Debe cambiar su contraseña temporal antes de continuar.')
                return redirect('accounts:cambiar_password_temporal')

            # Si el paciente seleccionó una cita en la agenda pública antes de iniciar sesión
            if 'cita_pendiente' in request.session and user.es_paciente:
                messages.info(request, 'Recuperamos la cita seleccionada en la agenda para que pueda confirmarla.')
                return redirect('appointments:confirmar_cita_pendiente')

            next_url = request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('core:dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos. Por favor revise sus credenciales.')
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, 'Ha cerrado sesión correctamente. ¡Hasta pronto!')
    return redirect('accounts:login')


def registro_paciente(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        form = RegistroPacienteForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Su cuenta de paciente ha sido creada con éxito.')

            # Si el usuario seleccionó una cita en la agenda pública antes de registrarse
            if 'cita_pendiente' in request.session:
                messages.info(request, 'Recuperamos la cita que seleccionó para que pueda confirmarla ahora.')
                return redirect('appointments:confirmar_cita_pendiente')

            return redirect('core:dashboard')
        else:
            messages.error(request, 'Por favor verifique los datos introducidos en el formulario.')
    else:
        form = RegistroPacienteForm()

    return render(request, 'accounts/registro.html', {'form': form})


@login_required
def cambiar_password_temporal(request):
    """
    Vista accesible cuando el usuario tiene must_change_password=True
    o cuando un usuario autenticado desea actualizar su clave.
    """
    if request.method == 'POST':
        form = CambiarPasswordTemporalForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Su contraseña ha sido actualizada con éxito. Ya tiene acceso completo al sistema.')
            return redirect('core:dashboard')
        else:
            messages.error(request, 'Por favor corrija los errores indicados a continuación.')
    else:
        form = CambiarPasswordTemporalForm(request.user)

    return render(request, 'accounts/cambiar_password.html', {'form': form})


@dentista_requerido
def dentista_crear_paciente(request):
    """
    Permite al dentista dar de alta una nueva cuenta de paciente asignándole una contraseña temporal
    que deberá ser cambiada en el primer acceso.
    """
    if request.method == 'POST':
        form = CrearPacientePorDentistaForm(request.POST)
        if form.is_valid():
            nuevo_usuario, paciente, password_temporal = form.save()
            context = {
                'nuevo_usuario': nuevo_usuario,
                'paciente': paciente,
                'password_temporal': password_temporal,
            }
            messages.success(request, f"Paciente {paciente.nombre_completo} dado de alta con éxito.")
            return render(request, 'accounts/paciente_creado_confirmacion.html', context)
        else:
            messages.error(request, 'No se pudo crear la cuenta del paciente. Revise los campos requeridos.')
    else:
        form = CrearPacientePorDentistaForm()

    return render(request, 'accounts/dentista_crear_paciente.html', {'form': form})


@dentista_requerido
def dentista_lista_pacientes(request):
    """
    Muestra la lista de pacientes registrados para consulta del equipo médico.
    """
    query = request.GET.get('q', '').strip()
    pacientes = Paciente.objects.select_related('user').all()
    if not (request.user.is_superuser or request.user.is_staff):
        dentista = getattr(request.user, 'perfil_dentista', None)
        pacientes = pacientes.filter(citas__dentista=dentista).distinct() if dentista else pacientes.none()

    if query:
        pacientes = pacientes.filter(
            Q(nombre__icontains=query) |
            Q(apellidos__icontains=query) |
            Q(telefono__icontains=query) |
            Q(dni__icontains=query) |
            Q(email__icontains=query)
        )

    return render(request, 'accounts/lista_pacientes.html', {
        'pacientes': pacientes,
        'query': query
    })
