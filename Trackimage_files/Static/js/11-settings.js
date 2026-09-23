/* Settings, processing, network.
 *
 * File 11 of 13 — the page loads these in number order.
 */

var SETICO={
ui:_svgIcon('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 9v12"/>'),
proc:_svgIcon('<rect x="8" y="8" width="8" height="8" rx="1"/><path d="M4 9V6a2 2 0 0 1 2-2h3"/><path d="M20 9V6a2 2 0 0 0-2-2h-3"/><path d="M4 15v3a2 2 0 0 0 2 2h3"/><path d="M20 15v3a2 2 0 0 1-2 2h-3"/>'),
tag:_svgIcon('<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><circle cx="7" cy="7" r="1.3"/>'),
db:_svgIcon('<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'),
data:_svgIcon('<rect x="2.5" y="4" width="19" height="6" rx="1.6"/><rect x="2.5" y="14" width="19" height="6" rx="1.6"/><path d="M6 7h.01"/><path d="M6 17h.01"/><path d="M12 10v4"/>'),
keys:_svgIcon('<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01"/><path d="M7 14h10"/>'),
help:_svgIcon('<circle cx="12" cy="12" r="9"/><path d="M9.2 9.2a2.9 2.9 0 0 1 5.6 1c0 1.9-2.8 2.4-2.8 4"/><path d="M12 17.4h.01"/>'),
repair:_svgIcon('<path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v5h-5"/>')
};

var _settingsPollTimer=null;

var _conSeq=0,_conTimer=null;

var _conBuf=[];

var SET_CATS=[['ui','Interface & Gallery','ui'],['proc','Processing','proc'],
              ['tag','Auto-tagging','tag'],['data','Data & Network','data'],
              ['keys','Keyboard Shortcuts','keys'],
              ['help','Help & Reference','help'],
              ['repair','Repair & Update','repair']];

function setCat(){var c=localStorage.getItem('ti_set_cat')||'ui';
if(c==='db'||c==='net')c='data';        /* v4.32: the two merged into one */
return SET_CATS.some(function(x){return x[0]===c;})?c:'ui';}

function setNavHtml(){var cur=setCat();
return SET_CATS.map(function(x){return '<button class="set-nav-item'+(x[0]===cur?' active':'')+'" data-cat="'+x[0]+'" onclick="selectSetCat(\''+x[0]+'\')">'+SETICO[x[2]]+'<span>'+x[1]+'</span>'+(catBusy(x[0])?'<i class="work-spin on"></i>':'')+'</button>';}).join('');}

function catBusy(cat){var p=S._proc||{},t=S._tag||{},dl=(t.model_download||{});
/* v4.28: p.thumbs reports active/current/total -- there is no "pending" field on
   it, so this test was always false and the thumbnail back-fill never lit the
   indicator, in the topbar or here. */
if(cat==='proc')return ((p.pending||0)>0)||((p.active||0)>0)||
    !!(p.scan&&p.scan.active)||!!(p.unlink&&p.unlink.active)||
    !!(p.thumbs&&p.thumbs.active)||!!(p.pairs&&p.pairs.active);
if(cat==='repair')return updBusy();
if(cat==='data')return false;
if(cat==='tag')return !!dl.active||((t.active||0)>0)||(!!t.running&&(t.total||0)>(t.done||0));
return false;}

function refreshSetNav(){var nav=document.getElementById('set-nav');if(!nav)return;
SET_CATS.forEach(function(x){var b=nav.querySelector('.set-nav-item[data-cat="'+x[0]+'"]');if(!b)return;
var dot=b.querySelector('.work-spin');var want=catBusy(x[0]);
if(want&&!dot){var i=document.createElement('i');i.className='work-spin on';b.appendChild(i);}
else if(!want&&dot)dot.remove();});
/* v4.30: an 11px dot on a nav item answers "something is busy" but not "what".
   This line sits above the settings body and names the phase, so the question
   the indicator exists for is actually answered. */
var bar=document.getElementById('set-workbar');
if(bar){var busy=workBusy(),lab=workLabel();
bar.classList.toggle('on',busy);
bar.innerHTML=busy?('<i class="work-spin on"></i><span>'+esc(lab||'Working\u2026')+'</span>'):'';}}

function applySetCat(c){
document.querySelectorAll('.set-nav-item').forEach(function(b){b.classList.toggle('active',b.dataset.cat===c);});
document.querySelectorAll('.set-pane').forEach(function(p){p.classList.toggle('active',p.dataset.cat===c);});
var b=document.getElementById('set-body');if(b)b.scrollTop=0;}

function selectSetCat(c){localStorage.setItem('ti_set_cat',c);applySetCat(c);}

function advOpen(){return localStorage.getItem('ti_proc_adv')==='1';}

function toggleAdv(){var el=document.getElementById('proc-adv');if(!el)return;
var open=!el.classList.toggle('closed');localStorage.setItem('ti_proc_adv',open?'1':'0');}

function toggleConsolePanel(){var el=document.getElementById('set-console');if(!el)return;
var open=!el.classList.toggle('closed');
localStorage.setItem('ti_con_open',open?'1':'0');
if(open){var box=document.getElementById('con-box');if(box)box.scrollTop=box.scrollHeight;}}

function conClass(t){var u=t.toUpperCase();
/* v4.09: web server access lines are noise next to what the app itself says.
   They keep their place in trackimage.log, they are just folded out of view. */
if(/^\d+\.\d+\.\d+\.\d+ .*"(GET|POST|PUT|DELETE|HEAD) /.test(t)){
/* v4.14: the web server's own chatter is always hidden -- nobody reads a wall of
   "GET /thumb/123 200". A request that FAILED is another matter, so 4xx and 5xx
   stay visible. */
return / [45]\d\d [-0-9]/.test(t)?'l-err':'l-http';}
if(u.indexOf(' ERROR')>=0||u.indexOf('TRACEBACK')>=0||t.indexOf('\u26a0')>=0)return 'l-err';
if(u.indexOf('WARNING')>=0)return 'l-warn';
if(t.indexOf('\u2713')>=0)return 'l-ok';return '';}

function conLineHtml(t){var c=conClass(t);return '<div'+(c?' class="'+c+'"':'')+'>'+esc(t)+'</div>';}

function conRepaint(){
var box=document.getElementById('con-box');if(!box)return;
box.innerHTML=_conBuf.length?_conBuf.map(conLineHtml).join('')
    :'<span class="con-empty">Waiting for output\u2026</span>';
box.dataset.painted='1';
var f=document.getElementById('con-follow');
if(!f||f.checked)box.scrollTop=box.scrollHeight;
}

async function conPoll(){
var d;try{d=await api('/api/console?since='+_conSeq);}catch(e){return;}
if(!d||!d.lines)return;
if(!d.lines.length)return;
d.lines.forEach(function(l){_conBuf.push(l.t);});
while(_conBuf.length>4000)_conBuf.shift();
_conSeq=d.seq;
var box=document.getElementById('con-box');if(!box)return;
/* v4.15: a rebuilt panel is recognised by a marker, not by counting children.
   Counting was wrong: the "Waiting for output" placeholder IS a child, so a
   freshly built panel never looked empty, the log was never painted back, and
   only the newest lines were appended underneath the placeholder. */
if(box.dataset.painted!=='1')return conRepaint();
box.insertAdjacentHTML('beforeend',d.lines.map(function(l){return conLineHtml(l.t);}).join(''));
while(box.childElementCount>4000)box.removeChild(box.firstElementChild);
var f=document.getElementById('con-follow');
if(!f||f.checked)box.scrollTop=box.scrollHeight;
}

function startConsolePoll(){
clearInterval(_conTimer);
/* _conSeq is deliberately NOT reset -- see _conBuf above. */
conRepaint();conRestoreHeight();
var ep=S.navEpoch||0;
conPoll();
_conTimer=setInterval(function(){
if(ep!==(S.navEpoch||0)||S.page!=='settings'||!document.getElementById('con-box')){clearInterval(_conTimer);return;}
conPoll();},1500);
}

function conApplyHeight(h){
    var box=document.getElementById('con-box');if(!box)return;
    h=Math.max(90,Math.min(Math.round(window.innerHeight*0.75),h));
    box.style.height=h+'px';
    localStorage.setItem('ti_con_h',h);
}

function conRestoreHeight(){
    var h=parseInt(localStorage.getItem('ti_con_h')||'0',10);
    if(h>=90)conApplyHeight(h);
}

function conCopy(){var box=document.getElementById('con-box');if(!box)return;
try{navigator.clipboard.writeText(box.innerText);showToast('Console copied','success');}
catch(e){showToast('Could not copy');}}

function startSettingsPoll(){if(_settingsPollTimer)return;var tick=async function(){if(S.page!=='settings'){_settingsPollTimer=null;return;}await refreshProcStatus();_settingsPollTimer=setTimeout(tick,800);};_settingsPollTimer=setTimeout(tick,800);}

async function refreshProcStatus(){try{var d=await api('/api/processing/status');S._proc=d;
if(S.page==='settings'){updateSettingsProc(d);refreshSetNav();}
updateGalleryProgress();}catch(_){}}

var _embedRate={},_tagRate={},_thumbRate={};

function _fpsRate(st,cur){var now=Date.now();if(!st.s)st.s=[];st.s.push([now,cur]);while(st.s.length>1&&now-st.s[0][0]>5000)st.s.shift();if(st.s.length<2)return 0;var dt=(now-st.s[0][0])/1000,dv=cur-st.s[0][1];if(dt<=0||dv<0)return 0;return dv/dt;}

function _resetRate(st){st.s=[];}

function _fmtEta(sec){if(!isFinite(sec)||sec<=0)return '';sec=Math.round(sec);if(sec<60)return sec+'s';var m=Math.floor(sec/60),x=sec%60;if(m<60)return m+'m '+(x<10?'0':'')+x+'s';var h=Math.floor(m/60);m=m%60;return h+'h '+(m<10?'0':'')+m+'m';}

