/* Small helpers with no opinion about the rest of the app.
 *
 * File 02 of 13 — the page loads these in number order.
 */

function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML.replace(/"/g,'&quot;');}

function showToast(m,t,undoable){var e=document.getElementById('toast');e.textContent=m+(undoable?' (Ctrl+Z to undo)':'');e.className='toast show'+(t?' '+t:'');setTimeout(function(){e.classList.remove('show');},undoable?5000:3000);}

function refreshBtnClick(){if(S.autosync){rescan();return;}var fs=selFolders();if(!fs.length){showToast('Open a folder to refresh it (autosync is off)');return;}var done=0,checked=0;fs.forEach(function(f){api('/api/refresh-folder',{method:'POST',body:JSON.stringify({folder:f})}).then(function(r){done++;if(r&&r.ok)checked+=(r.checked||0);else return showToast('Error: '+((r&&r.error)||'refresh failed'));if(done===fs.length)showToast('Refreshing '+(fs.length>1?fs.length+' folders':'\u201c'+folderLeaf(fs[0])+'\u201d')+' \u2014 '+checked+' files checked\u2026','success');});});}

function ndPress(e,imgId){primeLocalPaths([imgId]);}

function toggleDetailLibrary(){
  S.detailLibCollapsed=!S.detailLibCollapsed;
  try{localStorage.setItem('ti_detail_lib',S.detailLibCollapsed?'1':'0');}catch(e){}
  var ov=document.getElementById('detail-overlay');
  if(ov)ov.classList.toggle('lib-collapsed',S.detailLibCollapsed);
}

/* The library beside an open picture is also the way back out of it. Choosing a
   folder, a name, a tag or a rating there means "show me those", so the picture
   steps aside and the gallery it just filtered comes forward -- filtering a
   view that is covered by a photograph is not something anyone asked for.
   Folding a branch of the tree open is not a choice of that kind and leaves the
   picture where it is. */
function detailExitToGallery(){
  if(S.page!=='detail')return false;
  var from=S._returnPage||'gallery';
  var ov=document.getElementById('detail-overlay');if(ov)ov.remove();
  S._returnPage=null;S.page='gallery';
  updateNav();pushHistory('gallery');
  if(from!=='gallery')render();   /* underneath lies the page it was opened from */
  if(S.tagsModified){S.tagsModified=false;loadCharacters().then(renderTagList);}
  return true;
}

function toggleDetailBare(){
  S.detailBare=!S.detailBare;
  
  var ov=document.getElementById('detail-overlay');
  if(ov)ov.classList.toggle('bare',S.detailBare);
  showToast(S.detailBare?'Just the picture \u2014 F brings the panels back'
                        :'Panels are back','success');
}

function updateFolderActive(){document.querySelectorAll('.tree-toggle').forEach(function(el){var idx=el.dataset.fidx;if(idx!==undefined){var fp=_folderPaths[parseInt(idx)];el.classList.toggle('active',selFolders().indexOf(fp)>=0);}});}

function isPhone(){return window.matchMedia('(max-width:820px)').matches;}

function toggleDrawer(){
var d=drawerEl();if(!d)return;
if(d.classList.contains('open'))closeDrawer();else openDrawer();
}

function openDrawer(){
var d=drawerEl();if(!d)return;
d.classList.add('open');scrimEl().classList.add('on');
}

function closeDrawer(){
var d=drawerEl();if(d)d.classList.remove('open');
var sc=document.getElementById('drawer-scrim');if(sc)sc.classList.remove('on');
}

function closeDrawerAfterPick(){if(isPhone())closeDrawer();}

function orphanBlock(o){
if(!o||!o.checked||!o.count)return '';
return '<div style="margin-top:14px;padding:10px 12px;border:1px solid var(--warning,#c9a227);border-radius:var(--radius);background:rgba(201,162,39,.08)">'
+'<b>'+_etaNum(o.count)+' image rows point outside every linked folder.</b>'
+'<div class="proc-hint" style="margin:6px 0 8px">Nothing has been deleted. This is normal right after a folder was unlinked, and it also happens when a folder is linked under a different spelling than the one its images were imported with \u2014 a mapped drive letter versus the network path it points at. If these images should still be in your library, re-link that folder rather than cleaning up. Removing the rows never touches a file on disk, but the images have to be scanned again.</div>'
+'<button class="btn btn-sm btn-warning" onclick="onOrphanCleanup(event)">Remove '+_etaNum(o.count)+' rows</button></div>';
}

async function onOrphanCleanup(ev){
var b=ev&&ev.target;
if(!confirm('Remove these image rows from the database?\n\nNo file on disk is touched. Re-linking the folder imports them again.'))return;
if(b){b.disabled=true;b.textContent='Removing\u2026';}
try{var r=await api('/api/orphans/cleanup',{method:'POST',body:'{}'});
showToast(r.removed?('Removed '+_etaNum(r.removed)+' rows'):'Nothing to remove');
loadStats();navigate('settings');}
catch(e){showToast('Cleanup failed');if(b){b.disabled=false;b.textContent='Remove rows';}}
}

function _etaNum(n){try{return Number(n).toLocaleString();}catch(e){return ''+n;}}

function _etaDur(s){s=Math.max(0,Math.round(s));if(s<60)return s+'s';if(s<3600)return Math.round(s/60)+' min';var h=Math.floor(s/3600),m=Math.round((s%3600)/60);return m?h+' h '+m+' min':h+' h';}

function etaText(d){
if(!d)return '';
var bits=[];
if(d.done!=null&&d.total)bits.push(_etaNum(d.done)+' / '+_etaNum(d.total));
if(d.rate>0)bits.push(d.rate.toFixed(1)+'/s');
if(d.eta>0)bits.push('~'+_etaDur(d.eta)+' left');
return bits.length?' \u00b7 '+bits.join(' \u00b7 '):'';
}

function qaRename(){var n=S.selectedImages.size;if(!n)return qaHint();if(n===1)renameFromCtx(qaSel()[0]);else bulkRenameSelected();}

function qaMeta(){var n=S.selectedImages.size;if(!n)return qaHint();if(n===1)removeMetadataSingle(qaSel()[0]);else bulkRemoveMetadata();}

function qaDelete(){var n=S.selectedImages.size;if(!n)return qaHint();if(n===1)deleteSingleFromCtx(qaSel()[0]);else bulkDeleteSelected();}

function qaDup(tagMode){if(S.selectedImages.size!==1)return showToast('Select exactly one image');if(tagMode)findSimilarTags(qaSel()[0]);else findSimilar(qaSel()[0]);}

function qaPaste(){if(!S.clipboard||!S.clipboard.ids.length)return showToast('Clipboard is empty');var t=curFolder();if(!t)return showToast('Open a single folder to paste into');pasteIntoFolder(t);}

function qaBtn(icon,title,fn,need,cls){var dis=(need==='sel'&&!S.selectedImages.size)||(need==='one'&&S.selectedImages.size!==1)||(need==='clip'&&!(S.clipboard&&S.clipboard.ids.length));
return '<button class="qa-btn'+(cls?' '+cls:'')+(dis?' disabled':'')+'" data-need="'+need+'" data-fn="'+fn+'" title="'+title+'" onclick="'+(dis?'qaHint()':fn)+'">'+icon+'</button>';}

function qaToolbar(){return '<div class="qa-bar" id="qa-bar">'
+qaBtn(ICO.explorer,'Open in Explorer','bulkOpenExplorer()','sel')
+qaBtn(ICO.move,'Move to folder...','showMoveModal()','sel')
+'<span class="qa-sep"></span>'
+qaBtn(ICO.copy,'Copy \u2014 file goes to the system clipboard too','copyToClipboard()','sel')+qaBtn(ICO.osimg,'Copy as picture (paste into an image editor)','copyImageToOS()','sel')
+qaBtn(ICO.cut,'Cut','cutToClipboard()','sel')
+qaBtn(ICO.paste,'Paste into the open folder','qaPaste()','clip')
+'<span class="qa-sep"></span>'
+qaBtn(ICO.rename,'Rename','qaRename()','sel')
+qaBtn(ICO.tags,'Edit tags','editTagsSelected()','sel')
+qaBtn(ICO.meta,'Remove metadata','qaMeta()','sel','gold')
+qaBtn(ICO.dup,'Find Duplicates (pixel-based)','qaDup(0)','one')
+'<span class="qa-sep"></span>'
+qaBtn(ICO.trash,'Delete','qaDelete()','sel','danger')
+'</div>';}

function updateQaState(){var n=S.selectedImages.size,clip=!!(S.clipboard&&S.clipboard.ids.length);
document.querySelectorAll('.qa-btn').forEach(function(b){var need=b.dataset.need;
var dis=(need==='sel'&&!n)||(need==='one'&&n!==1)||(need==='clip'&&!clip);
b.classList.toggle('disabled',dis);
b.setAttribute('onclick',dis?'qaHint()':b.dataset.fn);});}

async function toggleInclSub(v){S.inclSub=!!v;localStorage.setItem('ti_incl_sub',S.inclSub?'1':'0');
document.querySelectorAll('.incl-sub-cb').forEach(function(c){c.checked=S.inclSub;});
document.querySelectorAll('.tb-check').forEach(function(l){l.classList.toggle('on',S.inclSub);});
if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedFolder=null;S._dupCachedChars=null;render();return;}
await Promise.all([loadCharacters(),loadImagesReset()]);renderMain();renderTagList();}

