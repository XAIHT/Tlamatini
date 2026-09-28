/* Tlamatini — Created by Angela López Mendoza · @angelahack1
 * Tlamatini Author Banner — do not remove
 * Direct Whisperer dictation; the existing chat form owns prompt submission.
 */
(function () {
  'use strict';
  const button = document.getElementById('chat-microphone');
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-message-input');
  const send = document.getElementById('chat-message-submit');
  const panel = document.getElementById('dictation-status');
  if (!button || !form || !input || !send || !panel) return;
  const label = document.getElementById('dictation-label');
  const detail = document.getElementById('dictation-detail');
  const meter = document.getElementById('dictation-meter');
  const clock = document.getElementById('dictation-clock');
  const buttonLabel = button.querySelector('.mic-label');
  let socket = null, ready = false, runId = null, cancelled = false;
  let state = 'preparing', clickedAt = 0, firstSample = false, startWhenReady = false;
  let previousReadOnly = false, previousDisabled = false;
  let activePreferences = {mode: 'send', capture: {}};

  function chatAvailable() {
    return isChatSocketOpen() && !inLongOperation && !lapseLoadingContext
      && !input.disabled && !/cancel|stop|disconnected/i.test(send.textContent);
  }
  function paint(next, message) {
    state = next;
    button.dataset.state = next;
    panel.dataset.state = next;
    panel.hidden = next === 'ready';
    if (message) label.textContent = message;
    buttonLabel.textContent = next === 'recording' ? 'Listening' :
      (next === 'transcribing' ? 'To text' : (runId ? 'Cancel' : 'Mic'));
    button.setAttribute('aria-pressed', runId ? 'true' : 'false');
    const mode = runId ? activePreferences.mode : (window.TLM_MIC?.snapshot().mode || 'send');
    button.setAttribute('aria-label', runId ? 'Cancel dictation' :
      (mode === 'draft' ? 'Dictate into the chat input' : 'Dictate and send a prompt'));
    button.title = runId ? 'Cancel dictation · Escape' :
      'Use the microphone on the Tlamatini computer. Stops on silence; ' +
      (mode === 'draft' ? 'keeps the text in your draft for review.' : 'sends automatically.');
    button.disabled = !runId && (!chatAvailable() || (next === 'preparing' && !ready));
  }
  function release() {
    window.TLM_VOICE?.setListening(false);
    // Restore our edit lock even if the chat disconnected during capture.
    // The chat transport still owns input.disabled and its busy Send state.
    input.readOnly = previousReadOnly;
    if (chatAvailable()) send.disabled = previousDisabled;
    meter.style.setProperty('--voice-level', '0');
    button.style.setProperty('--voice-level', '0');
    button.style.setProperty('--silence-turn', '0deg');
    detail.textContent = '';
    clock.textContent = '';
  }
  function finish(next, message) {
    runId = null;
    release();
    paint(next, message);
  }
  function transmit(message) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    try { socket.send(JSON.stringify(message)); return true; }
    catch (error) { return false; }
  }
  function cancel() {
    if (!runId || cancelled) return;
    cancelled = true;
    window.TLM_VOICE?.setListening(false);
    transmit({action: 'cancel', run_id: runId});
    paint('cancelling', 'Cancelling voice prompt…');
    detail.textContent = 'The transcript will not be added or sent.';
  }
  function start() {
    if (runId || !chatAvailable() || input.readOnly || send.disabled) return;
    if (!ready) {
      startWhenReady = true;
      connect();
      return;
    }
    const bytes = new Uint32Array(3);
    window.crypto.getRandomValues(bytes);
    runId = Array.from(bytes, n => n.toString(16)).join('-');
    cancelled = false;
    activePreferences = window.TLM_MIC?.snapshot() || {mode: 'send', capture: {}};
    firstSample = false;
    clickedAt = performance.now();
    previousReadOnly = input.readOnly;
    previousDisabled = send.disabled;
    input.readOnly = true;
    send.disabled = true;
    window.TLM_VOICE?.prime();
    window.TLM_VOICE?.setListening(true);
    paint('starting', 'Opening microphone…');
    detail.textContent = 'Speak when Listening appears. ' + (activePreferences.mode === 'draft'
      ? 'Your words will stay in the chat input for review.' : 'Your prompt sends automatically.');
    if (!transmit({action: 'start', run_id: runId, settings: activePreferences.capture})) {
      finish('error', 'Voice connection lost. Click the microphone to retry.');
      ready = false;
    }
  }
  function submitTranscript(data) {
    if (cancelled) { finish('ready'); return; }
    const text = typeof data.text === 'string' ? data.text.trim() : '';
    if (!text) { finish('empty', 'No words recognized. Your draft is unchanged.'); return; }
    // Clear ownership before a synchronous normal-form submission. Late/duplicate
    // frames no longer match, even if a new recording is started immediately.
    runId = null;
    release();
    const original = input.value;
    input.value = original + (original && !/\s$/.test(original) ? '\n' : '') + text;
    input.dispatchEvent(new Event('input', {bubbles: true}));
    if (activePreferences.mode === 'draft') {
      paint('draft', 'Transcription ready — review your prompt');
      detail.textContent = 'Edit the text, then press Send when you are ready.';
      if (!window.TLM_MIC?.isOpen()) {
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
      }
      document.dispatchEvent(new CustomEvent('tlm-dictation-timing', {detail: data.timings || {}}));
      return;
    }
    if (!chatAvailable() || input.readOnly || send.disabled) {
      paint('error', 'Your voice prompt is in the draft. Send it when chat is ready.');
      return;
    }
    paint('submitting', 'Sending your voice prompt…');
    form.dataset.voiceSubmitting = 'true';
    try {
      form.requestSubmit(send);
      if (input.value === '') {
        paint('ready');
        document.dispatchEvent(new CustomEvent('tlm-dictation-timing', {detail: data.timings || {}}));
      } else {
        paint('error', 'Your voice prompt is saved in the draft. Reconnect, then send it.');
      }
    } finally {
      delete form.dataset.voiceSubmitting;
    }
  }
  function onMessage(data) {
    if (data.event === 'ready' || data.event === 'options') window.TLM_MIC?.applyMetadata(data);
    if (data.event === 'options') return;
    if (data.event === 'ready') {
      ready = true;
      if (!runId) paint('ready');
      if (startWhenReady) { startWhenReady = false; start(); }
      return;
    }
    if (data.event === 'preparing') return;
    if (!data.run_id) {
      if (data.event === 'error' && !runId) {
        ready = false;
        startWhenReady = false;
        paint('error', data.message || 'Whisperer is unavailable. Click to retry.');
      }
      return;
    }
    if (data.run_id !== runId) return;
    if (data.event === 'rejected') {
      finish('error', data.message || 'Mic settings were rejected. Open Config → Mic to correct them.');
      return;
    }
    if (cancelled && !['cancelled', 'error', 'empty', 'result'].includes(data.event)) return;
    switch (data.event) {
      case 'recording': {
        if (!firstSample) {
          firstSample = true;
          button.dataset.captureStartMs = String(Math.round(performance.now() - clickedAt));
          paint('recording', 'Listening');
        }
        const level = Math.max(0, Math.min(1, Number(data.level) || 0));
        const elapsed = Math.max(0, Number(data.elapsed) || 0);
        const silence = Math.max(0, Number(data.silence) || 0);
        const timeout = Math.max(0, Number(data.silence_timeout) || 0);
        meter.style.setProperty('--voice-level', String(Math.sqrt(level)));
        button.style.setProperty('--voice-level', String(Math.sqrt(level)));
        button.style.setProperty('--silence-turn', (timeout ? Math.min(360, silence / timeout * 360) : 0) + 'deg');
        clock.textContent = Math.floor(elapsed / 60) + ':' + String(Math.floor(elapsed % 60)).padStart(2, '0');
        detail.textContent = silence > 0.2 && timeout
          ? 'Recording ends after ' + Math.max(0, timeout - silence).toFixed(1) + 's of silence'
          : 'Speak naturally · click again or press Esc to cancel';
        break;
      }
      case 'transcribing':
        window.TLM_VOICE?.setListening(false);
        paint('transcribing', 'Turning your voice into a prompt…');
        detail.textContent = activePreferences.mode === 'draft'
          ? 'Recording finished. The words will appear in your draft for review.'
          : 'Recording finished. Sending automatically when the words are ready.';
        break;
      case 'result': submitTranscript(data); break;
      case 'empty': finish('empty', data.message || 'No speech detected. Try again.'); break;
      case 'cancelled': finish('ready'); break;
      case 'error': finish('error', data.message || 'Dictation failed. Your draft is unchanged.'); break;
      default: break;
    }
  }
  function connect() {
    if (socket && socket.readyState <= WebSocket.OPEN) {
      if (ready) return;
      socket.close();
    }
    ready = false;
    paint('preparing', 'Preparing voice input…');
    detail.textContent = 'The microphone is off.';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const current = new WebSocket(protocol + '//' + window.location.host + '/ws/chat-voice/');
    socket = current;
    current.onmessage = event => {
      if (socket !== current) return;
      try { onMessage(JSON.parse(event.data)); }
      catch (error) { cancel(); finish('error', 'Invalid voice response. Please retry.'); }
    };
    current.onclose = () => {
      if (socket !== current) return;
      ready = false;
      startWhenReady = false;
      cancelled = true;
      if (runId) finish('error', 'Voice connection lost. Your draft is unchanged.');
      else paint('error', 'Voice is disconnected. Click the microphone to reconnect.');
    };
    current.onerror = () => { if (socket === current) current.close(); };
  }

  button.addEventListener('click', () => runId ? cancel() : start());
  document.addEventListener('keydown', event => {
    if (event.defaultPrevented || window.TLM_MIC?.isOpen()) return;
    if (event.key === 'Escape' && runId) { event.preventDefault(); cancel(); }
  });
  // Covers Enter, requestSubmit and legacy dispatchEvent('submit') callers.
  form.addEventListener('submit', event => {
    if (runId) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  chatSocket.addEventListener('close', () => {
    if (runId) cancel();
    paint(state);
  });
  chatSocket.addEventListener('open', () => paint(state));
  new MutationObserver(() => {
    if (runId && !chatAvailable()) cancel();
    paint(state);
  }).observe(send, {attributes: true, childList: true, characterData: true, subtree: true});
  window.addEventListener('pagehide', () => { cancel(); socket?.close(); });
  document.addEventListener('tlm-mic-settings-changed', () => paint(state));
  window.TLM_DICTATION = {isActive: () => !!runId, cancel,
    refreshSettings: () => !runId && ready && transmit({action: 'options'})};
  connect();
}());