function procStatHTML(d){var pending=d.pending||0,done=d.done||0,total=done+pending;if(pending===0&&!d.running)return '✓ All images processed';if(d.paused)return 'Paused · <b>'+pending+'</b> remaining';return '<b>'+done+'</b> / '+total+' files processed · <b>'+pending+'</b> pending · '+(d.active||0)+' active processors';}

function updateSettingsProc(d){if(!d)return;var wv=document.getElementById('proc-workers-val');if(wv)wv.textContent=d.workers;var ws=document.getElementById('proc-workers-slider');if(ws){if(d.max_workers)ws.max=d.max_workers;if(document.activeElement!==ws)ws.value=d.workers;}var at=document.getElementById('proc-auto-toggle');if(at&&document.activeElement!==at)at.checked=(d.auto!==false);var pending=d.pending||0,done=d.done||0,total=done+pending;var sc=d.scan||{};var ppScan=document.getElementById('pp-scan');if(ppScan){if(sc.active){ppScan.style.display='';var spc=sc.total>0?Math.round(sc.current/sc.total*100):0;var fsc=document.getElementById('ppf-scan');if(fsc)fsc.style.width=spc+'%';var ssc=document.getElementById('pps-scan');if(ssc)ssc.innerHTML=(sc.folder?esc(sc.folder)+' · ':'')+'<b>'+(sc.current||0)+'</b> / '+(sc.total||0)+' files';}else ppScan.style.display='none';}var ul=d.unlink||{};var ppUnlink=document.getElementById('pp-unlink');if(ppUnlink){if(ul.active){ppUnlink.style.display='';var upc=ul.total>0?Math.round(ul.current/ul.total*100):0;var ful=document.getElementById('ppf-unlink');if(ful)ful.style.width=upc+'%';var sul=document.getElementById('pps-unlink');if(sul)sul.innerHTML='<b>'+(ul.current||0)+'</b> / '+(ul.total||0)+' unlinked'+((ul.root)?' \u00b7 '+esc(ul.root):'');}else ppUnlink.style.display='none';}var fe=document.getElementById('ppf-embed');if(fe){var pe=total>0?Math.round(done/total*100):100;fe.style.width=pe+'%';fe.className='proc-bar-fill'+((pending===0&&!d.running)?' idle':'');}var se=document.getElementById('pps-embed');if(se){var _eh=procStatHTML(d);if(d.running&&(d.pending||0)>0){var _er=_fpsRate(_embedRate,done);if(_er>=0.5){_eh+=' \u00b7 <b>'+Math.round(_er)+'</b>/s';var _et=_fmtEta((d.pending||0)/_er);if(_et)_eh+=' \u00b7 ~'+_et+' left';}}else{_resetRate(_embedRate);}se.innerHTML=_eh;}var th=d.thumbs||{};var ppTh=document.getElementById('pp-thumbs');if(ppTh){var fth=document.getElementById('ppf-thumbs');var sth=document.getElementById('pps-thumbs');if(th.active){var tpc=th.total>0?Math.round(th.current/th.total*100):0;if(fth){fth.style.width=tpc+'%';fth.className='proc-bar-fill';}var _tp=(th.total||0)-(th.current||0);var _thh='<b>'+(th.current||0)+'</b> / '+(th.total||0)+' thumbnails \u00b7 <b>'+_tp+'</b> pending'+(th.workers?(' \u00b7 '+th.workers+' active workers'):'');var _tr=_fpsRate(_thumbRate,th.current||0);if(_tr>=0.5){_thh+=' \u00b7 <b>'+Math.round(_tr)+'</b>/s';var _te=_fmtEta(_tp/_tr);if(_te)_thh+=' \u00b7 ~'+_te+' left';}if(sth)sth.innerHTML=_thh;}else{_resetRate(_thumbRate);if(th.total>0){if(fth){fth.style.width='100%';fth.className='proc-bar-fill idle';}if(sth)sth.innerHTML='\u2713 All thumbnails cached';}else{if(fth){fth.style.width='100%';fth.className='proc-bar-fill off';}if(sth)sth.innerHTML='Idle \u2014 thumbnails render on demand';}}}var btn=document.getElementById('proc-pause-btn');if(btn){if(d.paused){btn.innerHTML='Resume';btn.disabled=false;}else if(d.running){btn.innerHTML='Pause';btn.disabled=false;}else if(pending>0){btn.innerHTML='\u25b6 Start';btn.disabled=false;}else{btn.innerHTML='Pause';btn.disabled=true;}}}

function applyProc(d){if(d&&!d.error){S._proc=d;if(S.page==='settings')updateSettingsProc(d);}}

var _procWorkTimer=null;

function onProcPauseToggle(){var d=S._proc||{};var ep=d.paused?'/api/processing/resume':(d.running?'/api/processing/pause':'/api/processing/start');api(ep,{method:'POST'}).then(applyProc);}

async function onProcReprocess(){if(!await showConfirm('Reprocess <strong>all</strong> images?\n\nThis recomputes metadata, thumbnails and duplicate hashes for every image. It runs in the background but can take a while for large collections.',[{label:'Cancel',key:'cancel'},{label:'Reprocess all',key:'ok',cls:'primary'}]))return;var d=await api('/api/processing/reprocess-all',{method:'POST'});applyProc(d);showToast('Reprocessing started','success');}

async function loadStats(){S.stats=await api('/api/stats');}

function toggleSettings(){navigate(S.page==='settings'?'gallery':'settings');}

function galleryProgressHtml(){ return ''; }

function updateGalleryProgress(){
    var host=document.getElementById('main-area');if(!host)return;
    var html=galleryProgressHtml(),el=document.getElementById('gal-progress');
    if(!html){if(el)el.remove();return;}
    if(!el){host.insertAdjacentHTML('afterbegin',html);return;}
    el.outerHTML=html;
}

function cpuTotal(){var p=S._proc||{};return p.cpu_count||p.max_workers||1;}

function wLabel(n){var t=cpuTotal();var pct=t?Math.round(n/t*100):0;
/* v4.16: no "Auto" any more. A slider reading "Auto" at the far right told the
   opposite of what it did -- it sat at 100% of the scale while asking for 85% of
   the machine. Both numbers, always. */
return '('+n+') \u00b7 '+pct+'%';}

/* An update is work like any other: while one runs the indicator turns, the bar
   above the settings names the phase, and the Repair & Update tab carries its
   own dot. S._updPhase is set by the status poll below. */
function updBusy(){var f=S._updPhase;return !!(f&&f!=='idle'&&f!=='failed');}

function workBusy(){
    var p=S._proc||{},t=S._tag||{},dl=(t.model_download||{});
    return !!(updBusy()||p.running||((p.pending||0)>0)||((p.active||0)>0)
        ||(p.scan&&p.scan.active)||(p.unlink&&p.unlink.active)
        ||(p.thumbs&&p.thumbs.active)||(p.pairs&&p.pairs.active)
        ||t.running||((t.active||0)>0)||dl.active);
}

function updateWorkSpinner(){
    var busy=workBusy();
    var el=document.getElementById('work-spin');
    if(el){el.classList.toggle('on',busy);
        el.title=busy?(workLabel()||'TrackImage is working in the background\u2026')
                     :'TrackImage is idle';}
}

var UPD_WORDS={downloading:'Downloading the new version',verifying:'Checking the archive',
  'backing-up':'Backing up the database',staging:'Unpacking',ready:'Restarting'};

function workLabel(){
    var p=S._proc||{},t=S._tag||{},dl=(t.model_download||{});
    if(updBusy())return (UPD_WORDS[S._updPhase]||'Updating')+'\u2026';
    if(p.unlink&&p.unlink.active)return 'Unlinking a folder\u2026';
    if(p.scan&&p.scan.active)return 'Scanning a folder\u2026';
    if(dl.active)return 'Downloading the auto-tagging model\u2026';
    if(((p.pending||0)>0)||p.running)return 'Processing images \u2014 '+(p.pending||0)+' left';
    if(p.thumbs&&p.thumbs.active){var tl=Math.max(0,(p.thumbs.total||0)-(p.thumbs.current||0));
        return 'Generating thumbnails'+(tl?' \u2014 '+tl+' left':'\u2026');}
    if(p.pairs&&p.pairs.active)return 'Comparing images for duplicates\u2026';
    if(t.running||((t.active||0)>0))return 'Auto-tagging \u2014 '+Math.max(0,(t.total||0)-(t.done||0))+' left';
    return '';
}

async function installTagging(){try{var d=await api('/api/tag/install',{method:'POST'});S._tag=Object.assign(S._tag||{},d);updateTagCard(d);showToast(((d&&d.runtime)?'Downloading the auto-tagging model':'Installing the auto-tagging runtime')+' in the background','success');}catch(e){showToast('Install failed');}}

function setThumbMode(m){S.thumbMode=(m==='ratio')?'ratio':'fixed';localStorage.setItem('ti_thumb_mode',S.thumbMode);}

function setThumbModeUI(m){setThumbMode(m);var f=document.getElementById('tm-fixed'),r=document.getElementById('tm-ratio');if(f)f.classList.toggle('btn-primary',m!=='ratio');if(r)r.classList.toggle('btn-primary',m==='ratio');}

function setInfoOpt(k,v){S.info[k]=!!v;localStorage.setItem('ti_info_'+k,v?'1':'0');}

function toggleInfoVisible(){S.info.visible=!S.info.visible;localStorage.setItem('ti_info_visible',S.info.visible?'1':'0');document.querySelectorAll('.gallery').forEach(function(g){g.classList.toggle('no-info',!S.info.visible);});layoutJustified();var b=document.getElementById('info-btn');if(b)b.classList.toggle('active',S.info.visible);}