function renderTopbar(){var isDup=S.page==='duplicates';
var _sub='<label class="tb-check'+(S.inclSub?' on':'')+'" title="Include subfolders - when off, only files directly inside the selected folder are listed"><input type="checkbox" class="incl-sub-cb" '+(S.inclSub?'checked':'')+' onchange="toggleInclSub(this.checked)"/><span>Subfolders</span></label>';
// v3.82: the tile-size slider lives in the top bar on the duplicates page too
// (same markup, same position as in the gallery) instead of in the filter row.
var _gs='<span class="grid-slider" title="Images per row"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg><input type="range" min="1" max="15" step="1" value="'+S.cols+'" oninput="setGridCols(this.value)"><span class="grid-slider-val">'+S.cols+'</span></span>';
return '<div class="topbar"><button id="drawer-btn" onclick="toggleDrawer()" title="Folders and tags" aria-label="Folders and tags"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M3 6h18M3 12h18M3 18h18"/></svg></button><div class="logo" onclick="navigate(\'gallery\')"><span class="logo-icon">◈</span><span class="logo-text">TrackImage</span></div><div id="watcher-dot" class="watcher-dot'+(S.autosync?' active':' off')+'" title="Autosync"></div><div class="search-box"><svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg><input type="text" id="search-input" placeholder="Search tags, characters, folders, filenames..." value="'+esc(S.pendingSearch||'')+'" oninput="onSearch(this.value)" onkeydown="if(event.key===\'Enter\')commitSearch()"/><button class="search-clear'+((S.searchChips.length||S.pendingSearch)?' visible':'')+'" id="search-clear" onclick="clearSearch()" title="Clear search">✕</button></div>'+(isDup?'<div class="sort-controls"><button class="sort-btn" onclick="refreshBtnClick()" title="Refresh (autosync off: only the opened folder + subfolders)" '+(S.loading?'disabled':'')+'>↻</button>'+_gs+'<button class="sort-btn'+(S.info.visible?' active':'')+'" id="info-btn" onclick="toggleInfoVisible()" title="Show/hide tile info (i)">i</button>'+_sub+'</div>':'<div class="sort-controls"><button class="sort-btn '+(S.sort==='newest'?'active':'')+'" data-sort="newest" onclick="setSort(\'newest\')">'+(S.sort==='newest'?(S.order==='desc'?'Newest':'Oldest'):'Newest')+'</button><button class="sort-btn '+(S.sort==='folder'?'active':'')+'" data-sort="folder" onclick="setSort(\'folder\')">Folder</button><button class="sort-btn '+(S.sort==='filename'?'active':'')+'" data-sort="filename" onclick="setSort(\'filename\')">'+(S.sort==='filename'?(S.order==='asc'?'A–Z':'Z–A'):'A–Z')+'</button><button class="sort-btn" onclick="refreshBtnClick()" title="Refresh (autosync off: only the opened folder + subfolders)" '+(S.loading?'disabled':'')+'>↻</button>'+_gs+'<button class="sort-btn'+(S.info.visible?' active':'')+'" id="info-btn" onclick="toggleInfoVisible()" title="Show/hide tile info (i)">i</button>'+_sub+'</div>')+'<div class="selection-info" id="sel-info" style="display:none"><span class="sel-count">0</span></div><div class="clipboard-info" id="cb-info" style="display:none"><span class="cb-chip" id="cb-chip"></span></div><div class="qa-wrap"><span class="work-spin" id="work-spin" title="TrackImage is working in the background\u2026"></span>'+qaToolbar()+'</div><div class="nav-links"><button class="nav-link'+(isDup?' active':'')+'" data-page="duplicates" onclick="gotoMatches()" title="Find duplicate or similar images"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="vertical-align:-1px;margin-right:5px"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg><span class="nav-long">Find </span>Duplicates</button><button class="nav-link'+(S.page==='settings'?' active':'')+'" onclick="toggleSettings()" title="Settings">\u2699</button></div></div>';}

