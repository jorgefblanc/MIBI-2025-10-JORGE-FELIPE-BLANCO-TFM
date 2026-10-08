/** Tablero de forma de adquisición (Organización). */
(function () {
  function $(id) {
    return document.getElementById(id);
  }

  function escape(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fillTable(tableId, rows, cells) {
    const tbody = $(tableId)?.querySelector('tbody');
    if (!tbody) return;
    if (!rows?.length) {
      tbody.innerHTML = `<tr><td colspan="${cells.length}">Sin registros en el alcance actual.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((row) => `<tr>${cells.map((fn) => `<td>${fn(row)}</td>`).join('')}</tr>`)
      .join('');
  }

  async function loadAdquisicionPanel() {
    const msg = $('adq-msg');
    if (msg) {
      msg.hidden = false;
      msg.textContent = 'Cargando tablero…';
    }
    const { response, data } = await window.AtlasOps.api('/api/adquisicion/tablero');
    if (!response.ok || !data.ok) {
      if (msg) {
        msg.classList.add('error');
        msg.textContent = data.error || 'No autorizado o no se pudo cargar el tablero.';
      }
      return;
    }
    if (msg) {
      msg.hidden = true;
      msg.classList.remove('error');
      msg.textContent = '';
    }
    const t = data.totales || {};
    const kpis = $('adq-kpis');
    if (kpis) {
      kpis.innerHTML = `
        <article class="dim-kpi"><span>Equipos en dotación</span><strong>${t.equipos_dotacion || 0}</strong></article>
        <article class="dim-kpi dim-kpi--accent"><span>Comodato / Leasing (MP tercero)</span><strong>${t.terceriza_mp || 0}</strong></article>
        <article class="dim-kpi dim-kpi--ok"><span>Con modalidad conocida</span><strong>${t.conocida || 0}</strong></article>
        <article class="dim-kpi dim-kpi--warn"><span>Sin dato / No especifica</span><strong>${t.faltante || 0}</strong></article>
        <article class="dim-kpi"><span>Solicitudes pendientes</span><strong>${t.pendientes_bandeja || 0}</strong></article>
        <article class="dim-kpi"><span>Solicitudes resueltas</span><strong>${t.resueltas || 0}</strong></article>
      `;
    }
    fillTable('adq-table-empresa', data.por_empresa, [
      (r) => escape(r.empresa),
      (r) => String(r.total || 0),
      (r) => String(r.terceriza_mp || 0),
      (r) => String(r.conocida || 0),
      (r) => String(r.faltante || 0),
    ]);
    fillTable('adq-table-sede', data.por_sede, [
      (r) => escape(r.empresa),
      (r) => escape(`${r.ID_sede || ''} ${r.name_sede || ''}`.trim()),
      (r) => String(r.total || 0),
      (r) => String(r.terceriza_mp || 0),
      (r) => String(r.faltante || 0),
    ]);
    fillTable('adq-table-servicio', data.por_servicio, [
      (r) => escape(r.empresa),
      (r) => escape(r.name_sede),
      (r) => escape(r.servicio),
      (r) => String(r.total || 0),
      (r) => String(r.terceriza_mp || 0),
      (r) => String(r.faltante || 0),
    ]);
    fillTable('adq-table-pendientes', data.pendientes, [
      (r) => escape(r.empresa),
      (r) => escape(`${r.ID_sede || ''} ${r.name_sede || ''}`.trim()),
      (r) => escape(r.servicio),
      (r) => escape(r.equipo),
      (r) => escape(r.codigo),
      (r) => escape(r.forma_adquisicion || '—'),
    ]);
  }

  window.AtlasOps = window.AtlasOps || {};
  window.AtlasOps.loadAdquisicionPanel = loadAdquisicionPanel;
})();
