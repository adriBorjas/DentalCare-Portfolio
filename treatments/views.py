from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Tratamiento
from .forms import TratamientoForm
from accounts.decorators import dentista_requerido


def lista_tratamientos(request):
    """
    Catálogo de tratamientos. Si es dentista, muestra también los inactivos y opciones de edición.
    """
    es_dentista = request.user.is_authenticated and request.user.es_dentista
    if es_dentista:
        tratamientos = Tratamiento.objects.all()
    else:
        tratamientos = Tratamiento.objects.filter(activo=True)

    return render(request, 'treatments/lista_tratamientos.html', {
        'tratamientos': tratamientos,
        'es_dentista': es_dentista
    })


@dentista_requerido
def crear_tratamiento(request):
    if request.method == 'POST':
        form = TratamientoForm(request.POST)
        if form.is_valid():
            tratamiento = form.save()
            messages.success(request, f'Tratamiento "{tratamiento.nombre}" añadido correctamente al catálogo.')
            return redirect('treatments:lista')
        else:
            messages.error(request, 'Error al guardar el tratamiento. Revise los datos.')
    else:
        form = TratamientoForm()

    return render(request, 'treatments/form_tratamiento.html', {
        'form': form,
        'titulo': 'Nuevo Tratamiento Odontológico'
    })


@dentista_requerido
def editar_tratamiento(request, pk):
    tratamiento = get_object_or_404(Tratamiento, pk=pk)
    if request.method == 'POST':
        form = TratamientoForm(request.POST, instance=tratamiento)
        if form.is_valid():
            form.save()
            messages.success(request, f'Tratamiento "{tratamiento.nombre}" actualizado con éxito.')
            return redirect('treatments:lista')
        else:
            messages.error(request, 'Error al actualizar el tratamiento.')
    else:
        form = TratamientoForm(instance=tratamiento)

    return render(request, 'treatments/form_tratamiento.html', {
        'form': form,
        'titulo': f'Editar: {tratamiento.nombre}',
        'tratamiento': tratamiento
    })


@dentista_requerido
@require_POST
def toggle_activo_tratamiento(request, pk):
    tratamiento = get_object_or_404(Tratamiento, pk=pk)
    tratamiento.activo = not tratamiento.activo
    tratamiento.save(update_fields=['activo'])
    estado_str = "activado" if tratamiento.activo else "desactivado"
    messages.info(request, f'Tratamiento "{tratamiento.nombre}" {estado_str}.')
    return redirect('treatments:lista')