function librarySidebarHtml(allCount){
  return '<div class="sidebar">'
    +'<div class="sidebar-col-wrap folders-wrap'+(S.foldersCollapsed?' collapsed':'')+'" id="folders-wrap">'
    +'<div class="col-collapsed-bar" onclick="toggleSidebarCol(\'folders\')" title="Expand"><span>\u25B6</span><span class="cc-label">Folders</span></div>'
    +'<div class="sidebar-col folders-col" id="folders-col"><div class="sidebar-title"><span>Folders</span>'
    +'<span class="sel-count-folders" style="display:none;font-family:\'Space Mono\',monospace;font-size:10px;color:var(--accent-light)"></span>'
    +'<span class="col-collapse-btn" onclick="toggleSidebarCol(\'folders\')" title="Collapse">\u25C0</span></div>'
    +renderFolderNode(buildFolderTree(),0)
    +'<div class="link-folder-btn" onclick="pickAndAddFolder()">Link new folder</div></div>'
    +'<div class="col-resizer" onmousedown="startResize(event,\'folder\')"></div></div>'
    +'<div class="sidebar-col-wrap tags-wrap'+(S.tagsCollapsed?' collapsed':'')+'" id="tags-wrap">'
    +'<div class="col-collapsed-bar" onclick="toggleSidebarCol(\'tags\')" title="Expand"><span>\u25B6</span><span class="cc-label">Tags</span></div>'
    +'<div class="sidebar-col tags-col" id="tags-col">'+tagColInner(allCount)+'</div>'
    +'<div class="col-resizer" onmousedown="startResize(event,\'tag\')"></div></div></div>';
}

function _fmtBytes(b){b=b||0;if(b>=1073741824)return (b/1073741824).toFixed(1)+' GB';if(b>=1048576)return (b/1048576).toFixed(0)+' MB';if(b>=1024)return (b/1024).toFixed(0)+' KB';return Math.round(b)+' B';}

function _tsCurHtml(b,n){return 'Current cache: <strong>'+_fmtBytes(b||0)+'</strong> · '+(n||0).toLocaleString()+' thumbnails'+(n?' · ~'+_fmtBytes((b||0)/n)+' each':'');}

function _qf(q){var t=[[60,.22],[65,.25],[70,.28],[75,.32],[80,.38],[85,.45],[90,.55],[95,.7],[100,1]];for(var i=0;i<t.length;i++){if(q<=t[i][0])return t[i][1];}return 1;}

function recalcThumbEst(){var e=document.getElementById('ts-est');if(!e)return;var c=window._tsCur||{};var a=document.getElementById('ts-sz'),b=document.getElementById('ts-q');if(!a||!b||!c.total||!c.sz){e.textContent='';return;}var sz=parseInt(a.value),q=parseInt(b.value);if(sz===c.sz&&q===c.q){e.textContent='';return;}var est=c.total*Math.pow(sz/c.sz,2)*(_qf(q)/_qf(c.q));e.textContent='Estimated after apply: ≈ '+_fmtBytes(est);}

