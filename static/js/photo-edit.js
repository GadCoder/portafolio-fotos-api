const form = document.getElementById('photoEditForm');
const button = document.getElementById('savePhotoButton');
const status = document.getElementById('editStatus');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (button.disabled) return;
  const fields = new FormData(form);
  const optionalText = (name) => fields.get(name).trim() || null;
  const presentation = {
    featured: fields.has('featured'),
    featuredLayout: fields.get('featuredLayout'),
    title: optionalText('title'),
    location: optionalText('location'),
    year: fields.get('year') ? Number(fields.get('year')) : null,
    seriesSlug: optionalText('seriesSlug'),
  };
  button.disabled = true;
  button.textContent = 'Guardando…';
  status.classList.remove('text-danger', 'text-success');
  status.textContent = 'Guardando los cambios…';
  try {
    const response = await fetch(`/photo/${form.dataset.photoId}/presentation`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': fields.get('csrf_token'),
      },
      body: JSON.stringify(presentation),
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Tu sesión ha caducado. Inicia sesión nuevamente para guardar.');
      }
      if (response.status === 404) {
        throw new Error('Esta fotografía ya no está disponible. Vuelve a la galería.');
      }
      throw new Error('No se pudieron guardar los cambios. Revisa los campos e inténtalo de nuevo.');
    }
    status.classList.add('text-success');
    status.textContent = 'Cambios guardados. Se mostrarán al abrir o recargar el portafolio.';
  } catch (error) {
    status.classList.add('text-danger');
    status.textContent = error instanceof TypeError
      ? 'No se pudo conectar con el servidor. Inténtalo de nuevo.'
      : error.message;
  } finally {
    button.disabled = false;
    button.textContent = 'Guardar cambios';
  }
});
