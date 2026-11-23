from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages


class ForcePasswordChangeMiddleware:
    """
    Middleware que intercepta peticiones de usuarios que tengan el flag
    'must_change_password' activo (cuentas creadas por dentistas con contraseña temporal)
    y los obliga a cambiar la clave antes de navegar por el sistema.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and getattr(request.user, 'must_change_password', False):
            try:
                allowed_paths = [
                    reverse('accounts:cambiar_password_temporal'),
                    reverse('accounts:logout'),
                ]
            except Exception:
                allowed_paths = ['/accounts/cambiar-password-temporal/', '/accounts/logout/']

            # Permitir rutas estáticas y rutas seguras de cambio de clave / logout
            is_allowed = any(request.path.startswith(p) for p in allowed_paths) or request.path.startswith('/static/')

            if not is_allowed:
                messages.warning(
                    request,
                    'Por motivos de seguridad, debe cambiar su contraseña temporal antes de continuar.'
                )
                return redirect('accounts:cambiar_password_temporal')

        return self.get_response(request)
