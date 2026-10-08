/** Dashboard empresarial de dimensionamiento (Organización). */
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

  function fmt(v, digits = 2) {
    if (v == null || v === '') return '—';
    const n = Number(v);
    if (Number.isNaN(n)) return '—';
    return Number.isInteger(n) ? String(n) : n.toFixed(digits);
  }

  function fmtIc(v) {
    return fmt(v, 2);
  }

  function currentUser() {
    return window.AtlasOps?.currentUser || {};
  }

  function canPickEmpresa() {
    return String(currentUser().ROLL || '').toUpperCase() === 'ADMIN';
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

  function setMsg(text, isError = false) {
    const el = $('dim-emp-msg');
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = '';
      el.classList.remove('error');
      return;
    }
    el.hidden = false;
    el.textContent = text;
    el.classList.toggle('error', isError);
  }

  function fillEmpresaSelect(empresas, selectedId) {
    const sel = $('dim-emp-empresa');
    const wrap = $('dim-emp-empresa-wrap');
    if (!sel || !wrap) return;
    wrap.hidden = !canPickEmpresa();
    sel.innerHTML = '<option value="">Selecciona empresa</option>';
    (empresas || []).forEach((e) => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = e.ID_NIT
        ? `${e.ID_Empresa} · ${e.ID_NIT}`
        : e.ID_Empresa || `Empresa ${e.id}`;
      sel.appendChild(opt);
    });
    if (selectedId) sel.value = String(selectedId);
  }

  function fillRatios(ratios, canEdit) {
    const form = $('dim-emp-form-ratios');
    if (!form) return;
    const map = {
      equipos_ic_bajo: ratios?.Bajo,
      equipos_ic_medio: ratios?.Medio,
      equipos_ic_alto: ratios?.Alto,
    };
    Object.entries(map).forEach(([name, value]) => {
      const input = form.elements[name];
      if (input) {
        input.value = value ?? '';
        input.disabled = !canEdit;
      }
    });
    const save = $('dim-emp-save-ratios');
    if (save) save.hidden = !canEdit;
  }

  function svgBarChart(title, items) {
    const max = Math.max(...items.map((i) => Number(i.value) || 0), 1);
    const rows = items
      .map((item) => {
        const v = Number(item.value) || 0;
        const w = Math.round((v / max) * 100);
        return `<div class="pm-bar">
          <span>${escape(item.label)} <em>${escape(item.display ?? String(v))}</em></span>
          <svg viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
            <rect class="pm-bar__track" x="0" y="2" width="100" height="6" rx="2"></rect>
            <rect class="pm-bar__fill" x="0" y="2" width="${w}" height="6" rx="2"></rect>
          </svg>
        </div>`;
      })
      .join('');
    return `<div class="pm-chart">
      <div class="pm-chart__title">${escape(title)}</div>
      ${rows || '<p class="field-hint">Sin datos</p>'}
    </div>`;
  }

  function donutChart(title, items) {
    const palette = ['#1f7a6c', '#3d7a70', '#c17a2e', '#4a6fa5', '#8b4d6b', '#6b7c85', '#2a6f65'];
    const total = items.reduce((s, i) => s + (Number(i.value) || 0), 0);
    let acc = 0;
    const stops = items
      .map((item, i) => {
        const v = Number(item.value) || 0;
        const start = total ? (acc / total) * 100 : 0;
        acc += v;
        const end = total ? (acc / total) * 100 : 0;
        return `${palette[i % palette.length]} ${start}% ${end}%`;
      })
      .join(', ');
    const legend = items
      .map((item, i) => {
        const v = Number(item.value) || 0;
        const pct = total ? Math.round((v / total) * 100) : 0;
        return `<li><span class="dim-donut__swatch" style="background:${palette[i % palette.length]}"></span>${escape(item.label)} <em>${v} (${pct}%)</em></li>`;
      })
      .join('');
    return `<div class="pm-chart dim-donut-card">
      <div class="pm-chart__title">${escape(title)}</div>
      <div class="dim-donut-wrap">
        <div class="dim-donut" style="background: conic-gradient(${stops || '#e6eeec 0 100%'})" role="img" aria-label="${escape(title)}"></div>
        <ul class="dim-donut-legend">${legend || '<li>Sin datos</li>'}</ul>
      </div>
    </div>`;
  }

  function renderCharts(data) {
    const root = $('dim-emp-charts');
    if (!root) return;
    const d = data.dashboard || {};
    const adq = (data.por_adquisicion || []).map((r) => ({
      label: r.forma_adquisicion,
      value: r.equipos,
    }));
    const crit = (data.dotacion?.por_criticidad_dotacion || []).map((r) => ({
      label: r.criticidad,
      value: r.equipos,
    }));
    const act = (data.resumen?.por_actividad || [])
      .filter((r) => Number(r.horas) > 0)
      .map((r) => ({
        label: r.actividad,
        value: Number(r.horas) || 0,
        display: fmt(r.horas),
      }));
    const sedes = [...(data.por_sede || [])]
      .sort((a, b) => Number(b.total_ajustado || 0) - Number(a.total_ajustado || 0))
      .slice(0, 8)
      .map((r) => ({
        label: r.name_sede || r.ID_sede || 'Sede',
        value: Number(r.ingenieros_recomendados || 0),
        display: `${fmt(r.ingenieros_recomendados, 0)} h / ${fmt(r.ingenieros_recomendados_dotacion, 0)} c`,
      }));
    const metodos = [
      { label: 'IC por horas', value: Number(d.ingenieros_recomendados || 0) },
      { label: 'IC por criticidad', value: Number(d.ingenieros_recomendados_dotacion || 0) },
      { label: 'Personal asignado', value: Number(d.ingenieros_disponibles || 0) },
    ];
    const chartsLib = window.AtlasOps?.charts;
    if (chartsLib) {
      root.innerHTML =
        chartsLib.pair(
          'Equipos en plantilla por criticidad',
          crit,
          'Horas por actividad',
          act
        ) +
        (adq.length ? chartsLib.pie('Equipos por forma de adquisición', adq) : '') +
        svgBarChart('IC recomendados vs personal', metodos) +
        (sedes.length ? svgBarChart('IC por horas (top sedes)', sedes) : '');
      return;
    }
    root.innerHTML =
      donutChart('Equipos por forma de adquisición', adq) +
      svgBarChart('Equipos en plantilla por criticidad', crit) +
      svgBarChart('Horas por actividad', act) +
      svgBarChart('IC recomendados vs personal', metodos) +
      (sedes.length ? svgBarChart('IC por horas (top sedes)', sedes) : '');
  }

  function renderDashboard(data) {
    const d = data.dashboard || {};
    const kpis = $('dim-emp-kpis');
    if (kpis) {
      const brechaH = Number(d.brecha_horas || 0);
      const brechaD = Number(d.brecha_dotacion || 0);
      kpis.innerHTML = `
        <article class="dim-kpi"><span>Sedes</span><strong>${d.sedes || 0}</strong></article>
        <article class="dim-kpi"><span>Equipos en carga horaria</span><strong>${d.total_equipos || 0}</strong></article>
        <article class="dim-kpi"><span>Equipos en plantilla</span><strong>${d.total_equipos_dotacion || 0}</strong></article>
        <article class="dim-kpi"><span>Comodato / Leasing</span><strong>${d.equipos_comodato_leasing || 0}</strong></article>
        <article class="dim-kpi"><span>Altos únicos (ratio medio)</span><strong>${d.alto_unico_como_medio || 0}</strong></article>
        <article class="dim-kpi"><span>Horas ajustadas / año</span><strong>${fmt(d.total_ajustado)}</strong></article>
        <article class="dim-kpi dim-kpi--accent"><span>IC por carga horaria</span><strong>${fmtIc(d.ingenieros_requeridos)} → ${fmt(d.ingenieros_recomendados, 0)}</strong></article>
        <article class="dim-kpi dim-kpi--accent"><span>IC por criticidad</span><strong>${fmtIc(d.ingenieros_por_dotacion)} → ${fmt(d.ingenieros_recomendados_dotacion, 0)}</strong></article>
        <article class="dim-kpi ${brechaH >= 0 && brechaD >= 0 ? 'dim-kpi--ok' : 'dim-kpi--warn'}"><span>IC/técnicos asignados a las sedes</span><strong>${d.ingenieros_disponibles || 0}</strong></article>
      `;
    }

    fillRatios(data.ratios, Boolean(data.can_edit_ratios));
    renderCharts(data);
    fillTable(
      'dim-emp-table-adquisicion',
      data.por_adquisicion || [],
      [
        (r) => escape(r.forma_adquisicion),
        (r) => String(r.equipos || 0),
        (r) => String(r.en_plantilla || 0),
        (r) => String(r.fuera_plantilla || 0),
        (r) => fmt(r.horas),
      ]
    );
    fillTable(
      'dim-emp-table-criticidad',
      data.dotacion?.por_criticidad_dotacion || [],
      [
        (r) => escape(r.criticidad),
        (r) => String(r.equipos || 0),
        (r) => fmt(r.equipos_por_ic, 0),
        (r) => fmtIc(r.ingenieros),
        (r) => fmt(r.ingenieros_recomendados, 0),
      ]
    );
    fillTable('dim-emp-table-actividad', data.resumen?.por_actividad || [], [
      (r) => escape(r.actividad),
      (r) => fmt(r.horas),
    ]);
    fillTable('dim-emp-table-sede', data.por_sede || [], [
      (r) => escape(`${r.ID_sede || ''} ${r.name_sede || ''}`.trim()),
      (r) => String(r.total_equipos || 0),
      (r) => String(r.equipos_plantilla || 0),
      (r) => String(r.equipos_comodato_leasing || 0),
      (r) => String(r.equipos_bajo || 0),
      (r) => String(r.equipos_medio || 0),
      (r) => String(r.equipos_alto || 0),
      (r) => fmt(r.total_ajustado),
      (r) => `${fmtIc(r.ingenieros_requeridos)} (${fmt(r.ingenieros_recomendados, 0)})`,
      (r) => `${fmtIc(r.ingenieros_por_dotacion)} (${fmt(r.ingenieros_recomendados_dotacion, 0)})`,
      (r) => String(r.ingenieros_disponibles || 0),
    ]);
    fillTable('dim-emp-table-tipo', data.dotacion?.por_tipo_equipo || [], [
      (r) => escape(r.equipo),
      (r) => String(r.equipos || 0),
      (r) => escape(r.criticidad),
      (r) => fmt(r.equipos_por_ic, 0),
      (r) => fmtIc(r.ingenieros),
      (r) => fmt(r.ingenieros_recomendados, 0),
    ]);
  }

  function qsEmpresa(empresaId) {
    const params = new URLSearchParams();
    if (empresaId) params.set('empresa_id', empresaId);
    const anio = Number($('dim-emp-anio')?.value) || new Date().getFullYear();
    params.set('anio', String(anio));
    const qs = params.toString();
    return qs ? `?${qs}` : '';
  }

  async function loadTablero(empresaId) {
    const content = $('dim-emp-content');
    setMsg('Cargando consolidado de sedes…');
    const qs = qsEmpresa(empresaId);
    const { response, data } = await window.AtlasOps.api(
      `/api/dimensionamiento/empresa/tablero${qs}`
    );
    if (!response.ok || !data.ok) {
      if (content) content.hidden = true;
      if ($('dim-emp-export-pdf')) $('dim-emp-export-pdf').hidden = true;
      if ($('dim-emp-export-xlsx')) $('dim-emp-export-xlsx').hidden = true;
      setMsg(data.error || 'No autorizado o no se pudo cargar el dashboard.', true);
      return;
    }
    fillEmpresaSelect(data.empresas, data.empresa?.id);
    if ($('dim-emp-anio') && data.anio) $('dim-emp-anio').value = String(data.anio);
    if (data.need_empresa) {
      if (content) content.hidden = true;
      if ($('dim-emp-export-pdf')) $('dim-emp-export-pdf').hidden = true;
      if ($('dim-emp-export-xlsx')) $('dim-emp-export-xlsx').hidden = true;
      setMsg(data.message || 'Selecciona una empresa.');
      return;
    }
    setMsg('');
    if (content) content.hidden = false;
    if ($('dim-emp-export-pdf')) $('dim-emp-export-pdf').hidden = false;
    if ($('dim-emp-export-xlsx')) $('dim-emp-export-xlsx').hidden = false;
    renderDashboard(data);
  }

  async function saveRatios() {
    const form = $('dim-emp-form-ratios');
    if (!form) return;
    const empresaId = $('dim-emp-empresa')?.value;
    const body = {
      empresa_id: empresaId ? Number(empresaId) : undefined,
      equipos_ic_bajo: Number(form.elements.equipos_ic_bajo.value),
      equipos_ic_medio: Number(form.elements.equipos_ic_medio.value),
      equipos_ic_alto: Number(form.elements.equipos_ic_alto.value),
    };
    const { response, data } = await window.AtlasOps.api('/api/dimensionamiento/empresa/ratios', {
      method: 'PUT',
      body: JSON.stringify(body),
    });
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast?.(data.error || 'No se pudieron guardar los parámetros.', 'error');
      return;
    }
    window.AtlasOps.showToast?.(data.message || 'Parámetros actualizados.', 'success');
    await loadTablero(empresaId);
  }

  async function exportInforme(kind) {
    const empresaId = $('dim-emp-empresa')?.value;
    const qs = qsEmpresa(empresaId);
    const ext = kind === 'pdf' ? 'pdf' : 'xlsx';
    try {
      await window.AtlasOps.downloadFile(
        `/api/dimensionamiento/empresa/export.${ext}${qs}`,
        `informe_dimensionamiento_empresa.${ext}`
      );
      window.AtlasOps.showToast?.(
        kind === 'pdf' ? 'Informe PDF generado.' : 'XLSX exportado.',
        'success'
      );
    } catch (err) {
      window.AtlasOps.showToast?.(err.message || 'No se pudo exportar.', 'error');
    }
  }

  function bindAccordion() {
    $('panel-dimensionamiento-empresa')?.addEventListener('click', (event) => {
      const toggle = event.target.closest('.dim-acc__toggle');
      if (!toggle) return;
      window.AtlasOps?.exclusiveAccordion?.($('panel-dimensionamiento-empresa'), toggle);
    });
  }

  let bound = false;
  async function initDimensionamientoEmpresaPanel() {
    if (!bound) {
      bound = true;
      bindAccordion();
      $('dim-emp-reload')?.addEventListener('click', () => {
        loadTablero($('dim-emp-empresa')?.value);
      });
      $('dim-emp-empresa')?.addEventListener('change', () => {
        loadTablero($('dim-emp-empresa')?.value);
      });
      if ($('dim-emp-anio') && !$('dim-emp-anio').value) {
        $('dim-emp-anio').value = String(new Date().getFullYear());
      }
      $('dim-emp-anio')?.addEventListener('change', () => {
        loadTablero($('dim-emp-empresa')?.value);
      });
      $('dim-emp-save-ratios')?.addEventListener('click', saveRatios);
      $('dim-emp-export-pdf')?.addEventListener('click', () => exportInforme('pdf'));
      $('dim-emp-export-xlsx')?.addEventListener('click', () => exportInforme('xlsx'));
    }
    await loadTablero(canPickEmpresa() ? $('dim-emp-empresa')?.value : undefined);
  }

  window.AtlasOps = window.AtlasOps || {};
  window.AtlasOps.loadDimensionamientoEmpresaPanel = initDimensionamientoEmpresaPanel;
})();
