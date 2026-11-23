from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from accounts.models import Usuario


def dentista_requerido(view_func):
    """
    Decorador que restringe el acceso al equipo odontológico y a usuarios de gestión clínica.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.info(request, 'Debe iniciar sesión para acceder a esta sección.')
            return redirect('accounts:login')
        if not (request.user.role == Usuario.Rol.DENTISTA or request.user.is_superuser or request.user.is_staff):
            messages.error(request, 'Acceso denegado: Esta función está reservada al equipo odontológico y de gestión.')
            return redirect('core:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def paciente_requerido(view_func):
    """
    Decorador que restringe el acceso a pacientes.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.info(request, 'Debe iniciar sesión para acceder a su espacio de paciente.')
            return redirect('accounts:login')
        if not request.user.es_paciente and not request.user.is_superuser:
            messages.warning(request, 'Esta sección está destinada a la consulta de pacientes.')
            return redirect('core:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view