function applyUiScale(v){v=Math.max(80,Math.min(150,parseInt(v)||100));S.uiScale=v;try{localStorage.setItem('ti_ui_scale',v);}catch(_e){}document.documentElement.style.zoom=v/100;var e=document.getElementById('ui-scale-val');if(e)e.textContent=v+'%';var s=document.getElementById('ui-scale-range');if(s&&+s.value!==v)s.value=v;clearTimeout(_ljTimer);_ljTimer=setTimeout(layoutJustified,80);}

function procTroubleHtml(p){
  if(!p)return '';
  if(p.died)return '<div class="proc-hint" style="color:var(--danger);border-left:3px solid var(--danger);padding-left:10px;margin:8px 0">'
    +'<b>Background processing stopped.</b> '+esc(p.died)
    +'<br>The full error is in Settings \u203a Console and in Logs/trackimage.log. Press Resume to start it again.</div>';
  if(p.stalled)return '<div class="proc-hint" style="color:var(--accent-light);border-left:3px solid var(--accent);padding-left:10px;margin:8px 0">'
    +'<b>Waiting for the drive.</b> Files cannot be read at the moment, so processing is holding rather than '
    +'marking them as bad. It carries on by itself as soon as the drive answers.</div>';
  return '';
}

function benchLine(tg){
var b=(tg&&tg.benchmark)||{};
var names={CUDAExecutionProvider:'CUDA',DmlExecutionProvider:'DirectML',ROCMExecutionProvider:'ROCm'};
var cpu=b.CPUExecutionProvider,gpu=null,gname='';
for(var k in b){if(k!=='CPUExecutionProvider'&&k!=='_for'&&names[k]){gpu=b[k];gname=names[k];break;}}
/* a stored 0 means "too fast to measure", not "no measurement" -- treat it as
   absent rather than dividing by it */
if(!(cpu>0)&&!(gpu>0))return '';
if(cpu>0&&gpu>0){}else{gpu=(gpu>0?gpu:null);cpu=(cpu>0?cpu:null);}
var ms=function(v){return Math.round(v*1000)+' ms';};
if(cpu&&gpu){
  var faster=gpu<cpu, ratio=faster?(cpu/gpu):(gpu/cpu);
  var txt=faster
    ? gname+' is '+ratio.toFixed(1)+'\u00d7 faster than the processor here'
    : 'The processor is '+ratio.toFixed(1)+'\u00d7 faster than '+gname+' on this machine';
  return '<div class="proc-hint" style="margin-top:6px'+(faster?'':';color:var(--warning,#c9a227)')+'">'
    +esc(txt)+' \u2014 '+gname+' '+ms(gpu)+' vs CPU '+ms(cpu)+' per image.'
    +(faster?'':' Switching to the CPU runtime below would tag faster.')+'</div>';
}
return '<div class="proc-hint" style="margin-top:6px">Measured '+ms(cpu||gpu)+' per image.</div>';
}

function updateTagInstallLine(d){
if(!d)return;
var tg=Object.assign({},S._tag||{},d);
// v3.87: never guess the runtime flag -- the event carries it now, and
// assuming "installed" showed the wrong size on the install button.
var nodes=document.querySelectorAll(".tag-status-line");
if(nodes.length){var html=_tagStatusInner(tg);
for(var i=0;i<nodes.length;i++){if(nodes[i].innerHTML!==html)nodes[i].innerHTML=html;}}
// v3.75: the detail view, tag table and duplicates page render through
// _tagInstallHint instead, which v3.74 never refreshed \u2014 so a stale
// percentage sat next to a live one. Replace those in place too.
var hints=document.querySelectorAll(".tag-install-hint");
for(var j=0;j<hints.length;j++){
var pre=hints[j].getAttribute("data-pre")||"";
var rep=_tagInstallHint(pre);
if(!rep){hints[j].remove();continue;}
var tmp=document.createElement("div");tmp.innerHTML=rep;
var el=tmp.firstElementChild;
if(el&&hints[j].innerHTML!==el.innerHTML)hints[j].innerHTML=el.innerHTML;}
}

var _venv=null;

function runtimeName(k){return {cuda:'CUDA (NVIDIA)',dml:'DirectML',cpu:'Processor'}[k]||k||'\u2014';}

async function loadVenv(deep){
    var el=document.getElementById('venv-body');
    if(el)el.innerHTML='<span class="spinner"></span> '+(deep?'Hashing every file \u2014 this reads gigabytes\u2026':'Checking\u2026');
    try{_venv=await api('/api/venv/check'+(deep?'?deep=1':''));}catch(e){_venv={error:String(e)};}
    renderVenv();
}

function renderVenv(){
    var v=_venv||{};
    /* v4.23: the card + runtime now live in the auto-tagging block itself, so the
       tagging status is what has to be redrawn once the check comes back. */
    try{ if(S._tag) updateTagInstallLine(S._tag); }catch(_e){}
    var sel=document.getElementById('rt-sel');
    if(sel&&v.runtime_pref)sel.value=v.runtime_pref;
    var el=document.getElementById('venv-body');if(!el)return;
    if(v.error)return el.innerHTML='<p style="color:var(--danger)">'+esc(v.error)+'</p>';
    var body;
    if(v.ok){
        body='<p style="color:var(--success)">\u2713 '+(v.checked||0).toLocaleString()+
             ' files match what pip recorded'+(v.deep?' \u2014 contents verified':' \u2014 sizes verified')+'.</p>';
    }else{
        var list=(v.damaged||[]).map(function(d){
            return '<li>'+esc(d.file)+' \u2014 expected '+esc(d.expected)+', found '+esc(d.found)+'</li>';}).join('')+
            (v.missing||[]).map(function(f){return '<li>'+esc(f)+' \u2014 missing</li>';}).join('');
        body='<p style="color:var(--danger)">Some files do not match what pip recorded.</p>'+
             '<ul style="margin:6px 0 8px 18px;font-size:12px">'+list+'</ul>'+
             (v.packages&&v.packages.length?'<p style="font-size:12px;color:var(--text-muted)">Affected: '+
               esc(v.packages.join(', '))+'</p>':'');
    }
    /* All three buttons, always. Repair says plainly when there is nothing to do
       rather than hiding until the day it is needed. */
    el.innerHTML=body+
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">'+
      '<button class="btn btn-sm" onclick="loadVenv(false)">Check again</button>'+
      '<button class="btn btn-sm" onclick="loadVenv(true)">Deep check \u2014 reads every file</button>'+
      '<button class="btn btn-sm'+(v.ok?'':' btn-primary')+'" onclick="repairVenv()">Repair installation</button>'+
      '</div>'+
      (v.ok?'<p style="margin:8px 0 0;font-size:12px;color:var(--text-muted)">Nothing needs repairing right now. '+
            'Repair reinstalls the auto-tagging packages from scratch, ignoring pip\'s cache \u2014 useful if '+
            'tagging misbehaves for no obvious reason.</p>':'');
}

async function repairVenv(){
    var healthy=!!(_venv&&_venv.ok);
    var msg=healthy
        ? 'Nothing looks damaged. Reinstall the auto-tagging runtime anyway? It is downloaded again \u2014 up to ~2.5 GB for CUDA, ~25 MB for DirectML.'
        : 'Reinstall the packages that do not match? They are downloaded again \u2014 up to a few GB for CUDA.';
    if(!await showConfirm(msg,[{label:'Cancel',key:'cancel'},{label:'Repair',key:'ok',cls:'danger'}]))return;
    var el=document.getElementById('venv-body');
    if(el)el.innerHTML='<span class="spinner"></span> Reinstalling \u2014 watch the console for progress\u2026';
    try{var r=await api('/api/venv/repair',{method:'POST',body:JSON.stringify({force:healthy})});
        showToast(r&&r.ok?'Repaired \u2014 restart TrackImage to load the new files':'Repair did not finish \u2014 see the console',
                  r&&r.ok?'success':'error');
    }catch(e){showToast('Repair failed','error');}
    loadVenv(false);
}

async function setRuntime(v){
    try{var r=await api('/api/venv/runtime',{method:'POST',body:JSON.stringify({pref:v})});
        if(r&&r.error)return showToast(r.error,'error');
        showToast('Runtime set to '+runtimeName(r.runtime)+' \u2014 reinstall auto-tagging to apply','success');
        loadVenv(false);
    }catch(e){showToast('Could not change the runtime','error');}
}

function runtimeSelectHtml(){
    var v=(_venv&&_venv.runtime_pref)||'auto';
    function o(val,label){return '<option value="'+val+'"'+(v===val?' selected':'')+'>'+label+'</option>';}
    return '<select class="sel" style="max-width:290px" onchange="setRuntime(this.value)" id="rt-sel">'+
        o('auto','Match the graphics card (recommended)')+
        o('cuda','CUDA \u2014 NVIDIA only, ~2.5 GB, fastest')+
        o('dml','DirectML \u2014 any DirectX 12 card, ~25 MB, slower')+
        o('cpu','Processor only \u2014 ~15 MB')+'</select>';
}

function hardwareLineHtml(){
    var v=_venv||{};
    if(!v.runtime)return '';
    return '<div style="margin-top:8px;font-size:12px;color:var(--text-muted)">'+
        'Graphics card: <b>'+esc((v.gpu||'not identified').toUpperCase())+'</b> \u00b7 '+
        'runtime: <b>'+esc(runtimeName(v.runtime))+'</b>'+
        (v.device?' \u00b7 currently running on <b>'+esc(v.device)+'</b>':'')+
        (v.runtime_reason?' \u2014 '+esc(v.runtime_reason):'')+'</div>';
}

