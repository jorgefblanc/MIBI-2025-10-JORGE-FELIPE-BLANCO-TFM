/**
 * Guía rápida contextual. Carga /api/help/<modulo> y registra help_viewed.
 */
(() => {
  const CACHE_KEY = 'sigtb.help.cache.v2';
  const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
  const IMAGE_RE = /^[A-Za-z0-9._-]{1,120}$/;
  const EXAMPLE_RE =
    /^\/api\/help\/(suficiencia|dimensionamiento|frecuencia-pm|preinstalacion|kpis)\/examples\/(plantilla\.xlsx|ejemplo\.pdf)$/;
  const FALLBACK_IMG = '/img/help/_fallback.svg';

  const VIEW_PERMS = {
    suficiencia: [
      'view_suficiencia',
      'view_help_suficiencia',
      'edit_suficiencia_asistencial',
      'request_suficiencia_update',
    ],
    dimensionamiento: ['view_dimensionamiento', 'view_help_dimensionamiento'],
    'frecuencia-pm': ['view_frecuencia_pm', 'view_help_frecuencia_pm'],
    preinstalacion: ['view_preinstalacion', 'view_help_preinstalacion'],
    kpis: ['view_kpis', 'view_respaldo', 'view_help_kpis'],
  };

  const CONTEXT_IDS = {
    suficiencia: { empresa: 'suf-empresa', sede: 'suf-sede', servicio: 'suf-servicio' },
    dimensionamiento: { empresa: 'dim-empresa', sede: 'dim-sede' },
    'frecuencia-pm': { empresa: 'pm-empresa', sede: 'pm-sede', servicio: 'pm-servicio' },
    preinstalacion: { empresa: 'pre-empresa', sede: 'pre-sede', servicio: 'pre-servicio' },
    kpis: { empresa: 'kpi-empresa' },
  };

  const COPY = {
    es: {
      loading: 'Cargando…',
      title: 'Guía rápida',
      what: 'Qué es esto',
      canDo: 'Qué puedes hacer aquí',
      steps: 'Cómo empezar',
      errors: 'Si te pasa esto',
      examples: 'Ejemplos para practicar',
      tips: 'Consejos cortos',
      contact: '¿Falta algo?',
      tech: 'Detalles técnicos',
      techHint: 'Solo si te lo pide soporte o vas a cargar un archivo grande.',
      preview: 'Vista del informe de ejemplo',
      closePreview: 'Ocultar ejemplo',
      forbidden: 'No tienes permiso para abrir esta guía.',
      fail: 'No se pudo cargar la guía. Recarga la página; si sigue igual, pide al ADMIN que reinicie el servidor.',
    },
    en: {
      loading: 'Loading…',
      title: 'Quick guide',
      what: 'What this is',
      canDo: 'What you can do here',
      steps: 'How to start',
      errors: 'If this happens',
      examples: 'Practice examples',
      tips: 'Short tips',
      contact: 'Missing something?',
      tech: 'Technical details',
      techHint: 'Only if support asked, or you are uploading a large file.',
      preview: 'Sample report preview',
      closePreview: 'Hide example',
      forbidden: 'You do not have permission to open this guide.',
      fail: 'Could not load the guide.',
    },
  };

  const FOCUSABLE =
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

  let lastFocus = null;
  let activeModule = null;

  const els = {
    modal: () => document.getElementById('help-modal'),
    title: () => document.getElementById('help-modal-title'),
    overview: () => document.getElementById('help-modal-overview'),
    body: () => document.getElementById('help-modal-body'),
    close: () => document.getElementById('help-modal-close'),
    dialog: () => document.getElementById('help-modal-dialog'),
  };

  function t() {
    return COPY[currentLang()] || COPY.es;
  }

  function can(name) {
    return Boolean(window.AtlasOps?.can?.(name));
  }

  function canViewModule(moduleName) {
    return (VIEW_PERMS[moduleName] || []).some((p) => can(p));
  }

  function isTechnicalUser() {
    const roll = String(window.AtlasOps?.currentUser?.ROLL || '').toUpperCase();
    return roll === 'ADMIN' || roll === 'OPERATIVO';
  }

  function currentLang() {
    const htmlLang = String(document.documentElement.lang || 'es')
      .slice(0, 2)
      .toLowerCase();
    return htmlLang === 'en' ? 'en' : 'es';
  }

  function readCache() {
    try {
      return JSON.parse(localStorage.getItem(CACHE_KEY) || '{}') || {};
    } catch {
      return {};
    }
  }

  function writeCache(store) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(store));
    } catch {
      /* cuota */
    }
  }

  function cacheGet(moduleName, lang) {
    const entry = readCache()[`${moduleName}:${lang}`];
    if (!entry || !entry.data) return null;
    return entry;
  }

  function cacheSet(moduleName, lang, data, etag) {
    const store = readCache();
    store[`${moduleName}:${lang}`] = {
      version: data.version,
      etag: etag || '',
      fetchedAt: Date.now(),
      data,
    };
    writeCache(store);
  }

  function selectInt(id) {
    if (!id) return null;
    const n = Number(document.getElementById(id)?.value || 0);
    return Number.isFinite(n) && n > 0 ? n : null;
  }

  function contextPayload(moduleName) {
    const ids = CONTEXT_IDS[moduleName] || {};
    return {
      empresa_id: selectInt(ids.empresa),
      sede_id: selectInt(ids.sede),
      servicio_id: selectInt(ids.servicio),
    };
  }

  function setText(node, text) {
    if (node) node.textContent = text == null ? '' : String(text);
  }

  function heading(tag, text) {
    const h = document.createElement(tag);
    h.textContent = text;
    return h;
  }

  function list(items, ordered) {
    const el = document.createElement(ordered ? 'ol' : 'ul');
    el.className = ordered ? 'help-modal__steps' : 'help-modal__list';
    items.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = item;
      el.appendChild(li);
    });
    return el;
  }

  function article(title) {
    const art = document.createElement('article');
    art.className = 'help-modal__section';
    art.appendChild(heading('h3', title));
    return art;
  }

  function renderImage(moduleName, filename, alt) {
    const figure = document.createElement('figure');
    figure.className = 'help-modal__figure';
    const img = document.createElement('img');
    const src = IMAGE_RE.test(filename || '') ? `/img/help/${moduleName}/${filename}` : '';
    img.alt = alt || '';
    img.loading = 'lazy';
    if (!src) {
      img.src = FALLBACK_IMG;
      img.alt = alt ? `${alt} (imagen no disponible)` : 'Imagen de ayuda no disponible';
    } else {
      img.src = src;
      img.addEventListener('error', () => {
        if (img.dataset.fallback === '1') return;
        img.dataset.fallback = '1';
        img.src = FALLBACK_IMG;
        img.alt = alt ? `${alt} (imagen no disponible)` : 'Imagen de ayuda no disponible';
      });
    }
    figure.appendChild(img);
    return figure;
  }

  function renderHelp(help) {
    const labels = t();
    const title = els.title();
    const overview = els.overview();
    const body = els.body();
    if (!title || !overview || !body) return;
    setText(title, help.title || labels.title);
    setText(overview, help.what || '');
    body.replaceChildren();

    if ((help.can_do || []).length) {
      const art = article(labels.canDo);
      art.appendChild(list(help.can_do, false));
      body.appendChild(art);
    }

    if ((help.steps || []).length) {
      const art = article(labels.steps);
      art.appendChild(list(help.steps, true));
      if ((help.images || [])[0]) {
        art.appendChild(renderImage(help.module, help.images[0], help.steps[0] || help.title));
      }
      body.appendChild(art);
    }

    if ((help.common_errors || []).length) {
      const art = article(labels.errors);
      const dl = document.createElement('dl');
      dl.className = 'help-modal__errors';
      help.common_errors.forEach((row) => {
        const dt = document.createElement('dt');
        dt.textContent = row.error;
        const dd = document.createElement('dd');
        dd.textContent = row.fix;
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      art.appendChild(dl);
      if ((help.images || [])[1]) {
        art.appendChild(renderImage(help.module, help.images[1], labels.errors));
      }
      body.appendChild(art);
    }

    if ((help.examples || []).length) {
      const art = article(labels.examples);
      const actions = document.createElement('div');
      actions.className = 'help-modal__example-actions';
      help.examples.forEach((ex) => {
        if (!EXAMPLE_RE.test(ex.href || '')) return;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-primary';
        btn.textContent = ex.label || ex.type;
        btn.addEventListener('click', () => openExample(ex, art));
        actions.appendChild(btn);
      });
      art.appendChild(actions);
      const preview = document.createElement('div');
      preview.className = 'help-modal__preview';
      preview.hidden = true;
      const cap = document.createElement('p');
      cap.className = 'help-modal__preview-label';
      cap.textContent = labels.preview;
      const frame = document.createElement('iframe');
      frame.title = labels.preview;
      frame.className = 'help-modal__iframe';
      const hide = document.createElement('button');
      hide.type = 'button';
      hide.className = 'btn btn-ghost';
      hide.textContent = labels.closePreview;
      hide.addEventListener('click', () => {
        preview.hidden = true;
        frame.src = 'about:blank';
      });
      preview.append(cap, frame, hide);
      art.appendChild(preview);
      art._helpPreview = { preview, frame };
      body.appendChild(art);
    }

    if ((help.tips || []).length) {
      const art = article(labels.tips);
      art.appendChild(list(help.tips, false));
      body.appendChild(art);
    }

    if (help.contact) {
      const art = article(labels.contact);
      const p = document.createElement('p');
      p.className = 'help-modal__prose';
      p.textContent = help.contact;
      art.appendChild(p);
      body.appendChild(art);
    }

    if (help.tech_notes && isTechnicalUser()) {
      const details = document.createElement('details');
      details.className = 'help-modal__tech';
      const summary = document.createElement('summary');
      summary.textContent = labels.tech;
      const hint = document.createElement('p');
      hint.className = 'help-modal__tech-hint';
      hint.textContent = labels.techHint;
      const note = document.createElement('p');
      note.textContent = help.tech_notes;
      details.append(summary, hint, note);
      body.appendChild(details);
    }
  }

  async function openExample(ex, art) {
    const href = ex.href;
    if (!EXAMPLE_RE.test(href)) return;
    const isPdf = href.endsWith('.pdf');
    if (isPdf && art?._helpPreview) {
      art._helpPreview.frame.src = href;
      art._helpPreview.preview.hidden = false;
      art._helpPreview.frame.focus?.();
      return;
    }
    const name = href.split('/').pop() || 'ejemplo.xlsx';
    try {
      if (window.AtlasOps?.downloadFile) {
        await window.AtlasOps.downloadFile(href, name);
      } else {
        window.location.assign(href);
      }
    } catch (err) {
      window.AtlasOps?.showToast?.(err.message || t().fail, 'error');
    }
  }

  function focusables() {
    const dialog = els.dialog();
    if (!dialog) return [];
    return Array.from(dialog.querySelectorAll(FOCUSABLE)).filter(
      (n) => !n.hasAttribute('hidden') && n.getClientRects().length > 0
    );
  }

  function trapFocus(event) {
    if (event.key !== 'Tab') return;
    const nodes = focusables();
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function onKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeHelp();
      return;
    }
    trapFocus(event);
  }

  function closeHelp() {
    const modal = els.modal();
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.removeEventListener('keydown', onKeydown);
    activeModule = null;
    const frame = modal.querySelector('.help-modal__iframe');
    if (frame) frame.src = 'about:blank';
    if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
    lastFocus = null;
  }

  function openModalShell() {
    const modal = els.modal();
    if (!modal) return;
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.addEventListener('keydown', onKeydown);
    (els.close() || els.dialog())?.focus?.();
  }

  async function fetchHelp(moduleName, lang) {
    const cached = cacheGet(moduleName, lang);
    const headers = {};
    if (cached?.etag) headers['If-None-Match'] = cached.etag;
    const ctx = contextPayload(moduleName);
    const qs = new URLSearchParams({
      lang,
      viewed: '1',
    });
    if (ctx.empresa_id) qs.set('empresa_id', String(ctx.empresa_id));
    if (ctx.sede_id) qs.set('sede_id', String(ctx.sede_id));
    if (ctx.servicio_id) qs.set('servicio_id', String(ctx.servicio_id));
    const { response, data } = await window.AtlasOps.api(
      `/api/help/${encodeURIComponent(moduleName)}?${qs.toString()}`,
      { headers }
    );
    if (response.status === 304 && cached?.data) return cached.data;
    if (response.status === 403) {
      const err = new Error('forbidden');
      err.code = 403;
      throw err;
    }
    if (!response.ok || !data || data.ok === false) {
      if (cached?.data) return cached.data;
      throw new Error(data?.error || t().fail);
    }
    cacheSet(moduleName, lang, data, response.headers.get('ETag') || '');
    return data;
  }

  async function openHelp(moduleName) {
    if (!moduleName || !canViewModule(moduleName)) {
      window.AtlasOps?.showToast?.(t().forbidden, 'error');
      return;
    }
    activeModule = moduleName;
    openModalShell();
    setText(els.title(), t().title);
    setText(els.overview(), t().loading);
    els.body()?.replaceChildren();
    try {
      const help = await fetchHelp(moduleName, currentLang());
      if (activeModule !== moduleName) return;
      renderHelp(help);
    } catch (err) {
      if (activeModule !== moduleName) return;
      setText(els.overview(), err.code === 403 ? t().forbidden : err.message || t().fail);
    }
  }

  function onPanelChange(panelId) {
    const modal = els.modal();
    if (!modal || modal.hidden) return;
    if (VIEW_PERMS[panelId]) {
      if (panelId !== activeModule) openHelp(panelId);
      return;
    }
    closeHelp();
  }

  function refreshButtons() {
    document.querySelectorAll('[data-help-module]').forEach((btn) => {
      const allowed = canViewModule(btn.getAttribute('data-help-module'));
      btn.hidden = !allowed;
      btn.disabled = !allowed;
    });
  }

  function bind() {
    document.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-help-module]');
      if (btn) {
        event.preventDefault();
        openHelp(btn.getAttribute('data-help-module'));
        return;
      }
      if (event.target.closest('[data-close-help-modal]')) {
        event.preventDefault();
        closeHelp();
      }
    });
  }

  window.SIGTBHelp = { openHelp, closeHelp, refreshButtons, onPanelChange };
  window.AtlasOps = Object.assign(window.AtlasOps || {}, {
    openHelp,
    refreshHelpButtons: refreshButtons,
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      bind();
      refreshButtons();
    });
  } else {
    bind();
    refreshButtons();
  }
})();
