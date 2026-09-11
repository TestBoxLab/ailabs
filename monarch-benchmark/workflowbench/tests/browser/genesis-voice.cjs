// Offline voice lifecycle acceptance. No provider requests or physical microphone.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
let playwright;
for (const name of [process.env.PLAYWRIGHT_MODULE, 'playwright', 'C:/Users/Lucas Wakigawa/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'].filter(Boolean)) {
  try { playwright = require(name); break; } catch {}
}
if (!playwright) throw new Error('Playwright is unavailable');
const staticDir = path.resolve(__dirname, '../../wb_studio/static');
const results = [];
const shell = () => fs.readFileSync(path.join(staticDir,'index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'');
const server = http.createServer((req,res) => {
  const name = req.url.split('?')[0];
  const file = name === '/' ? null : path.join(staticDir,name);
  res.setHeader('Content-Type', name.endsWith('.css')?'text/css':name.endsWith('.js')?'application/javascript':'text/html');
  if (!file) res.end(shell());
  else if (file.startsWith(staticDir) && fs.existsSync(file)) res.end(fs.readFileSync(file));
  else { res.statusCode=404;res.end('Missing fixture asset'); }
});
async function setup(browser, width=1440) {
  const page=await browser.newPage({viewport:{width,height:960},reducedMotion:'reduce'});
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.evaluate(() => {
    window.calls=[];window.turns=[];window.pendingMic=null;window.deferMic=false;window.rejectMic=false;
    window.stopped=0;window.peers=[];window.recordings=0;
    window.state={token:'fixture-token'};localStorage.setItem('ailabs-person-key','fixture-person');
    window.genesisVoiceThreadContext=()=>({thread:'thread-1',parent:'turn-1'});
    window.genesisWorkspaceContext=()=>({route:location.hash||'#reports'});
    window.genesisAcceptVoiceTurn=turn=>window.turns.push(turn);
    window.api=async (url,body) => {
      window.calls.push({url,body});
      if(url.endsWith('/sessions')) {
        if(window.deferCreate) await new Promise(resolve=>window.releaseCreate=resolve);
        return {id:'voice-1',session:{id:'live-provider-1'},transport:{type:'webrtc',sdp:'answer'},max_seconds:300};
      }
      return {status:'active',turns:[{id:'delegated-1',status:'running'}]};
    };
    const media=()=>{const track={enabled:true,stop(){window.stopped++;}};return {getTracks:()=>[track],getAudioTracks:()=>[track]};};
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{
      if(window.rejectMic)throw new DOMException('denied','NotAllowedError');
      if(window.deferMic)return new Promise(resolve=>window.pendingMic=()=>resolve(media()));
      return media();
    }}});
    window.RTCPeerConnection=class extends EventTarget {
      constructor(){super();window.peers.push(this);this.iceGatheringState='complete';this.connectionState='new';this.closed=false;}
      addTrack(t){this.track=t;}
      createDataChannel(){const c=new EventTarget();c.readyState='open';c.sent=[];c.send=x=>c.sent.push(JSON.parse(x));c.close=()=>{c.readyState='closed';};this.channel=c;return c;}
      async createOffer(){return {type:'offer',sdp:'offer'};}
      async setLocalDescription(d){this.localDescription=d;}
      async setRemoteDescription(d){this.remoteDescription=d;}
      close(){this.closed=true;}
    };
    window.emitVoice=e=>window.peers.at(-1).channel.dispatchEvent(new MessageEvent('message',{data:JSON.stringify(e)}));
    window.SpeechRecognition=class {
      static async available(options){window.recognitionLangs=options.langs;return window.localRecognition?'available':'unavailable';}
      start(){window.recognitionLanguage=this.lang;}stop(){}
    };
    window.AudioContext=class {createAnalyser(){return {fftSize:2048,getByteTimeDomainData:b=>b.fill(128)};}createMediaStreamSource(){return {connect(){}};}async close(){}};
    window.MediaRecorder=class {static isTypeSupported(){return true;}constructor(){this.state='inactive';}start(){window.recordings++;this.state='recording';}stop(){this.state='inactive';this.ondataavailable({data:new Blob(['fixture-audio'])});this.onstop();}};
    window.fetch=async (url,opts)=>{window.calls.push({url,headers:opts.headers});return {ok:true,json:async()=>({text:'Fixture transcription',cost_usd:0.001})};};
  });
  await page.addScriptTag({path:path.join(staticDir,'voice.js')});
  await page.addScriptTag({path:path.join(staticDir,'voice-live.js')});
  return page;
}
async function check(name, fn){await fn();results.push(name);console.log('PASS '+name);}
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await playwright.chromium.launch({channel:process.env.BROWSER_CHANNEL||'chrome'});
  try {
    await check('end before microphone permission releases late tracks without creating a session',async()=>{
      const p=await setup(browser);await p.evaluate(()=>window.deferMic=true);
      await p.locator('#genesis-voice-start').click();await p.locator('#genesis-voice-end').click();
      await p.evaluate(()=>window.pendingMic());await p.waitForFunction(()=>window.stopped===1);
      assert.equal(await p.evaluate(()=>window.calls.filter(x=>x.url.endsWith('/sessions')).length),0);
      assert.equal(await p.locator('#genesis-voice-start').isEnabled(),true);await p.close();
    });
    await check('late session admission is closed after cancellation',async()=>{
      const p=await setup(browser);await p.evaluate(()=>window.deferCreate=true);
      await p.locator('#genesis-voice-start').click();await p.waitForFunction(()=>window.releaseCreate);
      await p.locator('#genesis-voice-end').click();await p.evaluate(()=>window.releaseCreate());
      await p.waitForFunction(()=>window.calls.some(x=>x.url==='/api/genesis/voice/sessions/voice-1/close'));
      assert.equal(await p.evaluate(()=>window.peers[0].closed),true);await p.close();
    });
    await check('captions preserve overlap and late fragments; mute and graceful close retain lifecycle',async()=>{
      const p=await setup(browser);await p.locator('#genesis-voice-start').click();
      await p.waitForFunction(()=>window.peers[0].remoteDescription);
      await p.evaluate(()=>window.emitVoice({type:'session.started',session:{id:'live-provider-1'}}));
      assert.equal(await p.evaluate(()=>window.peers[0].channel.sent.some(x=>x.type==='session.start')),false);
      assert.deepEqual(await p.evaluate(()=>window.calls.find(x=>x.url.endsWith('/sessions')).body),{sdp:'offer',thread:'thread-1',parent:'turn-1',workspace:{route:'#reports'}});
      await p.evaluate(()=>{
        window.emitVoice({type:'session.output_transcript.delta',event_id:'caption-1',delta:'Hello ',start_ms:100,end_ms:200});
        window.emitVoice({type:'session.output_transcript.delta',event_id:'caption-1',delta:'Hello ',start_ms:100,end_ms:200});
        window.emitVoice({type:'session.input_transcript.delta',delta:'Open ',start_ms:150,end_ms:250});
        window.emitVoice({type:'session.output_transcript.delta',delta:'there',start_ms:200,end_ms:300});
        window.emitVoice({type:'session.input_transcript.delta',delta:'the report',start_ms:250,end_ms:400});
        window.emitVoice({type:'session.output_transcript.delta',delta:'Later.',start_ms:5000,end_ms:6000});
        window.emitVoice({type:'session.output_transcript.delta',delta:'!',start_ms:300,end_ms:350});
      });
      assert.deepEqual(await p.locator('.voice-caption-text').allTextContents(),['Hello there!','Open the report','Later.']);
      await p.locator('#genesis-voice-mute').click();assert.equal(await p.evaluate(()=>window.peers[0].track.enabled),false);
      assert.equal(await p.locator('#genesis-voice-mute').isEnabled(),false);
      await p.evaluate(()=>window.emitVoice({type:'session.input_audio.muted',client_event_id:window.peers[0].channel.sent.at(-1).event_id}));
      await p.locator('#genesis-voice-mute').click();assert.equal(await p.evaluate(()=>window.peers[0].track.enabled),false);
      assert.equal(await p.evaluate(()=>window.peers[0].channel.sent.at(-1).type),'session.input_audio.unmute');
      await p.evaluate(()=>window.emitVoice({type:'session.input_audio.unmuted',client_event_id:window.peers[0].channel.sent.at(-1).event_id}));
      assert.equal(await p.evaluate(()=>window.peers[0].track.enabled),true);
      await p.locator('#genesis-voice-playback').click();assert.equal(await p.locator('#genesis-voice-audio').evaluate(e=>e.muted),true);
      await p.evaluate(()=>location.hash='#studio/draft');
      await p.waitForFunction(()=>window.calls.some(x=>x.url.endsWith('/context')&&x.body.workspace.route==='#studio/draft'));
      await p.waitForFunction(()=>window.turns.some(x=>x.id==='delegated-1'));
      await p.locator('#genesis-voice-end').click();
      assert.equal(await p.evaluate(()=>window.peers[0].closed),false);
      assert.equal(await p.evaluate(()=>window.peers[0].channel.sent.at(-1).type),'session.close');
      await p.evaluate(()=>window.emitVoice({type:'session.closed',usage:{seconds:5}}));
      await p.waitForFunction(()=>window.peers[0].closed);assert.equal(await p.evaluate(()=>window.stopped),1);await p.close();
    });
    await check('listen button and remembered mode control microphone capture',async()=>{
      const p=await setup(browser);
      assert.equal(await p.locator('#genesis-voice-mode').innerText(),'Mode: always listen');
      await p.locator('#genesis-voice-mode').click();
      assert.equal(await p.locator('#genesis-voice-mode').innerText(),'Mode: push to talk');
      assert.equal(await p.locator('#genesis-voice-mode-notice').innerText(),'Push to talk · Hold Ctrl+Shift+Space while you speak.');
      assert.equal(await p.locator('#genesis-voice-mode-notice').getAttribute('data-visible'),'true');
      await p.waitForTimeout(2700);
      assert.equal(await p.locator('#genesis-voice-mode-notice').getAttribute('data-visible'),'false');
      assert.equal(await p.evaluate(()=>localStorage.getItem('genesis.voice.mode')),'push');
      await p.locator('#genesis-voice-start').click();await p.waitForFunction(()=>window.peers[0].remoteDescription);
      assert.equal(await p.evaluate(()=>window.peers[0].track.enabled),false);
      await p.evaluate(()=>window.emitVoice({type:'session.started'}));
      assert.equal(await p.evaluate(()=>window.peers[0].channel.sent.at(-1).type),'session.input_audio.mute');
      await p.evaluate(()=>window.emitVoice({type:'session.input_audio.muted',client_event_id:window.peers[0].channel.sent.at(-1).event_id}));
      assert.equal(await p.locator('#genesis-voice-mute').innerText(),'Start listening');
      await p.locator('#genesis-voice-mute').click();
      assert.equal(await p.evaluate(()=>window.peers[0].track.enabled),false);
      await p.evaluate(()=>window.emitVoice({type:'session.input_audio.unmuted',client_event_id:window.peers[0].channel.sent.at(-1).event_id}));
      assert.equal(await p.evaluate(()=>window.peers[0].track.enabled),true);
      assert.equal(await p.locator('#genesis-voice-mute').innerText(),'Stop listening');await p.close();
    });
    await check('keyboard switches modes and push to talk releases safely',async()=>{
      const p=await setup(browser);await p.locator('#genesis-voice-start').click();await p.waitForFunction(()=>window.peers[0].remoteDescription);
      await p.evaluate(()=>window.emitVoice({type:'session.started'}));
      await p.locator('#genesis-voice-mode').focus();await p.keyboard.press('F8');
      assert.equal(await p.locator('#genesis-voice-mode').innerText(),'Mode: push to talk');
      await p.evaluate(()=>window.emitVoice({type:'session.input_audio.muted',client_event_id:window.peers[0].channel.sent.at(-1).event_id}));
      await p.keyboard.down('Control');await p.keyboard.down('Shift');await p.keyboard.down('Space');
      assert.equal(await p.evaluate(()=>window.peers[0].channel.sent.at(-1).type),'session.input_audio.unmute');
      await p.evaluate(()=>window.emitVoice({type:'session.input_audio.unmuted',client_event_id:window.peers[0].channel.sent.at(-1).event_id}));
      assert.equal(await p.evaluate(()=>window.peers[0].track.enabled),true);
      await p.keyboard.up('Space');await p.keyboard.up('Shift');await p.keyboard.up('Control');
      assert.equal(await p.evaluate(()=>window.peers[0].track.enabled),false);
      await p.evaluate(()=>window.emitVoice({type:'session.input_audio.muted',client_event_id:window.peers[0].channel.sent.at(-1).event_id}));
      await p.locator('#genesis-panel').evaluate(e=>e.classList.remove('hidden'));await p.locator('#genesis-message').focus();await p.keyboard.press('F8');
      assert.equal(await p.locator('#genesis-voice-mode').innerText(),'Mode: push to talk');await p.close();
    });
    await check('microphone refusal is recoverable without a provider session',async()=>{
      const p=await setup(browser);await p.evaluate(()=>window.rejectMic=true);await p.locator('#genesis-voice-start').click();
      await p.waitForFunction(()=>document.querySelector('#genesis-voice-start').disabled===false);
      assert.match(await p.locator('#genesis-voice-state').innerText(),/microphone/i);
      assert.equal(await p.evaluate(()=>window.calls.length),0);await p.close();
    });
    await check('dictation release during permission request never records',async()=>{
      const p=await setup(browser);await p.locator('#genesis-panel').evaluate(e=>e.classList.remove('hidden'));
      await p.evaluate(()=>window.deferMic=true);await p.locator('#genesis-mic').dispatchEvent('pointerdown');
      await p.locator('#genesis-mic').dispatchEvent('pointerup');await p.evaluate(()=>window.pendingMic());
      await p.waitForFunction(()=>window.stopped===1);assert.equal(await p.evaluate(()=>window.recordings),0);await p.close();
    });
    await check('dictation uses person authentication and remains a draft',async()=>{
      const p=await setup(browser);await p.locator('#genesis-panel').evaluate(e=>e.classList.remove('hidden'));
      await p.locator('#genesis-mic').dispatchEvent('pointerdown');await p.waitForFunction(()=>window.recordings===1);
      await p.waitForTimeout(350);await p.locator('#genesis-mic').dispatchEvent('pointerup');
      await p.waitForFunction(()=>window.calls.some(x=>x.url==='/api/voice/stt'));
      assert.equal(await p.evaluate(()=>window.calls.find(x=>x.url==='/api/voice/stt').headers['X-Person-Key']),'fixture-person');
      assert.equal(await p.locator('#genesis-message').inputValue(),'Fixture transcription');await p.close();
    });
    await check('lost event channel releases capture and retains billing uncertainty',async()=>{
      const p=await setup(browser);await p.locator('#genesis-voice-start').click();await p.waitForFunction(()=>window.peers[0].remoteDescription);
      await p.evaluate(()=>{window.emitVoice({type:'session.started'});window.peers[0].channel.dispatchEvent(new Event('close'));});
      assert.equal(await p.evaluate(()=>window.stopped),1);assert.equal(await p.evaluate(()=>window.peers[0].closed),true);
      assert.match(await p.locator('#genesis-voice-state').innerText(),/without final usage/);await p.close();
    });
    await check('missing final event times out without claiming confirmed usage',async()=>{
      const p=await setup(browser);await p.clock.install();await p.locator('#genesis-voice-start').click();await p.waitForFunction(()=>window.peers[0].remoteDescription);
      await p.evaluate(()=>window.emitVoice({type:'session.started'}));await p.locator('#genesis-voice-end').click();await p.clock.fastForward(15001);
      assert.equal(await p.evaluate(()=>window.peers[0].closed),true);assert.match(await p.locator('#genesis-voice-state').innerText(),/without confirmed final usage/);await p.close();
    });
    await check('dictation defaults to English on-device recognition',async()=>{
      const p=await setup(browser);await p.evaluate(()=>window.localRecognition=true);await p.locator('#genesis-mic').dispatchEvent('pointerdown');
      await p.waitForFunction(()=>window.recognitionLanguage);assert.equal(await p.evaluate(()=>window.recognitionLanguage),'en-US');
      await p.locator('#genesis-mic').dispatchEvent('pointerup');await p.close();
    });
    await check('dictation ends capture at sixty seconds',async()=>{
      const p=await setup(browser);await p.clock.install();await p.locator('#genesis-mic').dispatchEvent('pointerdown');
      await p.waitForFunction(()=>window.recordings===1);await p.clock.fastForward(60001);
      assert.equal(await p.evaluate(()=>window.stopped),1);assert.equal(await p.locator('#genesis-mic').getAttribute('aria-pressed'),'false');await p.close();
    });
    await check('dictation audio setup failure releases microphone',async()=>{
      const p=await setup(browser);await p.evaluate(()=>window.AudioContext=class {constructor(){throw new Error('Audio device busy');}});
      await p.locator('#genesis-mic').dispatchEvent('pointerdown');await p.waitForTimeout(100);
      assert.equal(await p.evaluate(()=>window.stopped),1);assert.match(await p.locator('#mic-state').innerText(),/could not start/);await p.close();
    });
    const out=path.resolve(__dirname,'../../.tmp/genesis-voice-browser');fs.mkdirSync(out,{recursive:true});
    for (const width of [1440,390]) {
      const p=await setup(browser,width);await p.locator('#genesis-voice-start').click();await p.waitForFunction(()=>window.peers[0].remoteDescription);
      await p.evaluate(()=>{window.emitVoice({type:'session.started'});window.emitVoice({type:'session.output_transcript.delta',delta:'I can inspect this architecture and show the recorded changes as I work.',start_ms:0,end_ms:1000});});
      assert(await p.locator('#genesis-voice-end').isVisible());
      await p.locator('#genesis-voice-mode').click();
      assert(await p.locator('#genesis-voice-mode-notice').evaluate(e=>e.scrollWidth<=e.clientWidth));
      assert(await p.locator('#genesis-voice-bar').evaluate(e=>e.scrollWidth<=e.clientWidth));
      await p.screenshot({path:path.join(out,`voice-${width}.png`)});await p.close();
    }
    fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));
    console.log(`Genesis voice: ${results.length} scenarios passed; desktop/mobile screenshots saved.`);
  } finally {await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