function healthCardHtml(){
    return '<div class="settings-card"><h3>Installation health</h3>'+
      '<p>Every file pip installs is recorded with its size and checksum. Holding the '+
      'installation against that record finds a library that arrived incomplete \u2014 a '+
      'download cut short, a disk that filled up \u2014 which otherwise shows up much later '+
      'as auto-tagging quietly falling back to the processor.</p>'+
      '<div id="venv-body"><span class="spinner"></span> Checking\u2026</div></div>';
}

function buildTagCard(tg){tg=tg||{};var pct=tg.total?Math.round((tg.done||0)/tg.total*100):0;
var g=(tg.gen!=null?tg.gen:0.25),c=(tg.char!=null?tg.char:0.85);
var mw=(tg.max_workers||8),wv=(tg.workers!=null?tg.workers:4),wpos=(wv>0?Math.min(wv,mw):Math.max(1,Math.round(mw*0.85)));
return sCard('Auto-tagging','Recognises what is in each picture \u2014 characters, clothing, scenery \u2014 so you can search for it. Runs in the background over the whole library and every new picture; the tags are kept in the database. GIFs and videos are tagged from their first frame.',
  '<div id="tag-status-box" class="s-status">'+_tagStatusHtml(tg)+'</div>'
  +sRow('Tag new pictures automatically','Part of Autosync.',sSwitch('id="tag-toggle"',S.autosync,'toggleAutosync()'))
  +sSlider('General tags','<span id="tag-gen-val">'+g.toFixed(2)+'</span>','<input id="tag-gen" type="range" min="0.05" max="0.9" step="0.05" value="'+g+'" oninput="var e=document.getElementById(\'tag-gen-val\');if(e)e.textContent=parseFloat(this.value).toFixed(2)" onchange="applyTagThreshold()">','How sure the model must be. Lower gives more tags and more wrong ones.')
  +sSlider('Character names','<span id="tag-char-val">'+c.toFixed(2)+'</span>','<input id="tag-char" type="range" min="0.05" max="0.95" step="0.05" value="'+c+'" oninput="var e=document.getElementById(\'tag-char-val\');if(e)e.textContent=parseFloat(this.value).toFixed(2)" onchange="applyTagThreshold()">','How sure it must be before it names a character.')
  +sSlider('Parallel workers','<span id="tag-workers-val">'+wLabel(wpos)+'</span>','<input id="tag-workers" type="range" min="1" max="'+mw+'" step="1" value="'+wpos+'" oninput="var e=document.getElementById(\'tag-workers-val\');if(e)e.textContent=wLabel(+this.value)" onchange="onTagWorkers()">','Prepare pictures for the model. Follows Processing power unless set here.')
  +'<div class="s-bars"><div class="proc-phase"><div class="proc-phase-label">Tagging</div><div class="proc-bar"><div class="proc-bar-fill'+(tg.pending?'':' idle')+'" id="tag-bar-fill" style="width:'+pct+'%"></div></div><div class="proc-stat" id="tag-stat">'+_tagStatText(tg)+'</div></div></div>'
  +'<div class="s-actions"><button class="btn btn-sm" id="tag-pause-btn" onclick="onTagPauseToggle()">'+(tg.running?'Pause':'Resume')+'</button><button class="btn btn-sm btn-warning" onclick="retagAll()" title="Work out the tags of every picture again">\u21bb Re-tag all</button></div>'
  +sMore('About the workers','<p>They read, decode and resize each picture to the size the model expects. They are not graphics-card workers: the model itself runs one picture at a time on the device, and the workers keep it fed. On a busy graphics card more of them only use memory; on the processor more genuinely helps.</p>'));}

function updateTagCard(d){if(!d)return;S._tag=Object.assign(S._tag||{},d);var t=S._tag;var fill=document.getElementById('tag-bar-fill');if(fill){var pct=t.total?Math.round((t.done||0)/t.total*100):0;fill.style.width=pct+'%';fill.className='proc-bar-fill'+(((t.pending||0)===0&&!t.running)?' idle':'');}var st=document.getElementById('tag-stat');if(st)st.innerHTML=_tagStatText(t);var tgl=document.getElementById('tag-toggle');if(tgl&&d.enabled!=null&&document.activeElement!==tgl)tgl.checked=!!d.enabled;var pb=document.getElementById('tag-pause-btn');if(pb)pb.innerHTML=t.running?'Pause':'Resume';var box=document.getElementById('tag-status-box');if(box)box.innerHTML=_tagStatusHtml(t);updateWorkSpinner();}

async function applyTagThreshold(){var g=parseFloat(document.getElementById('tag-gen').value),c=parseFloat(document.getElementById('tag-char').value);try{var d=await api('/api/tag-settings',{method:'POST',body:JSON.stringify({gen:g,char:c})});updateTagCard(d);}catch(e){}}

async function onTagWorkers(){var sl=document.getElementById('tag-workers');var mw=(+sl.max);        /* v4.16: no Auto slot past the end any more */var v=parseInt(sl.value);var w=(v>mw)?0:v;try{var d=await api('/api/tag-settings',{method:'POST',body:JSON.stringify({workers:w})});updateTagCard(d);showToast('Workers: '+wLabel(w>0?w:Math.max(1,Math.round(mw*0.85)))+' \u00b7 applies on next run','success');}catch(e){}}

async function onTagPauseToggle(){var t=S._tag||{};try{var d;if(t.running){d=await api('/api/tag/stop',{method:'POST'});showToast('Tagging paused','success');}else{d=await api('/api/tag/start',{method:'POST'});if(d&&d.error){showToast(d.error);return;}showToast('Tagging resumed','success');}updateTagCard(d);}catch(e){showToast('Failed');}}

async function retagAll(){if(!await showConfirm('Re-tag <strong>all</strong> images?\n\nThis recomputes auto-tags for the whole library in the background.'))return;try{var d=await api('/api/tag/retag-all',{method:'POST'});if(d.error){showToast(d.error);}else{updateTagCard(d);showToast('Re-tagging all images\u2026','success');}}catch(e){showToast('Failed');}}

function settingsShellHtml(){
    return '<div style="border-bottom:1px solid var(--border);padding:0 12px;min-height:40px;'+
           'display:flex;align-items:center;gap:10px"><div class="logo" onclick="navigate(\'gallery\')">'+
           '<span class="logo-icon">\u25C8</span><span class="logo-text">TrackImage</span></div></div>'+
           '<div class="set-root"><div class="set-shell">'+
           '<nav class="set-nav" id="set-nav"><div class="set-nav-title">Settings</div>'+setNavHtml()+'</nav>'+
           '<div class="set-body" id="set-boot"><div class="set-pane active">'+
           '<div class="settings-card"><span class="spinner"></span> Loading settings\u2026</div>'+
           '</div></div></div></div>';
}

function netCardHtml(n,dbInfo){
n=n||{};dbInfo=dbInfo||{};
var addr='';
if(n.active&&n.best_url){
  addr='<div class="net-addr"><div class="net-addr-label">Open this on the other device</div>'
   +'<div class="net-addr-url"><code id="net-url">'+esc(n.best_url)+'</code><button class="btn btn-sm" onclick="copyNetUrl()" title="Copy">Copy</button></div>'
   +'<div class="net-addr-meta">Port <b>'+(n.port||5001)+'</b>'
   +(n.confirmed===(n.best_url.split("//")[1]||"").split(":")[0]?' \u00b7 <span style="color:var(--success)">a device has already connected on this address</span>':'')+'</div>'
   +(n.qr?('<div class="net-qr"><img alt="QR code for '+esc(n.best_url)+'" src="/api/network/qr?url='+encodeURIComponent(n.best_url)+'&t='+Date.now()+'"><div class="s-hint" style="text-align:center">Point the phone\u2019s camera at this</div></div>')
        :'<div class="s-hint">The QR code needs the <code>qrcode</code> package \u2014 the launcher installs it on the next start.</div>')
   +'</div>';
}
var share=sCard('Share on your network','Open the library on your phone, tablet or another computer \u2014 in its browser. The pictures stay on this machine.',
  sRow('Share on the local network','Changes apply after a restart.',sSwitch('',n.enabled,'onNetEnabled(this.checked)'))
  +(n.enabled&&!n.active?'<div class="s-warn"><b>Restart TrackImage</b> to open the port.</div>':'')
  +addr
  +(n.active&&!n.best_url?'<div class="s-warn">Sharing is on, but no network address was found. Look up this computer\u2019s address in your router, or with <code>ipconfig</code>.</div>':'')
  +sRow('Password','Asked once on each other device. This computer is never asked. Changing it signs the others out.'
      +(n.is_default_password?' <b style="color:var(--warning,#c9a227)">Still the default \u2014 change it before sharing.</b>':''),
      '<input id="net-pw" class="s-input" type="text" value="'+esc(n.password||'')+'"><button class="btn btn-sm btn-primary" onclick="onNetPassword(event)">Save</button>')
  +(n.sessions?'<div class="s-actions"><button class="btn btn-sm btn-warning" onclick="onNetLogoutAll()">Sign out '+n.sessions+' device'+(n.sessions>1?'s':'')+'</button></div>':'')
  +sMore('Is this safe?','<p>Every device on your network can reach TrackImage while this is on \u2014 which is why the password is not optional. Anyone with it can delete files from this computer, move folders and unlink libraries. Only switch this on in a network you control, never on public or guest Wi-Fi.</p>'));
var nasHint=dbInfo.db_on_network?(dbInfo.nas_active?'Your pictures are on a network drive, so the database runs <b>locally</b> and a copy is written back to the NAS on shutdown and every 24 h.':'<b style="color:var(--danger)">The database is on a network drive.</b> Switch this on \u2014 strongly recommended.'):'Your pictures are on a local drive, so this is idle. It switches itself on if you link a folder from a network drive.';
var nas=sCard('Network drive (NAS)','',
  sRow('NAS protection',nasHint+' Changes apply after a restart.',sSwitch('',dbInfo.nas_protection,'onNasProtection(this.checked)'))
  +sMore('Details','<p>A database on a network drive can be damaged, because file locking over the network is unreliable. With protection on, TrackImage keeps it on this computer and writes a copy (<code>trackimage.db.backup</code>) back to the drive.</p><p>A mapped drive letter and the network path behind it are the same folder: linking <code>P:\\Photos</code> and <code>\\\\server\\share\\Photos</code> does not import anything twice.</p><p style="word-break:break-all">Database: <code>'+esc(dbInfo.db_path||'')+'</code></p>'));
return share+nas;
}