function _vacLine(v,busy){var el=document.getElementById('db-vac');if(!el)return;
if(busy){el.innerHTML='<b style=\"color:var(--accent-light)\">Compacting the database\u2026 this can take a moment.</b><br>';return;}
if(v&&v.error){el.innerHTML='<b style=\"color:var(--danger)\">Compaction failed: '+esc(v.error)+'</b><br>';return;}
if(v&&v.after){var f=(v.before||0)-(v.after||0);el.innerHTML='<b style=\"color:var(--success)\">'+_fmtBytes(v.before||0)+' \u2192 '+_fmtBytes(v.after||0)+(f>0?' \u00b7 '+_fmtBytes(f)+' freed':' \u00b7 nothing to reclaim')+'</b><br>';return;}
el.innerHTML='';}

function pollVacuum(){if(window._vacPoll)clearInterval(window._vacPoll);
var btn=document.getElementById('db-vac-btn');if(btn){btn.disabled=true;btn.textContent='Compacting\u2026';}
window._vacPoll=setInterval(async function(){var d;try{d=await api('/api/db-info');}catch(e){return;}
var v=d.vacuum||{},busy=!!(v.running||d.thumb_regen);
var sz=document.getElementById('db-size');if(sz)sz.textContent=_fmtBytes(d.db_bytes||0);
_vacLine(v,busy);
if(!busy){clearInterval(window._vacPoll);window._vacPoll=null;
var b=document.getElementById('db-vac-btn');if(b){b.disabled=false;b.textContent='Compact database';}}},1000);}

async function onVacuum(){try{var r=await api('/api/db-vacuum',{method:'POST'});if(r&&r.error){showToast(r.error);return;}pollVacuum();}catch(e){showToast('Compaction could not be started');}}

async function applyThumbSettings(ev){var btn=ev&&ev.target;var sz=parseInt(document.getElementById('ts-sz').value),q=parseInt(document.getElementById('ts-q').value);if(btn){btn.disabled=true;btn.textContent='Regenerating…';}try{await api('/api/thumb-settings',{method:'POST',body:JSON.stringify({max_size:sz,quality:q})});}catch(e){}if(window._thumbPoll)clearInterval(window._thumbPoll);window._thumbPoll=setInterval(async function(){var st;try{st=await api('/api/thumb-settings');}catch(e){return;}var est=document.getElementById('ts-est');if(st.regenerating){if(est)est.textContent='Regenerating thumbnails… '+(st.regen_done||0).toLocaleString()+' / '+(st.regen_total||0).toLocaleString();var cur=document.getElementById('ts-cur');if(cur)cur.innerHTML=_tsCurHtml(st.total_bytes,st.count);}else{clearInterval(window._thumbPoll);window._thumbPoll=null;window._tsCur={total:st.total_bytes||0,count:st.count||0,sz:st.max_size,q:st.quality};var cur2=document.getElementById('ts-cur');if(cur2)cur2.innerHTML=_tsCurHtml(st.total_bytes,st.count);if(est)est.textContent='Done · regenerated to '+_fmtBytes(st.total_bytes||0);var t=Date.now();document.querySelectorAll('img').forEach(function(im){var s=im.getAttribute('src')||'';if(s.indexOf('/thumb/')>=0){var b=s.split(/[?&]v=/)[0];im.src=b+(b.indexOf('?')>=0?'&':'?')+'v='+t;}});if(btn){btn.disabled=false;btn.textContent='Apply & regenerate';}pollVacuum();}},1000);}

async function onNasProtection(v){var r=await api('/api/nas-protection',{method:'POST',body:JSON.stringify({enabled:!!v})});if(r&&r.ok){showToast('NAS protection '+(v?'enabled':'disabled')+' \u2014 restart TrackImage to apply','success');}else{showToast('Could not save setting');}}

async function onPower(){var s=document.getElementById('pw-slider');if(!s)return;var mx=parseInt(s.max);  /* v4.16: the scale ends at the real maximum */var v=parseInt(s.value);var n=(v>mx)?0:v;try{var r=await api('/api/processing-power',{method:'POST',body:JSON.stringify({n:n})});showToast('Processing power: '+wLabel(n||r.effective||mx),'success',true);if(S.page==='settings')render();}catch(e){showToast('Could not change processing power','error');}}

async function onTwWorkers(){var s=document.getElementById('tw-procs');if(!s)return;var mx=parseInt(s.max);  /* v4.16: the scale ends at the real maximum */var v=parseInt(s.value);var n=(v>mx)?0:v;try{var r=await api('/api/thumb-workers',{method:'POST',body:JSON.stringify({n:n})});S._thumbCfg=r.n;showToast('Thumbnail workers: '+(n?n:wLabel(r.effective)),'success',true);}catch(e){showToast('Could not change thumbnail workers','error');}}

async function onWtWorkers(){var s=document.getElementById('wt-procs');if(!s)return;var mx=parseInt(s.max);  /* v4.16: the scale ends at the real maximum */var v=parseInt(s.value);var n=(v>mx)?0:v;try{var r=await api('/api/processing/settings',{method:'POST',body:JSON.stringify({workers:n})});S._proc=r;updateSettingsProc(r);showToast('Worker threads: '+wLabel(n||mx),'success',true);}catch(e){showToast('Could not change worker threads','error');}}

