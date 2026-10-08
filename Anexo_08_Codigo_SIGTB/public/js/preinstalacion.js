(() => {
  /* Cliente de preinstalación SITIO: exigencias, decisión e informe. */

  const $ = (id) => document.getElementById(id);

  const CAT_ICON = {
    'Área física e ingreso': '▣',
    Eléctrico: '⚡',
    'Gases medicinales/fluidos': '◎',
    'Condiciones ambientales': '🌡',
    'Redes y conectividad': '⌬',
    'Seguridad física': '⛨',
    'Accesorios requeridos': '⧉',
    Documentación: '▤',
  };

  let catalogos = null;
  let caps = {};
  let contexto = null;
  let evaluacion = null;
  let presets = [];
  let bound = false;
  let saveTimer = null;
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

  function setMsg(text, isError = false) {
    const el = $('pre-msg');
    if (!el) return;
    el.hidden = !text;
    el.textContent = text || '';
    el.classList.toggle('error', isError);
  }

  function setBanner(text, isError = false) {
    const el = $('pre-banner');
    if (!el) return;
    el.hidden = !text;
    el.textContent = text || '';
    el.classList.toggle('error', isError);
  }

  function pctLabel(v) {
    if (v === null || v === undefined || v === '') return '—';
    const n = Number(v);
    if (!Number.isFinite(n)) return '—';
    return `${(n * 100).toFixed(1)} %`;
  }

  function estadoClass(estado) {
    const map = {
      Cumple: 'pre-st--ok',
      'No cumple': 'pre-st--bad',
      Pendiente: 'pre-st--warn',
      'No aplica': 'pre-st--na',
    };
    return map[estado] || 'pre-st--warn';
  }

  function critClass(c) {
    if (c === 'Crítico') return 'pre-crit--alta';
    if (c === 'Mayor') return 'pre-crit--media';
    return 'pre-crit--baja';
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
    const sel = $('pre-empresa');
    if (!sel) return;
    sel.innerHTML = '<option value="">Selecciona empresa</option>';
    (empresas || []).forEach((e) => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = e.ID_NIT ? `${e.ID_Empresa} · ${e.ID_NIT}` : e.ID_Empresa || `Empresa ${e.id}`;
      sel.appendChild(opt);
    });
    if (selectedId) sel.value = String(selectedId);
  }

  function fillSedeSelectLocal(empresaId) {
    const sel = $('pre-sede');
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
    const sedeId = $('pre-sede')?.value || '';
    const srvSel = $('pre-servicio');
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
      const empSel = $('pre-empresa');
      if (empSel) empSel.disabled = false;
    }
    fillServicioFromSede();
    window.AtlasOps?.refreshOrgScopeSummaries?.();
  }

  function applyCapsUi() {
    document.querySelectorAll('[data-pre-edit]').forEach((el) => {
      el.hidden = !caps.can_edit;
    });
    const root = $('pre-root');
    if (root) root.classList.toggle('is-readonly', !caps.can_edit);
  }

  function fillPresets() {
    const sel = $('pre-preset');
    if (!sel) return;
    sel.innerHTML = '<option value="">Selecciona un preset</option>';
    const nuevo = document.createElement('option');
    nuevo.value = '__new__';
    nuevo.textContent = 'Nuevo preset';
    sel.appendChild(nuevo);
    presets.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.nombre;
      sel.appendChild(opt);
    });
    if (evaluacion?.preset_id) sel.value = String(evaluacion.preset_id);
  }

  function fillEquipos() {
    const sel = $('pre-equipo');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">Equipo (inventario)</option>';
    const na = document.createElement('option');
    na.value = '__na__';
    na.textContent = 'No aplica (equipo nuevo / no está en inventario)';
    sel.appendChild(na);
    (contexto?.equipos || []).forEach((eq) => {
      const opt = document.createElement('option');
      opt.value = eq.id;
      const code = eq.num_biomedica || eq.serie || eq.id;
      opt.textContent = `${eq.alerta_sin_datos_anio ? '(!) ' : ''}${eq.equipo} · ${eq.marca || '—'} ${eq.modelo || ''} (${code})`.trim();
      if (eq.alerta_sin_datos_anio) {
        opt.dataset.eqAlerta = '1';
      }
      sel.appendChild(opt);
    });
    if (evaluacion?.inventario_equipo_id) sel.value = String(evaluacion.inventario_equipo_id);
    else if (evaluacion) sel.value = '__na__';
    else if (current) sel.value = current;
    updatePreEquipoAlerta();
  }

  function updatePreEquipoAlerta() {
    const hint = $('pre-equipo-alerta');
    const sel = $('pre-equipo');
    if (!hint || !sel) return;
    const eq = (contexto?.equipos || []).find((e) => String(e.id) === String(sel.value));
    if (eq?.alerta_sin_datos_anio) {
      hint.hidden = false;
      hint.innerHTML = `${window.AtlasOps.equipoAlertaMarkup(eq)} ${escapeHtml(
        eq.alerta_mensaje || window.AtlasOps.EQ_ALERTA_MSG
      )}`;
    } else {
      hint.hidden = true;
      hint.textContent = '';
    }
  }

  function renderGuia() {
    const ol = $('pre-guia');
    if (ol) {
      ol.innerHTML = (catalogos?.guia_uso || []).map((t) => `<li>${escapeHtml(t)}</li>`).join('');
    }
    const alc = $('pre-alcance');
    if (alc) alc.textContent = catalogos?.alcance || '';
  }

  function field(id, label, value, tip, type = 'text') {
    const v = value == null ? '' : String(value).slice(0, 10) === '20' && type === 'date' ? String(value).slice(0, 10) : value;
    return `<label>
      <span class="field-with-tip">${escapeHtml(label)}
        <button type="button" class="tip" data-pre-tip="${tip}" aria-label="Ayuda">?</button>
      </span>
      <input id="${id}" type="${type}" value="${escapeHtml(v || '')}" ${caps.can_edit ? '' : 'disabled'} />
    </label>`;
  }

  function renderDatos() {
    const box = $('pre-form-datos');
    if (!box) return;
    if (!evaluacion) {
      box.innerHTML = '<p class="field-hint">Selecciona servicio y pulsa «Nueva visita», o abre una evaluación existente.</p>';
      return;
    }
    const e = evaluacion;
    box.innerHTML = `
      <div class="pre-form-grid">
        ${field('pre-f-institucion', 'Institución', e.institucion, 'institucion')}
        ${field('pre-f-servicio', 'Servicio / Área', e.servicio_area, 'servicio')}
        ${field('pre-f-tecnologia', 'Tecnología biomédica', e.tecnologia, 'tecnologia')}
        ${field('pre-f-marca', 'Marca / Modelo', e.marca_modelo, 'marca_modelo')}
        ${field('pre-f-proveedor', 'Proveedor', e.proveedor, 'proveedor')}
        ${field('pre-f-serial', 'Serial / Código interno', e.serial_codigo, 'serial')}
        ${field('pre-f-ubicacion', 'Ubicación propuesta', e.ubicacion_propuesta, 'ubicacion')}
        ${field('pre-f-fecha', 'Fecha de visita', e.fecha_visita, 'fecha_visita', 'date')}
        ${field('pre-f-responsable', 'Responsable de verificación', e.responsable_verificacion, 'responsable')}
        ${field('pre-f-acompanante', 'Acompañante del servicio', e.acompanante_servicio, 'acompanante')}
        ${field('pre-f-fuente', 'Fuente de requisitos', e.fuente_requisitos, 'fuente')}
      </div>
      <label class="pre-full">Objetivo
        <textarea id="pre-f-objetivo" rows="2" ${caps.can_edit ? '' : 'disabled'}>${escapeHtml(e.objetivo || '')}</textarea>
      </label>`;
    box.querySelectorAll('input, textarea').forEach((el) => {
      el.addEventListener('change', () => saveDatos());
    });
  }

  function renderInteg() {
    const box = $('pre-integ');
    if (!box) return;
    const i = evaluacion?.integracion;
    if (!i || (!i.inventario && !i.suficiencia && !i.dimensionamiento && !i.frecuencia_pm)) {
      box.hidden = true;
      box.innerHTML = '';
      return;
    }
    box.hidden = false;
    const chips = [];
    if (i.inventario) {
      chips.push(`<span class="pre-chip">Inventario: ${escapeHtml(i.inventario.estado || '—')} · INVIMA ${escapeHtml(i.inventario.registro_invima || '—')}</span>`);
    }
    if (i.suficiencia) {
      chips.push(`<span class="pre-chip">Suficiencia: ${escapeHtml(i.suficiencia.resultado || '—')} (${pctLabel((i.suficiencia.suficiencia_pct || 0) / 100)})</span>`);
    }
    if (i.dimensionamiento) {
      chips.push(`<span class="pre-chip">Dimensionamiento: criticidad ${escapeHtml(i.dimensionamiento.criticidad || '—')}</span>`);
    }
    if (i.frecuencia_pm) {
      chips.push(`<span class="pre-chip">PM: GE ${escapeHtml(i.frecuencia_pm.ge_total ?? '—')} · ${escapeHtml(i.frecuencia_pm.frecuencia_definitiva || '—')}</span>`);
    }
    box.innerHTML = `<p class="pre-integ__title">Integración con módulos</p><div class="pre-chips">${chips.join('')}</div>`;
  }

  function renderEvalsList() {
    const box = $('pre-evals');
    if (!box) return;
    const list = contexto?.evaluaciones || [];
    if (!list.length) {
      box.innerHTML = '';
      return;
    }
    box.innerHTML = `<p class="pre-integ__title">Visitas de este servicio</p>
      <div class="pre-eval-list">${list
        .map(
          (ev) => `<button type="button" class="pre-eval-item ${evaluacion && Number(evaluacion.id) === Number(ev.id) ? 'is-active' : ''}" data-pre-open="${ev.id}">
            <strong>${escapeHtml(ev.tecnologia || 'Sin tecnología')}</strong>
            <span>${escapeHtml(String(ev.fecha_visita || '').slice(0, 10))} · ${escapeHtml(ev.decision || ev.estado_eval || '')}</span>
          </button>`
        )
        .join('')}</div>`;
  }

  function itemCard(it) {
    const estados = (catalogos?.estados || ['Cumple', 'No cumple', 'Pendiente', 'No aplica'])
      .map((s) => `<button type="button" class="pre-st ${estadoClass(s)} ${it.estado === s ? 'is-on' : ''}" data-pre-estado="${it.id}" data-val="${s}">${s}</button>`)
      .join('');
    const crits = (catalogos?.criticidades || ['Crítico', 'Mayor', 'Menor'])
      .map((c) => `<option value="${c}" ${it.criticidad === c ? 'selected' : ''}>${c}</option>`)
      .join('');
    return `<article class="pre-card ${critClass(it.criticidad)}" data-item="${it.id}">
      <header>
        <span class="pre-card__id">#${it.item_id}</span>
        <h4>${escapeHtml(it.requisito)}</h4>
        <span class="pre-badge ${critClass(it.criticidad)}">${escapeHtml(it.criticidad)}</span>
      </header>
      <p class="pre-card__exig"><strong>Exigencia:</strong> ${escapeHtml(it.exigencia || '—')}</p>
      <label>Evidencia observada en sitio
        <textarea data-f="evidencia" rows="2" ${caps.can_edit ? '' : 'disabled'}>${escapeHtml(it.evidencia || '')}</textarea>
      </label>
      <div class="pre-st-row">${estados}</div>
      <div class="pre-card__meta">
        <label>Criticidad <select data-f="criticidad" ${caps.can_edit ? '' : 'disabled'}>${crits}</select></label>
        <label>Responsable de cierre <input data-f="responsable_cierre" value="${escapeHtml(it.responsable_cierre || '')}" ${caps.can_edit ? '' : 'disabled'} /></label>
        <label>Fecha compromiso <input data-f="fecha_compromiso" type="date" value="${escapeHtml(String(it.fecha_compromiso || '').slice(0, 10))}" ${caps.can_edit ? '' : 'disabled'} /></label>
      </div>
      <label>Observaciones / acción correctiva
        <textarea data-f="observaciones" rows="2" ${caps.can_edit ? '' : 'disabled'}>${escapeHtml(it.observaciones || '')}</textarea>
      </label>
    </article>`;
  }

  function renderChecklist(targetId, seccion) {
    const box = $(targetId);
    if (!box) return;
    const items = (evaluacion?.items || []).filter((i) => i.seccion === seccion);
    if (!items.length) {
      box.innerHTML = '<p class="field-hint">Crea o abre una visita para ver el checklist.</p>';
      return;
    }
    const cats = [];
    items.forEach((it) => {
      if (!cats.includes(it.categoria)) cats.push(it.categoria);
    });
    box.innerHTML = cats
      .map((cat) => {
        const group = items.filter((i) => i.categoria === cat);
        const icon = CAT_ICON[cat] || '•';
        return `<section class="pre-cat is-open">
          <button type="button" class="pre-cat__toggle">${icon} ${escapeHtml(cat)} <em>${group.length}</em></button>
          <div class="pre-cat__body">${group.map(itemCard).join('')}</div>
        </section>`;
      })
      .join('');
  }

  function renderResultado() {
    const box = $('pre-resultado');
    if (!box) return;
    if (!evaluacion) {
      box.innerHTML = '<p class="field-hint">Sin evaluación cargada.</p>';
      return;
    }
    const e = evaluacion;
    const sem = e.semaforo || 'amarillo';
    box.innerHTML = `
      <div class="pre-kpis">
        <div class="pm-kpi"><span>Evaluables fabricante</span><strong>${e.evaluables_fab ?? 0}</strong></div>
        <div class="pm-kpi"><span>Evaluables documentación</span><strong>${e.evaluables_doc ?? 0}</strong></div>
        <div class="pm-kpi"><span>Total evaluables</span><strong>${e.total_evaluables ?? 0}</strong></div>
        <div class="pm-kpi pm-kpi--ok"><span>Cumplidos</span><strong>${e.cumplidos ?? 0}</strong></div>
        <div class="pm-kpi"><span>No cumplidos</span><strong>${e.no_cumplidos ?? 0}</strong></div>
        <div class="pm-kpi"><span>Pendientes</span><strong>${e.pendientes ?? 0}</strong></div>
        <div class="pm-kpi"><span>No aplica</span><strong>${e.no_aplica ?? 0}</strong></div>
        <div class="pm-kpi ${e.criticos_abiertos ? 'pre-kpi-bad' : 'pm-kpi--ok'}"><span>Críticos abiertos</span><strong>${e.criticos_abiertos ?? 0}</strong></div>
        <div class="pm-kpi pm-kpi--accent"><span>% cumplimiento</span><strong>${pctLabel(e.pct_cumplimiento)}</strong></div>
      </div>
      <div class="pre-decision pre-decision--${sem}">
        <span>Decisión automática</span>
        <strong>${escapeHtml(e.decision || '—')}</strong>
        <p>Regla Excel: críticos abiertos bloquean. Si % ≥ 90 y no hay pendientes → Aprobado; si % ≥ 90 con pendientes → Aprobado con condiciones.</p>
      </div>
      <h4>Resultado por bloque</h4>
      ${
        window.AtlasOps?.charts
          ? window.AtlasOps.charts.pair(
              'Estado de requisitos',
              [
                { label: 'Cumple', value: e.cumplidos ?? 0 },
                { label: 'No cumple', value: e.no_cumplidos ?? 0 },
                { label: 'Pendiente', value: e.pendientes ?? 0 },
                { label: 'No aplica', value: e.no_aplica ?? 0 },
              ],
              '% cumplimiento por bloque',
              (e.por_bloque || []).map((b) => ({
                label: b.categoria,
                value: Math.round((b.pct || 0) * 100),
                display: `${Math.round((b.pct || 0) * 100)}%`,
              }))
            )
          : ''
      }
      <div class="pm-charts">${(e.por_bloque || [])
        .map((b) => {
          const w = Math.round((b.pct || 0) * 100);
          return `<div class="pm-bar"><span>${escapeHtml(b.categoria)} <em>${w}%</em></span>
            <div class="pm-bar__track"><div class="pm-bar__fill" style="width:${w}%"></div></div>
            <small>C ${b.cumple} · NC ${b.no_cumple} · P ${b.pendiente} · NA ${b.no_aplica}</small></div>`;
        })
        .join('')}</div>
      <div class="pre-validar" ${caps.can_validate ? '' : 'hidden'}>
        <label>Comentario asistencial
          <textarea id="pre-comentario-as" rows="2">${escapeHtml(e.comentario_asistencial || '')}</textarea>
        </label>
        <button type="button" class="btn btn-primary" id="pre-btn-aprobar">Aprobar preinstalación</button>
        <button type="button" class="btn btn-ghost" id="pre-btn-rechazar">Rechazar</button>
      </div>`;
  }

  function renderInforme() {
    const box = $('pre-informe');
    if (!box) return;
    if (!evaluacion) {
      box.innerHTML = '<p class="field-hint">Sin evaluación cargada.</p>';
      return;
    }
    const e = evaluacion;
    const abiertos = e.abiertos || [];
    box.innerHTML = `
      <article class="pre-report">
        <h3>Informe de verificación de preinstalación</h3>
        <p><strong>${escapeHtml(e.tecnologia || '—')}</strong> · ${escapeHtml(e.marca_modelo || '—')} · ${escapeHtml(e.servicio_area || '—')}</p>
        <p>Decisión: <strong>${escapeHtml(e.decision || '—')}</strong> · ${pctLabel(e.pct_cumplimiento)} · críticos abiertos: ${e.criticos_abiertos ?? 0}</p>
        ${
          window.AtlasOps?.charts
            ? window.AtlasOps.charts.pair(
                'Estado de requisitos',
                [
                  { label: 'Cumple', value: e.cumplidos ?? 0 },
                  { label: 'No cumple', value: e.no_cumplidos ?? 0 },
                  { label: 'Pendiente', value: e.pendientes ?? 0 },
                ],
                '% por bloque',
                (e.por_bloque || []).map((b) => ({
                  label: b.categoria,
                  value: Math.round((b.pct || 0) * 100),
                  display: `${Math.round((b.pct || 0) * 100)}%`,
                }))
              )
            : ''
        }
        <h4>Requisitos abiertos</h4>
        ${
          abiertos.length
            ? `<ul>${abiertos.map((a) => `<li><strong>${escapeHtml(a.criticidad)}</strong> · ${escapeHtml(a.requisito)} (${escapeHtml(a.estado)})</li>`).join('')}</ul>`
            : '<p>No hay requisitos abiertos.</p>'
        }
        <label>Concepto técnico de ingeniería clínica
          <textarea id="pre-concepto" rows="4" ${caps.can_edit ? '' : 'disabled'}>${escapeHtml(e.concepto_tecnico || '')}</textarea>
        </label>
        <div class="pre-firmas">
          <fieldset><legend>Firma Ingeniería Clínica</legend>
            <input id="pre-ic-nombre" placeholder="Nombre" value="${escapeHtml(e.firma_ic_nombre || '')}" ${caps.can_edit ? '' : 'disabled'} />
            <input id="pre-ic-cargo" placeholder="Cargo" value="${escapeHtml(e.firma_ic_cargo || '')}" ${caps.can_edit ? '' : 'disabled'} />
            <input id="pre-ic-fecha" type="date" value="${escapeHtml(String(e.firma_ic_fecha || '').slice(0, 10))}" ${caps.can_edit ? '' : 'disabled'} />
          </fieldset>
          <fieldset><legend>Firma Servicio Usuario</legend>
            <input id="pre-sv-nombre" placeholder="Nombre" value="${escapeHtml(e.firma_servicio_nombre || '')}" ${caps.can_edit ? '' : 'disabled'} />
            <input id="pre-sv-cargo" placeholder="Cargo" value="${escapeHtml(e.firma_servicio_cargo || '')}" ${caps.can_edit ? '' : 'disabled'} />
            <input id="pre-sv-fecha" type="date" value="${escapeHtml(String(e.firma_servicio_fecha || '').slice(0, 10))}" ${caps.can_edit ? '' : 'disabled'} />
          </fieldset>
        </div>
        <div class="pre-report__actions">
          <button type="button" class="btn btn-ghost" id="pre-btn-save-informe" data-pre-edit>Guardar concepto y firmas</button>
          <button type="button" class="btn btn-primary" id="pre-btn-cierre" data-pre-edit>Solicitar cierre de requisitos</button>
        </div>
      </article>`;
  }

  function renderAll() {
    fillEquipos();
    fillPresets();
    renderDatos();
    renderInteg();
    renderEvalsList();
    renderChecklist('pre-exigencias', 'fabricante');
    renderChecklist('pre-docs', 'documentacion');
    renderResultado();
    renderInforme();
    applyCapsUi();
    if (evaluacion?.decision) {
      setBanner(`${evaluacion.decision} · ${pctLabel(evaluacion.pct_cumplimiento)} · críticos abiertos: ${evaluacion.criticos_abiertos || 0}`);
    }
  }

  async function loadContexto() {
    const servicioId = $('pre-servicio')?.value;
    const req = ++contextoReq;
    if (!servicioId) {
      contexto = null;
      return;
    }
    const { response, data } = await window.AtlasOps.api(
      `/api/preinstalacion/servicios/${servicioId}/contexto`
    );
    if (req !== contextoReq) return;
    if (!response.ok || !data.ok) {
      setMsg(data.error || 'No se pudo cargar el contexto.', true);
      return;
    }
    contexto = data;
    caps = data.caps || caps;
    fillEquipos();
    renderEvalsList();
  }

  async function loadEvaluacion(id) {
    const { response, data } = await window.AtlasOps.api(`/api/preinstalacion/evaluaciones/${id}`);
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo abrir la evaluación.', 'error');
      return;
    }
    evaluacion = data.evaluacion;
    caps = data.evaluacion.caps || caps;
    renderAll();
  }

  async function crearVisita() {
    const servicioId = $('pre-servicio')?.value;
    if (!servicioId) {
      window.AtlasOps.showToast('Selecciona un servicio.', 'error');
      return;
    }
    if (!caps.can_edit) {
      window.AtlasOps.showToast('Sin permiso para diligenciar.', 'error');
      return;
    }
    const payload = { servicio_id: Number(servicioId) };
    const eq = $('pre-equipo')?.value;
    if (eq && eq !== '__na__') payload.inventario_equipo_id = Number(eq);
    if (eq === '__na__') {
      const tec = ($('pre-f-tecnologia')?.value || '').trim();
      payload.tecnologia = tec || 'Equipo nuevo (no aplica inventario)';
    }
    const { response, data } = await window.AtlasOps.api('/api/preinstalacion/evaluaciones', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo crear la visita.', 'error');
      return;
    }
    evaluacion = data.evaluacion;
    window.AtlasOps.showToast(data.message, 'success');
    await loadContexto();
    renderAll();
  }

  function collectDatos() {
    return {
      institucion: $('pre-f-institucion')?.value,
      servicio_area: $('pre-f-servicio')?.value,
      tecnologia: $('pre-f-tecnologia')?.value,
      marca_modelo: $('pre-f-marca')?.value,
      proveedor: $('pre-f-proveedor')?.value,
      serial_codigo: $('pre-f-serial')?.value,
      ubicacion_propuesta: $('pre-f-ubicacion')?.value,
      fecha_visita: $('pre-f-fecha')?.value,
      responsable_verificacion: $('pre-f-responsable')?.value,
      acompanante_servicio: $('pre-f-acompanante')?.value,
      fuente_requisitos: $('pre-f-fuente')?.value,
      objetivo: $('pre-f-objetivo')?.value,
    };
  }

  async function saveDatos() {
    if (!evaluacion || !caps.can_edit) return;
    const { response, data } = await window.AtlasOps.api(
      `/api/preinstalacion/evaluaciones/${evaluacion.id}`,
      { method: 'PUT', body: JSON.stringify(collectDatos()) }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se guardaron los datos.', 'error');
      return;
    }
    evaluacion = { ...evaluacion, ...data.evaluacion, integracion: evaluacion.integracion };
  }

  function collectItemsFromDom() {
    const items = [];
    document.querySelectorAll('.pre-card[data-item]').forEach((card) => {
      const id = Number(card.getAttribute('data-item'));
      const estadoBtn = card.querySelector('.pre-st.is-on');
      items.push({
        id,
        estado: estadoBtn?.getAttribute('data-val') || 'Pendiente',
        criticidad: card.querySelector('[data-f="criticidad"]')?.value,
        evidencia: card.querySelector('[data-f="evidencia"]')?.value,
        responsable_cierre: card.querySelector('[data-f="responsable_cierre"]')?.value,
        fecha_compromiso: card.querySelector('[data-f="fecha_compromiso"]')?.value,
        observaciones: card.querySelector('[data-f="observaciones"]')?.value,
      });
    });
    return items;
  }

  async function saveItems(silent = false) {
    if (!evaluacion || !caps.can_edit) return;
    const { response, data } = await window.AtlasOps.api(
      `/api/preinstalacion/evaluaciones/${evaluacion.id}/items`,
      { method: 'PUT', body: JSON.stringify({ items: collectItemsFromDom() }) }
    );
    if (!response.ok || !data.ok) {
      if (!silent) window.AtlasOps.showToast(data.error || 'No se guardó el checklist.', 'error');
      return;
    }
    const integ = evaluacion.integracion;
    evaluacion = data.evaluacion;
    evaluacion.integracion = integ;
    renderChecklist('pre-exigencias', 'fabricante');
    renderChecklist('pre-docs', 'documentacion');
    renderResultado();
    renderInforme();
    applyCapsUi();
    setBanner(`${evaluacion.decision} · ${pctLabel(evaluacion.pct_cumplimiento)} · críticos abiertos: ${evaluacion.criticos_abiertos || 0}`);
    if (!silent) window.AtlasOps.showToast(data.message, 'success');
  }

  function scheduleSaveItems() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveItems(true), 600);
  }

  async function aplicarPreset() {
    const pid = $('pre-preset')?.value;
    if (!evaluacion || !pid || pid === '__new__') {
      window.AtlasOps.showToast('Selecciona un preset existente y una visita.', 'error');
      return;
    }
    const { response, data } = await window.AtlasOps.api(
      `/api/preinstalacion/evaluaciones/${evaluacion.id}/aplicar-preset`,
      { method: 'POST', body: JSON.stringify({ preset_id: Number(pid) }) }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se aplicó el preset.', 'error');
      return;
    }
    evaluacion = { ...data.evaluacion, integracion: evaluacion.integracion };
    window.AtlasOps.showToast(data.message, 'success');
    renderAll();
  }

  async function guardarPreset() {
    if (!evaluacion) return;
    const selected = $('pre-preset')?.value;
    let nombre = '';
    if (selected === '__new__') {
      nombre = ($('pre-f-tecnologia')?.value || '').trim();
      if (!nombre) {
        window.AtlasOps.showToast('Indica la tecnología biomédica para nombrar el nuevo preset.', 'error');
        return;
      }
    } else {
      nombre = window.prompt('Nombre del preset a guardar:', evaluacion.tecnologia || 'Preset de sitio');
      if (!nombre) return;
    }
    const limit = window.SIGTB_LIMITS?.label || 255;
    nombre = String(nombre).slice(0, limit);
    const { response, data } = await window.AtlasOps.api('/api/preinstalacion/presets', {
      method: 'POST',
      body: JSON.stringify({ nombre, evaluacion_id: evaluacion.id, es_global: currentUser().ROLL === 'ADMIN' }),
    });
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se guardó el preset.', 'error');
      return;
    }
    window.AtlasOps.showToast(data.message, 'success');
    await loadMeta();
    fillPresets();
    if (data.preset?.id) $('pre-preset').value = String(data.preset.id);
  }

  async function saveInforme() {
    if (!evaluacion || !caps.can_edit) return;
    const payload = {
      ...collectDatos(),
      concepto_tecnico: $('pre-concepto')?.value,
      firma_ic_nombre: $('pre-ic-nombre')?.value,
      firma_ic_cargo: $('pre-ic-cargo')?.value,
      firma_ic_fecha: $('pre-ic-fecha')?.value,
      firma_servicio_nombre: $('pre-sv-nombre')?.value,
      firma_servicio_cargo: $('pre-sv-cargo')?.value,
      firma_servicio_fecha: $('pre-sv-fecha')?.value,
    };
    const { response, data } = await window.AtlasOps.api(
      `/api/preinstalacion/evaluaciones/${evaluacion.id}`,
      { method: 'PUT', body: JSON.stringify(payload) }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se guardó el informe.', 'error');
      return;
    }
    evaluacion = { ...evaluacion, ...data.evaluacion };
    window.AtlasOps.showToast(data.message, 'success');
  }

  async function solicitarCierre() {
    if (!evaluacion) return;
    const { response, data } = await window.AtlasOps.api(
      `/api/preinstalacion/evaluaciones/${evaluacion.id}/solicitar-cierre`,
      { method: 'POST', body: '{}' }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se envió la solicitud.', 'error');
      return;
    }
    window.AtlasOps.showToast(data.message, 'success');
  }

  async function validar(decision) {
    if (!evaluacion) return;
    const { response, data } = await window.AtlasOps.api(
      `/api/preinstalacion/evaluaciones/${evaluacion.id}/validar`,
      {
        method: 'POST',
        body: JSON.stringify({ decision, comentario: $('pre-comentario-as')?.value || '' }),
      }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo validar.', 'error');
      return;
    }
    evaluacion = { ...data.evaluacion, integracion: evaluacion.integracion };
    window.AtlasOps.showToast(data.message, 'success');
    renderAll();
  }

  async function downloadPdf() {
    if (!evaluacion) {
      window.AtlasOps.showToast('Abre una visita primero.', 'error');
      return;
    }
    try {
      await window.AtlasOps.downloadFile(
        `/api/preinstalacion/evaluaciones/${evaluacion.id}/pdf`,
        `preinstalacion_${evaluacion.id}.pdf`
      );
      window.AtlasOps.showToast('PDF generado.', 'success');
    } catch (err) {
      window.AtlasOps.showToast(err.message || 'Error al generar PDF.', 'error');
    }
  }

  function gotoStep(step) {
    document.querySelectorAll('.pre-step').forEach((b) => {
      b.classList.toggle('is-active', b.dataset.preStep === step);
    });
    const map = { datos: 'datos', exigencias: 'exigencias', docs: 'docs', resultado: 'resultado', informe: 'informe' };
    const section = document.querySelector(`[data-pre-section="${map[step]}"]`);
    document.querySelectorAll('#pre-root .dim-acc').forEach((acc) => {
      const open = acc === section;
      acc.classList.toggle('is-open', open);
      const body = acc.querySelector('.dim-acc__body');
      const btn = acc.querySelector('.dim-acc__toggle');
      if (body) body.hidden = !open;
      if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    section?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function setupTooltips() {
    window.AtlasOps?.bindTips?.({
      panelId: 'panel-preinstalacion',
      bubbleId: 'pre-tip-bubble',
      selector: '.tip[data-pre-tip]',
      getContent: (btn) => (catalogos?.tooltips || {})[btn.getAttribute('data-pre-tip')] || '',
    });
  }

  function bindEvents() {
    if (bound) return;
    bound = true;
    $('pre-empresa')?.addEventListener('change', () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      fillSedeSelectLocal($('pre-empresa').value);
      fillServicioFromSede();
    });
    $('pre-sede')?.addEventListener('change', () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      fillServicioFromSede();
    });
    $('pre-servicio')?.addEventListener('change', () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      evaluacion = null;
      loadContexto().then(renderAll);
    });
    $('pre-equipo')?.addEventListener('change', updatePreEquipoAlerta);
    document.addEventListener('orgscope:applied', (ev) => {
      if (ev.detail?.key !== 'preinstalacion') return;
      evaluacion = null;
      loadContexto().then(renderAll);
    });
    $('pre-btn-refresh')?.addEventListener('click', () => loadContexto().then(renderAll));
    $('pre-btn-nueva')?.addEventListener('click', crearVisita);
    $('pre-btn-pdf')?.addEventListener('click', downloadPdf);
    $('pre-btn-preset')?.addEventListener('click', aplicarPreset);
    $('pre-btn-save-preset')?.addEventListener('click', guardarPreset);

    document.getElementById('pre-steps')?.addEventListener('click', (ev) => {
      const btn = ev.target.closest('[data-pre-step]');
      if (btn) gotoStep(btn.dataset.preStep);
    });

    $('pre-root')?.addEventListener('click', (ev) => {
      const accBtn = ev.target.closest('.dim-acc__toggle');
      if (accBtn) {
        window.AtlasOps?.exclusiveAccordion?.($('pre-root'), accBtn);
        return;
      }
      const catBtn = ev.target.closest('.pre-cat__toggle');
      if (catBtn) {
        catBtn.parentElement.classList.toggle('is-open');
        return;
      }
      const openEv = ev.target.closest('[data-pre-open]');
      if (openEv) {
        loadEvaluacion(Number(openEv.getAttribute('data-pre-open')));
        return;
      }
      const st = ev.target.closest('[data-pre-estado]');
      if (st && caps.can_edit) {
        const card = st.closest('.pre-card');
        card.querySelectorAll('.pre-st').forEach((b) => b.classList.remove('is-on'));
        st.classList.add('is-on');
        scheduleSaveItems();
        return;
      }
      if (ev.target.id === 'pre-btn-aprobar') validar('APROBADA');
      if (ev.target.id === 'pre-btn-rechazar') validar('RECHAZADA');
      if (ev.target.id === 'pre-btn-save-informe') saveInforme();
      if (ev.target.id === 'pre-btn-cierre') solicitarCierre();
    });

    $('pre-root')?.addEventListener('change', (ev) => {
      if (ev.target.closest('.pre-card')) scheduleSaveItems();
    });
  }

  async function loadMeta() {
    const { response, data } = await window.AtlasOps.api('/api/preinstalacion/meta');
    if (!response.ok || !data.ok) {
      setMsg(data.error || 'No se pudo cargar el módulo.', true);
      return;
    }
    catalogos = data.catalogos;
    caps = data.caps || {};
    presets = data.presets || [];
  }

  async function initPreinstalacionPanel() {
    bindEvents();
    setupTooltips();
    await loadMeta();
    await setupScopeSelectors();
    applyCapsUi();
    fillPresets();
    if ($('pre-servicio')?.value) await loadContexto();
    renderAll();
  }

  window.AtlasOps = window.AtlasOps || {};
  window.AtlasOps.loadPreinstalacionPanel = initPreinstalacionPanel;
})();
