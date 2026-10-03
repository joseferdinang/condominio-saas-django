(() => {
  const form = document.querySelector('[data-login-form]');
  if (!form) return;
  const toggle = form.querySelector('[data-password-toggle]');
  const password = document.getElementById(toggle?.getAttribute('aria-controls'));
  if (toggle && password) {
    toggle.hidden = false;
    toggle.addEventListener('click', () => {
      const visible = password.type === 'password';
      password.type = visible ? 'text' : 'password';
      toggle.setAttribute('aria-pressed', String(visible));
      toggle.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
    });
  }
  const submit = form.querySelector('[type="submit"]');
  const label = form.querySelector('[data-submit-label]');
  form.addEventListener('submit', () => {
    form.setAttribute('aria-busy', 'true');
    submit.disabled = true;
    label.textContent = 'Entrando…';
  });
  window.addEventListener('pageshow', () => {
    form.removeAttribute('aria-busy');
    submit.disabled = false;
    label.textContent = 'Entrar a mi comunidad';
    if (password) password.type = 'password';
    if (toggle) {
      toggle.setAttribute('aria-pressed', 'false');
      toggle.setAttribute('aria-label', 'Mostrar contraseña');
    }
  });
})();