async function onMpWorkers(){var s=document.getElementById('mp-procs');if(!s)return;var mx=parseInt(s.max);  /* v4.16: the scale ends at the real maximum */var v=parseInt(s.value);var n=(v>mx)?0:v;var r=await api('/api/mp-workers',{method:'POST',body:JSON.stringify({n:n})});if(r&&r.error)return showToast('Error: '+r.error);var e=document.getElementById('mp-procs-val');if(e)e.textContent=wLabel(r.procs);showToast('Compute processes: '+wLabel(r.procs),'success',true);}

function uiModeCardHtml(){
    var inWin=WINDOW_MODE;
    return '<div class="settings-card"><h3>Where TrackImage runs</h3>'+
      '<p>Currently in <b>'+(inWin?'its own window':'a browser tab')+'</b>.'+
      (!inWin&&SERVER_WINDOW?' The app window is open as well \u2014 this tab is a second view of the same program.':'')+'</p>'+
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0">'+
      '<button class="btn btn-sm'+(inWin?'':' btn-primary')+'" onclick="setUiMode(\'window\')"'+(inWin?' disabled':'')+'>Use its own window</button>'+
      '<button class="btn btn-sm'+(inWin?' btn-primary':'')+'" onclick="setUiMode(\'browser\')"'+(inWin?'':' disabled')+'>Use a browser tab</button>'+
      '</div>'+
      '<div class="proc-how"><div class="sec-title">What changes</div><div class="proc-how-body">'+
      '<p><b>Own window</b> \u2014 dragging a file out works into any program. The window '+
      'carries the TrackImage icon. Closing it shuts the program down.</p>'+
      '<p><b>Browser tab</b> \u2014 dragging out hands over the real file in Chrome and Edge only; '+
      'Firefox gets the address instead. No TrackImage icon on the window. Whichever tab you '+
      'leave open keeps the program alive.</p>'+
      '<p style="color:var(--text-muted)">Either way the library, the database and every setting '+
      'stay exactly as they are \u2014 only the window around it changes.</p>'+
      '</div></div></div>';
}

async function setUiMode(mode){
    var toBrowser=(mode==='browser');
    var q=toBrowser
      ? 'Move TrackImage into a browser tab? Dragging files out will then only hand over the real file in Chrome and Edge \u2014 Firefox gets the address instead.'
      : 'Move TrackImage into its own window? It has to restart for that; this tab can be closed afterwards.';
    if(!await showConfirm(q,[{label:'Cancel',key:'cancel'},{label:toBrowser?'Use a browser tab':'Use its own window',key:'ok'}]))return;
    try{
        var r=await api('/api/ui-mode',{method:'POST',body:JSON.stringify({mode:mode})});
        if(r&&r.error)return showToast(r.error,'error');
        showToast((r&&r.note)||'Done','success');
    }catch(e){showToast('Could not switch','error');}
}

async function onNetEnabled(v){
if(v&&!confirm('Open TrackImage to your local network?\\n\\nEvery device on the network will be able to reach it, and anyone who knows the password can delete files from this computer.\\n\\nOnly do this on a network you trust.')){render();return;}
var r=await api('/api/network',{method:'POST',body:JSON.stringify({enabled:!!v})});
if(r&&r.ok){showToast('Network sharing '+(v?'enabled':'disabled')+' \u2014 restart TrackImage to apply','success');render();}
else showToast((r&&r.error)||'Could not save');
}

async function onNetPassword(ev){
var el=document.getElementById('net-pw');if(!el)return;
var pw=(el.value||'').trim();
if(pw.length<4){showToast('At least four characters');el.focus();return;}
var r=await api('/api/network',{method:'POST',body:JSON.stringify({password:pw})});
if(r&&r.ok){showToast('Password saved \u2014 other devices have to sign in again','success');render();}
else showToast((r&&r.error)||'Could not save');
}

function copyNetUrl(){
var el=document.getElementById('net-url');if(!el)return;
var t=el.textContent||'';
if(navigator.clipboard&&navigator.clipboard.writeText){
  navigator.clipboard.writeText(t).then(function(){showToast('Address copied','success');})
   .catch(function(){fallbackCopy(t);showToast('Address copied','success');});
}else{fallbackCopy(t);showToast('Address copied','success');}
}

async function onNetLogoutAll(){
var r=await api('/api/network/logout-all',{method:'POST',body:'{}'});
if(r&&r.ok){showToast('Signed out '+r.signed_out+' device(s)','success');render();}
}

function renderSetup(){return '<div class="setup-screen"><div class="setup-card"><h2>◈ TrackImage</h2><p>Add a folder containing your images to get started.</p><button class="btn btn-primary" onclick="pickAndAddFolder()" style="width:100%;padding:12px">Choose folder & scan</button></div></div>';}

function sortQueryMatches(a){var m=S.dupSort||'size',o=(a||[]).slice();
if(m==='similarity_desc')o.sort(function(x,y){return (y.similarity||0)-(x.similarity||0);});
else if(m==='similarity_asc')o.sort(function(x,y){return (x.similarity||0)-(y.similarity||0);});
else o.sort(function(x,y){return (y.file_size||0)-(x.file_size||0);});
return o;}

function requeryDup(mode){
var q=S._dupQuery;if(!q)return;
S.dupGroups=null;S._collapsedGroups=new Set();
if(q.imgId){q.mode=mode;q.allMatches=null;render();return;}
if(q.file){dupScanBlob(q.file,mode);return;}
S._dupQuery=null;render();}

