/* Tlamatini — Created by Angela López Mendoza · @angelahack1
 * Tlamatini Author Banner — do not remove
 * Browser preferences for direct dictation; microphone access stays in Whisperer.
 */
(function () {
  'use strict';
  const overlay = document.getElementById('tlm-mic-overlay');
  const form = document.getElementById('tlm-mic-form');
  if (!overlay || !form) return;
  const KEY = 'tlm_mic_settings_v1';
  const FALLBACK = {input_gain_percent: 100, silence_timeout_seconds: 3.5,
    max_record_seconds: 300, silence_threshold_db: 0, sample_rate: 0,
    channels: 1, language: '', task: 'transcribe', beam_size: 5, vad_filter: true};
  const fields = Array.from(form.querySelectorAll('[data-mic-setting]'));
  const device = document.getElementById('tlm-mic-device');
  const refresh = document.getElementById('tlm-mic-refresh');
  const feedback = document.getElementById('tlm-mic-feedback');
  const sensitivity = document.getElementById('tlm-mic-sensitivity');
  const threshold = document.getElementById('tlm-mic-threshold');
  let defaults = {...FALLBACK}, devices = [], refreshTimer = null;
  let editorDefaults = {...FALLBACK}, dirty = false, editingPreferences = null;
  let saved = {mode: 'send', capture: {}};
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '{}');
    saved = {mode: raw?.mode === 'draft' ? 'draft' : 'send',
      capture: raw?.capture && typeof raw.capture === 'object' && !Array.isArray(raw.capture) ? raw.capture : {}};
  } catch (error) { /* Missing/corrupt storage uses the original automatic behavior. */ }

  function snapshot() {
    // A recording owns its preference snapshot, even when another tab saves.
    return {mode: saved.mode, capture: JSON.parse(JSON.stringify(saved.capture))};
  }
  function notice(text) {
    feedback.textContent = text;
    feedback.hidden = !text;
  }
  function isOpen() { return overlay.style.display !== 'none'; }
  function close() {
    overlay.style.display = 'none';
    document.getElementById('config-menu-button')?.focus();
  }
  function updateSensitivity() {
    const manual = sensitivity.value === 'manual';
    document.getElementById('tlm-mic-threshold-row').hidden = !manual;
    threshold.disabled = !manual;
  }
  function deviceKey(value) {
    return JSON.stringify([value.device_index ?? value.index, value.device_name ?? value.name,
      value.device_hostapi ?? value.hostapi]);
  }
  function renderDevices(selected) {
    const desired = selected || device.value || 'inherit';
    device.replaceChildren(new Option('Use configured Whisperer microphone', 'inherit'),
      new Option('System default input', 'default'));
    devices.forEach(item => {
      device.add(new Option(item.name + ' · ' + item.hostapi, deviceKey(item)));
    });
    if (!Array.from(device.options).some(option => option.value === desired)) {
      // Preserve a removed/saved input, never silently choose a different microphone.
      device.add(new Option('Saved input unavailable — refresh or choose another', desired));
    }
    device.value = desired;
  }
  function populate(preferences) {
    editingPreferences = preferences;
    editorDefaults = {...defaults};
    dirty = false;
    const values = {...defaults, ...preferences.capture};
    form.querySelector('input[name="tlm-mic-mode"][value="' + preferences.mode + '"]').checked = true;
    fields.forEach(field => {
      const value = values[field.dataset.micSetting];
      if (field.type === 'checkbox') field.checked = value === true;
      else field.value = String(value ?? '');
    });
    document.getElementById('tlm-mic-gain-value').textContent = values.input_gain_percent + '%';
    sensitivity.value = values.silence_threshold_db === 0 ? 'auto' : 'manual';
    threshold.value = values.silence_threshold_db || -50;
    updateSensitivity();
    const capture = preferences.capture;
    renderDevices(capture.device_index >= 0 ? deviceKey(capture) :
      (capture.device_index === -1 ? 'default' : 'inherit'));
  }
  function applyMetadata(data) {
    if (data.defaults && typeof data.defaults === 'object') defaults = {...FALLBACK, ...data.defaults};
    if (Array.isArray(data.devices)) {
      devices = data.devices.filter(item => Number.isInteger(item.index) && item.index >= 0 &&
        typeof item.name === 'string' && typeof item.hostapi === 'string');
    }
    clearTimeout(refreshTimer);
    refresh.disabled = false;
    document.getElementById('tlm-mic-device-note').textContent = data.devices_error
      ? 'Input discovery is unavailable. The configured or system default microphone can still be used.'
      : devices.length + ' host input device' + (devices.length === 1 ? '' : 's') + ' available.';
    // Do not replace an unsaved edit when an asynchronous refresh arrives.
    if (isOpen() && !dirty && editingPreferences) populate(editingPreferences);
    else renderDevices();
  }
  function refreshInputs() {
    if (window.TLM_DICTATION?.isActive()) {
      notice('Finish or cancel the current recording before refreshing inputs.');
      return;
    }
    if (!window.TLM_DICTATION?.refreshSettings()) {
      notice('Microphone settings are reconnecting. Try Refresh inputs when the connection is ready.');
      return;
    }
    refresh.disabled = true;
    notice('');
    refreshTimer = setTimeout(() => {
      refresh.disabled = false;
      notice('Input refresh timed out. Try again or keep the configured microphone.');
    }, 6500);
  }
  function open(event) {
    event?.preventDefault();
    if (inLongOperation || lapseLoadingContext) return;
    notice('');
    populate(saved);
    overlay.style.display = 'flex';
    requestAnimationFrame(() => form.querySelector('input[name="tlm-mic-mode"]:checked').focus());
    refreshInputs();
  }
  function collect() {
    const capture = {};
    fields.forEach(field => {
      const key = field.dataset.micSetting;
      const value = field.type === 'checkbox' ? field.checked :
        (key === 'language' ? field.value.trim().toLowerCase() :
          (key === 'task' ? field.value : Number(field.value)));
      if (value !== editorDefaults[key]) capture[key] = value;
    });
    const thresholdValue = sensitivity.value === 'manual' ? Number(threshold.value) : 0;
    if (thresholdValue !== editorDefaults.silence_threshold_db) capture.silence_threshold_db = thresholdValue;
    if (device.value === 'default') {
      capture.device_index = -1;
      capture.device_name = '';
    } else if (device.value !== 'inherit') {
      const [index, name, hostapi] = JSON.parse(device.value);
      capture.device_index = index;
      capture.device_name = name;
      capture.device_hostapi = hostapi;
    }
    return {mode: form.querySelector('input[name="tlm-mic-mode"]:checked').value, capture};
  }
  form.addEventListener('input', () => { dirty = true; });
  form.addEventListener('change', () => { dirty = true; });
  form.addEventListener('submit', event => {
    event.preventDefault();
    // Expand advanced fields before showing native validation messages.
    if (!form.checkValidity()) {
      form.querySelector('details').open = true;
      form.reportValidity();
      return;
    }
    saved = collect();
    document.dispatchEvent(new CustomEvent('tlm-mic-settings-changed'));
    try {
      localStorage.setItem(KEY, JSON.stringify(saved));
      close();
    } catch (error) {
      notice('Applied for this tab. Browser storage is unavailable, so these settings may not survive a reload.');
    }
  });
  form.addEventListener('invalid', () => { form.querySelector('details').open = true; }, true);
  form.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const targets = Array.from(form.querySelectorAll('button,input,select,summary'))
      .filter(element => !element.disabled && element.getClientRects().length);
    const first = targets[0], last = targets.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  document.getElementById('tlm-mic-close').addEventListener('click', close);
  document.getElementById('tlm-mic-cancel').addEventListener('click', close);
  // Shared modal policy: outside clicks never discard an unsaved configuration.
  document.getElementById('tlm-mic-reset').addEventListener('click', () => {
    populate({mode: 'send', capture: {}});
    notice('Whisperer defaults restored in this dialog. Save to apply.');
  });
  document.getElementById('tlm-mic-gain').addEventListener('input', event => {
    document.getElementById('tlm-mic-gain-value').textContent = event.target.value + '%';
  });
  sensitivity.addEventListener('change', updateSensitivity);
  refresh.addEventListener('click', refreshInputs);
  window.addEventListener('storage', event => {
    if (event.key !== KEY) return;
    try {
      const value = JSON.parse(event.newValue || '{}');
      saved = {mode: value.mode === 'draft' ? 'draft' : 'send',
        capture: value.capture && typeof value.capture === 'object' && !Array.isArray(value.capture) ? value.capture : {}};
      document.dispatchEvent(new CustomEvent('tlm-mic-settings-changed'));
      if (isOpen()) notice('Mic preferences changed in another tab. Close and reopen to load them, or Save your edits.');
    } catch (error) { /* Ignore malformed external storage updates. */ }
  });
  window.OpenMicDialog = open;
  window.TLM_MIC = {snapshot, applyMetadata, isOpen};
}());