/* ---- Settings building blocks ---------------------------------------------
   One look for every page: cards stacked in one readable column, each setting a
   row -- its name and one line of explanation on the left, the control on the
   right. Everything longer than a line sits behind "How it works" and opens on
   request. The pages used to run the full width of the window with every
   explanation spelled out in small print underneath, and two cards nested in a
   third ran into each other. */
function sCard(title,intro,body){return '<section class="s-card">'+(title?'<h3>'+title+'</h3>':'')+(intro?'<p class="s-intro">'+intro+'</p>':'')+body+'</section>';}

function sRow(name,hint,ctl){return '<div class="s-row"><div class="s-label"><div class="s-name">'+name+'</div>'+(hint?'<div class="s-hint">'+hint+'</div>':'')+'</div>'+(ctl?'<div class="s-ctl">'+ctl+'</div>':'')+'</div>';}

function sSlider(name,val,input,hint){return '<div class="s-slider"><div class="s-slider-head"><span class="s-name">'+name+'</span><span class="s-val">'+val+'</span></div>'+input+(hint?'<div class="s-hint">'+hint+'</div>':'')+'</div>';}

function sSwitch(attrs,on,onchange){return '<label class="switch"><input type="checkbox" '+attrs+(on?' checked':'')+' onchange="'+onchange+'"><span class="slider"></span></label>';}

function sMore(title,body,open){return '<details class="s-more"'+(open?' open':'')+'><summary>'+title+'</summary><div class="s-more-body">'+body+'</div></details>';}