function startHashPoll(){
clearInterval(_hashPollTimer);
var _ep=S.navEpoch||0;
_hashPollTimer=setInterval(async function(){
var hs=await api('/api/hash-status');
/* v3.93: clearInterval does not cancel a request that is already in flight. Without this check its callback would run on to render() after the user has already left for the gallery, wiping a page that is loading. */
if(_ep!==(S.navEpoch||0)||S.page!=='duplicates'){clearInterval(_hashPollTimer);return;}
var txt=document.getElementById('hash-progress-text');
var bar=document.getElementById('hash-progress-bar');
if(txt){var label=hs.phase==='comparing'?'Comparing images... ':'Hashing images... ';txt.textContent=label+(hs.hashing?hs.hash_current+' / '+hs.hash_total:hs.hashed+' / '+hs.total);}
if(bar){var pct=hs.hashing?(hs.hash_total?hs.hash_current/hs.hash_total*100:0):(hs.total?hs.hashed/hs.total*100:0);bar.style.width=pct+'%';}
if(!hs.hashing){clearInterval(_hashPollTimer);S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedSort=null;render();}
},2000);
}

function startDupComputePoll(){
clearInterval(_dupComputeTimer);
var _ep=S.navEpoch||0;
_dupComputeTimer=setInterval(async function(){
var threshold=S.simMode?(S.simMatch||70):_dupThr();
var sort=S.dupSort||'size';
var d=await api(dupApiUrl(threshold,sort,'',true));
/* v3.93: clearInterval does not cancel a request that is already in flight. Without this check its callback would run on to render() after the user has already left for the gallery, wiping a page that is loading. */
if(_ep!==(S.navEpoch||0)||S.page!=='duplicates'){clearInterval(_dupComputeTimer);return;}
var txt=document.getElementById('dup-compute-text');
var bar=document.getElementById('dup-compute-bar');
if(d.computing){
if(txt)txt.textContent=(d.phase==='processing'?('Processing '+d.pending+' images first… '+d.progress+'%'+etaText(d)):('Comparing images... '+d.progress+'%'+etaText(d)));
if(bar)bar.style.width=d.progress+'%';
}else{
clearInterval(_dupComputeTimer);
S.dupGroups=d.groups;S._dupCachedMode=dupModeKey();S._dupCachedThreshold=threshold;S._dupCachedSort=sort;
render();
}
},800);
}

function renderDupGroups(groups){
var h='';
if(!groups.length)return '<div style="padding:40px;text-align:center;color:var(--text-muted)">No '+(S.simMode?'similar images':'duplicates')+' found at this threshold.</div>';
groups.forEach(function(group,gi){
var imgs=group.images||group;var sim=group.similarity!=null?group.similarity:null;
var collapsed=S._collapsedGroups&&S._collapsedGroups.has(gi);
h+='<div class="dup-group"><div class="dup-group-title" onclick="toggleDupGroup('+gi+')" style="cursor:pointer;user-select:none">';
h+='<span style="display:inline-block;width:16px;flex:none;transition:transform .2s;transform:rotate('+(collapsed?'-90deg':'0')+')">\u25BE</span>';
h+='<span class="dgt-label">Group '+(gi+1)+' \u2014 '+imgs.length+' images'+(sim!=null?' <span style="color:var(--accent);font-weight:600;margin-left:6px">'+sim+'% similar</span>':'')+'</span><span class="dgt-actions">'+(S.dupShowIgnored?'<button class="btn btn-sm" onclick="event.stopPropagation();dupIgnoreGroup('+gi+',false)" title="Offer this group as a duplicate again">Restore</button>':'<button class="btn btn-sm" onclick="event.stopPropagation();dupIgnoreGroup('+gi+',true)" title="Wanted variants \u2014 stop showing this group">Ignore</button>')+'</span>'+'</div>';
h+='<div class="gallery dup-grid'+(S.thumbMode==='ratio'?' justified':'')+(S.info.visible?'':' no-info')+'" style="'+(collapsed?'display:none':'')+'">';
// v3.83: the badges are scored GROUP-WISE (see dupGroupStats). The heatmap is
// pairwise by construction, so it still needs one reference image -- that is the
// only thing _best is used for now.
var _best=null,_bestPx=-1;
imgs.forEach(function(im){var px=(im.width||0)*(im.height||0);if(px>_bestPx){_bestPx=px;_best=im;}});
var _gst=dupGroupStats(imgs);
imgs.forEach(function(img){
var sel=S.selectedImages.has(img.id)?' selected':'';
h+='<div class="gallery-item'+sel+'" data-id="'+img.id+'" data-group="'+gi+'" data-w="'+(img.width||0)+'" data-h="'+(img.height||0)+'" oncontextmenu="showGalleryCtx(event,'+img.id+')" onclick="dupCardClick(event,'+img.id+','+gi+')" '+DRAGGABLE_ATTR+' ondragstart="onGalleryDragStart(event,'+img.id+')" onmousedown="ndPress(event,'+img.id+')" ondragend="onGalleryDragEnd()">';
h+='<div class="img-wrap"'+wrapStyle(img)+'>'+cardMediaHtml(img)
 +'</div>'+dupCardInfo(img,_gst)+'</div>';
});
h+='</div></div>';});
/* v3.83: every caller writes this string straight into the DOM, so one rAF here
   covers all of them -- justified rows need measuring after the paint. */
requestAnimationFrame(function(){layoutJustified();});
return h;
}

