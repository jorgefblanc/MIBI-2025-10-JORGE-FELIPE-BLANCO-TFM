(() => {
  /* Cliente de suficiencia: contexto, autosave y presentación de resultados del servidor. */

  const tipDefaults = {
    tipo_calculo:
      'Tipos de cálculo de suficiencia: por capacidad, por demanda, mínimo técnico, por sala/equipo principal, esterilización/rotación y mixto.',
    ocupacion: 'Porcentaje de uso = Promedio ocupado / Capacidad instalada.',
    capacidad_instalada: 'Capacidad instalada del servicio (camas, camillas, quirófanos, etc.).',
    promedio_ocupado: 'Promedio de puestos/pacientes ocupados de forma simultánea.',
    disponible: 'Disponible real según estado operativo del equipo.',
    simultaneos:
      'Pacientes/puestos que requieren el equipo al mismo tiempo. Ej.: si 5 pacientes pueden requerir monitor, indique 5.',
    minimo_tecnico: 'Cantidad mínima exigida por normativa o estándar institucional.',
    concurrencia:
      '% concurrencia = pacientes/puestos simultáneos ÷ capacidad base (inventario del equipo).',
    utilizacion_segura: 'Tope de utilización segura institucional (p. ej. 75%).',
    respaldo_pct: 'Porcentaje institucional de respaldo sobre el requerido base.',
    umbral_alerta: 'Umbral de suficiencia para marcar Alerta (p. ej. 80%).',
    req_capacidad: 'Necesidad estimada a partir de capacidad, ocupación y concurrencia.',
    req_demanda: 'Necesidad estimada a partir de demanda diaria, tiempo de uso y horas de servicio.',
    requerido_final:
      'Rfinal = ⌈Rb·(1+b)⌉ + Re. S = D / Rfinal. Denominador 0 o dato faltante → Revisar.',
    brecha: 'Brecha = Inventario disponible − Requerido final. Negativo = déficit.',
    suficiencia:
      'Suficiencia = Inventario disponible ÷ Requerido final (≥1 Suficiente; 0.80–0.99 Alerta; <0.80 Insuficiente).',
    acciones: 'Recomendaciones automáticas según el resultado.',
  };

  const richTips = {
    tipo_calculo: {
      title: 'Tipos de cálculo',
      items: [
        {
          label: 'Por capacidad',
          text:
            'Evalúa si el equipo puede procesar suficiente volumen de pacientes, muestras o procedimientos según su capacidad técnica nominal.',
        },
        {
          label: 'Por demanda',
          text:
            'Evalúa si el equipo cubre la cantidad real de uso que se presenta en la institución: número de pacientes, procedimientos, estudios, etc.',
        },
        {
          label: 'Mínimo técnico',
          text:
            'Define el mínimo indispensable de equipos para que un servicio pueda operar según normativa, protocolos o estándares técnicos.',
        },
        {
          label: 'Por sala/equipo principal',
          text:
            'Evalúa la suficiencia según la cantidad de salas, consultorios o áreas que requieren un equipo principal para funcionar.',
        },
        {
          label: 'Esterilización/Rotación',
          text:
            'Evalúa si la cantidad de equipos permite mantener rotación adecuada considerando tiempos de esterilización, reprocesamiento o descanso operativo.',
        },
        {
          label: 'Mixto',
          text:
            'Combina dos o más criterios anteriores cuando ninguno por sí solo representa adecuadamente la realidad del servicio.',
        },
      ],
    },
  };

  let meta = { tooltips: tipDefaults, tipos_calculo: [] };
  let contexto = null;
  let canEditAsist = false;
  let canRequestUpdate = false;
  let paramsOpen = false;
  /** Servicio activo del contexto cargado (para autosave al cambiar de selector). */
  let activeServicioId = null;
  const INV_PAGE_SIZES = [10, 25, 50];
  let invPageSize = 10;
  let invPage = 0;
  let invFilterServicioId = null;
  const matrizDirty = new Set();
  const matrizSaveTimers = new Map();
  const matrizSaveSeq = new Map();
  const MATRIZ_AUTOSAVE_MS = 450;
  let contextoReq = 0;

  const $ = (id) => document.getElementById(id);

  function tipText(key) {
    return (meta.tooltips && meta.tooltips[key]) || tipDefaults[key] || '';
  }

  function escape(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtPct(v) {
    if (v == null || Number.isNaN(Number(v))) return '—';
    return `${(Number(v) * 100).toFixed(1)}%`;
  }

  function fmtNum(v, digits = 2) {
    if (v == null || v === '') return '—';
    const n = Number(v);
    if (Number.isNaN(n)) return '—';
    return Number.isInteger(n) ? String(n) : n.toFixed(digits);
  }

  function toPctInput(frac) {
    if (frac == null || Number.isNaN(Number(frac))) return '';
    return Math.round(Number(frac) * 100);
  }

  function resultadoClass(resultado) {
    if (resultado === 'Suficiente') return 'suf-chip--ok';
    if (resultado === 'Alerta') return 'suf-chip--warn';
    if (resultado === 'Insuficiente') return 'suf-chip--bad';
    if (resultado === 'Revisar') return 'suf-chip--review';
    return '';
  }

  function tipoLabel(id) {
    const found = (meta.tipos_calculo || []).find((t) => t.id === id);
    return found ? found.label : id || '—';
  }

  function tipoOptions(selected) {
    return (meta.tipos_calculo || [])
      .map(
        (t) =>
          `<option value="${escape(t.id)}" ${t.id === selected ? 'selected' : ''}>${escape(
            t.label
          )}</option>`
      )
      .join('');
  }

  function classifyEstado(estado, row) {
    if (row?.en_bodega || row?.es_baja) return 'prestado_nd';
    const raw = String(estado || '')
      .trim()
      .toUpperCase();
    if (!raw || raw === 'OPERATIVO') return 'operativo';
    if (raw.includes('MANTEN') || raw.includes('REPAR')) return 'mantenimiento';
    return 'prestado_nd';
  }

  function alertaEquipoTipo(name, extra) {
    const bucket = contexto?.inventario_por_equipo?.[name];
    const rows = (contexto?.inventario_rows || []).filter(
      (r) => String(r.equipo || '').toLowerCase() === String(name || '').toLowerCase()
    );
    const flag = Boolean(
      extra?.alerta_sin_datos_anio ||
        bucket?.alerta_sin_datos_anio ||
        rows.some((r) => r.alerta_sin_datos_anio)
    );
    return window.AtlasOps?.equipoAlertaMarkup?.({ alerta_sin_datos_anio: flag }) || '';
  }

  function servicioNombre() {
    return contexto?.servicio?.name_servicio || '—';
  }

  function setMsg(text, isError = false) {
    const el = $('suf-msg');
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

  function updateBanner() {
    const banner = $('suf-banner');
    if (!banner) return;
    if (!contexto) {
      banner.hidden = true;
      return;
    }
    banner.hidden = false;
    banner.classList.toggle('suf-banner--warn', !canEditAsist);
    banner.textContent = canEditAsist
      ? 'Modo asistencial: puede editar datos del servicio y la matriz de concurrencia/demanda. Los cálculos se actualizan y guardan solos al ingresar datos.'
      : 'Modo consulta: los datos los captura el rol asistencial. Use «Solicitar actualización» si requieren cambios.';
  }

  function applyRoleLocks() {
    const editable = canEditAsist;
    document.querySelectorAll('#panel-suficiencia [data-suf-edit]').forEach((el) => {
      if (el.tagName === 'BUTTON') {
        el.hidden = !editable;
      } else {
        el.disabled = !editable;
      }
    });
    if ($('suf-btn-recalc')) $('suf-btn-recalc').hidden = !editable;
    if ($('suf-btn-solicitar')) $('suf-btn-solicitar').hidden = !canRequestUpdate;
    if ($('suf-save-params')) {
      const canParams = Boolean(
        window.AtlasOps?.can?.('admin_panel') || window.AtlasOps?.can?.('modify_empresa')
      );
      $('suf-save-params').hidden = !canParams;
      document.querySelectorAll('#suf-form-params input, #suf-form-params select').forEach((el) => {
        el.disabled = !canParams;
      });
    }
    updateBanner();
  }

  function currentUser() {
    return window.AtlasOps?.currentUser || {};
  }

  function isAdminScope() {
    return currentUser().ROLL === 'ADMIN' || Boolean(currentUser().global_scope);
  }

  function isDireccionScope() {
    const job = currentUser().JOB;
    return (
      job === 'Director Operativo' ||
      job === 'Dirección' ||
      (currentUser().ROLL === 'ASISTENCIAL' && job === 'Director')
    );
  }

  function isCoordinacionScope() {
    return currentUser().JOB === 'Coordinador';
  }

  function canPickAnyEmpresa() {
    if (typeof window.AtlasOps?.canPickAnyEmpresa === 'function') {
      return window.AtlasOps.canPickAnyEmpresa();
    }
    return (
      isAdminScope() || Boolean(window.AtlasOps?.can?.('view_all_empresas'))
    );
  }

  function assignedSedeIds() {
    return (currentUser().assigned_sede_ids || []).map(Number);
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

  function fillEmpresaSelect(empresas, { locked = false, selectedId = '' } = {}) {
    const sel = $('suf-empresa');
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
    sel.disabled = Boolean(locked && selectedId);
  }

  function fillSedeSelectForEmpresa(empresaId, { selectedId = '' } = {}) {
    const sel = $('suf-sede');
    if (!sel) return;
    const sedes = (window.AtlasOps?.getSedesCache?.() || []).filter(
      (s) => empresaId && Number(s.empresa_id) === Number(empresaId)
    );
    let allowed = sedes;
    const assigned = assignedSedeIds();
    // Roles no admin/dirección: solo sedes asignadas (si las hay).
    if (!canPickAnyEmpresa() && assigned.length) {
      allowed = sedes.filter((s) => assigned.includes(Number(s.id)));
      if (!allowed.length) allowed = sedes;
    }
    sel.innerHTML = '<option value="">Selecciona sede</option>';
    allowed.forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = `${s.ID_sede} · ${s.name_sede}`;
      sel.appendChild(opt);
    });
    if (selectedId && allowed.some((s) => Number(s.id) === Number(selectedId))) {
      sel.value = String(selectedId);
    }
    sel.disabled = false;
  }

  async function setupScopeSelectors() {
    await window.AtlasOps.ensureSedes({ force: true });
    const sedes = window.AtlasOps.getSedesCache?.() || [];
    let empresas = [];
    if (canPickAnyEmpresa()) {
      const { data } = await window.AtlasOps.api('/api/empresas');
      if (data?.ok) empresas = data.empresas || [];
    }
    if (!empresas.length) empresas = empresasFromSedes(sedes);

    const userEmpresa = currentUser().empresa_id;
    let selectedEmpresa = '';
    let lockEmpresa = false;

    if (!canPickAnyEmpresa()) {
      lockEmpresa = true;
    }

    fillEmpresaSelect(empresas, { locked: lockEmpresa, selectedId: selectedEmpresa });
    fillSedeSelectForEmpresa('');
    window.AtlasOps.fillServicioSelect($('suf-servicio'), '');
    window.AtlasOps?.refreshOrgScopeSummaries?.();
  }

  function renderDatosServicio() {
    const body = $('suf-datos-body');
    if (!body) return;
    if (!contexto) {
      body.innerHTML = '<tr><td colspan="10">Seleccione sede y servicio.</td></tr>';
      return;
    }
    const d = contexto.datos_servicio || {};
    const ocup =
      d.ocupacion_pct != null
        ? fmtPct(d.ocupacion_pct)
        : d.capacidad_instalada && d.promedio_ocupado != null
          ? fmtPct(Number(d.promedio_ocupado) / Number(d.capacidad_instalada))
          : '—';
    const locked = !canEditAsist ? 'disabled' : '';
    body.innerHTML = `<tr>
      <td>${escape(servicioNombre())}</td>
      <td><input data-suf-edit type="number" id="suf-capacidad" min="0" step="any" value="${escape(
        d.capacidad_instalada ?? ''
      )}" ${locked} /></td>
      <td><input data-suf-edit type="text" id="suf-unidad" value="${escape(
        d.unidad_capacidad || ''
      )}" placeholder="camas, camillas…" ${locked} /></td>
      <td><input data-suf-edit type="number" id="suf-promedio" min="0" step="any" value="${escape(
        d.promedio_ocupado ?? ''
      )}" ${locked} /></td>
      <td class="col-calc" id="suf-ocupacion-cell">${ocup}</td>
      <td><input data-suf-edit type="number" id="suf-horas" min="0" max="24" step="any" value="${escape(
        d.horas_servicio_dia ?? ''
      )}" ${locked} /></td>
      <td><input data-suf-edit type="number" id="suf-jornadas" min="0" step="any" value="${escape(
        d.jornadas_dia ?? 1
      )}" ${locked} /></td>
      <td><input data-suf-edit type="text" id="suf-fuente-datos" value="${escape(
        d.fuente_dato || contexto.fuente_default || ''
      )}" ${locked} /></td>
      <td><textarea data-suf-edit id="suf-comentario-datos" ${locked}>${escape(
        d.comentario || ''
      )}</textarea></td>
      <td>
        <button type="button" class="btn btn-primary btn-sm" id="suf-datos-save" data-suf-edit ${
          canEditAsist ? '' : 'hidden'
        }>Guardar</button>
      </td>
    </tr>`;

    $('suf-capacidad')?.addEventListener('input', updateOcupacionLocal);
    $('suf-promedio')?.addEventListener('input', updateOcupacionLocal);
    $('suf-datos-save')?.addEventListener('click', saveDatosServicio);
  }

  function updateOcupacionLocal() {
    const cap = Number($('suf-capacidad')?.value);
    const prom = Number($('suf-promedio')?.value);
    const cell = $('suf-ocupacion-cell');
    if (!cell) return;
    if (cap > 0 && !Number.isNaN(prom)) {
      cell.textContent = fmtPct(prom / cap);
    } else {
      cell.textContent = '—';
    }
  }

  async function saveDatosServicio() {
    const servicioId = $('suf-servicio')?.value;
    if (!servicioId) {
      window.AtlasOps.showToast('Selecciona un servicio.', 'error');
      return;
    }
    await flushDirtyMatriz();
    const payload = {
      capacidad_instalada: $('suf-capacidad').value || null,
      unidad_capacidad: $('suf-unidad').value.trim(),
      promedio_ocupado: $('suf-promedio').value || null,
      horas_servicio_dia: $('suf-horas').value || null,
      jornadas_dia: $('suf-jornadas').value || 1,
      fuente_dato: $('suf-fuente-datos').value.trim(),
      comentario: $('suf-comentario-datos').value.trim(),
    };
    const { response, data } = await window.AtlasOps.api(
      `/api/suficiencia/servicios/${servicioId}/datos`,
      { method: 'PUT', body: JSON.stringify(payload) }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se guardaron los datos.', 'error');
      return;
    }
    window.AtlasOps.showToast(data.message, 'success');
    loadContexto();
  }

  function invSearchHaystack(row) {
    return [
      row.equipo,
      row.marca,
      row.modelo,
      row.serie,
      row.num_biomedica,
    ]
      .map((v) => String(v || '').toLowerCase())
      .join(' ');
  }

  function filteredInventarioRows(rows) {
    const q = String($('suf-inv-search')?.value || '')
      .trim()
      .toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => invSearchHaystack(row).includes(q));
  }

  function readInvPageSize() {
    const n = Number($('suf-inv-page-size')?.value);
    if (INV_PAGE_SIZES.includes(n)) invPageSize = n;
    return invPageSize;
  }

  function renderInventario() {
    const body = $('suf-inv-body');
    const hint = $('suf-inv-hint');
    const pager = $('suf-inv-pager');
    const pageLabel = $('suf-inv-page-label');
    if (!body) return;
    const rows = contexto?.inventario_rows || [];
    const map = contexto?.inventario_por_equipo || {};
    const servicioId = Number(contexto?.servicio?.id || activeServicioId || 0);
    if (invFilterServicioId !== servicioId) {
      invFilterServicioId = servicioId;
      invPage = 0;
      if ($('suf-inv-search')) $('suf-inv-search').value = '';
    }
    const size = readInvPageSize();
    const filtered = filteredInventarioRows(rows);
    const totalAll = rows.length;
    const total = filtered.length;
    const pages = Math.max(1, Math.ceil(total / size) || 1);
    if (invPage > pages - 1) invPage = pages - 1;
    if (invPage < 0) invPage = 0;
    const start = total ? invPage * size : 0;
    const slice = filtered.slice(start, start + size);
    const from = total ? start + 1 : 0;
    const to = start + slice.length;

    if (!totalAll) {
      body.innerHTML = '<tr><td colspan="12">Sin inventario para el servicio.</td></tr>';
      if (hint) hint.textContent = '';
      if (pager) pager.hidden = true;
      return;
    }
    if (!total) {
      body.innerHTML =
        '<tr><td colspan="12">Ningún equipo coincide con la búsqueda.</td></tr>';
    } else {
      const srv = servicioNombre();
      body.innerHTML = slice
        .map((r) => {
          const kind = classifyEstado(r.estado, r);
          const operativa = kind === 'operativo' ? 1 : 0;
          const mant = kind === 'mantenimiento' ? 1 : 0;
          const nd = kind === 'prestado_nd' ? 1 : 0;
          const disp = operativa;
          const marcaModelo = [r.marca, r.modelo].filter(Boolean).join(' / ') || '—';
          const obs =
            kind === 'mantenimiento'
              ? 'En mantenimiento: no cuenta como operativo'
              : kind === 'prestado_nd'
                ? 'Prestado / no disponible'
                : '';
          return `<tr>
          <td>${escape(srv)}</td>
          <td>${escape(r.ubicacion || '—')}</td>
          <td>${escape(r.equipo || '—')}${window.AtlasOps.equipoAlertaMarkup(r)}</td>
          <td>${escape(marcaModelo)}</td>
          <td>${escape(r.serie || r.num_biomedica || '—')}</td>
          <td style="text-align:center">1</td>
          <td style="text-align:center">${operativa}</td>
          <td style="text-align:center">${mant}</td>
          <td style="text-align:center">${nd}</td>
          <td class="col-calc">${disp}</td>
          <td>${escape(r.estado || 'Operativo')}</td>
          <td>${escape(obs)}</td>
        </tr>`;
        })
        .join('');
    }

    if (pager) {
      pager.hidden = total <= size;
      if (pageLabel) {
        pageLabel.textContent = total
          ? `Mostrando ${from}–${to} de ${total}`
          : 'Sin coincidencias';
      }
      const prev = $('suf-inv-prev');
      const next = $('suf-inv-next');
      if (prev) prev.disabled = invPage <= 0;
      if (next) next.disabled = invPage >= pages - 1 || !total;
    }

    if (hint) {
      const resumen = Object.entries(map)
        .map(([eq, s]) => `${eq}: ${s.disponible_real || 0} disp.`)
        .join(' · ');
      const vis =
        totalAll === total
          ? `Visualizando ${slice.length} de ${totalAll} equipos.`
          : `Filtro: ${total} de ${totalAll} equipos. Visualizando ${slice.length}.`;
      hint.textContent = resumen
        ? `${vis} Resumen por tipo (Disponible real usado en evaluación): ${resumen}`
        : vis;
    }
  }

  function matrizRows() {
    const evals = contexto?.evaluaciones || [];
    const byEquipo = new Map(evals.map((e) => [String(e.equipo).toLowerCase(), e]));
    const names = new Set([
      ...(contexto?.equipos || []),
      ...evals.map((e) => e.equipo),
    ]);
    return [...names]
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }))
      .map((name) => {
        const e = byEquipo.get(String(name).toLowerCase()) || {
          equipo: name,
          tipo_calculo: 'mixto',
        };
        return e;
      });
  }

  function localConcurrencia(simult, capacidadBase) {
    const s = Number(simult);
    const c = Number(capacidadBase);
    if (!(c > 0) || Number.isNaN(s)) return '—';
    return fmtPct(s / c);
  }

  function renderMatriz() {
    const body = $('suf-matriz-body');
    if (!body) return;
    const rows = matrizRows();
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="10">Sin equipos en el servicio.</td></tr>';
      return;
    }
    const locked = !canEditAsist ? 'disabled' : '';
    const srv = servicioNombre();
    const inv = contexto?.inventario_por_equipo || {};
    body.innerHTML = rows
      .map((e, idx) => {
        const invRow = inv[e.equipo] || {};
        const capBase = invRow.cantidad_total || e.capacidad_base_auto || 0;
        const conc =
          e.concurrencia_pct != null
            ? fmtPct(e.concurrencia_pct)
            : localConcurrencia(e.pacientes_simultaneos, capBase);
        return `<tr data-matriz-idx="${idx}" data-equipo="${escape(e.equipo)}">
          <td>${escape(srv)}</td>
          <td>${escape(e.equipo)}${alertaEquipoTipo(e.equipo, e)}</td>
              e.tipo_calculo || 'mixto'
            )}</select>
          </td>
          <td><input data-suf-edit data-f="pacientes_simultaneos" type="number" min="0" step="any" value="${escape(
            e.pacientes_simultaneos ?? ''
          )}" ${locked} /></td>
          <td><input data-suf-edit data-f="demanda_diaria" type="number" min="0" step="any" value="${escape(
            e.demanda_diaria ?? ''
          )}" ${locked} /></td>
          <td><input data-suf-edit data-f="tiempo_uso_min" type="number" min="0" step="any" value="${escape(
            e.tiempo_uso_min ?? ''
          )}" ${locked} /></td>
          <td><input data-suf-edit data-f="minimo_tecnico" type="number" min="0" step="any" value="${escape(
            e.minimo_tecnico ?? 0
          )}" ${locked} /></td>
          <td><input data-suf-edit data-f="respaldo_especifico" type="number" min="0" step="any" value="${escape(
            e.respaldo_especifico ?? 0
          )}" ${locked} /></td>
          <td class="col-calc" data-conc-cell>${conc}</td>
          <td class="col-fuente"><input data-suf-edit data-f="fuente_dato" type="text" value="${escape(
            e.fuente_dato || contexto.fuente_default || ''
          )}" ${locked} /></td>
        </tr>`;
      })
      .join('');
  }

  function collectMatrizPayload(tr, equipo) {
    const raw = (f) => tr.querySelector(`[data-f="${f}"]`)?.value;
    const numOrNull = (f) => {
      const v = raw(f);
      if (v === '' || v == null) return null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    };
    const numOrZero = (f) => {
      const n = numOrNull(f);
      return n == null ? 0 : n;
    };
    return {
      equipo,
      tipo_calculo: raw('tipo_calculo') || 'mixto',
      pacientes_simultaneos: numOrNull('pacientes_simultaneos'),
      demanda_diaria: numOrNull('demanda_diaria'),
      tiempo_uso_min: numOrNull('tiempo_uso_min'),
      minimo_tecnico: numOrZero('minimo_tecnico'),
      respaldo_especifico: numOrZero('respaldo_especifico'),
      fuente_dato: (raw('fuente_dato') || '').trim(),
      comentario: '',
    };
  }

  function mergeEvaluacionLocal(ev) {
    if (!contexto || !ev) return;
    const list = Array.isArray(contexto.evaluaciones) ? [...contexto.evaluaciones] : [];
    const key = String(ev.equipo || '').toLowerCase();
    const idx = list.findIndex((e) => String(e.equipo || '').toLowerCase() === key);
    if (idx >= 0) list[idx] = { ...list[idx], ...ev };
    else list.push(ev);
    contexto.evaluaciones = list;
  }

  function updateMatrizConcCell(tr, ev) {
    const cell = tr?.querySelector('[data-conc-cell]');
    if (!cell) return;
    if (ev?.concurrencia_pct != null) {
      cell.textContent = fmtPct(ev.concurrencia_pct);
      return;
    }
    const equipo = tr.dataset.equipo;
    const invRow = (contexto?.inventario_por_equipo || {})[equipo] || {};
    const simult = tr.querySelector('[data-f="pacientes_simultaneos"]')?.value;
    cell.textContent = localConcurrencia(simult, invRow.cantidad_total || 0);
  }

  function scheduleMatrizAutosave(tr) {
    if (!canEditAsist || !tr) return;
    const equipo = tr.dataset.equipo;
    if (!equipo) return;
    matrizDirty.add(equipo);
    updateMatrizConcCell(tr, null);
    const prev = matrizSaveTimers.get(equipo);
    if (prev) clearTimeout(prev);
    matrizSaveTimers.set(
      equipo,
      setTimeout(() => {
        matrizSaveTimers.delete(equipo);
        saveMatrizRow(equipo, tr, { silent: true });
      }, MATRIZ_AUTOSAVE_MS)
    );
  }

  async function flushDirtyMatriz() {
    if (!canEditAsist || !matrizDirty.size) return;
    for (const timer of matrizSaveTimers.values()) clearTimeout(timer);
    matrizSaveTimers.clear();
    const body = $('suf-matriz-body');
    if (!body || !activeServicioId) {
      matrizDirty.clear();
      return;
    }
    const pending = [...matrizDirty];
    await Promise.all(
      pending.map((equipo) => {
        const tr = [...body.querySelectorAll('tr[data-equipo]')].find(
          (row) => row.dataset.equipo === equipo
        );
        if (!tr) {
          matrizDirty.delete(equipo);
          return Promise.resolve();
        }
        return saveMatrizRow(equipo, tr, { silent: true });
      })
    );
  }

  async function saveMatrizRow(equipo, tr, { silent = false } = {}) {
    const servicioId = activeServicioId || $('suf-servicio')?.value;
    if (!servicioId || !tr) return false;
    const seq = (matrizSaveSeq.get(equipo) || 0) + 1;
    matrizSaveSeq.set(equipo, seq);
    const payload = collectMatrizPayload(tr, equipo);
    const { response, data } = await window.AtlasOps.api(
      `/api/suficiencia/servicios/${servicioId}/evaluaciones`,
      { method: 'POST', body: JSON.stringify(payload) }
    );
    if (matrizSaveSeq.get(equipo) !== seq) return false;
    if (!response.ok || !data.ok) {
      if (!silent) {
        window.AtlasOps.showToast(data.error || 'No se pudo calcular.', 'error');
      } else {
        window.AtlasOps.showToast(
          data.error || `No se pudo guardar «${equipo}».`,
          'error'
        );
      }
      return false;
    }
    matrizDirty.delete(equipo);
    mergeEvaluacionLocal(data.evaluacion);
    updateMatrizConcCell(tr, data.evaluacion);
    renderEvaluaciones();
    applyRoleLocks();
    if (!silent) window.AtlasOps.showToast(data.message, 'success');
    return true;
  }

  function renderEvaluaciones() {
    const body = $('suf-eval-body');
    const title = $('suf-eval-title');
    if (title) {
      const name = servicioNombre();
      title.textContent =
        name && name !== '—'
          ? `EVALUACIÓN DE SUFICIENCIA — ${name.toUpperCase()}`
          : 'EVALUACIÓN DE SUFICIENCIA';
    }
    if (!body) return;
    const rows = contexto?.evaluaciones || [];
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="25">Sin evaluaciones todavía. Complete la matriz; el cálculo se guarda automáticamente.</td></tr>';
      const chartsEmpty = $('suf-eval-charts');
      if (chartsEmpty) chartsEmpty.innerHTML = '';
      return;
    }
    const charts = window.AtlasOps?.charts;
    const host = $('suf-eval-charts');
    if (host && charts) {
      const byRes = {};
      rows.forEach((e) => {
        const k = e.resultado || 'Sin clasificar';
        byRes[k] = (byRes[k] || 0) + 1;
      });
      const pieItems = Object.entries(byRes).map(([label, value]) => ({ label, value }));
      const barItems = rows.slice(0, 12).map((e) => ({
        label: e.equipo,
        value: (Number(e.suficiencia_pct) || 0) * 100,
        display: fmtPct(e.suficiencia_pct),
      }));
      host.innerHTML = charts.pair('Resultado de suficiencia', pieItems, '% suficiencia por equipo', barItems);
    }
    const params = contexto?.parametros || {};
    body.innerHTML = rows
      .map((e) => {
        const chip = `<span class="suf-chip ${resultadoClass(e.resultado)}">${escape(
          e.resultado || '—'
        )}</span>`;
        const brechaNeg = Number(e.brecha) < 0 ? 'is-neg' : '';
        return `<tr>
          <td>${escape(e.equipo)}${alertaEquipoTipo(e.equipo, e)}</td>
          <td>${escape(tipoLabel(e.tipo_calculo))}</td>
          <td>${fmtNum(e.capacidad_base_auto, 0)}</td>
          <td>${fmtPct(e.ocupacion_pct)}</td>
          <td>${fmtNum(e.puestos_ocupados_auto, 0)}</td>
          <td>${fmtNum(e.pacientes_simultaneos, 0)}</td>
          <td>${fmtPct(e.concurrencia_pct)}</td>
          <td>${fmtNum(e.demanda_diaria, 0)}</td>
          <td>${fmtNum(e.tiempo_uso_min, 0)}</td>
          <td>${fmtNum(e.horas_servicio_dia, 0)}</td>
          <td>${fmtPct(e.utilizacion_segura ?? params.utilizacion_segura)}</td>
          <td>${fmtNum(e.minimo_tecnico, 0)}</td>
          <td>${fmtPct(e.respaldo_pct ?? params.respaldo_general)}</td>
          <td>${fmtNum(e.req_capacidad, 0)}</td>
          <td>${fmtNum(e.req_demanda, 0)}</td>
          <td>${fmtNum(e.requerido_base, 0)}</td>
          <td>${fmtNum(e.respaldo_unidades, 0)}</td>
          <td>${fmtNum(e.requerido_final, 0)}</td>
          <td class="col-calc">${fmtNum(e.disponible_real ?? e.inventario_disponible, 0)}</td>
          <td class="col-brecha ${brechaNeg}">${fmtNum(e.brecha, 0)}</td>
          <td>${fmtPct(e.suficiencia_pct)}</td>
          <td>${chip}</td>
          <td class="suf-acciones">${escape(e.acciones_sugeridas || '—')}</td>
          <td class="col-fuente">${escape(e.fuente_dato || e.comentario || '—')}</td>
          <td>
            <button type="button" class="btn btn-ghost btn-sm" data-suf-del="${e.id}" data-suf-edit ${
              canEditAsist ? '' : 'hidden'
            }>Eliminar</button>
          </td>
        </tr>`;
      })
      .join('');
  }

  function renderAll() {
    renderDatosServicio();
    renderInventario();
    renderMatriz();
    renderEvaluaciones();
    applyRoleLocks();
  }

  async function loadMeta() {
    const { data } = await window.AtlasOps.api('/api/suficiencia/meta');
    if (data.ok) {
      meta = data;
      meta.tooltips = { ...tipDefaults, ...(data.tooltips || {}) };
    }
  }

  async function loadParamsIntoForm() {
    const { data } = await window.AtlasOps.api('/api/suficiencia/parametros');
    if (!data.ok) return;
    const p = data.parametros || {};
    if ($('suf-utilizacion')) $('suf-utilizacion').value = toPctInput(p.utilizacion_segura ?? 0.75);
    if ($('suf-respaldo')) $('suf-respaldo').value = toPctInput(p.respaldo_general ?? 0.2);
    if ($('suf-umbral')) $('suf-umbral').value = toPctInput(p.umbral_alerta ?? 0.8);
    if ($('suf-redondeo')) $('suf-redondeo').value = p.redondeo || 'CEIL';
  }

  async function loadContexto() {
    const servicioId = $('suf-servicio')?.value;
    const req = ++contextoReq;
    if (!servicioId) {
      contexto = null;
      activeServicioId = null;
      matrizDirty.clear();
      for (const timer of matrizSaveTimers.values()) clearTimeout(timer);
      matrizSaveTimers.clear();
      if (req === contextoReq) renderAll();
      return;
    }
    const { response, data } = await window.AtlasOps.api(
      `/api/suficiencia/servicios/${servicioId}/contexto`
    );
    if (req !== contextoReq) return;
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo cargar el contexto.', 'error');
      return;
    }
    contexto = data;
    activeServicioId = Number(servicioId);
    matrizDirty.clear();
    for (const timer of matrizSaveTimers.values()) clearTimeout(timer);
    matrizSaveTimers.clear();
    canEditAsist = Boolean(data.can_edit_asistencial);
    canRequestUpdate = Boolean(data.can_request_update);
    renderAll();
  }

  async function initSuficienciaPanel() {
    canEditAsist = Boolean(window.AtlasOps?.can?.('edit_suficiencia_asistencial'));
    canRequestUpdate = Boolean(window.AtlasOps?.can?.('request_suficiencia_update'));
    await loadMeta();
    await loadParamsIntoForm();
    await setupScopeSelectors();
    if ($('suf-sheet-params')) $('suf-sheet-params').hidden = !paramsOpen;
    applyRoleLocks();
    setMsg('');
    if ($('suf-servicio')?.value) loadContexto();
  }

  function setupTooltips() {
    window.AtlasOps?.bindTips?.({
      panelId: 'panel-suficiencia',
      bubbleId: 'suf-tip-bubble',
      selector: '.tip[data-tip]',
      maxWidth: 420,
      getContent: (btn) => {
        const key = btn.dataset.tip;
        const rich = richTips[key];
        if (rich) {
          const items = rich.items
            .map(
              (item) => `<div class="tip-bubble__item">
            <strong>${escape(item.label)}</strong>
            <p>${escape(item.text)}</p>
          </div>`
            )
            .join('');
          return { html: `<div class="tip-bubble__head">${escape(rich.title)}</div>${items}` };
        }
        return tipText(key);
      },
    });
  }

  function bindEvents() {
    $('suf-empresa')?.addEventListener('change', async () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      await flushDirtyMatriz();
      fillSedeSelectForEmpresa($('suf-empresa').value);
      window.AtlasOps.fillServicioSelect($('suf-servicio'), $('suf-sede')?.value || '');
      loadContexto();
    });
    $('suf-sede')?.addEventListener('change', async () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      await flushDirtyMatriz();
      window.AtlasOps.fillServicioSelect($('suf-servicio'), $('suf-sede').value);
      loadContexto();
    });
    $('suf-servicio')?.addEventListener('change', async () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      await flushDirtyMatriz();
      loadContexto();
    });
    document.addEventListener('orgscope:applied', (ev) => {
      if (ev.detail?.key !== 'suficiencia') return;
      flushDirtyMatriz().then(() => loadContexto());
    });
    $('suf-btn-refresh')?.addEventListener('click', async () => {
      await flushDirtyMatriz();
      await setupScopeSelectors();
      loadParamsIntoForm();
      loadContexto();
    });
    $('suf-btn-params')?.addEventListener('click', () => {
      paramsOpen = !paramsOpen;
      if ($('suf-sheet-params')) $('suf-sheet-params').hidden = !paramsOpen;
    });

    $('suf-form-params')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const payload = {
        utilizacion_segura: Number($('suf-utilizacion').value),
        respaldo_general: Number($('suf-respaldo').value),
        umbral_alerta: Number($('suf-umbral').value),
        redondeo: $('suf-redondeo').value,
      };
      const { response, data } = await window.AtlasOps.api('/api/suficiencia/parametros', {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      if (!response.ok || !data.ok) {
        window.AtlasOps.showToast(data.error || 'No se guardaron parámetros.', 'error');
        return;
      }
      window.AtlasOps.showToast(data.message, 'success');
      if ($('suf-servicio')?.value) {
        await flushDirtyMatriz();
        loadContexto();
      }
    });

    $('suf-btn-solicitar')?.addEventListener('click', async () => {
      const sedeId = $('suf-sede')?.value;
      const servicioId = $('suf-servicio')?.value;
      if (!sedeId) {
        window.AtlasOps.showToast('Selecciona una sede.', 'error');
        return;
      }
      if (!servicioId) {
        window.AtlasOps.showToast('Selecciona el servicio.', 'error');
        return;
      }
      const mensaje =
        window.prompt(
          'Describe qué datos asistenciales deben actualizarse (capacidad, horas, demanda, etc.):',
          'Solicito actualización de datos de suficiencia para el servicio seleccionado.'
        ) || '';
      if (!mensaje.trim()) return;
      const { response, data } = await window.AtlasOps.api('/api/solicitudes-permiso', {
        method: 'POST',
        body: JSON.stringify({
          sede_id: Number(sedeId),
          servicio_id: Number(servicioId),
          tipo: 'actualizar_datos_suficiencia',
          destinatario_rol: 'asistencial',
          prioridad: 'MODERADA',
          mensaje: mensaje.trim(),
        }),
      });
      if (!response.ok || !data.ok) {
        window.AtlasOps.showToast(data.error || 'No se pudo enviar la solicitud.', 'error');
        return;
      }
      window.AtlasOps.showToast(data.message, 'success');
    });

    $('suf-btn-recalc')?.addEventListener('click', async () => {
      const servicioId = $('suf-servicio')?.value;
      if (!servicioId) return;
      await flushDirtyMatriz();
      const { response, data } = await window.AtlasOps.api(
        `/api/suficiencia/servicios/${servicioId}/recalcular`,
        { method: 'POST', body: '{}' }
      );
      if (!response.ok || !data.ok) {
        window.AtlasOps.showToast(data.error || 'No se pudo recalcular.', 'error');
        return;
      }
      window.AtlasOps.showToast(data.message, 'success');
      loadContexto();
    });

    $('suf-btn-print')?.addEventListener('click', printInformeSuficiencia);

    $('suf-inv-search')?.addEventListener('input', () => {
      invPage = 0;
      renderInventario();
    });
    $('suf-inv-page-size')?.addEventListener('change', () => {
      invPage = 0;
      renderInventario();
    });
    $('suf-inv-prev')?.addEventListener('click', () => {
      invPage -= 1;
      renderInventario();
    });
    $('suf-inv-next')?.addEventListener('click', () => {
      invPage += 1;
      renderInventario();
    });

    const panel = document.getElementById('panel-suficiencia');
    panel?.addEventListener('input', (event) => {
      const field = event.target.closest('#suf-matriz-body [data-f]');
      if (!field) return;
      scheduleMatrizAutosave(field.closest('tr'));
    });
    panel?.addEventListener('change', (event) => {
      const field = event.target.closest('#suf-matriz-body [data-f]');
      if (!field) return;
      scheduleMatrizAutosave(field.closest('tr'));
    });

    panel?.addEventListener('click', async (event) => {
      const del = event.target.closest('[data-suf-del]');
      if (del) {
        const id = Number(del.dataset.sufDel);
        if (!window.confirm('¿Eliminar esta evaluación?')) return;
        await flushDirtyMatriz();
        const { response, data } = await window.AtlasOps.api(`/api/suficiencia/evaluaciones/${id}`, {
          method: 'DELETE',
        });
        if (!response.ok || !data.ok) {
          window.AtlasOps.showToast(data.error || 'No se pudo eliminar.', 'error');
          return;
        }
        window.AtlasOps.showToast(data.message, 'success');
        loadContexto();
      }
    });
  }

  function formatFechaInforme(date = new Date()) {
    try {
      return date.toLocaleString('es-CO', {
        year: 'numeric',
        month: 'long',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return date.toISOString();
    }
  }

  function resumenResultados(rows) {
    const counts = { Suficiente: 0, Alerta: 0, Insuficiente: 0, Revisar: 0, Otro: 0 };
    rows.forEach((e) => {
      const key = counts[e.resultado] != null ? e.resultado : 'Otro';
      counts[key] += 1;
    });
    return counts;
  }

  function buildInformeHtml() {
    if (!contexto) return null;
    const rows = contexto.evaluaciones || [];
    if (!rows.length) return null;

    const srv = contexto.servicio || {};
    const datos = contexto.datos_servicio || {};
    const params = contexto.parametros || {};
    const user = window.AtlasOps?.currentUser || {};
    const counts = resumenResultados(rows);
    const fecha = formatFechaInforme();

    const metaRows = [
      ['Empresa', srv.ID_Empresa || '—'],
      ['Sede', `${srv.ID_sede || ''} · ${srv.name_sede || ''}`.trim()],
      ['Servicio', `${srv.ID_servicio || ''} · ${srv.name_servicio || ''}`.trim()],
      ['Fecha del informe', fecha],
      ['Elaborado por', `${user.NAME_USER || ''} ${user.LAST_NAME_USER || ''}`.trim() || user.usuario_login || '—'],
      ['Rol / cargo', `${user.ROLL || '—'} / ${user.JOB || '—'}`],
    ];

    const datosRows = [
      ['Capacidad instalada', `${fmtNum(datos.capacidad_instalada, 0)} ${escape(datos.unidad_capacidad || '')}`.trim()],
      ['Promedio ocupado', fmtNum(datos.promedio_ocupado, 0)],
      ['% ocupación', fmtPct(datos.ocupacion_pct)],
      ['Horas servicio/día', fmtNum(datos.horas_servicio_dia, 0)],
      ['Jornadas/día', fmtNum(datos.jornadas_dia ?? 1, 0)],
      ['Utilización segura', fmtPct(params.utilizacion_segura)],
      ['Respaldo institucional', fmtPct(params.respaldo_general)],
      ['Umbral de alerta', fmtPct(params.umbral_alerta)],
    ];

    const bodyRows = rows
      .map((e, idx) => {
        const brecha = Number(e.brecha);
        const brechaCls = brecha < 0 ? 'neg' : '';
        return `<tr>
          <td class="num">${idx + 1}</td>
          <td>${escape(e.equipo)}${alertaEquipoTipo(e.equipo, e)}</td>
          <td>${escape(tipoLabel(e.tipo_calculo))}</td>
          <td class="num">${fmtNum(e.requerido_base, 0)}</td>
          <td class="num">${fmtNum(e.respaldo_unidades, 0)}</td>
          <td class="num">${fmtNum(e.requerido_final, 0)}</td>
          <td class="num">${fmtNum(e.disponible_real ?? e.inventario_disponible, 0)}</td>
          <td class="num ${brechaCls}">${fmtNum(e.brecha, 0)}</td>
          <td class="num">${fmtPct(e.suficiencia_pct)}</td>
          <td><span class="badge badge-${escape(String(e.resultado || 'Otro').toLowerCase())}">${escape(
            e.resultado || '—'
          )}</span></td>
          <td>${escape(e.acciones_sugeridas || '—')}</td>
        </tr>`;
      })
      .join('');

    const byRes = {};
    rows.forEach((e) => {
      const k = e.resultado || 'Sin clasificar';
      byRes[k] = (byRes[k] || 0) + 1;
    });
    const chartsHtml = window.AtlasOps?.charts
      ? window.AtlasOps.charts.pair(
          'Resultado de suficiencia',
          Object.entries(byRes).map(([label, value]) => ({ label, value })),
          '% suficiencia por equipo',
          rows.slice(0, 12).map((e) => ({
            label: e.equipo,
            value: (Number(e.suficiencia_pct) || 0) * 100,
            display: fmtPct(e.suficiencia_pct),
          }))
        )
      : '';

    return `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Informe de evaluación de suficiencia — ${escape(srv.name_servicio || '')}</title>
  <style>
    @page { size: A4 landscape; margin: 12mm; }
    * { box-sizing: border-box; }
    body {
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      color: #1a2430;
      font-size: 11px;
      line-height: 1.35;
      margin: 0;
      padding: 0;
    }
    .report-head {
      border-bottom: 2px solid #1a4a7a;
      padding-bottom: 10px;
      margin-bottom: 14px;
      display: flex;
      justify-content: space-between;
      gap: 16px;
    }
    .brand {
      font-size: 18px;
      font-weight: 800;
      color: #1a4a7a;
      letter-spacing: 0.04em;
      margin: 0 0 4px;
    }
    .subtitle {
      margin: 0;
      color: #445566;
      font-size: 12px;
    }
    .doc-id {
      text-align: right;
      color: #5a6b80;
      font-size: 10px;
    }
    h2 {
      margin: 0 0 8px;
      font-size: 14px;
      color: #1a4a7a;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .meta, .params {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 14px;
    }
    .meta td, .params td {
      border: 1px solid #c5d0dc;
      padding: 5px 8px;
      vertical-align: top;
    }
    .meta td:nth-child(odd), .params td:nth-child(odd) {
      width: 18%;
      background: #eef3f8;
      font-weight: 700;
      color: #243447;
    }
    .summary {
      display: flex;
      gap: 10px;
      margin: 0 0 14px;
      flex-wrap: wrap;
    }
    .summary .card {
      border: 1px solid #c5d0dc;
      border-radius: 6px;
      padding: 8px 12px;
      min-width: 110px;
      background: #f7fafc;
    }
    .summary .card strong { display: block; font-size: 16px; }
    .summary .card span { color: #5a6b80; font-size: 10px; text-transform: uppercase; }
    table.data {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 18px;
    }
    table.data th, table.data td {
      border: 1px solid #b7c4d3;
      padding: 5px 6px;
      text-align: left;
    }
    table.data th {
      background: #1a4a7a;
      color: #fff;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    table.data tbody tr:nth-child(even) { background: #f3f7fb; }
    .num { text-align: center; white-space: nowrap; }
    .num.neg { color: #b33a1a; font-weight: 700; }
    .badge {
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 10px;
      text-transform: uppercase;
    }
    .badge-suficiente { background: #d8f3e4; color: #176b48; }
    .badge-alerta { background: #ffe9b5; color: #8a6412; }
    .badge-insuficiente { background: #f8d4d4; color: #8f2c2c; }
    .badge-revisar, .badge-otro { background: #dde3f5; color: #3d4578; }
    .note {
      margin: 0 0 18px;
      color: #445566;
      font-size: 10px;
    }
    .signs {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 24px;
      margin-top: 28px;
    }
    .signs .box {
      border-top: 1px solid #334;
      padding-top: 8px;
      text-align: center;
      color: #445566;
      font-size: 10px;
    }
    .footer {
      margin-top: 20px;
      border-top: 1px solid #c5d0dc;
      padding-top: 8px;
      color: #6a7a8a;
      font-size: 9px;
      display: flex;
      justify-content: space-between;
    }
    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
    .pm-charts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 10px 0 16px; }
    .pm-chart { border: 1px solid #d5e0ea; border-radius: 8px; padding: 8px; background: #f8fbfa; }
    .pm-chart__title { font-size: 11px; font-weight: 700; color: #1a4a7a; margin-bottom: 6px; }
    .sigtb-pie { display: grid; grid-template-columns: auto 1fr; gap: 8px; align-items: center; }
    .sigtb-legend { list-style: none; margin: 0; padding: 0; font-size: 10px; }
    .sigtb-legend em { font-style: normal; color: #667; }
    .sigtb-swatch { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; }
    .sigtb-bar-svg { width: 100%; height: auto; }
    .sigtb-legend--compact { display: grid; grid-template-columns: 1fr 1fr; gap: 2px; margin-top: 6px; }
  </style>
</head>
<body>
  <header class="report-head">
    <div>
      <p class="brand">SIGTB</p>
      <p class="subtitle">Informe de evaluación de suficiencia de equipos biomédicos</p>
    </div>
    <div class="doc-id">
      <div>Documento: INF-SUF-${escape(srv.ID_servicio || 'SRV')}</div>
      <div>${escape(fecha)}</div>
    </div>
  </header>

  <h2>1. Identificación</h2>
  <table class="meta">
    <tr>
      <td>${escape(metaRows[0][0])}</td><td>${escape(metaRows[0][1])}</td>
      <td>${escape(metaRows[1][0])}</td><td>${escape(metaRows[1][1])}</td>
    </tr>
    <tr>
      <td>${escape(metaRows[2][0])}</td><td>${escape(metaRows[2][1])}</td>
      <td>${escape(metaRows[3][0])}</td><td>${escape(metaRows[3][1])}</td>
    </tr>
    <tr>
      <td>${escape(metaRows[4][0])}</td><td>${escape(metaRows[4][1])}</td>
      <td>${escape(metaRows[5][0])}</td><td>${escape(metaRows[5][1])}</td>
    </tr>
  </table>

  <h2>2. Datos del servicio y parámetros</h2>
  <table class="params">
    <tr>
      <td>${escape(datosRows[0][0])}</td><td>${datosRows[0][1]}</td>
      <td>${escape(datosRows[1][0])}</td><td>${datosRows[1][1]}</td>
      <td>${escape(datosRows[2][0])}</td><td>${datosRows[2][1]}</td>
      <td>${escape(datosRows[3][0])}</td><td>${datosRows[3][1]}</td>
    </tr>
    <tr>
      <td>${escape(datosRows[4][0])}</td><td>${datosRows[4][1]}</td>
      <td>${escape(datosRows[5][0])}</td><td>${datosRows[5][1]}</td>
      <td>${escape(datosRows[6][0])}</td><td>${datosRows[6][1]}</td>
      <td>${escape(datosRows[7][0])}</td><td>${datosRows[7][1]}</td>
    </tr>
  </table>

  <h2>3. Resumen de resultados</h2>
  <div class="summary">
    <div class="card"><strong>${rows.length}</strong><span>Equipos evaluados</span></div>
    <div class="card"><strong>${counts.Suficiente}</strong><span>Suficiente</span></div>
    <div class="card"><strong>${counts.Alerta}</strong><span>Alerta</span></div>
    <div class="card"><strong>${counts.Insuficiente}</strong><span>Insuficiente</span></div>
    <div class="card"><strong>${counts.Revisar + counts.Otro}</strong><span>Revisar / otro</span></div>
  </div>
  ${chartsHtml}

  <h2>4. Detalle por equipo</h2>
  <p class="note">Brecha = Inventario disponible − Requerido final. Suficiencia = Inventario disponible ÷ Requerido final (≥1 Suficiente; 0,80–0,99 Alerta; &lt;0,80 Insuficiente).</p>
  <table class="data">
    <thead>
      <tr>
        <th>#</th>
        <th>Equipo</th>
        <th>Tipo cálculo</th>
        <th>Req. base</th>
        <th>Respaldo</th>
        <th>Req. final</th>
        <th>Disponible</th>
        <th>Brecha</th>
        <th>% Suficiencia</th>
        <th>Resultado</th>
        <th>Acción sugerida</th>
      </tr>
    </thead>
    <tbody>${bodyRows}</tbody>
  </table>

  <div class="signs">
    <div class="box">Elaboró<br/>Nombre / firma</div>
    <div class="box">Revisó<br/>Nombre / firma</div>
    <div class="box">Aprobó<br/>Nombre / firma</div>
  </div>

  <footer class="footer">
    <span>Informe generado automáticamente por SIGTB — módulo de suficiencia de equipos.</span>
    <span>Elaborado por Ing. Jorge Felipe Blanco Medina</span>
    <span>Página 1</span>
  </footer>
</body>
</html>`;
  }

  function printInformeSuficiencia() {
    if (!contexto) {
      window.AtlasOps.showToast('Selecciona sede y servicio.', 'error');
      return;
    }
    if (!(contexto.evaluaciones || []).length) {
      window.AtlasOps.showToast('No hay equipos evaluados para imprimir.', 'error');
      return;
    }
    const html = buildInformeHtml();
    if (!html) {
      window.AtlasOps.showToast('No se pudo generar el informe.', 'error');
      return;
    }

    // iframe en la misma página: evita popup / welcome screen del navegador embebido
    const existing = document.getElementById('suf-print-frame');
    if (existing) existing.remove();

    const frame = document.createElement('iframe');
    frame.id = 'suf-print-frame';
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText =
      'position:fixed;right:0;bottom:0;width:0;height:0;border:0;opacity:0;pointer-events:none;';
    document.body.appendChild(frame);

    const doc = frame.contentDocument || frame.contentWindow?.document;
    if (!doc) {
      frame.remove();
      window.AtlasOps.showToast('No se pudo preparar la impresión.', 'error');
      return;
    }

    doc.open();
    doc.write(html);
    doc.close();

    const triggerPrint = () => {
      try {
        frame.contentWindow?.focus();
        frame.contentWindow?.print();
      } catch (err) {
        window.AtlasOps.showToast('No se pudo abrir el diálogo de impresión.', 'error');
      } finally {
        setTimeout(() => frame.remove(), 1000);
      }
    };

    // Esperar render del documento del iframe
    if (frame.contentWindow?.document?.readyState === 'complete') {
      setTimeout(triggerPrint, 150);
    } else {
      frame.onload = () => setTimeout(triggerPrint, 150);
      setTimeout(triggerPrint, 400);
    }
  }

  window.AtlasOps = window.AtlasOps || {};
  window.AtlasOps.loadSuficienciaPanel = initSuficienciaPanel;

  document.addEventListener('DOMContentLoaded', () => {
    setupTooltips();
    bindEvents();
  });
})();