async function renderSettings(){
/* Seven requests at once: the server answers on threads, so the page costs the
   slowest of them instead of the sum. A failure stays a failure of that one
   card, not of the page. */
var _s=await Promise.all([loadIgnoreWords().catch(function(){}),api('/api/processing/status').catch(function(){return {};}),api('/api/db-info').catch(function(){return {};}),api('/api/orphans').catch(function(){return {};}),api('/api/network').catch(function(){return {};}),api('/api/thumb-settings').catch(function(){return {};}),api('/api/tag-settings').catch(function(){return {};})]);
var proc=_s[1]||{};S._proc=proc;var dbInfo=_s[2]||{};var orph=_s[3]||{};var net=_s[4]||{};

/* -- Data: the database -- */
var dbCard=sCard('Database','Everything TrackImage knows about your pictures — tags, ratings, thumbnails — lives in one file.',
  sRow('Size','<span id="db-vac"></span>','<span class="s-val" id="db-size">'+_fmtBytes(dbInfo.db_bytes||0)+'</span><button class="btn btn-sm" id="db-vac-btn" onclick="onVacuum()">Compact</button>')
  +orphanBlock(orph)
  +sMore('Why compact?','<p>The database never shrinks on its own: space freed by deleted pictures or smaller thumbnails stays inside the file until it is compacted. This also runs by itself after the thumbnails are regenerated. It needs about the file’s size again as free disk space; TrackImage stays usable meanwhile.</p>')
  +sMore('Technical details','<p>'+(dbInfo.rows!=null?_etaNum(dbInfo.rows)+' pictures, ':'')+(dbInfo.count||0)+' columns per picture:</p><p style="font-family:\'Space Mono\',monospace;font-size:11.5px;word-break:break-word">'+(dbInfo.columns||[]).map(function(c){return esc(c);}).join(', ')+'</p>'));

/* -- Interface: thumbnails -- */
var ts=_s[5]||{};var tsz=ts.max_size||1024,tq=ts.quality||90;window._tsCur={total:ts.total_bytes||0,count:ts.count||0,sz:tsz,q:tq};
var thumbCard=sCard('Thumbnails','The small pictures in the grid. The full view always shows the original file.',
  '<div class="s-note" style="margin:0 0 4px"><span id="ts-cur">'+_tsCurHtml(ts.total_bytes,ts.count)+'</span><br><span id="ts-est" style="color:var(--accent-light)"></span></div>'
  +sSlider('Resolution','<span id="ts-sz-val">'+tsz+'</span> px','<input id="ts-sz" type="range" min="384" max="1280" step="128" value="'+tsz+'" oninput="var e=document.getElementById(\'ts-sz-val\');if(e)e.textContent=this.value;recalcThumbEst()">','Higher is sharper on big tiles.')
  +sSlider('Quality','<span id="ts-q-val">'+tq+'</span>%','<input id="ts-q" type="range" min="60" max="100" step="5" value="'+tq+'" oninput="var e=document.getElementById(\'ts-q-val\');if(e)e.textContent=this.value;recalcThumbEst()">','Higher looks cleaner and takes more space.')
  +'<div class="s-actions"><button class="btn btn-sm btn-primary" onclick="applyThumbSettings(event)">Apply &amp; regenerate</button></div>');

/* -- Processing -- */
var pmax=proc.max_workers||16;var mp=proc.mp||{};var mpProcs=mp.procs||Math.max(2,Math.floor(pmax/2));var mpLab=wLabel(mpProcs);
var wtPos=(proc.workers_cfg!=null&&proc.workers_cfg)||proc.workers_eff||proc.workers||pmax;var wtLab=wLabel(wtPos);
var _tw=(proc.thumbs||{});var twCfg=(_tw.workers_cfg!=null?_tw.workers_cfg:(S._thumbCfg||0));var twAuto=(_tw.workers_eff||mpProcs);var twPos=twCfg||twAuto;var twLab=wLabel(twPos);
var _pw=(proc.power||{});var pwCustom=!!_pw.custom;var pwCfg=(_pw.power!=null?_pw.power:0);var pwPos=pwCfg||(proc.auto_workers||mpProcs);var pwLab=pwCustom?'Custom':wLabel(pwPos);
function _wSlider(id,valId,lab,min,val,cb){return '<input id="'+id+'" type="range" min="'+min+'" max="'+pmax+'" step="1" value="'+val+'" oninput="var e=document.getElementById(\''+valId+'\');if(e)e.textContent=wLabel(+this.value)" onchange="'+cb+'()">';}
var procCard=sCard('Background processing','New pictures appear straight away. Their size, metadata, duplicate fingerprint and thumbnail are worked out afterwards, in the background.',
  sRow('Process new pictures automatically','Part of Autosync.',sSwitch('id="proc-auto-toggle"',S.autosync,'toggleAutosync()'))
  +sSlider('Processing power','<span id="pw-val">'+pwLab+'</span>',_wSlider('pw-slider','pw-val',pwLab,1,pwPos,'onPower'),
     'How much of the computer the background work may use. The default leaves 15% free for you.'+(pwCustom?' <b style="color:var(--accent-light)">The stages below are set individually — moving this slider lines them up again.</b>':''))
  +procTroubleHtml(proc)
  +'<div id="proc-bars" class="s-bars"><div class="proc-phase" id="pp-unlink" style="display:none"><div class="proc-phase-label">Unlinking folder</div><div class="proc-bar"><div class="proc-bar-fill" id="ppf-unlink"></div></div><div class="proc-stat" id="pps-unlink"></div></div><div class="proc-phase" id="pp-scan" style="display:none"><div class="proc-phase-label">Folder scan</div><div class="proc-bar"><div class="proc-bar-fill" id="ppf-scan"></div></div><div class="proc-stat" id="pps-scan"></div></div><div class="proc-phase" id="pp-embed"><div class="proc-phase-label">Reading pictures <span style="font-weight:400;color:var(--text-muted)">(metadata and fingerprint)</span></div><div class="proc-bar"><div class="proc-bar-fill" id="ppf-embed"></div></div><div class="proc-stat" id="pps-embed"></div></div><div class="proc-phase" id="pp-thumbs"><div class="proc-phase-label">Thumbnails <span style="font-weight:400;color:var(--text-muted)">(pictures you look at are made at once)</span></div><div class="proc-bar"><div class="proc-bar-fill" id="ppf-thumbs"></div></div><div class="proc-stat" id="pps-thumbs"></div></div></div>'
  +'<div class="s-actions"><button class="btn btn-sm" id="proc-pause-btn" onclick="onProcPauseToggle()">Pause</button><button class="btn btn-sm btn-warning" onclick="onProcReprocess()" title="Read every picture again">↻ Reprocess all</button></div>'
  +sMore('How it works','<p><b>1 · Scan</b> — a new folder is listed at once: name, date and type of every file. Nothing is opened yet, so the pictures show in the gallery immediately.</p><p><b>2 · Reading</b> — each file is then read once, and its size, embedded metadata, search words and duplicate fingerprint all come from that one read.</p><p><b>3 · Thumbnails</b> — made last, at the lowest priority. Any picture you actually look at jumps the queue.</p>')
  +'<div class="proc-how proc-adv'+(advOpen()?'':' closed')+'" id="proc-adv"><div class="sec-title" onclick="toggleAdv()"><span class="arr"></span>Advanced — set each stage separately</div><div class="proc-adv-body">'
    +sSlider('Worker threads','<span id="wt-val">'+wtLab+'</span>',_wSlider('wt-procs','wt-val',wtLab,1,wtPos,'onWtWorkers'),'Hand work to the processes below and save the results. They mostly wait — more than the processes adds nothing.')
    +sSlider('Compute processes','<span id="mp-procs-val">'+mpLab+'</span>',_wSlider('mp-procs','mp-procs-val',mpLab,2,mpProcs,'onMpWorkers'),'Do the actual work, one per processor core. Each needs about 100 MB of memory.')
    +sSlider('Thumbnail workers','<span id="tw-val">'+twLab+'</span>',_wSlider('tw-procs','tw-val',twLab,1,twPos,'onTwWorkers'),'For making thumbnails in the background. Always gives way to imports and to what you are looking at.')
  +'</div></div>');

var tg=_s[6]||{};S._tag=tg;
var tagCard=buildTagCard(tg)
  +sCard('Ignored tags','Tags the auto-tagger must never give. Removing a character with “Ignore globally” adds it here.',
     '<div class="s-tags">'+S.ignoreWords.map(function(w){return '<span class="ignore-word-tag">'+esc(w)+' <span class="remove" onclick="removeIgnoreWord(\''+esc(w)+'\')">✕</span></span>';}).join('')
     +(!S.ignoreWords.length?'<span class="s-hint" style="margin:0">None yet.</span>':'')
     +'<button class="add-tag-btn" onclick="toggleIgnoreAdd()" id="ignore-add-toggle" title="Add a word">+</button><div class="add-tag-inline" id="ignore-add-inline" style="min-width:140px"><input id="ignore-word-input" placeholder="Word…" onkeydown="if(event.key===\'Enter\')addIgnoreWord();if(event.key===\'Escape\')toggleIgnoreAdd()" onfocus="this.parentElement.classList.add(\'open\')" /></div></div>'
     +'<div class="s-note">Applies to tagging from now on — “Re-tag all” applies it to every picture.</div>');

/* -- Interface -- */
var uiCard=sCard('Appearance','',
    sSlider('Interface size','<span id="ui-scale-val">'+S.uiScale+'%</span>','<input id="ui-scale-range" type="range" min="80" max="150" step="5" value="'+S.uiScale+'" oninput="applyUiScale(this.value)">','Text, buttons and pictures together. Saved in this browser.')
    +'<div class="s-actions" style="margin-top:0"><button class="btn btn-sm" onclick="applyUiScale(100)">Reset to 100%</button></div>')
  +sCard('Gallery','',
    sRow('Tile shape','Square crop, or the whole picture in rows.','<button class="btn btn-sm'+(S.thumbMode!=='ratio'?' btn-primary':'')+'" id="tm-fixed" onclick="setThumbModeUI(\'fixed\')">Square</button><button class="btn btn-sm'+(S.thumbMode==='ratio'?' btn-primary':'')+'" id="tm-ratio" onclick="setThumbModeUI(\'ratio\')">Original ratio</button>')
    +sRow('Show name','',sSwitch('',S.info.name,'setInfoOpt(\'name\',this.checked)'))
    +sRow('Show folder','',sSwitch('',S.info.folder,'setInfoOpt(\'folder\',this.checked)'))
    +sRow('Show date','',sSwitch('',S.info.date,'setInfoOpt(\'date\',this.checked)'))
    +sRow('Include subfolders','A folder also shows the pictures in its subfolders. Also in the top bar.',sSwitch('class="incl-sub-cb"',S.inclSub,'toggleInclSub(this.checked)'))
    +'<div class="s-note">The <b>i</b> button in the top bar (key <b>I</b>) hides or shows all tile info at once.</div>'
    +sMore('Grid measurement — for troubleshooting','<p><span class="s-val" id="lj-readout">—</span></p><p>What the gallery measured when it last built a row. If a row is ever cut off at the edge, these numbers show which measurement was wrong.</p>'))
  +sCard('Full view','The full view always loads the original file.',
    sSlider('Show real pixels from','<span id="pp-val">'+(pixelPeepAt()<=0?'Off':Math.round(pixelPeepAt()*100)+'%')+'</span>','<input id="pp-slider" type="range" min="0" max="12" step="1" value="'+Math.round(pixelPeepAt())+'" oninput="setPixelPeep(this.value)">',
      'Zoomed in further than this, you see the file’s actual pixels (sharp, blocky) instead of a smoothed picture. <b>Off</b> = always smooth. Default 400%.'))
  +thumbCard
  +sCard('Drag &amp; drop','',
    sRow('Dragging out','Drop a picture onto any program and the <b>original file</b> arrives — same name, same bytes. Onto a folder in the tree, it moves there.','')
    +sRow('Dropping in',NATIVE_DROP?'Files dropped on the gallery are <b>moved</b> into the open folder. Hold <b>Ctrl</b> to copy instead; <b>Ctrl+Z</b> puts them back.':'Files dropped on the gallery are <b>copied</b> into the open folder; the originals stay where they are.',''));
var _sc=setCat();
var conOpen=localStorage.getItem('ti_con_open')!=='0';
var conStrip='<div class="set-console'+(conOpen?'':' closed')+'" id="set-console"><div class="con-grip" id="con-grip" title="Drag to resize"></div><div class="set-console-head" onclick="toggleConsolePanel()"><span class="arr">\u25BE</span><h4>Console</h4><span style="flex:1"></span><button class="btn btn-sm" onclick="event.stopPropagation();conCopy()" style="padding:2px 8px;font-size:11px">Copy</button><label class="tb-check" style="padding:0;font-size:11px" onclick="event.stopPropagation()"><input type="checkbox" id="con-follow" checked/><span>Follow</span></label></div><div class="set-console-body"><div class="con-box nohttp" id="con-box"><span class="con-empty">Waiting for output\u2026</span></div></div></div>';
var helpCard='<div class="settings-card"><p>How search, ratings and tagging work.</p><div class="proc-how"><div class="sec-title">Search &amp; Ratings</div><div class="proc-how-body"><div class="detail-section-title" style="margin:0 0 6px">Search</div><div style="font-size:14px;color:var(--text-secondary);line-height:1.8">Typing filters <strong>live</strong>; the whole box is <strong>one</strong> term \u2014 spaces belong to it ("shoyo hinata" also matches "shoyo_hinata"; underscores and spaces are interchangeable everywhere). <strong>Enter</strong> commits the term as a chip and clears the box; more chips combine with <strong>AND</strong>. Suggestions include <span style="color:var(--accent);font-weight:600">names</span>, <span style="color:#2fbfae;font-weight:600">tags</span>, <span style="color:#4d9fff;font-weight:600">folders</span> and metadata words \u2014 picking a folder applies the folder filter directly. \u2191/\u2193 select, Enter picks the highlighted entry.</div><div class="detail-section-title" style="margin:14px 0 6px">Ratings</div><div style="font-size:14px;color:var(--text-secondary);line-height:1.8"><strong>Rate 1–9</strong> with the number keys — in the detail view (current image) or with images selected in the gallery. Press <strong>0</strong> to clear.<br>Ratings are <strong>color-coded</strong> from <span style="color:hsl(0,65%,45%);font-weight:700">red (1)</span> through <span style="color:hsl(60,65%,45%);font-weight:700">yellow (5)</span> to <span style="color:hsl(120,65%,45%);font-weight:700">green (9)</span>, and the same color tints the <strong>thumbnail border</strong>.<br><strong>Content rating</strong> (from auto-tagging) is one of <span style="color:hsl(120,65%,45%);font-weight:700">general</span>, <span style="color:hsl(35,85%,50%);font-weight:700">sensitive</span>, <span style="color:hsl(0,65%,45%);font-weight:700">explicit</span> \u2014 an ambiguous (questionable) score is resolved to whichever of sensitive/explicit scores higher. Star ratings and content ratings appear as fixed filter rows at the top of the Names / Tags columns.</div></div></div><div class="proc-how"><div class="sec-title">How Tagging Works</div><div class="proc-how-body"><div style="font-size:14px;color:var(--text-secondary);line-height:1.8">All tags come from the <strong>ML auto-tagger</strong> \u2014 filenames are never parsed into tags.<br>The <strong>Names</strong> column simply groups <strong>filename bases</strong> on the fly ("Oliver (1)"/"Oliver (2)" \u2192 Oliver); clicking filters by that base.<br>The <strong>Tags</strong> column and the detail Tags panel hold every ML tag; <span style="color:var(--accent);font-weight:600">character tags</span> use gold text (like content ratings use colored text). Manual tags look identical to auto tags and survive re-tagging. Underscore and space are treated the same everywhere.<br><strong>+</strong> below the tags adds one (labeled suggestions skip tags the image already has); \u2715 on hover removes it from <strong>this image only</strong>. <strong>\u21bb</strong> in the panel header re-tags the image to restore removed auto-tags.</div></div></div></div>';startSettingsPoll();startConsolePoll();setTimeout(updateLjReadout,80);setTimeout(loadAutoCheck,90);return '<div style="border-bottom:1px solid var(--border);padding:0 12px;min-height:40px;display:flex;align-items:center;gap:10px"><div class="logo" onclick="navigate(\'gallery\')"><span class="logo-icon">◈</span><span class="logo-text">TrackImage</span></div><label class="switch" title="Autosync: watcher + auto-processing + auto-tagging"><input type="checkbox" '+(S.autosync?'checked':'')+' onchange="toggleAutosync()"><span class="slider"></span></label><span style="font-size:12px;font-weight:600;color:'+(S.autosync?'var(--success)':'var(--danger)')+'">Autosync</span><div class="nav-links"><button class="nav-link active" onclick="toggleSettings()">\u2699</button></div></div><div class="set-root"><div class="set-shell"><nav class="set-nav"><div class="set-nav-title">Settings</div>'+setNavHtml()+'</nav><div class="set-body" id="set-body"><div id="set-workbar"></div><div class="set-pane'+(_sc==='ui'?' active':'')+'" data-cat="ui">'+uiModeCardHtml()+uiCard+'</div><div class="set-pane'+(_sc==='proc'?' active':'')+'" data-cat="proc">'+procCard+'</div><div class="set-pane'+(_sc==='tag'?' active':'')+'" data-cat="tag">'+tagCard+'</div><div class="set-pane'+(_sc==='data'?' active':'')+'" data-cat="data">'+netCardHtml(net,dbInfo)+dbCard+'</div><div class="set-pane'+(_sc==='keys'?' active':'')+'" data-cat="keys">'+shortcutCardHtml()+'</div><div class="set-pane'+(_sc==='help'?' active':'')+'" data-cat="help">'+helpCard+'</div><div class="set-pane'+(_sc==='repair'?' active':'')+'" data-cat="repair">'+updateCardHtml()+healthCardHtml()+'</div><div class="footer">TrackImage v' + TI_VERSION + '</div></div></div>'+conStrip+'</div>';}