function fmtBytes(n){
if(!n)return '';
if(n<1024)return n+' B';
if(n<1048576)return (n/1024).toFixed(0)+' KB';
return (n/1048576).toFixed(n<10485760?1:0)+' MB';
}

function toggleDupGroup(gi){
if(!S._collapsedGroups)S._collapsedGroups=new Set();
if(S._collapsedGroups.has(gi))S._collapsedGroups.delete(gi);else S._collapsedGroups.add(gi);
var dr=document.getElementById('dup-results');
if(dr&&S.dupGroups){dr.innerHTML=renderDupGroups(S.dupGroups);}
}

function toggleDupVerify(on){S.dupVerify=!!on;localStorage.setItem('ti_dup_verify',on?'1':'0');
if(S._dupQuery&&S.page==='duplicates')return requeryDup(S._dupQuery.mode);   /* v4.33 */
S.dupGroups=null;S._dupCachedMode=null;swapDupMain();}

function onDupSlider(val){
val=parseInt(val);S._collapsedGroups=new Set();
var _tagCtx=(S._dupQuery?S._dupQuery.mode==='tags':S.simMode);
if(_tagCtx){S.simMatch=val;localStorage.setItem('ti_sim_match',String(val));}else S.dupThreshold=val;
var el=document.getElementById('dup-threshold-val');if(el)el.textContent=val+'%';
var _sb=document.getElementById('dup-smart-btn');if(_sb)_sb.style.opacity=(val===0?'':'.5');
if(S._dupQuery){var _qm=sortQueryMatches((S._dupQuery.allMatches||[]).filter(function(m){return m.similarity>=(_tagCtx?val:100-val);}));S.dupGroups=[{images:_qm,similarity:null}];var _r=document.getElementById('dup-results');if(_r)_r.innerHTML=renderDupGroups(S.dupGroups);var _st=document.getElementById('dup-stats');if(_st)_st.textContent=dupQueryStats(_qm.length,_tagCtx,(S._lastHashed||0));return;}
clearTimeout(_dupSliderTimer);clearInterval(_dupComputeTimer);
var r=document.getElementById('dup-results');if(r)r.innerHTML='<div class="dup-loading"><div class="spinner"></div>Filtering duplicates...</div>';
_dupSliderTimer=setTimeout(async function(){
var myseq=++_dupReqSeq;
var threshold=S.simMode?(S.simMatch||70):_dupThr();
var sort=S.dupSort||'size';
var dupFolder=folderKey();
var d=await api(dupApiUrl(threshold,sort,dupFolder,true));
if(myseq!==_dupReqSeq)return;
if(d.computing){startDupComputePoll();return;}
S.dupGroups=d.groups;S._dupCachedMode=dupModeKey();S._dupCachedThreshold=threshold;S._dupCachedSort=sort;S._dupCachedFolder=dupFolder;S._dupCachedChars=S.filter.ratings.join(',')+'|'+S.filter.characters.join('|');S._dupCachedSearch=S.filter.search;S.selectedImages.clear();updateSelectionBar();
var r2=document.getElementById('dup-results');if(r2)r2.innerHTML=renderDupGroups(d.groups);
var st=document.getElementById('dup-stats');if(st)st.textContent=d.total_groups+' group'+(d.total_groups!==1?'s':'')+' \u00b7 '+d.total_duplicates+' images \u00b7 '+d.hashed+(S.simMode?' tagged':' hashed');
},300);
}

async function setDupSort(mode){
S.dupSort=mode;
/* v4.33: a single-image scan is one flat list already in memory -- reorder it,
   do not ask the server for it again. */
if(S._dupQuery&&S.page==='duplicates'){render();return;}
S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedSort=null;S._dupCachedFolder=null;swapDupMain();
}

function clearDupQuery(){S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;render();}

function _hookDupPaste(){if(window._dupPasteHooked)return;window._dupPasteHooked=true;document.addEventListener('paste',function(e){if(S.page!=='duplicates')return;var items=(e.clipboardData&&e.clipboardData.items)||[];for(var i=0;i<items.length;i++){if(items[i].type&&items[i].type.indexOf('image')>=0){var blob=items[i].getAsFile();if(blob){e.preventDefault();dupScanBlob(blob);return;}}}});}

function gotoMatches(){if(S.page==='duplicates'){navigate('gallery');return;}gotoDup(!!S.simMode,true);}

async function swapDupMain(){var full=await renderDuplicates();var i=full.indexOf('<div class="main"');var m=document.getElementById('main-area');if(i<0||!m){render();return;}m.outerHTML=full.slice(i,full.lastIndexOf('</div>'));}

function gotoDup(sim,force){if(!force&&S.page==='duplicates'&&!!S.simMode===sim)return;
/* v4.33: a scan already on screen survives the switch between pixel and tag
   matching. It used to be thrown away, so changing mode meant dropping the
   file in a second time. */
if(!force&&S._dupQuery&&S.page==='duplicates'){S.simMode=sim;return requeryDup(sim?'tags':undefined);}
S.simMode=sim;S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedSort=null;S._dupCachedFolder=null;S._dupCachedChars=null;S._dupCachedSearch=null;S._dupCachedMode=null;S._collapsedGroups=new Set();if(S.page==='duplicates'){swapDupMain();}else navigate('duplicates');}

function updateDupSelectionUI(){
updateQaState();
document.querySelectorAll('#dup-results .gallery-item[data-id]').forEach(function(el){el.classList.toggle('selected',S.selectedImages.has(parseInt(el.dataset.id)));});
updateSelectionBar();
}

