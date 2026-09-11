// Hold to talk. Feature 024, stage S3.
//
// The indicator is a measurement, not a claim: it is driven by the microphone's own
// signal, so it visibly fails when the mic is muted, the wrong input device is selected,
// or nobody is speaking. That failure is the whole diagnostic value. A timer-driven
// pulse keeps going confidently at a dead microphone, which in a lab whose founding rule
// is that nothing grades itself is the same category of error as a fake pass rate.
//
// It is a CAPTURE indicator and never an activity one. It appears on key-down, breathes
// with the signal, and disappears on key-up. The minutes Genesis spends on tool calls
// get the step list; one shape may not mean two things.
//
// Nothing here reaches the network. Recognition runs on the device or not at all:
// Chrome's default sends every utterance to Google with no contract and no retention
// statement, and this screen carries provider keys and unreleased results. There is no
// fallback to remote recognition — if on-device is unavailable the button says so and
// the composer still takes typing.
(() => {
  const $ = s => document.querySelector(s);
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LANGS = ['pt-BR', 'en-US'];
  const OFF_KEY = 'genesis.voice.off';

  let stream = null, ctx = null, analyser = null, frame = 0, recogniser = null;
  let level = 0, started = 0, tick = 0, reduced = false;

  const orb = () => $('#mic-orb');
  const button = () => $('#genesis-mic');
  const say = text => { const el = $('#mic-state'); if (el && el.textContent !== text) el.textContent = text; };

  function disabled() { try { return localStorage.getItem(OFF_KEY) === '1'; } catch (e) { return false; } }

  // --- the reading -------------------------------------------------------------------
  // Smoothed, or it flashes. Human syllable rate is 4-7 Hz and an unsmoothed per-frame
  // RMS produces more than three opposing changes a second, which is what WCAG 2.3.1 is
  // about. Attack 50 ms, release 250 ms.
  function envelope(next) {
    const a = next > level ? 0.35 : 0.08;
    level = level + (next - level) * a;
    return level;
  }

  function read() {
    if (!analyser) return;
    const buf = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
    const rms = Math.min(1, Math.sqrt(sum / buf.length) * 4);
    const value = envelope(rms);
    const node = orb();
    if (node) {
      if (reduced) {
        // Not a frozen orb — a frozen orb conveys nothing and removes the only live
        // evidence the microphone works. Discrete fills are a change of content, not
        // motion, and they update at 2 Hz.
        const now = Date.now();
        if (now - tick > 500) {
          tick = now;
          const lit = Math.max(1, Math.round(value * 5));
          node.querySelectorAll('.mic-step').forEach((b, i) => b.classList.toggle('on', i < lit));
        }
      } else if (Math.abs(value - Number(node.dataset.level || 0)) > 0.02) {
        node.dataset.level = value.toFixed(2);
        // CSSOM, not an inline style attribute: the CSP check greps source text for
        // `style="`, and `style-src 'self'` governs attributes, not this.
        node.style.setProperty('--mic-level', value.toFixed(2));
      }
    }
    const seconds = Math.floor((Date.now() - started) / 1000);
    say('Listening · ' + Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0'));
    frame = requestAnimationFrame(read);
  }

  // --- recognition, on the device or not at all ---------------------------------------
  async function localAvailable() {
    if (!SR) return false;
    if (typeof SR.available !== 'function') return false;   // no on-device API: refuse
    try {
      const state = await SR.available({ langs: LANGS, processLocally: true });
      return state === 'available' || state === true;
    } catch (e) { return false; }
  }

  function listen() {
    if (!SR) return null;
    const r = new SR();
    r.lang = LANGS[0];
    r.interimResults = true;       // otherwise a speech error is invisible and unrecoverable
    r.continuous = false;
    try { r.processLocally = true; } catch (e) { /* refused below if it did not take */ }
    const box = $('#genesis-message');
    const base = box.value ? box.value.replace(/\s+$/, '') + ' ' : '';
    r.onresult = e => {
      let text = '';
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      // The transcript is a draft. It is never sent on its own: speech errors are
      // otherwise invisible, and this is the text-parity anchor for WCAG 1.2.1.
      box.value = base + text;
      box.dispatchEvent(new Event('input', { bubbles: true }));
    };
    r.onerror = e => {
      const known = { 'not-allowed': 'The browser blocked the microphone. Allow it in the address bar.',
                      'service-not-allowed': 'This browser will not transcribe on the device. Type instead.',
                      'no-speech': 'Nothing was heard.',
                      'audio-capture': 'No microphone was found.',
                      'language-not-supported': 'No on-device model for ' + r.lang + '. Type instead.',
                      'network': 'Refused: that would have sent the audio off this machine.' };
      say(known[e.error] || ('Speech stopped: ' + e.error));
    };
    try { r.start(); } catch (e) { return null; }
    return r;
  }

  // --- the gesture --------------------------------------------------------------------
  async function down(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (stream || disabled()) return;
    const node = orb();
    if (node) node.hidden = false;
    say('Waiting for permission');
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: false, channelCount: 1 } });
    } catch (err) {
      stream = null;
      if (node) node.hidden = true;
      say(err && err.name === 'NotAllowedError'
        ? 'The microphone was refused. Allow it in the address bar, or type.'
        : (err && err.name === 'NotFoundError' ? 'No microphone was found. Type instead.'
          : 'The microphone could not be opened. Type instead.'));
      return;
    }
    button().setAttribute('aria-pressed', 'true');
    started = Date.now(); level = 0;
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.6;
    ctx.createMediaStreamSource(stream).connect(analyser);
    frame = requestAnimationFrame(read);
    recogniser = await localAvailable() ? listen() : null;
    if (!recogniser) say('Listening · not transcribing on this browser');
  }

  function up() {
    if (!stream) return;
    if (frame) { cancelAnimationFrame(frame); frame = 0; }
    // stop(), never enabled=false: the browser and OS recording indicators only go out
    // when the track actually ends.
    stream.getTracks().forEach(t => t.stop());
    stream = null;
    if (ctx) { ctx.close().catch(() => {}); ctx = null; }
    analyser = null;
    if (recogniser) { try { recogniser.stop(); } catch (e) {} recogniser = null; }
    const node = orb();
    if (node) { node.hidden = true; node.style.removeProperty('--mic-level'); delete node.dataset.level; }
    button().setAttribute('aria-pressed', 'false');
    say('');
    $('#genesis-message').focus();
  }

  function start() {
    const b = button();
    if (!b) return;
    reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', e => { reduced = e.matches; });
    if (!SR && !navigator.mediaDevices) { b.hidden = true; return; }
    b.addEventListener('pointerdown', down);
    b.addEventListener('pointerup', up);
    b.addEventListener('pointercancel', up);
    b.addEventListener('pointerleave', up);
    // Keyboard parity. Not plain space — the composer is a textarea.
    document.addEventListener('keydown', e => {
      if (e.code === 'Space' && e.ctrlKey && e.shiftKey && !e.repeat) down(e);
    });
    document.addEventListener('keyup', e => { if (e.code === 'Space' && e.ctrlKey && e.shiftKey) up(); });
    localAvailable().then(ok => {
      if (!ok) b.title = 'Speech is not transcribed on this browser; the microphone still records nothing off this machine.';
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
