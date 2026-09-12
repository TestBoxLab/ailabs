// GPT-Live-1 media and captions. The authenticated server owns work and billing.
(() => {
  const $ = id => document.getElementById(id);
  let current = null;
  const MODE_KEY = 'genesis.voice.mode';
  let mode = (() => { try { return localStorage.getItem(MODE_KEY) === 'push' ? 'push' : 'always'; } catch { return 'always'; } })();
  let pttHeld = false;
  let noticeTimer = null;
  const audio = () => $('genesis-voice-audio');
  const say = text => { $('genesis-voice-state').textContent = text; };
  const workspace = () => window.genesisWorkspaceContext?.() || {route: location.hash || '#reports'};
  const endpoint = s => '/api/genesis/voice/sessions/' + encodeURIComponent(s.id);
  const owned = s => current === s && !s.finished;

  function controls(s) {
    $('genesis-voice-start').disabled = !!s;
    $('genesis-voice-end').hidden = !s;
    $('genesis-voice-end').disabled = !!s?.closing;
    $('genesis-voice-mute').hidden = !s;
    $('genesis-voice-mute').disabled = !s?.ready || s.closing || !!s.mutePending;
    $('genesis-voice-mute').textContent = s?.muted ? 'Start listening' : 'Stop listening';
    $('genesis-voice-mute').setAttribute('aria-pressed', String(!!s && !s.muted));
    const modeButton = $('genesis-voice-mode');
    modeButton.textContent = mode === 'always' ? 'Mode: always listen' : 'Mode: push to talk';
    modeButton.setAttribute('aria-pressed', String(mode === 'always'));
    modeButton.title = mode === 'always' ? 'Switch to push to talk (F8)' : 'Switch to always listen (F8)';
    $('genesis-voice-playback').hidden = !s;
    $('genesis-voice-playback').textContent = audio().muted ? 'Resume audio' : 'Pause audio';
    $('genesis-voice-playback').setAttribute('aria-pressed', String(audio().muted));
    $('genesis-voice-bar').dataset.active = String(!!s);
    window.genesisOrb?.voice(s);
    const mic = $('genesis-mic'); if (mic) mic.disabled = !!s;
  }

  function requestMuted(s, muted) {
    if (!owned(s) || !s.stream) return;
    s.wantedMuted = muted;
    if (muted) {
      s.muted = true;
      s.stream.getAudioTracks().forEach(track => { track.enabled = false; });
    }
    if (!s.ready || s.closing || s.mutePending || s.channel?.readyState !== 'open') { controls(s); return; }
    if (s.remoteMuted === muted) {
      s.muted = muted;
      s.stream.getAudioTracks().forEach(track => { track.enabled = !muted; });
      controls(s); say(muted ? 'Connected · not listening' : 'Connected · listening');
      return;
    }
    const id = 'mic-' + (++s.commandId);
    s.mutePending = {id,muted};
    s.channel.send(JSON.stringify({type:muted?'session.input_audio.mute':'session.input_audio.unmute',event_id:id}));
    controls(s); say(muted ? 'Stopping listening…' : 'Starting listening…');
    s.muteTimer = setTimeout(() => {
      if (!owned(s)) return;
      s.mutePending = null; s.muted = true; s.wantedMuted = true;
      s.stream.getAudioTracks().forEach(track => { track.enabled = false; });
      controls(s); say('Genesis is not listening. The voice service did not confirm; try Start listening again.');
    },5000);
  }

  function notifyMode() {
    const notice = $('genesis-voice-mode-notice');
    if (!notice) return;
    notice.textContent = mode === 'always'
      ? 'Always listen · Genesis will listen until you stop it.'
      : 'Push to talk · Hold Ctrl+Shift+Space while you speak.';
    notice.dataset.visible = 'true';
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => { notice.dataset.visible = 'false'; }, 2600);
  }

  function setMode(next) {
    const changed = mode !== (next === 'push' ? 'push' : 'always');
    mode = next === 'push' ? 'push' : 'always';
    try { localStorage.setItem(MODE_KEY, mode); } catch {}
    const s = current;
    if (s) requestMuted(s, mode === 'push' && !pttHeld);
    controls(s);
    if (changed) notifyMode();
    if (!s) say(mode === 'always' ? 'Always listen selected.' : 'Push to talk selected. Hold Ctrl+Shift+Space to speak.');
  }

  function release(s) {
    if (s.finished) return;
    s.finished = true;
    for (const key of ['startup','deadline','closeTimer','disconnectTimer','pollTimer','muteTimer']) clearTimeout(s[key]);
    s.stream?.getTracks().forEach(t => t.stop());
    s.channel?.close(); s.peer?.close();
    if (current === s) { current = null; audio().srcObject = null; controls(null); if(s.idle)window.genesisOrb?.idle(); }
  }

  function serverClose(s, detached=false) {
    if (!s.id || s.closeRequested) return;
    s.closeRequested = true;
    // The server retains unknown usage if finalization is not observed.
    api(endpoint(s) + (detached ? '/detach' : '/close'), {}, false, {keepalive:detached}).catch(() => {
      if (!current || current === s) say('Audio ended. Server finalization is unconfirmed; check Genesis usage before reconnecting.');
    });
  }

  function fail(s, message) {
    if (!owned(s)) return;
    serverClose(s); release(s); say(message); window.genesisOrb?.problem();
  }

  function end() {
    const s = current;
    if (!s || s.closing) return;
    s.closing = true;
    // Stop capturing the caller immediately, but retain tracks and event transport
    // until session.closed so final usage can arrive.
    s.stream?.getAudioTracks().forEach(t => { t.enabled = false; });
    controls(s);
    if (s.ready && s.channel?.readyState === 'open') {
      say('Ending voice…');
      s.channel.send(JSON.stringify({type:'session.close'}));
      serverClose(s);
      s.closeTimer = setTimeout(() => fail(s, 'Voice ended without confirmed final usage. Check Genesis usage before reconnecting.'), 15000);
    } else {
      serverClose(s); release(s); say('Voice canceled.');
    }
  }

  function caption(s, event) {
    if (typeof event.delta !== 'string' || !event.delta) return;
    if (event.event_id && s.seen.has(event.event_id)) return;
    if (event.event_id) s.seen.add(event.event_id);
    const speaker = event.type === 'session.input_transcript.delta' ? 'You' : 'Genesis';
    const start = Number.isFinite(event.start_ms) ? event.start_ms : 0;
    const stop = Number.isFinite(event.end_ms) ? event.end_ms : start;
    const pane = $('genesis-voice-captions');
    const follow = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 40;
    // A 1.2s display gap groups fragments, never initiates or cancels a task.
    let group = s.captions.find(row => row.speaker === speaker && start <= row.end + 1200 && stop >= row.start - 1200);
    if (!group) {
      const row = document.createElement('p');
      const label = document.createElement('strong'); label.textContent = speaker + ' ';
      const text = document.createElement('span'); text.className = 'voice-caption-text';
      row.append(label, text); pane.append(row);
      group = {speaker,start,end:stop,fragments:[],row,text}; s.captions.push(group);
    }
    group.fragments.push({delta:event.delta,start,end:stop});
    group.fragments.sort((a,b) => a.start-b.start || a.end-b.end);
    group.start = Math.min(start,group.start); group.end = Math.max(stop,group.end);
    group.text.textContent = group.fragments.map(f => f.delta).join('');
    // Bound only the browser display. The server retains the session record.
    if (s.captions.length > 80) s.captions.shift().row.remove();
    if (group.fragments.length > 500) group.fragments.splice(0,250);
    if (s.seen.size > 4000) s.seen.delete(s.seen.values().next().value);
    $('genesis-voice-transcript').hidden = false;
    if (follow) pane.scrollTop = pane.scrollHeight;
    $('genesis-voice-latest').hidden = follow;
  }

  async function poll(s) {
    if (!owned(s) || !s.id) return;
    try {
      const known = [...(s.acceptedTurns || [])].slice(-12).join(',');
      const data = await api(endpoint(s) + (known ? '?known=' + encodeURIComponent(known) : ''));
      if (!owned(s)) return;
      if (data.close_reason === 'idle_timeout') s.idle = true;
      if (data.status === 'closing' && s.idle) {
        s.closing = true; s.stream?.getAudioTracks().forEach(track => { track.enabled = false; });
        controls(s); say('Going idle. Voice is closing.');
      }
      for (const turn of data.turns || []) {
        if (!window.genesisAcceptVoiceTurn) continue;
        await window.genesisAcceptVoiceTurn(turn);
        (s.acceptedTurns ||= new Set()).add(turn.id);
      }
      if (data.status === 'closed') {
        release(s); say(s.idle ? 'Voice is idle. Click the ball to talk again.' : 'Voice ended.'); return;
      }
      if (['failed','unknown','expired','disconnected'].includes(data.status)) {
        fail(s, 'Voice disconnected. Final usage may be unconfirmed. Start a new conversation when ready.'); return;
      }
      const context = workspace(), fingerprint = JSON.stringify(context);
      if (!s.closing && fingerprint !== s.context) {
        await api(endpoint(s) + '/context', {workspace:context});
        if (owned(s)) s.context = fingerprint;
      }
      s.pollErrors = 0;
    } catch {
      if (!owned(s)) return;
      s.pollErrors = (s.pollErrors || 0) + 1;
      $('genesis-voice-work').textContent = 'Workspace connection interrupted. Reconnecting…';
      if (s.pollErrors >= 3) { fail(s, 'Workspace connection lost. Voice ended; final usage is unconfirmed.'); return; }
    }
    if (owned(s)) s.pollTimer = setTimeout(() => poll(s), 1000);
  }

  function event(s, raw) {
    if (!owned(s)) return;
    let data; try { data = JSON.parse(raw); } catch { return; }
    if (data.type === 'session.started') {
      s.ready = true; clearTimeout(s.startup);
      requestMuted(s, mode === 'push' && !pttHeld);
      $('genesis-voice-work').textContent = 'Work and recorded changes appear in your Genesis conversation.';
      if (s.closing) return;
      poll(s);
    } else if (data.type === 'session.closed') {
      release(s); say(s.idle ? 'Voice is idle. Click the ball to talk again.' : 'Voice ended.');
    } else if (data.type === 'session.input_transcript.delta' || data.type === 'session.output_transcript.delta') {
      caption(s, data);
    } else if (data.type === 'session.input_audio.muted' || data.type === 'session.input_audio.unmuted') {
      if (s.mutePending && data.client_event_id === s.mutePending.id) {
        clearTimeout(s.muteTimer);
        s.remoteMuted = s.mutePending.muted; s.muted = s.remoteMuted; s.mutePending = null;
        s.stream.getAudioTracks().forEach(t => { t.enabled = !s.muted && !s.closing; });
        controls(s); say(s.muted ? 'Connected · not listening' : 'Connected · listening');
        if (s.wantedMuted !== s.remoteMuted) requestMuted(s, s.wantedMuted);
      }
    } else if (data.type === 'error') {
      say('Voice reported a problem: ' + String(data.error?.message || data.message || 'Check the connection and try speaking again.').slice(0,300)); window.genesisOrb?.problem();
    }
  }

  function waitForIce(peer) {
    if (peer.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise((resolve,reject) => {
      const timeout = setTimeout(() => { peer.removeEventListener('icegatheringstatechange', changed); reject(new Error('Microphone connection timed out. Try again.')); }, 10000);
      function changed() {
        if (peer.iceGatheringState !== 'complete') return;
        clearTimeout(timeout); peer.removeEventListener('icegatheringstatechange', changed); resolve();
      }
      peer.addEventListener('icegatheringstatechange', changed); changed();
    });
  }

  async function start() {
    if (current) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
      say('Live voice needs microphone support on HTTPS or localhost. You can still type to Genesis.'); window.genesisOrb?.problem(); return;
    }
    window.genesisStopDictation?.(); window.genesisStopSpeaking?.();
    const s = {ready:false,finished:false,closing:false,muted:false,remoteMuted:false,wantedMuted:false,commandId:0,captions:[],seen:new Set()};
    current = s; audio().muted = false; controls(s); say('Waiting for microphone permission…');
    $('genesis-voice-captions').replaceChildren();
    $('genesis-voice-work').textContent = '';
    s.startup = setTimeout(() => fail(s, 'Voice connection timed out. Check microphone permission and start again.'), 45000);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
      if (!owned(s)) { stream.getTracks().forEach(t => t.stop()); return; }
      s.stream = stream;
      window.genesisOrb?.attach(stream, 'input');
      s.muted = s.wantedMuted = mode === 'push' && !pttHeld;
      if (s.muted) stream.getAudioTracks().forEach(track => { track.enabled = false; });
      controls(s); say('Connecting to Genesis…');
      const peer = s.peer = new RTCPeerConnection();
      for (const track of stream.getAudioTracks()) peer.addTrack(track,stream);
      peer.addEventListener('track', e => {
        if (!owned(s)) return;
        audio().srcObject = e.streams?.[0] || new MediaStream([e.track]);
        window.genesisOrb?.attach(audio().srcObject, 'output');
        audio().play().catch(() => {
          if (owned(s)) { s.playbackBlocked = true; controls(s); say('Click the ball to hear Genesis.'); }
        });
      });
      peer.addEventListener('connectionstatechange', () => {
        if (!owned(s)) return;
        if (peer.connectionState === 'failed') fail(s, 'Voice connection failed. Start a new conversation when ready.');
        else if (peer.connectionState === 'disconnected') {
          say('Voice connection interrupted. Reconnecting…');
          clearTimeout(s.disconnectTimer);
          s.disconnectTimer = setTimeout(() => fail(s, 'Voice disconnected. Start a new conversation when ready.'), 10000);
        } else if (peer.connectionState === 'connected') {
          clearTimeout(s.disconnectTimer);
          if (s.ready && !s.closing) say(s.muted ? 'Connected · microphone muted' : 'Connected · listening');
        }
      });
      const channel = s.channel = peer.createDataChannel('oai-events');
      channel.addEventListener('message', e => event(s,e.data));
      channel.addEventListener('close', () => fail(s, 'Voice disconnected without final usage. Check Genesis usage before reconnecting.'));
      const offer = await peer.createOffer(); if (!owned(s)) return;
      await peer.setLocalDescription(offer); await waitForIce(peer); if (!owned(s)) return;
      const context = workspace(); s.context = JSON.stringify(context);
      await window.genesisRestoreConversation?.();
      if (!owned(s)) return;
      const thread = window.genesisVoiceThreadContext?.() || {};
      const result = await api('/api/genesis/voice/sessions', {sdp:peer.localDescription.sdp,...thread,workspace:context});
      s.id = result.id || result.session?.id;
      window.genesisRememberVoiceThread?.(result);
      if (!owned(s)) { serverClose(s); return; }
      if (!s.id || !result.transport?.sdp) throw new Error('Voice connection returned no session or audio connection. Try again.');
      await peer.setRemoteDescription({type:'answer',sdp:result.transport.sdp});
      if (!owned(s)) return;
      // The provider has already started the session. Never send session.start.
      const seconds = Math.max(15,Math.min(900,Number(result.max_seconds)||300));
      s.deadline = setTimeout(end, seconds * 1000);
    } catch (error) {
      const message = error.name === 'NotAllowedError' ? 'Microphone permission was refused. Allow the microphone in your browser, then start again.'
        : error.name === 'NotFoundError' ? 'No microphone was found. Connect one, then start again.'
        : error.message || 'Voice could not connect. Try again.';
      fail(s,message);
    }
  }

  function init() {
    if (!$('genesis-voice-start')) return;
    controls(null);
    $('genesis-voice-start').addEventListener('click',start);
    $('genesis-voice-end').addEventListener('click',end);
    $('genesis-voice-mute').addEventListener('click', () => {
      const s = current; if (!s?.ready || s.closing) return;
      requestMuted(s, !s.muted);
    });
    $('genesis-voice-mode').addEventListener('click', () => setMode(mode === 'always' ? 'push' : 'always'));
    $('genesis-voice-playback').addEventListener('click', () => {
      audio().muted = !audio().muted;
      if (!audio().muted) audio().play().catch(() => { audio().hidden = false; });
      controls(current);
    });
    $('genesis-voice-latest').addEventListener('click', () => {
      const pane = $('genesis-voice-captions'); pane.scrollTop = pane.scrollHeight;
      $('genesis-voice-latest').hidden = true;
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && current) { end(); return; }
      const target = e.target;
      const typing = target?.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target?.tagName || '');
      if (typing) return;
      if (e.code === 'F8' && !e.repeat) {
        e.preventDefault(); setMode(mode === 'always' ? 'push' : 'always');
      } else if (e.code === 'Space' && e.ctrlKey && e.shiftKey) {
        e.preventDefault();
        if (e.repeat || pttHeld) return;
        pttHeld = true; setMode('push');
        if (current) requestMuted(current,false); else start();
      }
    });
    document.addEventListener('keyup', e => {
      if (e.code !== 'Space' || !pttHeld) return;
      e.preventDefault(); pttHeld = false;
      if (current && mode === 'push') requestMuted(current,true);
    });
    window.addEventListener('blur', () => {
      if (!pttHeld) return;
      pttHeld = false; if (current && mode === 'push') requestMuted(current,true);
    });
    window.addEventListener('pagehide', () => { const s = current; if (s) { serverClose(s,true); release(s); } });
  }
  window.genesisLiveVoice = {active:() => !!current, start, end, interact(){const s=current;if(!s){start();return;}if(s.playbackBlocked){audio().play().then(()=>{s.playbackBlocked=false;controls(s);say('Connected.');}).catch(()=>say('Playback was blocked. Click the ball to try again.'));}else end();}};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
