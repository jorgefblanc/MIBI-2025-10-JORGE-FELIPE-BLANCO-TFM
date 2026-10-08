(() => {
  /* Núcleo del cliente: sesión, menú, inventario, RBAC, bandeja y arranque. */

  const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const LETTERS_ONLY_REGEX = /^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s]+$/;

  /* Contraseñas recordadas (localStorage). La sesión autenticada vive en la cookie del servidor. */
  const SAVED_LOGINS_KEY = 'sigtb_saved_logins';
  const LAST_LOGIN_KEY = 'sigtb_last_login';
  const LOGOUT_FLASH_KEY = 'sigtb_logout_flash';

  /** Codifica texto para guardarlo de forma ofuscada (no es cifrado fuerte). */
  function encodeSecret(value) {
    try {
      return btoa(unescape(encodeURIComponent(String(value ?? ''))));
    } catch {
      return '';
    }
  }

  function decodeSecret(value) {
    try {
      return decodeURIComponent(escape(atob(String(value ?? ''))));
    } catch {
      return '';
    }
  }

  function readSavedLogins() {
    try {
      const raw = localStorage.getItem(SAVED_LOGINS_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch {
      return {};
    }
  }

  function writeSavedLogins(map) {
    try {
      localStorage.setItem(SAVED_LOGINS_KEY, JSON.stringify(map || {}));
    } catch {
      /* quota / private mode */
    }
  }

  function getSavedPassword(email) {
    const key = normalizeEmail(email);
    if (!key) return '';
    return decodeSecret(readSavedLogins()[key] || '');
  }

  function savePasswordForUser(email, password) {
    const key = normalizeEmail(email);
    if (!key || !password) return;
    const map = readSavedLogins();
    map[key] = encodeSecret(password);
    writeSavedLogins(map);
    try {
      localStorage.setItem(LAST_LOGIN_KEY, key);
    } catch {
      /* ignore */
    }
  }

  function forgetPasswordForUser(email) {
    const key = normalizeEmail(email);
    if (!key) return;
    const map = readSavedLogins();
    if (!(key in map)) return;
    delete map[key];
    writeSavedLogins(map);
  }

  /* Referencias DOM y estado en memoria (sedes, inventario, usuario actual). */
  const els = {
    page: document.querySelector('.page'),
    loginForm: document.getElementById('login-form'),
    loginEmail: document.getElementById('login-email'),
    loginPassword: document.getElementById('login-password'),
    loginRemember: document.getElementById('login-remember'),
    loginSection: document.getElementById('login-section'),
    welcomeSection: document.getElementById('welcome-section'),
    openRegister: document.getElementById('open-register'),
    openForgot: document.getElementById('open-forgot'),
    logoutBtn: document.getElementById('logout-btn'),
    modal: document.getElementById('register-modal'),
    forgotModal: document.getElementById('forgot-modal'),
    forgotForm: document.getElementById('forgot-form'),
    forgotEmail: document.getElementById('forgot-email'),
    resetModal: document.getElementById('reset-modal'),
    resetForm: document.getElementById('reset-form'),
    resetToken: document.getElementById('reset-token'),
    resetPassword: document.getElementById('reset-password'),
    resetPassword2: document.getElementById('reset-password2'),
    registerForm: document.getElementById('register-form'),
    regEmail: document.getElementById('reg-email'),
    regPassword: document.getElementById('reg-password'),
    regName: document.getElementById('reg-name'),
    regLastName: document.getElementById('reg-lastname'),
    regRoll: document.getElementById('reg-roll'),
    regEmpresa: document.getElementById('reg-empresa'),
    regEmpresaSugerida: document.getElementById('reg-empresa-sugerida'),
    regEmpresaSugeridaWrap: document.getElementById('reg-empresa-sugerida-wrap'),
    regNitSugerido: document.getElementById('reg-nit-sugerido'),
    regNitSugeridoWrap: document.getElementById('reg-nit-sugerido-wrap'),
    regEmpresaCargarWrap: document.getElementById('reg-empresa-cargar-wrap'),
    regEmpresaCargar: document.getElementById('reg-empresa-cargar'),
    regEmpresaCargarHint: document.getElementById('reg-empresa-cargar-hint'),
    toastRoot: document.getElementById('toast-root'),
    dashboard: document.getElementById('dashboard'),
    dashWelcome: document.getElementById('dash-welcome'),
    dashDatetime: document.getElementById('dash-datetime'),
    dashEmail: document.getElementById('dash-email'),
    dashEmpresa: document.getElementById('dash-empresa'),
    dashPending: document.getElementById('dash-pending'),
    dashPendingCard: document.getElementById('dash-pending-card'),
    dashPendingTitle: document.getElementById('dash-pending-title'),
    dashPendingCopy: document.getElementById('dash-pending-copy'),
    dashMain: document.getElementById('dash-main'),
    dashNav: document.getElementById('dash-nav'),
    dashNavToggle: document.getElementById('dash-nav-toggle'),
    opsNavOverlay: document.getElementById('ops-nav-overlay'),
    dashInbox: document.getElementById('dash-inbox'),
    dashInboxBadge: document.getElementById('dash-inbox-badge'),
    dashReporteFallos: document.getElementById('dash-reporte-fallos'),
    dashSettings: document.getElementById('dash-settings'),
    dashLogout: document.getElementById('dash-logout'),
    perfilModal: document.getElementById('perfil-modal'),
    perfilForm: document.getElementById('perfil-form'),
    perfilName: document.getElementById('perfil-name'),
    perfilLastName: document.getElementById('perfil-lastname'),
    perfilEmail: document.getElementById('perfil-email'),
    perfilTelefono: document.getElementById('perfil-telefono'),
    perfilPassword: document.getElementById('perfil-password'),
    perfilPassword2: document.getElementById('perfil-password2'),
    perfilMsg: document.getElementById('perfil-msg'),
    perfilAvisoEstado: document.getElementById('perfil-aviso-estado'),
    perfilAvisoCheck: document.getElementById('perfil-aviso-check'),
    perfilAvisoCheckWrap: document.getElementById('perfil-aviso-check-wrap'),
    regAviso: document.getElementById('reg-aviso'),
    panelBandeja: document.getElementById('panel-bandeja'),
    mailList: document.getElementById('mail-list'),
    mailEmpty: document.getElementById('mail-empty'),
    mailMessage: document.getElementById('mail-message'),
    mailMsgType: document.getElementById('mail-msg-type'),
    mailMsgSubject: document.getElementById('mail-msg-subject'),
    mailMsgFrom: document.getElementById('mail-msg-from'),
    mailMsgDate: document.getElementById('mail-msg-date'),
    mailMsgEstado: document.getElementById('mail-msg-estado'),
    mailMsgBody: document.getElementById('mail-msg-body'),
    mailMsgActions: document.getElementById('mail-msg-actions'),
    mailBack: document.getElementById('mail-back'),
    mailRefresh: document.getElementById('mail-refresh'),
    mailFolderNotif: document.getElementById('mail-folder-notif'),
    mailFolderCompose: document.getElementById('mail-folder-compose'),
    mailBadgeInbox: document.getElementById('mail-badge-inbox'),
    mailFilterTipo: document.getElementById('mail-filter-tipo'),
    mailFilterTramite: document.getElementById('mail-filter-tramite'),
    mailFilterLimit: document.getElementById('mail-filter-limit'),
    mailFilterCounts: document.getElementById('mail-filter-counts'),
    onlineDock: document.getElementById('online-dock'),
    onlineDockToggle: document.getElementById('online-dock-toggle'),
    onlineDockPanel: document.getElementById('online-dock-panel'),
    onlineDockCount: document.getElementById('online-dock-count'),
    onlineDockList: document.getElementById('online-dock-list'),
    inventarioPager: document.getElementById('inventario-pager'),
    inventarioPageLabel: document.getElementById('inventario-page-label'),
    inventarioPageSize: document.getElementById('inventario-page-size'),
    inventarioPrev: document.getElementById('inventario-prev'),
    inventarioNext: document.getElementById('inventario-next'),
    mailBadgeNotif: document.getElementById('mail-badge-notif'),
    mailBadgeSol: document.getElementById('mail-badge-sol'),
    mailViewTitle: document.getElementById('mail-view-title'),
    mailViewEyebrow: document.getElementById('mail-view-eyebrow'),
    notifEmpresaForm: document.getElementById('notif-empresa-form'),
    notifId: document.getElementById('notif-id'),
    notifUsuarioId: document.getElementById('notif-usuario-id'),
    notifRazon: document.getElementById('notif-razon'),
    notifNit: document.getElementById('notif-nit'),
    notifSedesBuilder: document.getElementById('notif-sedes-builder'),
    notifAddSede: document.getElementById('notif-add-sede'),
    notifJobForm: document.getElementById('notif-job-form'),
    notifJobId: document.getElementById('notif-job-id'),
    notifJobUserId: document.getElementById('notif-job-user-id'),
    notifJobSelect: document.getElementById('notif-job-select'),
    panelSedes: document.getElementById('panel-sedes'),
    panelInventario: document.getElementById('panel-inventario'),
    panelEmpresas: document.getElementById('panel-empresas'),
    panelDireccion: document.getElementById('panel-direccion'),
    panelUsuarios: document.getElementById('panel-usuarios'),
    panelRbac: document.getElementById('panel-rbac'),
    solicitudForm: document.getElementById('solicitud-form'),
    solicitudSede: document.getElementById('solicitud-sede'),
    rbacForbidden: document.getElementById('rbac-forbidden'),
    rbacContent: document.getElementById('rbac-content'),
    rbacRolesList: document.getElementById('rbac-roles-list'),
    rbacPermsList: document.getElementById('rbac-perms-list'),
    rbacPermsEmpty: document.getElementById('rbac-perms-empty'),
    rbacPermsTitle: document.getElementById('rbac-perms-title'),
    rbacPermsHint: document.getElementById('rbac-perms-hint'),
    rbacRoleForm: document.getElementById('rbac-role-form'),
    rbacRoleName: document.getElementById('rbac-role-name'),
    rbacSaveMatrix: document.getElementById('rbac-save-matrix'),
    rbacExportCsv: document.getElementById('rbac-export-csv'),
    rbacExportXlsx: document.getElementById('rbac-export-xlsx'),
    backupCreateBtn: document.getElementById('backup-create-btn'),
    backupTableBody: document.getElementById('backup-table-body'),
    backupPaths: document.getElementById('backup-paths'),
    backupHint: document.getElementById('backup-hint'),
    sedesList: document.getElementById('sedes-list'),
    sedesDetail: document.getElementById('sedes-detail'),
    inventarioEmpresaSelect: document.getElementById('inventario-empresa'),
    inventarioSedeSelect: document.getElementById('inventario-sede'),
    inventarioServicioSelect: document.getElementById('inventario-servicio'),
    inventarioSearch: document.getElementById('inventario-search'),
    inventarioSearchHint: document.getElementById('inventario-search-hint'),
    inventarioTableBody: document.getElementById('inventario-body'),
    inventarioFile: document.getElementById('inventario-file'),
    inventarioImportBtn: document.getElementById('inventario-import'),
    inventarioExportCsv: document.getElementById('inventario-export-csv'),
    inventarioExportXlsx: document.getElementById('inventario-export-xlsx'),
    inventarioExportPdf: document.getElementById('inventario-export-pdf'),
    inventarioImportHint: document.getElementById('inventario-import-hint'),
    inventarioPurgeBtn: document.getElementById('inventario-purge'),
    inventarioRestoreBtn: document.getElementById('inventario-restore-backup'),
    inventarioRecycleBanner: document.getElementById('inventario-recycle-banner'),
    equipoModal: document.getElementById('equipo-modal'),
    equipoForm: document.getElementById('equipo-form'),
    equipoId: document.getElementById('equipo-id'),
    equipoBiomedica: document.getElementById('equipo-biomedica'),
    equipoActivo: document.getElementById('equipo-activo'),
    equipoInvima: document.getElementById('equipo-invima'),
    equipoNombre: document.getElementById('equipo-nombre'),
    equipoMarca: document.getElementById('equipo-marca'),
    equipoSerie: document.getElementById('equipo-serie'),
    equipoModelo: document.getElementById('equipo-modelo'),
    equipoRiesgo: document.getElementById('equipo-riesgo'),
    equipoUbicacion: document.getElementById('equipo-ubicacion'),
    equipoEstado: document.getElementById('equipo-estado'),
    equipoAplicaMp: document.getElementById('equipo-aplica-mp'),
    equipoFreqMp: document.getElementById('equipo-freq-mp'),
    equipoTiempoMp: document.getElementById('equipo-tiempo-mp'),
    equipoAplicaCal: document.getElementById('equipo-aplica-cal'),
    equipoFreqCal: document.getElementById('equipo-freq-cal'),
    equipoTiempoCal: document.getElementById('equipo-tiempo-cal'),
    equipoAplicaVal: document.getElementById('equipo-aplica-val'),
    equipoFreqVal: document.getElementById('equipo-freq-val'),
    equipoTiempoVal: document.getElementById('equipo-tiempo-val'),
    equipoExtraWrap: document.getElementById('equipo-extra-wrap'),
    equipoExtra: document.getElementById('equipo-extra'),
    empresaForm: document.getElementById('empresa-form'),
    empresaSedesBuilder: document.getElementById('empresa-sedes-builder'),
    empresaAddSede: document.getElementById('empresa-add-sede'),
    sedeForm: document.getElementById('sede-form'),
    sedeEmpresaSelect: document.getElementById('sede-empresa'),
    empresasList: document.getElementById('empresas-list'),
    empresasDetail: document.getElementById('empresas-detail'),
    empresaFormWrap: document.getElementById('empresa-form-wrap'),
    sedeFormWrap: document.getElementById('sede-form-wrap'),
    assignFormWrap: document.getElementById('assign-form-wrap'),
    direccionEmpresa: document.getElementById('direccion-empresa'),
    direccionLogBox: document.getElementById('direccion-log-box'),
    direccionLogHint: document.getElementById('direccion-log-hint'),
    direccionLogDownload: document.getElementById('direccion-log-download'),
    inventarioCrear: document.getElementById('inventario-crear'),
    fallosModal: document.getElementById('fallos-modal'),
    fallosForm: document.getElementById('fallos-form'),
    fallosTipo: document.getElementById('fallos-tipo'),
    fallosDescripcion: document.getElementById('fallos-descripcion'),
    fallosSolucion: document.getElementById('fallos-solucion'),
    fallosRemitenteHint: document.getElementById('fallos-remitente-hint'),
    fallosFormError: document.getElementById('fallos-form-error'),
    fallosDashboard: document.getElementById('fallos-dashboard'),
    fallosKpis: document.getElementById('fallos-kpis'),
    fallosChart: document.getElementById('fallos-chart'),
    direccionTree: document.getElementById('direccion-tree'),
    direccionEmpty: document.getElementById('direccion-empty'),
    direccionInvModal: document.getElementById('direccion-inv-modal'),
    direccionInvTitle: document.getElementById('direccion-inv-title'),
    direccionInvSubtitle: document.getElementById('direccion-inv-subtitle'),
    direccionInvBody: document.getElementById('direccion-inv-body'),
    usersTableBody: document.getElementById('users-table-body'),
    exportCsvBtn: document.getElementById('export-csv-btn'),
    exportXlsxBtn: document.getElementById('export-xlsx-btn'),
    adminCreateUserBtn: document.getElementById('admin-create-user-btn'),
    adminRefreshBtn: document.getElementById('admin-refresh-btn'),
    editModal: document.getElementById('edit-modal'),
    editForm: document.getElementById('edit-form'),
    editId: document.getElementById('edit-id'),
    editEmail: document.getElementById('edit-email'),
    editPassword: document.getElementById('edit-password'),
    editPasswordHint: document.getElementById('edit-password-hint'),
    editName: document.getElementById('edit-name'),
    editLastName: document.getElementById('edit-lastname'),
    editRoll: document.getElementById('edit-roll'),
    editJob: document.getElementById('edit-job'),
    editCreation: document.getElementById('edit-creation'),
    editEmpresa: document.getElementById('edit-empresa'),
    editTitle: document.getElementById('edit-title'),
    editEyebrow: document.getElementById('edit-eyebrow'),
    editSubmit: document.getElementById('edit-submit'),
    assignForm: document.getElementById('assign-form'),
    assignEmpresa: document.getElementById('assign-empresa'),
    assignSede: document.getElementById('assign-sede'),
    assignUser: document.getElementById('assign-user'),
  };

  let jobsByRole = {};
  let adminJobsByRole = {};
  let editModalMode = 'edit';
  let currentUser = null;
  let usersCache = [];
  let empresasCatalogCache = [];
  let registerEmpresaCargada = null;
  let sedesCache = [];
  let sedesEmpresasCache = [];
  let sedesSelectedEmpresaId = null;
  let empresasCache = [];
  let empresasSelectedId = null;
  let empresasSelectedSedeId = null;
  let empresasEmpresaPersonal = [];
  let inventarioCache = [];
  let inventarioRecycle = null;
  let inventarioRecycleTimer = null;
  let rbacState = { roles: [], jobs: [], permisos: {} };
  let rbacSelectedRolId = null;
  let rbacRenamingRolId = null;
  let rbacDeletingRolId = null;
  let rbacExpandedGroups = new Set();
  let mailState = {
    folder: 'inbox',
    messages: [],
    selectedKey: null,
    filterTipo: 'all',
    filterTramite: 'all',
    pageSize: 50,
  };
  let bandejaLoadGen = 0;
  let inventarioPage = 1;
  let inventarioTotalHint = 0;
  let inventarioServerPaged = false;
  let inventarioFilteredTotal = 0;
  let inventarioSearchTimer = null;
  let equipoSaving = false;
  let invEjSaving = false;
  let onlineTimer = null;
  let openNavSectionId = null;
  let clockTimer = null;
  let direccionEmpresas = [];
  let direccionInvCache = {};
  let direccionInvModalServicioId = null;
  let direccionInvModalEquipoTipo = null;
  let direccionInvModalRows = [];

  const RBAC_ICONS = {
    users: 'US',
    chart: 'RP',
    clinical: 'CL',
    database: 'DB',
    settings: 'CF',
    export: 'EX',
    engineering: 'IN',
    support: 'SP',
    module: 'MD',
    asistencial: 'AS',
    indicators: 'ID',
    inventory: 'IV',
    company: 'EM',
    process: 'PR',
    jobs: 'JB',
    acquisition: 'AD',
    servicio: 'SV',
  };

  function can(name) {
    return Boolean(currentUser?.can?.[name] ?? currentUser?.permissions?.[name]);
  }

  /* Validación de formularios, avisos y llamadas HTTP a /api y /admin. */
  function normalizeEmail(value) {
    return String(value || '').trim().toLowerCase();
  }

  function isValidEmail(value) {
    const email = normalizeEmail(value);
    return email.length > 0 && EMAIL_REGEX.test(email);
  }

  function isLettersOnly(value) {
    const text = String(value || '').trim();
    return text.length > 0 && LETTERS_ONLY_REGEX.test(text);
  }

  function validatePassword(password) {
    const errors = [];
    if (!password || password.length < 8) errors.push('Mínimo 8 caracteres.');
    return { valid: errors.length === 0, errors };
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function clearFieldErrors(form) {
    form.querySelectorAll('.field-error').forEach((node) => {
      node.hidden = true;
      node.textContent = '';
    });
    form.querySelectorAll('.is-invalid').forEach((node) => node.classList.remove('is-invalid'));
  }

  function setFieldError(input, message) {
    if (!input) return;
    input.classList.add('is-invalid');
    const errorNode = document.querySelector(`[data-error-for="${input.id}"]`);
    if (errorNode) {
      errorNode.textContent = message;
      errorNode.hidden = !message;
    }
  }

  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.innerHTML = `<p></p><button type="button" aria-label="Cerrar">×</button>`;
    toast.querySelector('p').textContent = message;
    toast.querySelector('button').addEventListener('click', () => toast.remove());
    els.toastRoot.appendChild(toast);
    window.setTimeout(() => toast.remove(), 7000);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      headers: {
        ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...(options.headers || {}),
      },
      ...options,
    });

    const contentType = response.headers.get('Content-Type') || '';
    let data = null;
    if (contentType.includes('application/json')) {
      try {
        data = await response.json();
      } catch {
        data = { ok: false, error: 'Respuesta inválida del servidor.' };
      }
    } else if (response.status === 405) {
      data = {
        ok: false,
        error: 'Esta acción no está activa. Detenga el servidor (Ctrl+C) y vuelva a iniciarlo.',
      };
    } else if (response.status === 404) {
      data = { ok: false, error: 'Recurso no encontrado. Recargue la página e inténtelo de nuevo.' };
    } else {
      data = {
        ok: false,
        error: `Respuesta inválida del servidor (${response.status}).`,
      };
    }
    return { response, data };
  }

  async function downloadFile(path, fallbackName) {
    const response = await fetch(path, { credentials: 'same-origin' });
    if (!response.ok) {
      let message = 'No se pudo exportar el archivo.';
      const contentType = response.headers.get('Content-Type') || '';
      if (contentType.includes('application/json')) {
        try {
          const data = await response.json();
          message = data.error || message;
        } catch {
          /* ignore */
        }
      } else if (response.status === 404 || response.status === 405) {
        message = 'No se pudo generar el PDF. Detenga el servidor (Ctrl+C) y vuelva a iniciarlo.';
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename="?([^"]+)"?/i);
    const filename = match?.[1] || fallbackName;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    return {
      filename,
      empty: response.headers.get('X-Inventario-Vacio') === '1',
      count: Number(response.headers.get('X-Inventario-Count') || 0),
    };
  }

  const ROLL_LABELS = {
    OPERATIVO: 'Operador',
    ASISTENCIAL: 'Asistencial',
    ADMIN: 'Administrador',
  };

  function rollLabel(roll) {
    const key = String(roll || '').toUpperCase();
    return ROLL_LABELS[key] || roll || '—';
  }

  function jobLabel(job) {
    const text = String(job || '').trim();
    return text || 'Sin asignar';
  }

  function fillSelectRoles(select, catalog, selected = '') {
    select.innerHTML = '<option value="" disabled>Selecciona un rol</option>';
    (catalog.roles || []).forEach((role) => {
      const option = document.createElement('option');
      option.value = role;
      option.textContent = rollLabel(role);
      if (role === selected) option.selected = true;
      select.appendChild(option);
    });
  }

  const PUBLIC_JOBS_BY_ROLE = {
    ASISTENCIAL: ['Coordinador', 'Líder'],
    OPERATIVO: ['Ingeniero', 'Técnico'],
  };
  const ALL_JOBS_BY_ROLE = {
    ASISTENCIAL: ['Director', 'Coordinador', 'Líder'],
    OPERATIVO: ['Director Operativo', 'Coordinador', 'Ingeniero', 'Técnico'],
    ADMIN: ['Administrador'],
  };

  function jobsForRoll(jobsMap, roll) {
    if (!roll || !jobsMap) {
      const upper = String(roll || '').toUpperCase();
      return PUBLIC_JOBS_BY_ROLE[upper] || ALL_JOBS_BY_ROLE[upper] || [];
    }
    if (Array.isArray(jobsMap[roll]) && jobsMap[roll].length) return jobsMap[roll];
    const key = Object.keys(jobsMap).find(
      (name) => String(name).toUpperCase() === String(roll).toUpperCase()
    );
    if (key && Array.isArray(jobsMap[key]) && jobsMap[key].length) return jobsMap[key];
    const upper = String(roll).toUpperCase();
    const isAdminCatalog = Object.keys(jobsMap).some(
      (name) => String(name).toUpperCase() === 'ADMIN'
    );
    if (isAdminCatalog) return ALL_JOBS_BY_ROLE[upper] || [];
    return PUBLIC_JOBS_BY_ROLE[upper] || ALL_JOBS_BY_ROLE[upper] || [];
  }

  function fillSelectJobs(select, jobsMap, roll, selected = '') {
    if (!select) return;
    const jobs = jobsForRoll(jobsMap, roll);
    select.innerHTML = '';
    if (!roll || !jobs.length) {
      select.disabled = true;
      select.innerHTML = '<option value="">Selecciona primero el ROLL</option>';
      return;
    }
    select.disabled = false;
    select.removeAttribute('disabled');
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.disabled = true;
    placeholder.textContent = 'Selecciona un cargo';
    if (!selected || !jobs.includes(selected)) placeholder.selected = true;
    select.appendChild(placeholder);
    jobs.forEach((job) => {
      const option = document.createElement('option');
      option.value = job;
      option.textContent = job;
      if (job === selected) option.selected = true;
      select.appendChild(option);
    });
    if ((!selected || !jobs.includes(selected)) && jobs.length === 1) {
      select.value = jobs[0];
    }
  }

  function setPasswordToggleUi(btn, showing) {
    if (!btn) return;
    btn.setAttribute('aria-pressed', showing ? 'true' : 'false');
    btn.setAttribute('aria-label', showing ? 'Ocultar contraseña' : 'Mostrar contraseña');
    const eye = btn.querySelector('.password-toggle__eye');
    const off = btn.querySelector('.password-toggle__eye-off');
    if (eye) eye.hidden = showing;
    if (off) off.hidden = !showing;
  }

  function resetPasswordToggles(root) {
    (root || document).querySelectorAll('[data-password-toggle]').forEach((btn) => {
      const input = document.getElementById(btn.dataset.passwordToggle);
      if (input) input.type = 'password';
      setPasswordToggleUi(btn, false);
    });
  }

  function fillRoles(catalog) {
    jobsByRole = catalog.jobsByRole || {};
    fillSelectRoles(els.regRoll, catalog);
  }

  /* Formulario de acceso y correos recordados. */
  function savedLoginEmails() {
    return Object.keys(readSavedLogins()).sort((a, b) => a.localeCompare(b, 'es'));
  }

  function closeLoginEmailMenu() {
    const menu = document.getElementById('login-email-menu');
    if (!menu) return;
    menu.hidden = true;
    if (els.loginEmail) els.loginEmail.setAttribute('aria-expanded', 'false');
  }

  function openLoginEmailMenu(filterText = '') {
    const menu = document.getElementById('login-email-menu');
    const toggle = document.getElementById('login-email-toggle');
    if (!menu) return;
    const q = normalizeEmail(filterText || '');
    const emails = savedLoginEmails().filter((email) => !q || email.includes(q));
    if (!emails.length) {
      closeLoginEmailMenu();
      if (toggle) toggle.hidden = !savedLoginEmails().length;
      return;
    }
    if (toggle) toggle.hidden = false;
    menu.innerHTML = emails
      .map(
        (email) =>
          `<li role="option">
            <button type="button" class="login-email-menu__item" data-email="${escapeHtml(email)}">${escapeHtml(
              email
            )}</button>
          </li>`
      )
      .join('');
    menu.hidden = false;
    if (els.loginEmail) els.loginEmail.setAttribute('aria-expanded', 'true');
  }

  function refreshLoginEmailSuggestions() {
    const toggle = document.getElementById('login-email-toggle');
    const emails = savedLoginEmails();
    if (toggle) toggle.hidden = emails.length === 0;
    const menu = document.getElementById('login-email-menu');
    if (menu && !menu.hidden) openLoginEmailMenu(els.loginEmail?.value || '');
  }

  function selectSavedLoginEmail(email) {
    if (!els.loginEmail) return;
    els.loginEmail.value = email;
    closeLoginEmailMenu();
    if (els.loginPassword) els.loginPassword.value = '';
    if (els.loginRemember) els.loginRemember.checked = false;
    els.loginPassword?.focus();
  }

  function wipeLoginFormFields() {
    if (els.loginForm) els.loginForm.reset();
    if (els.loginEmail) {
      els.loginEmail.value = '';
      els.loginEmail.defaultValue = '';
    }
    if (els.loginPassword) {
      els.loginPassword.value = '';
      els.loginPassword.defaultValue = '';
      els.loginPassword.type = 'password';
    }
    if (els.loginRemember) {
      els.loginRemember.checked = false;
      els.loginRemember.defaultChecked = false;
    }
    closeLoginEmailMenu();
  }

  function clearLoginResiduals() {
    try {
      localStorage.removeItem(SAVED_LOGINS_KEY);
      localStorage.removeItem(LAST_LOGIN_KEY);
    } catch {
      /* ignore */
    }
    wipeLoginFormFields();
    refreshLoginEmailSuggestions();
  }

  function applyRememberedLogin() {
    if (!els.loginEmail || !els.loginPassword) return;
    refreshLoginEmailSuggestions();
    wipeLoginFormFields();
  }

  function showLogin() {
    currentUser = null;
    window.AtlasOps?.refreshHelpButtons?.();
    currentRoute = null;
    spaCursor = 0;
    sedesCache = [];
    sedesEmpresasCache = [];
    sedesSelectedEmpresaId = null;
    if (clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
    stopOnlinePresence();
    els.dashboard.hidden = true;
    els.page.hidden = false;
    closeMobileNav();
    els.loginSection.hidden = false;
    if (els.welcomeSection) els.welcomeSection.hidden = true;
    wipeLoginFormFields();
    applyRememberedLogin();
  }

  function syncMobileLayout() {
    const root = document.documentElement;
    const vv = window.visualViewport;
    const height = Math.round((vv && vv.height) || window.innerHeight || 0);
    if (height > 0) root.style.setProperty('--app-vh', `${height}px`);
    const topbar = document.querySelector('.ops-topbar');
    if (topbar && !els.dashboard?.hidden) {
      root.style.setProperty('--ops-topbar-h', `${Math.round(topbar.getBoundingClientRect().height)}px`);
    }
  }

  function stopOnlinePresence() {
    if (onlineTimer) {
      clearInterval(onlineTimer);
      onlineTimer = null;
    }
    if (els.onlineDock) els.onlineDock.hidden = true;
    if (els.onlineDockPanel) els.onlineDockPanel.hidden = true;
    if (els.onlineDockToggle) els.onlineDockToggle.setAttribute('aria-expanded', 'false');
  }

  function renderOnlineUsers(payload) {
    if (!els.onlineDockList) return;
    const rows = payload?.usuarios || [];
    if (els.onlineDockCount) {
      els.onlineDockCount.hidden = rows.length === 0;
      els.onlineDockCount.textContent = String(rows.length);
    }
    if (!rows.length) {
      els.onlineDockList.innerHTML = '<li class="online-dock__meta">Nadie más conectado ahora.</li>';
      return;
    }
    const showEmp = Boolean(payload?.see_all_empresas);
    els.onlineDockList.innerHTML = rows
      .map((u) => {
        const rol = [u.JOB, u.ROLL].filter(Boolean).join(' · ');
        const emp = showEmp && u.empresa ? ` · ${u.empresa}` : '';
        const yo = u.yo ? ' (tú)' : '';
        return `<li>
          <span class="online-dock__name">${escapeHtml(u.nombre || 'Usuario')}${yo}</span>
          <span class="online-dock__meta">${escapeHtml(rol)}${escapeHtml(emp)}</span>
        </li>`;
      })
      .join('');
  }

  async function refreshOnlineUsers() {
    if (!currentUser || els.dashboard?.hidden || document.hidden) return;
    try {
      const { response, data } = await api('/api/online-users');
      if (!response.ok || !data.ok) return;
      if (els.onlineDock) els.onlineDock.hidden = false;
      renderOnlineUsers(data);
    } catch {
      /* no bloquear la UI */
    }
  }

  function startOnlinePresence() {
    if (!currentUser || !els.onlineDock) return;
    els.onlineDock.hidden = false;
    refreshOnlineUsers();
    if (onlineTimer) return;
    onlineTimer = setInterval(refreshOnlineUsers, 60000);
  }

  function closeMobileNav() {
    els.dashboard?.classList.remove('is-nav-open');
    els.dashNavToggle?.setAttribute('aria-expanded', 'false');
    if (els.dashNavToggle) els.dashNavToggle.setAttribute('aria-label', 'Abrir menú de módulos');
    if (els.opsNavOverlay) els.opsNavOverlay.hidden = true;
    document.body.classList.remove('nav-drawer-open');
  }

  function openMobileNav() {
    els.dashboard?.classList.add('is-nav-open');
    els.dashNavToggle?.setAttribute('aria-expanded', 'true');
    if (els.dashNavToggle) els.dashNavToggle.setAttribute('aria-label', 'Cerrar menú de módulos');
    if (els.opsNavOverlay) els.opsNavOverlay.hidden = false;
    document.body.classList.add('nav-drawer-open');
  }

  function toggleMobileNav() {
    if (els.dashboard?.classList.contains('is-nav-open')) closeMobileNav();
    else openMobileNav();
  }

  /* Cabecera del dashboard, perfil y cierre de sesión. */
  function formatDashDateTime(date = new Date()) {
    try {
      return date.toLocaleString('es-CO', {
        weekday: 'short',
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return date.toLocaleString();
    }
  }

  function updateDashClock() {
    if (els.dashDatetime) els.dashDatetime.textContent = formatDashDateTime();
  }

  function refreshDashHeader() {
    if (!currentUser) return;
    const fullName = `${currentUser.NAME_USER || ''} ${currentUser.LAST_NAME_USER || ''}`.trim();
    if (els.dashWelcome) {
      els.dashWelcome.textContent = fullName
        ? `¡Bienvenido! ${fullName}`
        : '¡Bienvenido!';
    }
    if (els.dashEmail) els.dashEmail.textContent = currentUser.usuario_login || '';
    updateDashClock();
    if (els.dashEmpresa) {
      const empresa = currentUser.ID_Empresa || '';
      if (empresa && currentUser.ROLL !== 'ADMIN') {
        els.dashEmpresa.hidden = false;
        els.dashEmpresa.textContent = empresa;
        els.dashEmpresa.title = empresa;
      } else if (empresa && currentUser.ROLL === 'ADMIN') {
        els.dashEmpresa.hidden = false;
        els.dashEmpresa.textContent = 'Administración global';
      } else {
        els.dashEmpresa.hidden = true;
        els.dashEmpresa.textContent = '';
      }
    }
    const jobPend =
      currentUser.ROLL !== 'ADMIN' &&
      (Boolean(currentUser.job_pendiente) || !String(currentUser.JOB || '').trim());
    const empPend =
      currentUser.ROLL !== 'ADMIN' &&
      (Boolean(currentUser.empresa_pendiente) || !currentUser.empresa_id);
    const showCard = jobPend || empPend;
    if (els.dashPending) els.dashPending.hidden = true;
    if (els.dashPendingCard) {
      els.dashPendingCard.hidden = !showCard;
      if (els.dashPendingTitle) {
        els.dashPendingTitle.textContent = jobPend
          ? 'Asignación de rol pendiente'
          : 'Asignación de empresa pendiente';
      }
      if (els.dashPendingCopy) {
        if (jobPend && empPend) {
          els.dashPendingCopy.textContent =
            'Espera hasta que el administrador asigne tu rol y tu empresa.';
        } else if (jobPend) {
          els.dashPendingCopy.textContent =
            'Espera hasta que el administrador asigne tu rol.';
        } else {
          els.dashPendingCopy.textContent =
            'Espera hasta que te asignen la empresa. Si se rechazó la solicitud, un rol con permisos de asignación debe hacerlo.';
        }
      }
    }
    if (els.dashMain) els.dashMain.classList.toggle('is-pending-role', showCard);
  }

  function setInboxBadge(count) {
    if (!els.dashInboxBadge) return;
    const n = Number(count) || 0;
    if (n > 0) {
      els.dashInboxBadge.hidden = false;
      els.dashInboxBadge.textContent = n > 99 ? '99+' : String(n);
    } else {
      els.dashInboxBadge.hidden = true;
      els.dashInboxBadge.textContent = '0';
    }
  }

  async function refreshInboxBadge() {
    try {
      const { data } = await api('/api/bandeja/resumen');
      if (data.ok) {
        setInboxBadge(Number(data.pendientes || 0));
        return;
      }
    } catch {
      /* ignore */
    }
    setInboxBadge(0);
  }

  function openPerfilModal() {
    if (!els.perfilModal || !currentUser) return;
    if (els.perfilMsg) {
      els.perfilMsg.hidden = true;
      els.perfilMsg.textContent = '';
    }
    if (els.perfilName) els.perfilName.value = currentUser.NAME_USER || '';
    if (els.perfilLastName) els.perfilLastName.value = currentUser.LAST_NAME_USER || '';
    if (els.perfilEmail) els.perfilEmail.value = currentUser.usuario_login || '';
    if (els.perfilTelefono) els.perfilTelefono.value = currentUser.telefono || '';
    if (els.perfilPassword) els.perfilPassword.value = '';
    if (els.perfilPassword2) els.perfilPassword2.value = '';
    const aceptado = Boolean(currentUser.aviso_aceptado_en);
    if (els.perfilAvisoEstado) {
      els.perfilAvisoEstado.textContent = aceptado
        ? `Autorización registrada el ${currentUser.aviso_aceptado_en} (aviso ${currentUser.aviso_version || 'vigente'}).`
        : 'Aún no hay autorización del titular. Márquela para guardar el perfil.';
    }
    if (els.perfilAvisoCheckWrap) els.perfilAvisoCheckWrap.hidden = aceptado;
    if (els.perfilAvisoCheck) els.perfilAvisoCheck.checked = aceptado;
    els.perfilModal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closePerfilModal() {
    if (!els.perfilModal) return;
    els.perfilModal.hidden = true;
    document.body.style.overflow = '';
  }

  async function logout({ silent = false } = {}) {
    try {
      await api('/logout', { method: 'POST', body: '{}' });
    } catch {
      /* ignore */
    }
    currentUser = null;
    clearLoginResiduals();
    try {
      if (silent) sessionStorage.removeItem(LOGOUT_FLASH_KEY);
      else sessionStorage.setItem(LOGOUT_FLASH_KEY, '1');
    } catch {
      /* ignore */
    }
    window.location.replace(window.location.pathname || '/');
  }

  /* Menú lateral, paneles e historial de navegación. */
  let currentRoute = null;
  let spaCursor = 0;
  let applyRouteGen = 0;

  function sectionForPanel(panel) {
    return (
      document.querySelector(`#dash-nav [data-panel="${panel}"]`)?.dataset?.sectionRef ||
      null
    );
  }

  function normalizeRoute(route = {}) {
    const panel = String(route.panel || '').trim() === 'respaldo' ? 'kpis' : String(route.panel || '').trim();
    const id = (value) =>
      value == null || value === '' ? null : String(value);
    return {
      panel,
      sectionId: route.sectionId || sectionForPanel(panel),
      empresaId: id(route.empresaId),
      sedeId: id(route.sedeId),
      servicioId: id(route.servicioId),
    };
  }

  function routesEqual(a, b) {
    if (!a || !b) return false;
    return (
      a.panel === b.panel &&
      String(a.empresaId || '') === String(b.empresaId || '') &&
      String(a.sedeId || '') === String(b.sedeId || '') &&
      String(a.servicioId || '') === String(b.servicioId || '')
    );
  }

  function parseLocation() {
    const hash = String(location.hash || '').replace(/^#/, '');
    const qIndex = hash.indexOf('?');
    const path = (qIndex >= 0 ? hash.slice(0, qIndex) : hash).replace(/^\/+/, '');
    const query = new URLSearchParams(qIndex >= 0 ? hash.slice(qIndex + 1) : '');
    const parts = path.split('/').filter(Boolean);
    const panel = parts[0] || '';
    const route = {
      panel,
      sectionId: null,
      empresaId: query.get('empresa'),
      sedeId: query.get('sede'),
      servicioId: query.get('servicio'),
    };
    if (panel === 'sedes' && parts[1] === 'empresa' && parts[2]) {
      route.empresaId = decodeURIComponent(parts[2]);
    }
    if (panel === 'empresas' && parts[1]) {
      route.empresaId = decodeURIComponent(parts[1]);
      if (parts[2] === 'sede' && parts[3]) {
        route.sedeId = decodeURIComponent(parts[3]);
      }
    }
    return normalizeRoute(route);
  }

  function serializeRoute(route) {
    const panel = route.panel || '';
    if (panel === 'sedes' && route.empresaId) {
      return `#/sedes/empresa/${encodeURIComponent(route.empresaId)}`;
    }
    if (panel === 'empresas' && route.empresaId) {
      let path = `#/empresas/${encodeURIComponent(route.empresaId)}`;
      if (route.sedeId) path += `/sede/${encodeURIComponent(route.sedeId)}`;
      return path;
    }
    if (panel === 'inventario' && (route.empresaId || route.sedeId || route.servicioId)) {
      const q = new URLSearchParams();
      if (route.empresaId) q.set('empresa', route.empresaId);
      if (route.sedeId) q.set('sede', route.sedeId);
      if (route.servicioId) q.set('servicio', route.servicioId);
      return `#/inventario?${q.toString()}`;
    }
    if (
      ['suficiencia', 'dimensionamiento', 'frecuencia-pm', 'preinstalacion', 'kpis'].includes(panel) &&
      (route.empresaId || route.sedeId || route.servicioId)
    ) {
      const q = new URLSearchParams();
      if (route.empresaId) q.set('empresa', route.empresaId);
      if (route.sedeId) q.set('sede', route.sedeId);
      if (route.servicioId) q.set('servicio', route.servicioId);
      return `#/${panel}?${q.toString()}`;
    }
    return panel ? `#/${panel}` : '#/';
  }

  function showPanel(name, { sectionId = null } = {}) {
    document.querySelectorAll('.dash-panel').forEach((p) => {
      p.hidden = true;
    });
    document.querySelectorAll('#dash-nav [data-panel]').forEach((b) => b.classList.remove('is-active'));
    document.querySelectorAll('#dash-nav .nav-section').forEach((s) => s.classList.remove('is-active'));

    const panel = document.getElementById(`panel-${name}`);
    const btn = document.querySelector(`#dash-nav [data-panel="${name}"]`);
    if (panel) panel.hidden = false;
    if (btn) btn.classList.add('is-active');

    const section = sectionId
      ? document.querySelector(`#dash-nav .nav-section[data-section="${sectionId}"]`)
      : btn?.closest('.nav-section');
    if (section) {
      section.classList.add('is-active', 'is-open');
      openNavSectionId = section.dataset.section;
      document.querySelectorAll('#dash-nav .nav-section').forEach((s) => {
        if (s !== section) s.classList.remove('is-open');
      });
    }
    window.SIGTBHelp?.onPanelChange?.(name);
  }

  async function loadInstrumentWithScope(loader, scopeKey, route) {
    await loader?.();
    if (route?.empresaId || route?.sedeId || route?.servicioId) {
      await window.AtlasOps?.applyOrgScope?.(scopeKey, route);
    }
  }

  const PANEL_LOADERS = {
    sedes: (route) => loadSedes({ empresaId: route?.empresaId }),
    inventario: (route) =>
      loadInventarioPanel({
        empresaId: route?.empresaId,
        sedeId: route?.sedeId,
        servicioId: route?.servicioId,
      }),
    empresas: (route) =>
      loadEmpresasPanel({
        empresaId: route?.empresaId,
        sedeId: route?.sedeId,
      }),
    direccion: () => loadDireccion(),
    adquisicion: () => window.AtlasOps?.loadAdquisicionPanel?.(),
    'dimensionamiento-empresa': () => window.AtlasOps?.loadDimensionamientoEmpresaPanel?.(),
    usuarios: () => loadUsers(),
    rbac: () => loadRbacPanel(),
    bandeja: () => loadBandeja(),
    suficiencia: (route) =>
      loadInstrumentWithScope(
        () => window.AtlasOps?.loadSuficienciaPanel?.(),
        'suficiencia',
        route
      ),
    dimensionamiento: (route) =>
      loadInstrumentWithScope(
        () => window.AtlasOps?.loadDimensionamientoPanel?.(),
        'dimensionamiento',
        route
      ),
    'frecuencia-pm': (route) =>
      loadInstrumentWithScope(
        () => window.AtlasOps?.loadFrecuenciaPmPanel?.(),
        'frecuencia-pm',
        route
      ),
    preinstalacion: (route) =>
      loadInstrumentWithScope(
        () => window.AtlasOps?.loadPreinstalacionPanel?.(),
        'preinstalacion',
        route
      ),
    kpis: (route) =>
      loadInstrumentWithScope(() => window.AtlasOps?.loadKpisPanel?.(), 'kpis', route),
  };

  function canOpenPanel(panelId) {
    if (!panelId || !document.getElementById(`panel-${panelId}`)) return false;
    if (INSTRUMENT_PANEL_IDS.has(panelId) && !allowedInstrumentPanels().has(panelId)) {
      return false;
    }
    const navBtn = document.querySelector(`#dash-nav [data-panel="${panelId}"]`);
    if (navBtn) return true;
    if (panelId === 'bandeja') return true;
    if (panelId === 'dimensionamiento-empresa' && currentUser?.ROLL === 'ADMIN') return true;
    return false;
  }

  async function applyRoute(route) {
    const next = normalizeRoute(route);
    if (!next.panel) return;
    const gen = ++applyRouteGen;
    if (!canOpenPanel(next.panel)) {
      showToast('No tiene permiso para este módulo.', 'warn');
      return;
    }
    showPanel(next.panel, { sectionId: next.sectionId });
    await PANEL_LOADERS[next.panel]?.(next);
    if (gen !== applyRouteGen) return;
  }

  function navigateTo(route, { replace = false } = {}) {
    const next = normalizeRoute(route);
    if (!next.panel) return;
    const url = serializeRoute(next);
    const same = routesEqual(currentRoute, next);
    if (same && currentRoute?.panel) {
      currentRoute = next;
      applyRoute(next);
      return;
    }
    if (replace || !currentRoute?.panel) {
      history.replaceState({ ...next, spaCursor }, '', url);
    } else {
      spaCursor += 1;
      history.pushState({ ...next, spaCursor }, '', url);
    }
    currentRoute = next;
    applyRoute(next);
  }

  function inAppBack(parentRoute) {
    if (spaCursor > 0) {
      history.back();
      return;
    }
    navigateTo(parentRoute, { replace: true });
  }

  function rememberCurrentRoute(route) {
    const next = normalizeRoute(route);
    if (!next.panel) return;
    history.replaceState({ ...next, spaCursor }, '', serializeRoute(next));
    currentRoute = next;
  }

  function rememberInventarioSelection() {
    if (currentRoute?.panel !== 'inventario') return;
    rememberCurrentRoute({
      panel: 'inventario',
      sectionId: currentRoute.sectionId || 'organizacion',
      empresaId: els.inventarioEmpresaSelect?.value || null,
      sedeId: els.inventarioSedeSelect?.value || null,
      servicioId: els.inventarioServicioSelect?.value || null,
    });
  }

  function openModule(panelId, sectionId, extra = {}) {
    if (INSTRUMENT_PANEL_IDS.has(panelId) && !allowedInstrumentPanels().has(panelId)) {
      showToast('No tiene permiso para este módulo.', 'warn');
      return;
    }
    navigateTo({
      panel: panelId,
      sectionId,
      empresaId: extra.empresaId,
      sedeId: extra.sedeId,
      servicioId: extra.servicioId,
    });
  }

  window.addEventListener('popstate', (event) => {
    if (els.dashboard?.hidden || !currentUser) return;
    const st = event.state;
    const route = st && st.panel ? normalizeRoute(st) : parseLocation();
    if (st && Number.isFinite(Number(st.spaCursor))) {
      spaCursor = Number(st.spaCursor);
    }
    currentRoute = route;
    applyRoute(route);
  });

  const INSTRUMENT_PANEL_IDS = new Set([
    'suficiencia',
    'dimensionamiento',
    'frecuencia-pm',
    'preinstalacion',
    'kpis',
    'capex',
  ]);

  function allowedInstrumentPanels() {
    const roll = String(currentUser.ROLL || '').toUpperCase();
    if (roll === 'ADMIN') return new Set(INSTRUMENT_PANEL_IDS);
    const allowed = new Set();
    if (
      can('view_suficiencia') ||
      can('edit_suficiencia_asistencial') ||
      can('request_suficiencia_update')
    ) {
      allowed.add('suficiencia');
    }
    if (can('view_dimensionamiento')) allowed.add('dimensionamiento');
    if (can('view_frecuencia_pm')) allowed.add('frecuencia-pm');
    if (can('view_preinstalacion')) allowed.add('preinstalacion');
    if (can('view_kpis') || can('view_respaldo')) allowed.add('kpis');
    if (can('view_capex')) allowed.add('capex');
    return allowed;
  }

  function buildNav() {
    const canOrg =
      currentUser.ROLL === 'ADMIN' ||
      can('view_sedes') ||
      can('view_inventory') ||
      can('access_servicio') ||
      can('create_empresa') ||
      can('create_sede') ||
      can('admin_panel') ||
      can('view_all_empresas') ||
      can('view_dimensionamiento_empresa');
    const canPersonal =
      can('manage_users') ||
      can('manage_asistencial_users') ||
      currentUser.ROLL === 'ADMIN';
    const instrumentItems = [];
    const allowedInstruments = allowedInstrumentPanels();
    const instrumentCatalog = [
      ['suficiencia', 'Suficiencia de equipos'],
      ['dimensionamiento', 'Dimensionamiento de personal'],
      ['frecuencia-pm', 'Frecuencia de mantenimiento preventivo'],
      ['preinstalacion', 'Preinstalación de la tecnología biomédica'],
      ['kpis', 'KPIs de ingeniería clínica'],
      ['capex', 'Instrumento CAPEX'],
    ];
    instrumentCatalog.forEach(([id, label]) => {
      if (allowedInstruments.has(id)) instrumentItems.push([id, label]);
    });

    const groups = [];

    if (canOrg) {
      const items = [];
      if (can('view_sedes')) items.push(['sedes', 'Sedes']);
      if (can('view_inventory') || can('access_servicio')) items.push(['inventario', 'Inventario']);
      if (can('create_empresa') || can('create_sede') || can('admin_panel')) {
        items.push(['empresas', 'Empresas / sedes']);
      }
      if (can('view_all_empresas')) items.push(['direccion', 'Módulo Dirección']);
      if (can('view_adquisicion_dashboard')) {
        items.push(['adquisicion', 'Forma de adquisición']);
      }
      if (can('view_dimensionamiento_empresa') || currentUser.ROLL === 'ADMIN') {
        items.push(['dimensionamiento-empresa', 'Dimensionamiento empresarial']);
      }
      if (items.length) {
        groups.push({
          id: 'organizacion',
          label: 'Organización',
          defaultPanel: items[0][0],
          items,
        });
      }
    }

    if (canPersonal) {
      const items = [];
      if (can('manage_users') || can('manage_asistencial_users') || currentUser.ROLL === 'ADMIN') {
        items.push(['usuarios', 'Usuarios']);
      }
      if (currentUser.ROLL === 'ADMIN') items.push(['rbac', 'Roles y permisos']);
      if (items.length) {
        groups.push({
          id: 'personal',
          label: 'Personal',
          defaultPanel: items[0][0],
          items,
        });
      }
    }

    if (instrumentItems.length) {
      groups.push({
        id: 'instrumentos',
        label: 'Instrumentos de análisis',
        defaultPanel: instrumentItems[0][0],
        items: instrumentItems,
      });
    }

    els.dashNav.innerHTML = groups
      .map(
        (g) => `
        <div class="nav-section" data-section="${g.id}" data-default-panel="${g.defaultPanel}">
          <button type="button" class="nav-section__toggle" data-section-toggle="${g.id}" aria-expanded="false">
            <span>${escapeHtml(g.label)}</span>
            <span class="nav-section__chevron" aria-hidden="true">▸</span>
          </button>
          <div class="nav-section__items" role="group" aria-label="${escapeHtml(g.label)}">
            ${g.items
              .map(
                ([id, name]) =>
                  `<button type="button" data-panel="${id}" data-section-ref="${g.id}">${escapeHtml(name)}</button>`
              )
              .join('')}
          </div>
        </div>`
      )
      .join('');

    els.dashNav.querySelectorAll('[data-section-toggle]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const section = btn.closest('.nav-section');
        const sectionId = section.dataset.section;
        document.querySelectorAll('#dash-nav .nav-section').forEach((s) => {
          const open = s === section;
          s.classList.toggle('is-open', open);
          s.querySelector('[data-section-toggle]')?.setAttribute(
            'aria-expanded',
            open ? 'true' : 'false'
          );
        });
        openModule(section.dataset.defaultPanel, sectionId);
      });
    });

    els.dashNav.querySelectorAll('button[data-panel]').forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.stopPropagation();
        openModule(btn.dataset.panel, btn.dataset.sectionRef);
        closeMobileNav();
      });
    });

    if (groups.length) {
      const first = groups[0];
      const fromUrl = parseLocation();
      const allowed = new Set(groups.flatMap((g) => g.items.map(([id]) => id)));
      allowed.add('bandeja');
      if (fromUrl.panel && allowed.has(fromUrl.panel) && canOpenPanel(fromUrl.panel)) {
        navigateTo(
          {
            ...fromUrl,
            sectionId: fromUrl.sectionId || sectionForPanel(fromUrl.panel),
          },
          { replace: true }
        );
      } else {
        navigateTo(
          { panel: first.defaultPanel, sectionId: first.id },
          { replace: true }
        );
      }
    }
  }

  async function openDashboard(user) {
    // Evita reutilizar sedes de otra sesión/empresa (p. ej. tras ADMIN).
    sedesCache = [];
    sedesEmpresasCache = [];
    sedesSelectedEmpresaId = null;
    currentRoute = null;
    spaCursor = 0;
    currentUser = user;
    const { data } = await api('/api/me');
    if (data.ok) currentUser = { ...user, ...data.user };
    window.AtlasOps?.refreshHelpButtons?.();
    els.page.hidden = true;
    els.dashboard.hidden = false;
    refreshDashHeader();
    requestAnimationFrame(syncMobileLayout);
    if (clockTimer) clearInterval(clockTimer);
    clockTimer = setInterval(updateDashClock, 30000);
    buildNav();
    if (els.dashInbox) els.dashInbox.hidden = false;
    refreshInboxBadge();
    startOnlinePresence();
  }

  async function restoreSessionFromCache() {
    const params = new URLSearchParams(window.location.search);
    const resetToken = params.get('reset');
    if (resetToken) {
      openResetModal(resetToken);
      history.replaceState({}, document.title, window.location.pathname);
    }
    const { response, data } = await api('/api/me');
    if (response.ok && data.ok && data.user) {
      await openDashboard(data.user);
      return;
    }
    showLogin();
    try {
      if (sessionStorage.getItem(LOGOUT_FLASH_KEY)) {
        sessionStorage.removeItem(LOGOUT_FLASH_KEY);
        showToast('Sesión cerrada.', 'info');
      }
    } catch {
      /* ignore */
    }
  }

  /* Sedes y selectores de alcance (empresa / sede / servicio). */
  function parseServiciosInput(value) {
    return String(value || '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function addSedeBuilderRow(container, { name = '', servicios = '' } = {}) {
    if (!container) return;
    const row = document.createElement('div');
    row.className = 'sede-builder-row sede-builder-row--compact';
    row.innerHTML = `
      <div class="field">
        <label>Sede</label>
        <input class="sede-name-input" type="text" placeholder="Nombre" value="${escapeHtml(name)}" />
      </div>
      <div class="field">
        <label>ID sede (opc.)</label>
        <input class="sede-id-input" type="text" placeholder="Si ya existe" />
      </div>
      <div class="field">
        <label>Servicios</label>
        <input class="sede-servicios-input" type="text" placeholder="3000 Urgencias, Cirugía" value="${escapeHtml(servicios)}" />
      </div>
      <button type="button" class="btn btn-ghost btn-sm sede-remove-btn" aria-label="Quitar sede">×</button>
    `;
    row.querySelector('.sede-remove-btn').addEventListener('click', () => row.remove());
    container.appendChild(row);
  }

  function collectSedesFromBuilder(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll('.sede-builder-row'))
      .map((row) => {
        const name_sede = row.querySelector('.sede-name-input')?.value.trim() || '';
        const ID_sede = row.querySelector('.sede-id-input')?.value.trim() || '';
        const servicios = parseServiciosInput(row.querySelector('.sede-servicios-input')?.value);
        return { name_sede, ID_sede: ID_sede || undefined, servicios };
      })
      .filter((item) => item.name_sede);
  }

  function formatServicios(servicios) {
    if (!servicios || !servicios.length) return '—';
    return servicios
      .map((s) => `${s.ID_servicio || ''} ${s.name_servicio || s}`.trim())
      .join(', ');
  }

  function groupSedesByEmpresa(sedes) {
    const map = new Map();
    (sedes || []).forEach((s) => {
      const key = String(s.empresa_id ?? s.ID_Empresa);
      if (!map.has(key)) {
        map.set(key, {
          id: s.empresa_id,
          ID_Empresa: s.ID_Empresa,
          ID_NIT: s.ID_NIT,
          sedes: [],
        });
      }
      map.get(key).sedes.push(s);
    });
    return [...map.values()].sort((a, b) =>
      String(a.ID_Empresa || '').localeCompare(String(b.ID_Empresa || ''), 'es')
    );
  }

  function renderSedesEmpresaCards() {
    if (!els.sedesList) return;
    if (els.sedesDetail) {
      els.sedesDetail.hidden = true;
      els.sedesDetail.innerHTML = '';
    }
    els.sedesList.hidden = false;

    if (!sedesEmpresasCache.length) {
      els.sedesList.innerHTML =
        '<p class="empty">No hay empresas con sedes registradas para tu perfil.</p>';
      return;
    }

    els.sedesList.innerHTML = sedesEmpresasCache
      .map((e) => {
        const sedesCount = (e.sedes || []).length;
        const serviciosCount = (e.sedes || []).reduce(
          (acc, s) => acc + (s.servicios || []).length,
          0
        );
        const selectKey = e.id != null ? e.id : e.ID_Empresa;
        return `
        <button type="button" class="info-card info-card--empresa" data-select-empresa="${escapeHtml(
          String(selectKey)
        )}">
          <h3>${escapeHtml(e.ID_Empresa)}</h3>
          <p>NIT ${escapeHtml(e.ID_NIT)}</p>
          <p class="field-hint">
            ${sedesCount} sede${sedesCount === 1 ? '' : 's'} ·
            ${serviciosCount} servicio${serviciosCount === 1 ? '' : 's'}
          </p>
        </button>`;
      })
      .join('');
  }

  function renderSedesEmpresaDetail(empresaKey) {
    if (!els.sedesDetail || !els.sedesList) return;
    const empresa = sedesEmpresasCache.find(
      (e) =>
        String(e.id) === String(empresaKey) ||
        String(e.ID_Empresa) === String(empresaKey)
    );
    if (!empresa) {
      sedesSelectedEmpresaId = null;
      renderSedesEmpresaCards();
      return;
    }

    sedesSelectedEmpresaId = empresa.id ?? empresa.ID_Empresa;
    els.sedesList.hidden = true;

    const sedes = empresa.sedes || [];
    const sedesHtml = sedes.length
      ? sedes
          .map((sede) => {
            const servicios = sede.servicios || [];
            const serviciosHtml = servicios.length
              ? `<ul class="servicio-list servicio-list--actions">${servicios
                  .map((srv) => {
                    const openBtn = can('access_servicio')
                      ? `<button type="button" class="btn btn-primary btn-sm" data-open-servicio="${srv.id}" data-sede-id="${sede.id}" data-empresa-id="${empresa.id}">
                           Abrir
                         </button>`
                      : '';
                    return `<li class="servicio-list__item">
                        <span><strong>${escapeHtml(srv.ID_servicio)}</strong> · ${escapeHtml(
                          srv.name_servicio
                        )}</span>
                        <span class="servicio-list__actions">
                          ${openBtn}
                          ${renderInventarioExportActions(srv.id, { compact: true, shortLabels: true })}
                        </span>
                      </li>`;
                  })
                  .join('')}</ul>`
              : '<p class="field-hint">Sin servicios</p>';
            const sedePdf = canDownloadInventarioPdf()
              ? `<button type="button" class="btn btn-ghost btn-sm" data-export-sede-inv="pdf" data-sede-id="${sede.id}">
                   Plantilla PDF
                 </button>`
              : '';
            return `
            <section class="sedes-detail__sede">
              <header class="sedes-detail__sede-head">
                <h4>${escapeHtml(sede.ID_sede)} · ${escapeHtml(sede.name_sede)}</h4>
                ${sedePdf}
              </header>
              ${serviciosHtml}
            </section>`;
          })
          .join('')
      : '<p class="empty">Esta empresa no tiene sedes registradas.</p>';

    els.sedesDetail.hidden = false;
    els.sedesDetail.innerHTML = `
      <div class="sedes-detail__toolbar">
        <button type="button" class="btn btn-ghost" data-sedes-back>← Empresas</button>
      </div>
      <header class="sedes-detail__head">
        <p class="eyebrow">Empresa</p>
        <h3>${escapeHtml(empresa.ID_Empresa)}</h3>
        <p>NIT ${escapeHtml(empresa.ID_NIT)}</p>
        <p class="field-hint">
          ${sedes.length} sede${sedes.length === 1 ? '' : 's'}
        </p>
      </header>
      <div class="sedes-detail__sedes">${sedesHtml}</div>`;
  }

  async function loadSedes(opts = {}) {
    if (!els.sedesList) return;
    const { response, data } = await api('/api/sedes');
    if (!response.ok || !data.ok) {
      els.sedesList.hidden = false;
      els.sedesList.innerHTML = `<p class="empty">${escapeHtml(data.error || 'Error')}</p>`;
      if (els.sedesDetail) {
        els.sedesDetail.hidden = true;
        els.sedesDetail.innerHTML = '';
      }
      return;
    }

    sedesCache = data.sedes || [];
    sedesEmpresasCache = groupSedesByEmpresa(sedesCache);
    if (opts.empresaId) {
      renderSedesEmpresaDetail(opts.empresaId);
    } else {
      sedesSelectedEmpresaId = null;
      renderSedesEmpresaCards();
    }
  }

  function fillInventarioEmpresaSelect() {
    const sel = els.inventarioEmpresaSelect;
    if (!sel) return;
    const map = new Map();
    (sedesCache || []).forEach((s) => {
      if (!s.empresa_id || map.has(Number(s.empresa_id))) return;
      map.set(Number(s.empresa_id), s);
    });
    const empresas = [...map.values()].sort((a, b) =>
      String(a.ID_Empresa || '').localeCompare(String(b.ID_Empresa || ''), 'es')
    );
    const prev = sel.value;
    sel.innerHTML = '<option value="">Selecciona empresa</option>';
    empresas.forEach((e) => {
      const opt = document.createElement('option');
      opt.value = e.empresa_id;
      opt.textContent = e.ID_NIT
        ? `${e.ID_Empresa} · ${e.ID_NIT}`
        : e.ID_Empresa || `Empresa ${e.empresa_id}`;
      sel.appendChild(opt);
    });
    if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
    sel.hidden = empresas.length <= 1 && currentUser?.ROLL !== 'ADMIN';
  }

  function fillSedeSelect(select, empresaId) {
    if (!select) return;
    const filterId = empresaId || els.inventarioEmpresaSelect?.value || '';
    const useFilter = select === els.inventarioSedeSelect ? filterId : empresaId;
    if (select === els.inventarioSedeSelect && !useFilter) {
      select.innerHTML = '<option value="">Selecciona sede</option>';
      return;
    }
    let list = sedesCache || [];
    if (useFilter) {
      list = list.filter((s) => Number(s.empresa_id) === Number(useFilter));
    }
    select.innerHTML = '<option value="">Selecciona sede</option>';
    const byEmpresa = new Map();
    list.forEach((s) => {
      const key = s.ID_Empresa || `Empresa ${s.empresa_id || ''}`;
      if (!byEmpresa.has(key)) byEmpresa.set(key, []);
      byEmpresa.get(key).push(s);
    });
    const multi = byEmpresa.size > 1 && !useFilter;
    byEmpresa.forEach((sedes, empresaName) => {
      const parent = multi ? document.createElement('optgroup') : select;
      if (multi) {
        parent.label = empresaName;
        select.appendChild(parent);
      }
      sedes.forEach((s) => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.ID_sede ? `${s.ID_sede} · ${s.name_sede}` : s.name_sede;
        parent.appendChild(opt);
      });
    });
  }

  function fillServicioSelect(select, sedeId) {
    select.innerHTML = '<option value="">Selecciona servicio</option>';
    const sede = sedesCache.find((s) => String(s.id) === String(sedeId));
    (sede?.servicios || []).forEach((srv) => {
      const opt = document.createElement('option');
      opt.value = srv.id;
      opt.textContent = `${srv.ID_servicio} · ${srv.name_servicio}`;
      select.appendChild(opt);
    });
  }

  async function ensureSedes({ force = false } = {}) {
    if (!force && sedesCache.length) return sedesCache;
    const { data } = await api('/api/sedes');
    if (data.ok) sedesCache = data.sedes || [];
    return sedesCache;
  }

  /* Inventario biomédico del servicio: listado, edición e importación. */
  async function loadInventarioPanel(opts = {}) {
    await ensureSedes({ force: true });
    fillInventarioEmpresaSelect();
    if (els.inventarioEmpresaSelect && opts.empresaId) {
      els.inventarioEmpresaSelect.value = String(opts.empresaId);
    }
    fillSedeSelect(els.inventarioSedeSelect, els.inventarioEmpresaSelect?.value || '');
    if (opts.sedeId && els.inventarioSedeSelect) {
      els.inventarioSedeSelect.value = String(opts.sedeId);
    }
    fillServicioSelect(
      els.inventarioServicioSelect,
      els.inventarioSedeSelect?.value || ''
    );
    window.AtlasOps?.refreshOrgScopeSummaries?.();
    els.inventarioExportCsv.hidden = !can('export_inventory');
    els.inventarioExportXlsx.hidden = !can('export_inventory');
    if (els.inventarioExportPdf) {
      els.inventarioExportPdf.hidden = !(
        can('view_inventory') ||
        can('export_inventory') ||
        can('access_servicio')
      );
    }
    els.inventarioImportBtn.hidden = !can('import_inventory');
    els.inventarioFile.hidden = !can('import_inventory');
    if (els.inventarioImportHint) {
      els.inventarioImportHint.hidden = !can('import_inventory');
    }
    if (opts.servicioId && els.inventarioServicioSelect) {
      els.inventarioServicioSelect.value = String(opts.servicioId);
      if (els.inventarioSearch) els.inventarioSearch.value = '';
      window.AtlasOps?.refreshOrgScopeSummaries?.();
      await loadInventario(opts.servicioId);
      return;
    }
    els.inventarioTableBody.innerHTML =
      '<tr><td colspan="11">Selecciona sede y servicio para ver el inventario.</td></tr>';
    if (els.inventarioSearch) els.inventarioSearch.value = '';
    if (els.inventarioSearchHint) {
      els.inventarioSearchHint.hidden = true;
      els.inventarioSearchHint.textContent = '';
    }
    inventarioCache = [];
    inventarioRecycle = null;
    renderInventarioRecycle();
  }

  async function openServicioInventario({ empresaId, sedeId, servicioId } = {}) {
    if (!can('access_servicio')) {
      showToast(
        'No tienes permiso para visualizar ni tratar la información de este servicio.',
        'warn'
      );
      return;
    }
    if (!servicioId) {
      showToast('Selecciona un servicio.', 'error');
      return;
    }
    openModule('inventario', 'organizacion', {
      empresaId,
      sedeId,
      servicioId,
    });
  }

  function canPurgeInventory() {
    if (!currentUser) return false;
    if (currentUser.ROLL === 'ADMIN') return true;
    return (
      currentUser.ROLL === 'OPERATIVO' &&
      ['Director Operativo', 'Dirección'].includes(currentUser.JOB)
    );
  }

  function formatRecycleCountdown(seconds) {
    const n = Math.max(0, Number(seconds) || 0);
    const m = Math.floor(n / 60);
    const s = n % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function renderInventarioRecycle() {
    const canPurge = canPurgeInventory();
    const pending = Boolean(inventarioRecycle?.pending && inventarioRecycle?.can_restore);
    if (els.inventarioPurgeBtn) {
      els.inventarioPurgeBtn.hidden = !canPurge;
      els.inventarioPurgeBtn.disabled = !els.inventarioServicioSelect?.value;
    }
    if (els.inventarioRestoreBtn) {
      els.inventarioRestoreBtn.hidden = !canPurge;
      els.inventarioRestoreBtn.disabled = !pending;
    }
    if (inventarioRecycleTimer) {
      clearInterval(inventarioRecycleTimer);
      inventarioRecycleTimer = null;
    }
    if (!els.inventarioRecycleBanner) return;
    if (!canPurge || !pending) {
      els.inventarioRecycleBanner.hidden = true;
      els.inventarioRecycleBanner.textContent = '';
      return;
    }
    const tick = () => {
      const remaining = Number(inventarioRecycle?.remaining_seconds || 0);
      if (remaining <= 0) {
        inventarioRecycle = { pending: false, can_restore: false };
        renderInventarioRecycle();
        return;
      }
      els.inventarioRecycleBanner.hidden = false;
      els.inventarioRecycleBanner.textContent =
        `Inventario eliminado (${inventarioRecycle.equipos || 0} equipo(s)). ` +
        `Puede restaurarlo con «Restaurar último backup» durante ${formatRecycleCountdown(remaining)}. ` +
        `Pasado ese tiempo el respaldo de este borrado se elimina de forma definitiva. ` +
        `El auto-backup del sistema no se modifica.`;
      inventarioRecycle.remaining_seconds = remaining - 1;
    };
    tick();
    inventarioRecycleTimer = setInterval(tick, 1000);
  }

  function setTriSelect(el, value) {
    if (!el) return;
    if (value === true || value === 1 || value === '1') el.value = '1';
    else if (value === false || value === 0 || value === '0') el.value = '0';
    else el.value = '';
  }

  function triSelectValue(el) {
    if (!el || el.value === '') return null;
    return el.value === '1';
  }

  function numOrNull(el) {
    if (!el || el.value === '' || el.value == null) return null;
    const n = Number(el.value);
    return Number.isFinite(n) ? n : null;
  }

  function renderEquipoExtra(equipo) {
    const wrap = els.equipoExtraWrap || document.getElementById('equipo-extra-wrap');
    const box = els.equipoExtra || document.getElementById('equipo-extra');
    if (!wrap || !box) return;
    const pairs = [
      ['Clasificación biomédica', equipo.clasificacion_biomedica],
      ['Periodicidad MP', equipo.periodicidad_mp],
      ['Periodicidad calibración', equipo.periodicidad_cal],
      ['Último PM', (equipo.fecha_ultimo_pm || '').toString().slice(0, 10)],
      ['Fecha de compra', (equipo.fecha_compra || '').toString().slice(0, 10)],
      ['Fecha de operación', (equipo.fecha_operacion || '').toString().slice(0, 10)],
      ['Vencimiento de garantía', (equipo.fecha_garantia || '').toString().slice(0, 10)],
      ['Fecha de baja', (equipo.fecha_baja || '').toString().slice(0, 10)],
      ['Vida útil', equipo.vida_util_txt],
      ['Forma de adquisición', equipo.forma_adquisicion],
      ['Tecnología', equipo.tecnologia],
      ['Comercializador', equipo.comercializador],
      ['Tensión', equipo.voltaje],
      ['Corriente', equipo.corriente],
      ['Potencia', equipo.potencia],
      ['Peso', equipo.peso],
      ['Temperatura de trabajo', equipo.temperatura_trabajo],
      ['Presión', equipo.presion],
      ['Novedad', equipo.novedad_desc],
      ['Institución origen', equipo.institucion_origen],
    ].filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '');
    if (!pairs.length) {
      wrap.hidden = true;
      box.innerHTML = '';
      return;
    }
    wrap.hidden = false;
    box.innerHTML = pairs
      .map(
        ([label, value]) =>
          `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`
      )
      .join('');
  }

  function openEquipoModal(equipo) {
    if (!els.equipoModal || !els.equipoForm) return;
    els.equipoForm.reset();
    const title = document.getElementById('equipo-title');
    const creating = !equipo || !equipo.id;
    const src = equipo || {};
    if (title) {
      title.textContent = creating ? 'Crear equipo' : 'Editar equipo';
    }
    const alertaHost = document.getElementById('equipo-alerta-slot');
    if (alertaHost) {
      alertaHost.innerHTML = creating ? '' : window.AtlasOps.equipoAlertaMarkup(src);
    }
    els.equipoId.value = creating ? '' : equipo.id;
    els.equipoBiomedica.value = src.num_biomedica || '';
    if (els.equipoActivo) els.equipoActivo.value = src.codigo_activo || '';
    els.equipoInvima.value = src.registro_invima || '';
    els.equipoNombre.value = src.equipo || '';
    els.equipoMarca.value = src.marca || '';
    els.equipoSerie.value = src.serie || '';
    els.equipoModelo.value = src.modelo || '';
    els.equipoRiesgo.value = src.clasificacion_riesgo || '';
    els.equipoUbicacion.value = src.ubicacion || '';
    els.equipoEstado.value = src.estado || '';
    setTriSelect(els.equipoAplicaMp, src.aplica_mp);
    els.equipoFreqMp.value = src.freq_mp ?? '';
    els.equipoTiempoMp.value = src.tiempo_mp ?? '';
    setTriSelect(els.equipoAplicaCal, src.aplica_cal);
    els.equipoFreqCal.value = src.freq_cal ?? '';
    els.equipoTiempoCal.value = src.tiempo_cal ?? '';
    setTriSelect(els.equipoAplicaVal, src.aplica_val);
    els.equipoFreqVal.value = src.freq_val ?? '';
    els.equipoTiempoVal.value = src.tiempo_val ?? '';
    renderEquipoExtra(src);
    els.equipoModal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeEquipoModal() {
    if (!els.equipoModal) return;
    els.equipoModal.hidden = true;
    document.body.style.overflow = '';
  }

  const invEjState = { equipoId: null, page: 1, total: 0, equipo: null };

  function closeInvEjecucionModal() {
    const modal = document.getElementById('inv-ejecucion-modal');
    if (!modal) return;
    modal.hidden = true;
    document.body.style.overflow = '';
  }

  async function loadInvEjecucion() {
    const body = document.getElementById('inv-ej-body');
    if (!invEjState.equipoId || !body) return;
    const { response, data } = await api(
      `/api/inventario/${invEjState.equipoId}/ejecucion?page=${invEjState.page}&page_size=10`
    );
    if (!response.ok || !data.ok) {
      body.innerHTML = `<tr><td colspan="5">${escapeHtml(data.error || 'No se pudo cargar el historial.')}</td></tr>`;
      return;
    }
    invEjState.total = Number(data.total || 0);
    invEjState.equipo = data.equipo || invEjState.equipo;
    const label = document.getElementById('inv-ejecucion-equipo');
    if (label && data.equipo) {
      label.textContent = `${data.equipo.equipo || 'Equipo'} · biomédica ${data.equipo.codigo_biomedica || '—'} · activo ${data.equipo.codigo_activo || '—'}`;
    }
    const items = data.items || [];
    if (!items.length) {
      body.innerHTML =
        '<tr><td colspan="5">Sin historial. Puede registrar ejecución manual; inventario, suficiencia y KPIs siguen disponibles.</td></tr>';
    } else {
      body.innerHTML = items
        .map(
          (row) => `<tr>
            <td>${escapeHtml((row.fecha_ejecucion || '').toString().slice(0, 10))}</td>
            <td>${escapeHtml(row.tipo_mantenimiento || '—')}</td>
            <td>${row.duracion_horas != null ? escapeHtml(String(row.duracion_horas)) : '—'}</td>
            <td>${escapeHtml(row.fuente || '—')}</td>
            <td>${escapeHtml(row.observaciones || '—')}</td>
          </tr>`
        )
        .join('');
    }
    const pager = document.getElementById('inv-ej-pager');
    const pageLabel = document.getElementById('inv-ej-page-label');
    const pages = Math.max(1, Math.ceil(invEjState.total / 10));
    if (pager) pager.hidden = invEjState.total <= 10;
    if (pageLabel) {
      const from = invEjState.total ? (invEjState.page - 1) * 10 + 1 : 0;
      const to = Math.min(invEjState.page * 10, invEjState.total);
      pageLabel.textContent = invEjState.total ? `${from}–${to} de ${invEjState.total}` : '';
    }
    const prev = document.getElementById('inv-ej-prev');
    const next = document.getElementById('inv-ej-next');
    if (prev) prev.disabled = invEjState.page <= 1;
    if (next) next.disabled = invEjState.page >= pages;
    const form = document.getElementById('inv-ejecucion-form');
    if (form) form.hidden = !(can('modify_inventory') || can('access_servicio'));
  }

  async function openInvEjecucionModal(equipoId) {
    const modal = document.getElementById('inv-ejecucion-modal');
    if (!modal) return;
    invEjState.equipoId = Number(equipoId);
    invEjState.page = 1;
    document.getElementById('inv-ej-equipo-id').value = String(equipoId);
    document.getElementById('inv-ejecucion-form')?.reset();
    document.getElementById('inv-ej-equipo-id').value = String(equipoId);
    const msg = document.getElementById('inv-ej-msg');
    if (msg) {
      msg.hidden = true;
      msg.textContent = '';
    }
    const eqLabel = document.getElementById('inv-ejecucion-equipo');
    const cached = inventarioCache.find((e) => Number(e.id) === Number(equipoId));
    if (eqLabel) {
      const name = cached
        ? `${cached.equipo || 'Equipo'} · ${cached.num_biomedica || cached.codigo_activo || ''}`.trim()
        : '';
      eqLabel.innerHTML = `${escapeHtml(name)}${window.AtlasOps.equipoAlertaMarkup(cached)}`;
    }
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    await loadInvEjecucion();
  }

  async function loadInventario(servicioId, opts = {}) {
    if (!servicioId) return;
    if (opts.resetPage) inventarioPage = 1;
    const pageSize = Math.max(10, Number(els.inventarioPageSize?.value) || 50);
    const params = new URLSearchParams();
    params.set('page', String(inventarioPage || 1));
    params.set('page_size', String(pageSize));
    const q = (els.inventarioSearch?.value || '').trim();
    if (q) params.set('q', q);
    const { response, data } = await api(`/api/servicios/${servicioId}/inventario?${params.toString()}`);
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo cargar inventario.', 'error');
      return;
    }
    inventarioCache = data.inventario || [];
    inventarioTotalHint = Number(data.total || inventarioCache.length) || 0;
    inventarioServerPaged = Boolean(data.server_paged);
    inventarioFilteredTotal = Number(
      data.filtered_total != null ? data.filtered_total : data.total || inventarioCache.length
    ) || 0;
    if (inventarioServerPaged && data.page) inventarioPage = Number(data.page) || 1;
    inventarioRecycle = data.recycle || null;
    renderInventarioRecycle();
    renderInventarioTable();
    if (els.inventarioCrear) {
      const canCreate = can('modify_inventory') || can('access_servicio');
      els.inventarioCrear.hidden = !canCreate || !servicioId;
    }
  }

  function normalizeInvSearch(text) {
    return String(text || '')
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/\s+/g, ' ');
  }

  function filterInventarioRows(rows, query) {
    const q = normalizeInvSearch(query);
    if (!q) return rows;
    // Cada palabra debe coincidir en #BIOMÉDICA, código de activo o EQUIPO.
    const tokens = q.split(' ').filter(Boolean);
    return rows.filter((e) => {
      const bio = normalizeInvSearch(e.num_biomedica);
      const activo = normalizeInvSearch(e.codigo_activo);
      const equipo = normalizeInvSearch(e.equipo);
      const haystack = `${bio} ${activo} ${equipo}`;
      return tokens.every(
        (token) =>
          bio.includes(token) || activo.includes(token) || equipo.includes(token) || haystack.includes(token)
      );
    });
  }

  function highlightInvMatch(text, query) {
    const raw = String(text || '');
    const q = normalizeInvSearch(query);
    if (!q || !raw) return escapeHtml(raw);
    const tokens = q.split(' ').filter(Boolean);
    if (!tokens.length) return escapeHtml(raw);

    // Resalta la primera coincidencia de cualquier token (case-insensitive, sin acentos).
    const normRaw = normalizeInvSearch(raw);
    let best = null;
    tokens.forEach((token) => {
      const idx = normRaw.indexOf(token);
      if (idx < 0) return;
      if (!best || idx < best.idx) best = { idx, len: token.length };
    });
    if (!best) return escapeHtml(raw);

    // Mapear índice normalizado ≈ índice original (aprox. suficiente para resaltar).
    const start = best.idx;
    const end = Math.min(raw.length, start + best.len);
    const before = raw.slice(0, start);
    const mid = raw.slice(start, end);
    const after = raw.slice(end);
    return `${escapeHtml(before)}<mark class="inv-search-mark">${escapeHtml(mid)}</mark>${escapeHtml(after)}`;
  }

  function renderInventarioTable() {
    if (!els.inventarioTableBody) return;
    const searchEl = els.inventarioSearch || document.getElementById('inventario-search');
    const query = searchEl?.value || '';
    const rows = inventarioServerPaged
      ? inventarioCache
      : filterInventarioRows(inventarioCache, query);

    if (els.inventarioSearchHint) {
      if (!inventarioTotalHint && !inventarioCache.length) {
        els.inventarioSearchHint.hidden = true;
        els.inventarioSearchHint.textContent = '';
      } else if (normalizeInvSearch(query)) {
        const shown = inventarioServerPaged ? inventarioFilteredTotal : rows.length;
        const universe = inventarioServerPaged ? inventarioTotalHint : inventarioCache.length;
        els.inventarioSearchHint.hidden = false;
        els.inventarioSearchHint.textContent = inventarioServerPaged
          ? `Mostrando ${shown} de ${universe} equipo(s) · filtro en servidor (#BIOMÉDICA / activo / EQUIPO)`
          : `Mostrando ${shown} de ${universe} equipo(s) · filtro: #BIOMÉDICA / activo / EQUIPO`;
      } else {
        els.inventarioSearchHint.hidden = true;
        els.inventarioSearchHint.textContent = '';
      }
    }

    if (!inventarioCache.length && !(inventarioServerPaged && inventarioFilteredTotal === 0 && normalizeInvSearch(query))) {
      const pending = Boolean(inventarioRecycle?.pending && inventarioRecycle?.can_restore);
      els.inventarioTableBody.innerHTML = pending
        ? '<tr><td colspan="11">Inventario vaciado. Restaure el último backup dentro de la ventana de 30 minutos o importe un CSV nuevo.</td></tr>'
        : '<tr><td colspan="11">Sin equipos. Use «Crear equipo» o importe un CSV (ADMIN/Dirección).</td></tr>';
      if (els.inventarioPager) els.inventarioPager.hidden = true;
      if (inventarioTotalHint === 0) return;
    }
    if (!rows.length) {
      els.inventarioTableBody.innerHTML =
        '<tr><td colspan="11">Ningún equipo coincide con la búsqueda (#BIOMÉDICA, código de activo o EQUIPO).</td></tr>';
      if (els.inventarioPager) els.inventarioPager.hidden = true;
      return;
    }

    const pageSize = Math.max(10, Number(els.inventarioPageSize?.value) || 50);
    let pages;
    let start;
    let pageRows;
    if (inventarioServerPaged) {
      pages = Math.max(1, Math.ceil(inventarioFilteredTotal / pageSize));
      if (inventarioPage > pages) inventarioPage = pages;
      if (inventarioPage < 1) inventarioPage = 1;
      start = (inventarioPage - 1) * pageSize;
      pageRows = rows;
    } else {
      pages = Math.max(1, Math.ceil(rows.length / pageSize));
      if (inventarioPage > pages) inventarioPage = pages;
      if (inventarioPage < 1) inventarioPage = 1;
      start = (inventarioPage - 1) * pageSize;
      pageRows = rows.slice(start, start + pageSize);
    }
    const listed = inventarioServerPaged ? inventarioFilteredTotal : rows.length;
    if (els.inventarioPager) {
      els.inventarioPager.hidden = listed <= pageSize && inventarioTotalHint <= pageSize;
      if (els.inventarioPageLabel) {
        const extra =
          inventarioServerPaged && inventarioFilteredTotal !== inventarioTotalHint
            ? ` · filtrado de ${inventarioTotalHint}`
            : inventarioTotalHint > inventarioCache.length && !inventarioServerPaged
              ? ` · servidor limitó a ${inventarioCache.length} de ${inventarioTotalHint}`
              : '';
        const from = listed ? start + 1 : 0;
        const to = start + pageRows.length;
        els.inventarioPageLabel.textContent = `${from}–${to} de ${listed}${extra}`;
      }
      if (els.inventarioPrev) els.inventarioPrev.disabled = inventarioPage <= 1;
      if (els.inventarioNext) els.inventarioNext.disabled = inventarioPage >= pages;
    }

    const canEdit = can('modify_inventory') || can('access_servicio');
    const hasQuery = Boolean(normalizeInvSearch(query));
    els.inventarioTableBody.innerHTML = pageRows
      .map(
        (e) => `
        <tr class="${hasQuery ? 'inv-row--match' : ''}">
          <td>${hasQuery ? highlightInvMatch(e.num_biomedica, query) : escapeHtml(e.num_biomedica || '')}</td>
          <td>${hasQuery ? highlightInvMatch(e.codigo_activo, query) : escapeHtml(e.codigo_activo || '')}</td>
          <td>${escapeHtml(e.registro_invima || '')}</td>
          <td>${hasQuery ? highlightInvMatch(e.equipo, query) : escapeHtml(e.equipo || '')}${window.AtlasOps.equipoAlertaMarkup(e)}</td>
          <td>${escapeHtml(e.marca || '')}</td>
          <td>${escapeHtml(e.serie || '')}</td>
          <td>${escapeHtml(e.modelo || '')}</td>
          <td>${escapeHtml(e.clasificacion_riesgo || '')}</td>
          <td>${escapeHtml(e.ubicacion || '')}</td>
          <td>${escapeHtml(e.estado || '—')}</td>
          <td class="table-actions">
            ${
              canEdit
                ? `<div class="table-actions__row">
                     <button type="button" class="btn btn-ghost" data-edit-equipo="${e.id}">Editar</button>
                     <button type="button" class="btn btn-ghost" data-historial-equipo="${e.id}">Historial</button>
                     <button type="button" class="btn btn-ghost" data-delete-equipo="${e.id}">Eliminar</button>
                   </div>`
                : `<button type="button" class="btn btn-ghost" data-historial-equipo="${e.id}">Historial</button>`
            }
          </td>
        </tr>`
      )
      .join('');
  }

  /* Catálogo de empresas y asignación de personal a sedes. */
  function renderEmpresasCatalog() {
    if (!els.empresasList) return;
    if (els.empresasDetail) {
      els.empresasDetail.hidden = true;
      els.empresasDetail.innerHTML = '';
    }
    els.empresasList.hidden = false;

    if (!empresasCache.length) {
      els.empresasList.innerHTML = '<p class="empty">No hay empresas registradas.</p>';
      return;
    }

    els.empresasList.innerHTML = empresasCache
      .map((e) => {
        const sedesCount = (e.sedes || []).length;
        const serviciosCount = (e.sedes || []).reduce(
          (acc, s) => acc + (s.servicios || []).length,
          0
        );
        return `
        <button type="button" class="empresas-card" data-select-empresa-catalog="${e.id}">
          <h3>${escapeHtml(e.ID_Empresa)}</h3>
          <p class="field-hint">NIT ${escapeHtml(e.ID_NIT)}</p>
          <p class="empresas-card__meta">
            ${sedesCount} sede${sedesCount === 1 ? '' : 's'} ·
            ${serviciosCount} servicio${serviciosCount === 1 ? '' : 's'}
          </p>
        </button>`;
      })
      .join('');
  }

  function fillAssignEmpresaSelect(selectedId = '') {
    if (!els.assignEmpresa) return;
    els.assignEmpresa.innerHTML = '<option value="">Selecciona empresa</option>';
    empresasCache.forEach((e) => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = `${e.ID_Empresa} · ${e.ID_NIT}`;
      if (String(e.id) === String(selectedId)) opt.selected = true;
      els.assignEmpresa.appendChild(opt);
    });
  }

  function fillAssignSedeSelect(empresaId, selectedSedeId = '') {
    if (!els.assignSede) return;
    els.assignSede.innerHTML = '<option value="">Selecciona sede</option>';
    const empresa = empresasCache.find((e) => Number(e.id) === Number(empresaId));
    (empresa?.sedes || []).forEach((s) => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = `${s.ID_sede} · ${s.name_sede}`;
      if (String(s.id) === String(selectedSedeId)) opt.selected = true;
      els.assignSede.appendChild(opt);
    });
  }

  function fillAssignUserSelect(personal, selectedUserId = '') {
    if (!els.assignUser) return;
    els.assignUser.innerHTML = '<option value="">Selecciona personal</option>';
    (personal || []).forEach((u) => {
      const opt = document.createElement('option');
      opt.value = u.id_usuario;
      opt.textContent = `${u.NAME_USER} ${u.LAST_NAME_USER} · ${u.JOB} (${u.ROLL})`;
      if (String(u.id_usuario) === String(selectedUserId)) opt.selected = true;
      els.assignUser.appendChild(opt);
    });
  }

  async function loadEmpresaPersonal(empresaId) {
    if (!empresaId) {
      empresasEmpresaPersonal = [];
      fillAssignUserSelect([]);
      return [];
    }
    const { response, data } = await api(`/api/empresas/${empresaId}/personal`);
    if (!response.ok || !data.ok) {
      empresasEmpresaPersonal = [];
      fillAssignUserSelect([]);
      showToast(data.error || 'No se pudo cargar el personal.', 'error');
      return [];
    }
    empresasEmpresaPersonal = data.personal || [];
    fillAssignUserSelect(empresasEmpresaPersonal);
    return empresasEmpresaPersonal;
  }

  async function syncAssignFormForEmpresa(empresaId, sedeId = '') {
    fillAssignEmpresaSelect(empresaId || '');
    fillAssignSedeSelect(empresaId || '', sedeId || '');
    await loadEmpresaPersonal(empresaId || '');
  }

  function renderEmpresasDetail(empresaId) {
    if (!els.empresasDetail || !els.empresasList) return;
    const empresa = empresasCache.find((e) => Number(e.id) === Number(empresaId));
    if (!empresa) {
      empresasSelectedId = null;
      empresasSelectedSedeId = null;
      renderEmpresasCatalog();
      return;
    }

    empresasSelectedId = empresa.id;
    empresasSelectedSedeId = null;
    els.empresasList.hidden = true;

    const sedes = empresa.sedes || [];
    const sedesHtml = sedes.length
      ? `<div class="empresas-detail__grid">${sedes
          .map((sede) => {
            const servicios = sede.servicios || [];
            const areasHtml = servicios.length
              ? `<ul class="empresas-areas-list">${servicios
                  .map(
                    (srv) =>
                      `<li>${escapeHtml(srv.name_servicio)}</li>`
                  )
                  .join('')}</ul>`
              : '<p class="field-hint">Sin áreas</p>';
            return `
            <button type="button" class="empresas-sede-card" data-select-sede="${sede.id}">
              <p class="empresas-sede-card__code">${escapeHtml(sede.ID_sede)}</p>
              <h4>${escapeHtml(sede.name_sede)}</h4>
              <p class="empresas-sede-card__label">Áreas</p>
              ${areasHtml}
            </button>`;
          })
          .join('')}</div>
        <div id="empresas-sede-personal" class="empresas-sede-personal" hidden></div>`
      : '<p class="empty">Sin sedes en esta empresa.</p>';

    els.empresasDetail.hidden = false;
    els.empresasDetail.innerHTML = `
      <div class="empresas-detail__toolbar">
        <button type="button" class="btn btn-ghost btn-sm" data-empresas-back>← Catálogo</button>
      </div>
      <header class="empresas-detail__head">
        <div class="empresas-detail__head-copy">
          <p class="eyebrow">Empresa</p>
          <h3>${escapeHtml(empresa.ID_Empresa)}</h3>
          <p class="field-hint">NIT ${escapeHtml(empresa.ID_NIT)} · ${sedes.length} sede${
            sedes.length === 1 ? '' : 's'
          }</p>
        </div>
        ${
          canDeleteEmpresa()
            ? `<button type="button" class="btn btn-ghost btn-sm empresas-danger-btn" data-delete-empresa="${empresa.id}">
                 Eliminar empresa
               </button>`
            : ''
        }
      </header>
      <p class="field-hint empresas-detail__hint">Selecciona una sede para ver el personal asignado.</p>
      ${sedesHtml}`;

    syncAssignFormForEmpresa(empresa.id);
  }

  async function showSedePersonal(sedeId) {
    const panel = document.getElementById('empresas-sede-personal');
    if (!panel) return;
    const empresa = empresasCache.find((e) => Number(e.id) === Number(empresasSelectedId));
    const sede = (empresa?.sedes || []).find((s) => Number(s.id) === Number(sedeId));
    if (!sede) return;

    empresasSelectedSedeId = sede.id;
    els.empresasDetail
      ?.querySelectorAll('.empresas-sede-card')
      .forEach((card) => {
        card.classList.toggle(
          'is-selected',
          Number(card.dataset.selectSede) === Number(sedeId)
        );
      });

    panel.hidden = false;
    panel.innerHTML = '<p class="field-hint">Cargando personal…</p>';
    fillAssignSedeSelect(empresasSelectedId, sede.id);

    const { response, data } = await api(`/api/sedes/${sedeId}/personal`);
    if (!response.ok || !data.ok) {
      panel.innerHTML = `<p class="field-hint">${escapeHtml(
        data.error || 'No se pudo cargar el personal de la sede.'
      )}</p>`;
      return;
    }

    const personal = data.personal || [];
    const listHtml = personal.length
      ? `<ul class="empresas-personal-list">${personal
          .map(
            (p) => `
          <li>
            <strong>${escapeHtml(p.NAME_USER)} ${escapeHtml(p.LAST_NAME_USER)}</strong>
            <span>${escapeHtml(jobLabel(p.JOB))} · ${escapeHtml(rollLabel(p.ROLL))}</span>
          </li>`
          )
          .join('')}</ul>`
      : '<p class="field-hint">No hay personal asignado a esta sede.</p>';

    const actions = [];
    if (canDownloadInventarioPdf()) {
      actions.push(`
        <button type="button" class="btn btn-ghost btn-sm" data-export-sede-inv="pdf" data-sede-id="${sede.id}">
          Plantilla PDF
        </button>`);
    }
    if (canDeleteSede()) {
      actions.push(`
        <button type="button" class="btn btn-ghost btn-sm empresas-danger-btn" data-delete-sede="${sede.id}">
          Eliminar sede
        </button>`);
    }

    panel.innerHTML = `
      <header class="empresas-sede-personal__head">
        <div class="empresas-detail__head-copy">
          <p class="eyebrow">Personal de la sede</p>
          <h4>${escapeHtml(sede.name_sede)}</h4>
          <p class="field-hint">${personal.length} persona${
            personal.length === 1 ? '' : 's'
          }</p>
        </div>
        ${actions.length ? `<div class="empresas-detail__actions">${actions.join('')}</div>` : ''}
      </header>
      ${listHtml}`;
  }

  async function loadEmpresasPanel(opts = {}) {
    const { data } = await api('/api/empresas');
    if (!data.ok) {
      showToast(data.error || 'Error al cargar empresas.', 'error');
      return;
    }
    empresasCache = data.empresas || [];
    if (opts.empresaId) {
      renderEmpresasDetail(opts.empresaId);
      if (opts.sedeId) await showSedePersonal(opts.sedeId);
    } else {
      empresasSelectedId = null;
      empresasSelectedSedeId = null;
      renderEmpresasCatalog();
    }

    if (els.sedeEmpresaSelect) {
      els.sedeEmpresaSelect.innerHTML = '<option value="">Selecciona empresa</option>';
      empresasCache.forEach((e) => {
        const opt = document.createElement('option');
        opt.value = e.id;
        opt.textContent = `${e.ID_Empresa} (${e.ID_NIT})`;
        els.sedeEmpresaSelect.appendChild(opt);
      });
    }

    const canCreateEmpresa = can('create_empresa') || currentUser?.ROLL === 'ADMIN';
    const canCreateSede = can('create_sede');
    const canAssign = can('assign_sede_coordinators');

    if (els.empresaFormWrap) els.empresaFormWrap.hidden = !canCreateEmpresa;
    if (els.sedeFormWrap) els.sedeFormWrap.hidden = !canCreateSede;
    if (els.assignFormWrap) els.assignFormWrap.hidden = !canAssign;
    if (els.empresaForm) els.empresaForm.hidden = false;
    if (els.sedeForm) els.sedeForm.hidden = false;
    if (els.assignForm) els.assignForm.hidden = false;

    if (els.empresaSedesBuilder && !els.empresaSedesBuilder.children.length) {
      addSedeBuilderRow(els.empresaSedesBuilder);
    }

    if (canAssign) {
      fillAssignEmpresaSelect();
      fillAssignSedeSelect('');
      fillAssignUserSelect([]);
    }
  }

  /* Vista Dirección: resumen de inventario y exportación. */
  function summarizeInventario(inventario) {
    const counts = {};
    (inventario || []).forEach((item) => {
      const key = String(item.equipo || '').trim() || 'Sin nombre';
      counts[key] = (counts[key] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([equipo, count]) => ({ equipo, count }))
      .sort((a, b) => b.count - a.count || a.equipo.localeCompare(b.equipo, 'es'));
  }

  function equipoTypeKey(value) {
    return String(value || '').trim() || 'Sin nombre';
  }

  const DIRECCION_INV_HEADERS = [
    '#BIOMÉDICA',
    'REGISTRO INVIMA',
    'EQUIPO',
    'MARCA',
    'SERIE',
    'MODELO',
    'CLASIFICACIÓN RIESGO',
    'UBICACIÓN',
    'ESTADO',
  ];
  const DIRECCION_INV_FIELDS = [
    'num_biomedica',
    'registro_invima',
    'equipo',
    'marca',
    'serie',
    'modelo',
    'clasificacion_riesgo',
    'ubicacion',
    'estado',
  ];

  function sanitizeFilenamePart(value) {
    return String(value || 'equipos')
      .trim()
      .replace(/[^\w\-áéíóúÁÉÍÓÚñÑüÜ]+/g, '_')
      .replace(/_+/g, '_')
      .slice(0, 40) || 'equipos';
  }

  function triggerBlobDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function csvEscapeCell(value) {
    const text = String(value ?? '');
    if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
    return text;
  }

  function buildInventarioCsv(rows) {
    const lines = [DIRECCION_INV_HEADERS.map(csvEscapeCell).join(',')];
    (rows || []).forEach((row) => {
      lines.push(
        DIRECCION_INV_FIELDS.map((field) => csvEscapeCell(row[field] ?? '')).join(',')
      );
    });
    return `\ufeff${lines.join('\r\n')}`;
  }

  function buildInventarioSpreadsheetMl(rows) {
    const escapeXml = (value) =>
      String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    const cell = (value) =>
      `<Cell><Data ss:Type="String">${escapeXml(value)}</Data></Cell>`;
    const headerRow = `<Row>${DIRECCION_INV_HEADERS.map(cell).join('')}</Row>`;
    const dataRows = (rows || [])
      .map(
        (row) =>
          `<Row>${DIRECCION_INV_FIELDS.map((field) => cell(row[field] ?? '')).join(
            ''
          )}</Row>`
      )
      .join('');
    return `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="inventario">
  <Table>
   ${headerRow}
   ${dataRows}
  </Table>
 </Worksheet>
</Workbook>`;
  }

  function exportDireccionModalInventario(format) {
    const rows = direccionInvModalRows || [];
    const tipo = direccionInvModalEquipoTipo || 'equipos';
    if (!rows.length) {
      showToast('No hay registros de este tipo para exportar.', 'error');
      return;
    }
    const base = `inventario_${sanitizeFilenamePart(tipo)}`;
    if (format === 'xlsx') {
      const xml = buildInventarioSpreadsheetMl(rows);
      const blob = new Blob([xml], {
        type: 'application/vnd.ms-excel;charset=utf-8',
      });
      triggerBlobDownload(blob, `${base}.xls`);
      showToast(`Excel exportado: ${rows.length} × ${tipo}.`, 'success');
      return;
    }
    const csv = buildInventarioCsv(rows);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    triggerBlobDownload(blob, `${base}.csv`);
    showToast(`CSV exportado: ${rows.length} × ${tipo}.`, 'success');
  }

  function canDownloadInventarioPdf() {
    return can('view_inventory') || can('export_inventory');
  }

  function canDeleteEmpresa() {
    return can('delete_empresa') || can('create_empresa') || currentUser?.ROLL === 'ADMIN';
  }

  function canDeleteSede() {
    return can('delete_sede') || can('create_sede') || currentUser?.ROLL === 'ADMIN';
  }

  function renderDireccionModalExportActions() {
    const buttons = [];
    if (canDownloadInventarioPdf()) {
      buttons.push(`
        <button type="button" class="btn btn-ghost btn-sm" data-export-inv-modal="pdf">
          Plantilla PDF
        </button>`);
    }
    if (can('export_inventory')) {
      buttons.push(`
        <button type="button" class="btn btn-ghost btn-sm" data-export-inv-modal="csv">
          Exportar CSV
        </button>
        <button type="button" class="btn btn-ghost btn-sm" data-export-inv-modal="xlsx">
          Exportar XLSX
        </button>`);
    }
    if (!buttons.length) return '';
    return `<div class="inventario-export-actions">${buttons.join('')}</div>`;
  }

  async function exportInventarioServicio(servicioId, format, equipoTipo = null) {
    if (!servicioId) {
      showToast('Selecciona un servicio.', 'error');
      return;
    }
    const isPdf = format === 'pdf';
    if (isPdf && !canDownloadInventarioPdf()) {
      showToast('No tienes permiso para descargar la plantilla PDF.', 'error');
      return;
    }
    if (!isPdf && !can('export_inventory')) {
      showToast('No tienes permiso para exportar inventario.', 'error');
      return;
    }
    const ext = isPdf ? 'pdf' : format === 'xlsx' ? 'xlsx' : 'csv';
    const params = new URLSearchParams();
    const equipo = String(equipoTipo || '').trim();
    if (equipo) params.set('equipo', equipo);
    const query = params.toString();
    const path = isPdf
      ? `/api/servicios/${servicioId}/inventario/export/pdf${query ? `?${query}` : ''}`
      : `/api/servicios/${servicioId}/inventario/export.${ext}${
          query ? `?${query}` : ''
        }`;
    const fallback = equipo
      ? `inventario_${equipo.replace(/\s+/g, '_')}.${ext}`
      : `inventario.${ext}`;
    try {
      const result = await downloadFile(path, fallback);
      const n = Number(result?.count || 0);
      showToast(
        isPdf
          ? n
            ? `Plantilla PDF descargada (${n} equipo${n === 1 ? '' : 's'}).`
            : 'Plantilla PDF descargada (sin equipos cargados).'
          : equipo
            ? `${ext.toUpperCase()} exportado (${equipo}).`
            : `${ext.toUpperCase()} exportado.`,
        'success'
      );
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function exportInventarioSede(sedeId) {
    if (!sedeId) {
      showToast('Selecciona una sede.', 'error');
      return;
    }
    if (!canDownloadInventarioPdf()) {
      showToast('No tienes permiso para descargar la plantilla PDF.', 'error');
      return;
    }
    try {
      const result = await downloadFile(
        `/api/sedes/${sedeId}/inventario/export/pdf`,
        'inventario_sede.pdf'
      );
      const n = Number(result?.count || 0);
      showToast(
        n
          ? `Ficha PDF de la sede descargada (${n} equipo${n === 1 ? '' : 's'}).`
          : 'Ficha PDF de la sede descargada (sin equipos cargados).',
        'success'
      );
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  async function deleteEmpresaById(empresaId) {
    const empresa = empresasCache.find((e) => Number(e.id) === Number(empresaId));
    const nombre = empresa?.ID_Empresa || 'esta empresa';
    const nit = empresa?.ID_NIT || '';
    const sedesN = (empresa?.sedes || []).length;
    const ok = window.confirm(
      `Se eliminará la empresa «${nombre}»${nit ? ` (NIT ${nit})` : ''}.\n` +
        `También se borrarán ${sedesN} sede(s), sus servicios y todo el inventario cargado.\n` +
        `El personal quedará sin empresa asignada.\n\n` +
        `Esta acción no se puede deshacer. ¿Continuar?`
    );
    if (!ok) return;
    const { response, data } = await api(`/api/empresas/${empresaId}/eliminar`, {
      method: 'POST',
      body: '{}',
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo eliminar la empresa.', 'error');
      return;
    }
    showToast(data.message, 'success');
    navigateTo({ panel: 'empresas', sectionId: 'organizacion' }, { replace: true });
    if (typeof loadSedes === 'function') loadSedes();
  }

  async function deleteSedeById(sedeId) {
    const empresa = empresasCache.find((e) => Number(e.id) === Number(empresasSelectedId));
    const sede = (empresa?.sedes || []).find((s) => Number(s.id) === Number(sedeId));
    const nombre = sede?.name_sede || 'esta sede';
    const nServicios = (sede?.servicios || []).length;
    const ok = window.confirm(
      `Se eliminará la sede «${nombre}», ${nServicios} servicio(s) y todo el inventario cargado en ella.\n` +
        `El personal asignado a esta sede perderá esa asignación.\n\n` +
        `Esta acción no se puede deshacer. ¿Continuar?`
    );
    if (!ok) return;
    const { response, data } = await api(`/api/sedes/${sedeId}/eliminar`, {
      method: 'POST',
      body: '{}',
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo eliminar la sede.', 'error');
      return;
    }
    showToast(data.message, 'success');
    const keepEmpresa = empresasSelectedId;
    navigateTo(
      {
        panel: 'empresas',
        sectionId: 'organizacion',
        empresaId: keepEmpresa || null,
      },
      { replace: true }
    );
    if (typeof loadSedes === 'function') loadSedes();
  }

  function renderInventarioExportActions(
    servicioId,
    { compact = false, equipoTipo = null, shortLabels = false } = {}
  ) {
    const sizeClass = compact ? 'btn-sm' : '';
    const equipoAttr = equipoTipo
      ? ` data-equipo="${escapeHtml(equipoTipo)}"`
      : '';
    const buttons = [];
    if (canDownloadInventarioPdf()) {
      const pdfLabel = shortLabels ? 'PDF' : 'Plantilla PDF';
      buttons.push(`
        <button type="button" class="btn btn-ghost ${sizeClass}" data-export-inv="pdf" data-servicio-id="${servicioId}"${equipoAttr}>
          ${pdfLabel}
        </button>`);
    }
    if (can('export_inventory')) {
      const csvLabel = shortLabels ? 'CSV' : 'Exportar CSV';
      const xlsxLabel = shortLabels ? 'XLSX' : 'Exportar XLSX';
      buttons.push(`
        <button type="button" class="btn btn-ghost ${sizeClass}" data-export-inv="csv" data-servicio-id="${servicioId}"${equipoAttr}>
          ${csvLabel}
        </button>
        <button type="button" class="btn btn-ghost ${sizeClass}" data-export-inv="xlsx" data-servicio-id="${servicioId}"${equipoAttr}>
          ${xlsxLabel}
        </button>`);
    }
    if (!buttons.length) return '';
    return `<div class="inventario-export-actions">${buttons.join('')}</div>`;
  }

  function renderDireccionResumen(counts, total, servicioId) {
    const exportActions = renderInventarioExportActions(servicioId, {
      compact: true,
      shortLabels: true,
    });
    if (!total) {
      return `
        <p class="field-hint">Sin equipos en inventario.</p>
        ${exportActions}`;
    }
    const chips = counts
      .map(
        (row) =>
          `<li>
            <button
              type="button"
              class="direccion-equipo-chip"
              data-open-inv-tipo="${escapeHtml(row.equipo)}"
              data-servicio-id="${servicioId}"
              title="Ver detalle: ${escapeHtml(row.equipo)}"
            >
              <span class="direccion-equipo-chip__name">${escapeHtml(row.equipo)}</span>
              <strong class="direccion-equipo-chip__count">${row.count}</strong>
            </button>
          </li>`
      )
      .join('');
    return `
      <div class="direccion-servicio__toolbar">
        <p class="direccion-equipo-total">${total} equipo${total === 1 ? '' : 's'}</p>
        ${
          can('access_servicio')
            ? `<button type="button" class="btn btn-primary btn-sm" data-open-servicio="${servicioId}">
                 Tratar información
               </button>`
            : ''
        }
        ${exportActions}
      </div>
      <ul class="direccion-equipo-resumen">${chips}</ul>`;
  }

  function openDireccionInvDetalle(servicioId, equipoTipo) {
    const cached = direccionInvCache[servicioId];
    if (!cached?.inventario) {
      showToast('No hay inventario cargado para este servicio.', 'error');
      return;
    }
    direccionInvModalServicioId = servicioId;
    const tipo = equipoTypeKey(equipoTipo);
    direccionInvModalEquipoTipo = tipo;
    const rows = cached.inventario.filter(
      (item) => equipoTypeKey(item.equipo) === tipo
    );
    direccionInvModalRows = rows;

    const details = els.direccionTree?.querySelector(
      `details.direccion-servicio[data-servicio-id="${servicioId}"]`
    );
    const servicioName =
      details?.querySelector('.direccion-servicio__name')?.textContent?.trim() ||
      `Servicio ${servicioId}`;

    if (els.direccionInvTitle) {
      els.direccionInvTitle.textContent = tipo;
    }
    if (els.direccionInvSubtitle) {
      els.direccionInvSubtitle.textContent = `${servicioName} · ${rows.length} registro${
        rows.length === 1 ? '' : 's'
      }`;
    }

    if (els.direccionInvBody) {
      els.direccionInvBody.innerHTML = rows.length
        ? rows
            .map(
              (e) => `
          <tr>
            <td>${escapeHtml(e.num_biomedica || '')}</td>
            <td>${escapeHtml(e.codigo_activo || '')}</td>
            <td>${escapeHtml(e.registro_invima || '')}</td>
            <td>${escapeHtml(e.equipo || '')}</td>
            <td>${escapeHtml(e.marca || '')}</td>
            <td>${escapeHtml(e.serie || '')}</td>
            <td>${escapeHtml(e.modelo || '')}</td>
            <td>${escapeHtml(e.clasificacion_riesgo || '')}</td>
            <td>${escapeHtml(e.ubicacion || '')}</td>
            <td>${escapeHtml(e.estado || '—')}</td>
          </tr>`
            )
            .join('')
        : '<tr><td colspan="10">Sin equipos de este tipo.</td></tr>';
    }

    const exportSlot = document.getElementById('direccion-inv-export');
    if (exportSlot) {
      exportSlot.innerHTML = renderDireccionModalExportActions();
    }

    if (els.direccionInvModal) els.direccionInvModal.hidden = false;
  }

  function closeDireccionInvModal() {
    if (els.direccionInvModal) els.direccionInvModal.hidden = true;
    direccionInvModalServicioId = null;
    direccionInvModalEquipoTipo = null;
    direccionInvModalRows = [];
  }

  function renderDireccionTree(empresaId) {
    if (!els.direccionTree || !els.direccionEmpty) return;
    const empresa = direccionEmpresas.find((e) => Number(e.id) === Number(empresaId));
    if (!empresa) {
      els.direccionTree.hidden = true;
      els.direccionTree.innerHTML = '';
      els.direccionEmpty.hidden = false;
      els.direccionEmpty.textContent =
        'Selecciona una empresa para desplegar sus sedes y servicios.';
      return;
    }

    const sedes = empresa.sedes || [];
    els.direccionEmpty.hidden = true;
    els.direccionTree.hidden = false;

    if (!sedes.length) {
      els.direccionTree.innerHTML =
        '<p class="empty">Esta empresa no tiene sedes registradas.</p>';
      return;
    }

    els.direccionTree.innerHTML = `
      <header class="direccion-empresa-meta">
        <p class="eyebrow">Empresa seleccionada</p>
        <h3>${escapeHtml(empresa.ID_Empresa)}</h3>
        <p class="field-hint">NIT ${escapeHtml(empresa.ID_NIT)} · ${sedes.length} sede${
          sedes.length === 1 ? '' : 's'
        }</p>
      </header>
      <div class="direccion-sedes-grid">
        ${sedes
          .map((sede) => {
            const servicios = sede.servicios || [];
            const serviciosHtml = servicios.length
              ? servicios
                  .map(
                    (srv) => `
                  <details class="direccion-servicio" data-servicio-id="${srv.id}" data-sede-id="${sede.id}" data-empresa-id="${empresa.id}">
                    <summary title="${escapeHtml(srv.ID_servicio)}">
                      <span class="direccion-servicio__name">${escapeHtml(srv.name_servicio)}</span>
                    </summary>
                    <div class="direccion-servicio__body" data-inv-body="${srv.id}">
                      <p class="field-hint">Cargando…</p>
                    </div>
                  </details>`
                  )
                  .join('')
              : '<p class="field-hint">Sin servicios</p>';

            return `
              <section class="direccion-sede" aria-label="${escapeHtml(sede.name_sede)}">
                <header class="direccion-sede__head">
                  <p class="direccion-sede__code">${escapeHtml(sede.ID_sede)}</p>
                  <h3>${escapeHtml(sede.name_sede)}</h3>
                  <p class="field-hint">${servicios.length} servicio${
                    servicios.length === 1 ? '' : 's'
                  }</p>
                </header>
                <div class="direccion-sede__servicios">${serviciosHtml}</div>
              </section>`;
          })
          .join('')}
      </div>`;

    els.direccionTree.querySelectorAll('details.direccion-servicio').forEach((details) => {
      details.addEventListener('toggle', () => {
        if (details.open) loadDireccionServicioResumen(details);
      });
    });
  }

  async function loadDireccionServicioResumen(detailsEl) {
    const servicioId = detailsEl?.dataset?.servicioId;
    if (!servicioId) return;
    const body = detailsEl.querySelector(`[data-inv-body="${servicioId}"]`);
    if (!body) return;

    if (direccionInvCache[servicioId]) {
      const cached = direccionInvCache[servicioId];
      body.innerHTML = renderDireccionResumen(cached.counts, cached.total, servicioId);
      return;
    }

    body.innerHTML = '<p class="field-hint">Cargando resumen…</p>';
    const { response, data } = await api(`/api/servicios/${servicioId}/inventario`);
    if (!response.ok || !data.ok) {
      body.innerHTML = `<p class="field-hint">${escapeHtml(
        data.error || 'No se pudo cargar el inventario.'
      )}</p>`;
      return;
    }

    const inventario = data.inventario || [];
    const counts = summarizeInventario(inventario);
    const total = inventario.length;
    direccionInvCache[servicioId] = { counts, total, inventario };
    body.innerHTML = renderDireccionResumen(counts, total, servicioId);
  }

  async function loadDireccion() {
    if (!els.direccionEmpresa || !els.direccionTree) return;

    const { response, data } = await api('/api/direccion/empresas-sedes');
    if (!response.ok || !data.ok) {
      showToast(data.error || 'Error módulo Dirección.', 'error');
      return;
    }

    direccionEmpresas = data.empresas || [];
    direccionInvCache = {};

    if (!direccionEmpresas.length) {
      els.direccionEmpresa.innerHTML = '<option value="">Sin empresas</option>';
      els.direccionTree.hidden = true;
      els.direccionTree.innerHTML = '';
      if (els.direccionEmpty) {
        els.direccionEmpty.hidden = false;
        els.direccionEmpty.textContent = 'No hay empresas disponibles para tu perfil.';
      }
      return;
    }

    const previous = els.direccionEmpresa.value;
    els.direccionEmpresa.innerHTML = '<option value="">Selecciona empresa</option>';
    direccionEmpresas.forEach((e) => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = `${e.ID_Empresa} · NIT ${e.ID_NIT}`;
      els.direccionEmpresa.appendChild(opt);
    });

    let selected = previous;
    if (
      selected &&
      !direccionEmpresas.some((e) => Number(e.id) === Number(selected))
    ) {
      selected = '';
    }
    if (!selected && direccionEmpresas.length === 1) {
      selected = String(direccionEmpresas[0].id);
    }
    els.direccionEmpresa.value = selected || '';
    renderDireccionTree(els.direccionEmpresa.value);
    loadDireccionEventLog(els.direccionEmpresa.value);
  }

  /* Matriz RBAC de permisos por rol y cargo. */
  function rbacIcon(icono) {
    return RBAC_ICONS[icono] || RBAC_ICONS.module;
  }

  /** Agrupa permisos/módulos según el área de la aplicación que afectan. */
  const RBAC_MODULE_GROUPS = [
    {
      id: 'empresas',
      title: 'Empresas y sedes',
      jobs: [
        'Agregar empresa',
        'Crear y modificar sedes',
        'Acceso a servicio específico',
        'Tablero de forma de adquisición',
        'Dimensionamiento de la empresa',
        'Personal de sedes',
        'Visualización de inventarios y sedes',
        'Alcance por empresa',
        'Configuración del sistema',
      ],
    },
    {
      id: 'inventario',
      title: 'Inventario biomédico',
      jobs: [
        'Importación de inventario',
        'Exportación de datos',
        'Edición de datos clínicos',
        'Acceso a base de datos',
      ],
    },
    {
      id: 'suficiencia',
      title: 'Suficiencia e instrumentos (activar cada módulo por separado)',
      jobs: [
        'Suficiencia de equipos',
        'Actualizar datos de suficiencia',
        'Solicitar actualización de suficiencia',
        'Dimensionamiento de personal',
        'Frecuencia de mantenimiento preventivo',
        'Preinstalación de la tecnología biomédica',
        'KPIs de ingeniería clínica',
        'Instrumento CAPEX',
        'Módulo de ingeniería',
      ],
    },
    {
      id: 'usuarios',
      title: 'Usuarios y cargos',
      jobs: ['Gestión de usuarios', 'Edición de JOBS'],
    },
    {
      id: 'asistencial',
      title: 'Módulo asistencial',
      jobs: [
        'Módulo asistencial',
        'Procesos asistenciales',
        'Gestión de personal asistencial',
      ],
    },
    {
      id: 'solicitudes',
      title: 'Solicitudes y bandeja',
      jobs: ['Aprobar solicitudes', 'Solicitar permisos ampliados', 'Módulo de soporte'],
    },
    {
      id: 'reportes',
      title: 'Reportes e indicadores',
      jobs: [
        'Visualización de reportes',
        'Reporte final de indicadores',
        'Indicadores operativos',
      ],
    },
  ];

  function groupRbacJobs(jobs) {
    const used = new Set();
    const groups = RBAC_MODULE_GROUPS.map((g) => {
      const items = g.jobs
        .map((name) =>
          jobs.find((j) => String(j.nombre_job).toLowerCase() === name.toLowerCase())
        )
        .filter(Boolean);
      items.forEach((j) => used.add(j.id_job));
      return { ...g, items };
    }).filter((g) => g.items.length);

    const leftover = jobs.filter((j) => !used.has(j.id_job));
    if (leftover.length) {
      groups.push({
        id: 'otros',
        title: 'Otros módulos',
        items: leftover.sort((a, b) =>
          String(a.nombre_job).localeCompare(String(b.nombre_job), 'es')
        ),
      });
    }
    return groups;
  }

  function renderRbacPermRow(role, j, locked) {
    const key = `${role.id_rol}:${j.id_job}`;
    const on = locked || Boolean(rbacState.permisos[key]?.permiso_activo);
    const tip = j.descripcion || j.nombre_job;
    const code = j.codigo_permiso ? ` (${j.codigo_permiso})` : '';
    return `
      <li class="rbac-perm-row">
        <div class="rbac-item__icon" title="${escapeHtml(tip)}">${escapeHtml(rbacIcon(j.icono))}</div>
        <div class="rbac-item__meta">
          <strong title="${escapeHtml(tip)}">${escapeHtml(j.nombre_job)}${escapeHtml(code)}</strong>
          <span>${escapeHtml(j.descripcion || 'Sin descripción')}</span>
        </div>
        <label class="rbac-toggle ${on ? 'is-on' : ''}" title="${escapeHtml(tip)}">
          <input type="checkbox" data-matrix-rol="${role.id_rol}" data-matrix-job="${j.id_job}"
            ${on ? 'checked' : ''} ${locked ? 'disabled' : ''} />
          <span></span>
        </label>
      </li>`;
  }

  function countActiveJobs(role, jobs, locked) {
    return jobs.filter((j) => {
      const key = `${role.id_rol}:${j.id_job}`;
      return locked || Boolean(rbacState.permisos[key]?.permiso_activo);
    }).length;
  }

  function renderRbacModuleGroups(role, jobs, locked) {
    const groups = groupRbacJobs(jobs);
    if (!groups.length) {
      return '<p class="field-hint">No hay módulos activos en el catálogo.</p>';
    }
    return groups
      .map((g) => {
        const groupKey = `${role.id_rol}:${g.id}`;
        const open = rbacExpandedGroups.has(groupKey);
        const activeCount = countActiveJobs(role, g.items, locked);
        return `
        <section class="rbac-perm-group ${open ? 'is-open' : ''}" data-group-key="${escapeHtml(groupKey)}">
          <button type="button" class="rbac-perm-group__toggle" data-toggle-group="${escapeHtml(groupKey)}" aria-expanded="${open}">
            <span class="rbac-perm-group__chevron" aria-hidden="true">▸</span>
            <span class="rbac-perm-group__title">${escapeHtml(g.title)}</span>
            <span class="rbac-perm-group__count">${activeCount}/${g.items.length}</span>
          </button>
          <div class="rbac-perm-group__body" ${open ? '' : 'hidden'}>
            <ul class="rbac-perm-group__list">
              ${g.items.map((j) => renderRbacPermRow(role, j, locked)).join('')}
            </ul>
          </div>
        </section>`;
      })
      .join('');
  }

  function renderRbacRoles() {
    if (!els.rbacRolesList) return;
    const roles = rbacState.roles || [];
    if (!roles.length) {
      els.rbacRolesList.innerHTML =
        '<li class="field-hint">No hay roles. Crea el primero abajo.</li>';
      return;
    }

    els.rbacRolesList.innerHTML = roles
      .map((r) => {
        const inactive = r.estado !== 'ACTIVO';
        const selected = Number(rbacSelectedRolId) === Number(r.id_rol);
        const renaming = Number(rbacRenamingRolId) === Number(r.id_rol);
        const deleting = Number(rbacDeletingRolId) === Number(r.id_rol);

        if (renaming && !r.protegido) {
          return `
        <li class="rbac-item is-renaming ${selected ? 'is-selected' : ''}" data-rol-id="${r.id_rol}">
          <form class="rbac-rename-form" data-rename-form="${r.id_rol}">
            <input type="text" name="nombre_rol" value="${escapeHtml(r.nombre_rol)}" required maxlength="80" aria-label="Nuevo nombre del rol" />
            <button type="submit" class="btn btn-primary">Guardar</button>
            <button type="button" class="btn btn-ghost" data-cancel-rename>Cancelar</button>
          </form>
        </li>`;
        }

        if (deleting && !r.protegido) {
          return `
        <li class="rbac-item is-deleting ${selected ? 'is-selected' : ''}" data-rol-id="${r.id_rol}">
          <div class="rbac-item__icon" aria-hidden="true">!</div>
          <div class="rbac-item__meta">
            <strong>¿Eliminar «${escapeHtml(r.nombre_rol)}»?</strong>
            <span>Se borrarán también sus permisos.</span>
          </div>
          <div class="rbac-item__actions">
            <button type="button" class="btn btn-danger" data-confirm-delete-rol="${r.id_rol}">Confirmar</button>
            <button type="button" class="btn btn-ghost" data-cancel-delete>Cancelar</button>
          </div>
        </li>`;
        }

        return `
        <li class="rbac-item ${inactive ? 'is-inactive' : ''} ${selected ? 'is-selected' : ''}" data-rol-id="${r.id_rol}">
          <button type="button" class="rbac-item__select" data-select-rol="${r.id_rol}">
            <div class="rbac-item__icon">${r.protegido ? 'AD' : 'RL'}</div>
            <div class="rbac-item__meta">
              <strong>${escapeHtml(r.nombre_rol)}</strong>
              <span>${escapeHtml(r.estado)}${r.protegido ? ' · protegido' : ''}</span>
            </div>
          </button>
          <div class="rbac-item__actions">
            ${
              r.protegido
                ? ''
                : `<button type="button" class="btn btn-ghost" data-rename-rol="${r.id_rol}">Renombrar</button>
                   <button type="button" class="btn btn-ghost" data-toggle-rol="${r.id_rol}">${r.estado === 'ACTIVO' ? 'Desactivar' : 'Activar'}</button>
                   <button type="button" class="btn btn-ghost btn-danger-text" data-delete-rol="${r.id_rol}">Eliminar</button>`
            }
          </div>
        </li>`;
      })
      .join('');

    if (rbacRenamingRolId != null) {
      const input = els.rbacRolesList.querySelector(
        `[data-rename-form="${rbacRenamingRolId}"] input[name="nombre_rol"]`
      );
      if (input) {
        input.focus();
        input.select();
      }
    }
  }

  function renderRbacRolePerms() {
    if (!els.rbacPermsList || !els.rbacPermsEmpty) return;
    const role = (rbacState.roles || []).find(
      (r) => Number(r.id_rol) === Number(rbacSelectedRolId)
    );
    const jobs = (rbacState.jobs || []).filter((j) => j.estado === 'ACTIVO');

    if (!role) {
      if (els.rbacPermsTitle) els.rbacPermsTitle.textContent = 'Sin rol seleccionado';
      if (els.rbacPermsHint) {
        els.rbacPermsHint.textContent =
          'Los módulos se agrupan en secciones desplegables. Expande cada una para activar o desactivar permisos.';
      }
      if (els.rbacSaveMatrix) els.rbacSaveMatrix.hidden = true;
      els.rbacPermsEmpty.hidden = false;
      els.rbacPermsList.hidden = true;
      els.rbacPermsList.innerHTML = '';
      return;
    }

    const locked = Boolean(role.protegido);
    const activeCount = countActiveJobs(role, jobs, locked);

    if (els.rbacPermsTitle) {
      els.rbacPermsTitle.textContent = locked
        ? `${role.nombre_rol} · acceso total`
        : role.nombre_rol;
    }
    if (els.rbacPermsHint) {
      els.rbacPermsHint.textContent = locked
        ? 'El Administrador siempre tiene todos los módulos activos.'
        : `${activeCount}/${jobs.length} módulos activos. Expande cada sección para editar.`;
    }
    if (els.rbacSaveMatrix) els.rbacSaveMatrix.hidden = locked;

    els.rbacPermsEmpty.hidden = true;
    els.rbacPermsList.hidden = false;
    els.rbacPermsList.innerHTML = `
      ${
        locked
          ? '<p class="field-hint rbac-acc__note">El Administrador mantiene todos los módulos activos. No se edita desde aquí.</p>'
          : ''
      }
      <div class="rbac-acc__groups">
        ${renderRbacModuleGroups(role, jobs, locked)}
      </div>`;
  }

  function applyRbacState(data) {
    rbacState = {
      roles: data.roles || [],
      jobs: data.jobs || [],
      permisos: data.permisos || {},
    };
    const validIds = new Set((rbacState.roles || []).map((r) => Number(r.id_rol)));
    if (rbacSelectedRolId != null && !validIds.has(Number(rbacSelectedRolId))) {
      rbacSelectedRolId = null;
    }
    if (rbacSelectedRolId == null && validIds.size) {
      rbacSelectedRolId = [...validIds][0];
    }
    rbacExpandedGroups = new Set(
      [...rbacExpandedGroups].filter((key) => {
        const rolId = Number(String(key).split(':')[0]);
        return validIds.has(rolId);
      })
    );
    renderRbacRoles();
    renderRbacRolePerms();
  }

  async function loadRbacPanel() {
    if (!els.panelRbac) return;
    const isAdmin = currentUser?.ROLL === 'ADMIN';
    if (els.rbacForbidden) els.rbacForbidden.hidden = isAdmin;
    if (els.rbacContent) els.rbacContent.hidden = !isAdmin;
    if (!isAdmin) return;

    const { response, data } = await api('/admin/rbac/matrix');
    if (response.status === 403) {
      if (els.rbacForbidden) els.rbacForbidden.hidden = false;
      if (els.rbacContent) els.rbacContent.hidden = true;
      showToast(data.error || 'No autorizado.', 'error');
      return;
    }
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo cargar Roles y permisos.', 'error');
      return;
    }
    applyRbacState(data);
    loadBackupsPanel();
  }

  function renderBackupsTable(payload) {
    if (els.backupPaths) {
      const local = payload.local_dir || '';
      const off = payload.offsite_dir || '';
      els.backupPaths.textContent =
        `Local: ${local}  ·  Externa: ${off}  ·  Se conservan los últimos ${payload.keep || 20}.`;
    }
    const rows = payload.backups || [];
    if (!els.backupTableBody) return;
    if (!rows.length) {
      els.backupTableBody.innerHTML =
        '<tr><td colspan="5">Aún no hay respaldos. Pulse «Crear respaldo ahora».</td></tr>';
      return;
    }
    els.backupTableBody.innerHTML = rows
      .map((item) => {
        const files = (item.ok_files || []).join(', ') || '—';
        const offsite = item.offsite ? 'Sí' : 'No';
        return `
        <tr>
          <td>${escapeHtml(item.created_at || item.id || '')}</td>
          <td>${escapeHtml(item.reason || '')}</td>
          <td>${escapeHtml(files)}</td>
          <td>${escapeHtml(offsite)}</td>
          <td>
            <button type="button" class="btn btn-ghost backup-restore-btn" data-id="${escapeHtml(item.id)}">
              Restaurar
            </button>
          </td>
        </tr>`;
      })
      .join('');
  }

  async function loadBackupsPanel() {
    if (!els.backupTableBody) return;
    const { response, data } = await api('/admin/backups');
    if (!response.ok || !data.ok) {
      els.backupTableBody.innerHTML =
        `<tr><td colspan="5">${escapeHtml(data.error || 'No se pudieron listar los respaldos.')}</td></tr>`;
      return;
    }
    renderBackupsTable(data);
  }

  async function loadAdminRoles() {
    const { response, data } = await api('/admin/roles');
    if (!response.ok || !data.ok) return;
    adminJobsByRole = data.jobsByRole || {};
    fillSelectRoles(els.editRoll, data);
  }

  /* Administración de usuarios. */
  function renderUsersTable(users) {
    usersCache = users;
    els.usersTableBody.innerHTML = users
      .map(
        (user) => `
        <tr>
          <td>${escapeHtml(user.id_usuario)}</td>
          <td>${escapeHtml(user.usuario_login)}</td>
          <td>${escapeHtml(user.NAME_USER)}</td>
          <td>${escapeHtml(user.LAST_NAME_USER)}</td>
          <td>${escapeHtml(jobLabel(user.JOB))}</td>
          <td>${escapeHtml(rollLabel(user.ROLL))}</td>
          <td>${escapeHtml(user.ID_Empresa || user.empresa_id || '—')}</td>
          <td>${escapeHtml(user.creation_date || '')}</td>
          <td class="table-actions">
            <div class="table-actions__row">
              <button type="button" class="btn btn-ghost" data-edit-user="${user.id_usuario}">Editar</button>
              <button type="button" class="btn btn-ghost" data-delete-user="${user.id_usuario}">Eliminar</button>
            </div>
          </td>
        </tr>`
      )
      .join('') || '<tr><td colspan="9">Sin usuarios.</td></tr>';
  }

  async function loadUsers() {
    await loadAdminRoles();
    const { response, data } = await api('/admin/users');
    if (!response.ok || !data.ok) {
      showToast(data.error || 'Error al cargar usuarios.', 'error');
      return;
    }
    renderUsersTable(data.users || []);
    loadFallosDashboard();
  }

  function openFallosModal() {
    if (!els.fallosModal || !els.fallosForm) return;
    els.fallosForm.reset();
    if (els.fallosFormError) {
      els.fallosFormError.hidden = true;
      els.fallosFormError.textContent = '';
    }
    if (els.fallosRemitenteHint) {
      els.fallosRemitenteHint.innerHTML = currentUser
        ? `Se radicará con su usuario: <strong>${escapeHtml(
            `${currentUser.NAME_USER || ''} ${currentUser.usuario_login || ''}`.trim()
          )}</strong>.`
        : 'Se radicará como <strong>Invitado</strong> (no requiere inicio de sesión).';
    }
    els.fallosModal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeFallosModal() {
    if (!els.fallosModal) return;
    els.fallosModal.hidden = true;
    document.body.style.overflow = '';
  }

  function renderFallosDashboard(payload) {
    if (!els.fallosDashboard) return;
    const isAdmin = currentUser?.ROLL === 'ADMIN';
    els.fallosDashboard.hidden = !isAdmin;
    if (!isAdmin || !payload) return;
    const kpis = [
      ['Total', payload.total || 0],
      ['Pendientes', payload.pendientes || 0],
      ['Atendidos', payload.atendidos || 0],
    ];
    if (els.fallosKpis) {
      els.fallosKpis.innerHTML = kpis
        .map(
          ([label, value]) =>
            `<div class="fallos-kpi"><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(
              label
            )}</span></div>`
        )
        .join('');
    }
    const porEstado = payload.por_estado || {};
    const max = Math.max(1, ...Object.values(porEstado).map((n) => Number(n) || 0));
    const labels = {
      PENDIENTE: 'Pendiente',
      RESUELTO: 'Resuelto',
      IMPLEMENTADO: 'Implementado',
      DESCARTADO: 'Descartado',
    };
    if (els.fallosChart) {
      els.fallosChart.innerHTML = Object.entries(labels)
        .map(([key, label]) => {
          const n = Number(porEstado[key] || 0);
          const pct = Math.round((n / max) * 100);
          const slug = key.toLowerCase();
          return `<div class="fallos-bar fallos-bar--${slug}">
            <span>${escapeHtml(label)}</span>
            <div class="fallos-bar__track"><div class="fallos-bar__fill" style="width:${pct}%"></div></div>
            <strong>${n}</strong>
          </div>`;
        })
        .join('');
    }
  }

  async function loadFallosDashboard() {
    if (currentUser?.ROLL !== 'ADMIN' || !els.fallosDashboard) {
      if (els.fallosDashboard) els.fallosDashboard.hidden = true;
      return;
    }
    const { response, data } = await api('/api/reportes-fallos/dashboard');
    if (!response.ok || !data.ok) {
      els.fallosDashboard.hidden = true;
      return;
    }
    renderFallosDashboard(data);
  }

  async function loadDireccionEventLog(empresaId) {
    if (!els.direccionLogBox) return;
    if (!empresaId) {
      els.direccionLogBox.hidden = true;
      return;
    }
    const canSee =
      currentUser?.ROLL === 'ADMIN' ||
      currentUser?.JOB === 'Director Operativo' ||
      currentUser?.JOB === 'Dirección';
    if (!canSee) {
      els.direccionLogBox.hidden = true;
      return;
    }
    const { response, data } = await api(`/api/empresas/${empresaId}/eventos/resumen`);
    if (!response.ok || !data.ok) {
      els.direccionLogBox.hidden = true;
      return;
    }
    els.direccionLogBox.hidden = false;
    const n = Number(data.pendientes || 0);
    if (els.direccionLogHint) {
      els.direccionLogHint.textContent = n
        ? `${n} evento(s) desde ${data.desde || '—'} hasta ${data.hasta || '—'}. Al descargar, el log se elimina.`
        : 'Sin eventos pendientes de descarga.';
    }
    if (els.direccionLogDownload) {
      els.direccionLogDownload.hidden = !n;
      els.direccionLogDownload.dataset.empresaId = String(empresaId);
    }
  }

  function syncEmpresaHintForRoll() {
    const hint = document.getElementById('edit-empresa-hint');
    if (!hint) return;
    if ((els.editRoll?.value || '').toUpperCase() === 'ADMIN') {
      hint.textContent =
        'El Administrador no requiere empresa, sede ni servicio. Puede quedar sin asignar.';
      if (els.editEmpresa) els.editEmpresa.required = false;
    } else {
      hint.textContent =
        'Obligatoria al crear, excepto si el ROLL es Administrador.';
    }
  }

  async function loadEmpresasForEdit() {
    // ADMIN ve todas; Dirección solo la suya (el endpoint ya filtra).
    const { data } = await api('/api/empresas');
    const list = data.ok ? data.empresas || [] : [];
    if (!els.editEmpresa) return list;
    els.editEmpresa.innerHTML = '<option value="">Sin empresa</option>';
    list.forEach((e) => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = `${e.ID_Empresa} (${e.ID_NIT})`;
      els.editEmpresa.appendChild(opt);
    });
    return list;
  }

  function scopedAdminJobsCatalog() {
    if ((currentUser?.ROLL || '').toUpperCase() === 'ASISTENCIAL') {
      return {
        ASISTENCIAL:
          adminJobsByRole.ASISTENCIAL || ['Director', 'Coordinador', 'Líder'],
      };
    }
    if ((currentUser?.ROLL || '').toUpperCase() !== 'ADMIN') {
      const copy = { ...(adminJobsByRole || {}) };
      delete copy.ADMIN;
      return copy;
    }
    return adminJobsByRole;
  }

  function setEditModalChrome({ mode, title, eyebrow, submitLabel, passwordRequired }) {
    editModalMode = mode;
    if (els.editTitle) els.editTitle.textContent = title;
    if (els.editEyebrow) els.editEyebrow.textContent = eyebrow;
    if (els.editSubmit) els.editSubmit.textContent = submitLabel;
    if (els.editPassword) {
      els.editPassword.required = Boolean(passwordRequired);
      els.editPassword.placeholder = passwordRequired
        ? 'Mín. 8 caracteres'
        : 'Dejar vacío para no cambiar';
    }
    if (els.editPasswordHint) {
      els.editPasswordHint.textContent = passwordRequired
        ? 'Mínimo 8 caracteres.'
        : 'Si la completas: mínimo 8 caracteres.';
    }
    const creationField = els.editCreation?.closest('.field');
    if (creationField) creationField.hidden = mode === 'create';
    if (els.editCreation) els.editCreation.required = mode !== 'create';
  }

  function openCreateUserModal() {
    clearFieldErrors(els.editForm);
    els.editForm.reset();
    resetPasswordToggles(els.editForm);
    els.editId.value = '';
    setEditModalChrome({
      mode: 'create',
      title: 'Crear usuario',
      eyebrow: 'Nuevo usuario',
      submitLabel: 'Crear usuario',
      passwordRequired: true,
    });
    const catalog = scopedAdminJobsCatalog();
    const rolls = Object.keys(catalog);
    fillSelectRoles(els.editRoll, { roles: rolls }, rolls[0] || '');
    fillSelectJobs(els.editJob, catalog, els.editRoll.value);
    syncEmpresaHintForRoll();
    const hint = els.editEmpresa?.closest('.field')?.querySelector('.field-hint');
    if (hint) {
      hint.textContent =
        'Obligatoria al crear. En edición puede quedar en blanco hasta una asignación posterior.';
    }
    loadEmpresasForEdit().then((list) => {
      if (!els.editEmpresa) return;
      if (list.length === 1) els.editEmpresa.value = String(list[0].id);
    });
    els.editModal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function openEditModal(user) {
    clearFieldErrors(els.editForm);
    els.editForm.reset();
    resetPasswordToggles(els.editForm);
    setEditModalChrome({
      mode: 'edit',
      title: 'Modificar información',
      eyebrow: 'Editar usuario',
      submitLabel: 'Guardar cambios',
      passwordRequired: false,
    });
    els.editId.value = user.id_usuario;
    els.editEmail.value = user.usuario_login;
    els.editPassword.value = '';
    els.editName.value = user.NAME_USER;
    els.editLastName.value = user.LAST_NAME_USER;
    els.editCreation.value = user.creation_date || '';
    const catalog = scopedAdminJobsCatalog();
    fillSelectRoles(els.editRoll, { roles: Object.keys(catalog) }, user.ROLL);
    fillSelectJobs(els.editJob, catalog, user.ROLL, user.JOB);
    syncEmpresaHintForRoll();
    loadEmpresasForEdit().then((list) => {
      if (!els.editEmpresa) return;
      const empresaId = user.empresa_id != null ? String(user.empresa_id) : '';
      const exists = list.some((e) => String(e.id) === empresaId);
      if (empresaId && !exists) {
        const orphan = document.createElement('option');
        orphan.value = empresaId;
        orphan.textContent = `${user.ID_Empresa || 'Empresa'} (id ${empresaId}) — no en catálogo`;
        els.editEmpresa.appendChild(orphan);
      }
      els.editEmpresa.value = empresaId;
      if (user.ROLL && user.ROLL !== 'ADMIN' && !empresaId) {
        const hint = els.editEmpresa?.closest('.field')?.querySelector('.field-hint');
        if (hint) {
          hint.textContent =
            'Sin empresa: asígnala ahora o déjala en blanco hasta que un rol con permisos de asignación lo haga.';
        }
      }
      if (!String(user.JOB || '').trim() && els.editJob) {
        setFieldError(els.editJob, 'Este usuario no tiene JOB. Debes asignar el cargo para guardar.');
      }
    });
    els.editModal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeEditModal() {
    els.editModal.hidden = true;
    document.body.style.overflow = '';
  }

  /* Bandeja de solicitudes y notificaciones. */
  function setMailBadge(el, count) {
    if (!el) return;
    if (count > 0) {
      el.hidden = false;
      el.textContent = String(count);
    } else {
      el.hidden = true;
      el.textContent = '0';
    }
  }

  function setMailReadingMode(on) {
    document.querySelector('.mail-app')?.classList.toggle('is-reading', Boolean(on));
    if (els.mailBack) els.mailBack.hidden = !on;
    requestAnimationFrame(syncMobileLayout);
  }

  function hideMailViews() {
    if (els.mailEmpty) els.mailEmpty.hidden = true;
    if (els.mailMessage) els.mailMessage.hidden = true;
    if (els.solicitudForm) els.solicitudForm.hidden = true;
    if (els.notifEmpresaForm) els.notifEmpresaForm.hidden = true;
    if (els.notifJobForm) els.notifJobForm.hidden = true;
  }

  function setMailViewHeader(eyebrow, title) {
    if (els.mailViewEyebrow) els.mailViewEyebrow.textContent = eyebrow;
    if (els.mailViewTitle) els.mailViewTitle.textContent = title;
  }

  function showMailEmpty() {
    hideMailViews();
    setMailReadingMode(false);
    if (!els.mailEmpty) return;
    els.mailEmpty.hidden = false;
    if (els.mailMsgActions) els.mailMsgActions.innerHTML = '';
    setMailViewHeader('Bandeja', 'Selecciona un mensaje');
    const title = els.mailEmpty.querySelector('h3');
    const hint = els.mailEmpty.querySelector('p:last-of-type');
    if (title) title.textContent = 'Ningún mensaje abierto';
    if (hint) {
      hint.textContent =
        'Elige un ítem de la bandeja izquierda para ver el detalle y actuar sobre él.';
    }
  }

  function canSeeOnboardingNotifs() {
    const roll = (currentUser?.ROLL || '').toUpperCase();
    const job = currentUser?.JOB || '';
    if (roll === 'ADMIN') return true;
    if (roll === 'OPERATIVO' && ['Director Operativo', 'Dirección'].includes(job)) return true;
    if (roll === 'ASISTENCIAL' && ['Director', 'Dirección'].includes(job)) return true;
    return false;
  }

  function isMailTramitado(m) {
    const e = String(m?.estado || '').toUpperCase();
    return [
      'RESUELTA',
      'CERRADA',
      'APROBADA',
      'RECHAZADA',
      'RESUELTO',
      'IMPLEMENTADO',
      'DESCARTADO',
      'DESCARTADA',
    ].includes(e);
  }

  function mailKindFilterValue(m) {
    if (m.kind === 'notif') return 'notif';
    if (m.kind === 'fallo') return 'fallo';
    return m.raw?.tipo || 'solicitud';
  }

  function filteredMailMessages() {
    const isAdmin = currentUser?.ROLL === 'ADMIN';
    let rows;
    if (mailState.folder === 'notificaciones') {
      rows = mailState.messages.filter((m) => m.kind === 'notif' || m.kind === 'fallo');
    } else if (mailState.folder === 'solicitudes') {
      rows = mailState.messages.filter((m) => m.kind === 'solicitud' && m.isMine);
    } else if (isAdmin) {
      rows = mailState.messages.slice();
    } else if (canSeeOnboardingNotifs()) {
      rows = mailState.messages.filter(
        (m) => (m.kind === 'solicitud' && (m.isDest || m.raw?.es_bandeja_destino)) || m.kind === 'notif'
      );
    } else {
      rows = mailState.messages.filter(
        (m) => m.kind === 'solicitud' && (m.isDest || m.raw?.es_bandeja_destino)
      );
    }
    const tipo = mailState.filterTipo || 'all';
    if (tipo !== 'all') {
      rows = rows.filter((m) => {
        if (tipo === 'solicitud') return m.kind === 'solicitud';
        if (tipo === 'notif') return m.kind === 'notif';
        if (tipo === 'fallo') return m.kind === 'fallo';
        return mailKindFilterValue(m) === tipo;
      });
    }
    const tramite = mailState.filterTramite || 'all';
    if (tramite === 'pendiente') rows = rows.filter((m) => !isMailTramitado(m));
    if (tramite === 'tramitado') rows = rows.filter((m) => isMailTramitado(m));
    const limit = Number(mailState.pageSize) || 50;
    return rows.slice(0, limit);
  }

  function updateMailFilterCounts() {
    if (!els.mailFilterCounts) return;
    const folderRows = (() => {
      const prevTipo = mailState.filterTipo;
      const prevTramite = mailState.filterTramite;
      const prevSize = mailState.pageSize;
      mailState.filterTipo = 'all';
      mailState.filterTramite = 'all';
      mailState.pageSize = 500;
      const rows = filteredMailMessages();
      mailState.filterTipo = prevTipo;
      mailState.filterTramite = prevTramite;
      mailState.pageSize = prevSize;
      return rows;
    })();
    const pendientes = folderRows.filter((m) => !isMailTramitado(m)).length;
    const tramitados = folderRows.filter((m) => isMailTramitado(m)).length;
    els.mailFilterCounts.textContent = `Pendientes: ${pendientes} · Tramitados: ${tramitados}`;
  }

  function mailTrashIconSvg() {
    return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
      <polyline points="3 6 5 6 21 6"></polyline>
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>
      <path d="M10 11v6M14 11v6"></path>
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>
    </svg>`;
  }

  function mailDeleteButtonHtml(key, extraClass) {
    return `<button type="button" class="${extraClass}" data-mail-delete="${escapeHtml(key)}" title="Eliminar mensaje" aria-label="Eliminar mensaje">${mailTrashIconSvg()}</button>`;
  }

  async function hideResolvedMail(key) {
    const raw = String(key || '');
    let url = '';
    let confirmText = '¿Eliminar este mensaje de tu bandeja?';
    if (raw.startsWith('sol-')) {
      const id = Number(raw.slice(4));
      if (!id) return;
      url = `/api/solicitudes-permiso/${id}/ocultar`;
      confirmText =
        '¿Eliminar este mensaje de tu bandeja? El otro destinatario seguirá viéndolo.';
    } else if (raw.startsWith('notif-')) {
      const id = Number(raw.slice(6));
      if (!id) return;
      url = `/api/admin/notificaciones/${id}/ocultar`;
    } else if (raw.startsWith('fallo-')) {
      const id = Number(raw.slice(6));
      if (!id) return;
      url = `/api/reportes-fallos/${id}/ocultar`;
    } else {
      return;
    }
    if (!window.confirm(confirmText)) return;
    const { response, data } = await api(url, {
      method: 'POST',
      body: '{}',
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo eliminar el mensaje.', 'error');
      return;
    }
    showToast(data.message || 'Mensaje eliminado de tu bandeja.', 'success');
    if (mailState.selectedKey === key) mailState.selectedKey = null;
    await loadBandeja();
  }

  function solicitudScopeFrom(s) {
    const meta = s?.meta || {};
    return {
      empresaId: s?.empresa_id || meta.empresa_id || null,
      sedeId: s?.sede_id || meta.sede_id || null,
      servicioId: s?.servicio_id || meta.servicio_id || null,
    };
  }

  function estadoBadgeHtml(estado) {
    const key = String(estado || '').toUpperCase();
    const map = {
      PENDIENTE: ['🟡', 'Pendiente'],
      TOMADA: ['🟠', 'Tomada'],
      RESUELTA: ['🟢', 'Resuelta'],
      REENVIADA: ['🔴', 'Reenviada'],
      CERRADA: ['⚪', 'Cerrada'],
      APROBADA: ['🟢', 'Aprobada'],
      RECHAZADA: ['⚪', 'Rechazada'],
    };
    const pair = map[key] || ['', key || '—'];
    return `<span class="mail-estado" data-estado="${escapeHtml(key)}">${pair[0]} ${escapeHtml(pair[1])}</span>`;
  }

  function selectedSolicitudRaw() {
    const msg = mailState.messages.find((m) => m.key === mailState.selectedKey);
    return msg?.kind === 'solicitud' ? msg.raw || {} : {};
  }

  function renderMailList() {
    if (!els.mailList) return;
    updateMailFilterCounts();
    const rows = filteredMailMessages();
    if (!rows.length) {
      els.mailList.innerHTML =
        '<p class="field-hint" style="padding:0.75rem">No hay mensajes en esta carpeta.</p>';
      return;
    }
    els.mailList.innerHTML = rows
      .map((m) => {
        const unread = m.leido === false;
        const active = mailState.selectedKey === m.key;
        const canHide = Boolean(m.canHide);
        return `<div class="mail-item${unread ? ' is-unread' : ''}${active ? ' is-active' : ''}${canHide ? ' has-trash' : ''}" data-mail-key="${escapeHtml(m.key)}" role="option" aria-selected="${active}">
          <button type="button" class="mail-item__select">
            <span class="mail-item__from">${escapeHtml(m.from)}</span>
            <strong class="mail-item__subject">${escapeHtml(m.subject)}${
              m.alertaEquipo ? window.AtlasOps.equipoAlertaMarkup({ alerta_sin_datos_anio: true }) : ''
            }</strong>
            <p class="mail-item__preview">${escapeHtml(m.preview)}</p>
            <div class="mail-item__meta">
              <span>${escapeHtml(m.kindLabel)}</span>
              ${estadoBadgeHtml(m.estado)}
              <span>${escapeHtml(m.date || '')}</span>
            </div>
          </button>
          ${canHide ? mailDeleteButtonHtml(m.key, 'mail-item__trash') : ''}
        </div>`;
      })
      .join('');
  }

  function renderMailMessage(msg) {
    hideMailViews();
    if (!msg) {
      showMailEmpty();
      return;
    }
    els.mailMessage.hidden = false;
    setMailViewHeader(msg.kindLabel, msg.subject);
    els.mailMsgType.textContent = msg.kindLabel;
    els.mailMsgSubject.innerHTML = `${escapeHtml(msg.subject)}${
      msg.alertaEquipo ? window.AtlasOps.equipoAlertaMarkup({ alerta_sin_datos_anio: true }) : ''
    }`;
    els.mailMsgFrom.textContent = msg.fromDetail || msg.from;
    els.mailMsgDate.textContent = msg.date || '—';
    if (els.mailMsgEstado) els.mailMsgEstado.innerHTML = estadoBadgeHtml(msg.estado);
    els.mailMsgBody.textContent = msg.body || '';
    els.mailMsgActions.innerHTML = msg.actionsHtml || '';
  }

  function canValidatePmUser() {
    if (currentUser?.ROLL === 'ADMIN') return true;
    if ((currentUser?.ROLL || '').toUpperCase() !== 'ASISTENCIAL') return false;
    const job = (currentUser?.JOB || '').toLowerCase();
    return ['coordinador', 'director', 'dirección', 'direccion', 'líder', 'lider'].some((t) =>
      job.includes(t)
    );
  }

  function canComposeMail() {
    if (!currentUser) return false;
    // ADMIN usa Notificaciones; el resto puede radicar en solicitudes.db
    return currentUser.ROLL !== 'ADMIN';
  }

  function isDireccionMailUser() {
    return ['Director Operativo', 'Dirección', 'Director'].includes(currentUser?.JOB);
  }

  function fillSolicitudSedeSelect() {
    if (!els.solicitudSede) return;
    fillSedeSelect(els.solicitudSede);
    const assigned = (currentUser.assigned_sede_ids || []).map(Number);
    let options = [...els.solicitudSede.options].filter((o) => o.value);
    if (assigned.length) {
      // Limitar a sedes asignadas cuando existan.
      const keep = new Set(assigned.map(String));
      [...els.solicitudSede.options].forEach((opt) => {
        if (opt.value && !keep.has(opt.value)) opt.remove();
      });
      options = [...els.solicitudSede.options].filter((o) => o.value);
    }
    if (assigned.length === 1) {
      els.solicitudSede.value = String(assigned[0]);
      els.solicitudSede.disabled = true;
    } else if (options.length === 1) {
      els.solicitudSede.value = options[0].value;
      els.solicitudSede.disabled = true;
    } else if (options.length > 1) {
      if (assigned.length) els.solicitudSede.value = String(assigned[0]);
      else els.solicitudSede.selectedIndex = 1;
      els.solicitudSede.disabled = false;
    } else {
      els.solicitudSede.disabled = false;
    }
    const hint = document.getElementById('solicitud-sede-hint');
    if (hint) {
      hint.textContent = els.solicitudSede.disabled
        ? 'Sede asignada automáticamente según tu perfil.'
        : 'Elige la sede sobre la que radicas la solicitud.';
    }
  }

  function openMailCompose() {
    hideMailViews();
    mailState.selectedKey = null;
    renderMailList();
    if (els.mailMsgActions) els.mailMsgActions.innerHTML = '';
    setMailViewHeader('Redacción', 'Nueva solicitud');
    if (!canComposeMail()) {
      showMailEmpty();
      return;
    }
    ensureSedes().then(() => {
      fillSolicitudSedeSelect();
      const adminOpt = document.getElementById('solicitud-dest-admin');
      if (adminOpt) adminOpt.hidden = !isDireccionMailUser();
      const destSel = document.getElementById('solicitud-destinatario');
      if (destSel) {
        if (adminOpt?.hidden && destSel.value === 'administracion') destSel.value = '';
        if (!destSel.value) destSel.value = 'coordinacion';
      }
      const prio = document.getElementById('solicitud-prioridad');
      if (prio && !prio.value) prio.value = 'MODERADA';
      els.solicitudForm.hidden = false;
    });
  }

  function selectMailMessage(key) {
    const msg = mailState.messages.find((m) => m.key === key);
    mailState.selectedKey = key || null;
    setMailReadingMode(Boolean(msg));
    if (msg && msg.leido === false) {
      msg.leido = true;
      const kind = msg.kind === 'notif' ? 'notif' : msg.kind === 'fallo' ? 'fallo' : 'solicitud';
      api('/api/bandeja/leer', {
        method: 'POST',
        body: JSON.stringify({ kind, id: msg.id }),
      }).catch(() => {});
    }
    renderMailList();
    renderMailMessage(msg);
    if (msg && window.matchMedia('(max-width: 960px)').matches) {
      document.getElementById('mail-reading')?.scrollIntoView({ block: 'start' });
    }
  }

  async function loadBandeja() {
    const gen = ++bandejaLoadGen;
    const seeNotifs = canSeeOnboardingNotifs();
    if (els.mailFolderNotif) els.mailFolderNotif.hidden = !seeNotifs;
    if (els.mailFolderCompose) {
      els.mailFolderCompose.hidden = !canComposeMail();
    }

    const messages = [];
    let pendingNotif = 0;
    let pendingSol = 0;
    let pendingSent = 0;

    if (seeNotifs) {
      const { response, data } = await api('/api/admin/notificaciones');
      if (response.ok && data.ok) {
        pendingNotif = data.pendientes || 0;
        (data.notificaciones || []).forEach((n) => {
          const pending = n.estado === 'PENDIENTE';
          const isJob = n.tipo === 'JOB_PENDIENTE';
          let actionsHtml = '';
          if (n.tipo === 'LOG_EVENTOS_PENDIENTE' && pending && currentUser?.ROLL === 'ADMIN') {
            const empId = n.empresa_creada_id || '';
            actionsHtml = `<button type="button" class="btn btn-primary" data-log-download="${empId}">Descargar log</button>
                 <button type="button" class="btn btn-ghost" data-notif-reject="${n.id}">Descartar aviso</button>`;
          } else if (n.tipo === 'LOG_EVENTOS_BORRADO' && pending && currentUser?.ROLL === 'ADMIN') {
            actionsHtml = `<button type="button" class="btn btn-primary" data-notif-ack="${n.id}">Entendido</button>`;
          } else if (pending && isJob) {
            actionsHtml = `<button type="button" class="btn btn-primary" data-notif-assign-job="${n.id}">Asignar JOB</button>`;
          } else if (pending && currentUser?.ROLL === 'ADMIN' && n.tipo !== 'LOG_EVENTOS_PENDIENTE' && n.tipo !== 'LOG_EVENTOS_BORRADO') {
            actionsHtml = `<button type="button" class="btn btn-primary" data-notif-create="${n.id}">Aprobar</button>
                 <button type="button" class="btn btn-ghost" data-notif-reject="${n.id}">Rechazar</button>`;
          }
          const resolved = n.estado === 'RESUELTA' || n.estado === 'DESCARTADA';
          if (resolved) {
            actionsHtml += mailDeleteButtonHtml(
              `notif-${n.id}`,
              'mail-icon-btn mail-icon-btn--danger'
            );
          }
          const isLog = n.tipo === 'LOG_EVENTOS_PENDIENTE' || n.tipo === 'LOG_EVENTOS_BORRADO';
          messages.push({
            key: `notif-${n.id}`,
            kind: 'notif',
            kindLabel: isLog ? 'Log de eventos' : isJob ? 'JOB pendiente' : 'Notificación',
            id: n.id,
            raw: n,
            from: n.solicitante_nombre || n.solicitante_email || (isLog ? 'Sistema' : 'Solicitante'),
            fromDetail: isLog
              ? 'Sistema SIGTB'
              : `${n.solicitante_nombre || ''} <${n.solicitante_email || ''}>`.trim(),
            subject: isLog
              ? (n.tipo === 'LOG_EVENTOS_BORRADO'
                  ? `Log de eventos borrado · ${n.empresa_sugerida || ''}`
                  : `Log de eventos pendiente · ${n.empresa_sugerida || ''}`)
              : isJob
                ? `Asignación de JOB · ${rollLabel(n.solicitante_roll)}`
                : n.empresa_sugerida
                  ? `Solicitud de empresa: ${n.empresa_sugerida}`
                  : 'Solicitud de creación de empresa',
            preview: isLog
              ? `${n.estado || ''} · ${n.mensaje || ''}`.slice(0, 140)
              : isJob
                ? `${n.solicitante_email || ''} · ${jobLabel(n.solicitante_job)}`
                : n.nit_sugerido
                  ? `NIT ${n.nit_sugerido} · ${n.estado || ''}`
                  : n.mensaje || '',
            body: isLog
              ? `${n.mensaje || ''}\n\nRadicado: ${n.creation_date || '—'}`
              : isJob
                ? `${n.mensaje || 'Usuario nuevo sin cargo asignado.'}\n\n` +
                  `Rol: ${rollLabel(n.solicitante_roll)}\n` +
                  `JOB actual: ${jobLabel(n.solicitante_job)}\n` +
                  `Empresa: ${n.solicitante_empresa_id || 'Sin asignar'}`
                : `${n.mensaje || 'El usuario indicó que su empresa no está en el catálogo.'}\n\n` +
                  `Empresa sugerida: ${n.empresa_sugerida || '—'}\n` +
                  `NIT sugerido: ${n.nit_sugerido || '—'}\n` +
                  `Rol del solicitante: ${n.solicitante_roll || '—'}\n` +
                  `JOB actual: ${jobLabel(n.solicitante_job)}\n` +
                  `Empresa actual: ${n.solicitante_empresa_id ? n.solicitante_empresa_id : 'Sin asignar'}`,
            date: n.creation_date || '',
            estado: n.estado,
            leido: n.leido === true,
            canHide: resolved,
            actionsHtml,
          });
        });
      }
    }

    {
      const { data } = await api('/api/solicitudes-permiso');
      if (data.ok) {
        pendingSent = Number(data.pendientes_enviadas || 0);
        const satisfactionLabels = [
          'Muy satisfecho',
          'Satisfecho',
          'Insatisfecho',
          'Muy insatisfecho',
        ];
        const kindLabels = {
          actualizar_datos_suficiencia: 'Actualización datos suficiencia',
          consulta_general: 'Consulta / solicitud',
          modificar_empresa: 'Modificar empresa',
          modificar_sede: 'Modificar sede',
          permisos_ampliados: 'Permisos ampliados',
          validar_pm_cronograma: 'Validar PM cronograma',
          cerrar_requisitos_preinstalacion: 'Cierre requisitos preinstalación',
          validar_preinstalacion: 'Validar preinstalación',
          completar_forma_adquisicion: 'Completar forma de adquisición',
        };
        (data.solicitudes || []).forEach((s) => {
          const isDest = Boolean(
            s.es_destinatario ||
              s.es_bandeja_destino ||
              s.es_asignado ||
              s.en_pool ||
              Number(s.destinatario_id || s.coordinador_id) === Number(currentUser.id_usuario)
          );
          const isMine = Boolean(
            s.es_solicitante || Number(s.solicitante_id) === Number(currentUser.id_usuario)
          );
          if (
            ['PENDIENTE', 'REENVIADA', 'TOMADA'].includes(s.estado) &&
            (isDest || s.es_gestor_adquisicion)
          ) {
            pendingSol += 1;
          }

          let actionsHtml = '';
          const tipo = s.tipo || '';
          const meta = s.meta || {};
          const commentMax = window.SIGTB_LIMITS?.comment || 500;

          if (s.puede_tomar) {
            actionsHtml += `<button type="button" class="btn btn-primary" data-take="${s.id}">Tomar solicitud</button>`;
          }
          if (s.puede_marcar_resuelta) {
            actionsHtml += ` <button type="button" class="btn btn-primary" data-mark-resuelta="${s.id}">Marcar como resuelta</button>`;
            actionsHtml +=
              ' <button type="button" class="btn btn-ghost" data-open-suficiencia="1">Ir a Suficiencia</button>';
          }
          if (s.puede_completar_adq) {
            const catalogo = (meta.catalogo || [
              'Compra directa',
              'Leasing',
              'Comodato',
              'No Aplica',
            ]).map(
              (opt) =>
                `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`
            );
            actionsHtml += `
              <div class="mail-adq-form" data-adq-form="${s.id}">
                <label>Forma de adquisición
                  <select data-adq-forma>
                    <option value="">Seleccione</option>
                    ${catalogo.join('')}
                  </select>
                </label>
                <label>Observación (opcional)
                  <textarea data-adq-obs rows="3" maxlength="500" placeholder="Opcional: justifique la modalidad elegida"></textarea>
                </label>
                <button type="button" class="btn btn-primary" data-adq-complete="${s.id}">Registrar modalidad</button>
              </div>`;
          } else if (s.puede_aprobar) {
            actionsHtml += ` <button type="button" class="btn btn-primary" data-approve="${s.id}">Aprobar</button>
              <button type="button" class="btn btn-ghost" data-reject="${s.id}">Rechazar</button>`;
          }
          if (s.puede_confirmar) {
            actionsHtml += `
              <div class="mail-confirm">
                <p class="field-hint">Tu solicitud #${s.id} ha sido resuelta.</p>
                <button type="button" class="btn btn-primary" data-confirm="${s.id}">Confirmar</button>
                <button type="button" class="btn btn-ghost" data-deny-open="${s.id}">Denegar</button>
                <div class="mail-deny-form" hidden data-deny-form="${s.id}">
                  <label>Comentario
                    <textarea data-deny-comment="${s.id}" rows="3" maxlength="${commentMax}" placeholder="Explique el motivo del reenvío"></textarea>
                  </label>
                  <button type="button" class="btn btn-primary" data-deny-submit="${s.id}">Reenviar solicitud</button>
                </div>
              </div>`;
          }
          if (
            s.estado === 'APROBADA' &&
            tipo === 'permisos_ampliados' &&
            isMine &&
            can('request_expanded_permissions')
          ) {
            actionsHtml +=
              ' <button type="button" class="btn btn-primary" data-activate="1">Activar en sesión</button>';
          }
          if (s.asignado_nombre && s.estado === 'TOMADA') {
            actionsHtml += `<p class="field-hint">Solicitud tomada por ${escapeHtml(s.asignado_nombre)}</p>`;
          }

          if (tipo === 'validar_pm_cronograma' && !actionsHtml.includes('data-open-frecuencia-pm')) {
            actionsHtml +=
              ' <button type="button" class="btn btn-ghost" data-open-frecuencia-pm="1">Ir a Frecuencia PM</button>';
          }
          if (
            (tipo === 'cerrar_requisitos_preinstalacion' || tipo === 'validar_preinstalacion') &&
            !actionsHtml.includes('data-open-preinstalacion')
          ) {
            actionsHtml +=
              ' <button type="button" class="btn btn-ghost" data-open-preinstalacion="1">Ir a Preinstalación</button>';
          }

          const resolved = s.estado === 'APROBADA' || s.estado === 'RECHAZADA' || s.estado === 'CERRADA';
          const alreadyRated = satisfactionLabels.includes(String(s.calificacion || '').trim());
          if (resolved) {
            actionsHtml += mailDeleteButtonHtml(`sol-${s.id}`, 'mail-icon-btn mail-icon-btn--danger');
          }
          if (isMine && resolved && !alreadyRated) {
            actionsHtml += `
              <div class="mail-rate">
                <span class="field-hint">Califica la atención:</span>
                <button type="button" class="btn btn-ghost btn-sm" data-rate="${s.id}" data-rate-value="muy_satisfecho">Muy satisfecho</button>
                <button type="button" class="btn btn-ghost btn-sm" data-rate="${s.id}" data-rate-value="satisfecho">Satisfecho</button>
                <button type="button" class="btn btn-ghost btn-sm" data-rate="${s.id}" data-rate-value="insatisfecho">Insatisfecho</button>
                <button type="button" class="btn btn-ghost btn-sm" data-rate="${s.id}" data-rate-value="muy_insatisfecho">Muy insatisfecho</button>
              </div>`;
          }
          const destLabels = {
            direccion: 'Dirección',
            coordinacion: 'Coordinación',
            ingenieria: 'Ingeniería',
            soporte: 'Soporte técnico',
            administracion: 'Administración',
            asistencial: 'Asistencial',
          };
          const kindLabel = kindLabels[tipo] || tipo || 'Solicitud';
          const hist = Array.isArray(meta.historial) ? meta.historial : [];
          const histLine = hist.length
            ? `Historial:\n${hist
                .map(
                  (h) =>
                    `· ${h.fecha || ''} ${h.evento || ''} ${h.nombre || ''}${
                      h.comentario ? ` — ${h.comentario}` : ''
                    }`
                )
                .join('\n')}\n`
            : '';
          const metaLine =
            `Empresa: ${meta.empresa || s.empresa_id || '—'}\n` +
            `Sede: ${s.ID_sede || meta.ID_sede || '—'} · ${s.name_sede || meta.name_sede || '—'}\n` +
            `Servicio: ${meta.servicio || meta.ID_servicio || s.servicio_id || '—'}\n` +
            (s.asignado_nombre ? `Asignada a: ${s.asignado_nombre}\n` : '') +
            (s.comentario ? `Comentario: ${s.comentario}\n` : '') +
            (tipo === 'validar_pm_cronograma'
              ? `Ref PM: ${s.ref_id || '—'} · Equipo: ${meta.equipo || meta.codigo_equipo || '—'} · ${meta.anio || ''}/${meta.mes != null ? String(meta.mes).padStart(2, '0') : '—'}\n`
              : '') +
            (tipo === 'completar_forma_adquisicion'
              ? `Equipo: ${meta.equipo || '—'} (${meta.codigo || s.ref_id || '—'})\n`
              : '') +
            (meta.alerta_sin_datos_anio
              ? `${meta.alerta_mensaje || window.AtlasOps.EQ_ALERTA_MSG}\n`
              : '') +
            histLine;
          messages.push({
            key: `sol-${s.id}`,
            kind: 'solicitud',
            isDest,
            isMine,
            kindLabel,
            id: s.id,
            raw: s,
            from: s.solicitante_nombre || s.solicitante_email || 'Usuario',
            fromDetail: `${s.solicitante_nombre || ''} <${s.solicitante_email || ''}>`.trim(),
            subject: `${kindLabel} · ${s.ID_sede || ''} ${s.name_sede || ''}`.trim(),
            preview: s.mensaje || '',
            alertaEquipo: Boolean(meta.alerta_sin_datos_anio),
            body:
              `Tipo: ${kindLabel}\n` +
              `Prioridad: ${s.prioridad || 'MODERADA'}\n` +
              `Destinatario: ${destLabels[s.destinatario_rol] || s.email_destino || '—'}\n` +
              metaLine +
              `Estado: ${s.estado}\n` +
              (alreadyRated ? `Calificación: ${s.calificacion}\n` : '') +
              `\n${s.mensaje || ''}`,
            date: s.creation_date || '',
            estado: s.estado,
            leido: s.leido === true,
            canHide: resolved,
            actionsHtml,
          });
        });
      }
    }

    if (currentUser?.ROLL === 'ADMIN') {
      const { response, data } = await api('/api/reportes-fallos');
      if (response.ok && data.ok) {
        (data.reportes || []).forEach((r) => {
          const pending = r.estado === 'PENDIENTE';
          if (pending) pendingNotif += 1;
          let actionsHtml = '';
          if (pending) {
            actionsHtml = `
              <label class="mail-obs">Observación
                <textarea data-fallo-obs="${r.id}" rows="2" maxlength="500" placeholder="Observación del administrador"></textarea>
              </label>
              <button type="button" class="btn btn-primary" data-fallo-estado="RESUELTO" data-fallo-id="${r.id}">Resuelto</button>
              <button type="button" class="btn btn-ghost" data-fallo-estado="IMPLEMENTADO" data-fallo-id="${r.id}">Implementado</button>
              <button type="button" class="btn btn-ghost" data-fallo-estado="DESCARTADO" data-fallo-id="${r.id}">Descartado</button>`;
          } else {
            actionsHtml = mailDeleteButtonHtml(
              `fallo-${r.id}`,
              'mail-icon-btn mail-icon-btn--danger'
            );
          }
          messages.push({
            key: `fallo-${r.id}`,
            kind: 'fallo',
            kindLabel: 'Reporte de fallos',
            id: r.id,
            raw: r,
            from: r.remitente_nombre || 'Invitado',
            fromDetail: r.remitente_email
              ? `${r.remitente_nombre || 'Invitado'} <${r.remitente_email}>`
              : r.remitente_nombre || 'Invitado',
            subject: `${r.tipo} · ${r.estado}`,
            preview: r.descripcion || '',
            body:
              `Tipo de falla: ${r.tipo}\n` +
              `Radicación: ${r.creation_date || '—'}\n` +
              `Remitente: ${r.remitente_nombre || 'Invitado'}\n` +
              (r.remitente_email ? `Correo: ${r.remitente_email}\n` : '') +
              `\nNovedad detectada:\n${r.descripcion || '—'}\n` +
              `\nSolución recomendada:\n${r.solucion_recomendada || '—'}` +
              (r.observacion_admin
                ? `\n\nObservación del administrador:\n${r.observacion_admin}`
                : '') +
              (r.resolved_at ? `\n\nCierre: ${r.resolved_at}` : ''),
            date: r.creation_date || '',
            estado: r.estado,
            leido: r.leido === true,
            canHide: !pending,
            actionsHtml,
          });
        });
      }
    }

    messages.sort((a, b) => String(b.date).localeCompare(String(a.date)));
    if (gen !== bandejaLoadGen) return;
    mailState.messages = messages;
    setMailBadge(els.mailBadgeInbox, pendingNotif + pendingSol);
    setMailBadge(els.mailBadgeNotif, pendingNotif);
    setMailBadge(els.mailBadgeSol, pendingSent);
    setInboxBadge(pendingNotif + pendingSol);

    document.querySelectorAll('.mail-nav__item').forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.mailFolder === mailState.folder);
    });

    if (mailState.folder === 'compose') {
      openMailCompose();
      return;
    }

    renderMailList();
    if (mailState.selectedKey && messages.some((m) => m.key === mailState.selectedKey)) {
      selectMailMessage(mailState.selectedKey);
    } else {
      mailState.selectedKey = null;
      showMailEmpty();
    }
    requestAnimationFrame(syncMobileLayout);
  }

  async function loadSolicitudes() {
    mailState.folder = 'solicitudes';
    await loadBandeja();
  }

  async function loadNotificaciones() {
    mailState.folder = 'notificaciones';
    await loadBandeja();
  }

  /* Modal de registro de usuario. */
  async function loadEmpresasCatalog() {
    const { data } = await api('/empresas/catalog');
    if (!data.ok || !els.regEmpresa) return;
    const current = els.regEmpresa.value;
    empresasCatalogCache = data.empresas || [];
    els.regEmpresa.innerHTML =
      '<option value="" disabled selected>Selecciona tu empresa</option>';
    empresasCatalogCache.forEach((e) => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = `${e.ID_Empresa} (${e.ID_NIT})`;
      els.regEmpresa.appendChild(opt);
    });
    const notFound = document.createElement('option');
    notFound.value = '__not_found__';
    notFound.textContent = 'No se encuentra';
    els.regEmpresa.appendChild(notFound);
    if (current) els.regEmpresa.value = current;
  }

  function resetEmpresaCargadaHint() {
    registerEmpresaCargada = null;
    if (els.regEmpresaCargarHint) {
      els.regEmpresaCargarHint.textContent =
        'Cargar no asigna la empresa. Envía una solicitud al administrador para crearla.';
    }
  }

  function toggleEmpresaSugerida() {
    const notFound = els.regEmpresa?.value === '__not_found__';
    if (els.regEmpresaSugeridaWrap) els.regEmpresaSugeridaWrap.hidden = !notFound;
    if (els.regNitSugeridoWrap) els.regNitSugeridoWrap.hidden = !notFound;
    if (els.regEmpresaCargarWrap) els.regEmpresaCargarWrap.hidden = !notFound;
    if (els.regEmpresaSugerida) els.regEmpresaSugerida.required = notFound;
    if (els.regNitSugerido) els.regNitSugerido.required = notFound;
    if (!notFound) {
      resetEmpresaCargadaHint();
      if (els.regEmpresaSugerida) els.regEmpresaSugerida.value = '';
      if (els.regNitSugerido) els.regNitSugerido.value = '';
    }
  }

  function cargarEmpresaSugerida() {
    if (els.regEmpresaSugerida) els.regEmpresaSugerida.classList.remove('is-invalid');
    if (els.regNitSugerido) els.regNitSugerido.classList.remove('is-invalid');
    const nombre = (els.regEmpresaSugerida?.value || '').trim();
    const nit = (els.regNitSugerido?.value || '').trim();
    if (!nombre) {
      setFieldError(els.regEmpresaSugerida, 'Indica el nombre de la empresa.');
      showToast('Indica el nombre de la empresa.', 'error');
      return;
    }
    if (!nit) {
      setFieldError(els.regNitSugerido, 'El NIT es obligatorio.');
      showToast('El NIT es obligatorio.', 'error');
      return;
    }
    const existing = empresasCatalogCache.find(
      (e) => String(e.ID_NIT || '').toUpperCase() === nit.toUpperCase()
    );
    if (existing) {
      showToast('Ese NIT ya está en el catálogo. Selecciónalo en la lista.', 'error');
      els.regEmpresa.value = String(existing.id);
      toggleEmpresaSugerida();
      return;
    }
    registerEmpresaCargada = { nombre, nit: nit.toUpperCase() };
    if (els.regEmpresaCargarHint) {
      els.regEmpresaCargarHint.textContent =
        `Solicitud lista: ${nombre} · NIT ${nit}. No se asignará hasta que el administrador la apruebe.`;
    }
    showToast(
      'Datos cargados. Al crear el usuario se enviará la solicitud al administrador.',
      'success'
    );
  }

  function openModal(prefillEmail = '') {
    clearFieldErrors(els.registerForm);
    els.registerForm.reset();
    resetPasswordToggles(els.registerForm);
    resetEmpresaCargadaHint();
    if (!Object.keys(jobsByRole).length) {
      loadRoles();
    } else {
      fillSelectRoles(els.regRoll, { roles: Object.keys(jobsByRole) });
    }
    loadEmpresasCatalog().then(toggleEmpresaSugerida);
    if (prefillEmail) els.regEmail.value = normalizeEmail(prefillEmail);
    els.modal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    els.modal.hidden = true;
    document.body.style.overflow = '';
  }

  function openForgotModal() {
    if (!els.forgotModal) return;
    if (els.forgotForm) {
      clearFieldErrors(els.forgotForm);
      els.forgotForm.reset();
    }
    if (els.forgotEmail && els.loginEmail?.value) {
      els.forgotEmail.value = normalizeEmail(els.loginEmail.value);
    }
    els.forgotModal.hidden = false;
    document.body.style.overflow = 'hidden';
    els.forgotEmail?.focus();
  }

  function closeForgotModal() {
    if (!els.forgotModal) return;
    els.forgotModal.hidden = true;
    document.body.style.overflow = '';
  }

  function openResetModal(token) {
    if (!els.resetModal) return;
    if (els.resetForm) {
      clearFieldErrors(els.resetForm);
      els.resetForm.reset();
    }
    if (els.resetToken) els.resetToken.value = token || '';
    els.resetModal.hidden = false;
    document.body.style.overflow = 'hidden';
    els.resetPassword?.focus();
  }

  function closeResetModal() {
    if (!els.resetModal) return;
    els.resetModal.hidden = true;
    document.body.style.overflow = '';
  }

  /* Enlace de eventos de la interfaz (clics y envío de formularios). */
  els.openRegister.addEventListener('click', () => openModal(els.loginEmail.value));
  els.openForgot?.addEventListener('click', openForgotModal);
  els.modal.querySelectorAll('[data-close-modal]').forEach((n) => n.addEventListener('click', closeModal));
  els.forgotModal?.querySelectorAll('[data-close-forgot-modal]').forEach((n) =>
    n.addEventListener('click', closeForgotModal)
  );
  els.resetModal?.querySelectorAll('[data-close-reset-modal]').forEach((n) =>
    n.addEventListener('click', closeResetModal)
  );
  els.editModal.querySelectorAll('[data-close-edit-modal]').forEach((n) =>
    n.addEventListener('click', closeEditModal)
  );
  els.regEmpresa?.addEventListener('change', toggleEmpresaSugerida);
  els.regEmpresaCargar?.addEventListener('click', cargarEmpresaSugerida);
  els.regEmpresaSugerida?.addEventListener('input', resetEmpresaCargadaHint);
  els.regNitSugerido?.addEventListener('input', resetEmpresaCargadaHint);
  els.mailRefresh?.addEventListener('click', () => loadBandeja());
  els.mailFilterTipo?.addEventListener('change', () => {
    mailState.filterTipo = els.mailFilterTipo.value || 'all';
    renderMailList();
  });
  els.mailFilterTramite?.addEventListener('change', () => {
    mailState.filterTramite = els.mailFilterTramite.value || 'all';
    renderMailList();
  });
  els.mailFilterLimit?.addEventListener('change', () => {
    mailState.pageSize = Number(els.mailFilterLimit.value) || 50;
    renderMailList();
  });
  els.onlineDockToggle?.addEventListener('click', () => {
    if (!els.onlineDockPanel) return;
    const open = els.onlineDockPanel.hidden;
    els.onlineDockPanel.hidden = !open;
    els.onlineDockToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) refreshOnlineUsers();
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refreshOnlineUsers();
  });
  els.inventarioPrev?.addEventListener('click', () => {
    inventarioPage -= 1;
    if (inventarioServerPaged) {
      const srv = els.inventarioServicioSelect?.value;
      if (srv) loadInventario(srv);
      else renderInventarioTable();
    } else {
      renderInventarioTable();
    }
  });
  els.inventarioNext?.addEventListener('click', () => {
    inventarioPage += 1;
    if (inventarioServerPaged) {
      const srv = els.inventarioServicioSelect?.value;
      if (srv) loadInventario(srv);
      else renderInventarioTable();
    } else {
      renderInventarioTable();
    }
  });
  els.inventarioPageSize?.addEventListener('change', () => {
    inventarioPage = 1;
    if (inventarioServerPaged) {
      const srv = els.inventarioServicioSelect?.value;
      if (srv) loadInventario(srv, { resetPage: true });
      else renderInventarioTable();
    } else {
      renderInventarioTable();
    }
  });

  document.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-password-toggle]');
    if (!btn) return;
    const input = document.getElementById(btn.dataset.passwordToggle);
    if (!input) return;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    setPasswordToggleUi(btn, show);
  });

  document.querySelectorAll('.mail-nav__item').forEach((btn) => {
    btn.addEventListener('click', () => {
      mailState.folder = btn.dataset.mailFolder;
      mailState.selectedKey = null;
      document.querySelectorAll('.mail-nav__item').forEach((b) => {
        b.classList.toggle('is-active', b === btn);
      });
      if (mailState.folder === 'compose') {
        openMailCompose();
        return;
      }
      loadBandeja();
    });
  });

  els.mailBack?.addEventListener('click', () => {
    mailState.selectedKey = null;
    renderMailList();
    showMailEmpty();
  });

  els.mailList?.addEventListener('click', (event) => {
    const delBtn = event.target.closest('[data-mail-delete]');
    if (delBtn) {
      event.preventDefault();
      event.stopPropagation();
      hideResolvedMail(delBtn.dataset.mailDelete);
      return;
    }
    const item = event.target.closest('[data-mail-key]');
    if (!item) return;
    selectMailMessage(item.dataset.mailKey);
  });

  els.mailMsgActions?.addEventListener('click', async (event) => {
    const deleteBtn = event.target.closest('[data-mail-delete]');
    if (deleteBtn) {
      event.preventDefault();
      await hideResolvedMail(deleteBtn.dataset.mailDelete);
      return;
    }
    const createBtn = event.target.closest('[data-notif-create]');
    const assignJobBtn = event.target.closest('[data-notif-assign-job]');
    const discardBtn = event.target.closest('[data-notif-discard]');
    const rejectBtn = event.target.closest('[data-notif-reject]');
    const ackBtn = event.target.closest('[data-notif-ack]');
    const logDownloadBtn = event.target.closest('[data-log-download]');
    const falloBtn = event.target.closest('[data-fallo-estado]');
    const approve = event.target.closest('[data-approve]');
    const reject = event.target.closest('[data-reject]');
    const activate = event.target.closest('[data-activate]');
    const adqComplete = event.target.closest('[data-adq-complete]');
    const takeBtn = event.target.closest('[data-take]');
    const markResueltaBtn = event.target.closest('[data-mark-resuelta]');
    const confirmBtn = event.target.closest('[data-confirm]');
    const denyOpenBtn = event.target.closest('[data-deny-open]');
    const denySubmitBtn = event.target.closest('[data-deny-submit]');

    if (falloBtn) {
      const id = Number(falloBtn.dataset.falloId);
      const estado = falloBtn.dataset.falloEstado;
      const obs = document.querySelector(`[data-fallo-obs="${id}"]`)?.value || '';
      const { response, data } = await api(`/api/reportes-fallos/${id}/resolver`, {
        method: 'POST',
        body: JSON.stringify({ estado, observacion: obs }),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo actualizar el reporte.', 'error');
        return;
      }
      showToast(data.message, 'success');
      loadBandeja();
      loadFallosDashboard();
      return;
    }

    if (logDownloadBtn) {
      const empId = Number(logDownloadBtn.dataset.logDownload);
      if (!empId) {
        showToast('No se identificó la empresa del log.', 'error');
        return;
      }
      try {
        await downloadFile(`/api/empresas/${empId}/eventos.xlsx`, `log_eventos_${empId}.xlsx`);
        showToast('Log descargado. Los eventos de esa empresa se eliminaron del servidor.', 'success');
        loadBandeja();
        loadDireccionEventLog(empId);
      } catch (err) {
        showToast(err.message || 'No se pudo descargar el log.', 'error');
      }
      return;
    }

    if (ackBtn) {
      const { response, data } = await api(
        `/api/admin/notificaciones/${ackBtn.dataset.notifAck}/descartar`,
        { method: 'POST', body: '{}' }
      );
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo marcar como leído.', 'error');
        return;
      }
      showToast('Aviso de borrado marcado como leído.', 'success');
      loadBandeja();
      return;
    }

    if (takeBtn) {
      const id = Number(takeBtn.dataset.take);
      const raw = selectedSolicitudRaw();
      const { response, data } = await api(`/api/solicitudes-permiso/${id}/tomar`, {
        method: 'POST',
        body: '{}',
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo tomar la solicitud.', 'error');
        return;
      }
      showToast(data.message, 'success');
      const taken = data.solicitud || raw;
      if ((taken.tipo || raw.tipo) === 'actualizar_datos_suficiencia') {
        openModule('suficiencia', 'instrumentos', solicitudScopeFrom(taken));
        return;
      }
      loadBandeja();
      return;
    }

    if (markResueltaBtn) {
      const id = Number(markResueltaBtn.dataset.markResuelta);
      const { response, data } = await api(`/api/solicitudes-permiso/${id}/resolver`, {
        method: 'POST',
        body: JSON.stringify({ decision: 'RESUELTA' }),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo marcar como resuelta.', 'error');
        return;
      }
      showToast(data.message, 'success');
      loadBandeja();
      return;
    }

    if (confirmBtn) {
      const id = Number(confirmBtn.dataset.confirm);
      const { response, data } = await api(`/api/solicitudes-permiso/${id}/confirmar`, {
        method: 'POST',
        body: '{}',
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo confirmar.', 'error');
        return;
      }
      showToast(data.message, 'success');
      loadBandeja();
      return;
    }

    if (denyOpenBtn) {
      const form = els.mailMsgActions?.querySelector(
        `[data-deny-form="${denyOpenBtn.dataset.denyOpen}"]`
      );
      if (form) form.hidden = false;
      form?.querySelector('textarea')?.focus();
      return;
    }

    if (denySubmitBtn) {
      const id = Number(denySubmitBtn.dataset.denySubmit);
      const comentario =
        els.mailMsgActions?.querySelector(`[data-deny-comment="${id}"]`)?.value || '';
      const { response, data } = await api(`/api/solicitudes-permiso/${id}/denegar`, {
        method: 'POST',
        body: JSON.stringify({ comentario }),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo reenviar la solicitud.', 'error');
        return;
      }
      showToast(data.message, 'success');
      loadBandeja();
      return;
    }

    if (adqComplete) {
      const id = Number(adqComplete.dataset.adqComplete);
      const form = adqComplete.closest('[data-adq-form]');
      const forma = form?.querySelector('[data-adq-forma]')?.value || '';
      const observacion = form?.querySelector('[data-adq-obs]')?.value || '';
      if (!forma) {
        showToast('Seleccione la forma de adquisición.', 'error');
        return;
      }
      const { response, data } = await api(`/api/solicitudes-permiso/${id}/resolver`, {
        method: 'POST',
        body: JSON.stringify({
          decision: 'APROBADA',
          forma_adquisicion: forma,
          observacion,
        }),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo registrar la modalidad.', 'error');
        return;
      }
      showToast(data.message, 'success');
      loadBandeja();
      return;
    }

    if (discardBtn || rejectBtn) {
      const id = Number(
        (discardBtn && discardBtn.dataset.notifDiscard) ||
          (rejectBtn && rejectBtn.dataset.notifReject)
      );
      const { response, data } = await api(`/api/admin/notificaciones/${id}/rechazar`, {
        method: 'POST',
        body: '{}',
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo rechazar.', 'error');
        return;
      }
      showToast(data.message, 'success');
      mailState.selectedKey = null;
      loadBandeja();
      return;
    }

    if (assignJobBtn) {
      const id = Number(assignJobBtn.dataset.notifAssignJob);
      const msg = mailState.messages.find((m) => m.key === `notif-${id}`);
      const notif = msg?.raw;
      if (!notif) return;
      hideMailViews();
      setMailViewHeader('Solicitud', 'Asignar JOB');
      els.mailMsgActions.innerHTML = '';
      if (els.notifJobForm) els.notifJobForm.hidden = false;
      if (els.notifJobId) els.notifJobId.value = notif.id;
      if (els.notifJobUserId) els.notifJobUserId.value = notif.solicitante_id || '';
      const roll = notif.solicitante_roll || '';
      fillSelectJobs(els.notifJobSelect, ALL_JOBS_BY_ROLE, roll, '');
      els.notifJobSelect?.focus();
      return;
    }

    if (createBtn) {
      const id = Number(createBtn.dataset.notifCreate);
      const msg = mailState.messages.find((m) => m.key === `notif-${id}`);
      const notif = msg?.raw;
      if (!notif) return;
      hideMailViews();
      setMailViewHeader('Solicitud', 'Aprobar creación de empresa');
      els.mailMsgActions.innerHTML = '';
      els.notifEmpresaForm.hidden = false;
      els.notifId.value = notif.id;
      els.notifUsuarioId.value = notif.solicitante_id || '';
      els.notifRazon.value = notif.empresa_sugerida || '';
      els.notifNit.value = notif.nit_sugerido || '';
      if (els.notifSedesBuilder) {
        els.notifSedesBuilder.innerHTML = '';
        addSedeBuilderRow(els.notifSedesBuilder);
      }
      els.notifRazon.focus();
      return;
    }

    if (approve || reject) {
      const id = Number((approve || reject).dataset.approve || (approve || reject).dataset.reject);
      const decision = approve ? 'APROBADA' : 'RECHAZADA';
      const { response, data } = await api(`/api/solicitudes-permiso/${id}/resolver`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo resolver.', 'error');
        return;
      }
      showToast(data.message, 'success');
      loadBandeja();
      return;
    }

    if (activate) {
      const { response, data } = await api('/api/permisos-ampliados/activar', {
        method: 'POST',
        body: '{}',
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo activar.', 'error');
        return;
      }
      showToast(data.message, 'success');
      const me = await api('/api/me');
      if (me.response.ok && me.data.ok && me.data.user) {
        currentUser = { ...currentUser, ...me.data.user };
        buildNav();
        refreshDashHeader();
        window.AtlasOps?.refreshHelpButtons?.();
      }
      loadBandeja();
      return;
    }

    const rateBtn = event.target.closest('[data-rate]');
    if (rateBtn) {
      const id = Number(rateBtn.dataset.rate);
      const calificacion = rateBtn.dataset.rateValue;
      const { response, data } = await api(`/api/solicitudes-permiso/${id}/calificar`, {
        method: 'POST',
        body: JSON.stringify({ calificacion }),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo calificar.', 'error');
        return;
      }
      showToast(data.message, 'success');
      loadBandeja();
      return;
    }

    if (event.target.closest('[data-open-suficiencia]')) {
      openModule('suficiencia', 'instrumentos', solicitudScopeFrom(selectedSolicitudRaw()));
    }
    if (event.target.closest('[data-open-frecuencia-pm]')) {
      openModule('frecuencia-pm', null, solicitudScopeFrom(selectedSolicitudRaw()));
    }
    if (event.target.closest('[data-open-preinstalacion]')) {
      openModule('preinstalacion', null, solicitudScopeFrom(selectedSolicitudRaw()));
    }
  });

  els.notifEmpresaForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = {
      ID_Empresa: els.notifRazon.value.trim(),
      ID_NIT: els.notifNit.value.trim(),
    };
    const notifId = Number(els.notifId.value);
    const { response, data } = await api(`/api/admin/notificaciones/${notifId}/aprobar`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo crear la empresa.', 'error');
      return;
    }
    showToast(data.message, 'success');
    els.notifEmpresaForm.reset();
    if (els.notifSedesBuilder) els.notifSedesBuilder.innerHTML = '';
    els.notifEmpresaForm.hidden = true;
    mailState.selectedKey = null;
    loadBandeja();
  });

  els.notifJobForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const notifId = Number(els.notifJobId?.value);
    const job = els.notifJobSelect?.value || '';
    if (!job) {
      showToast('Selecciona el JOB.', 'error');
      return;
    }
    const { response, data } = await api(`/api/admin/notificaciones/${notifId}/asignar-job`, {
      method: 'POST',
      body: JSON.stringify({ JOB: job }),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo asignar el JOB.', 'error');
      return;
    }
    showToast(data.message, 'success');
    els.notifJobForm.reset();
    els.notifJobForm.hidden = true;
    mailState.selectedKey = null;
    loadBandeja();
    if (els.panelUsuarios && !els.panelUsuarios.hidden) loadUsers();
  });

  els.notifAddSede?.addEventListener('click', () => addSedeBuilderRow(els.notifSedesBuilder));
  els.empresaAddSede?.addEventListener('click', () => addSedeBuilderRow(els.empresaSedesBuilder));

  els.editRoll.addEventListener('change', () => {
    fillSelectJobs(els.editJob, scopedAdminJobsCatalog(), els.editRoll.value);
    syncEmpresaHintForRoll();
  });
  els.dashLogout.addEventListener('click', logout);
  if (els.logoutBtn) els.logoutBtn.addEventListener('click', logout);

  els.dashNavToggle?.addEventListener('click', toggleMobileNav);
  els.opsNavOverlay?.addEventListener('click', closeMobileNav);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMobileNav();
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 1100) closeMobileNav();
    syncMobileLayout();
  });
  window.addEventListener('orientationchange', () => {
    requestAnimationFrame(syncMobileLayout);
  });
  window.visualViewport?.addEventListener('resize', syncMobileLayout);
  window.visualViewport?.addEventListener('scroll', syncMobileLayout);
  syncMobileLayout();

  els.dashInbox?.addEventListener('click', () => {
    openModule('bandeja');
  });

  els.dashSettings?.addEventListener('click', openPerfilModal);

  document.getElementById('open-reporte-fallos')?.addEventListener('click', openFallosModal);
  els.dashReporteFallos?.addEventListener('click', openFallosModal);
  document.querySelectorAll('[data-close-fallos-modal]').forEach((el) => {
    el.addEventListener('click', closeFallosModal);
  });
  els.fallosForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (els.fallosFormError) {
      els.fallosFormError.hidden = true;
      els.fallosFormError.textContent = '';
    }
    const tipo = els.fallosTipo?.value || '';
    const descripcion = els.fallosDescripcion?.value.trim() || '';
    const solucion = els.fallosSolucion?.value.trim() || '';
    if (!tipo) {
      showToast('Seleccione el tipo de falla.', 'error');
      return;
    }
    if (descripcion.length < 8) {
      showToast('Describa la novedad (mínimo 8 caracteres).', 'error');
      return;
    }
    const L = window.SIGTB_LIMITS || {};
    if (L.description && descripcion.length > L.description) {
      showToast(`La descripción no puede superar ${L.description} caracteres.`, 'error');
      return;
    }
    if (L.solution && solucion.length > L.solution) {
      showToast(`La solución no puede superar ${L.solution} caracteres.`, 'error');
      return;
    }
    const { response, data } = await api('/api/reportes-fallos', {
      method: 'POST',
      body: JSON.stringify({
        tipo,
        descripcion,
        solucion_recomendada: solucion,
      }),
    });
    if (!response.ok || !data.ok) {
      const msg = data.error || 'No se pudo radicar el reporte.';
      if (els.fallosFormError) {
        els.fallosFormError.hidden = false;
        els.fallosFormError.textContent = msg;
      }
      showToast(msg, 'error');
      return;
    }
    showToast(
      `${data.message} Radicación: ${data.creation_date || ''} · ${data.remitente_nombre || 'Invitado'}.`,
      'success'
    );
    closeFallosModal();
    if (currentUser?.ROLL === 'ADMIN') {
      loadBandeja();
      loadFallosDashboard();
    }
  });

  els.inventarioCrear?.addEventListener('click', () => {
    if (!els.inventarioServicioSelect?.value) {
      showToast('Seleccione empresa, sede y servicio para crear el equipo.', 'error');
      return;
    }
    openEquipoModal(null);
  });

  els.direccionLogDownload?.addEventListener('click', async () => {
    const empId = Number(els.direccionLogDownload.dataset.empresaId || els.direccionEmpresa?.value);
    if (!empId) return;
    if (!window.confirm('Al descargar, el log de esta empresa se eliminará del servidor. ¿Continuar?')) {
      return;
    }
    try {
      await downloadFile(`/api/empresas/${empId}/eventos.xlsx`, `log_eventos_${empId}.xlsx`);
      showToast('Log descargado y eliminado del servidor.', 'success');
      loadDireccionEventLog(empId);
    } catch (err) {
      showToast(err.message || 'No se pudo descargar el log.', 'error');
    }
  });

  document.querySelectorAll('[data-close-perfil-modal]').forEach((el) => {
    el.addEventListener('click', closePerfilModal);
  });

  els.perfilForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (els.perfilMsg) {
      els.perfilMsg.hidden = true;
      els.perfilMsg.textContent = '';
    }
    const password = els.perfilPassword?.value || '';
    const password2 = els.perfilPassword2?.value || '';
    if (password || password2) {
      if (password !== password2) {
        if (els.perfilMsg) {
          els.perfilMsg.hidden = false;
          els.perfilMsg.textContent = 'Las contraseñas no coinciden.';
        }
        showToast('Las contraseñas no coinciden.', 'error');
        return;
      }
    }
    const payload = {
      NAME_USER: els.perfilName.value.trim(),
      LAST_NAME_USER: els.perfilLastName.value.trim(),
      telefono: els.perfilTelefono.value.trim(),
    };
    if (password) payload.password = password;
    if (!currentUser.aviso_aceptado_en) {
      if (!els.perfilAvisoCheck?.checked) {
        if (els.perfilMsg) {
          els.perfilMsg.hidden = false;
          els.perfilMsg.textContent = 'Debe autorizar el tratamiento de sus datos personales.';
        }
        showToast('Debe autorizar el tratamiento de sus datos personales.', 'error');
        return;
      }
      payload.aviso_aceptado = true;
    }
    const { response, data } = await api('/api/me/perfil', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      const err =
        data.error ||
        Object.values(data.fieldErrors || {})[0] ||
        'No se pudo guardar el perfil.';
      if (els.perfilMsg) {
        els.perfilMsg.hidden = false;
        els.perfilMsg.textContent = err;
      }
      showToast(err, 'error');
      return;
    }
    currentUser = { ...currentUser, ...data.user };
    refreshDashHeader();
    closePerfilModal();
    showToast(data.message || 'Perfil actualizado.', 'success');
  });

  els.inventarioEmpresaSelect?.addEventListener('change', () => {
    if (window.AtlasOps?._orgScopeApplying) return;
    fillSedeSelect(els.inventarioSedeSelect, els.inventarioEmpresaSelect.value);
    fillServicioSelect(els.inventarioServicioSelect, '');
    if (els.inventarioSearch) els.inventarioSearch.value = '';
    inventarioCache = [];
    inventarioRecycle = null;
    renderInventarioRecycle();
    if (els.inventarioSearchHint) {
      els.inventarioSearchHint.hidden = true;
      els.inventarioSearchHint.textContent = '';
    }
    els.inventarioTableBody.innerHTML =
      '<tr><td colspan="11">Selecciona sede y servicio para ver el inventario.</td></tr>';
    rememberInventarioSelection();
  });

  els.inventarioSedeSelect.addEventListener('change', () => {
    if (window.AtlasOps?._orgScopeApplying) return;
    fillServicioSelect(els.inventarioServicioSelect, els.inventarioSedeSelect.value);
    if (els.inventarioSearch) els.inventarioSearch.value = '';
    inventarioCache = [];
    inventarioRecycle = null;
    renderInventarioRecycle();
    if (els.inventarioSearchHint) {
      els.inventarioSearchHint.hidden = true;
      els.inventarioSearchHint.textContent = '';
    }
    els.inventarioTableBody.innerHTML =
      '<tr><td colspan="11">Selecciona un servicio para ver el inventario.</td></tr>';
    rememberInventarioSelection();
  });

  els.sedesList?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-select-empresa]');
    if (!btn) return;
    navigateTo({
      panel: 'sedes',
      sectionId: 'organizacion',
      empresaId: btn.dataset.selectEmpresa,
    });
  });

  els.empresasList?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-select-empresa-catalog]');
    if (!btn) return;
    navigateTo({
      panel: 'empresas',
      sectionId: 'organizacion',
      empresaId: btn.dataset.selectEmpresaCatalog,
    });
  });

  els.empresasDetail?.addEventListener('click', async (event) => {
    if (event.target.closest('[data-empresas-back]')) {
      inAppBack({ panel: 'empresas', sectionId: 'organizacion' });
      return;
    }
    const deleteEmpresaBtn = event.target.closest('[data-delete-empresa]');
    if (deleteEmpresaBtn) {
      event.preventDefault();
      await deleteEmpresaById(deleteEmpresaBtn.dataset.deleteEmpresa);
      return;
    }
    const deleteSedeBtn = event.target.closest('[data-delete-sede]');
    if (deleteSedeBtn) {
      event.preventDefault();
      await deleteSedeById(deleteSedeBtn.dataset.deleteSede);
      return;
    }
    const sedePdfBtn = event.target.closest('[data-export-sede-inv]');
    if (sedePdfBtn) {
      event.preventDefault();
      await exportInventarioSede(sedePdfBtn.dataset.sedeId);
      return;
    }
    const sedeBtn = event.target.closest('[data-select-sede]');
    if (sedeBtn) {
      navigateTo({
        panel: 'empresas',
        sectionId: 'organizacion',
        empresaId: empresasSelectedId,
        sedeId: sedeBtn.dataset.selectSede,
      });
    }
  });

  els.assignEmpresa?.addEventListener('change', async () => {
    const empresaId = els.assignEmpresa.value;
    fillAssignSedeSelect(empresaId);
    await loadEmpresaPersonal(empresaId);
  });

  els.sedesDetail?.addEventListener('click', async (event) => {
    if (event.target.closest('[data-sedes-back]')) {
      inAppBack({ panel: 'sedes', sectionId: 'organizacion' });
      return;
    }
    const sedePdfBtn = event.target.closest('[data-export-sede-inv]');
    if (sedePdfBtn) {
      event.preventDefault();
      await exportInventarioSede(sedePdfBtn.dataset.sedeId);
      return;
    }
    const openServicioBtn = event.target.closest('[data-open-servicio]');
    if (openServicioBtn) {
      event.preventDefault();
      await openServicioInventario({
        empresaId: openServicioBtn.dataset.empresaId,
        sedeId: openServicioBtn.dataset.sedeId,
        servicioId: openServicioBtn.dataset.openServicio,
      });
      return;
    }
    const exportBtn = event.target.closest('[data-export-inv]');
    if (exportBtn) {
      await exportInventarioServicio(
        exportBtn.dataset.servicioId,
        exportBtn.dataset.exportInv,
        exportBtn.dataset.equipo || null
      );
    }
  });

  els.direccionEmpresa?.addEventListener('change', () => {
    direccionInvCache = {};
    renderDireccionTree(els.direccionEmpresa.value);
    loadDireccionEventLog(els.direccionEmpresa.value);
  });

  els.direccionTree?.addEventListener('click', async (event) => {
    const openServicioBtn = event.target.closest('[data-open-servicio]');
    if (openServicioBtn) {
      event.preventDefault();
      const details = openServicioBtn.closest('details.direccion-servicio');
      await openServicioInventario({
        empresaId:
          openServicioBtn.dataset.empresaId || details?.dataset?.empresaId,
        sedeId: openServicioBtn.dataset.sedeId || details?.dataset?.sedeId,
        servicioId: openServicioBtn.dataset.openServicio,
      });
      return;
    }
    const exportBtn = event.target.closest('[data-export-inv]');
    if (exportBtn) {
      event.preventDefault();
      await exportInventarioServicio(
        exportBtn.dataset.servicioId,
        exportBtn.dataset.exportInv,
        exportBtn.dataset.equipo || null
      );
      return;
    }
    const chip = event.target.closest('[data-open-inv-tipo]');
    if (!chip) return;
    event.preventDefault();
    openDireccionInvDetalle(chip.dataset.servicioId, chip.dataset.openInvTipo);
  });

  els.direccionInvModal?.addEventListener('click', (event) => {
    const modalExportBtn = event.target.closest('[data-export-inv-modal]');
    if (modalExportBtn) {
      event.preventDefault();
      exportDireccionModalInventario(modalExportBtn.dataset.exportInvModal);
      return;
    }
    const exportBtn = event.target.closest('[data-export-inv]');
    if (exportBtn) {
      exportInventarioServicio(
        exportBtn.dataset.servicioId || direccionInvModalServicioId,
        exportBtn.dataset.exportInv,
        exportBtn.dataset.equipo || direccionInvModalEquipoTipo
      );
    }
  });

  els.direccionInvModal?.querySelectorAll('[data-close-direccion-inv-modal]').forEach((n) =>
    n.addEventListener('click', closeDireccionInvModal)
  );

  els.inventarioServicioSelect.addEventListener('change', () => {
    if (window.AtlasOps?._orgScopeApplying) return;
    if (els.inventarioSearch) els.inventarioSearch.value = '';
    rememberInventarioSelection();
    loadInventario(els.inventarioServicioSelect.value, { resetPage: true });
  });
  document.addEventListener('orgscope:applied', (ev) => {
    if (ev.detail?.key !== 'inventario') return;
    const srv = els.inventarioServicioSelect?.value;
    if (els.inventarioSearch) els.inventarioSearch.value = '';
    rememberInventarioSelection();
    if (srv) loadInventario(srv, { resetPage: true });
  });

  // Filtrado en vivo: cualquier carácter común en #BIOMÉDICA o EQUIPO actualiza la lista.
  els.panelInventario?.addEventListener('input', (event) => {
    if (event.target?.id !== 'inventario-search') return;
    inventarioPage = 1;
    if (inventarioServerPaged) {
      clearTimeout(inventarioSearchTimer);
      inventarioSearchTimer = setTimeout(() => {
        const srv = els.inventarioServicioSelect?.value;
        if (srv) loadInventario(srv, { resetPage: true });
      }, 300);
    } else {
      renderInventarioTable();
    }
  });
  els.panelInventario?.addEventListener('keyup', (event) => {
    if (event.target?.id !== 'inventario-search') return;
    if (inventarioServerPaged) return;
    renderInventarioTable();
  });
  els.panelInventario?.addEventListener('search', (event) => {
    if (event.target?.id !== 'inventario-search') return;
    inventarioPage = 1;
    if (inventarioServerPaged) {
      const srv = els.inventarioServicioSelect?.value;
      if (srv) loadInventario(srv, { resetPage: true });
    } else {
      renderInventarioTable();
    }
  });

  els.inventarioTableBody?.addEventListener('click', async (event) => {
    const editBtn = event.target.closest('[data-edit-equipo]');
    if (editBtn) {
      const id = Number(editBtn.dataset.editEquipo);
      const equipo = inventarioCache.find((e) => e.id === id);
      if (equipo) openEquipoModal(equipo);
      return;
    }

    const histBtn = event.target.closest('[data-historial-equipo]');
    if (histBtn) {
      openInvEjecucionModal(Number(histBtn.dataset.historialEquipo));
      return;
    }

    const deleteBtn = event.target.closest('[data-delete-equipo]');
    if (!deleteBtn) return;
    const id = Number(deleteBtn.dataset.deleteEquipo);
    const equipo = inventarioCache.find((e) => e.id === id);
    const label = equipo?.equipo || `#${id}`;
    if (!window.confirm(`¿Eliminar el equipo "${label}"? Esta acción no se puede deshacer.`)) {
      return;
    }
    const { response, data } = await api(`/api/inventario/${id}`, { method: 'DELETE' });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo eliminar el equipo.', 'error');
      return;
    }
    showToast(data.message || 'Equipo eliminado.', 'success');
    loadInventario(els.inventarioServicioSelect.value);
  });

  els.equipoModal?.querySelectorAll('[data-close-equipo-modal]').forEach((n) =>
    n.addEventListener('click', closeEquipoModal)
  );

  document.querySelectorAll('[data-close-inv-ejecucion]').forEach((n) =>
    n.addEventListener('click', closeInvEjecucionModal)
  );
  document.getElementById('inv-ej-prev')?.addEventListener('click', () => {
    if (invEjState.page > 1) {
      invEjState.page -= 1;
      loadInvEjecucion();
    }
  });
  document.getElementById('inv-ej-next')?.addEventListener('click', () => {
    invEjState.page += 1;
    loadInvEjecucion();
  });
  bindDuracionDesdeFechas('inv-ej-atencion', 'inv-ej-cierre', 'inv-ej-duracion');
  document.getElementById('inv-ejecucion-form')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (invEjSaving) return;
    const equipoId = Number(document.getElementById('inv-ej-equipo-id')?.value);
    if (!equipoId) return;
    const payload = {
      tipo_mantenimiento: document.getElementById('inv-ej-tipo')?.value,
      fecha_ejecucion: document.getElementById('inv-ej-fecha')?.value,
      fecha_atencion: document.getElementById('inv-ej-atencion')?.value || null,
      fecha_cierre: document.getElementById('inv-ej-cierre')?.value || null,
      observaciones: document.getElementById('inv-ej-obs')?.value || '',
    };
    invEjSaving = true;
    try {
    const { response, data } = await api(`/api/inventario/${equipoId}/ejecucion`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const msg = document.getElementById('inv-ej-msg');
    if (!response.ok || !data.ok) {
      if (msg) {
        msg.hidden = false;
        msg.textContent = data.error || 'No se pudo guardar.';
      }
      showToast(data.error || 'No se pudo guardar la ejecución.', 'error');
      return;
    }
    if (msg) {
      msg.hidden = false;
      msg.textContent = 'Ejecución guardada. Inventario y demás módulos siguen disponibles.';
    }
    showToast(data.message || 'Ejecución registrada.', 'success');
    document.getElementById('inv-ejecucion-form')?.reset();
    document.getElementById('inv-ej-equipo-id').value = String(equipoId);
    invEjState.page = 1;
    await loadInvEjecucion();
    } finally {
      invEjSaving = false;
    }
  });

  els.equipoForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (equipoSaving) return;
    const id = Number(els.equipoId.value);
    const payload = {
      num_biomedica: els.equipoBiomedica.value.trim(),
      codigo_activo: els.equipoActivo?.value.trim() || '',
      registro_invima: els.equipoInvima.value.trim(),
      equipo: els.equipoNombre.value.trim(),
      marca: els.equipoMarca.value.trim(),
      serie: els.equipoSerie.value.trim(),
      modelo: els.equipoModelo.value.trim(),
      clasificacion_riesgo: els.equipoRiesgo.value.trim(),
      ubicacion: els.equipoUbicacion.value.trim(),
      estado: els.equipoEstado.value,
      aplica_mp: triSelectValue(els.equipoAplicaMp),
      freq_mp: numOrNull(els.equipoFreqMp),
      tiempo_mp: numOrNull(els.equipoTiempoMp),
      aplica_cal: triSelectValue(els.equipoAplicaCal),
      freq_cal: numOrNull(els.equipoFreqCal),
      tiempo_cal: numOrNull(els.equipoTiempoCal),
      aplica_val: triSelectValue(els.equipoAplicaVal),
      freq_val: numOrNull(els.equipoFreqVal),
      tiempo_val: numOrNull(els.equipoTiempoVal),
    };
    if (!payload.equipo) {
      showToast('EQUIPO es obligatorio.', 'error');
      return;
    }
    const creating = !id;
    const servicioId = els.inventarioServicioSelect?.value;
    if (creating && !servicioId) {
      showToast('Seleccione un servicio antes de crear el equipo.', 'error');
      return;
    }
    const url = creating
      ? `/api/servicios/${servicioId}/inventario`
      : `/api/inventario/${id}`;
    equipoSaving = true;
    try {
      const { response, data } = await api(url, {
        method: creating ? 'POST' : 'PUT',
        body: JSON.stringify(payload),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || (creating ? 'No se pudo crear el equipo.' : 'No se pudo actualizar el equipo.'), 'error');
        return;
      }
      showToast(data.message || (creating ? 'Equipo creado.' : 'Equipo actualizado.'), 'success');
      closeEquipoModal();
      loadInventario(els.inventarioServicioSelect.value);
    } finally {
      equipoSaving = false;
    }
  });

  els.rbacRoleForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const nombre_rol = els.rbacRoleName.value.trim();
    const { response, data } = await api('/admin/rbac/roles', {
      method: 'POST',
      body: JSON.stringify({ nombre_rol }),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo crear el rol.', 'error');
      return;
    }
    showToast(data.message, 'success');
    els.rbacRoleForm.reset();
    loadRbacPanel();
  });

  els.rbacRolesList?.addEventListener('click', async (event) => {
    if (event.target.closest('[data-cancel-rename]')) {
      rbacRenamingRolId = null;
      renderRbacRoles();
      return;
    }

    if (event.target.closest('[data-cancel-delete]')) {
      rbacDeletingRolId = null;
      renderRbacRoles();
      return;
    }

    const renameBtn = event.target.closest('[data-rename-rol]');
    if (renameBtn) {
      rbacDeletingRolId = null;
      rbacRenamingRolId = Number(renameBtn.dataset.renameRol);
      rbacSelectedRolId = rbacRenamingRolId;
      renderRbacRoles();
      renderRbacRolePerms();
      return;
    }

    const deleteBtn = event.target.closest('[data-delete-rol]');
    if (deleteBtn) {
      rbacRenamingRolId = null;
      rbacDeletingRolId = Number(deleteBtn.dataset.deleteRol);
      rbacSelectedRolId = rbacDeletingRolId;
      renderRbacRoles();
      renderRbacRolePerms();
      return;
    }

    const confirmDeleteBtn = event.target.closest('[data-confirm-delete-rol]');
    if (confirmDeleteBtn) {
      const id = Number(confirmDeleteBtn.dataset.confirmDeleteRol);
      confirmDeleteBtn.disabled = true;
      const { response, data } = await api(`/admin/rbac/roles/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo eliminar el rol.', 'error');
        confirmDeleteBtn.disabled = false;
        return;
      }
      showToast(data.message || 'Rol eliminado.', 'success');
      rbacDeletingRolId = null;
      rbacRenamingRolId = null;
      if (Number(rbacSelectedRolId) === id) rbacSelectedRolId = null;
      applyRbacState(data);
      return;
    }

    const selectBtn = event.target.closest('[data-select-rol]');
    if (selectBtn) {
      rbacRenamingRolId = null;
      rbacDeletingRolId = null;
      rbacSelectedRolId = Number(selectBtn.dataset.selectRol);
      renderRbacRoles();
      renderRbacRolePerms();
      return;
    }

    const toggleBtn = event.target.closest('[data-toggle-rol]');
    if (toggleBtn) {
      const id = Number(toggleBtn.dataset.toggleRol);
      const role = rbacState.roles.find((r) => r.id_rol === id);
      const estado = role?.estado === 'ACTIVO' ? 'INACTIVO' : 'ACTIVO';
      const { response, data } = await api(`/admin/rbac/roles/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ estado }),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo cambiar el estado.', 'error');
        return;
      }
      showToast(data.message, 'success');
      rbacRenamingRolId = null;
      rbacDeletingRolId = null;
      loadRbacPanel();
    }
  });

  els.rbacRolesList?.addEventListener('submit', async (event) => {
    const form = event.target.closest('[data-rename-form]');
    if (!form) return;
    event.preventDefault();
    event.stopPropagation();
    const id = Number(form.dataset.renameForm);
    const input = form.querySelector('input[name="nombre_rol"]');
    const nombre = (input?.value || '').trim();
    if (!Number.isFinite(id) || id <= 0) {
      showToast('Rol inválido.', 'error');
      return;
    }
    if (!nombre) {
      showToast('Indica el nombre del rol.', 'error');
      input?.focus();
      return;
    }
    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;
    try {
      const { response, data } = await api(`/admin/rbac/roles/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ nombre_rol: nombre }),
      });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo renombrar.', 'error');
        return;
      }
      showToast(data.message || 'Rol renombrado.', 'success');
      rbacRenamingRolId = null;
      loadRbacPanel();
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  });

  els.rbacPermsList?.addEventListener('click', (event) => {
    const groupToggle = event.target.closest('[data-toggle-group]');
    if (!groupToggle) return;
    event.preventDefault();
    const key = groupToggle.dataset.toggleGroup;
    const section = groupToggle.closest('.rbac-perm-group');
    const body = section?.querySelector('.rbac-perm-group__body');
    const open = !rbacExpandedGroups.has(key);
    if (open) rbacExpandedGroups.add(key);
    else rbacExpandedGroups.delete(key);
    section?.classList.toggle('is-open', open);
    groupToggle.setAttribute('aria-expanded', String(open));
    if (body) body.hidden = !open;
  });

  els.rbacPermsList?.addEventListener('change', (event) => {
    const input = event.target.closest('input[data-matrix-rol]');
    if (!input) return;
    const key = `${input.dataset.matrixRol}:${input.dataset.matrixJob}`;
    rbacState.permisos[key] = {
      ...(rbacState.permisos[key] || {}),
      permiso_activo: input.checked,
    };
    const label = input.closest('.rbac-toggle');
    if (label) label.classList.toggle('is-on', input.checked);
  });

  els.rbacSaveMatrix?.addEventListener('click', async () => {
    if (!rbacSelectedRolId) {
      showToast('Selecciona un rol primero.', 'error');
      return;
    }
    const permisos = [];
    els.rbacPermsList?.querySelectorAll('input[data-matrix-rol]').forEach((input) => {
      permisos.push({
        id_rol: Number(input.dataset.matrixRol),
        id_job: Number(input.dataset.matrixJob),
        permiso_activo: input.checked,
      });
    });
    if (!permisos.length) {
      showToast('No hay permisos para guardar en este rol.', 'error');
      return;
    }
    els.rbacSaveMatrix.disabled = true;
    const { response, data } = await api('/admin/rbac/matrix', {
      method: 'PUT',
      body: JSON.stringify({ permisos }),
    });
    els.rbacSaveMatrix.disabled = false;
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo guardar la matriz.', 'error');
      return;
    }
    showToast(
      data.message ||
        'Permisos guardados. Los usuarios afectados los verán al iniciar sesión o al refrescar la sesión.',
      'success'
    );
    applyRbacState(data);
  });

  els.backupCreateBtn?.addEventListener('click', async () => {
    els.backupCreateBtn.disabled = true;
    const { response, data } = await api('/admin/backups', { method: 'POST' });
    els.backupCreateBtn.disabled = false;
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo crear el respaldo.', 'error');
      return;
    }
    showToast(`Respaldo ${data.id} creado.`, 'success');
    loadBackupsPanel();
  });

  els.backupTableBody?.addEventListener('click', async (event) => {
    const btn = event.target.closest('.backup-restore-btn');
    if (!btn) return;
    const snapshotId = btn.dataset.id;
    if (!snapshotId) return;
    const ok = window.confirm(
      `¿Restaurar el respaldo ${snapshotId}?\nSe reemplazarán las bases actuales. El archivo corrupto o vigente se sustituye por esta copia.`
    );
    if (!ok) return;
    btn.disabled = true;
    const { response, data } = await api(`/admin/backups/${encodeURIComponent(snapshotId)}/restore`, {
      method: 'POST',
    });
    btn.disabled = false;
    if (!response.ok || !data.ok) {
      showToast(data.error || data.message || 'No se pudo restaurar.', 'error');
      return;
    }
    showToast(data.message || 'Bases restauradas.', 'success');
    loadBackupsPanel();
  });

  els.rbacExportCsv?.addEventListener('click', async () => {
    try {
      await downloadFile('/admin/rbac/matrix/export.csv', 'rbac_roles_permisos.csv');
      showToast('CSV de roles y permisos exportado.', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  els.rbacExportXlsx?.addEventListener('click', async () => {
    try {
      await downloadFile('/admin/rbac/matrix/export.xlsx', 'rbac_roles_permisos.xlsx');
      showToast('XLSX de roles y permisos exportado.', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  els.inventarioImportBtn.addEventListener('click', async () => {
    const servicioId = els.inventarioServicioSelect.value;
    const file = els.inventarioFile.files?.[0];
    if (!servicioId || !file) {
      showToast('Selecciona servicio y archivo.', 'error');
      return;
    }
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`/api/servicios/${servicioId}/inventario/import`, {
      method: 'POST',
      credentials: 'same-origin',
      body: form,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      showToast(data.error || 'Error al importar.', 'error');
      return;
    }
    showToast(data.message, 'success');
    loadInventario(servicioId);
  });

  els.inventarioExportCsv.addEventListener('click', async () => {
    await exportInventarioServicio(els.inventarioServicioSelect.value, 'csv');
  });

  els.inventarioExportXlsx.addEventListener('click', async () => {
    await exportInventarioServicio(els.inventarioServicioSelect.value, 'xlsx');
  });

  els.inventarioExportPdf?.addEventListener('click', async () => {
    await exportInventarioServicio(els.inventarioServicioSelect.value, 'pdf');
  });

  els.inventarioPurgeBtn?.addEventListener('click', async () => {
    const servicioId = els.inventarioServicioSelect?.value;
    if (!servicioId) {
      showToast('Selecciona sede y servicio.', 'error');
      return;
    }
    const n = inventarioCache.length;
    if (!n) {
      showToast('No hay inventario cargado en este servicio.', 'error');
      return;
    }
    const replaceNote = inventarioRecycle?.can_restore
      ? '\nYa existe un backup de borrado vigente: este lo reemplazará.'
      : '';
    const ok = window.confirm(
      `Se eliminarán ${n} equipo(s) del servicio actual.\n` +
        `Dispone de 30 minutos para restaurarlos con «Restaurar último backup».\n` +
        `Después se eliminará de forma definitiva.\n` +
        `El auto-backup del sistema (usuarios, empresas, solicitudes) no se modifica.` +
        replaceNote
    );
    if (!ok) return;
    const { response, data } = await api(`/api/servicios/${servicioId}/inventario/eliminar-cargado`, {
      method: 'POST',
      body: '{}',
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo eliminar el inventario.', 'error');
      return;
    }
    showToast(data.message, 'success');
    loadInventario(servicioId);
  });

  els.inventarioRestoreBtn?.addEventListener('click', async () => {
    const servicioId = els.inventarioServicioSelect?.value;
    if (!servicioId) {
      showToast('Selecciona sede y servicio.', 'error');
      return;
    }
    if (inventarioCache.length) {
      const ok = window.confirm(
        'Hay inventario en pantalla. Restaurar el último backup lo sustituirá por la copia del borrado.'
      );
      if (!ok) return;
    }
    const { response, data } = await api(`/api/servicios/${servicioId}/inventario/restaurar-backup`, {
      method: 'POST',
      body: '{}',
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo restaurar el inventario.', 'error');
      return;
    }
    showToast(data.message, 'success');
    loadInventario(servicioId);
  });

  els.empresaForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = {
      ID_Empresa: document.getElementById('empresa-razon').value.trim(),
      ID_NIT: document.getElementById('empresa-nit').value.trim(),
      sedes: collectSedesFromBuilder(els.empresaSedesBuilder),
    };
    if (!payload.sedes.length) {
      showToast('Añade al menos una sede exclusiva de la empresa.', 'error');
      return;
    }
    const { response, data } = await api('/api/empresas', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo crear la empresa.', 'error');
      return;
    }
    showToast(data.message, 'success');
    els.empresaForm.reset();
    if (els.empresaSedesBuilder) {
      els.empresaSedesBuilder.innerHTML = '';
      addSedeBuilderRow(els.empresaSedesBuilder);
    }
    sedesCache = [];
    loadEmpresasPanel();
  });

  els.sedeForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = {
      empresa_id: Number(els.sedeEmpresaSelect.value),
      name_sede: document.getElementById('sede-nombre').value.trim(),
      ID_sede: document.getElementById('sede-id')?.value.trim() || undefined,
      servicios: parseServiciosInput(document.getElementById('sede-servicios')?.value),
    };
    const { response, data } = await api('/api/sedes', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo crear la sede.', 'error');
      return;
    }
    showToast(data.message, 'success');
    els.sedeForm.reset();
    sedesCache = [];
    loadEmpresasPanel();
  });

  els.assignForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const empresaId = Number(els.assignEmpresa?.value || 0);
    const sedeId = els.assignSede.value;
    const usuarioId = Number(els.assignUser.value);
    if (!sedeId || !usuarioId) {
      showToast('Selecciona sede y personal.', 'error');
      return;
    }
    const person = (empresasEmpresaPersonal || []).find(
      (p) => Number(p.id_usuario) === usuarioId
    );
    if (empresaId && person?.empresa_id && Number(person.empresa_id) !== empresaId) {
      showToast(
        'El usuario ya pertenece a otra empresa y no puede asignarse a sedes de esta.',
        'error'
      );
      return;
    }
    const { response, data } = await api(`/api/sedes/${sedeId}/asignar-personal`, {
      method: 'POST',
      body: JSON.stringify({ usuario_id: usuarioId }),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo asignar.', 'error');
      return;
    }
    showToast(data.message, 'success');
    if (
      empresasSelectedId &&
      Number(empresasSelectedSedeId) === Number(sedeId)
    ) {
      showSedePersonal(sedeId);
    } else if (empresasSelectedId) {
      empresasSelectedSedeId = Number(sedeId);
      showSedePersonal(sedeId);
    }
  });

  els.exportCsvBtn?.addEventListener('click', async () => {
    try {
      await downloadFile('/admin/users/export.csv', 'usuarios.csv');
      showToast('CSV de usuarios exportado.', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  els.exportXlsxBtn?.addEventListener('click', async () => {
    try {
      await downloadFile('/admin/users/export.xlsx', 'usuarios.xlsx');
      showToast('XLSX de usuarios exportado.', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  els.adminRefreshBtn?.addEventListener('click', loadUsers);
  els.adminCreateUserBtn?.addEventListener('click', async () => {
    await loadAdminRoles();
    openCreateUserModal();
  });

  els.usersTableBody?.addEventListener('click', async (event) => {
    const editBtn = event.target.closest('[data-edit-user]');
    const deleteBtn = event.target.closest('[data-delete-user]');
    if (editBtn) {
      const id = Number(editBtn.dataset.editUser);
      const user = usersCache.find((u) => u.id_usuario === id);
      if (user) openEditModal(user);
    }
    if (deleteBtn) {
      const id = Number(deleteBtn.dataset.deleteUser);
      if (!window.confirm('¿Eliminar este usuario?')) return;
      const { response, data } = await api(`/admin/users/${id}`, { method: 'DELETE' });
      if (!response.ok || !data.ok) {
        showToast(data.error || 'No se pudo eliminar.', 'error');
        return;
      }
      showToast(data.message, 'success');
      loadUsers();
    }
  });

  function applyFieldErrors(fieldErrors) {
    if (!fieldErrors) return;
    const map = {
      usuario_login: els.editEmail,
      password: els.editPassword,
      NAME_USER: els.editName,
      LAST_NAME_USER: els.editLastName,
      ROLL: els.editRoll,
      JOB: els.editJob,
      creation_date: els.editCreation,
      empresa_id: els.editEmpresa,
    };
    Object.entries(fieldErrors).forEach(([key, message]) => {
      setFieldError(map[key] || document.getElementById(key), message);
    });
  }

  els.editForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFieldErrors(els.editForm);
    const userId = Number(els.editId.value);
    const roll = els.editRoll.value;
    const empresaVal = els.editEmpresa?.value || '';
    if (roll && roll !== 'ADMIN' && !empresaVal && editModalMode === 'create') {
      setFieldError(els.editEmpresa, 'Debes asignar la empresa a la que pertenece el usuario.');
      showToast('Validación fallida. Asigna una empresa al usuario.', 'error');
      return;
    }
    if (!els.editJob.value) {
      setFieldError(els.editJob, 'Debes asignar el JOB.');
      showToast('Validación fallida. Asigna el cargo (JOB).', 'error');
      return;
    }
    const payload = {
      usuario_login: normalizeEmail(els.editEmail.value),
      password: els.editPassword.value,
      NAME_USER: els.editName.value.trim(),
      LAST_NAME_USER: els.editLastName.value.trim(),
      ROLL: roll,
      JOB: els.editJob.value,
      creation_date: els.editCreation.value.trim(),
      empresa_id: empresaVal ? Number(empresaVal) : null,
    };
    if (editModalMode === 'create') {
      const pwdCheck = validatePassword(payload.password);
      if (!pwdCheck.valid) {
        setFieldError(els.editPassword, pwdCheck.errors.join(' '));
        showToast('Revisa la contraseña.', 'error');
        return;
      }
      const { response, data } = await api('/admin/users', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (!response.ok || !data.ok) {
        applyFieldErrors(data.fieldErrors);
        showToast(data.error || 'No se pudo crear el usuario.', 'error');
        return;
      }
      showToast(data.message, 'success');
      closeEditModal();
      loadUsers();
      return;
    }
    const { response, data } = await api(`/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      applyFieldErrors(data.fieldErrors);
      showToast(data.error || 'No se pudo actualizar.', 'error');
      return;
    }
    showToast(data.message, 'success');
    closeEditModal();
    loadUsers();
  });

  els.solicitudForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const dest = document.getElementById('solicitud-destinatario')?.value;
    if (!dest) {
      showToast('Selecciona el destinatario.', 'error');
      return;
    }
    if (dest === 'administracion' && !isDireccionMailUser()) {
      showToast('Solo Dirección puede solicitar a Administración.', 'error');
      return;
    }
    // Si el select está disabled (sede única), reactivar temporalmente no hace falta:
    // .value sigue disponible en JS.
    const sedeId = Number(els.solicitudSede.value);
    if (!sedeId) {
      showToast('Selecciona o asigna una sede para radicar la solicitud.', 'error');
      return;
    }
    const L = window.SIGTB_LIMITS || {};
    const asunto = document.getElementById('solicitud-asunto')?.value.trim() || '';
    const mensaje = document.getElementById('solicitud-mensaje')?.value.trim() || '';
    if (!asunto) {
      showToast('Escribe el asunto de la solicitud.', 'error');
      return;
    }
    if (L.subject && asunto.length > L.subject) {
      showToast(`El asunto no puede superar ${L.subject} caracteres.`, 'error');
      return;
    }
    if (!mensaje) {
      showToast('Escribe el mensaje de la solicitud.', 'error');
      return;
    }
    if (L.message && mensaje.length > L.message) {
      showToast(`El mensaje no puede superar ${L.message} caracteres.`, 'error');
      return;
    }
    const tipo = document.getElementById('solicitud-tipo')?.value || 'consulta_general';
    let destinatario_rol = dest;
    if (tipo === 'actualizar_datos_suficiencia') destinatario_rol = 'asistencial';
    if (tipo === 'permisos_ampliados' && !destinatario_rol) destinatario_rol = 'coordinacion';
    const payload = {
      sede_id: sedeId,
      tipo,
      asunto,
      mensaje,
      destinatario_rol,
      prioridad: document.getElementById('solicitud-prioridad')?.value || 'MODERADA',
    };
    const { response, data } = await api('/api/solicitudes-permiso', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo radicar la solicitud.', 'error');
      return;
    }
    showToast(data.message || 'Solicitud radicada.', 'success');
    els.solicitudForm.reset();
    mailState.folder = 'solicitudes';
    mailState.selectedKey = null;
    loadBandeja();
  });

  els.loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFieldErrors(els.loginForm);
    const usuario_login = normalizeEmail(els.loginEmail.value);
    const password = els.loginPassword.value;
    if (!isValidEmail(usuario_login) || !password) {
      showToast('Corrige correo y contraseña.', 'error');
      return;
    }
    const submitBtn = document.getElementById('login-submit');
    submitBtn.disabled = true;
    try {
      const { response, data } = await api('/login', {
        method: 'POST',
        body: JSON.stringify({ usuario_login, password }),
      });
      if (response.status === 404 && data.allowRegister) {
        showToast(data.error, 'info');
        openModal(usuario_login);
        return;
      }
      if (!response.ok || !data.ok) {
        forgetPasswordForUser(usuario_login);
        showToast(data.error || 'Login fallido.', 'error');
        return;
      }
      if (els.loginRemember?.checked) {
        savePasswordForUser(usuario_login, password);
      } else {
        forgetPasswordForUser(usuario_login);
      }
      wipeLoginFormFields();
      showToast(data.message, 'success');
      await openDashboard(data.user);
    } catch {
      showToast('Error de red al iniciar sesión.', 'error');
    } finally {
      submitBtn.disabled = false;
    }
  });

  els.loginEmail?.addEventListener('blur', () => {
    window.setTimeout(() => closeLoginEmailMenu(), 140);
  });
  els.loginEmail?.addEventListener('focus', () => {
    if (savedLoginEmails().length) openLoginEmailMenu(els.loginEmail.value);
  });
  els.loginEmail?.addEventListener('input', () => {
    if (savedLoginEmails().length) openLoginEmailMenu(els.loginEmail.value);
  });
  els.loginEmail?.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeLoginEmailMenu();
    if (event.key === 'ArrowDown' && savedLoginEmails().length) {
      event.preventDefault();
      openLoginEmailMenu(els.loginEmail.value);
      document.querySelector('#login-email-menu .login-email-menu__item')?.focus();
    }
  });
  document.getElementById('login-email-toggle')?.addEventListener('mousedown', (event) => {
    event.preventDefault();
    const menu = document.getElementById('login-email-menu');
    if (menu && !menu.hidden) closeLoginEmailMenu();
    else openLoginEmailMenu('');
  });
  document.getElementById('login-email-menu')?.addEventListener('mousedown', (event) => {
    const btn = event.target.closest('[data-email]');
    if (!btn) return;
    event.preventDefault();
    selectSavedLoginEmail(btn.dataset.email);
  });
  document.addEventListener('click', (event) => {
    if (event.target.closest?.('.login-email-wrap')) return;
    closeLoginEmailMenu();
  });
  els.loginRemember?.addEventListener('change', () => {
    const email = normalizeEmail(els.loginEmail?.value || '');
    if (!els.loginRemember.checked && email) {
      forgetPasswordForUser(email);
      refreshLoginEmailSuggestions();
    }
  });

  els.registerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFieldErrors(els.registerForm);
    const notFound = els.regEmpresa?.value === '__not_found__';
    const payload = {
      usuario_login: normalizeEmail(els.regEmail.value),
      password: els.regPassword.value,
      NAME_USER: els.regName.value.trim(),
      LAST_NAME_USER: els.regLastName.value.trim(),
      ROLL: els.regRoll.value,
      empresa_no_encontrada: notFound,
      empresa_id: notFound ? null : Number(els.regEmpresa.value),
      empresa_sugerida: notFound ? (registerEmpresaCargada?.nombre || '') : '',
      nit_sugerido: notFound ? (registerEmpresaCargada?.nit || '') : '',
    };

    if (!payload.ROLL) {
      showToast('Selecciona el rol (Operador o Asistencial).', 'error');
      return;
    }
    if (!notFound && !payload.empresa_id) {
      setFieldError(els.regEmpresa, 'Selecciona una empresa.');
      showToast('Debes elegir la empresa o «No se encuentra».', 'error');
      return;
    }
    if (notFound && !registerEmpresaCargada) {
      showToast('Ingresa Nombre y NIT y pulsa Cargar para enviar la solicitud.', 'error');
      return;
    }
    if (!isValidEmail(payload.usuario_login) || !validatePassword(payload.password).valid) {
      showToast('Revisa correo y contraseña.', 'error');
      return;
    }
    if (!isLettersOnly(payload.NAME_USER) || !isLettersOnly(payload.LAST_NAME_USER)) {
      showToast('Nombres solo con letras.', 'error');
      return;
    }
    if (!els.regAviso?.checked) {
      showToast('Debe autorizar el tratamiento de sus datos personales.', 'error');
      return;
    }
    payload.aviso_aceptado = true;
    const { response, data } = await api('/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo registrar.', 'error');
      return;
    }
    showToast(data.message, 'success');
    closeModal();
    els.loginEmail.value = payload.usuario_login;
  });

  els.forgotForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFieldErrors(els.forgotForm);
    const email = normalizeEmail(els.forgotEmail?.value || '');
    if (!isValidEmail(email)) {
      setFieldError(els.forgotEmail, 'Indica un correo válido.');
      showToast('Indica un correo válido.', 'error');
      return;
    }
    const { response, data } = await api('/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ usuario_login: email }),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo enviar el correo.', 'error');
      return;
    }
    showToast(data.message, 'success');
    closeForgotModal();
  });

  els.resetForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearFieldErrors(els.resetForm);
    const token = els.resetToken?.value || '';
    const password = els.resetPassword?.value || '';
    const password2 = els.resetPassword2?.value || '';
    if (!validatePassword(password).valid) {
      setFieldError(els.resetPassword, 'Mínimo 8 caracteres.');
      showToast('Revisa la nueva contraseña.', 'error');
      return;
    }
    if (password !== password2) {
      setFieldError(els.resetPassword2, 'Las contraseñas no coinciden.');
      showToast('Las contraseñas no coinciden.', 'error');
      return;
    }
    const { response, data } = await api('/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, password }),
    });
    if (!response.ok || !data.ok) {
      showToast(data.error || 'No se pudo restablecer la contraseña.', 'error');
      return;
    }
    showToast(data.message, 'success');
    closeResetModal();
  });

  /* Arranque: catálogo de roles, restauración de sesión y exportación AtlasOps. */
  async function loadRoles() {
    const { response, data } = await api('/roles');
    if (response.ok && data.ok) fillRoles(data);
  }

  function canPickAnyEmpresa() {
    const user = currentUser || {};
    return (
      String(user.ROLL || '').toUpperCase() === 'ADMIN' ||
      Boolean(can('admin_panel')) ||
      Boolean(can('view_all_empresas'))
    );
  }

  function exclusiveAccordion(root, toggle) {
    if (!root || !toggle) return;
    const acc = toggle.closest('.dim-acc');
    if (!acc || !root.contains(acc)) return;
    const siblings = [...acc.parentElement.children].filter((el) => el.classList.contains('dim-acc'));
    const body = [...acc.children].find((el) => el.classList.contains('dim-acc__body'));
    const opening = Boolean(body?.hidden);
    siblings.forEach((section) => {
      const topBody = [...section.children].find((el) => el.classList.contains('dim-acc__body'));
      const isTarget = opening && section === acc;
      if (topBody) topBody.hidden = !isTarget;
      section.classList.toggle('is-open', isTarget);
      section
        .querySelector(':scope > .dim-acc__head > .dim-acc__toggle')
        ?.setAttribute('aria-expanded', isTarget ? 'true' : 'false');
    });
  }

  function collapseAccordion(section) {
    if (!section) return;
    const body = [...section.children].find((el) => el.classList.contains('dim-acc__body'));
    if (body) body.hidden = true;
    section.classList.remove('is-open');
    section.querySelector('.dim-acc__toggle')?.setAttribute('aria-expanded', 'false');
  }

  function bindTips({ panelId, bubbleId, selector, getContent, maxWidth = 320 }) {
    const panel = document.getElementById(panelId);
    const bubble = document.getElementById(bubbleId);
    if (!panel || !bubble || bubble.dataset.tipsBound === '1') return;
    bubble.dataset.tipsBound = '1';
    if (bubble.parentElement !== document.body) document.body.appendChild(bubble);

    let pinnedBtn = null;

    function placeBubble(btn) {
      const rect = btn.getBoundingClientRect();
      const pad = 8;
      const width = Math.min(maxWidth, window.innerWidth - 24);
      bubble.style.width = `${width}px`;
      bubble.style.maxWidth = `${width}px`;
      const height = bubble.offsetHeight || 120;
      let left = rect.right + pad;
      let top = rect.top;
      if (left + width > window.innerWidth - pad) {
        left = rect.left - width - pad;
      }
      if (left < pad) left = pad;
      if (top + height > window.innerHeight - pad) {
        top = Math.max(pad, window.innerHeight - height - pad);
      }
      if (top < pad) top = pad;
      bubble.style.position = 'fixed';
      bubble.style.zIndex = '10000';
      bubble.style.top = `${top}px`;
      bubble.style.left = `${left}px`;
    }

    function hideBubble() {
      pinnedBtn = null;
      bubble.hidden = true;
      bubble.classList.remove('tip-bubble--open', 'tip-bubble--rich');
      bubble.textContent = '';
    }

    function showFromBtn(btn, { pin = false } = {}) {
      const content = getContent ? getContent(btn) : '';
      if (!content) return;
      if (typeof content === 'object' && content.html) {
        bubble.classList.add('tip-bubble--rich');
        bubble.innerHTML = content.html;
      } else {
        bubble.classList.remove('tip-bubble--rich');
        bubble.textContent = String(content);
      }
      bubble.hidden = false;
      bubble.classList.add('tip-bubble--open');
      placeBubble(btn);
      requestAnimationFrame(() => placeBubble(btn));
      if (pin) pinnedBtn = btn;
    }

    function pointerStillOnTip(related) {
      if (!related) return false;
      if (pinnedBtn && (pinnedBtn === related || pinnedBtn.contains(related))) return true;
      if (bubble.contains(related)) return true;
      const btn = related.closest?.(selector);
      return Boolean(btn && panel.contains(btn));
    }

    document.addEventListener(
      'click',
      (event) => {
        const btn = event.target.closest?.(selector);
        if (btn && panel.contains(btn)) {
          event.preventDefault();
          event.stopPropagation();
          if (pinnedBtn === btn && !bubble.hidden) {
            hideBubble();
            return;
          }
          showFromBtn(btn, { pin: true });
          return;
        }
        if (!bubble.hidden && !bubble.contains(event.target)) hideBubble();
      },
      true
    );

    panel.addEventListener('mouseover', (event) => {
      const btn = event.target.closest(selector);
      if (!btn || !panel.contains(btn)) return;
      showFromBtn(btn, { pin: Boolean(pinnedBtn === btn) });
    });
    panel.addEventListener('mouseout', (event) => {
      if (pointerStillOnTip(event.relatedTarget)) return;
      hideBubble();
    });
    bubble.addEventListener('mouseleave', (event) => {
      if (pointerStillOnTip(event.relatedTarget)) return;
      hideBubble();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') hideBubble();
    });
    window.addEventListener(
      'scroll',
      () => {
        if (!bubble.hidden) hideBubble();
      },
      true
    );
    window.addEventListener('resize', () => {
      if (pinnedBtn && !bubble.hidden) placeBubble(pinnedBtn);
    });
  }

  const MAX_DURACION_EJECUCION_H = 720;

  function duracionHorasDesdeFechas(atencion, cierre) {
    if (!atencion || !cierre) return null;
    const start = new Date(atencion);
    const end = new Date(cierre);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
    const hours = (end.getTime() - start.getTime()) / 3600000;
    if (hours <= 0 || hours > MAX_DURACION_EJECUCION_H) return null;
    return Math.round(hours * 100) / 100;
  }

  function bindDuracionDesdeFechas(atencionId, cierreId, duracionId) {
    const sync = () => {
      const dur = document.getElementById(duracionId);
      if (!dur) return;
      const hours = duracionHorasDesdeFechas(
        document.getElementById(atencionId)?.value,
        document.getElementById(cierreId)?.value
      );
      dur.value = hours == null ? '' : String(hours);
    };
    document.getElementById(atencionId)?.addEventListener('change', sync);
    document.getElementById(cierreId)?.addEventListener('change', sync);
    document.getElementById(atencionId)?.addEventListener('input', sync);
    document.getElementById(cierreId)?.addEventListener('input', sync);
  }

  const EQ_ALERTA_MSG =
    'Este equipo no cuenta con datos de mantenimiento, visitas u otros registrados para el año actual.';

  function equipoAlertaMarkup(eq) {
    if (!eq || !eq.alerta_sin_datos_anio) return '';
    const msg = String(eq.alerta_mensaje || EQ_ALERTA_MSG);
    const safe = escapeHtml(msg);
    return `<span class="eq-alerta" role="button" tabindex="0" data-eq-alerta data-eq-alerta-msg="${safe}" title="${safe}" aria-label="${safe}">!</span>`;
  }

  function bindEquipoAlertaClicks() {
    if (document.documentElement.dataset.eqAlertaBound) return;
    document.documentElement.dataset.eqAlertaBound = '1';
    const fire = (el) => {
      showToast(el.getAttribute('data-eq-alerta-msg') || EQ_ALERTA_MSG, 'warn');
    };
    document.addEventListener(
      'click',
      (event) => {
        const el = event.target.closest('[data-eq-alerta]');
        if (!el) return;
        event.preventDefault();
        event.stopPropagation();
        fire(el);
      },
      true
    );
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        const el = event.target.closest?.('[data-eq-alerta]');
        if (!el) return;
        event.preventDefault();
        event.stopPropagation();
        fire(el);
      },
      true
    );
  }

  window.AtlasOps = Object.assign(window.AtlasOps || {}, {
    api,
    showToast,
    ensureSedes,
    fillSedeSelect,
    fillServicioSelect,
    downloadFile,
    can,
    canPickAnyEmpresa,
    openModule,
    exclusiveAccordion,
    collapseAccordion,
    bindTips,
    duracionHorasDesdeFechas,
    bindDuracionDesdeFechas,
    equipoAlertaMarkup,
    EQ_ALERTA_MSG,
    getSedesCache() {
      return sedesCache;
    },
    get currentUser() {
      return currentUser;
    },
  });

  try {
    localStorage.removeItem('sigtb_saved_logins');
    localStorage.removeItem('sigtb_last_login');
  } catch {
    /* ignore */
  }
  bindEquipoAlertaClicks();
  loadRoles();
  restoreSessionFromCache();

  // Tablas con overflow-x (suficiencia, PM, SITIO) tragan la rueda/gesto
  // vertical y no lo pasan al panel. Encadenar a .ops-main.
  document.addEventListener(
    'wheel',
    (event) => {
      if (event.ctrlKey || event.defaultPrevented) return;
      const main = document.querySelector('.ops-main');
      const dash = document.getElementById('dashboard');
      if (!main || !dash || dash.hidden || !main.contains(event.target)) return;

      let node = event.target instanceof Element ? event.target : null;
      while (node && node !== main) {
        if (node instanceof HTMLElement) {
          const style = window.getComputedStyle(node);
          const yLock = style.overflowY;
          const xLock = style.overflowX;
          const canY =
            (yLock === 'auto' || yLock === 'scroll') &&
            node.scrollHeight - node.clientHeight > 1;
          const canX =
            (xLock === 'auto' || xLock === 'scroll') &&
            node.scrollWidth - node.clientWidth > 1;
          if (canY) {
            const atTop = node.scrollTop <= 0 && event.deltaY < 0;
            const atBottom =
              node.scrollTop + node.clientHeight >= node.scrollHeight - 1 &&
              event.deltaY > 0;
            if (!atTop && !atBottom) return;
          } else if (canX && Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
            return;
          }
        }
        node = node.parentElement;
      }

      if (Math.abs(event.deltaY) < 1) return;
      const before = main.scrollTop;
      main.scrollTop += event.deltaY;
      if (main.scrollTop !== before) event.preventDefault();
    },
    { passive: false, capture: true }
  );
})();
