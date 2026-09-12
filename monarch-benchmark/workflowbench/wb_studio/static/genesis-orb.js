// Presentation only. No new requests, microphone capture, or inferred completion.
(() => {
  const $ = id => document.getElementById(id);
  const bar = $('genesis-voice-bar');
  if (!bar) return;
  const panel = $('genesis-orb-panel'), launcher = $('genesis-orb-toggle');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let voice = null, turn = null, phase = '', motion = true, timer = 0, lastSample = 0, problem = false, idle = false;
  let context = null, input = null, output = null, inputSource = null, outputSource = null;
  let inputHistory = Array(80).fill(0), outputHistory = Array(80).fill(0);
  let speakingUntil = 0, lastEvents = '', pulseTimer = 0;

  function pulse() {
    if (!motion || reduced.matches || document.hidden) return;
    const sphere = $('genesis-orb-sphere');
    if (sphere.classList.contains('is-reacting')) return;
    sphere.classList.add('is-reacting');
    clearTimeout(pulseTimer); pulseTimer = setTimeout(() => sphere.classList.remove('is-reacting'), 1850);
  }
  function render() {
    const working = turn?.status === 'running';
    let next = !voice ? 'idle' : voice.closing ? 'ending' : !voice.ready ? 'connecting' : voice.muted ? 'muted' : 'listening';
    if (voice?.ready && !voice.closing && !voice.playbackMuted && !voice.playbackBlocked && Date.now() < speakingUntil) next = 'speaking';
    if (working) next = 'working';
    if (problem || (!working && ['failed','error','interrupted'].includes(turn?.status))) next = 'error';
    const labels = {idle:'Click to talk',ending:'Ending voice',connecting:'Connecting',muted:'Microphone off',listening:'Listening',speaking:'Speaking',working:'Working',error:'Needs attention'};
    if (!voice && turn?.status === 'completed') labels.idle = 'Turn complete';
    if (!voice && idle) labels.idle = 'Idle · click to talk';
    const latest = (turn?.events || []).filter(e => ['tool_started','tool_completed'].includes(e.type)).at(-1);
    const active = latest?.type === 'tool_started' ? latest : null;
    $('genesis-orb-phase').textContent = next === 'working' && active ? active.action.replaceAll('_',' ') : labels[next];
    bar.dataset.voice=String(Boolean(voice));
    panel.hidden = !voice && !problem && (!window.genesisWindowVisible?.() || location.hash.startsWith('#genesis')); 
    launcher.setAttribute('aria-expanded',String(!panel.hidden));
    launcher.setAttribute('aria-label', voice?.playbackBlocked ? 'Play Genesis audio' : voice ? 'End Genesis voice' : 'Talk to Genesis');
    if ($('genesis-orb-status').textContent !== labels[next]) $('genesis-orb-status').textContent = labels[next];
    bar.dataset.phase = next;
    if (phase !== next) { phase = next; pulse(); }
  }
  function signalPath(values, center) {
    return values.map((v,i) => `${(i * 320 / 79).toFixed(1)},${(center-v*22).toFixed(1)}`).join(' ');
  }
  function rms(analyser, enabled) {
    if (!analyser || !enabled) return 0;
    const buffer = new Uint8Array(analyser.fftSize); analyser.getByteTimeDomainData(buffer);
    let sum = 0; for (const n of buffer) sum += ((n-128)/128) ** 2;
    return Math.min(1,Math.sqrt(sum/buffer.length)*4);
  }
  function sample() {
    if (!voice) return;
    if (!document.hidden) {
      const now = Date.now();
      $('genesis-signal-reading').closest('figure').dataset.reduced = String(reduced.matches);
      const mic = rms(input,voice.ready && !voice.muted && !voice.closing);
      const speaker = rms(output,voice.ready && !voice.playbackMuted && !voice.playbackBlocked && !voice.closing);
      if (speaker > .025) speakingUntil = now + 250;
      if (now-lastSample >= 100) {
        inputHistory.push(mic); inputHistory.shift();outputHistory.push(speaker);outputHistory.shift();lastSample=now;
        if (motion && !reduced.matches) {
          $('genesis-input-line').setAttribute('points',signalPath(inputHistory,27));
          $('genesis-output-line').setAttribute('points',signalPath(outputHistory,59));
        }
        $('genesis-signal-reading').textContent = input ? `Mic ${Math.round(mic*100)} · Voice ${output ? Math.round(speaker*100) : '—'}` : 'Signal unavailable';
        if (mic > .08 || speaker > .08) pulse();
      }
      render();
    }
    timer = setTimeout(sample, reduced.matches || !motion ? 500 : 100);
  }
  function detach() {
    clearTimeout(timer); timer=0; inputSource?.disconnect(); outputSource?.disconnect();
    inputSource=outputSource=input=output=null;
    if(context) context.close().catch(()=>{});context=null;speakingUntil=0;
    inputHistory=Array(80).fill(0);outputHistory=Array(80).fill(0);
    $('genesis-input-line').setAttribute('points',signalPath(inputHistory,27));
    $('genesis-output-line').setAttribute('points',signalPath(outputHistory,59));
    $('genesis-signal-reading').textContent='Microphone off';
  }
  function attach(stream,kind) {
    try {
      context ||= new (window.AudioContext || window.webkitAudioContext)();
      const analyser=context.createAnalyser();analyser.fftSize=256;
      const source=context.createMediaStreamSource(stream);source.connect(analyser);
      if(kind==='input'){inputSource?.disconnect();inputSource=source;input=analyser;}
      else{outputSource?.disconnect();outputSource=source;output=analyser;}
      context.resume?.().catch(()=>{});
    } catch { $('genesis-signal-reading').textContent='Signal unavailable'; }
  }
  function acceptTurn(t) {
    if(!t?.id)return;
    turn=t;
    const events=t.events||[];
    const signature=t.id+':'+events.length+':'+t.status;
    if(signature===lastEvents)return;lastEvents=signature;
    const categories=[['Read',/search|read|inspect|list|fetch|browse|find/],['Build',/edit|save|create|build|update/],['Run',/run|execute|launch|test/],['Report',/report|analy|summar|show/],['Other',/.*/]];
    const counts=categories.map(()=>0);
    for(const event of events.filter(e=>e.type==='tool_completed'))counts[categories.findIndex(([,pattern])=>pattern.test(event.action||''))]++;
    const latest=events.filter(e=>['tool_started','tool_completed'].includes(e.type)).at(-1);
    const active=t.status==='running' && latest?.type==='tool_started' ? categories.findIndex(([,pattern])=>pattern.test(latest.action||'')) : -1;
    const max=Math.max(1,...counts), total=counts.reduce((a,b)=>a+b,0);
    $('genesis-action-count').textContent=total+' recorded';
    $('genesis-action-empty').hidden=events.some(e=>e.type==='tool_started'||e.type==='tool_completed');
    $('genesis-action-bars').hidden=!$('genesis-action-empty').hidden;
    [...$('genesis-action-bars').children].forEach((row,i)=>{
      row.querySelector('rect').setAttribute('width',String(counts[i]/max*100));
      row.querySelector('output').textContent=String(counts[i]);row.dataset.active=String(i===active);
    });
    $('genesis-action-note').textContent=active>=0 ? 'Now: '+latest.action.replaceAll('_',' ') : t.status==='running' ? 'Genesis is preparing its next step.' : 'Recorded tool completions · latest observed turn';
    pulse();render();
  }
  launcher.addEventListener('click',()=>{window.genesisLiveVoice?.interact();});
  document.addEventListener('genesis:turn',e=>acceptTurn(e.detail));
  document.addEventListener('genesis:window',render);
  window.genesisOrb={
    voice(s){const first=!voice&&s;if(first)idle=false;problem=false;voice=s?{ready:s.ready,muted:s.muted,closing:s.closing,playbackMuted:$('genesis-voice-audio').muted,playbackBlocked:s.playbackBlocked}:null;if(!s)detach();else if(first){clearTimeout(timer);sample();}render();},
    attach,turn:acceptTurn,idle(){idle=true;render();},
    problem(){problem=true;render();},
  };
  window.addEventListener('pagehide',detach);
  render();
})();
