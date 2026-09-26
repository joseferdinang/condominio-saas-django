(function () {
  'use strict';

  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie) {
      document.cookie.split(';').some(function (cookie) {
        cookie = cookie.trim();
        if (cookie.substring(0, name.length + 1) === name + '=') {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          return true;
        }
        return false;
      });
    }
    return cookieValue;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var root = document.documentElement;
    var control = document.querySelector('.appearance-control');
    if (!control) return;

    var panel = document.getElementById('appearance-panel');
    var panelToggle = control.querySelector('.palette-toggle');
    var themeToggle = control.querySelector('[data-theme-toggle]');
    var themeLabel = control.querySelector('.theme-toggle-label');
    var status = control.querySelector('.appearance-status');
    var paletteButtons = Array.prototype.slice.call(
      control.querySelectorAll('[data-palette]')
    );
    var saveUrl = control.dataset.preferencesUrl;
    var saveTimer;

    function setStatus(message, isError) {
      if (!status) return;
      status.textContent = message;
      status.classList.toggle('is-error', Boolean(isError));
      window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(function () {
        status.textContent = '';
        status.classList.remove('is-error');
      }, 2400);
    }

    function updateThemeControls() {
      var dark = root.dataset.theme === 'oscuro';
      themeToggle.setAttribute('aria-pressed', dark ? 'true' : 'false');
      themeToggle.setAttribute(
        'aria-label',
        dark ? 'Activar modo claro' : 'Activar modo oscuro'
      );
      themeLabel.textContent = dark ? 'Modo claro' : 'Modo oscuro';
      var themeColor = getComputedStyle(root).getPropertyValue('--brand-dark').trim();
      var metaTheme = document.querySelector('meta[name="theme-color"]');
      if (metaTheme && themeColor) metaTheme.setAttribute('content', themeColor);
    }

    function updatePaletteControls() {
      paletteButtons.forEach(function (button) {
        button.setAttribute(
          'aria-pressed',
          button.dataset.palette === root.dataset.palette ? 'true' : 'false'
        );
      });
    }

    function savePreferences() {
      var body = new URLSearchParams({
        tema: root.dataset.theme,
        paleta: root.dataset.palette
      });
      fetch(saveUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
          'X-CSRFToken': getCookie('csrftoken') || '',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: body.toString()
      }).then(function (response) {
        if (!response.ok) throw new Error('No se pudo guardar');
        return response.json();
      }).then(function () {
        setStatus('Preferencia guardada');
      }).catch(function () {
        setStatus('No se pudo guardar el cambio', true);
      });
    }

    function closePanel() {
      panel.classList.remove('is-open');
      panel.setAttribute('aria-hidden', 'true');
      panelToggle.setAttribute('aria-expanded', 'false');
    }

    themeToggle.addEventListener('click', function () {
      root.dataset.theme = root.dataset.theme === 'oscuro' ? 'claro' : 'oscuro';
      updateThemeControls();
      savePreferences();
    });

    panelToggle.addEventListener('click', function () {
      var willOpen = !panel.classList.contains('is-open');
      panel.classList.toggle('is-open', willOpen);
      panel.setAttribute('aria-hidden', willOpen ? 'false' : 'true');
      panelToggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
    });

    paletteButtons.forEach(function (button) {
      button.addEventListener('click', function () {
        root.dataset.palette = button.dataset.palette;
        updatePaletteControls();
        updateThemeControls();
        savePreferences();
      });
    });

    document.addEventListener('click', function (event) {
      if (!control.contains(event.target)) closePanel();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closePanel();
    });

    updateThemeControls();
    updatePaletteControls();
  });
})();
