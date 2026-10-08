(() => {
  /*
   * Módulo KPIs de ingeniería clínica — réplica del instrumento Excel.
   * Persiste parámetros, entradas mensuales y estado del plan.
   * Los KPI se recalculan en el servidor en cada lectura.
   */

  const $ = (id) => document.getElementById(id);
  const SNAP_KEYS = [
    'equipos_totales',
    'equipos_criticos',
    'tecnicos',
    'mp_programados',
    'cal_programadas',
    'equipos_documentacion_completa',
    'equipos_fuera_soporte',
    'equipos_candidatos_capex',
  ];
  const SNAP_EXEC_KEYS = ['mp_ejecutados', 'correctivos', 'tiempo_reparacion_h'];

  let estado = null;
  let bound = false;
  let currentMes = 1;
  let saving = false;
  let contextoReq = 0;

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function currentUser() {
    return window.AtlasOps?.currentUser || {};
  }

  function canPickEmpresa() {
    if (typeof window.AtlasOps?.canPickAnyEmpresa === 'function') {
      return window.AtlasOps.canPickAnyEmpresa();
    }
    const u = currentUser();
    return (
      String(u.ROLL || '').toUpperCase() === 'ADMIN' ||
      Boolean(window.AtlasOps?.can?.('view_all_empresas')) ||
      Boolean(window.AtlasOps?.can?.('admin_panel'))
    );
  }

  function setMsg(text, isError = false) {
    const el = $('kpi-msg');
    if (!el) return;
    el.hidden = !text;
    el.textContent = text || '';
    el.classList.toggle('error', isError);
  }

  function setBanner(text, isError = false) {
    const el = $('kpi-banner');
    if (!el) return;
    el.hidden = !text;
    el.textContent = text || '';
    el.classList.toggle('error', isError);
  }

  function empresasFromSedes(sedes) {
    const map = new Map();
    (sedes || []).forEach((s) => {
      if (!s.empresa_id) return;
      if (!map.has(s.empresa_id)) {
        map.set(s.empresa_id, {
          id: s.empresa_id,
          ID_Empresa: s.ID_Empresa || `Empresa ${s.empresa_id}`,
          ID_NIT: s.ID_NIT || '',
        });
      }
    });
    return [...map.values()];
  }

  function fillEmpresaSelect(empresas, selectedId = '') {
    const sel = $('kpi-empresa');
    const wrap = $('kpi-empresa-wrap');
    if (!sel || !wrap) return;
    const pick = canPickEmpresa();
    wrap.hidden = false;
    sel.innerHTML = '<option value="">Selecciona empresa</option>';
    (empresas || []).forEach((e) => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = e.ID_NIT ? `${e.ID_Empresa} · ${e.ID_NIT}` : e.ID_Empresa || `Empresa ${e.id}`;
      sel.appendChild(opt);
    });
    if (selectedId) sel.value = String(selectedId);
    sel.disabled = !pick && empresas.length <= 1 && Boolean(sel.value);
  }

  function selectedEmpresaId() {
    return Number($('kpi-empresa')?.value || 0) || null;
  }

  function selectedAnio() {
    const n = Number($('kpi-anio')?.value);
    if (Number.isFinite(n) && n >= 2000 && n <= 2100) return n;
    return new Date().getFullYear();
  }

  function fmtNum(value, digits = 2) {
    if (value == null || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return n.toLocaleString('es-CO', { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  }

  function fmtPct(value) {
    if (value == null || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return `${(n * 100).toLocaleString('es-CO', { maximumFractionDigits: 1 })} %`;
  }

  function fmtMoney(value) {
    if (value == null || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return n.toLocaleString('es-CO', { maximumFractionDigits: 0 });
  }

  function fmtKpi(value, ind) {
    if (value == null || value === '') return '—';
    if (!ind) return fmtNum(value);
    if (ind.unidad === '%') return fmtPct(value);
    if (ind.unidad === 'COP') return fmtMoney(value);
    return fmtNum(value, ind.unidad === 'horas' || ind.unidad === 'días' ? 1 : 2);
  }

  function semClass(sem) {
    if (sem === 'Verde') return 'kpi-sem kpi-sem--verde';
    if (sem === 'Amarillo') return 'kpi-sem kpi-sem--amarillo';
    if (sem === 'Rojo') return 'kpi-sem kpi-sem--rojo';
    return 'kpi-sem';
  }

  function monthOf(mes) {
    return (estado?.meses || []).find((m) => Number(m.mes) === Number(mes)) || null;
  }

  function catalog() {
    return estado?.catalogo || {};
  }

  function indicatorByKey(key) {
    return (catalog().indicadores || []).find((i) => i.key === key) || null;
  }

  function fillMesSelect() {
    const sel = $('kpi-mes');
    if (!sel) return;
    const meses = catalog().meses || [];
    sel.innerHTML = meses
      .map((name, i) => `<option value="${i + 1}">${escapeHtml(name)}</option>`)
      .join('');
    sel.value = String(currentMes);
  }

  function renderGuia() {
    const el = $('kpi-guia');
    if (!el) return;
    const steps = catalog().guia || [];
    el.innerHTML = steps.map((s) => `<li>${escapeHtml(s)}</li>`).join('');
  }

  function renderParams() {
    const form = $('kpi-form-params');
    if (!form || !estado) return;
    const p = estado.params || {};
    form.innerHTML = [
      ['institucion', 'Institución', p.institucion, 'text'],
      ['proceso', 'Proceso', p.proceso, 'text'],
      ['responsable', 'Responsable', p.responsable, 'text'],
      ['costo_diario_inactividad', 'Costo diario de inactividad (COP)', p.costo_diario_inactividad, 'number'],
      ['factor_mitigacion', 'Factor de mitigación (0–1)', p.factor_mitigacion, 'number'],
      ['horas_laborales_tecnico_mes', 'Horas laborales técnico / mes', p.horas_laborales_tecnico_mes, 'number'],
      ['costo_externo_referencia', 'Costo externo de referencia (COP)', p.costo_externo_referencia, 'number'],
    ]
      .map(
        ([name, label, value, type]) => `
      <label>
        <span>${escapeHtml(label)}</span>
        <input data-kpi-edit name="${name}" type="${type}" ${type === 'number' ? 'min="0" step="any"' : 'maxlength="180"'} value="${escapeHtml(value ?? '')}" />
      </label>`
      )
      .join('');

    const tbody = $('kpi-table-metas')?.querySelector('tbody');
    if (!tbody) return;
    const metas = p.metas || {};
    tbody.innerHTML = (catalog().indicadores || [])
      .map((ind) => {
        const metaVal = metas[ind.key] ?? ind.meta;
        const step = ind.unidad === '%' || ind.unidad === 'COP' ? 'any' : 'any';
        return `<tr>
          <td>${escapeHtml(ind.tipo)}</td>
          <td>${escapeHtml(ind.nombre)}</td>
          <td>${escapeHtml(ind.unidad)}</td>
          <td><input data-kpi-edit data-kpi-meta="${escapeHtml(ind.key)}" type="number" min="0" step="${step}" value="${escapeHtml(metaVal)}" /></td>
          <td>${escapeHtml(ind.verde)}</td>
          <td>${escapeHtml(ind.amarillo)}</td>
          <td>${escapeHtml(ind.rojo)}</td>
          <td>${escapeHtml(ind.lectura)}</td>
        </tr>`;
      })
      .join('');
  }

  function execSnap(mes) {
    const raw = estado?.snapshot?.ejecucion_mes || {};
    return raw[mes] || raw[String(mes)] || {};
  }

  function fieldValue(month, key) {
    const saved = month?.inputs || {};
    if (saved[key] != null && saved[key] !== '') return saved[key];
    if (SNAP_KEYS.includes(key) && estado?.snapshot && estado.snapshot[key] != null) {
      if (!month?.derived?.tiene_datos) return estado.snapshot[key];
    }
    if (SNAP_EXEC_KEYS.includes(key) && !month?.derived?.tiene_datos) {
      const val = execSnap(currentMes)[key];
      if (val != null && val !== '') return val;
    }
    return '';
  }

  function renderEntrada() {
    const host = $('kpi-entrada-groups');
    if (!host || !estado) return;
    const month = monthOf(currentMes);
    const groups = catalog().entrada_grupos || [];
    host.innerHTML = groups
      .map((g) => {
        const fields = (g.campos || [])
          .map((f) => {
            const val = fieldValue(month, f.key);
            const inv = SNAP_KEYS.includes(f.key);
            const ej = SNAP_EXEC_KEYS.includes(f.key);
            const tag = inv ? ' <em class="kpi-inv">inventario</em>' : ej ? ' <em class="kpi-inv">ejecución</em>' : '';
            return `<label>
              <span>${escapeHtml(f.label)}${tag}</span>
              <input data-kpi-edit data-kpi-field="${escapeHtml(f.key)}" type="number" min="0" step="any" value="${escapeHtml(val)}" title="${escapeHtml(f.hint || '')}" />
              <small>${escapeHtml(f.hint || '')}</small>
            </label>`;
          })
          .join('');
        return `<fieldset class="kpi-group"><legend>${escapeHtml(g.grupo)}</legend><div class="dim-params-grid">${fields}</div></fieldset>`;
      })
      .join('');

    const hint = $('kpi-entrada-hint');
    if (hint) {
      const snap = estado.snapshot || {};
      hint.textContent = month?.derived?.tiene_datos
        ? `Mes con datos guardados. El inventario no sobrescribe lo ya registrado (${snap.nota || ''})`
        : `Mes sin guardar. Se sugieren conteos del inventario y de ejecución de mantenimientos del mes. ${snap.nota || ''}`;
    }
    renderDerived(month);
  }

  function renderDerived(month) {
    const el = $('kpi-derived');
    if (!el) return;
    const d = month?.derived || {};
    const k = month?.kpis || {};
    const cards = [
      ['Horas parque', fmtNum(d.horas_parque_total, 0)],
      ['Horas disponibles', fmtNum(d.horas_disponibles_total, 0)],
      ['OPEX total', fmtMoney(d.opex_total)],
      ['Costo inactividad', fmtMoney(d.costo_inactividad)],
      ['Índice gerencial', fmtNum(k.indice_gerencial, 1)],
      ['Semáforo', k.semaforo_global || '—'],
    ];
    el.innerHTML = cards
      .map(([label, value], i) => {
        const extra =
          label === 'Semáforo'
            ? semClass(value)
            : i === 4
              ? 'dim-kpi--accent'
              : '';
        return `<article class="dim-kpi ${extra}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></article>`;
      })
      .join('');
  }

  function renderMensuales() {
    const table = $('kpi-table-mensuales');
    if (!table || !estado) return;
    const inds = catalog().indicadores || [];
    const months = estado.meses || [];
    const head = `<thead><tr><th>Indicador</th>${months
      .map((m) => `<th>${escapeHtml(m.nombre)}</th>`)
      .join('')}</tr></thead>`;
    const bodyRows = inds
      .map((ind) => {
        const cells = months
          .map((m) => {
            if (!m.derived?.tiene_datos) return '<td>—</td>';
            return `<td><span class="${semClass('')}">${escapeHtml(fmtKpi(m.kpis?.[ind.key], ind))}</span></td>`;
          })
          .join('');
        return `<tr><th scope="row">${escapeHtml(ind.nombre)}</th>${cells}</tr>`;
      })
      .join('');
    const idxRow = `<tr class="kpi-row-total"><th scope="row">Índice gerencial</th>${months
      .map((m) =>
        m.derived?.tiene_datos
          ? `<td><span class="${semClass(m.kpis?.semaforo_global)}">${escapeHtml(fmtNum(m.kpis?.indice_gerencial, 1))}</span></td>`
          : '<td>—</td>'
      )
      .join('')}</tr>`;
    table.innerHTML = `${head}<tbody>${bodyRows}${idxRow}</tbody>`;
  }

  function renderInterpretacion() {
    const tbody = $('kpi-table-interp')?.querySelector('tbody');
    if (!tbody) return;
    const interp = catalog().interpretacion || {};
    tbody.innerHTML = (catalog().indicadores || [])
      .map((ind) => {
        const row = interp[ind.key] || {};
        return `<tr>
          <td>${escapeHtml(ind.nombre)}</td>
          <td>${escapeHtml(row.que || '')}</td>
          <td>${escapeHtml(row.bajo || '')}</td>
          <td>${escapeHtml(row.alto || '')}</td>
          <td>${escapeHtml(row.analisis || '')}</td>
          <td>${escapeHtml(row.accion || '')}</td>
        </tr>`;
      })
      .join('');
  }

  function renderAnual() {
    const anual = estado?.anual || {};
    const kpis = $('kpi-anual-kpis');
    if (kpis) {
      kpis.innerHTML = [
        ['Índice gerencial', fmtNum(anual.indice_gerencial, 1), 'dim-kpi--accent'],
        ['Meses con datos', fmtNum(anual.meses_con_datos, 0), ''],
        ['Rojos', fmtNum(anual.rojos, 0), anual.rojos ? 'dim-kpi--warn' : 'dim-kpi--ok'],
        ['Amarillos', fmtNum(anual.amarillos, 0), ''],
      ]
        .map(
          ([label, value, cls]) =>
            `<article class="dim-kpi ${cls}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></article>`
        )
        .join('');
    }
    const tbody = $('kpi-table-anual')?.querySelector('tbody');
    if (!tbody) return;
    tbody.innerHTML = (anual.indicadores || [])
      .map((row) => {
        const ind = indicatorByKey(row.key) || row;
        return `<tr>
          <td>${escapeHtml(row.tipo)}</td>
          <td>${escapeHtml(row.nombre)}</td>
          <td>${escapeHtml(fmtKpi(row.resultado, ind))}</td>
          <td>${escapeHtml(fmtKpi(row.meta, ind))}</td>
          <td><span class="${semClass(row.semaforo)}">${escapeHtml(row.semaforo)}</span></td>
          <td>${escapeHtml(row.prioridad)}</td>
          <td>${escapeHtml(row.analisis)}</td>
          <td>${escapeHtml(row.decision)}</td>
        </tr>`;
      })
      .join('');
  }

  function renderDashboard() {
    const host = $('kpi-dashboard-cards');
    const anual = estado?.anual || {};
    if (host) {
      host.innerHTML = (anual.dashboard || [])
        .map((row) => {
          const ind = indicatorByKey(row.key) || row;
          return `<article class="dim-kpi ${semClass(row.semaforo)}">
            <span>${escapeHtml(row.nombre)}</span>
            <strong>${escapeHtml(fmtKpi(row.resultado, ind))}</strong>
            <small>Meta ${escapeHtml(fmtKpi(row.meta, ind))}</small>
          </article>`;
        })
        .join('');
    }
    const chartsHost = $('kpi-dashboard-charts');
    if (chartsHost && window.AtlasOps?.charts) {
      const rows = anual.dashboard || [];
      const bySem = { Verde: 0, Amarillo: 0, Rojo: 0 };
      rows.forEach((row) => {
        if (bySem[row.semaforo] != null) bySem[row.semaforo] += 1;
      });
      const pieItems = Object.entries(bySem).map(([label, value]) => ({ label, value }));
      const barItems = rows.map((row) => ({
        label: row.nombre,
        value: Number(row.resultado) || 0,
        display: fmtKpi(row.resultado, indicatorByKey(row.key) || row),
      }));
      chartsHost.innerHTML = window.AtlasOps.charts.pair(
        'Criticidad (semáforo)',
        pieItems,
        'Resultado de indicadores',
        barItems
      );
    }
    const resumen = $('kpi-dashboard-resumen');
    if (resumen) {
      resumen.innerHTML = `<strong>${escapeHtml(anual.resumen_ejecutivo || '')}</strong>
        <span>${escapeHtml(anual.decision_ejecutiva || '')}</span>`;
    }
  }

  function renderPlan() {
    const tbody = $('kpi-table-plan')?.querySelector('tbody');
    if (!tbody || !estado) return;
    const estados = catalog().estados_decision || ['Pendiente', 'En curso', 'Cerrado'];
    tbody.innerHTML = (estado.plan || [])
      .map((row) => {
        const opts = estados
          .map(
            (e) =>
              `<option value="${escapeHtml(e)}" ${e === row.estado ? 'selected' : ''}>${escapeHtml(e)}</option>`
          )
          .join('');
        return `<tr data-kpi-key="${escapeHtml(row.key)}">
          <td>${escapeHtml(row.nombre)}</td>
          <td><span class="${semClass(row.semaforo)}">${escapeHtml(row.semaforo)}</span></td>
          <td>${escapeHtml(row.accion_plan)}</td>
          <td>${escapeHtml(row.responsable)}</td>
          <td>${escapeHtml(row.plazo)}</td>
          <td><select data-kpi-edit data-kpi-estado>${opts}</select></td>
          <td><input data-kpi-edit data-kpi-obs maxlength="500" value="${escapeHtml(row.observaciones || '')}" /></td>
        </tr>`;
      })
      .join('');
  }

  function renderInforme() {
    const el = $('kpi-informe');
    if (!el || !estado) return;
    const p = estado.params || {};
    const anual = estado.anual || {};
    el.innerHTML = `
      <article class="kpi-exec">
        <p><strong>Institución:</strong> ${escapeHtml(p.institucion || estado.empresa)}</p>
        <p><strong>Proceso:</strong> ${escapeHtml(p.proceso || '')}</p>
        <p><strong>Responsable:</strong> ${escapeHtml(p.responsable || '')}</p>
        <p><strong>Año:</strong> ${escapeHtml(estado.anio)}</p>
        <p>${escapeHtml(anual.resumen_ejecutivo || '')}</p>
        <p><strong>Decisión sugerida:</strong> ${escapeHtml(anual.decision_ejecutiva || '')}</p>
        ${
          window.AtlasOps?.charts
            ? window.AtlasOps.charts.pair(
                'Criticidad (semáforo)',
                [
                  {
                    label: 'Verde',
                    value: (anual.dashboard || []).filter((r) => r.semaforo === 'Verde').length,
                  },
                  {
                    label: 'Amarillo',
                    value: (anual.dashboard || []).filter((r) => r.semaforo === 'Amarillo').length,
                  },
                  {
                    label: 'Rojo',
                    value: (anual.dashboard || []).filter((r) => r.semaforo === 'Rojo').length,
                  },
                ],
                'Resultado de indicadores',
                (anual.dashboard || []).map((row) => ({
                  label: row.nombre,
                  value: Number(row.resultado) || 0,
                  display: fmtKpi(row.resultado, indicatorByKey(row.key) || row),
                }))
              )
            : ''
        }
      </article>
      <p class="field-hint">Use «Informe Excel» para exportar el archivo equivalente a Informe_Alta_Gerencia del instrumento.</p>
    `;
  }

  function applyEditLock() {
    const canEdit = Boolean(estado?.can_edit);
    document.querySelectorAll('#panel-kpis [data-kpi-edit]').forEach((el) => {
      el.disabled = !canEdit;
    });
  }

  function renderAll() {
    const root = $('kpi-root');
    if (!root) return;
    if (!estado) {
      root.hidden = true;
      return;
    }
    root.hidden = false;
    if ($('kpi-anio') && !document.activeElement?.id?.startsWith('kpi-')) {
      $('kpi-anio').value = estado.anio;
    } else if ($('kpi-anio') && !$('kpi-anio').value) {
      $('kpi-anio').value = estado.anio;
    }
    fillMesSelect();
    renderParams();
    renderEntrada();
    renderMensuales();
    renderInterpretacion();
    renderAnual();
    renderDashboard();
    renderPlan();
    renderInforme();
    applyEditLock();
  }

  async function loadContexto() {
    const empresaId = selectedEmpresaId();
    const req = ++contextoReq;
    if (!empresaId) {
      setBanner('Selecciona una empresa para cargar el tablero de KPIs.', true);
      estado = null;
      if (req === contextoReq) renderAll();
      return;
    }
    const anio = selectedAnio();
    setMsg('Cargando KPIs…');
    const { data } = await window.AtlasOps.api(
      `/api/kpis/contexto?empresa_id=${encodeURIComponent(empresaId)}&anio=${encodeURIComponent(anio)}`
    );
    if (req !== contextoReq) return;
    if (!data?.ok) {
      estado = null;
      renderAll();
      setMsg(data?.error || 'No se pudo cargar el módulo de KPIs.', true);
      return;
    }
    estado = data;
    if ($('kpi-anio')) $('kpi-anio').value = data.anio;
    const nAlerta = Number(data.snapshot?.equipos_sin_datos_anio || 0);
    if (nAlerta > 0) {
      setBanner(
        `${nAlerta} equipo(s) no cuentan con datos de mantenimiento, visitas u otros para el año ${data.anio}.`
      );
    } else {
      setBanner('');
    }
    setMsg('');
    renderAll();
  }

  function collectParams() {
    const form = $('kpi-form-params');
    const get = (name) => form?.elements?.[name]?.value ?? '';
    const metas = {};
    document.querySelectorAll('#kpi-table-metas [data-kpi-meta]').forEach((input) => {
      const key = input.getAttribute('data-kpi-meta');
      if (!key || input.value === '') return;
      metas[key] = Number(input.value);
    });
    return {
      empresa_id: selectedEmpresaId(),
      anio: selectedAnio(),
      institucion: get('institucion'),
      proceso: get('proceso'),
      responsable: get('responsable'),
      costo_diario_inactividad: Number(get('costo_diario_inactividad')),
      factor_mitigacion: Number(get('factor_mitigacion')),
      horas_laborales_tecnico_mes: Number(get('horas_laborales_tecnico_mes')),
      costo_externo_referencia: Number(get('costo_externo_referencia')),
      metas,
    };
  }

  function collectMonth() {
    const entrada = {};
    document.querySelectorAll('#kpi-entrada-groups [data-kpi-field]').forEach((input) => {
      const key = input.getAttribute('data-kpi-field');
      if (!key || input.value === '') return;
      const n = Number(input.value);
      if (!Number.isFinite(n)) return;
      entrada[key] = n;
    });
    return entrada;
  }

  function applyInventario(force = false) {
    const snap = estado?.snapshot || {};
    const ej = execSnap(currentMes);
    let filled = 0;
    SNAP_KEYS.forEach((key) => {
      const input = document.querySelector(`#kpi-entrada-groups [data-kpi-field="${key}"]`);
      if (!input || snap[key] == null) return;
      if (!force && input.value !== '') return;
      input.value = snap[key];
      filled += 1;
    });
    SNAP_EXEC_KEYS.forEach((key) => {
      const input = document.querySelector(`#kpi-entrada-groups [data-kpi-field="${key}"]`);
      if (!input || ej[key] == null) return;
      if (!force && input.value !== '') return;
      input.value = ej[key];
      filled += 1;
    });
    setMsg(
      filled
        ? `Se aplicaron ${filled} sugerencias de inventario/ejecución al mes. Revise y pulse Guardar mes.`
        : 'No había campos vacíos de inventario o ejecución para completar.'
    );
  }

  async function saveParams() {
    if (saving) return;
    saving = true;
    setMsg('Guardando parámetros…');
    try {
      const { data } = await window.AtlasOps.api('/api/kpis/parametros', {
        method: 'PUT',
        body: JSON.stringify(collectParams()),
      });
      if (!data?.ok) {
        setMsg(data?.error || 'No se pudieron guardar los parámetros.', true);
        return;
      }
      window.AtlasOps.showToast(data.message || 'Parámetros guardados.', 'success');
      window.AtlasOps?.collapseAccordion?.($('kpi-btn-save-params')?.closest('.dim-acc'));
      await loadContexto();
    } finally {
      saving = false;
    }
  }

  async function saveMes() {
    if (saving) return;
    saving = true;
    setMsg(`Guardando ${catalog().meses?.[currentMes - 1] || 'mes'}…`);
    try {
      const { data } = await window.AtlasOps.api(`/api/kpis/entrada/${currentMes}`, {
        method: 'PUT',
        body: JSON.stringify({
          empresa_id: selectedEmpresaId(),
          anio: selectedAnio(),
          entrada: collectMonth(),
        }),
      });
      if (!data?.ok) {
        setMsg(data?.error || 'No se pudo guardar la entrada mensual.', true);
        return;
      }
      window.AtlasOps.showToast(data.message || 'Mes guardado.', 'success');
      await loadContexto();
    } finally {
      saving = false;
    }
  }

  async function saveDecision(key, estadoVal, obs) {
    const { data } = await window.AtlasOps.api(`/api/kpis/decisiones/${encodeURIComponent(key)}`, {
      method: 'PUT',
      body: JSON.stringify({
        empresa_id: selectedEmpresaId(),
        anio: selectedAnio(),
        estado: estadoVal,
        observaciones: obs,
      }),
    });
    if (!data?.ok) {
      setMsg(data?.error || 'No se pudo guardar la decisión.', true);
      return;
    }
    const row = (estado?.plan || []).find((r) => r.key === key);
    if (row) {
      row.estado = data.estado;
      row.observaciones = data.observaciones;
    }
  }

  async function exportXlsx() {
    const empresaId = selectedEmpresaId();
    if (!empresaId) return;
    await window.AtlasOps.downloadFile(
      `/api/kpis/informe.xlsx?empresa_id=${encodeURIComponent(empresaId)}&anio=${encodeURIComponent(selectedAnio())}`,
      `kpis_${empresaId}_${selectedAnio()}.xlsx`
    );
  }

  async function bootstrapEmpresas() {
    await window.AtlasOps.ensureSedes?.();
    let empresas = empresasFromSedes(window.AtlasOps.getSedesCache?.() || []);
    if (canPickEmpresa()) {
      const { data } = await window.AtlasOps.api('/api/empresas');
      if (data?.ok && data.empresas?.length) empresas = data.empresas;
    }
    const userEmp = currentUser().empresa_id;
    fillEmpresaSelect(empresas, '');
    if (!canPickEmpresa() && userEmp) {
      const empSel = $('kpi-empresa');
      if (empSel) empSel.disabled = false;
    }
    if ($('kpi-anio') && !$('kpi-anio').value) {
      $('kpi-anio').value = new Date().getFullYear();
    }
    window.AtlasOps?.refreshOrgScopeSummaries?.();
  }

  function bindEvents() {
    if (bound) return;
    bound = true;
    $('kpi-btn-load')?.addEventListener('click', loadContexto);
    $('kpi-empresa')?.addEventListener('change', () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      loadContexto();
    });
    document.addEventListener('orgscope:applied', (ev) => {
      if (ev.detail?.key !== 'kpis') return;
      loadContexto();
    });
    $('kpi-anio')?.addEventListener('change', loadContexto);
    $('kpi-btn-inventario')?.addEventListener('click', () => applyInventario(false));
    $('kpi-btn-xlsx')?.addEventListener('click', exportXlsx);
    $('kpi-btn-save-params')?.addEventListener('click', saveParams);
    $('kpi-btn-save-mes')?.addEventListener('click', saveMes);
    $('kpi-mes')?.addEventListener('change', () => {
      currentMes = Number($('kpi-mes').value) || 1;
      renderEntrada();
      applyEditLock();
    });

    $('kpi-root')?.addEventListener('click', (ev) => {
      const accBtn = ev.target.closest('.dim-acc__toggle');
      if (!accBtn) return;
      window.AtlasOps?.exclusiveAccordion?.($('kpi-root'), accBtn);
    });

    let decTimer = null;
    $('kpi-table-plan')?.addEventListener('change', (ev) => {
      const row = ev.target.closest('tr[data-kpi-key]');
      if (!row) return;
      const key = row.getAttribute('data-kpi-key');
      const estadoVal = row.querySelector('[data-kpi-estado]')?.value;
      const obs = row.querySelector('[data-kpi-obs]')?.value || '';
      window.clearTimeout(decTimer);
      decTimer = window.setTimeout(() => saveDecision(key, estadoVal, obs), 350);
    });
    $('kpi-table-plan')?.addEventListener('blur', (ev) => {
      const input = ev.target.closest('[data-kpi-obs]');
      if (!input) return;
      const row = input.closest('tr[data-kpi-key]');
      if (!row) return;
      saveDecision(row.getAttribute('data-kpi-key'), row.querySelector('[data-kpi-estado]')?.value, input.value);
    }, true);
  }

  async function initKpisPanel() {
    bindEvents();
    await bootstrapEmpresas();
    await loadContexto();
  }

  window.AtlasOps = Object.assign(window.AtlasOps || {}, {
    loadKpisPanel: initKpisPanel,
  });
})();
