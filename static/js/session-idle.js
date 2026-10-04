(function () {
  'use strict';

  var config = document.querySelector('script[data-activity-url]');
  if (!config) return;
  var timeout = 300000;
  var deadline = Date.now() + Number(config.dataset.remaining);
  var closing = false;
  var lastSent = 0;
  var pending = false;
  var heartbeatTimer;
  var idleTimer;
  var channelName = 'condominio-activity-' + config.dataset.user;
  var channel = window.BroadcastChannel ? new BroadcastChannel(channelName) : null;

  function csrfToken() {
    var input = document.querySelector('[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function broadcast(message) {
    if (channel) channel.postMessage(message);
    else {
      try { localStorage.setItem(channelName, JSON.stringify(message)); }
      catch (error) { /* Server expiration still protects private browsing. */ }
    }
  }

  function receive(message) {
    if (!message || closing) return;
    if (message.type === 'logout') {
      closing = true;
      window.location.replace(config.dataset.loginUrl);
    } else if (message.type === 'activity' && message.at <= Date.now() + 1000) {
      deadline = Math.max(deadline, message.at + timeout);
      scheduleExpiration();
    }
  }
  if (channel) channel.onmessage = function (event) { receive(event.data); };
  else window.addEventListener('storage', function (event) {
    if (event.key !== channelName || !event.newValue) return;
    try { receive(JSON.parse(event.newValue)); } catch (error) { /* Ignore invalid data. */ }
  });

  async function expire() {
    if (closing) return;
    closing = true;
    window.clearTimeout(heartbeatTimer);
    try {
      await fetch(config.dataset.logoutUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrfToken() },
      });
    } catch (error) { /* The server independently expires the session. */ }
    broadcast({ type: 'logout', at: Date.now() });
    window.location.replace(config.dataset.loginUrl);
  }

  function scheduleExpiration() {
    window.clearTimeout(idleTimer);
    if (closing) return;
    var remaining = deadline - Date.now();
    if (remaining <= 0) { expire(); return; }
    idleTimer = window.setTimeout(scheduleExpiration, remaining);
  }

  async function heartbeat() {
    if (closing || !pending) return;
    pending = false;
    lastSent = Date.now();
    try {
      var response = await fetch(config.dataset.activityUrl, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrfToken(), 'Accept': 'application/json' },
      });
      if (response.status === 401) expire();
    } catch (error) { /* Connectivity failures cannot disable server expiration. */ }
  }

  function activity(event) {
    if (!event.isTrusted || closing || document.visibilityState === 'hidden') return;
    if (Date.now() >= deadline) { expire(); return; }
    deadline = Date.now() + timeout;
    broadcast({ type: 'activity', at: Date.now() });
    scheduleExpiration();
    pending = true;
    window.clearTimeout(heartbeatTimer);
    // Send only after real interaction, never an unconditional periodic ping.
    var wait = Math.max(0, 10000 - (Date.now() - lastSent));
    heartbeatTimer = window.setTimeout(heartbeat, wait);
  }

  ['pointerdown', 'pointermove', 'keydown', 'input', 'wheel', 'touchstart'].forEach(function (name) {
    document.addEventListener(name, activity, { passive: true });
  });
  document.addEventListener('visibilitychange', scheduleExpiration);
  window.addEventListener('pageshow', scheduleExpiration);
  // A forbidden HTMX swap must never leave the login form inside a private panel.
  document.addEventListener('htmx:beforeSwap', function (event) {
    var xhr = event.detail.xhr;
    if (xhr.responseURL && xhr.responseURL.includes('/cuentas/login/')) {
      event.detail.shouldSwap = false;
      expire();
    }
  });
  scheduleExpiration();
}());