var _netW={remote:false,fails:0,locked:false};

function netLock(msg){
  if(_netW.locked)return;_netW.locked=true;
  try{document.querySelectorAll('img,video,iframe').forEach(function(e){try{e.pause&&e.pause();}catch(_x){}e.removeAttribute('src');});}catch(_e){}
  try{for(var i=1;i<99999;i++){clearInterval(i);clearTimeout(i);}}catch(_e2){}
  document.body.innerHTML='<div style="position:fixed;inset:0;z-index:99999;background:#111214;color:#e8e6e3;'
    +'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;text-align:center;padding:24px;'
    +'font-family:\'DM Sans\',system-ui,sans-serif">'
    +'<div style="font-size:34px;color:#d4a017">\u25C8</div>'
    +'<div style="font-size:17px;font-weight:600">TrackImage is disconnected</div>'
    +'<div style="font-size:13px;color:#9a9a9a;max-width:320px;line-height:1.6">'+String(msg||'')+'</div>'
    +'<button onclick="location.reload()" style="margin-top:6px;padding:11px 22px;font-size:14px;font-weight:600;'
    +'cursor:pointer;background:#d4a017;border:0;border-radius:8px;color:#111214">Reconnect</button></div>';
}

async function netHeartbeat(){
  if(_netW.locked)return;
  var r=null;
  try{r=await fetch('/api/net/ping',{cache:'no-store',credentials:'same-origin'});}catch(_e){r=null;}
  if(r&&r.status===401)return netLock('The session has ended. Enter the PIN again to continue.');
  if(r&&r.ok){
    var j=null;try{j=await r.json();}catch(_e2){}
    if(j&&j.remote===false)return netLock('This library is no longer shared on the network.');
    _netW.remote=true;_netW.fails=0;return;
  }
  /* v4.35: the first miss is enough. Waiting for a second one meant the library
     stayed readable on the phone for up to fifteen seconds after the server had
     gone -- and a picture on a screen that should have been locked is exactly
     what this is here to prevent. A dropped request on a good connection costs
     a reconnect tap; the other way round costs privacy. */
  _netW.fails++;
  netLock('TrackImage is not running, or it is no longer reachable from this device.');
}

/* ---- Repair & Update ------------------------------------------------------
   v4.57: the installation check moved out of Help, and the update check joined
   it. Both are about the install rather than about how the app is used. */

var _updLast=null,_updTimer=null;

/* Which of the two channels this installation follows. Stable is a version
   somebody has looked at and declared finished; Latest is the main branch as it
   stands, minutes after a change is pushed. Same numbering, same files -- they
   differ only in which commit they point at. */
var _updChannel='stable';

function channelBtns(){
  return '<span><button class="btn btn-sm'+(_updChannel==='stable'?' btn-primary':'')+'" onclick="setUpdateChannel(\'stable\')" title="Versions declared finished">Stable</button> '
        +'<button class="btn btn-sm'+(_updChannel==='latest'?' btn-primary':'')+'" onclick="setUpdateChannel(\'latest\')" title="The main branch as it stands \u2014 untested, may carry bugs">Latest (Beta)</button></span>';
}

function channelHintHtml(){
  return (_updChannel==='latest')
    ? '<b style="color:var(--danger)">Beta:</b> these versions go out as soon as they are pushed, with nobody having used them first \u2014 expect the occasional bug, and switch back to Stable if one gets in your way. Every change, as soon as it reaches the <b>main</b> branch \u2014 the version rises with each one, so an update can arrive several times a day. Newest work first, and the first to meet whatever it got wrong.'
    : 'Only versions that have been looked at and released. Fewer updates, each one somebody decided was ready to hand out.';
}

function updateCardHtml(){
  return '<div class="settings-card"><h3>Version</h3>'
   +'<div class="proc-row"><label>Installed</label><span class="val" style="font-family:\'Space Mono\',monospace;color:var(--accent-light)">v'+TI_VERSION+'</span></div>'
   +'<div class="proc-row"><label>Channel</label><span id="upd-ch-row">'+channelBtns()+'</span></div>'
   +'<div class="proc-hint" id="upd-ch-hint">'+channelHintHtml()+'</div>'
   +'<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">'
   +'<button class="btn btn-sm btn-primary" id="upd-btn" onclick="checkUpdates()">Search for updates</button>'
   /* No link to the changelog here. It pointed at a file in the repository, so
      it broke the moment that file moved -- and the check below already lists
      every version between this one and the one on offer, which is the thing
      somebody wanted the link for. */
   +'</div>'
   +'<div id="upd-result" style="margin-top:14px"></div>'
   +'<div class="proc-row" style="margin-top:16px"><label>Check automatically at start</label>'
   +'<label class="switch"><input id="upd-auto" type="checkbox" onchange="setAutoCheck(this.checked)"><span class="slider"></span></label></div>'
   +'<div class="proc-hint">Off by default. TrackImage opens no connection of its own \u2014 with this on, it asks GitHub once per start whether <b>the channel selected above</b> carries a newer version, and nothing else. The other channel is never looked at.</div>'
   +'<div class="proc-hint" style="margin-top:10px">An update downloads that version straight from the repository, checks the archive, copies the database — without the thumbnail cache, which is redrawn from your pictures — to <b>Trackimage_files/Userdata/Backup</b>, and then restarts into the new version \u2014 a window shows what it is doing while TrackImage is closed. Your pictures, database, settings and the tagging model stay where they are. If the swap fails at any point the previous version is put back.</div>'
   +'</div>';
}

async function setUpdateChannel(name){
  if(_updChannel===name)return;
  var prev=_updChannel;
  _updChannel=name;
  _redrawChannel();
  var out=document.getElementById('upd-result');if(out)out.innerHTML='';
  _updLast=null;
  var r={};
  try{r=await api('/api/update/channel',{method:'POST',body:JSON.stringify({channel:name})});}
  catch(e){r={error:String(e)};}
  if(r.error){_updChannel=prev;_redrawChannel();showToast('Could not switch channel','error');return;}
  /* No 'success' for the beta channel: the only toast styles are the default
     and a green one, and green is the wrong thing to say about a channel whose
     point is that nobody has tried the version yet. */
  showToast(name==='latest'?'Following the main branch — beta, bugs included':'Following stable versions',
            name==='latest'?'':'success');
  checkUpdates();
}

function _redrawChannel(){
  var row=document.getElementById('upd-ch-row');if(row)row.innerHTML=channelBtns();
  var h=document.getElementById('upd-ch-hint');if(h)h.innerHTML=channelHintHtml();
}

function _updFmtMB(n){return (n/1048576).toFixed(1)+' MB';}

/* Everything between the installed version and the one on offer -- one block
   per version, the way the changelog lists it. An update that skips five
   versions should say what all five brought, not only the newest. Falls back to
   whatever the channel gave as notes when the history could not be read. */
function changesHtml(r){
  var ch=r.changes||[];
  if(!ch.length)return esc(r.notes||'').replace(/\n/g,'<br>');
  var h='';
  if(ch.length>1)h+='<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">'+ch.length+' versions since v'+esc(r.current)+'</div>';
  ch.forEach(function(v){
    h+='<div style="margin-bottom:10px"><div style="font-family:\'Space Mono\',monospace;font-size:12px;color:var(--accent-light)">v'+esc(v.version)+(v.date?(' \u00b7 '+esc(v.date)):'')+'</div>';
    if(v.lines&&v.lines.length){
      h+='<ul style="margin:4px 0 0;padding-left:18px">';
      v.lines.forEach(function(l){h+='<li style="margin:2px 0">'+esc(l)+'</li>';});
      h+='</ul>';
    }
    h+='</div>';
  });
  return h;
}

async function checkUpdates(){
  var btn=document.getElementById('upd-btn'),out=document.getElementById('upd-result');
  if(!out)return;
  if(btn){btn.disabled=true;btn.textContent='Checking\u2026';}
  var r={};
  try{r=await api('/api/update/check');}catch(e){r={error:String(e)};}
  if(btn){btn.disabled=false;btn.textContent='Search for updates';}
  _updLast=r;
  if(r.error||!r.ok){
    out.innerHTML='<div class="proc-hint" style="color:var(--danger)">'+esc(r.error||'The check failed.')+'</div>';
    return;
  }
  if(!r.newer){
    out.innerHTML='<div class="proc-hint" style="color:var(--success)">\u2713 v'+esc(r.current)+' \u2014 nothing newer on '+(r.channel==='latest'?('the '+esc(r.branch||'main')+' branch'):'the stable channel')+'.</div>';
    return;
  }
  var notes=changesHtml(r);
  out.innerHTML='<div class="proc-how"><div class="sec-title">'+esc(r.name||('v'+r.latest))
   +(r.published?(' \u00b7 '+esc(r.published)):'')+'</div><div class="proc-how-body">'
   +'<p style="margin:0 0 8px"><b>v'+esc(r.latest)+'</b> is available \u2014 you have v'+esc(r.current)+'.</p>'
   +(notes?('<div style="font-size:13px;line-height:1.7;color:var(--text-secondary);max-height:220px;overflow:auto">'+notes+'</div>'):'')
   +'</div></div>'
   +(r.warn?('<div class="proc-hint" style="color:var(--warning)">'+esc(r.warn)+'</div>')
           :('<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">'
             +'<button class="btn btn-sm btn-primary" onclick="installUpdate()">Download &amp; install'+(r.asset_size?(' \u2014 '+esc(_updFmtMB(r.asset_size))):'')+'</button>'
             +'<a class="btn btn-sm" href="'+esc(r.page)+'" target="_blank" rel="noopener">Open on GitHub</a></div>'
             /* Where this comes from, said plainly rather than left for the
                user to wonder about. */
             +'<div class="proc-hint below-buttons">Taken from '+(r.channel==='latest'?('the <b>'+esc(r.branch||'main')+'</b> branch'+(r.sha?(' at '+esc(r.sha)):'')):('the <b>'+esc(r.tag||('v'+r.latest))+'</b> release'))+' \u2014 the repository\u2019s own folders, the same ones TrackImage runs from. GitHub packs that archive on request, so its size is only known once the download starts.</div>'))
   +'<div id="upd-prog" style="margin-top:12px"></div>';
}

