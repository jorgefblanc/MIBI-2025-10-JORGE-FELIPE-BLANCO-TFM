(() => {
  /* Cliente de dimensionamiento: parámetros, carga anual e informe PDF. */

  const $ = (id) => document.getElementById(id);

  const tipDefaults = {
    objetivo:
      'Calcular la carga anual de trabajo y estimar cuántos Ingenieros Clínicos se requieren para cubrir actividades programadas, correctivas y adicionales.',
    parametros:
      'Estos parámetros afectan directamente la disponibilidad anual del personal.',
    horas_semana: 'Modificar según jornada laboral institucional. Ejemplo: 42 h/semana.',
    semanas_anio: 'Base anual típica: 52 semanas.',
    vacaciones_h: 'Ejemplo: 15 días hábiles × 8,8 h = 132 h/año.',
    festivos_h: 'Puede ajustarse según país/calendario institucional.',
    permisos_h:
      'Tiempo no disponible para ejecución técnica (reuniones, permisos, capacitaciones).',
    productividad:
      'Fracción del tiempo realmente disponible para actividades del proceso (ej. 0,70 = 70%).',
    correctivo_sin_historico:
      'Si no existe histórico, el sistema estima correctivos automáticamente según este parámetro institucional (por defecto 15% de horas de MP).',
    contingencia:
      'Margen para imprevistos, ausencias, reprocesos y picos de carga (por defecto 15% sobre horas base).',
    horas_nominales:
      'Horas laborales brutas antes de descuentos = horas/semana × semanas/año.',
    horas_disponibles: 'Horas nominales menos vacaciones, festivos y permisos.',
    horas_efectivas: 'Horas disponibles ajustadas × productividad efectiva.',
    catalogos:
      'Catálogos institucionales para estandarizar la clasificación de equipos y servicios.',
    inventario:
      'Equipos agrupados por descripción. Si falta MP/Cal/Val, el cálculo reutiliza en memoria los datos de otro equipo con la misma descripción (sin guardarlos en los demás).',
    criticidad: 'Si marca Alto, indique si es por único equipo en el área, por alta complejidad o por ambos. Solo único en el área usa el ratio medio.',
    aplica_mp: 'Indique Sí si el equipo tiene mantenimiento preventivo programado.',
    freq_mp:
      'Número de veces que se realiza mantenimiento preventivo al equipo en un año.',
    tiempo_mp: 'Tiempo promedio en horas de cada intervención de MP.',
    horas_mp: 'Horas MP/año = frecuencia × tiempo (si aplica MP).',
    aplica_cal: 'Indique Sí si el equipo requiere calibración.',
    freq_cal: 'Frecuencia anual de calibración.',
    tiempo_cal: 'Tiempo promedio en horas de cada calibración.',
    aplica_val: 'Indique Sí si el equipo requiere validación / control de calidad.',
    freq_val: 'Frecuencia anual de validación / control de calidad.',
    tiempo_val: 'Tiempo promedio en horas de cada validación / control de calidad.',
    tercerizado:
      'Marque Sí si esta actividad se ejecuta mediante un servicio tercerizado. Freq/año y Tiempo pasan a 0 de inmediato y no suman carga al personal interno de Ingeniería Clínica.',
    aplica_cap: 'Indique Sí si se realiza capacitación asociada al equipo.',
    freq_cap: 'Frecuencia anual de capacitación.',
    tiempo_cap: 'Tiempo promedio en horas de cada capacitación.',
    tiene_historico:
      'Histórico solo con duración verificable (cierre − atención). Si hay MC o visita sin esas fechas, se mantiene el 15 % de las horas de MP.',
    historico_correctivo:
      'Horas anuales = suma de (cierre − atención) de MC y visitas. Sin ambas fechas no se asigna hora.',
    horas_correctivo:
      'Si hay duración verificable se usa ese histórico; si no, el estimado institucional sobre horas de MP.',
    gestion_documental:
      'Horas/año de hojas de vida, certificados, CMMS y registros. Se muestran por lote (mismo tipo de equipo).',
    acompanamiento:
      'Horas/año de entrega/recepción, coordinación, revisión de informes y cierre de evidencias.',
    otras_tareas: 'Proyectos, auditorías, formación y tareas especiales (h/año).',
    total_equipo: 'Carga total anual generada por cada equipo biomédico.',
    resumen: 'Suma de horas por actividad, servicio e institución.',
    ingenieros_requeridos:
      'El instrumento calcula cuántos Ingenieros Clínicos se requieren para cubrir toda la carga anual.',
    dashboard: 'Vista ejecutiva para análisis rápido de carga y necesidades.',
    informe: 'Informe listo para presentar a gerencia.',
    manual_sin_historico:
      'Ningún equipo con esta descripción tiene datos históricos. Ingrese frecuencia y tiempo promedio. Se usarán en el cálculo del grupo sin copiarlos a la BD de los demás.',
  };

  let meta = { tooltips: {}, catalogos: {}, can_edit: false, can_edit_adicionales: false };
  let contexto = null;
  let canEdit = false;
  let canEditAdicionales = false;
  let bound = false;
  let tipsReady = false;
  const catalogPrompted = new Set();
  const PAGE_SIZES = [10, 25, 50];
  const pagerState = {
    corr: { page: 0, size: 10 },
    adic: { page: 0, size: 10 },
  };
  let contextoReq = 0;

  function escape(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function tipText(key) {
    return (meta.tooltips && meta.tooltips[key]) || tipDefaults[key] || '';
  }

  function fmt(v, digits = 2) {
    if (v == null || v === '') return '—';
    const n = Number(v);
    if (Number.isNaN(n)) return '—';
    return Number.isInteger(n) ? String(n) : n.toFixed(digits);
  }

  function setMsg(text, isError = false) {
    const el = $('dim-msg');
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
    const sel = $('dim-empresa');
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

  function fillSedeSelect(empresaId) {
    const sel = $('dim-sede');
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
    fillSedeSelect('');
    if (!canPickAnyEmpresa() && userEmp) {
      $('dim-empresa').disabled = false;
    }
    window.AtlasOps?.refreshOrgScopeSummaries?.();
  }

  function setupTooltips() {
    window.AtlasOps?.bindTips?.({
      panelId: 'panel-dimensionamiento',
      bubbleId: 'dim-tip-bubble',
      selector: '.tip[data-dim-tip]',
      getContent: (btn) => tipText(btn.dataset.dimTip),
    });
  }

  function applyEditLocks() {
    document.querySelectorAll('#panel-dimensionamiento [data-dim-edit]').forEach((el) => {
      if (el.tagName === 'BUTTON') el.hidden = !canEdit;
      else el.disabled = !canEdit;
    });
    document.querySelectorAll('#panel-dimensionamiento [data-adq-lock]').forEach((el) => {
      el.disabled = true;
    });
    document.querySelectorAll('[data-dim-adicional-edit]').forEach((el) => {
      el.hidden = !canEditAdicionalesNow();
    });
    const banner = $('dim-banner');
    if (banner) {
      banner.hidden = false;
      banner.classList.toggle('error', !canEdit);
      banner.textContent = canEdit
        ? 'Modo operativo: puede editar parámetros y actividades por equipo.'
        : 'Modo consulta (asistencial): puede ver resultados; la edición está reservada a roles operativos.';
    }
    renderAdquisicionBanner();
  }

  function renderAdquisicionBanner() {
    const el = $('dim-adquisicion-banner');
    if (!el) return;
    const inbox = contexto?.adquisicion_inbox || {};
    const parts = [];
    if (inbox.created) {
      parts.push(
        `Se radicaron ${inbox.created} solicitud(es) en bandeja para equipos sin forma de adquisición.`
      );
    } else if (inbox.already) {
      parts.push(
        `${inbox.already} equipo(s) ya tenían solicitud pendiente de forma de adquisición.`
      );
    }
    if (inbox.warning) parts.push(inbox.warning);
    if (!parts.length) {
      el.hidden = true;
      el.textContent = '';
      return;
    }
    el.hidden = false;
    el.textContent = parts.join(' ');
  }

  function fillParams(p) {
    const form = $('dim-form-params');
    if (!form || !p) return;
    [
      'horas_semana',
      'semanas_anio',
      'vacaciones_h',
      'festivos_h',
      'permisos_h',
      'productividad',
      'correctivo_sin_historico',
      'contingencia',
    ].forEach((name) => {
      const input = form.elements[name];
      if (input) input.value = p[name] ?? '';
    });
    if ($('dim-kpi-nominal')) $('dim-kpi-nominal').textContent = `${fmt(p.horas_nominales)} h/año`;
    if ($('dim-kpi-disp')) $('dim-kpi-disp').textContent = `${fmt(p.horas_disponibles)} h/año`;
    if ($('dim-kpi-efec')) $('dim-kpi-efec').textContent = `${fmt(p.horas_efectivas)} h/año`;
  }

  function siNoOptions(selected) {
    const opts = meta.catalogos?.si_no || ['Sí', 'No'];
    const isYes = selected === true || selected === 'Sí' || selected === 1 || selected === '1';
    return opts
      .map(
        (o) =>
          `<option value="${escape(o)}" ${(o === 'Sí' ? isYes : !isYes) ? 'selected' : ''}>${escape(
            o
          )}</option>`
      )
      .join('');
  }

  function normalizeCriticidadUi(value) {
    const catalog = meta.catalogos?.criticidad || ['Bajo', 'Medio', 'Alto'];
    if (catalog.includes(value)) return value;
    const fold = String(value || '').toLowerCase();
    if (/vital|especializ|alto|alta/.test(fold)) return 'Alto';
    if (/bajo|baja/.test(fold)) return 'Bajo';
    return 'Medio';
  }

  function criticidadOptions(selected) {
    const catalog = meta.catalogos?.criticidad || ['Bajo', 'Medio', 'Alto'];
    const sel = normalizeCriticidadUi(selected);
    return catalog
      .map(
        (c) =>
          `<option value="${escape(c)}" ${c === sel ? 'selected' : ''}>${escape(c)}</option>`
      )
      .join('');
  }

  function fuenteLabel(fuente) {
    if (fuente === 'equipo_similar') return ' · cálculo desde equipo similar';
    if (fuente === 'inventario') return ' · inventario';
    if (fuente === 'manual') return ' · ingreso manual';
    if (fuente === 'dimensionamiento') return ' · dimensionamiento';
    return fuente ? ` · ${fuente}` : '';
  }

  function isSi(value) {
    return value === true || value === 1 || value === '1' || value === 'Sí';
  }

  function isNo(value) {
    return value === false || value === 0 || value === '0' || value === 'No';
  }

  /**
   * Una actividad (MP/Cal/Val) está completa si:
   * - Aplica = No, o
   * - Servicio tercerizado = Sí, o
   * - Aplica = Sí y ya hay datos (inventario / similar / diligenciados).
   * Freq/tiempo no pesan por separado en el % (solo las 3 actividades).
   */
  function activityIncomplete(eq, prefix) {
    if (isNo(eq[`aplica_${prefix}`])) return false;
    if (isSi(eq[`tercerizado_${prefix}`])) return false;

    // Aplica Sí (o pendiente): completo solo si hay datos útiles ya resueltos
    if (eq[`needs_manual_${prefix}`]) return true;
    const freq = Number(eq[`freq_${prefix}`]);
    const tiempo = Number(eq[`tiempo_${prefix}`]);
    if (freq > 0 && tiempo > 0) return false;
    const fuente = eq[`fuente_${prefix}`];
    if (fuente && fuente !== 'manual') return false;
    return true;
  }

  /** Verde: 3/3 · Amarillo: faltan ≤60% · Rojo: falta >60% (solo MP/Cal/Val) */
  function completenessClass(eq) {
    const prefixes = ['mp', 'cal', 'val'];
    const missing = prefixes.filter((p) => activityIncomplete(eq, p)).length;
    const missingPct = missing / prefixes.length;
    if (missing === 0) return 'dim-eq--ok';
    if (missingPct > 0.6) return 'dim-eq--critical';
    return 'dim-eq--warn';
  }

  function completenessFromForm(form) {
    if (!form) return 'dim-eq--warn';
    const fd = new FormData(form);
    const eq = {};
    ['mp', 'cal', 'val'].forEach((p) => {
      eq[`aplica_${p}`] = fd.get(`aplica_${p}`);
      eq[`tercerizado_${p}`] = fd.get(`tercerizado_${p}`);
      eq[`freq_${p}`] = fd.get(`freq_${p}`);
      eq[`tiempo_${p}`] = fd.get(`tiempo_${p}`);
      eq[`needs_manual_${p}`] = false;
      const freq = Number(eq[`freq_${p}`]);
      const tiempo = Number(eq[`tiempo_${p}`]);
      // Sin No ni tercerizado: incompleto si faltan freq/tiempo al aplicar Sí
      if (isSi(eq[`aplica_${p}`]) && !isSi(eq[`tercerizado_${p}`])) {
        eq[`needs_manual_${p}`] = !(freq > 0 && tiempo > 0);
      }
    });
    return completenessClass(eq);
  }

  function syncTercerizadoFields(form) {
    if (!form) return;
    ['mp', 'cal', 'val'].forEach((p) => {
      const select = form.querySelector(`select[name="tercerizado_${p}"]`);
      const hidden = form.querySelector(`input[type="hidden"][name="tercerizado_${p}"]`);
      if (!select && !hidden) return;
      const fieldset = (select || hidden).closest('fieldset');
      if (!fieldset) return;
      const terc = isSi(hidden?.value) || isSi(select?.value);
      fieldset.classList.toggle('dim-fieldset--tercerizado', terc);
      const freq = form.elements[`freq_${p}`];
      const tiempo = form.elements[`tiempo_${p}`];
      if (terc) {
        if (freq) {
          freq.value = '0';
          freq.readOnly = true;
        }
        if (tiempo) {
          tiempo.value = '0';
          tiempo.readOnly = true;
        }
        const hours = fieldset.querySelector('.dim-calc strong');
        if (hours) hours.textContent = fmt(0);
      } else {
        if (freq) freq.readOnly = false;
        if (tiempo) tiempo.readOnly = false;
      }
    });
  }

  function refreshEquipoStatus(article) {
    if (!article) return;
    const form = article.querySelector('.dim-eq-form');
    syncTercerizadoFields(form);
    const next = completenessFromForm(form);
    article.classList.remove('dim-eq--ok', 'dim-eq--warn', 'dim-eq--critical');
    article.classList.add(next);
  }

  function setSelectSiNo(select, value) {
    if (!select) return;
    if (isSi(value)) select.value = 'Sí';
    else if (isNo(value)) select.value = 'No';
  }

  function applyCatalogToForm(form, params) {
    if (!form || !params) return;
    if (params.criticidad && form.elements.criticidad) {
      form.elements.criticidad.value = normalizeCriticidadUi(params.criticidad);
    }
    if (form.elements.alto_unico_area) {
      form.elements.alto_unico_area.checked = Boolean(params.alto_unico_area);
    }
    if (form.elements.alto_especializado) {
      form.elements.alto_especializado.checked = Boolean(params.alto_especializado);
    }
    syncAltoCriterios(form);
    ['mp', 'cal', 'val'].forEach((p) => {
      setSelectSiNo(form.elements[`aplica_${p}`], params[`aplica_${p}`]);
      setSelectSiNo(form.elements[`tercerizado_${p}`], params[`tercerizado_${p}`]);
      if (form.elements[`freq_${p}`]) {
        form.elements[`freq_${p}`].value =
          params[`freq_${p}`] == null || params[`freq_${p}`] === ''
            ? ''
            : params[`freq_${p}`];
      }
      if (form.elements[`tiempo_${p}`]) {
        form.elements[`tiempo_${p}`].value =
          params[`tiempo_${p}`] == null || params[`tiempo_${p}`] === ''
            ? ''
            : params[`tiempo_${p}`];
      }
    });
    const article = form.closest('.dim-eq');
    if (article) refreshEquipoStatus(article);
  }

  function maybeOfferCatalog(article) {
    if (!article || !canEdit) return;
    const key = article.dataset.grupoKey || '';
    if (!key || catalogPrompted.has(key)) return;
    const grupo = (contexto?.grupos || []).find((g) => g.grupo_key === key);
    if (!grupo?.catalogo_disponible || !grupo.catalogo_parametros) return;
    if (completenessClass(grupo) === 'dim-eq--ok') {
      catalogPrompted.add(key);
      return;
    }
    catalogPrompted.add(key);
    const ok = window.confirm(
      `Este tipo de equipo tiene datos guardados previamente. ¿Desea cargarlos?\n\nTipo: ${grupo.equipo}`
    );
    if (!ok) return;
    const form = article.querySelector('.dim-eq-form');
    applyCatalogToForm(form, grupo.catalogo_parametros);
    window.AtlasOps.showToast('Parámetros previos cargados.', 'success');
  }

  function activityFieldset(label, tipKey, prefix, eq) {
    const tercerizado = Boolean(eq[`tercerizado_${prefix}`]);
    const lockMp = prefix === 'mp' && Boolean(eq.mp_forzado_tercerizado);
    const zeroed = tercerizado || lockMp;
    const freqVal = zeroed
      ? 0
      : eq[`freq_${prefix}`] === '' || eq[`freq_${prefix}`] == null
        ? ''
        : eq[`freq_${prefix}`];
    const tiempoVal = zeroed
      ? 0
      : eq[`tiempo_${prefix}`] === '' || eq[`tiempo_${prefix}`] == null
        ? ''
        : eq[`tiempo_${prefix}`];
    const fuente = fuenteLabel(eq[`fuente_${prefix}`]);
    const lockAttr = lockMp ? ' disabled data-adq-lock="1"' : ' data-dim-edit';
    const roAttr = zeroed ? ' readonly' : '';
    const lockHidden = lockMp
      ? `<input type="hidden" name="aplica_${prefix}" value="Sí" />
         <input type="hidden" name="tercerizado_${prefix}" value="Sí" />`
      : '';
    const lockNote = lockMp
      ? '<p class="field-hint">Forzado por forma de adquisición (Comodato/Leasing): MP lo ejecuta un tercero.</p>'
      : '';
    return `
      <fieldset class="${zeroed ? 'dim-fieldset--tercerizado' : ''}">
        <legend>${escape(label)}
          <button type="button" class="tip" data-dim-tip="${tipKey}" aria-label="Ayuda">?</button>
        </legend>
        ${lockHidden}
        <label>Aplica<select name="aplica_${prefix}"${lockAttr}>${siNoOptions(
          eq[`aplica_${prefix}`]
        )}</select></label>
        <label class="dim-tercerizado">
          <span class="field-with-tip">Servicio tercerizado
            <button type="button" class="tip" data-dim-tip="tercerizado" aria-label="Ayuda">?</button>
          </span>
          <select name="tercerizado_${prefix}"${lockAttr}>${siNoOptions(tercerizado || lockMp)}</select>
        </label>
        <label>
          <span class="field-with-tip">Freq/año
            <button type="button" class="tip" data-dim-tip="freq_${prefix}" aria-label="Ayuda">?</button>
          </span>
          <input type="number" step="0.1" min="0" name="freq_${prefix}" value="${escape(
            freqVal
          )}" data-dim-edit${roAttr} />
        </label>
        <label>
          <span class="field-with-tip">Tiempo (h)
            <button type="button" class="tip" data-dim-tip="tiempo_${prefix}" aria-label="Ayuda">?</button>
          </span>
          <input type="number" step="0.01" min="0" name="tiempo_${prefix}" value="${escape(
            tiempoVal
          )}" data-dim-edit${roAttr} />
        </label>
        ${lockNote}
        <span class="dim-calc">Horas carga IC (grupo): <strong>${fmt(
          eq[`horas_${prefix}`]
        )}</strong>${escape(fuente)}${
          tercerizado || lockMp ? ' · <em class="dim-tercerizado-tag">tercerizado</em>' : ''
        }
          ${
            prefix === 'mp'
              ? '<button type="button" class="tip" data-dim-tip="horas_mp" aria-label="Ayuda">?</button>'
              : ''
          }
        </span>
      </fieldset>`;
  }

  function renderEquipos() {
    const root = $('dim-equipos-list');
    if (!root) return;
    const grupos = contexto?.grupos || [];
    if (!grupos.length) {
      root.innerHTML =
        '<p class="field-hint">No hay equipos en el inventario biomédico de esta sede.</p>';
      return;
    }
    root.innerHTML = grupos
      .map((eq) => {
        const id = eq.referencia_inventario_equipo_id;
        const statusClass = completenessClass(eq);
        const servicios = (eq.servicios || []).join(', ') || '—';
        const codigos = (eq.codigos || []).slice(0, 8).join(', ');
        const masCodigos =
          (eq.codigos || []).length > 8 ? ` (+${eq.codigos.length - 8})` : '';
        return `
        <article class="dim-eq ${statusClass}" data-eq-id="${id}" data-grupo-key="${escape(
          eq.grupo_key
        )}">
          <button type="button" class="dim-eq__toggle" aria-expanded="false">
            <span class="dim-acc__chevron" aria-hidden="true">▸</span>
            <span class="dim-eq__title">
              <strong class="dim-eq__qty">${escape(String(eq.cantidad))} ×</strong>
              <span class="dim-eq__name">${escape(eq.equipo)}${window.AtlasOps.equipoAlertaMarkup(eq)}</span>
            </span>
            <em class="dim-eq__hours">${fmt(eq.total_horas)} h/año</em>
          </button>
          <div class="dim-eq__body" hidden>
            <div class="dim-eq__meta">
              <span>Cantidad: <strong>${escape(String(eq.cantidad))}</strong></span>
              <span>Servicio(s): ${escape(servicios)}</span>
              <span>Códigos: ${escape(codigos + masCodigos || '—')}</span>
              <span>Acumulado grupo: <strong>${fmt(eq.total_horas)} h/año</strong></span>
              ${
                eq.mp_forzado_tercerizado
                  ? '<span>Plantilla IC: <strong>no aplica</strong> (Comodato/Leasing)</span>'
                  : eq.criticidad === 'Alto' && eq.alto_unico_area && !eq.alto_especializado
                  ? '<span>Plantilla IC: <strong>Media</strong> (único en el área)</span>'
                  : eq.criticidad === 'Alto'
                    ? '<span>Plantilla IC: <strong>Alta</strong></span>'
                    : ''
              }
              ${
                eq.mp_forzado_tercerizado
                  ? '<span>Adquisición: <strong>Comodato/Leasing</strong> · MP y correctivo estimado a cargo de un tercero. Otras actividades y correctivos de apoyo sí pueden sumar. No entra en el IC por criticidad.</span>'
                  : eq.mp_forzado_count
                    ? `<span>Adquisición mixta: ${escape(String(eq.mp_forzado_count))} unidad(es) en Comodato/Leasing (fuera de plantilla; MP/correctivo estimado tercero)</span>`
                    : eq.formas_adquisicion?.length
                      ? `<span>Forma de adquisición: ${escape((eq.formas_adquisicion || []).join(', '))}</span>`
                      : ''
              }
              ${
                eq.adquisicion_faltante_count
                  ? `<span>Sin modalidad: <strong>${escape(String(eq.adquisicion_faltante_count))}</strong> (solicitud en bandeja)</span>`
                  : ''
              }
            </div>
            <form class="dim-eq-form" data-eq-form="${id}">
              <label>
                <span class="field-with-tip">Criticidad
                  <button type="button" class="tip" data-dim-tip="criticidad">?</button>
                </span>
                <select name="criticidad" data-dim-edit>${criticidadOptions(eq.criticidad)}</select>
              </label>
              <fieldset class="dim-eq__alto-criterios" data-alto-criterios ${eq.criticidad === 'Alto' ? '' : 'hidden'}>
                <legend>Si es Alta, ¿por qué?</legend>
                <label class="dim-eq__check">
                  <input type="checkbox" name="alto_unico_area" data-dim-edit ${eq.alto_unico_area ? 'checked' : ''} />
                  Único equipo en el área (aplica ratio medio)
                </label>
                <label class="dim-eq__check">
                  <input type="checkbox" name="alto_especializado" data-dim-edit ${eq.alto_especializado ? 'checked' : ''} />
                  Alta complejidad / especializado / soporte vital (aplica ratio alto)
                </label>
                <p class="field-hint">Si marca ambos, se aplica el criterio de alta criticidad. Criticidad y estos criterios se aplican a todas las unidades de este tipo en la sede.</p>
              </fieldset>
              ${activityFieldset('MP', 'aplica_mp', 'mp', eq)}
              ${activityFieldset('Calibración', 'aplica_cal', 'cal', eq)}
              ${activityFieldset('Validación / Control de calidad', 'aplica_val', 'val', eq)}
              <div class="dim-eq__meta dim-eq__meta--totals">
                <span>Capacitación (grupo): <strong>${fmt(eq.horas_cap)} h</strong></span>
                <span>Correctivos (grupo): <strong>${fmt(eq.horas_correctivo)} h</strong></span>
                <span>Gestión doc. (grupo): <strong>${fmt(eq.gestion_documental_h)} h</strong></span>
                <span>Acompañamiento (grupo): <strong>${fmt(eq.acompanamiento_h)} h</strong></span>
                <span>Otras tareas (grupo): <strong>${fmt(eq.otras_tareas_h)} h</strong></span>
              </div>
              <p class="dim-total">Total horas/año del grupo: <strong>${fmt(eq.total_horas)}</strong>
                <button type="button" class="tip" data-dim-tip="total_equipo">?</button>
              </p>
              <p class="field-hint">
                Al guardar, MP/Cal/Val quedan en el equipo de referencia. Las demás unidades
                con la misma descripción los usarán solo para el cálculo (sin copiarlos en BD).
              </p>
              <button type="submit" class="btn btn-primary" data-dim-edit>Guardar parámetros del grupo</button>
            </form>
          </div>
        </article>`;
      })
      .join('');
    applyEditLocks();
  }

  function slicePaged(rows, key, searchId, sizeId, pagerId, labelId, haystack) {
    const q = String($(searchId)?.value || '')
      .toLowerCase()
      .trim();
    const filtered = q
      ? rows.filter((row) => haystack(row).toLowerCase().includes(q))
      : rows.slice();
    const n = Number($(sizeId)?.value);
    if (PAGE_SIZES.includes(n)) pagerState[key].size = n;
    const size = pagerState[key].size;
    const pages = Math.max(1, Math.ceil(filtered.length / size) || 1);
    if (pagerState[key].page >= pages) pagerState[key].page = pages - 1;
    if (pagerState[key].page < 0) pagerState[key].page = 0;
    const start = pagerState[key].page * size;
    const slice = filtered.slice(start, start + size);
    const pager = $(pagerId);
    if (pager) pager.hidden = filtered.length <= 10 && !q;
    const label = $(labelId);
    if (label) {
      const from = filtered.length ? start + 1 : 0;
      const to = Math.min(start + size, filtered.length);
      label.textContent = `${from}–${to} de ${filtered.length}`;
    }
    return slice;
  }

  function opChartsHtml(dash, hoursItems) {
    const charts = window.AtlasOps?.charts;
    if (!charts) return '';
    const crit = (dash?.por_criticidad || []).map((a) => ({
      label: a.criticidad,
      value: Number(a.horas) || 0,
      display: `${fmt(a.horas)} h`,
    }));
    const hours = (hoursItems || []).map((a) => ({
      label: a.actividad || a.equipo || a.servicio || a.label,
      value: Number(a.horas ?? a.value) || 0,
      display: `${fmt(a.horas ?? a.value)} h`,
    }));
    return charts.pair('Criticidad (horas/año)', crit, 'Número de horas', hours);
  }

  function fuenteCorrectivoLabel(eq) {
    const src = eq.fuente_correctivo || '';
    if (src === 'manual') return 'Manual';
    if (src === 'ejecucion') return 'Ejecución (h)';
    if (src === 'ejecucion_eventos') return 'Ejecución (eventos)';
    if (src === 'estimado_con_eventos') return 'Estimado (hay eventos)';
    return 'Estimado';
  }

  function renderCorrectivos() {
    const tbody = $('dim-table-correctivos')?.querySelector('tbody');
    if (!tbody) return;
    const rows = contexto?.equipos || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7">Sin equipos en la sede.</td></tr>';
      if ($('dim-corr-pager')) $('dim-corr-pager').hidden = true;
      return;
    }
    const slice = slicePaged(
      rows,
      'corr',
      'dim-corr-search',
      'dim-corr-page-size',
      'dim-corr-pager',
      'dim-corr-page-label',
      (eq) => `${eq.codigo || ''} ${eq.equipo || ''}`
    );
    tbody.innerHTML = slice
      .map(
        (eq) => `
      <tr>
        <td>${escape(eq.codigo)}</td>
        <td>${escape(eq.equipo)}${window.AtlasOps.equipoAlertaMarkup(eq)}</td>
        <td>${eq.tiene_historico_correctivo ? 'Sí' : 'No'}</td>
        <td>${escape(fuenteCorrectivoLabel(eq))}</td>
        <td>${Number(eq.ejecucion_correctivos || 0)} / ${Number(eq.ejecucion_visitas || 0)}</td>
        <td>${fmt(eq.historico_correctivo_h)}</td>
        <td><strong>${fmt(eq.horas_correctivo)}</strong></td>
      </tr>`
      )
      .join('');
  }

  function canEditAdicionalesNow() {
    return (
      canEditAdicionales ||
      String(currentUser().ROLL || '').toUpperCase() === 'OPERATIVO'
    );
  }

  function renderAdicionales() {
    const tbody = $('dim-table-adicionales')?.querySelector('tbody');
    if (!tbody) return;
    const grupos = (contexto?.grupos || []).filter((g) => Number(g.cantidad) > 0);
    const editable = canEditAdicionalesNow();
    if (!grupos.length) {
      tbody.innerHTML =
        '<tr><td colspan="6">No hay lotes de equipo en dotación para esta sede.</td></tr>';
      if ($('dim-adic-pager')) $('dim-adic-pager').hidden = true;
      return;
    }
    const slice = slicePaged(
      grupos,
      'adic',
      'dim-adic-search',
      'dim-adic-page-size',
      'dim-adic-pager',
      'dim-adic-page-label',
      (g) => String(g.equipo || '')
    );
    tbody.innerHTML = slice
      .map((g) => {
        const addBtn = editable
          ? `<button type="button" class="btn btn-ghost btn-sm" data-dim-adicional-edit data-add-adicional="${escape(
              g.grupo_key
            )}">Agregar</button>`
          : '';
        return `
      <tr>
        <td><strong>${escape(g.equipo)}</strong></td>
        <td>${escape(String(g.cantidad))}</td>
        <td>${fmt(g.gestion_documental_h)}</td>
        <td>${fmt(g.acompanamiento_h)}</td>
        <td>${fmt(g.otras_tareas_h)}</td>
        <td class="table-actions">${addBtn}</td>
      </tr>`;
      })
      .join('');
  }

  function renderResumen() {
    const root = $('dim-resumen');
    const r = contexto?.resumen;
    if (!root || !r) return;
    root.innerHTML = `
      <div class="dim-kpi-row">
        <div class="dim-kpi"><span>Equipos en dotación</span><strong>${r.total_equipos}</strong></div>
        ${
          Number(r.equipos_excluidos) > 0
            ? `<div class="dim-kpi"><span>Excluidos (baja)</span><strong>${r.equipos_excluidos}</strong></div>`
            : ''
        }
        <div class="dim-kpi"><span>Horas base</span><strong>${fmt(r.total_base)}</strong></div>
        <div class="dim-kpi"><span>Contingencia</span><strong>${fmt(r.contingencia_h)}</strong></div>
        <div class="dim-kpi"><span>Horas ajustadas</span><strong>${fmt(r.total_ajustado)}</strong></div>
        <div class="dim-kpi"><span>IC requeridos</span><strong title="${escape(
          tipText('ingenieros_requeridos')
        )}">${fmt(r.ingenieros_requeridos)}</strong></div>
        <div class="dim-kpi dim-kpi--accent"><span>IC recomendados</span><strong>${fmt(
          r.ingenieros_recomendados,
          0
        )}</strong></div>
      </div>
      <div class="dim-split">
        <div>
          <h4>Por actividad</h4>
          <ul class="dim-bars">
            ${(r.por_actividad || [])
              .map(
                (a) =>
                  `<li><span>${escape(a.actividad)}</span><strong>${fmt(a.horas)} h</strong></li>`
              )
              .join('')}
          </ul>
        </div>
        <div>
          <h4>Por servicio</h4>
          <ul class="dim-bars">
            ${(r.por_servicio || [])
              .map(
                (a) =>
                  `<li><span>${escape(a.servicio)}</span><strong>${fmt(a.horas)} h</strong></li>`
              )
              .join('')}
          </ul>
        </div>
      </div>
      ${
        window.AtlasOps?.charts
          ? window.AtlasOps.charts.pair(
              'Distribución por actividad',
              (r.por_actividad || []).map((a) => ({
                label: a.actividad,
                value: Number(a.horas) || 0,
                display: `${fmt(a.horas)} h`,
              })),
              'Distribución por servicio',
              (r.por_servicio || []).map((a) => ({
                label: a.servicio,
                value: Number(a.horas) || 0,
                display: `${fmt(a.horas)} h`,
              }))
            )
          : ''
      }`;
  }

  function renderDashboard() {
    const root = $('dim-dashboard');
    const d = contexto?.dashboard;
    if (!root || !d) return;
    const disponibles = d.ingenieros_disponibles ?? 0;
    const rec = d.ingenieros_recomendados ?? 0;
    root.innerHTML = `
      <div class="dim-kpi-row">
        <div class="dim-kpi"><span>Horas ajustadas/año</span><strong>${fmt(d.total_ajustado)}</strong></div>
        <div class="dim-kpi"><span>Horas efectivas / IC</span><strong>${fmt(d.horas_efectivas)}</strong></div>
        <div class="dim-kpi"><span>IC requeridos</span><strong>${fmt(d.ingenieros_requeridos)}</strong></div>
        <div class="dim-kpi"><span>IC recomendados</span><strong>${fmt(rec, 0)}</strong></div>
        <div class="dim-kpi"><span>IC/técnicos asignados a la sede</span><strong>${disponibles}</strong></div>
        <div class="dim-kpi ${d.brecha_personal < 0 ? 'dim-kpi--warn' : 'dim-kpi--ok'}">
          <span>Brecha (asignados − rec)</span><strong>${fmt(d.brecha_personal, 0)}</strong>
        </div>
      </div>
      ${opChartsHtml(d, contexto?.resumen?.por_actividad || d.por_equipo_tipo || [])}
      <div class="dim-split">
        <div>
          <h4>Criticidad</h4>
          <ul class="dim-bars">
            ${(d.por_criticidad || [])
              .map(
                (a) =>
                  `<li><span>${escape(a.criticidad)}</span><strong>${fmt(a.horas)} h</strong></li>`
              )
              .join('')}
          </ul>
        </div>
        <div>
          <h4>Top equipos (tipo)</h4>
          <ul class="dim-bars">
            ${(d.por_equipo_tipo || [])
              .slice(0, 12)
              .map(
                (a) =>
                  `<li><span>${escape(a.equipo)}</span><strong>${fmt(a.horas)} h</strong></li>`
              )
              .join('')}
          </ul>
        </div>
      </div>`;
  }

  function renderInforme() {
    const root = $('dim-informe');
    const inf = contexto?.informe;
    if (!root || !inf) return;
    root.innerHTML = `
      <article class="dim-informe-card">
        <h3>Informe exportable</h3>
        <p><strong>1. Objetivo.</strong> ${escape(inf.objetivo)}</p>
        <p><strong>2. Perfil evaluado.</strong> ${escape(inf.perfil)}</p>
        <p><strong>3. Resultado general</strong></p>
        <ul>
          <li>Total equipos: <strong>${inf.total_equipos}</strong></li>
          <li>Total horas base: <strong>${fmt(inf.total_base)}</strong></li>
          <li>Contingencia: <strong>${fmt(inf.contingencia_h)}</strong></li>
          <li>Total horas ajustadas: <strong>${fmt(inf.total_ajustado)}</strong></li>
          <li>Horas efectivas / IC: <strong>${fmt(inf.horas_efectivas)}</strong></li>
          <li>IC requeridos: <strong>${fmt(inf.ingenieros_requeridos)}</strong></li>
          <li>IC recomendados: <strong>${fmt(inf.ingenieros_recomendados, 0)}</strong></li>
          <li>IC disponibles: <strong>${inf.ingenieros_disponibles}</strong></li>
        </ul>
        <h4>4. Resumen por servicio</h4>
        <ul class="dim-bars">
          ${(inf.por_servicio || [])
            .map(
              (a) =>
                `<li><span>${escape(a.servicio)}</span><strong>${fmt(a.horas)} h</strong></li>`
            )
            .join('')}
        </ul>
        <p><strong>5. Interpretación.</strong> ${escape(inf.interpretacion)}</p>
        <p><strong>6. Recomendación.</strong> ${escape(inf.recomendacion)}</p>
        ${
          window.AtlasOps?.charts
            ? window.AtlasOps.charts.barTrend(
                'Horas por servicio',
                (inf.por_servicio || []).map((a) => ({
                  label: a.servicio,
                  value: Number(a.horas) || 0,
                  display: `${fmt(a.horas)} h`,
                }))
              )
            : ''
        }
      </article>`;
  }

  function renderAll() {
    fillParams(contexto?.parametros);
    renderEquipos();
    renderCorrectivos();
    renderAdicionales();
    renderResumen();
    renderDashboard();
    renderInforme();
    $('dim-content').hidden = false;
    $('dim-export-csv').hidden = false;
    $('dim-export-xlsx').hidden = false;
    if ($('dim-export-pdf')) $('dim-export-pdf').hidden = false;
  }

  async function loadMeta() {
    const { data } = await window.AtlasOps.api('/api/dimensionamiento/meta');
    if (data?.ok) {
      meta = data;
      canEdit = Boolean(data.can_edit);
      canEditAdicionales = Boolean(data.can_edit_adicionales);
    }
  }

  async function loadContexto(sedeId, opts = {}) {
    const req = ++contextoReq;
    setMsg('Cargando dimensionamiento…');
    catalogPrompted.clear();
    const { response, data } = await window.AtlasOps.api(
      `/api/dimensionamiento/contexto?sede_id=${sedeId}&anio=${encodeURIComponent(
        Number($('dim-anio')?.value) || new Date().getFullYear()
      )}`
    );
    if (req !== contextoReq) return;
    if (!response.ok || !data.ok) {
      setMsg(data.error || 'No se pudo cargar el contexto.', true);
      window.AtlasOps.showToast(data.error || 'Error al cargar.', 'error');
      return;
    }
    contexto = data;
    canEdit = Boolean(data.can_edit);
    canEditAdicionales = Boolean(data.can_edit_adicionales);
    if ($('dim-anio') && data.anio) $('dim-anio').value = String(data.anio);
    setMsg('');
    renderAll();
    applyEditLocks();
    if (opts.restoreGrupoKey || opts.restoreEqId) {
      restoreOpenGrupo(opts.restoreGrupoKey, opts.restoreEqId);
    }
  }

  function restoreOpenGrupo(grupoKey, eqId) {
    const root = $('dim-equipos-list');
    if (!root) return;
    const articles = [...root.querySelectorAll('.dim-eq')];
    const article =
      articles.find((a) => grupoKey && a.dataset.grupoKey === String(grupoKey)) ||
      articles.find((a) => eqId != null && eqId !== '' && String(a.dataset.eqId) === String(eqId));
    if (!article) return;
    catalogPrompted.add(article.dataset.grupoKey || '');
    const acc = article.closest('.dim-acc');
    if (acc) {
      const accBody = acc.querySelector('.dim-acc__body');
      if (accBody) accBody.hidden = false;
      acc.classList.add('is-open');
      acc.querySelector('.dim-acc__toggle')?.setAttribute('aria-expanded', 'true');
    }
    const body = article.querySelector('.dim-eq__body');
    const toggle = article.querySelector('.dim-eq__toggle');
    if (body) body.hidden = false;
    article.classList.add('is-open');
    toggle?.setAttribute('aria-expanded', 'true');
    requestAnimationFrame(() => {
      article.scrollIntoView({ block: 'center', inline: 'nearest' });
      toggle?.focus({ preventScroll: true });
    });
  }

  function collapseEquipo(article) {
    if (!article) return;
    article.classList.remove('is-open');
    const body = article.querySelector('.dim-eq__body');
    if (body) body.hidden = true;
    article.querySelector('.dim-eq__toggle')?.setAttribute('aria-expanded', 'false');
  }

  function fillAdicionalLoteSelect(selectedKey = '') {
    const sel = $('dim-adicional-lote');
    if (!sel) return;
    const grupos = contexto?.grupos || [];
    sel.innerHTML = '<option value="">Selecciona el tipo de equipo</option>';
    grupos.forEach((g) => {
      const opt = document.createElement('option');
      opt.value = g.grupo_key;
      opt.textContent = `${g.cantidad} × ${g.equipo}`;
      if (String(g.grupo_key) === String(selectedKey)) opt.selected = true;
      sel.appendChild(opt);
    });
    updateAdicionalPreview();
  }

  function selectedAdicionalGrupo() {
    const key = $('dim-adicional-lote')?.value || '';
    return (contexto?.grupos || []).find((g) => String(g.grupo_key) === String(key)) || null;
  }

  function updateAdicionalPreview() {
    const preview = $('dim-adicional-preview');
    const hint = $('dim-adicional-lote-hint');
    const horas = Number($('dim-adicional-horas')?.value || 0);
    const freq = Number($('dim-adicional-freq')?.value || 0);
    const grupo = selectedAdicionalGrupo();
    const n = Number(grupo?.cantidad || 0);
    if (hint) {
      hint.textContent = grupo
        ? `Se aplica a las ${n} unidad(es) del lote «${grupo.equipo}» (mismas características).`
        : '';
    }
    if (!preview) return;
    if (horas > 0 && freq > 0) {
      const porEquipo = horas * freq;
      const lote = porEquipo * Math.max(n, 1);
      preview.textContent = `Horas/año por equipo: ${fmt(porEquipo)} · Horas/año del lote: ${fmt(
        lote
      )}`;
    } else {
      preview.textContent = 'Horas/año por equipo: — · Horas/año del lote: —';
    }
  }

  function openAdicionalModal(grupoKey = '') {
    if (!canEditAdicionalesNow()) {
      window.AtlasOps.showToast(
        'Solo cargos del rol operativo pueden agregar actividades adicionales.',
        'warn'
      );
      return;
    }
    if (!contexto?.grupos?.length) {
      window.AtlasOps.showToast('Carga una sede con inventario primero.', 'error');
      return;
    }
    $('dim-adicional-form')?.reset();
    fillAdicionalLoteSelect(grupoKey);
    const modal = $('dim-adicional-modal');
    if (modal) {
      modal.hidden = false;
      document.body.style.overflow = 'hidden';
    }
  }

  function closeAdicionalModal() {
    const modal = $('dim-adicional-modal');
    if (modal) modal.hidden = true;
    document.body.style.overflow = '';
  }

  async function submitAdicional(event) {
    event.preventDefault();
    if (!canEditAdicionalesNow()) return;
    const sedeId = contexto?.sede?.id || $('dim-sede')?.value;
    const grupoKey = $('dim-adicional-lote')?.value;
    const tipo = $('dim-adicional-tipo')?.value;
    const horas = Number($('dim-adicional-horas')?.value || 0);
    const periodicidad = Number($('dim-adicional-freq')?.value || 0);
    if (!sedeId || !grupoKey || !tipo || horas <= 0 || periodicidad <= 0) {
      window.AtlasOps.showToast('Completa tipo, horas y periodicidad anual.', 'error');
      return;
    }
    const { response, data } = await window.AtlasOps.api(
      '/api/dimensionamiento/grupos/actividad-adicional',
      {
        method: 'POST',
        body: JSON.stringify({
          sede_id: Number(sedeId),
          grupo_key: grupoKey,
          tipo,
          horas,
          periodicidad_anual: periodicidad,
        }),
      }
    );
    if (!response.ok || !data.ok) {
      window.AtlasOps.showToast(data.error || 'No se pudo guardar la actividad.', 'error');
      return;
    }
    window.AtlasOps.showToast(data.message, 'success');
    closeAdicionalModal();
    await loadContexto(sedeId);
  }

  function syncAltoCriterios(form) {
    if (!form) return;
    const wrap = form.querySelector('[data-alto-criterios]');
    if (!wrap) return;
    wrap.hidden = (form.elements.criticidad?.value || '') !== 'Alto';
  }

  function readFormActividad(form) {
    const fd = new FormData(form);
    const get = (k) => fd.get(k);
    const refId = Number(form.dataset.eqForm);
    const ref = (contexto?.equipos || []).find(
      (e) => Number(e.inventario_equipo_id) === refId
    );
    // Cap/correctivos/adicionales se conservan del equipo de referencia
    // (el formulario de grupo solo edita MP/Cal/Val + criticidad).
    const payload = {
      criticidad: get('criticidad') || ref?.criticidad || 'Medio',
      alto_unico_area: form.elements.alto_unico_area?.checked ? 'Sí' : 'No',
      alto_especializado: form.elements.alto_especializado?.checked ? 'Sí' : 'No',
      aplica_mp: get('aplica_mp'),
      freq_mp: get('freq_mp'),
      tiempo_mp: get('tiempo_mp'),
      aplica_cal: get('aplica_cal'),
      freq_cal: get('freq_cal'),
      tiempo_cal: get('tiempo_cal'),
      aplica_val: get('aplica_val'),
      freq_val: get('freq_val'),
      tiempo_val: get('tiempo_val'),
      tercerizado_mp: get('tercerizado_mp'),
      tercerizado_cal: get('tercerizado_cal'),
      tercerizado_val: get('tercerizado_val'),
      aplica_cap: ref?.aplica_cap ? 'Sí' : 'No',
      freq_cap: ref?.freq_cap ?? 0,
      tiempo_cap: ref?.tiempo_cap ?? 0,
      tiene_historico_correctivo: ref?.tiene_historico_correctivo ? 'Sí' : 'No',
      historico_correctivo_h: ref?.historico_correctivo_h ?? '',
      gestion_documental_h: ref?.gestion_documental_h ?? 0,
      acompanamiento_h: ref?.acompanamiento_h ?? 0,
      otras_tareas_h: ref?.otras_tareas_h ?? 0,
      observaciones: ref?.observaciones || '',
    };
    ['mp', 'cal', 'val'].forEach((p) => {
      if (isSi(payload[`tercerizado_${p}`])) {
        payload[`freq_${p}`] = 0;
        payload[`tiempo_${p}`] = 0;
      }
    });
    return payload;
  }

  function bindEvents() {
    if (bound) return;
    bound = true;
    const panel = $('panel-dimensionamiento');
    if (!panel) return;

    panel.addEventListener('change', (event) => {
      const el = event.target;
      if (!(el instanceof HTMLElement)) return;
      const name = el.getAttribute('name') || '';
      if (
        name !== 'criticidad' &&
        !name.startsWith('aplica_') &&
        !name.startsWith('tercerizado_') &&
        !name.startsWith('freq_') &&
        !name.startsWith('tiempo_')
      ) {
        return;
      }
      const form = el.closest('[data-eq-form]');
      if (name === 'criticidad' && form) syncAltoCriterios(form);
      const article = el.closest('.dim-eq');
      if (article) refreshEquipoStatus(article);
    });

    panel.addEventListener('click', (event) => {
      // Las ayudas (?) se manejan en setupTooltips (capture en document).
      if (event.target.closest('[data-dim-tip]')) return;

      const addAdicional = event.target.closest('[data-add-adicional]');
      if (addAdicional) {
        event.preventDefault();
        openAdicionalModal(addAdicional.dataset.addAdicional);
        return;
      }
      if (event.target.closest('#dim-add-adicional')) {
        event.preventDefault();
        openAdicionalModal();
        return;
      }

      const accToggle = event.target.closest('.dim-acc__toggle');
      if (accToggle) {
        window.AtlasOps?.exclusiveAccordion?.(panel, accToggle);
        return;
      }

      const eqToggle = event.target.closest('.dim-eq__toggle');
      if (eqToggle) {
        const article = eqToggle.closest('.dim-eq');
        const body = article?.querySelector('.dim-eq__body');
        const open = body && body.hidden;
        if (open) {
          article.parentElement?.querySelectorAll('.dim-eq.is-open').forEach((other) => {
            if (other === article) return;
            other.classList.remove('is-open');
            const ob = other.querySelector('.dim-eq__body');
            if (ob) ob.hidden = true;
            other.querySelector('.dim-eq__toggle')?.setAttribute('aria-expanded', 'false');
          });
        }
        if (body) body.hidden = !open;
        article?.classList.toggle('is-open', open);
        eqToggle.setAttribute('aria-expanded', String(open));
        if (open && article) maybeOfferCatalog(article);
      }
    });

    $('dim-empresa')?.addEventListener('change', () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      fillSedeSelect($('dim-empresa').value);
    });

    $('dim-sede')?.addEventListener('change', async () => {
      if (window.AtlasOps?._orgScopeApplying) return;
      const sedeId = $('dim-sede')?.value;
      if (sedeId) await loadContexto(sedeId);
    });

    if ($('dim-anio') && !$('dim-anio').value) {
      $('dim-anio').value = String(new Date().getFullYear());
    }
    $('dim-anio')?.addEventListener('change', async () => {
      const sedeId = contexto?.sede?.id || $('dim-sede')?.value;
      if (sedeId) await loadContexto(sedeId);
    });
    document.addEventListener('orgscope:applied', (ev) => {
      if (ev.detail?.key !== 'dimensionamiento') return;
      const sedeId = ev.detail.sede || $('dim-sede')?.value;
      if (sedeId) loadContexto(sedeId);
    });

    const bindDimPager = (key, searchId, sizeId, prevId, nextId, renderFn) => {
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
    };
    bindDimPager('corr', 'dim-corr-search', 'dim-corr-page-size', 'dim-corr-prev', 'dim-corr-next', renderCorrectivos);
    bindDimPager('adic', 'dim-adic-search', 'dim-adic-page-size', 'dim-adic-prev', 'dim-adic-next', renderAdicionales);

    $('dim-load')?.addEventListener('click', async () => {
      const sedeId = $('dim-sede')?.value;
      if (!sedeId) {
        window.AtlasOps.showToast('Selecciona una sede.', 'error');
        return;
      }
      await loadContexto(sedeId);
    });

    $('dim-save-params')?.addEventListener('click', async () => {
      if (!canEdit) return;
      const empresaId =
        contexto?.sede?.empresa_id || Number($('dim-empresa')?.value);
      if (!empresaId) {
        window.AtlasOps.showToast('Selecciona empresa/sede primero.', 'error');
        return;
      }
      const form = $('dim-form-params');
      const body = { empresa_id: Number(empresaId) };
      new FormData(form).forEach((v, k) => {
        body[k] = v;
      });
      const { response, data } = await window.AtlasOps.api('/api/dimensionamiento/parametros', {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      if (!response.ok || !data.ok) {
        window.AtlasOps.showToast(data.error || 'No se guardaron parámetros.', 'error');
        return;
      }
      window.AtlasOps.showToast(data.message, 'success');
      fillParams(data.parametros);
      window.AtlasOps?.collapseAccordion?.($('dim-save-params')?.closest('.dim-acc'));
      if ($('dim-sede')?.value) await loadContexto($('dim-sede').value);
    });

    panel.addEventListener('submit', async (event) => {
      const form = event.target.closest('[data-eq-form]');
      if (!form) return;
      event.preventDefault();
      if (!canEdit) return;
      const id = form.dataset.eqForm;
      const article = form.closest('.dim-eq');
      const payload = readFormActividad(form);
      if (
        payload.criticidad === 'Alto' &&
        payload.alto_unico_area !== 'Sí' &&
        payload.alto_especializado !== 'Sí'
      ) {
        window.AtlasOps.showToast(
          'Si la criticidad es Alta, marque único en el área, alta complejidad, o ambas.',
          'error'
        );
        return;
      }
      const { response, data } = await window.AtlasOps.api(
        `/api/dimensionamiento/equipos/${id}`,
        { method: 'PUT', body: JSON.stringify(payload) }
      );
      if (!response.ok || !data.ok) {
        window.AtlasOps.showToast(data.error || 'No se pudo guardar.', 'error');
        return;
      }
      window.AtlasOps.showToast(data.message, 'success');
      collapseEquipo(article);
      const sedeId = contexto?.sede?.id || $('dim-sede')?.value;
      if (sedeId) await loadContexto(sedeId);
    });

    $('dim-export-csv')?.addEventListener('click', async () => {
      const sedeId = contexto?.sede?.id || $('dim-sede')?.value;
      if (!sedeId) return;
      try {
        await window.AtlasOps.downloadFile(
          `/api/dimensionamiento/sedes/${sedeId}/export.csv`,
          'dimensionamiento.csv'
        );
        window.AtlasOps.showToast('CSV exportado.', 'success');
      } catch (err) {
        window.AtlasOps.showToast(err.message, 'error');
      }
    });

    $('dim-export-xlsx')?.addEventListener('click', async () => {
      const sedeId = contexto?.sede?.id || $('dim-sede')?.value;
      if (!sedeId) return;
      try {
        await window.AtlasOps.downloadFile(
          `/api/dimensionamiento/sedes/${sedeId}/export.xlsx`,
          'dimensionamiento.xlsx'
        );
        window.AtlasOps.showToast('XLSX exportado.', 'success');
      } catch (err) {
        window.AtlasOps.showToast(err.message, 'error');
      }
    });

    async function exportInformePdf() {
      const sedeId = contexto?.sede?.id || $('dim-sede')?.value;
      if (!sedeId) {
        window.AtlasOps.showToast('Carga una sede antes de generar el informe.', 'error');
        return;
      }
      try {
        await window.AtlasOps.downloadFile(
          `/api/dimensionamiento/sedes/${sedeId}/export.pdf`,
          'informe_dimensionamiento.pdf'
        );
        window.AtlasOps.showToast('Informe PDF generado.', 'success');
      } catch (err) {
        window.AtlasOps.showToast(err.message, 'error');
      }
    }

    $('dim-export-pdf')?.addEventListener('click', exportInformePdf);
    $('dim-informe-pdf')?.addEventListener('click', exportInformePdf);

    $('dim-adicional-form')?.addEventListener('submit', submitAdicional);
    $('dim-adicional-form')?.addEventListener('input', updateAdicionalPreview);
    $('dim-adicional-lote')?.addEventListener('change', updateAdicionalPreview);
    document.querySelectorAll('[data-close-dim-adicional]').forEach((el) => {
      el.addEventListener('click', closeAdicionalModal);
    });
  }

  async function initDimensionamientoPanel() {
    bindEvents();
    setupTooltips();
    await loadMeta();
    await setupScopeSelectors();
    applyEditLocks();
    setMsg('');
  }

  window.AtlasOps = window.AtlasOps || {};
  window.AtlasOps.loadDimensionamientoPanel = initDimensionamientoPanel;
})();
