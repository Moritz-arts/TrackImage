/* Talking to Python, and the loaders that fill S with what comes back.
 *
 * File 03 of 13 — the page loads these in number order.
 */

function _lsSave(k,o){try{localStorage.setItem(k,JSON.stringify(o));}catch(e){}}

async function api(u,o){o=o||{};var resp=await fetch(u,Object.assign({headers:{'Content-Type':'application/json'}},o));
/* v4.35: a refusal is a refusal, whichever request met it. The heartbeat used to
   be the only thing that noticed, so an expired session could go on being shown
   a stale page until the next tick came round. */
if(resp.status===401&&typeof netLock==='function'&&_netW&&_netW.remote){netLock('The session has ended. Enter the PIN again to continue.');return {error:'locked'};}
var j=await resp.json();if(!resp.ok)j.error=j.error||'Request failed';return j;}

function pushHistory(p){if(!S._skipPush)history.pushState({page:p},'',p==='gallery'?'/':'/'+p);}

async function init(){await loadKeymap();try{var _as=await api('/api/autosync');S.autosync=!(_as&&_as.on===false);}catch(e){S.autosync=true;}try{S._tag=await api('/api/tag-settings');}catch(e){}S.scanFolders=await api('/api/scan-folders');S.initialized=true;if(S.scanFolders.length){await Promise.all([loadStats(),loadCharacters(),loadFolders(),loadImagesReset()]);}var p=location.pathname.replace(/^\//,'')||'gallery';navigate(['gallery','settings','duplicates'].indexOf(p)>=0?p:'gallery');connectSSE();registerTab();refreshProcStatus();_hookDupPaste();updateWatcherIndicator();var _sp=document.getElementById('ti-splash');if(_sp)_sp.remove();maybeAutoCheckUpdate();}

var _tabId=Math.random().toString(36).slice(2)+Date.now().toString(36);

function registerTab(){api('/api/tab-open',{method:'POST',body:JSON.stringify({tab_id:_tabId})});window.addEventListener('beforeunload',function(){var blob=new Blob([JSON.stringify({tab_id:_tabId})],{type:'application/json'});navigator.sendBeacon('/api/tab-close',blob);});}

var _sse=null,_sseRetry=null;

function connectSSE(){if(_sse){_sse.close();}_sse=new EventSource('/api/events');_sse.addEventListener('sync',function(e){var d=JSON.parse(e.data);onAutoSync(d);});_sse.addEventListener('watcher_status',function(e){var d=JSON.parse(e.data);S.watcherActive=d.active;updateWatcherIndicator();});_sse.addEventListener('proc_progress',function(e){try{var d=JSON.parse(e.data);S._proc=d;if(S.page==='settings'){updateSettingsProc(d);refreshSetNav();}updateGalleryProgress();updateWorkSpinner();}catch(_){}});_sse.addEventListener('processed',function(e){try{onImageProcessed(JSON.parse(e.data));}catch(_){}});_sse.addEventListener('unlink_done',function(e){try{onUnlinkDone(JSON.parse(e.data));}catch(_){}});_sse.addEventListener('drag_handover',function(e){try{onDragHandover(JSON.parse(e.data));}catch(_){}});_sse.addEventListener('tag_progress',function(e){try{var d=JSON.parse(e.data);S._tag=Object.assign(S._tag||{},d);if(S.page==='settings')updateTagCard(d);updateTagInstallLine(d);updateWorkSpinner();}catch(_){}});_sse.onerror=function(){S.watcherActive=false;updateWatcherIndicator();if(_sseRetry)clearTimeout(_sseRetry);_sseRetry=setTimeout(connectSSE,5000);};}

var _syncDebounce=null;

function onAutoSync(d){if(_syncDebounce)clearTimeout(_syncDebounce);_syncDebounce=setTimeout(async function(){if(S.page==='detail')return;var _own=(S.page==='gallery');await Promise.all([loadStats(),loadCharacters(),loadFolders()].concat(_own?[loadImagesRefresh()]:[]));if(_own)renderMainSoft();renderTagList();renderFolderSidebar();if(d.new>0||d.removed>0||d.modified>0){var parts=[];if(d.new)parts.push(d.new+' new');if(d.removed)parts.push(d.removed+' removed');if(d.modified)parts.push(d.modified+' updated');showToast('Auto-sync: '+parts.join(', '),'success');}},10000);}

async function onImageProcessed(d){if(!d||!d.id)return;if(S.page!=='detail'||S.currentImageId!==d.id)return;try{var row=await api('/api/image/'+d.id);if(row&&!row.error){var idx=S.images.findIndex(function(i){return i.id===d.id;});if(idx>=0){S.images[idx].width=row.width;S.images[idx].height=row.height;}loadMetadata(d.id);}}catch(_){}}

async function loadCharacters(){var p=new URLSearchParams();folderParams(p);if(S.filter.search)p.set('search',S.filter.search);var qs=p.toString();S.characters=await api('/api/characters'+(qs?'?'+qs:''));if(S.tagMode==='tags'){try{S.tags=await api('/api/tags'+(qs?'?'+qs:''));}catch(e){S.tags=[];}}}

async function loadImagesRefresh(){
    var have=S.images.length;
    if(have<=60)return loadImagesReset();
    var _ep=S.navEpoch||0;
    var want=Math.ceil(have/60)*60;
    var p=new URLSearchParams();
    S.filter.characters.forEach(function(c){p.append('character',c);});
    S.filter.ratings.forEach(function(r){p.append('rating',r);});
    (S.filter.tags||[]).forEach(function(t){p.append('tag',t);});
    folderParams(p);
    if(S.filter.search)p.set('search',S.filter.search);
    p.set('sort',S.sort);p.set('order',S.order);p.set('page',1);p.set('per_page',want);
    var d;try{d=await api('/api/images?'+p);}catch(e){return;}
    if(_ep!==(S.navEpoch||0)||!d||!d.images)return;
    S.images=d.images;S.total=d.total;S.filteredTotal=d.total;
    S.allLoaded=d.images.length>=d.total;
    invalidateIndexMap();
}

async function loadImagesPreserve(){
    // Like loadImagesReset, but reloads as many pages as were already loaded
    // (instead of falling back to page 1), so the grid height — and thus the
    // saved scroll position — is preserved after rename/move/etc.
    var want=Math.max(S.images.length,60);
    var pages=Math.ceil(want/60);
    S.images=[];S.allLoaded=false;S.selectedImages.clear();invalidateIndexMap();
    var seen=new Set();var total=0;
    for(var pg=1;pg<=pages;pg++){
        var p=new URLSearchParams();
        S.filter.characters.forEach(function(c){p.append('character',c);});S.filter.ratings.forEach(function(r){p.append('rating',r);});(S.filter.tags||[]).forEach(function(t){p.append('tag',t);});
        folderParams(p);
        if(S.filter.search)p.set('search',S.filter.search);
        p.set('sort',S.sort);p.set('order',S.order);p.set('page',pg);p.set('per_page',60);
        var d=await api('/api/images?'+p);
        total=d.total;
        d.images.forEach(function(img){if(!seen.has(img.id)){seen.add(img.id);S.images.push(img);}});
        if(!d.images.length||S.images.length>=d.total)break;
    }
    S.total=total;S.filteredTotal=total;S.allLoaded=S.images.length>=total;
}
