// Tlamatini chat-avatar engine - extracted from agent_page.html (2026-07-17).
(function(){
  "use strict";
  function ready(fn){ if(document.readyState!=='loading'){setTimeout(fn,0);} else {document.addEventListener('DOMContentLoaded',fn);} }
  var FEMALE_RE=/(female|zira|jenny|aria|michelle|clara|nanami|sara|hazel|heera|catherine|hedda|elsa|paulina|helena|laura|isabel|sabina|woman|girl|monica|google us english|google uk english female|samantha|victoria|karen|tessa|fiona|moira|serena|allison|ava|susan|zoe|nora|mia|jess|tara|leah)/i;
  var MALE_RE=/(\bmale\b|david|mark|guy|ryan|george|james|richard|paul|thomas|daniel|alex|fred|diego|jorge|pablo|\bman\b|\bboy\b)/i;
  function allVoices(){ try{return window.speechSynthesis.getVoices()||[];}catch(e){return [];} }
  function femaleVoices(){
    var vs=allVoices();
    var en=vs.filter(function(v){return /^en(-|_|$)/i.test(v.lang||'');});
    var pool=en.length?en:vs;
    var fem=pool.filter(function(v){var n=(v.name||'');return FEMALE_RE.test(n) && !MALE_RE.test(n);});
    if(!fem.length) fem=pool.filter(function(v){return !MALE_RE.test(v.name||'');});
    if(!fem.length) fem=pool.slice();
    return fem;
  }
  var DEF={mode:'notify',voiceURI:'',volume:100,rate:1,pitch:1.05};
  function loadSettings(){ try{var s=JSON.parse(localStorage.getItem('tlm_voice_settings')||'{}');return Object.assign({},DEF,s);}catch(e){return Object.assign({},DEF);} }
  function saveSettings(s){ try{localStorage.setItem('tlm_voice_settings',JSON.stringify(s));}catch(e){} }
  var settings=loadSettings();
  function pickVoice(){
    var fem=femaleVoices(); if(!fem.length)return null;
    if(settings.voiceURI){ var m=fem.filter(function(v){return v.voiceURI===settings.voiceURI;}); if(m.length)return m[0]; }
    var pref=fem.filter(function(v){return /zira|jenny|aria|samantha|google us english|hazel/i.test(v.name||'');});
    return (pref[0]||fem[0]);
  }
  var _primed=false;
  function prime(){ if(_primed)return; _primed=true; try{ var u=new SpeechSynthesisUtterance(' '); u.volume=0; window.speechSynthesis.speak(u);}catch(e){} }
  var _keep=null;
  function keepAlive(on){ if(on){ if(_keep)return; _keep=setInterval(function(){ try{ if(window.speechSynthesis.speaking) window.speechSynthesis.resume(); else {clearInterval(_keep);_keep=null;} }catch(e){} },4000);} else { if(_keep){clearInterval(_keep);_keep=null;} } }
  function chunk(text){
    text=(text||'').replace(/\s+/g,' ').trim(); if(!text)return [];
    var parts=text.match(/[^.!?;:]+[.!?;:]?/g)||[text];
    var out=[],buf='';
    parts.forEach(function(p){ p=p.trim(); if(!p)return;
      if((buf+' '+p).length>170){ if(buf)out.push(buf); if(p.length>170){ for(var i=0;i<p.length;i+=170)out.push(p.slice(i,i+170)); buf=''; } else buf=p; }
      else buf=(buf?buf+' ':'')+p;
    });
    if(buf)out.push(buf); return out;
  }
  function speak(text,opts){
    if(!('speechSynthesis' in window))return;
    var s=loadSettings(); settings=s;
    // opts.queue = true  ->  do NOT cut off what is already being said, so that
    // consecutive messages are ALL spoken, one after another, none swallowed.
    if(!(opts&&opts.queue)){ try{window.speechSynthesis.cancel();}catch(e){} }
    var pieces=chunk(text); if(!pieces.length)return;
    var v=pickVoice(); keepAlive(true);
    pieces.forEach(function(p,i){
      var u=new SpeechSynthesisUtterance(p);
      if(v)u.voice=v;
      u.volume=Math.max(0,Math.min(1,(s.volume||100)/100));
      u.rate=s.rate||1; u.pitch=(s.pitch==null?1.05:s.pitch); u.lang=(v&&v.lang)||'en-US';
      if(i===pieces.length-1)u.onend=function(){
        // only stand down once NOTHING else is still speaking or queued
        try{ if(!window.speechSynthesis.speaking && !window.speechSynthesis.pending) keepAlive(false); }
        catch(e){ keepAlive(false); }
      };
      try{window.speechSynthesis.speak(u);}catch(e){}
    });
  }
  // ---- STOP TALKING, RIGHT NOW -------------------------------------------
  // Kills whatever is being said AND everything still queued behind it.
  function stopSpeaking(){
    try{ window.speechSynthesis.cancel(); }catch(e){}
    try{ window.speechSynthesis.cancel(); }catch(e){}   // Chrome sometimes needs a 2nd
    try{ keepAlive(false); }catch(e){}
  }
  // Turn the voice OFF for good (persists) - or back ON.
  function setSilent(on){
    var s=loadSettings(); s.mode=on?'silent':'notify'; saveSettings(s);
    if(on)stopSpeaking();
    return s.mode;
  }
  window.TLM_VOICE={speak:speak,notify:function(){speak('Your request is complete.');},femaleVoices:femaleVoices,pickVoice:pickVoice,loadSettings:loadSettings,saveSettings:saveSettings,prime:prime,stop:stopSpeaking,setSilent:setSilent};
  try{ if(window.speechSynthesis) window.speechSynthesis.onvoiceschanged=function(){}; }catch(e){}
  // ESC anywhere = shut up immediately.  Ctrl+Shift+M = mute for good / unmute.
  document.addEventListener('keydown',function(e){
    try{
      if(e.key==='Escape'){ stopSpeaking(); return; }
      if(e.ctrlKey&&e.shiftKey&&(e.key==='M'||e.key==='m')){
        e.preventDefault();
        var m=setSilent(loadSettings().mode!=='silent');
        var b=document.getElementById('tlm-avatar-bubble');
        if(b){ b.textContent=(m==='silent')?'Voice OFF':'Voice ON'; b.classList.add('tlm-show');
               clearTimeout(b._t); b._t=setTimeout(function(){b.classList.remove('tlm-show');},2600); }
      }
    }catch(err){}
  },true);
  document.addEventListener('click',prime,{once:true});
  document.addEventListener('keydown',prime,{once:true});

  ready(function(){
    var dock=document.getElementById('tlm-avatar-dock');
    var bubble=document.getElementById('tlm-avatar-bubble');
    var submit=document.getElementById('chat-message-submit');
    var input=document.getElementById('chat-message-input');
    var chatLog=document.getElementById('chat-log');
    var uname='there';
    try{ var el=document.getElementById('user_username'); if(el){var raw=JSON.parse(el.textContent||'""'); if(raw){uname=String(raw).charAt(0).toUpperCase()+String(raw).slice(1);}} }catch(e){}

    function pick(a){ return a[Math.floor(Math.random()*a.length)]; }
    function idlePhrase(){ return pick([
      "Tlamatini here, "+uname+" - one who knows, ready to learn with you.",
      uname+", I'm awake and sharp. Point me at something hard.",
      "Systems humming, "+uname+". What are we building today?",
      "Ready and listening, "+uname+". Give me a real challenge.",
      "I've got you, "+uname+". Say the word and I move.",
      "Standing by, "+uname+". Let's make something worth remembering.",
      "All circuits calm, "+uname+". Ask me anything.",
      "Here and focused, "+uname+". What's the mission?"
    ]); }
    function busyPhrase(){ return pick([
      "On it, "+uname+" - threads spinning, closing in.",
      "Deep in the work, "+uname+". Give me a heartbeat.",
      "Crunching this for you, "+uname+". Almost there.",
      "Hold tight, "+uname+" - I'm threading it together right now.",
      "Working hard, "+uname+". The good stuff is worth the wait.",
      "Almost done, "+uname+" - polishing the last piece.",
      "In the zone, "+uname+". Don't blink.",
      "Processing, "+uname+" - I've nearly got it."
    ]); }
    // Fixed completion notice - one exact line, never randomised.
    var COMPLETE_PHRASE="Your request is complete.";
    var CANCEL_PHRASE="You've canceled the task, I'm ready for new instructions.";
    // The FIXED messages are spoken EXACTLY AS WRITTEN - never paraphrased.
    // This only strips what must not be read aloud: markup, the username header
    // and the timestamp, and the END-RESPONSE sentinel.
    function plainText(m){
      var s=String(m==null?'':m);
      if(s.indexOf('<')>=0){
        try{
          var d=document.createElement('div'); d.innerHTML=s;
          d.querySelectorAll('script,style,button,.copy-button,.username,.message-timestamp,'
            +'.automated-message-execreport,.exec-report-table,.create-flow').forEach(function(n){try{n.remove();}catch(e){}});
          s=d.textContent||'';
        }catch(e){}
      }
      s=s.replace(/END-RESPONSE/g,'');
      s=s.replace(/^\s*Tlamatini\s*\([^)]*\)\s*/i,'');                 // "Tlamatini (2026/07/18 01:04:16.194)"
      s=s.replace(/\(\s*\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}[^)]*\)/g,' '); // any leftover timestamp
      s=s.replace(/\s+/g,' ').trim();
      return s.length>900?s.slice(0,900):s;
    }

    // Voice is ON for every fixed phrase unless the user picked "Silent".
    function voiceOn(){ try{ return loadSettings().mode!=='silent'; }catch(e){ return true; } }

    // Every PRE-ESTABLISHED phrase goes through here: it always shows the balloon
    // and always SPEAKS it aloud - the only exception is Silent mode.
    // `key` + `gapMs` stop the same state from repeating itself back-to-back
    // (e.g. our own "on it" and the server's "being processed" placeholder).
    var _said={};
    function announce(key,text,gapMs){
      if(!text)return false;
      var now=Date.now();
      if(key){ if(now-(_said[key]||0)<(gapMs==null?8000:gapMs))return false; _said[key]=now; }
      showBubble(text);
      if(!voiceOn())return true;
      // QUEUE it: a second message must never cut the first one short.
      prime(); speak(text,{queue:true});
      return true;
    }

    // What KIND of message is this? Every non-'answer' kind is a fixed/system
    // message that Tlamatini must speak with her own matching phrase.
    function classify(txt){
      var t=(txt||'').trim(); if(!t)return 'skip';
      var tl=t.toLowerCase();
      try{ if(window.isSelfHealingStatusMessage&&window.isSelfHealingStatusMessage(t))return 'retry'; }catch(e){}
      try{ if(window.isSessionRestoredInfoMessage&&window.isSessionRestoredInfoMessage(t))return 'restored'; }catch(e){}
      if(tl.indexOf('your agent is ready')>=0||tl.indexOf('you can now start chatting')>=0)return 'ready';
      if(tl.indexOf('you cancelled')>=0||tl.indexOf('you canceled')>=0)return 'cancel';
      if(tl.indexOf('execution interrupted')>=0)return 'interrupted';
      if(tl.indexOf('referenced rephrase')>=0||tl.indexOf('please rephrase')>=0)return 'rephrase';
      if(tl.indexOf('not ready')>=0&&tl.indexOf('agent')>=0)return 'notready';
      try{ if(window.isBusyMessageRequest&&window.isBusyMessageRequest(t))return 'busy'; }catch(e){}
      try{ if(window.isBusyMessageContext&&window.isBusyMessageContext(t))return 'busy'; }catch(e){}
      if(tl.indexOf('your request is being processed')>=0||tl.indexOf('being processed by tlamatini')>=0
         ||tl.indexOf('please wait a moment')>=0||tl.indexOf('loading the context')>=0)return 'busy';
      if(/^(please wait|loading|thinking|working on it|one moment|processing)/i.test(t))return 'busy';
      if(tl.indexOf('out of the root directory')>=0||tl.indexOf('outside the application root')>=0
         ||tl.indexOf('not a valid directory')>=0||(tl.indexOf('directory')>=0&&tl.indexOf('does not exist')>=0))return 'error';
      return 'answer';
    }

    function isWorking(){
      try{
        if(input&&input.disabled)return true;
        if(submit){var t=(submit.textContent||'').trim().toLowerCase(); if(t.indexOf('cancel')>=0||t.indexOf('stop')>=0)return true;}
        if(window.inLongOperation===true)return true;
      }catch(e){}
      return false;
    }
    function isCancelButton(){ try{ var t=(submit&&submit.textContent||'').trim().toLowerCase(); return t.indexOf('cancel')>=0||t.indexOf('stop')>=0; }catch(e){return false;} }
    function showBubble(t){ if(!bubble)return; bubble.textContent=t;
      try{ if(dock){ var r=dock.getBoundingClientRect(); bubble.style.position='fixed'; bubble.style.left='auto'; bubble.style.top='auto';
        bubble.style.right=Math.max(8,(window.innerWidth-r.right))+'px'; bubble.style.bottom=(window.innerHeight-r.top+10)+'px'; } }catch(e){}
      bubble.classList.add('tlm-show'); clearTimeout(bubble._t); bubble._t=setTimeout(function(){bubble.classList.remove('tlm-show');},4600); }

    // ---- run lifecycle: pending -> saw-work -> completed / cancelled ----
    var _pending=false, _seenWork=false, _spoken=false;
    function markSend(){
      _pending=true; _seenWork=false; _spoken=false;
      _said={};        // new run -> every fixed message may be announced again
      // NOTE: nothing is invented here. The server's own fixed message
      // ("Your request is being processed by Tlamatini. Please wait a moment.")
      // arrives a moment later and is spoken VERBATIM by onTlamatiniMessage.
    }
    function lastBotAnswer(){ try{ var arr=chatLog?chatLog.querySelectorAll('.bot-message'):[]; return arr.length?arr[arr.length-1]:null; }catch(e){return null;} }
    function extractAnswer(node){
      try{
        var body=node.querySelector('.automated-message-body')||node.querySelector('.automated-message');
        if(!body)return '';
        var clone=body.cloneNode(true);
        clone.querySelectorAll('.automated-message-execreport,.exec-report-table,.exec-denied-banner,button,.create-flow,.username,.message-timestamp,.copy-button').forEach(function(n){try{n.remove();}catch(e){}});
        return (clone.textContent||'').replace(/END-RESPONSE/g,'').trim();
      }catch(e){return '';}
    }
    // A "status" message is anything that is NOT the real final answer.
    function isStatusMsg(txt){ var k=classify(txt); return k!=='answer'; }

    function doComplete(){
      if(_spoken)return; _spoken=true; _pending=false;
      var s=loadSettings();
      showBubble(COMPLETE_PHRASE);              // balloon always
      if(s.mode==='silent')return;              // Silent: the ONLY mute case
      setTimeout(function(){
        var text=COMPLETE_PHRASE;               // exact fixed line
        if(s.mode==='speak'){
          var last=lastBotAnswer(); var a=last?extractAnswer(last):'';
          if(a && !isStatusMsg(a)) text=a;      // read the ANSWER itself, verbatim
        }
        prime(); speak(text);
      }, 220);
    }
    function doCancelSpeak(){
      _pending=false; _spoken=true;
      try{window.speechSynthesis.cancel();}catch(e){}
      _said['cancel']=0;                        // a cancel always gets announced
      announce('cancel',CANCEL_PHRASE,0);
    }

    if(submit)submit.addEventListener('click',function(){ if(isCancelButton()){ doCancelSpeak(); } else { markSend(); } });
    if(input)input.addEventListener('keydown',function(e){ if(e.key==='Enter'&&!e.shiftKey && !isCancelButton()){ markSend(); } });
    var _cf=document.getElementById('chat-form'); if(_cf)_cf.addEventListener('submit',function(){ if(!isCancelButton()){ markSend(); } });

    // (completion is handled below by hooking the app's own appendChatMessage)

    if(dock){
      var faceOuter=document.getElementById('tlm-face-outer');
      var reduce=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      var IMGS={ eo_mc:document.getElementById('tlm-s-eo-mc'), ec_mc:document.getElementById('tlm-s-ec-mc'),
                 eo_mo:document.getElementById('tlm-s-eo-mo'), ec_mo:document.getElementById('tlm-s-ec-mo') };
      var stt={eyesOpen:true, mouthOpen:false};
      function render(){
        var key=(stt.eyesOpen?'eo':'ec')+'_'+(stt.mouthOpen?'mo':'mc');
        for(var k in IMGS){ if(IMGS[k]) IMGS[k].classList.toggle('tlm-on', k===key); }
      }
      render();
      function layoutFace(){
        if(!faceOuter)return;
        var pad=5, pw=dock.clientWidth-2*pad, ph=dock.clientHeight-2*pad;
        if(pw<=0||ph<=0)return;
        var ar=1, iw,ih;
        if(pw/ph>ar){ih=ph;iw=ph*ar;}else{iw=pw;ih=pw/ar;}
        faceOuter.style.left=(pad+(pw-iw)/2)+'px';faceOuter.style.top=(pad+(ph-ih)/2)+'px';
        faceOuter.style.width=iw+'px';faceOuter.style.height=ih+'px';
      }
      layoutFace();
      if(window.ResizeObserver){try{new ResizeObserver(layoutFace).observe(dock);}catch(e){}}
      window.addEventListener('resize',layoutFace);
      function blink(done){ stt.eyesOpen=false; render(); setTimeout(function(){ stt.eyesOpen=true; render(); if(done)done(); }, 190); }
      function scheduleBlink(){
        if(reduce)return;
        setTimeout(function(){
          if(document.hidden){scheduleBlink();return;}
          blink(function(){ if(Math.random()<0.12){ setTimeout(function(){blink(scheduleBlink);},170); } else scheduleBlink(); });
        },2800+Math.random()*3800);
      }
      scheduleBlink();
      setInterval(function(){
        var sp=false; try{ sp=window.speechSynthesis&&window.speechSynthesis.speaking; }catch(e){}
        if(sp){ stt.mouthOpen=!stt.mouthOpen; render(); }
        else if(stt.mouthOpen){ stt.mouthOpen=false; render(); }
      }, 150);
      // CLICK HER WHILE SHE IS TALKING = STOP IMMEDIATELY (never talk more).
      // Click when she is quiet = she greets you. DOUBLE-CLICK = mute for good.
      function onClick(){
        prime();
        var busy=false;
        try{ busy=window.speechSynthesis.speaking||window.speechSynthesis.pending; }catch(e){}
        if(busy){ stopSpeaking(); showBubble('Voice stopped.'); return; }
        announce(null,(isWorking()?busyPhrase():idlePhrase()),0);
      }
      dock.addEventListener('click',onClick);
      dock.addEventListener('dblclick',function(e){
        e.preventDefault();
        var m=setSilent(loadSettings().mode!=='silent');
        stopSpeaking();
        showBubble(m==='silent'?'Voice OFF (double-click again for ON)':'Voice ON');
      });
      dock.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){e.preventDefault();onClick();} });
      dock.title='Click = stop talking / greet  ·  Double-click = mute  ·  Esc = stop  ·  Ctrl+Shift+M = mute';
    }

    // ---- completion: hook the app's OWN renderer (bulletproof, content-based).
    // appendChatMessage(username, message, ...) runs for EVERY message. A Tlamatini
    // message that is NOT a busy / loading / self-healing / status line IS the real
    // final answer (the app's own catch-all `else` branch that re-enables controls).
    // Speak ONLY then - never on the "Please wait a moment" placeholder or a status frame.
    // EVERY Tlamatini message is spoken: a real answer -> the completion phrase
    // (plus the answer itself in "speak" mode); any FIXED/system message -> its own
    // matching pre-established phrase. Silent mode is the only thing that mutes her.
    // Swallow only the burst of OLD messages replayed at page load; after this
    // the avatar speaks everything Tlamatini says.
    var _armed=false; setTimeout(function(){ _armed=true; },1500);

    function onTlamatiniMessage(message){
      if(!_armed)return;                       // history replay, not live speech
      var text=plainText(message);
      if(!text)return;
      var kind=classify(message);
      // The REAL answer to a request WE sent: "speak" mode reads it aloud,
      // "notify" mode says the fixed completion line instead.
      if(kind==='answer'&&_pending&&!_spoken){ doComplete(); return; }
      // EVERYTHING ELSE Tlamatini says - every fixed/system message, and any
      // message arriving with no request pending - is spoken WORD FOR WORD.
      if(kind==='cancel'||kind==='interrupted'||kind==='rephrase'||kind==='error'){
        _pending=false; _spoken=true;          // the run is over
      }
      // dedupe on the TEXT itself, so two DIFFERENT messages BOTH get spoken
      announce('t:'+text.slice(0,80),text,2500);
    }
    var _hooked=false;
    try{
      if(typeof window.appendChatMessage==='function'){
        var _origAppend=window.appendChatMessage;
        window.appendChatMessage=function(username,message){
          var r=_origAppend.apply(this,arguments);
          try{ if(username==='Tlamatini'){ var msg=message; setTimeout(function(){ onTlamatiniMessage(msg); },120); } }catch(e){}
          return r;
        };
        _hooked=true;
      }
    }catch(e){}
    // fallback DOM observer (only if the renderer could not be hooked)
    if(!_hooked && chatLog && ('MutationObserver' in window)){
      try{chatLog.querySelectorAll('.bot-message').forEach(function(b){b.setAttribute('data-tlm-spoken','1');});}catch(e){}
      var _deb=null;
      var obs=new MutationObserver(function(muts){
        if(!_pending||_spoken)return;
        var target=null;
        muts.forEach(function(mu){ Array.prototype.forEach.call(mu.addedNodes||[],function(n){
          if(n.nodeType!==1)return;
          var bm=(n.classList&&n.classList.contains('bot-message'))?n:(n.querySelector?n.querySelector('.bot-message'):null);
          if(bm&&!bm.getAttribute('data-tlm-spoken')) target=bm;
        }); });
        if(!target)return;
        clearTimeout(_deb);
        _deb=setTimeout(function(){
          if(_spoken||!_pending)return;
          var ans=extractAnswer(target); if(!ans||isStatusMsg(ans))return;
          target.setAttribute('data-tlm-spoken','1'); doComplete();
        },350);
      });
      try{obs.observe(chatLog,{childList:true,subtree:true});}catch(e){}
    }

    var overlay=document.getElementById('tlm-voice-overlay');
    function fillVoices(){
      var sel=document.getElementById('tlm-voice-select'); if(!sel)return;
      var fem=femaleVoices(); sel.innerHTML='';
      fem.forEach(function(v){var o=document.createElement('option');o.value=v.voiceURI;o.textContent=v.name+' ('+v.lang+')';sel.appendChild(o);});
      var s=loadSettings(); if(s.voiceURI)sel.value=s.voiceURI; else { var pv=pickVoice(); if(pv)sel.value=pv.voiceURI; }
    }
    function syncDialog(){
      var s=loadSettings();
      var vol=document.getElementById('tlm-voice-volume'),rate=document.getElementById('tlm-voice-rate'),pitch=document.getElementById('tlm-voice-pitch');
      if(vol){vol.value=s.volume;document.getElementById('tlm-voice-vol-val').textContent=s.volume+'%';}
      if(rate){rate.value=s.rate;document.getElementById('tlm-voice-rate-val').textContent=(s.rate).toFixed(2)+'x';}
      if(pitch){pitch.value=s.pitch;document.getElementById('tlm-voice-pitch-val').textContent=(s.pitch).toFixed(2);}
      var r=document.querySelector('input[name="tlm-voice-mode"][value="'+s.mode+'"]'); if(r)r.checked=true;
      fillVoices();
    }
    function readDialog(){
      var s=loadSettings();
      var vol=document.getElementById('tlm-voice-volume'),rate=document.getElementById('tlm-voice-rate'),pitch=document.getElementById('tlm-voice-pitch'),sel=document.getElementById('tlm-voice-select');
      if(vol)s.volume=parseInt(vol.value,10);
      if(rate)s.rate=parseFloat(rate.value);
      if(pitch)s.pitch=parseFloat(pitch.value);
      if(sel&&sel.value)s.voiceURI=sel.value;
      var r=document.querySelector('input[name="tlm-voice-mode"]:checked'); if(r)s.mode=r.value;
      return s;
    }
    window.OpenVoiceDialog=function(ev){ if(ev&&ev.preventDefault)ev.preventDefault(); prime(); if(!overlay)return; syncDialog(); overlay.style.display='flex'; };
    function closeDialog(){ if(overlay)overlay.style.display='none'; }
    if(overlay){
      var x=document.getElementById('tlm-voice-close'); if(x)x.addEventListener('click',closeDialog);
      overlay.addEventListener('click',function(e){ if(e.target===overlay)closeDialog(); });
      var save=document.getElementById('tlm-voice-save'); if(save)save.addEventListener('click',function(){ saveSettings(readDialog()); closeDialog(); });
      var test=document.getElementById('tlm-voice-test'); if(test)test.addEventListener('click',function(){ saveSettings(readDialog()); prime(); speak("Hello "+uname+"! This is my voice."); });
      ['tlm-voice-volume','tlm-voice-rate','tlm-voice-pitch'].forEach(function(id){
        var elx=document.getElementById(id); if(!elx)return;
        elx.addEventListener('input',function(){
          if(id==='tlm-voice-volume')document.getElementById('tlm-voice-vol-val').textContent=elx.value+'%';
          if(id==='tlm-voice-rate')document.getElementById('tlm-voice-rate-val').textContent=parseFloat(elx.value).toFixed(2)+'x';
          if(id==='tlm-voice-pitch')document.getElementById('tlm-voice-pitch-val').textContent=parseFloat(elx.value).toFixed(2);
        });
      });
    }
  });
})();
