(() => {
  /* Cliente de frecuencia PM (GE y fabricante): cronograma, cumplimiento y PDF. */

  const $ = (id) => document.getElementById(id);

  const MESES_NOMBRE = [
    'Enero',
    'Febrero',
    'Marzo',
    'Abril',
    'Mayo',
    'Junio',
    'Julio',
    'Agosto',
    'Septiembre',
    'Octubre',
    'Noviembre',
    'Diciembre',
  ];

  const tipDefaults = {
    guia:
      'Diligencie el inventario PM, asigne puntajes GE, revise el intervalo TGE y la frecuencia definitiva, ' +
      'consulte el cronograma y valide el cumplimiento con el área asistencial.',
    funcion: 'Rol clínico del equipo (soporte vital, diagnóstico, terapéutico o apoyo).',
    aplicacion: 'Entorno de uso: determina el riesgo según el área asistencial.',
    requisito: 'Complejidad de la rutina de mantenimiento exigida.',
    fallas: 'Historial de fallas del equipo (frecuentes, moderadas o raras).',
    pm_fabricante: 'Intervalo en meses recomendado por el fabricante.',
    ge: 'GE = F + A + M + Hf. Si falta un componente el resultado es Revisar.',
    oms: 'Intervalo TGE derivado del GE (≥19 → 4 meses; 15–18 → 6; 12–14 → anual; <12 sin TGE).',
    definitiva:
      'Si GE≥12: TPM = min(TGE, Tfab). Si GE<12 prevalece el fabricante cuando exige PM.',
    fecha_ultimo_pm: 'Punto de partida del cronograma automático anual.',
    cronograma: 'Marca PM en los meses calculados desde la fecha del último mantenimiento.',
    validacion:
      'El operativo marca cumplimiento; el coordinador asistencial aprueba o rechaza.',
    ejecucion:
      'Las visitas cuentan como correctivo solo con duración verificable (cierre − atención). Sin esas fechas se conserva el % de MP. Llave: Código Biomédica + Código de Activo.',
    fdef_historial:
      'Fdef = (F teórica TPM + F real del historial) / 2. Sin historial se conserva la teórica.',
  };

  let contexto = null;
  let caps = {
    can_view_full: false,
    can_view_cronograma: false,
    can_edit_scores: false,
    can_edit_operational: false,
    can_execute: false,
    can_validate: false,
  };
  let catalogos = null;
  let anio = new Date().getFullYear();
  let bound = false;
  let tipsReady = false;
  const PAGE_SIZES = [10, 25, 50];
  const pagerState = {
    inv: { page: 0, size: 10 },
    crono: { page: 0, size: 10 },
    val: { page: 0, size: 10 },
  };
  const ejState = { page: 1, size: 10, total: 0, items: [], caps: { can_create: false } };
  let pendingCumplirId = null;
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

  function tipText(key) {
    const tips = (catalogos && catalogos.tooltips) || {};
    if (key === 'guia') {
      if (catalogos?.guia_nota) return catalogos.guia_nota;
      if (Array.isArray(catalogos?.guia_uso) && catalogos.guia_uso.length) {
        return catalogos.guia_uso.join(' ');
      }
    }
    return tips[key] || tipDefaults[key] || '';
  }

  function fmt(v, digits = 2) {
    if (v == null || v === '') return '—';
    const n = Number(v);
    if (Number.isNaN(n)) return '—';
    return Number.isInteger(n) ? String(n) : n.toFixed(digits);
  }

  function setMsg(text, isError = false) {
    const el = $('pm-msg');
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = '';
      return;
    }
    el.hidden = false;
    el.textContent = text;
    el.classList.toggle('error', isError);
  }

  function setBanner(text, isError = false) {
    const el = $('pm-banner');
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = '';
      return;
    }
    el.hidden = false;
    el.textContent = text;
    el.classList.toggle('error', isError);
  }

  function canPickAnyEmpresa() {
    if (typeof window.AtlasOps?.canPickAnyEmpresa === 'function') {
      return window.AtlasOps.canPickAnyEmpresa();
    }
    const u = currentUser();
    return (
      u.ROLL === 'ADMIN' ||
      Boolean(window.AtlasOps?.can?.('view_all_empresas')) ||
      Boolean(window.AtlasOps?.can?.('admin_panel'))
    );
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
    const sel = $('pm-empresa');
    if (!sel) return;
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

  function fillSedeSelectLocal(empresaId) {
    const sel = $('pm-sede');
    if (!sel) return;
    const sedes = (window.AtlasOps?.getSedesCache?.() || []).filter(
      (s) => empresaId && Number(s.empresa_id) === Number(empresaId)
    );
    const assigned = (currentUser().assigned_sede_ids || []).map(Number);
    const filtered =
      canPickAnyEmpresa() || !assigned.length
        ? sedes
        : sedes.filter((s) => assigned.includes(Number(s.id)));
    sel.innerHTML = '<option value="">Selecciona sede</option>';
    filtered.forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.ID_sede ? `${s.name_sede} (${s.ID_sede})` : s.name_sede;
      sel.appendChild(opt);
    });
  }

  function fillServicioFromSede() {
    const sedeId = $('pm-sede')?.value || '';
    const srvSel = $('pm-servicio');
    if (!srvSel) return;
    if (typeof window.AtlasOps?.fillServicioSelect === 'function') {
      window.AtlasOps.fillServicioSelect(srvSel, sedeId);
    } else {
      srvSel.innerHTML = '<option value="">Selecciona servicio</option>';
    }
  }

  async function setupScopeSelectors() {
    await window.AtlasOps.ensureSedes({ force: true });
    const sedes = window.AtlasOps.getSedesCache?.() || [];
    let empresas = empresasFromSedes(sedes);
    if (canPickAnyEmpresa()) {
      const { data } = await window.AtlasOps.api('/api/empresas');
      if (data?.ok && data.empresas?.length) empresas = data.empresas;
    }
    const userEmp = currentUser().empresa_id;
    fillEmpresaSelect(empresas, '');
    fillSedeSelectLocal('');
    if (!canPickAnyEmpresa() && userEmp) {
      const empSel = $('pm-empresa');
      if (empSel) empSel.disabled = false;
    }
    fillServicioFromSede();

    const anioInput = $('pm-anio');
    if (anioInput && !anioInput.value) {
      anioInput.value = String(anio);
    }
    window.AtlasOps?.refreshOrgScopeSummaries?.();
  }

  function catalogOptions(list, selected) {
    const items = list || [];
    const opts = [`<option value="">—</option>`].concat(
      items.map((item) => {
        const label = typeof item === 'string' ? item : item.label;
        const sel = label === selected ? 'selected' : '';
        return `<option value="${escapeHtml(label)}" ${sel}>${escapeHtml(label)}</option>`;
      })
    );
    return opts.join('');
  }

  function estadoOptions(selected) {
    const estados =
      (catalogos && catalogos.estados) ||
      ['Operativo', 'En observación', 'Fuera de servicio', 'Retirado'];
    return estados
      .map(
        (e) =>
          `<option value="${escapeHtml(e)}" ${e === selected ? 'selected' : ''}>${escapeHtml(
            e
          )}</option>`
      )
      .join('');
  }

  function canEditAnything() {
    return Boolean(caps.can_edit_operational || caps.can_edit_scores);
  }

  function applyCapsUi() {
    const viewFull = Boolean(caps.can_view_full);
    const editOps = Boolean(caps.can_edit_operational);
    const editScores = Boolean(caps.can_edit_scores);
    const editAny = canEditAnything();

    ['inventario', 'ge', 'oms', 'definitiva', 'ejecucion'].forEach((sec) => {
      document
        .querySelectorAll(`#panel-frecuencia-pm [data-pm-section="${sec}"]`)
        .forEach((el) => {
          el.hidden = !viewFull;
        });
    });

    document.querySelectorAll('#panel-frecuencia-pm [data-pm-edit]').forEach((el) => {
      if (el.tagName === 'BUTTON') el.hidden = !editOps;
      else el.disabled = !editAny;
    });

    const syncBtn = $('pm-btn-sync');
    const recalcBtn = $('pm-btn-recalc');
    if (syncBtn) syncBtn.hidden = !editOps;
    if (recalcBtn) recalcBtn.hidden = !editOps;
    const ejForm = $('pm-ejecucion-form');
    if (ejForm) ejForm.hidden = !editOps;

    document.querySelectorAll('#panel-frecuencia-pm [data-pm-score]').forEach((el) => {
      el.disabled = !editScores;
    });

    document.querySelectorAll('#panel-frecuencia-pm [data-pm-ops]').forEach((el) => {
      el.disabled = !editOps;
    });

    let banner =
      'Modo consulta: cronograma, validación y dashboard disponibles según su rol.';
    if (viewFull && editOps && editScores) {
      banner =
        'Modo completo (ADMIN): edita puntajes GE, opera inventario/cronograma y valida.';
    } else if (viewFull && editOps) {
      banner =
        'Modo operativo: sincroniza inventario, edita datos operativos y marca cumplimiento. Los puntajes GE los define Administración.';
    } else if (caps.can_validate) {
      banner =
        'Modo asistencial (validación): consulte el cronograma y apruebe o rechace cumplimientos.';
    } else if (caps.can_view_cronograma) {
      banner = 'Modo asistencial: consulte cronograma y estado de validación.';
    }
    setBanner(banner, !viewFull && !caps.can_view_cronograma);
  }

  function equipos() {
    return (contexto && contexto.equipos) || [];
  }

  function readPageSize(selectId, key) {
    const n = Number($(selectId)?.value);
    if (PAGE_SIZES.includes(n)) pagerState[key].size = n;
    return pagerState[key].size;
  }

  function paginate(rows, key, searchId, sizeId, pagerId, labelId) {
    const q = String($(searchId)?.value || '')
      .trim()
      .toLowerCase();
    const filtered = q
      ? rows.filter((row) => String(row.equipo || '').toLowerCase().includes(q))
      : rows;
    const size = readPageSize(sizeId, key);
    const total = filtered.length;
    const pages = Math.max(1, Math.ceil(total / size) || 1);
    if (pagerState[key].page > pages - 1) pagerState[key].page = pages - 1;
    if (pagerState[key].page < 0) pagerState[key].page = 0;
    const start = total ? pagerState[key].page * size : 0;
    const slice = filtered.slice(start, start + size);
    const pager = $(pagerId);
    const label = $(labelId);
    if (pager) pager.hidden = total <= size && !q;
    if (label) {
      const from = total ? start + 1 : 0;
      const to = start + slice.length;
      label.textContent = total
        ? `${from}–${to} de ${total}${q ? ` (filtro: ${filtered.length === rows.length ? '' : total + ' coincidencias'})` : ''}`
        : q
          ? 'Ningún equipo coincide con la búsqueda.'
          : '';
    }
    return { slice, total, filtered };
  }

  function bindPager(key, searchId, sizeId, prevId, nextId, renderFn) {
    $(searchId)?.addEventListener('input', () => {
      pagerState[key].page = 0;
      renderFn();
    });
    $(sizeId)?.addEventListener('change', () => {
      pagerState[key].page = 0;
      renderFn();
    });
    $(prevId)?.addEventListener('click', () => {
      pagerState[key].page -= 1;
      renderFn();
    });
    $(nextId)?.addEventListener('click', () => {
      pagerState[key].page += 1;
      renderFn();
    });
  }

  function cumplimientoStats(list) {
    let total = 0;
    let cumplidos = 0;
    let aprobados = 0;
    let pendientes = 0;
    let rechazados = 0;
    (list || []).forEach((eq) => {
      (eq.validaciones || []).forEach((v) => {
        total += 1;
        const st = String(v.estado || '').toUpperCase();
        if (st === 'APROBADO') {
          aprobados += 1;
          cumplidos += 1;
        } else if (st === 'CUMPLIDO') {
          cumplidos += 1;
        } else if (st === 'RECHAZADO') {
          rechazados += 1;
        } else {
          pendientes += 1;
        }
      });
    });
    const pct = total ? Math.round((aprobados / total) * 100) : 0;
    return { total, cumplidos, aprobados, pendientes, rechazados, pct };
  }

  function renderInventario() {
    const body = $('pm-inv-body');
    if (!body) return;
    if (!caps.can_view_full) {
      body.innerHTML = '';
      return;
    }
    const rows = equipos();
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="10">Sin equipos PM. Use «Sincronizar inventario» o seleccione otro servicio.</td></tr>';
      if ($('pm-inv-pager')) $('pm-inv-pager').hidden = true;
      return;
    }
    const { slice, total } = paginate(
      rows,
      'inv',
      'pm-inv-search',
      'pm-inv-page-size',
      'pm-inv-pager',
      'pm-inv-page-label'
    );
    if (!total) {
      body.innerHTML = '<tr><td colspan="10">Ningún equipo coincide con la búsqueda.</td></tr>';
      return;
    }
    const editOps = caps.can_edit_operational;
    const editScores = caps.can_edit_scores;
    const editAny = canEditAnything();
    const opsDis = editOps ? '' : 'disabled';
    const scoreAttr = editScores ? '' : 'disabled';

    body.innerHTML = slice
      .map((eq) => {
        const id = eq.id;
        return `<tr data-pm-row="${id}">
          <td>${escapeHtml(eq.codigo_equipo || '—')}</td>
          <td>${escapeHtml(eq.equipo || '—')}${window.AtlasOps.equipoAlertaMarkup(eq)}</td>
          <td>
            <select data-pm-ops data-field="estado" ${opsDis}>
              ${estadoOptions(eq.estado || 'Operativo')}
            </select>
          </td>
          <td>
            <input data-pm-ops data-field="pm_fabricante_meses" type="number" min="0" step="1"
              value="${escapeHtml(eq.pm_fabricante_meses ?? '')}" ${opsDis} style="width:4.5rem" />
          </td>
          <td>
            <select data-pm-score data-field="funcion" ${scoreAttr}>
              ${catalogOptions(catalogos?.funcion, eq.funcion)}
            </select>
          </td>
          <td>
            <select data-pm-score data-field="aplicacion" ${scoreAttr}>
              ${catalogOptions(catalogos?.aplicacion, eq.aplicacion)}
            </select>
          </td>
          <td>
            <select data-pm-score data-field="requisito_mantto" ${scoreAttr}>
              ${catalogOptions(catalogos?.requisito_mantto, eq.requisito_mantto)}
            </select>
          </td>
          <td>
            <select data-pm-score data-field="antecedentes_fallas" ${scoreAttr}>
              ${catalogOptions(catalogos?.antecedentes_fallas, eq.antecedentes_fallas)}
            </select>
          </td>
          <td>
            <input data-pm-ops data-field="fecha_ultimo_pm" type="date"
              value="${escapeHtml((eq.fecha_ultimo_pm || '').toString().slice(0, 10))}" ${opsDis} />
          </td>
          <td>
            ${
              editAny
                ? `<button type="button" class="btn btn-ghost" data-pm-save="${id}">Guardar</button>`
                : ''
            }
          </td>
        </tr>`;
      })
      .join('');
  }

  function renderGe() {
    const body = $('pm-ge-body');
    if (!body) return;
    if (!caps.can_view_full) {
      body.innerHTML = '';
      return;
    }
    const rows = equipos();
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="6">Sin datos GE.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(
        (eq) => `<tr>
          <td>${escapeHtml(eq.equipo || '—')}${window.AtlasOps.equipoAlertaMarkup(eq)}</td>
          <td>${fmt(eq.puntaje_funcion, 0)}</td>
          <td>${fmt(eq.puntaje_aplicacion, 0)}</td>
          <td>${fmt(eq.puntaje_requisito, 0)}</td>
          <td>${fmt(eq.puntaje_fallas, 0)}</td>
          <td class="col-calc"><strong>${fmt(eq.ge_total, 0)}</strong></td>
        </tr>`
      )
      .join('');
  }

  function renderOms() {
    const body = $('pm-oms-body');
    if (!body) return;
    if (!caps.can_view_full) {
      body.innerHTML = '';
      return;
    }
    const rows = equipos();
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="4">Sin intervalos TGE.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(
        (eq) => `<tr>
          <td>${escapeHtml(eq.equipo || '—')}${window.AtlasOps.equipoAlertaMarkup(eq)}</td>
          <td>${fmt(eq.ge_total, 0)}</td>
          <td>${escapeHtml(eq.frecuencia_oms || '—')}</td>
          <td>${escapeHtml(eq.accion_sugerida || '—')}</td>
        </tr>`
      )
      .join('');
  }

  function renderDefinitiva() {
    const body = $('pm-def-body');
    if (!body) return;
    if (!caps.can_view_full) {
      body.innerHTML = '';
      return;
    }
    const rows = equipos();
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="7">Sin frecuencias definitivas.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map((eq) => {
        const fab =
          eq.pm_fabricante_meses != null && eq.pm_fabricante_meses !== ''
            ? `Cada ${fmt(eq.pm_fabricante_meses, 0)} meses`
            : '—';
        const real = eq.ejecucion?.real?.intervalo_promedio_meses;
        const realTxt =
          real != null
            ? `Cada ${fmt(real, 1)} meses`
            : eq.ejecucion?.cobertura === 'sin_historial'
              ? 'Sin historial'
              : 'Parcial';
        const fdef = eq.ejecucion?.definitiva?.f_def_label || '—';
        const mc = Number(eq.ejecucion?.real?.correctivos || 0);
        const vis = Number(eq.ejecucion?.real?.visitas || 0);
        return `<tr>
          <td>${escapeHtml(eq.equipo || '—')}${window.AtlasOps.equipoAlertaMarkup(eq)}</td>
          <td>${escapeHtml(fab)}</td>
          <td>${escapeHtml(eq.frecuencia_oms || '—')}</td>
          <td class="col-calc"><strong>${escapeHtml(eq.frecuencia_definitiva || '—')}</strong></td>
          <td>${escapeHtml(realTxt)}</td>
          <td>${mc} / ${vis}</td>
          <td class="col-calc">${escapeHtml(fdef)}</td>
        </tr>`;
      })
      .join('');
  }

  function renderCronograma() {
    const body = $('pm-crono-body');
    if (!body) return;
    const rows = equipos();
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="16">Sin cronograma. Seleccione un servicio o sincronice inventario.</td></tr>';
      if ($('pm-crono-pager')) $('pm-crono-pager').hidden = true;
      return;
    }
    const { slice, total } = paginate(
      rows,
      'crono',
      'pm-crono-search',
      'pm-crono-page-size',
      'pm-crono-pager',
      'pm-crono-page-label'
    );
    if (!total) {
      body.innerHTML = '<tr><td colspan="16">Ningún equipo coincide con la búsqueda.</td></tr>';
      return;
    }
    body.innerHTML = slice
      .map((eq) => {
        const meses = eq.meses || {};
        const cells = [];
        for (let m = 1; m <= 12; m += 1) {
          const marked = Number(meses[m] || meses[String(m)] || 0);
          cells.push(
            marked
              ? '<td class="pm-mark" title="PM programado">PM</td>'
              : '<td></td>'
          );
        }
        const obs =
          (eq.cronograma && eq.cronograma.observacion) ||
          (eq.frecuencia_definitiva && String(eq.frecuencia_definitiva).includes('Correctivo')
            ? 'Correctivo bajo demanda'
            : '');
        return `<tr class="${eq.en_programa_pm === false ? 'pm-row--out' : ''}">
          <td>${escapeHtml(eq.equipo || '—')}${window.AtlasOps.equipoAlertaMarkup(eq)}</td>
          <td>${escapeHtml((eq.fecha_ultimo_pm || '').toString().slice(0, 10) || '—')}</td>
          <td>${escapeHtml(eq.frecuencia_definitiva || '—')}</td>
          ${cells.join('')}
          <td>${escapeHtml(obs || (eq.en_programa_pm === false ? 'Fuera de programa PM' : '—'))}</td>
        </tr>`;
      })
      .join('');
  }

  function svgBarChart(title, items) {
    const max = Math.max(1, ...items.map((i) => Number(i.value) || 0));
    const rows = items
      .map((item) => {
        const v = Number(item.value) || 0;
        const w = Math.round((v / max) * 100);
        return `<div class="pm-bar">
          <span>${escapeHtml(item.label)} <em>${escapeHtml(String(v))}</em></span>
          <svg viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
            <rect class="pm-bar__track" x="0" y="2" width="100" height="6" rx="2"></rect>
            <rect class="pm-bar__fill" x="0" y="2" width="${w}" height="6" rx="2"></rect>
          </svg>
        </div>`;
      })
      .join('');
    return `<div class="pm-chart">
      <div class="pm-chart__title">${escapeHtml(title)}</div>
      ${rows || '<p class="field-hint">Sin datos</p>'}
    </div>`;
  }

  function renderDashboard() {
    const kpiRow = $('pm-kpi-row');
    const charts = $('pm-charts');
    const ejemplos = $('pm-ejemplos-body');
    const dash = (contexto && contexto.dashboard) || {};
    const list = equipos();
    const cump = cumplimientoStats(list);

    if (kpiRow) {
      const total = dash.total_equipos ?? list.length;
      const prom = dash.promedio_ge;
      kpiRow.innerHTML = `
        <div class="pm-kpi"><span>Equipos</span><strong>${escapeHtml(String(total))}</strong></div>
        <div class="pm-kpi pm-kpi--accent"><span>GE promedio</span><strong>${escapeHtml(
          fmt(prom)
        )}</strong></div>
        <div class="pm-kpi"><span>GE ≥ 19</span><strong>${escapeHtml(
          String(dash.ge_ge_19 ?? 0)
        )}</strong></div>
        <div class="pm-kpi"><span>GE 15–19</span><strong>${escapeHtml(
          String(dash.ge_15_19 ?? 0)
        )}</strong></div>
        <div class="pm-kpi"><span>GE 12–15</span><strong>${escapeHtml(
          String(dash.ge_12_15 ?? 0)
        )}</strong></div>
        <div class="pm-kpi"><span>GE &lt; 12</span><strong>${escapeHtml(
          String(dash.ge_lt_12 ?? 0)
        )}</strong></div>
        <div class="pm-kpi pm-kpi--ok"><span>Cumplimiento aprobado</span><strong>${escapeHtml(
          `${cump.aprobados}/${cump.total || 0} (${cump.pct}%)`
        )}</strong></div>
        <div class="pm-kpi"><span>Con historial</span><strong>${escapeHtml(
          String(dash.ejecucion?.equipos_con_historial ?? 0)
        )}</strong></div>
        <div class="pm-kpi"><span>Correctivos (MC+visitas)</span><strong>${escapeHtml(
          String(dash.ejecucion?.correctivos ?? 0)
        )}</strong></div>
        <div class="pm-kpi"><span>De ellas, visitas</span><strong>${escapeHtml(
          String(dash.ejecucion?.visitas ?? 0)
        )}</strong></div>
      `;
    }

    if (charts) {
      const geItems = [
        { label: 'GE ≥ 19', value: dash.ge_ge_19 || 0, color: '#9F1239' },
        { label: '15 ≤ GE < 19', value: dash.ge_15_19 || 0, color: '#EA580C' },
        { label: '12 ≤ GE < 15', value: dash.ge_12_15 || 0, color: '#CA8A04' },
        { label: 'GE < 12', value: dash.ge_lt_12 || 0, color: '#0F766E' },
      ];
      const freq = dash.frecuencias || {};
      const freqItems = Object.keys(freq).map((k) => ({ label: k, value: freq[k] }));
      const crit = dash.criticidad_por_servicio || [];
      const critItems = crit.map((c) => ({
        label: c.servicio || '—',
        value: c.alta || 0,
      }));
      if (!critItems.length && list.length) {
        critItems.push({
          label: contexto?.servicio?.name_servicio || 'Servicio',
          value: list.filter((e) => Number(e.ge_total) >= 19).length,
        });
      }
      const cumpItems = [
        { label: 'Aprobados', value: cump.aprobados },
        { label: 'Cumplidos (pend. validar)', value: Math.max(0, cump.cumplidos - cump.aprobados) },
        { label: 'Pendientes', value: cump.pendientes },
        { label: 'Rechazados', value: cump.rechazados },
      ];
      const chartsLib = window.AtlasOps?.charts;
      if (chartsLib) {
        charts.innerHTML =
          chartsLib.pair(
            'Equipos por criticidad GE',
            geItems,
            'Frecuencias definitivas',
            freqItems
          ) +
          svgBarChart('Criticidad alta (GE≥19) por servicio', critItems) +
          svgBarChart('Cumplimiento de validaciones', cumpItems);
      } else {
        charts.innerHTML =
          svgBarChart('Equipos por bucket GE', geItems) +
          svgBarChart('Frecuencias definitivas', freqItems) +
          svgBarChart('Criticidad alta (GE≥19) por servicio', critItems) +
          svgBarChart('Cumplimiento de validaciones', cumpItems);
      }
    }

    if (ejemplos) {
      const ex = dash.ejemplos || list.slice(0, 10);
      if (!ex.length) {
        ejemplos.innerHTML = '<tr><td colspan="5">Sin ejemplos.</td></tr>';
      } else {
        ejemplos.innerHTML = ex
          .map(
            (r) => `<tr>
              <td>${escapeHtml(r.equipo || '—')}</td>
              <td>${escapeHtml(r.servicio || r.servicio_nombre || '—')}</td>
              <td>${fmt(r.ge_total, 0)}</td>
              <td>${escapeHtml(r.frecuencia_definitiva || '—')}</td>
              <td>${escapeHtml(r.accion_sugerida || '—')}</td>
            </tr>`
          )
          .join('');
      }
    }
  }

  function renderInforme() {
    const el = $('pm-informe');
    if (!el) return;
    if (!contexto) {
      el.innerHTML = '<p class="field-hint">Cargue un servicio para generar el resumen.</p>';
      return;
    }
    const srv = contexto.servicio || {};
    const dash = contexto.dashboard || {};
    const list = equipos();
    const cump = cumplimientoStats(list);
    el.innerHTML = `
      <div class="dim-informe-card">
        <h3>Informe resumen — Frecuencia PM (GE + fabricante)</h3>
        <p><strong>Empresa:</strong> ${escapeHtml(srv.ID_Empresa || '—')} ·
           <strong>Sede:</strong> ${escapeHtml(srv.name_sede || '—')} ·
           <strong>Servicio:</strong> ${escapeHtml(srv.name_servicio || '—')}</p>
        <p><strong>Año cronograma:</strong> ${escapeHtml(String(contexto.anio || anio))} ·
           <strong>Equipos:</strong> ${escapeHtml(String(list.length))} ·
           <strong>GE promedio:</strong> ${escapeHtml(fmt(dash.promedio_ge))}</p>
        <p><strong>Buckets GE:</strong>
           ≥19: ${escapeHtml(String(dash.ge_ge_19 ?? 0))} ·
           15–19: ${escapeHtml(String(dash.ge_15_19 ?? 0))} ·
           12–15: ${escapeHtml(String(dash.ge_12_15 ?? 0))} ·
           &lt;12: ${escapeHtml(String(dash.ge_lt_12 ?? 0))}</p>
        <p><strong>Validación:</strong> ${escapeHtml(
          `${cump.aprobados} aprobados / ${cump.total} programadas (${cump.pct}%)`
        )}</p>
        <p class="suf-sheet-note">${escapeHtml(
          (catalogos && catalogos.guia_nota) || tipDefaults.guia
        )}</p>
        ${
          window.AtlasOps?.charts
            ? window.AtlasOps.charts.pair(
                'Equipos por criticidad GE',
                [
                  { label: 'GE ≥ 19', value: dash.ge_ge_19 || 0, color: '#9F1239' },
                  { label: '15 ≤ GE < 19', value: dash.ge_15_19 || 0, color: '#EA580C' },
                  { label: '12 ≤ GE < 15', value: dash.ge_12_15 || 0, color: '#CA8A04' },
                  { label: 'GE < 12', value: dash.ge_lt_12 || 0, color: '#0F766E' },
                ],
                'Frecuencias definitivas',
                Object.keys(dash.frecuencias || {}).map((k) => ({
                  label: k,
                  value: dash.frecuencias[k],
                }))
              )
            : ''
        }
        <ul>
          ${list
            .slice(0, 15)
            .map(
              (eq) =>
                `<li><strong>${escapeHtml(eq.equipo || '—')}</strong> —
                  GE ${escapeHtml(fmt(eq.ge_total, 0))} —
                  ${escapeHtml(eq.frecuencia_definitiva || 'sin frecuencia')}</li>`
            )
            .join('')}
        </ul>
        ${
          list.length > 15
            ? `<p class="field-hint">… y ${list.length - 15} equipos más (ver PDF completo).</p>`
            : ''
        }
      </div>
    `;
  }

  function renderValidaciones() {
    const body = $('pm-val-body');
    if (!body) return;
    const list = equipos();
    const flat = [];
    list.forEach((eq) => {
      (eq.validaciones || []).forEach((v) => {
        flat.push({ eq, v, equipo: eq.equipo });
      });
    });
    if (!flat.length) {
      body.innerHTML =
        '<tr><td colspan="9">Sin validaciones programadas para este año.</td></tr>';
      if ($('pm-val-pager')) $('pm-val-pager').hidden = true;
      return;
    }
    const { slice, total } = paginate(
      flat,
      'val',
      'pm-val-search',
      'pm-val-page-size',
      'pm-val-pager',
      'pm-val-page-label'
    );
    if (!total) {
      body.innerHTML = '<tr><td colspan="9">Ningún equipo coincide con la búsqueda.</td></tr>';
      return;
    }
    body.innerHTML = slice
      .map(({ eq, v }) => {
        const mesIdx = Number(v.mes) - 1;
        const mesNombre =
          mesIdx >= 0 && mesIdx < 12 ? MESES_NOMBRE[mesIdx] : `Mes ${v.mes}`;
        const estado = String(v.estado || 'PENDIENTE').toUpperCase();
        const actions = [];
        if (caps.can_execute && (estado === 'PENDIENTE' || estado === 'RECHAZADO')) {
          actions.push(
            `<button type="button" class="btn btn-primary" data-pm-cumplir="${v.id}">Cumplir</button>`
          );
        }
        if (caps.can_validate && (estado === 'CUMPLIDO' || estado === 'RECHAZADO')) {
          actions.push(
            `<button type="button" class="btn btn-ghost" data-pm-validar="${v.id}">Validar</button>`
          );
        }
        return `<tr>
          <td>${escapeHtml(eq.equipo || '—')}${window.AtlasOps.equipoAlertaMarkup(eq)}</td>
          <td>${escapeHtml(mesNombre)}</td>
          <td>${escapeHtml(v.fecha_programada || '—')}</td>
          <td>${escapeHtml(v.fecha_ejecucion || '—')}</td>
          <td><span class="suf-chip">${escapeHtml(estado)}</span></td>
          <td>${escapeHtml(v.ejecutado_por_login || '—')}</td>
          <td>${escapeHtml(v.validado_por_login || '—')}</td>
          <td>${v.calificacion != null ? escapeHtml(String(v.calificacion)) : '—'}</td>
          <td class="suf-acciones">${actions.join(' ') || '—'}</td>
        </tr>`;
      })
      .join('');
  }

  function renderCatalogos() {
    const el = $('pm-catalogos');
    if (!el) return;
    if (!catalogos) {
      el.innerHTML =
        '<p class="field-hint">Catálogos no disponibles para este rol (vista limitada).</p>';
      return;
    }
    const blocks = [
      ['Función', catalogos.funcion],
      ['Aplicación', catalogos.aplicacion],
      ['Requisito de mantenimiento', catalogos.requisito_mantto],
      ['Antecedentes de fallas', catalogos.antecedentes_fallas],
    ];
    const oms = catalogos.oms_reglas || [];

    el.innerHTML = `
      ${blocks
        .map(([title, items]) => {
          const rows = (items || [])
            .map(
              (it) => `<tr>
                <td>${escapeHtml(it.label)}</td>
                <td class="col-calc">${escapeHtml(String(it.puntaje))}</td>
                <td>${escapeHtml(it.descripcion || '')}</td>
                <td>${escapeHtml(it.ejemplo || '')}</td>
              </tr>`
            )
            .join('');
          return `<div class="pm-catalogos__block">
            <h4>${escapeHtml(title)}</h4>
            <div class="suf-scroll">
              <table class="suf-grid">
                <thead><tr><th>Etiqueta</th><th>Puntaje</th><th>Descripción</th><th>Ejemplo</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="4">—</td></tr>'}</tbody>
              </table>
            </div>
          </div>`;
        })
        .join('')}
      <div class="pm-catalogos__block">
        <h4>Bandas TGE</h4>
        <div class="suf-scroll">
          <table class="suf-grid">
            <thead><tr><th>Rango GE</th><th>Intervalo</th><th>Acción</th><th>Interpretación</th></tr></thead>
            <tbody>
              ${
                oms
                  .map(
                    (r) => `<tr>
                      <td>${escapeHtml(r.rango)}</td>
                      <td>${escapeHtml(r.intervalo)}</td>
                      <td>${escapeHtml(r.accion || '')}</td>
                      <td>${escapeHtml(r.interpretacion || '')}</td>
                    </tr>`
                  )
                  .join('') || '<tr><td colspan="4">—</td></tr>'
              }
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  function renderEjecucion() {
    const body = $('pm-ej-body');
    if (!body) return;
    const items = ejState.items || [];
    if (!caps.can_view_full) {
      body.innerHTML = '';
      return;
    }
    if (!items.length) {
      body.innerHTML =
        '<tr><td colspan="8">Sin registros de ejecución para esta empresa. Puede ingresar datos manualmente; el resto de módulos sigue disponible.</td></tr>';
      if ($('pm-ej-pager')) $('pm-ej-pager').hidden = true;
      return;
    }
    body.innerHTML = items
      .map((row) => {
        const sede = [row.name_sede, row.name_servicio].filter(Boolean).join(' · ') || '—';
        return `<tr>
          <td>${escapeHtml((row.fecha_ejecucion || '').toString().slice(0, 10))}</td>
          <td>${escapeHtml(row.tipo_mantenimiento || '—')}</td>
          <td>${escapeHtml(row.codigo_biomedica || '—')}</td>
          <td>${escapeHtml(row.codigo_activo || '—')}</td>
          <td>${escapeHtml(sede)}</td>
          <td>${row.duracion_horas != null ? escapeHtml(String(row.duracion_horas)) : '—'}</td>
          <td>${escapeHtml(row.fuente || '—')}</td>
          <td>${escapeHtml(row.observaciones || '—')}</td>
        </tr>`;
      })
      .join('');
    const pager = $('pm-ej-pager');
    const label = $('pm-ej-page-label');
    const size = Number($('pm-ej-page-size')?.value || ejState.size || 10);
    const pages = Math.max(1, Math.ceil((ejState.total || 0) / size));
    if (pager) pager.hidden = ejState.total <= size;
    if (label) {
      const from = ejState.total ? (ejState.page - 1) * size + 1 : 0;
      const to = Math.min(ejState.page * size, ejState.total);
      label.textContent = ejState.total ? `${from}–${to} de ${ejState.total}` : '';
    }
    if ($('pm-ej-prev')) $('pm-ej-prev').disabled = ejState.page <= 1;
    if ($('pm-ej-next')) $('pm-ej-next').disabled = ejState.page >= pages;
  }

  async function loadEjecucion() {
    const empresaId = contexto?.servicio?.empresa_id;
    const servicioId = $('pm-servicio')?.value;
    if (!empresaId && !servicioId) {
      ejState.items = [];
      ejState.total = 0;
      renderEjecucion();
      return;
    }
    const q = $('pm-ej-search')?.value || '';
    const tipo = $('pm-ej-tipo-filtro')?.value || '';
    const size = Number($('pm-ej-page-size')?.value || 10);
    ejState.size = PAGE_SIZES.includes(size) ? size : 10;
    const params = new URLSearchParams({
      page: String(ejState.page),
      page_size: String(ejState.size),
    });
    if (empresaId) params.set('empresa_id', empresaId);
    else if (servicioId) params.set('servicio_id', servicioId);
    if (q) params.set('q', q);
    if (tipo) params.set('tipo', tipo);
    const { response, data } = await window.AtlasOps.api(
      `/api/frecuencia-pm/ejecucion?${params.toString()}`
    );
    if (!response.ok || !data.ok) {
      ejState.items = [];
      ejState.total = 0;
      renderEjecucion();
      return;
    }
    ejState.items = data.items || [];
    ejState.total = Number(data.total || 0);
    ejState.page = Number(data.page || 1);
    ejState.caps = data.caps || ejState.caps;
    renderEjecucion();
  }

  function setEjMsg(text, isError = false) {
    const el = $('pm-ej-msg');
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = '';
      return;
    }
    el.hidden = false;
    el.textContent = text;
    el.style.color = isError ? '#9b1c1c' : '';
  }

  async function submitEjecucion(event) {
    event.preventDefault();
    if (!caps.can_edit_operational && !caps.can_execute) {
      window.AtlasOps.showToast('Sin permiso para registrar ejecución.', 'error');
      return;
    }
    const servicioId = $('pm-servicio')?.value;
    if (!servicioId) {
      window.AtlasOps.showToast('Selecciona un servicio.', 'error');
      return;
    }
    const payload = {
      servicio_id: Number(servicioId),
      codigo_biomedica: $('pm-ej-bio')?.value || '',
      codigo_activo: $('pm-ej-activo')?.value || '',
      tipo_mantenimiento: $('pm-ej-tipo')?.value || 'preventivo',
      fecha_ejecucion: $('pm-ej-fecha')?.value || '',
      fecha_atencion: $('pm-ej-atencion')?.value || null,
      fecha_cierre: $('pm-ej-cierre')?.value || null,
      duracion_horas: null,
      observaciones: $('pm-ej-obs')?.value || '',
      fuente: 'manual',
    };
    const { response, data } = await window.AtlasOps.api('/api/frecuencia-pm/ejecucion', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      setEjMsg(data.error || 'No se pudo guardar.', true);
      window.AtlasOps.showToast(data.error || 'No se pudo guardar la ejecución.', 'error');
      return;
    }
    setEjMsg('Ejecución guardada. El resto de módulos sigue disponible.', false);
    window.AtlasOps.showToast(data.message || 'Ejecución registrada.', 'success');
    $('pm-ejecucion-form')?.reset();
    ejState.page = 1;
    await loadEjecucion();
    if ($('pm-servicio')?.value) await loadContexto();
  }

  async function buscarCoincidenciasEjecucion() {
    const empresaId = contexto?.servicio?.empresa_id;
    const servicioId = $('pm-servicio')?.value;
    const bio = $('pm-ej-bio')?.value || '';
    const act = $('pm-ej-activo')?.value || '';
    if (!bio && !act) {
      window.AtlasOps.showToast('Indique Código Biomédica o Código de Activo.', 'error');
      return;
    }
    const params = new URLSearchParams({
      codigo_biomedica: bio,
      codigo_activo: act,
      limit: '25',
    });
    if (empresaId) params.set('empresa_id', empresaId);
    else if (servicioId) params.set('servicio_id', servicioId);
    const { response, data } = await window.AtlasOps.api(
      `/api/frecuencia-pm/ejecucion/coincidencias?${params.toString()}`
    );
    const box = $('pm-ej-match');
    if (!box) return;
    if (!response.ok || !data.ok) {
      box.hidden = false;
      box.innerHTML = `<p class="field-hint">${escapeHtml(data.error || 'No se pudo buscar.')}</p>`;
      return;
    }
    const items = data.items || [];
    box.hidden = false;
    if (!items.length) {
      box.innerHTML = '<p class="field-hint">Sin coincidencias en otras sedes o servicios.</p>';
      return;
    }
    box.innerHTML = `
      <p class="suf-sheet-note">${items.length} coincidencia(s) de ${data.total || items.length}.</p>
      <div class="suf-scroll">
        <table class="suf-grid">
          <thead><tr><th>Coincidencia</th><th>Equipo</th><th>Biomédica</th><th>Activo</th><th>Sede</th><th>Servicio</th></tr></thead>
          <tbody>
            ${items
              .map(
                (it) => `<tr>
                  <td>${escapeHtml(it.coincidencia || '—')}</td>
                  <td>${escapeHtml(it.equipo || '—')}</td>
                  <td>${escapeHtml(it.codigo_biomedica || '—')}</td>
                  <td>${escapeHtml(it.codigo_activo || '—')}</td>
                  <td>${escapeHtml(it.name_sede || '—')}</td>
                  <td>${escapeHtml(it.name_servicio || '—')}</td>
                </tr>`
              )
              .join('')}
          </tbody>
        </table>
      </div>`;
  }

  function renderAll() {
    renderInventario();
    renderGe();
    renderOms();
    renderDefinitiva();
    renderCronograma();
    renderDashboard();
    renderInforme();
    renderValidaciones();
    renderCatalogos();
    renderEjecucion();
    applyCapsUi();
  }

  function readRowPayload(tr) {
    const payload = {
      id: Number(tr.dataset.pmRow),
      anio: Number($('pm-anio')?.value || anio),
    };
    tr.querySelectorAll('[data-field]').forEach((input) => {
      const field = input.getAttribute('data-field');
      if (!field) return;
      payload[field] = input.value === '' ? null : input.value;
    });
    return payload;
  }

  async function saveRow(tr) {
    const servicioId = $('pm-servicio')?.value;
    if (!servicioId) {
      window.AtlasOps.showToast('Selecciona un servicio.', 'error');
      return;
    }
    if (!canEditAnything()) {
      window.AtlasOps.showToast('No tienes permiso para editar.', 'error');
      return;
    }
    const payload = readRowPayload(tr);
    const { response, data } = await window.AtlasOps.api(
      `/api/frecuencia-pm/servicios/${servicioId}/equipos`,
      { method: 'POST', body: JSON.stringify(payload) }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo guardar el equipo.', 'error');
      return;
    }
    window.AtlasOps.showToast(data.message || 'Equipo PM guardado.', 'success');
    await loadContexto();
  }

  async function loadContexto() {
    const servicioId = $('pm-servicio')?.value;
    const req = ++contextoReq;
    if (!servicioId) {
      setMsg('Selecciona empresa, sede y servicio.', true);
      contexto = null;
      if (req === contextoReq) renderAll();
      return;
    }
    const year = Number($('pm-anio')?.value || anio);
    anio = year;
    setMsg('Cargando contexto PM…');
    const { response, data } = await window.AtlasOps.api(
      `/api/frecuencia-pm/servicios/${servicioId}/contexto?anio=${encodeURIComponent(year)}`
    );
    if (req !== contextoReq) return;
    if (!response.ok || !data.ok) {
      setMsg(data.error || 'No se pudo cargar el contexto PM.', true);
      window.AtlasOps.showToast(data.error || 'Error al cargar Frecuencia PM.', 'error');
      return;
    }
    contexto = data;
    caps = data.caps || caps;
    if (data.catalogos) catalogos = data.catalogos;
    anio = data.anio || year;
    if ($('pm-anio')) $('pm-anio').value = String(anio);
    setMsg(
      `Servicio «${data.servicio?.name_servicio || servicioId}» · ${
        data.total_equipos ?? data.equipos?.length ?? 0
      } equipos · año ${anio}.`
    );
    renderAll();
    await loadEjecucion();
  }

  async function syncInventario() {
    const servicioId = $('pm-servicio')?.value;
    if (!servicioId) {
      window.AtlasOps.showToast('Selecciona un servicio.', 'error');
      return;
    }
    if (!caps.can_edit_operational) {
      window.AtlasOps.showToast('Sin permiso para sincronizar.', 'error');
      return;
    }
    const year = Number($('pm-anio')?.value || anio);
    const { response, data } = await window.AtlasOps.api(
      `/api/frecuencia-pm/servicios/${servicioId}/sync-inventario`,
      { method: 'POST', body: JSON.stringify({ anio: year }) }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo sincronizar.', 'error');
      return;
    }
    window.AtlasOps.showToast(data.message || 'Inventario sincronizado.', 'success');
    contexto = data;
    caps = data.caps || caps;
    if (data.catalogos) catalogos = data.catalogos;
    renderAll();
    await loadEjecucion();
    setMsg(data.message || 'Inventario sincronizado.');
  }

  async function recalcular() {
    const servicioId = $('pm-servicio')?.value;
    if (!servicioId) {
      window.AtlasOps.showToast('Selecciona un servicio.', 'error');
      return;
    }
    if (!caps.can_edit_operational) {
      window.AtlasOps.showToast('Sin permiso para recalcular.', 'error');
      return;
    }
    const year = Number($('pm-anio')?.value || anio);
    const { response, data } = await window.AtlasOps.api(
      `/api/frecuencia-pm/servicios/${servicioId}/recalcular`,
      { method: 'POST', body: JSON.stringify({ anio: year }) }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo recalcular.', 'error');
      return;
    }
    window.AtlasOps.showToast(data.message || 'GE / cronograma recalculados.', 'success');
    await loadContexto();
  }

  function evidenciaOptions(eq) {
    const opts = [];
    const estado = eq?.estado || 'Operativo';
    const fecha = (eq?.fecha_ultimo_pm || '').toString().slice(0, 10);
    const fab = eq?.pm_fabricante_meses;
    const freq = eq?.frecuencia_definitiva;
    opts.push(`PM ejecutado conforme a cronograma · ${eq?.equipo || 'equipo'} · estado ${estado}`);
    opts.push(`PM ejecutado con atraso · ${eq?.equipo || 'equipo'}${fecha ? ` · último PM ${fecha}` : ''}`);
    opts.push(`No ejecutado: equipo no disponible (${estado})`);
    if (fab) opts.push(`PM según fabricante cada ${fab} meses · ${eq?.equipo || 'equipo'}`);
    if (freq) opts.push(`Aplica frecuencia definitiva: ${freq}`);
    if (eq?.funcion) opts.push(`Inventario · función ${eq.funcion}`);
    if (eq?.aplicacion) opts.push(`Inventario · aplicación ${eq.aplicacion}`);
    opts.push('PM ejecutado por tercero (comodato/leasing)');
    opts.push('Checklist de inventario coincidente con el equipo');
    return [...new Set(opts.filter(Boolean))];
  }

  function findValidacion(validacionId) {
    const id = Number(validacionId);
    for (const eq of equipos()) {
      const v = (eq.validaciones || []).find((item) => Number(item.id) === id);
      if (v) return { eq, v };
    }
    return null;
  }

  function openCumplirModal(validacionId) {
    const found = findValidacion(validacionId);
    if (!found) {
      window.AtlasOps.showToast('Validación no encontrada.', 'error');
      return;
    }
    pendingCumplirId = validacionId;
    const label = $('pm-cumplir-equipo');
    if (label) {
      label.textContent = `${found.eq.equipo || 'Equipo'} · estado ${found.eq.estado || '—'} · último PM ${(found.eq.fecha_ultimo_pm || '—').toString().slice(0, 10)}`;
    }
    const sel = $('pm-cumplir-evidencia');
    if (sel) {
      sel.innerHTML = '<option value="">Seleccione la evidencia</option>';
      evidenciaOptions(found.eq).forEach((text) => {
        const opt = document.createElement('option');
        opt.value = text;
        opt.textContent = text;
        sel.appendChild(opt);
      });
    }
    const modal = $('pm-cumplir-modal');
    if (modal) modal.hidden = false;
  }

  function closeCumplirModal() {
    const modal = $('pm-cumplir-modal');
    if (modal) modal.hidden = true;
    pendingCumplirId = null;
  }

  async function cumplirValidacion(validacionId) {
    openCumplirModal(validacionId);
  }

  async function submitCumplir() {
    const evidencia = String($('pm-cumplir-evidencia')?.value || '').trim();
    if (!evidencia) {
      window.AtlasOps.showToast('Seleccione una evidencia de la lista.', 'error');
      return;
    }
    const validacionId = pendingCumplirId;
    if (!validacionId) return;
    const { response, data } = await window.AtlasOps.api(
      `/api/frecuencia-pm/validaciones/${validacionId}/cumplir`,
      {
        method: 'POST',
        body: JSON.stringify({ evidencia }),
      }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo registrar el cumplimiento.', 'error');
      return;
    }
    closeCumplirModal();
    window.AtlasOps.showToast(data.message || 'Cumplimiento registrado.', 'success');
    await loadContexto();
  }

  async function validarValidacion(validacionId) {
    const decisionRaw = window.prompt('Decisión: APROBADO o RECHAZADO', 'APROBADO');
    if (decisionRaw == null) return;
    const decision = String(decisionRaw).trim().toUpperCase();
    if (decision !== 'APROBADO' && decision !== 'RECHAZADO') {
      window.AtlasOps.showToast('La decisión debe ser APROBADO o RECHAZADO.', 'error');
      return;
    }
    const calRaw = window.prompt('Calificación (0–5, opcional):', '');
    if (calRaw == null) return;
    let calificacion = null;
    if (String(calRaw).trim() !== '') {
      calificacion = Number(calRaw);
      if (Number.isNaN(calificacion) || calificacion < 0 || calificacion > 5) {
        window.AtlasOps.showToast('Calificación inválida (0–5).', 'error');
        return;
      }
    }
    const comentario = window.prompt('Comentario de validación (opcional):', '');
    if (comentario == null) return;

    const { response, data } = await window.AtlasOps.api(
      `/api/frecuencia-pm/validaciones/${validacionId}/validar`,
      {
        method: 'POST',
        body: JSON.stringify({
          estado: decision,
          decision,
          calificacion,
          comentario: comentario.trim() || null,
        }),
      }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo validar.', 'error');
      return;
    }
    window.AtlasOps.showToast(data.message || 'Validación registrada.', 'success');
    await loadContexto();
  }

  async function downloadPdf(kind) {
    const servicioId = $('pm-servicio')?.value || contexto?.servicio?.id;
    if (!servicioId) {
      window.AtlasOps.showToast('Selecciona un servicio.', 'error');
      return;
    }
    const year = Number($('pm-anio')?.value || anio);
    try {
      if (kind === 'informe') {
        await window.AtlasOps.downloadFile(
          `/api/frecuencia-pm/servicios/${servicioId}/informe.pdf?anio=${encodeURIComponent(year)}`,
          `informe_frecuencia_pm_${servicioId}.pdf`
        );
        window.AtlasOps.showToast('PDF informe descargado.', 'success');
      } else {
        await window.AtlasOps.downloadFile(
          `/api/frecuencia-pm/servicios/${servicioId}/cronograma.pdf?anio=${encodeURIComponent(
            year
          )}`,
          `cronograma_pm_${servicioId}_${year}.pdf`
        );
        window.AtlasOps.showToast('PDF cronograma descargado.', 'success');
      }
    } catch (err) {
      window.AtlasOps.showToast(err.message || 'Error al descargar PDF.', 'error');
    }
  }

  function setupTooltips() {
    window.AtlasOps?.bindTips?.({
      panelId: 'panel-frecuencia-pm',
      bubbleId: 'pm-tip-bubble',
      selector: '.tip[data-pm-tip]',
      getContent: (btn) => tipText(btn.dataset.pmTip),
    });
  }

  function openCatalogosModal() {
    renderCatalogos();
    const modal = $('pm-catalogos-modal');
    if (!modal) return;
    modal.hidden = false;
    $('pm-catalogos-dialog')?.focus();
  }

  function closeCatalogosModal() {
    const modal = $('pm-catalogos-modal');
    if (modal) modal.hidden = true;
  }

  async function loadMeta() {
    const { response, data } = await window.AtlasOps.api('/api/frecuencia-pm/meta');
    if (!response.ok || !data.ok) return;
    caps = data.caps || caps;
    catalogos = data.catalogos || catalogos;
    if (data.anio_default && $('pm-anio') && !$('pm-anio').value) {
      anio = data.anio_default;
      $('pm-anio').value = String(anio);
    }
  }

  function bindEvents() {
    if (bound) return;
    bound = true;
    const panel = $('panel-frecuencia-pm');
    if (!panel) return;

    panel.addEventListener('click', (event) => {
      if (event.target.closest('[data-pm-tip]')) return;

      const accToggle = event.target.closest('.dim-acc__toggle');
      if (accToggle && panel.contains(accToggle)) {
        window.AtlasOps?.exclusiveAccordion?.(panel, accToggle);
        return;
      }

      const saveBtn = event.target.closest('[data-pm-save]');
      if (saveBtn) {
        const tr = saveBtn.closest('tr[data-pm-row]');
        if (tr) saveRow(tr);
        return;
      }

      const cumplirBtn = event.target.closest('[data-pm-cumplir]');
      if (cumplirBtn) {
        cumplirValidacion(Number(cumplirBtn.getAttribute('data-pm-cumplir')));
        return;
      }

      const validarBtn = event.target.closest('[data-pm-validar]');
      if (validarBtn) {
        validarValidacion(Number(validarBtn.getAttribute('data-pm-validar')));
      }
    });

    $('pm-empresa')?.addEventListener('change', () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      fillSedeSelectLocal($('pm-empresa').value);
      fillServicioFromSede();
    });

    $('pm-sede')?.addEventListener('change', () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      fillServicioFromSede();
    });

    $('pm-servicio')?.addEventListener('change', () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      loadContexto();
    });
    document.addEventListener('orgscope:applied', (ev) => {
      if (ev.detail?.key !== 'frecuencia-pm') return;
      loadContexto();
    });

    $('pm-anio')?.addEventListener('change', () => {
      if ($('pm-servicio')?.value) loadContexto();
    });

    $('pm-btn-refresh')?.addEventListener('click', () => loadContexto());
    $('pm-btn-sync')?.addEventListener('click', () => syncInventario());
    $('pm-btn-recalc')?.addEventListener('click', () => recalcular());
    $('pm-btn-pdf-informe')?.addEventListener('click', () => downloadPdf('informe'));
    $('pm-btn-pdf-crono')?.addEventListener('click', () => downloadPdf('crono'));
    $('btn-pm-catalogos')?.addEventListener('click', openCatalogosModal);
    document.querySelectorAll('[data-close-pm-catalogos]').forEach((el) => {
      el.addEventListener('click', closeCatalogosModal);
    });
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape' && !$('pm-catalogos-modal')?.hidden) closeCatalogosModal();
    });
    bindPager('inv', 'pm-inv-search', 'pm-inv-page-size', 'pm-inv-prev', 'pm-inv-next', renderInventario);
    bindPager('crono', 'pm-crono-search', 'pm-crono-page-size', 'pm-crono-prev', 'pm-crono-next', renderCronograma);
    bindPager('val', 'pm-val-search', 'pm-val-page-size', 'pm-val-prev', 'pm-val-next', renderValidaciones);
    $('pm-ejecucion-form')?.addEventListener('submit', submitEjecucion);
    window.AtlasOps?.bindDuracionDesdeFechas?.('pm-ej-atencion', 'pm-ej-cierre', 'pm-ej-duracion');
    $('pm-ej-coincidencias')?.addEventListener('click', buscarCoincidenciasEjecucion);
    $('pm-ej-search')?.addEventListener('input', () => {
      ejState.page = 1;
      loadEjecucion();
    });
    $('pm-ej-page-size')?.addEventListener('change', () => {
      ejState.page = 1;
      loadEjecucion();
    });
    $('pm-ej-tipo-filtro')?.addEventListener('change', () => {
      ejState.page = 1;
      loadEjecucion();
    });
    $('pm-ej-prev')?.addEventListener('click', () => {
      if (ejState.page > 1) {
        ejState.page -= 1;
        loadEjecucion();
      }
    });
    $('pm-ej-next')?.addEventListener('click', () => {
      ejState.page += 1;
      loadEjecucion();
    });
    $('pm-cumplir-ok')?.addEventListener('click', submitCumplir);
    document.querySelectorAll('[data-close-pm-cumplir]').forEach((el) => {
      el.addEventListener('click', closeCumplirModal);
    });
  }

  async function initFrecuenciaPmPanel() {
    bindEvents();
    setupTooltips();
    await loadMeta();
    await setupScopeSelectors();
    applyCapsUi();
    setMsg('');
    if ($('pm-servicio')?.value) {
      await loadContexto();
    } else {
      renderAll();
    }
    window.AtlasOps?.refreshOrgScopeSummaries?.();
  }

  window.AtlasOps = window.AtlasOps || {};
  window.AtlasOps.loadFrecuenciaPmPanel = initFrecuenciaPmPanel;
})();