function openDupImage(id,groupIdx){
if(!S.dupGroups||!S.dupGroups[groupIdx])return;
var group=S.dupGroups[groupIdx].images||S.dupGroups[groupIdx];
S.images=group.map(function(img){return {id:img.id,filename:img.filename,folder:img.folder,filepath:img.filepath,fphash:'',is_video:false,characters:[]};});
S.allLoaded=true;
S.currentImageIndex=S.images.findIndex(function(i){return i.id===id;});
S.currentImageId=id;S.page='detail';S._returnPage='duplicates';S.tagsModified=false;
pushHistory('detail');showDetailOverlay();
}

var _searchAC=null;

function hookSearchAC(){var inp=document.querySelector('.search-box input');if(!inp||inp._acAttached)return;inp._acAttached=true;attachAutocomplete(inp,{mode:'search',fetchItems:async function(q){var r=await api('/api/suggest?q='+encodeURIComponent(q));return Array.isArray(r)?r:[];},onPick:function(name,i){var inp=document.getElementById('search-input');if(i&&i.type==='folder'){if(inp)inp.value='';S.pendingSearch='';if(selFolders().indexOf(i.value)<0)filterByFolder(i.value);return;}if(inp)inp.value=(i&&i.value)||name;commitSearch();}});}

function syncViewportVars(){
  var vv=window.visualViewport,h=window.innerHeight,w=window.innerWidth;
  if(vv&&vv.height&&Math.abs((vv.scale||1)-1)<0.02){h=vv.height;w=vv.width;}
  if(!(h>80)||!(w>80))return;
  var st=document.documentElement.style;
  st.setProperty('--app-h',Math.round(h)+'px');
  st.setProperty('--app-w',Math.round(w)+'px');
}

/* ---- Keyboard -------------------------------------------------------------
   v4.57: every global shortcut resolves through here, so a binding can be
   changed in Settings without touching the handler that acts on it.

   Escape and the digits are deliberately absent. Escape is the way out of
   every state in the app and the digits are ten keys that would have to move
   together -- rebinding either is a way to lock yourself out. */
var KEY_ACTIONS=[
 ['undo',   'Undo the last move, delete or paste', 'ctrl+z',    'Everywhere'],
 ['copy',   'Copy the original file to the clipboard','ctrl+c', 'Gallery \u00b7 Full view'],
 ['cut',    'Cut the selected files',              'ctrl+x',    'Gallery'],
 ['paste',  'Paste into the open folder',          'ctrl+v',    'Gallery'],
 ['info',   'Show or hide the info panel',         'i',         'Gallery \u00b7 Full view'],
 ['bare',   'Whole-screen view',                   'f',         'Full view'],
 ['library','Fold the folder and tag columns away','l',         'Full view'],
 ['prev',   'Previous image',                      'ArrowLeft', 'Full view'],
 ['next',   'Next image',                          'ArrowRight','Full view'],
 ['del',    'Delete',                              'Delete',    'Gallery \u00b7 Full view']
];

var KEY_FIXED=[
 ['Escape','Leave the full view, drop a selection, close Settings'],
 ['0 \u2013 9','Rate the current or selected images; 0 clears the rating'],
 ['\u2191 \u2193','Walk the folder or tag column once it has focus'],
 ['Enter','Open the highlighted entry in a column, or commit a search chip'],
 ['\u2190 \u2192','Fold a folder open or shut while the column has focus']
];

function keyDefault(a){for(var i=0;i<KEY_ACTIONS.length;i++)if(KEY_ACTIONS[i][0]===a)return KEY_ACTIONS[i][2];return '';}

function keyFor(a){return (TI_KEYMAP&&TI_KEYMAP[a])||keyDefault(a);}

/* A pressed key as the one string the rest of the app compares against.
   Returns '' for a bare modifier, which is not a shortcut on its own. */
function keyChord(e){var k=e.key;
if(!k||k==='Control'||k==='Meta'||k==='Shift'||k==='Alt')return '';
if(k.length===1)k=k.toLowerCase();
var p='';
if(e.ctrlKey||e.metaKey)p+='ctrl+';   /* Cmd and Ctrl are the same shortcut */
if(e.altKey)p+='alt+';
if(e.shiftKey)p+='shift+';
return p+k;}

function keyAction(e){var c=keyChord(e);if(!c)return '';
for(var i=0;i<KEY_ACTIONS.length;i++)if(keyFor(KEY_ACTIONS[i][0])===c)return KEY_ACTIONS[i][0];
return '';}

/* 'ctrl+z' -> 'Ctrl + Z', 'ArrowLeft' -> '<-'. Display only. */
function keyLabel(c){if(!c)return '\u2014';
var NICE={arrowleft:'\u2190',arrowright:'\u2192',arrowup:'\u2191',arrowdown:'\u2193',
          delete:'Del',escape:'Esc',' ':'Space',ctrl:'Ctrl',alt:'Alt',shift:'Shift'};
return String(c).split('+').map(function(part){
  var low=part.toLowerCase();
  if(NICE[low])return NICE[low];
  return part.length===1?part.toUpperCase():part;
}).join(' + ');}

/* A typed character belongs in the field, not to a shortcut. */
function inTextField(){var a=document.activeElement;
return !!(a&&(a.tagName==='INPUT'||a.tagName==='TEXTAREA'||a.isContentEditable));}