async function installUpdate(){
  if(!_updLast||!_updLast.asset_url)return;
  if(!confirm('TrackImage will download v'+_updLast.latest+', back up the database and restart.\n\n'
              +'Anything still importing or tagging is interrupted. Continue?'))return;
  var r={};
  try{r=await api('/api/update/install',{method:'POST',body:JSON.stringify(_updLast)});}
  catch(e){r={error:String(e)};}
  if(r.error){
    var p=document.getElementById('upd-prog');
    if(p)p.innerHTML='<div class="proc-hint" style="color:var(--danger)">'+esc(r.error)+'</div>';
    return;
  }
  pollUpdate();
}

function pollUpdate(){
  clearInterval(_updTimer);
  _updTimer=setInterval(async function(){
    var st={};
    try{st=await api('/api/update/status');}catch(e){return;}
    S._updPhase=st.phase;updateWorkSpinner();refreshSetNav();
    /* Leaving the page must not stop the watch: the indicator is driven from
       here, and an interval cleared because a div went away would leave it
       turning for ever. It stops when the update does, not when the user looks
       somewhere else. */
    if(!updBusy())clearInterval(_updTimer);
    var p=document.getElementById('upd-prog');
    if(!p)return;
    if(st.phase==='failed'){
      p.innerHTML='<div class="proc-hint" style="color:var(--danger)">'+esc(st.error||'The update failed.')
        +'<br>Nothing was changed \u2014 the installation is untouched.</div>';
      return;
    }
    var label={downloading:'Downloading',verifying:'Checking the archive',
               'backing-up':'Backing up the database',staging:'Unpacking',
               ready:'Restarting'}[st.phase]||st.phase;
    p.innerHTML='<div class="proc-phase"><div class="proc-phase-label">'+esc(label)
      +(st.detail?(' <span style="font-weight:400;color:var(--text-muted)">'+esc(st.detail)+'</span>'):'')
      +'</div><div class="proc-bar"><div class="proc-bar-fill" style="width:'+(st.pct||0)+'%"></div></div></div>';
  },700);
}

async function setAutoCheck(on){
  try{await api('/api/update/auto',{method:'POST',body:JSON.stringify({enabled:!!on})});}catch(e){}
}

async function loadAutoCheck(){
  try{
    var r=await api('/api/update/auto');
    var el=document.getElementById('upd-auto');
    if(el)el.checked=!!r.enabled;
  }catch(e){}
  /* The card is drawn before this runs, so it starts on the default and is
     corrected here rather than guessing. */
  try{
    var c=await api('/api/update/channel');
    if(c&&c.channel&&c.channel!==_updChannel){_updChannel=c.channel;_redrawChannel();}
  }catch(e){}
}

/* ---- Shortcuts ------------------------------------------------------------ */

var _rebindFor=null;

function shortcutRowsHtml(){
  return KEY_ACTIONS.map(function(a){
    var cur=keyFor(a[0]),isDef=(cur===a[2]);
    return '<tr><td style="padding:6px 10px 6px 0;color:var(--text-secondary)">'+esc(a[1])
      +'<div style="font-size:11px;color:var(--text-muted)">'+esc(a[3])+'</div></td>'
      +'<td style="padding:6px 0;white-space:nowrap">'
      +'<button class="btn btn-sm" id="kb-'+a[0]+'" onclick="startRebind(\''+a[0]+'\')" '
      +'style="font-family:\'Space Mono\',monospace;min-width:104px'+(isDef?'':';color:var(--accent-light)')+'">'
      +esc(keyLabel(cur))+'</button></td></tr>';
  }).join('');
}

function shortcutCardHtml(){
  return '<div class="settings-card"><h3>Keyboard</h3>'
   +'<p>Click a key to change it, then press the combination you want. Esc cancels, Backspace puts the default back.</p>'
   +'<table style="width:100%;border-collapse:collapse;font-size:13px" id="kb-table"><tbody>'+shortcutRowsHtml()+'</tbody></table>'
   +'<div id="kb-note" class="proc-hint"></div>'
   +'<div style="margin-top:10px"><button class="btn btn-sm" onclick="resetKeymap()">Reset all to defaults</button></div>'
   +'<div class="proc-how" style="margin-top:16px"><div class="sec-title">Fixed keys</div><div class="proc-how-body">'
   +'<table style="width:100%;border-collapse:collapse;font-size:13px"><tbody>'
   +KEY_FIXED.map(function(f){return '<tr><td style="padding:4px 14px 4px 0;font-family:\'Space Mono\',monospace;color:var(--accent-light);white-space:nowrap">'
       +esc(f[0])+'</td><td style="padding:4px 0;color:var(--text-secondary)">'+esc(f[1])+'</td></tr>';}).join('')
   +'</tbody></table>'
   +'<div style="margin-top:10px;font-size:12px;color:var(--text-muted)">These cannot be changed. Escape is the way out of every state in the app, and the digits are ten keys that would have to move together \u2014 rebinding either is a way to lock yourself out.</div>'
   +'</div></div></div>';
}

function _kbNote(msg,bad){
  var n=document.getElementById('kb-note');
  if(n)n.innerHTML=msg?('<span style="color:var('+(bad?'--danger':'--success')+')">'+esc(msg)+'</span>'):'';
}

function startRebind(action){
  if(_rebindFor)return;
  _rebindFor=action;
  var b=document.getElementById('kb-'+action);
  if(b){b.textContent='Press a key\u2026';b.classList.add('btn-primary');}
  _kbNote('');
  document.addEventListener('keydown',_rebindCapture,true);
}

function _rebindCapture(e){
  if(!_rebindFor)return;
  if(e.key==='Control'||e.key==='Meta'||e.key==='Shift'||e.key==='Alt')return;
  e.preventDefault();e.stopPropagation();
  var action=_rebindFor;
  document.removeEventListener('keydown',_rebindCapture,true);
  _rebindFor=null;

  if(e.key==='Escape'){refreshShortcutRows();return;}
  if(e.key==='Backspace'){delete TI_KEYMAP[action];saveKeymap();refreshShortcutRows();
    _kbNote('Default restored.');return;}

  var chord=keyChord(e);
  if(!chord){refreshShortcutRows();return;}
  /* v4.57: Escape and the digits stay reachable no matter what is bound. */
  if(/^(ctrl\+)?(alt\+)?(shift\+)?[0-9]$/.test(chord)){
    refreshShortcutRows();_kbNote('The digits are the rating keys and cannot be reassigned.',true);return;}
  for(var i=0;i<KEY_ACTIONS.length;i++){
    var other=KEY_ACTIONS[i][0];
    if(other!==action&&keyFor(other)===chord){
      refreshShortcutRows();
      _kbNote(keyLabel(chord)+' is already used for "'+KEY_ACTIONS[i][1]+'".',true);
      return;
    }
  }
  TI_KEYMAP[action]=chord;
  saveKeymap();
  refreshShortcutRows();
  _kbNote(keyLabel(chord)+' saved.');
}

function refreshShortcutRows(){
  var t=document.getElementById('kb-table');
  if(t)t.querySelector('tbody').innerHTML=shortcutRowsHtml();
}

async function saveKeymap(){
  try{await api('/api/keymap',{method:'POST',body:JSON.stringify({keymap:TI_KEYMAP})});}catch(e){}
}

async function resetKeymap(){
  TI_KEYMAP={};
  try{await api('/api/keymap',{method:'POST',body:JSON.stringify({keymap:null})});}catch(e){}
  refreshShortcutRows();
  _kbNote('All shortcuts are back to their defaults.');
}

async function loadKeymap(){
  try{var r=await api('/api/keymap');TI_KEYMAP=(r&&r.keymap)||{};}catch(e){TI_KEYMAP={};}
}

/* v4.57: one look at GitHub per start, and only when the user asked for it in
   Repair & Update. It never interrupts -- a find is a toast, not a dialog. */
async function maybeAutoCheckUpdate(){
  var conf={};
  try{conf=await api('/api/update/auto');}catch(e){return;}
  if(!conf.enabled||!conf.configured)return;
  var r={};
  try{r=await api('/api/update/check');}catch(e){return;}
  /* The check follows the channel this installation is set to, and so does
     this. Saying which one it was is the difference between "a version exists"
     and "a version exists on the channel you chose" -- and it keeps the card
     from opening on the wrong one, since the page starts out assuming Stable
     until the server says otherwise. */
  if(r&&r.channel&&r.channel!==_updChannel){_updChannel=r.channel;_redrawChannel();}
  if(r&&r.ok&&r.newer){
    _updLast=r;
    showToast('TrackImage v'+r.latest+' is available on '
      +(r.channel==='latest'?'Latest (Beta)':'Stable')
      +' \u2014 Settings \u203a Repair & Update','success');
  }
}

