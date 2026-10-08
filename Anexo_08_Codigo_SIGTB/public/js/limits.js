/** Límites OWASP de entrada. Mantener alineado con server/limits.py */
window.SIGTB_LIMITS = {
  email: 254,
  name: 80,
  phone: 40,
  passwordMin: 8,
  passwordMax: 128,
  subject: 120,
  message: 2000,
  description: 2000,
  solution: 1000,
  comment: 500,
  longText: 4000,
  label: 255,
  code: 100,
  nit: 50,
  queryLimit: 500,
};
