(() => {
  /*
   * Selector modal Empresa / Sede / Servicio (reutilizado por instrumentos e inventario).
   */
  const PRESETS = {
    suficiencia: {
      empresa: 'suf-empresa',
      sede: 'suf-sede',
      servicio: 'suf-servicio',
      summary: 'suf-scope-summary',
      title: 'Empresa, sede y servicio',
      emptyLabel: 'Seleccionar Empresa, Sede y Servicio',
      requireSede: true,
      requireServicio: true,
    },
    dimensionamiento: {
      empresa: 'dim-empresa',
      sede: 'dim-sede',
      summary: 'dim-scope-summary',
      title: 'Empresa y sede',
      emptyLabel: 'Seleccionar Empresa y Sede',
      requireSede: true,
      requireServicio: false,
    },
    'frecuencia-pm': {
      empresa: 'pm-empresa',
      sede: 'pm-sede',
      servicio: 'pm-servicio',
      summary: 'pm-scope-summary',
      title: 'Empresa, sede y servicio',
      emptyLabel: 'Seleccionar Empresa, Sede y Servicio',
      requireSede: true,
      requireServicio: true,
    },
    preinstalacion: {
      empresa: 'pre-empresa',
      sede: 'pre-sede',
      servicio: 'pre-servicio',
      summary: 'pre-scope-summary',
      title: 'Empresa, sede y servicio',
      emptyLabel: 'Seleccionar Empresa, Sede y Servicio',
      requireSede: true,
      requireServicio: true,
    },
    kpis: {
      empresa: 'kpi-empresa',
      summary: 'kpi-scope-summary',
      title: 'Empresa',
      emptyLabel: 'Seleccionar Empresa',
      requireSede: false,
      requireServicio: false,
    },
    inventario: {
      empresa: 'inventario-empresa',
      sede: 'inventario-sede',
      servicio: 'inventario-servicio',
      summary: 'inv-scope-summary',
      title: 'Empresa, sede y servicio',
      emptyLabel: 'Seleccionar Empresa, Sede y Servicio',
      requireSede: true,
      requireServicio: true,
    },
  };

  let activeKey = null;
  let bound = false;

  function $(id) {
    return document.getElementById(id);
  }

  function optionLabel(select, value) {
    if (!select || !value) return '';
    const opt = [...select.options].find((o) => String(o.value) === String(value));
    return (opt && opt.textContent.trim()) || '';
  }

  function canPickAnyEmpresa() {
    if (typeof window.AtlasOps?.canPickAnyEmpresa === 'function') {
      return window.AtlasOps.canPickAnyEmpresa();
    }
    const user = window.AtlasOps?.currentUser || {};
    return (
      String(user.ROLL || '').toUpperCase() === 'ADMIN' ||
      Boolean(window.AtlasOps?.can?.('view_all_empresas')) ||
      Boolean(window.AtlasOps?.can?.('admin_panel'))
    );
  }

  function empresasFromSedes(sedes) {
    const map = new Map();
    (sedes || []).forEach((s) => {
      if (!s.empresa_id) return;
      const id = Number(s.empresa_id);
      if (map.has(id)) return;
      map.set(id, {
        id,
        ID_Empresa: s.ID_Empresa || `Empresa ${id}`,
        ID_NIT: s.ID_NIT || '',
      });
    });
    return [...map.values()];
  }

  function fillSelect(select, items, { placeholder, value, getValue, getLabel, locked, autoSelectSingle = false }) {
    if (!select) return;
    const list = items || [];
    const prev = value != null && value !== '' ? String(value) : select.value;
    select.innerHTML = '';
    const ph = document.createElement('option');
    ph.value = '';
    ph.textContent = placeholder;
    select.appendChild(ph);
    list.forEach((item) => {
      const opt = document.createElement('option');
      opt.value = getValue(item);
      opt.textContent = getLabel(item);
      select.appendChild(opt);
    });
    if (prev && [...select.options].some((o) => o.value === prev)) select.value = prev;
    else if (autoSelectSingle && list.length === 1) select.value = String(getValue(list[0]));
    if (locked) {
      select.disabled = list.length <= 1 && !canPickAnyEmpresa() && Boolean(select.value);
    } else {
      select.disabled = false;
    }
  }

  function assignedSedeIds() {
    return (window.AtlasOps?.currentUser?.assigned_sede_ids || []).map(Number);
  }

  function sedesForEmpresa(empresaId) {
    if (!empresaId) return [];
    const sedes = window.AtlasOps?.getSedesCache?.() || [];
    let list = sedes.filter((s) => Number(s.empresa_id) === Number(empresaId));
    const assigned = assignedSedeIds();
    if (!canPickAnyEmpresa() && assigned.length) {
      const scoped = list.filter((s) => assigned.includes(Number(s.id)));
      if (scoped.length) list = scoped;
    }
    return list;
  }

  function serviciosForSede(sedeId) {
    const sede = (window.AtlasOps?.getSedesCache?.() || []).find(
      (s) => String(s.id) === String(sedeId)
    );
    return sede?.servicios || [];
  }

  function refreshSummary(key) {
    const cfg = PRESETS[key];
    if (!cfg) return;
    const summary = $(cfg.summary);
    if (!summary) return;
    const parts = [];
    const emp = $(cfg.empresa);
    const sede = cfg.sede ? $(cfg.sede) : null;
    const srv = cfg.servicio ? $(cfg.servicio) : null;
    const empLabel = optionLabel(emp, emp?.value);
    const sedeLabel = optionLabel(sede, sede?.value);
    const srvLabel = optionLabel(srv, srv?.value);
    if (empLabel) parts.push(empLabel);
    if (sedeLabel) parts.push(sedeLabel);
    if (srvLabel) parts.push(srvLabel);
    summary.textContent = parts.length
      ? parts.join(' · ')
      : cfg.emptyLabel || 'Seleccionar para continuar';
  }

  function refreshAllSummaries() {
    Object.keys(PRESETS).forEach(refreshSummary);
  }

  async function loadEmpresas() {
    await window.AtlasOps?.ensureSedes?.();
    let empresas = empresasFromSedes(window.AtlasOps?.getSedesCache?.() || []);
    if (canPickAnyEmpresa()) {
      try {
        const { data } = await window.AtlasOps.api('/api/empresas');
        if (data?.ok && data.empresas?.length) empresas = data.empresas;
      } catch {
        /* usa sedes */
      }
    }
    const userEmp = window.AtlasOps?.currentUser?.empresa_id;
    if (!canPickAnyEmpresa() && userEmp) {
      const scoped = empresas.filter((e) => Number(e.id) === Number(userEmp));
      if (scoped.length) empresas = scoped;
    }
    return empresas;
  }

  function fillModalFromCfg(cfg) {
    const empSel = $('org-scope-empresa');
    const sedeSel = $('org-scope-sede');
    const srvSel = $('org-scope-servicio');
    const sedeWrap = $('org-scope-sede-wrap');
    const srvWrap = $('org-scope-servicio-wrap');
    if (sedeWrap) sedeWrap.hidden = !cfg.sede;
    if (srvWrap) srvWrap.hidden = !cfg.servicio;

    const sourceEmp = $(cfg.empresa);
    fillSelect(empSel, window._orgScopeEmpresas || [], {
      placeholder: 'Seleccionar Empresa',
      value: sourceEmp?.value || '',
      getValue: (e) => e.id,
      getLabel: (e) => (e.ID_NIT ? `${e.ID_Empresa} · ${e.ID_NIT}` : e.ID_Empresa || `Empresa ${e.id}`),
      locked: true,
      autoSelectSingle: true,
    });
    if (sourceEmp?.value) empSel.value = String(sourceEmp.value);

    if (cfg.sede) {
      const sedes = sedesForEmpresa(empSel.value);
      fillSelect(sedeSel, sedes, {
        placeholder: 'Seleccionar Sede',
        value: $(cfg.sede)?.value || '',
        getValue: (s) => s.id,
        getLabel: (s) => (s.ID_sede ? `${s.name_sede} (${s.ID_sede})` : s.name_sede),
        autoSelectSingle: true,
      });
    }
    if (cfg.servicio) {
      const list = serviciosForSede(sedeSel?.value);
      fillSelect(srvSel, list, {
        placeholder: 'Seleccionar Servicio',
        value: $(cfg.servicio)?.value || '',
        getValue: (s) => s.id,
        getLabel: (s) =>
          s.ID_servicio ? `${s.ID_servicio} · ${s.name_servicio}` : s.name_servicio,
        autoSelectSingle: true,
      });
    }
  }

  function setSelectValue(select, value) {
    if (!select) return false;
    if (value == null || value === '') return false;
    const str = String(value);
    if (![...select.options].some((o) => o.value === str)) return false;
    if (select.value !== str) select.value = str;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }

  function applyToHidden(cfg) {
    const empVal = $('org-scope-empresa')?.value || '';
    const sedeVal = $('org-scope-sede')?.value || '';
    const srvVal = $('org-scope-servicio')?.value || '';
    const emp = $(cfg.empresa);
    const sede = cfg.sede ? $(cfg.sede) : null;
    const srv = cfg.servicio ? $(cfg.servicio) : null;

    window.AtlasOps = window.AtlasOps || {};
    window.AtlasOps._orgScopeApplying = true;
    try {
      if (emp && empVal) {
        const str = String(empVal);
        if ([...emp.options].some((o) => o.value === str)) emp.value = str;
      }
      if (sede) {
        fillSelect(sede, sedesForEmpresa(empVal), {
          placeholder: 'Selecciona sede',
          value: sedeVal,
          getValue: (s) => s.id,
          getLabel: (s) => (s.ID_sede ? `${s.name_sede} (${s.ID_sede})` : s.name_sede),
        });
      }
      if (srv) {
        fillSelect(srv, serviciosForSede(sedeVal || sede?.value), {
          placeholder: 'Selecciona servicio',
          value: srvVal,
          getValue: (s) => s.id,
          getLabel: (s) =>
            s.ID_servicio ? `${s.ID_servicio} · ${s.name_servicio}` : s.name_servicio,
        });
      }
    } finally {
      window.AtlasOps._orgScopeApplying = false;
    }

    refreshSummary(activeKey);
    const trigger = srv || sede || emp;
    trigger?.dispatchEvent(new Event('change', { bubbles: true }));
    document.dispatchEvent(
      new CustomEvent('orgscope:applied', {
        bubbles: true,
        detail: {
          key: activeKey,
          empresa: empVal,
          sede: sedeVal,
          servicio: srvVal,
        },
      })
    );
  }

  async function applyOrgScope(key, ids = {}) {
    const cfg = PRESETS[key];
    if (!cfg) return false;
    const empresaId = ids.empresaId ?? ids.empresa ?? '';
    const sedeId = ids.sedeId ?? ids.sede ?? '';
    const servicioId = ids.servicioId ?? ids.servicio ?? '';
    if (!empresaId && !sedeId && !servicioId) return false;
    await window.AtlasOps?.ensureSedes?.();
    const empresas = await loadEmpresas();
    const emp = $(cfg.empresa);
    const sede = cfg.sede ? $(cfg.sede) : null;
    const srv = cfg.servicio ? $(cfg.servicio) : null;
    window.AtlasOps = window.AtlasOps || {};
    window.AtlasOps._orgScopeApplying = true;
    try {
      if (emp) {
        fillSelect(emp, empresas, {
          placeholder: 'Selecciona empresa',
          value: empresaId,
          getValue: (e) => e.id,
          getLabel: (e) => (e.ID_NIT ? `${e.ID_Empresa} (${e.ID_NIT})` : e.ID_Empresa || `Empresa ${e.id}`),
        });
      }
      if (sede) {
        fillSelect(sede, sedesForEmpresa(empresaId || emp?.value), {
          placeholder: 'Selecciona sede',
          value: sedeId,
          getValue: (s) => s.id,
          getLabel: (s) => (s.ID_sede ? `${s.name_sede} (${s.ID_sede})` : s.name_sede),
        });
      }
      if (srv) {
        fillSelect(srv, serviciosForSede(sedeId || sede?.value), {
          placeholder: 'Selecciona servicio',
          value: servicioId,
          getValue: (s) => s.id,
          getLabel: (s) =>
            s.ID_servicio ? `${s.ID_servicio} · ${s.name_servicio}` : s.name_servicio,
        });
      }
    } finally {
      window.AtlasOps._orgScopeApplying = false;
    }
    refreshSummary(key);
    document.dispatchEvent(
      new CustomEvent('orgscope:applied', {
        bubbles: true,
        detail: {
          key,
          empresa: String(empresaId || emp?.value || ''),
          sede: String(sedeId || sede?.value || ''),
          servicio: String(servicioId || srv?.value || ''),
        },
      })
    );
    return true;
  }

  function closeModal() {
    const modal = $('org-scope-modal');
    if (modal) modal.hidden = true;
    activeKey = null;
  }

  async function openModal(key) {
    const cfg = PRESETS[key];
    if (!cfg) return;
    activeKey = key;
    window._orgScopeEmpresas = await loadEmpresas();
    const title = $('org-scope-title');
    if (title) {
      title.textContent = cfg.servicio
        ? 'Selecciona Empresa, Sede y Servicio'
        : cfg.sede
          ? 'Selecciona Empresa y Sede'
          : 'Selecciona Empresa';
    }
    fillModalFromCfg(cfg);
    const modal = $('org-scope-modal');
    if (modal) modal.hidden = false;
    $('org-scope-empresa')?.focus();
  }

  function bindOnce() {
    if (bound) return;
    bound = true;

    document.addEventListener('click', (event) => {
      const opener = event.target.closest('[data-org-open]');
      if (opener) {
        event.preventDefault();
        openModal(opener.getAttribute('data-org-open'));
        return;
      }
      if (event.target.closest('[data-close-org-scope]')) {
        closeModal();
      }
    });

    $('org-scope-empresa')?.addEventListener('change', () => {
      const cfg = PRESETS[activeKey];
      if (!cfg) return;
      if (cfg.sede) {
        fillSelect($('org-scope-sede'), sedesForEmpresa($('org-scope-empresa').value), {
          placeholder: 'Seleccionar Sede',
          getValue: (s) => s.id,
          getLabel: (s) => (s.ID_sede ? `${s.name_sede} (${s.ID_sede})` : s.name_sede),
          autoSelectSingle: true,
        });
      }
      if (cfg.servicio) {
        fillSelect($('org-scope-servicio'), [], {
          placeholder: 'Seleccionar Servicio',
          getValue: (s) => s.id,
          getLabel: (s) => s.name_servicio,
        });
      }
    });

    $('org-scope-sede')?.addEventListener('change', () => {
      const cfg = PRESETS[activeKey];
      if (!cfg?.servicio) return;
      fillSelect($('org-scope-servicio'), serviciosForSede($('org-scope-sede').value), {
        placeholder: 'Seleccionar Servicio',
        getValue: (s) => s.id,
        getLabel: (s) =>
          s.ID_servicio ? `${s.ID_servicio} · ${s.name_servicio}` : s.name_servicio,
        autoSelectSingle: true,
      });
    });

    $('org-scope-continue')?.addEventListener('click', () => {
      const cfg = PRESETS[activeKey];
      if (!cfg) return;
      const empVal = $('org-scope-empresa')?.value;
      const sedeVal = $('org-scope-sede')?.value;
      const srvVal = $('org-scope-servicio')?.value;
      if (!empVal) {
        window.AtlasOps?.showToast?.('Selecciona la empresa.', 'error');
        return;
      }
      if (cfg.requireSede && !sedeVal) {
        window.AtlasOps?.showToast?.('Selecciona la sede.', 'error');
        return;
      }
      if (cfg.requireServicio && !srvVal) {
        window.AtlasOps?.showToast?.('Selecciona el servicio.', 'error');
        return;
      }
      applyToHidden(cfg);
      closeModal();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && activeKey && !$('org-scope-modal')?.hidden) {
        closeModal();
      }
    });

    Object.values(PRESETS).forEach((cfg) => {
      [cfg.empresa, cfg.sede, cfg.servicio].filter(Boolean).forEach((id) => {
        $(id)?.addEventListener('change', () => {
          const key = Object.keys(PRESETS).find((k) => PRESETS[k] === cfg);
          if (key) refreshSummary(key);
        });
      });
    });
  }

  window.AtlasOps = Object.assign(window.AtlasOps || {}, {
    refreshOrgScopeSummaries: refreshAllSummaries,
    openOrgScope: openModal,
    applyOrgScope,
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindOnce);
  } else {
    bindOnce();
  }
})();
