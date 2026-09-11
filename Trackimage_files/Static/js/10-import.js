/* Files dragged in and dragged out.
 *
 * File 10 of 13 — the page loads these in number order.
 */

var _impDepth=0;

function _impOurOwn(){
  if(S.dragIds&&S.dragIds.length)return true;
  return (typeof _cdHandedRecently==='function')&&_cdHandedRecently(8000);
}

var _impCtrlHeld=false;

function _impCopyHeld(){return _impCtrlHeld;}

function _impTypes(e){
  var dt=e.dataTransfer;if(!dt)return [];
  try{return Array.prototype.slice.call(dt.types||[]);}catch(_e){return [];}
}

function _impFilesInEvent(e){
  var t=_impTypes(e);
  return t.indexOf('Files')>=0||t.indexOf('application/x-moz-file')>=0;
}

function _impLinkInEvent(e){
  var t=_impTypes(e);
  return t.indexOf('text/uri-list')>=0||t.indexOf('text/x-moz-url')>=0;
}

var _impSeenAt=0,_impWatch=null;

function _impReset(){
  _impDepth=0;_impVeil(false);
  if(_impWatch){clearInterval(_impWatch);_impWatch=null;}
}

function _impAlive(){
  _impSeenAt=Date.now();
  if(_impWatch)return;
  _impWatch=setInterval(function(){
    if(Date.now()-_impSeenAt>1500)_impReset();
  },500);
}

function _impCollectFiles(dt){
  var plain=[];
  try{plain=Array.prototype.slice.call(dt.files||[]);}catch(_e){}
  var items=[];
  try{items=Array.prototype.slice.call(dt.items||[]);}catch(_e){}
  var wanted=items.filter(function(it){return it&&it.kind==='file';});
  if(!wanted.length||plain.length>=wanted.length)return Promise.resolve(plain);
  var jobs=wanted.map(function(it){
    var direct=null;
    try{direct=it.getAsFile();}catch(_e){}
    if(direct)return Promise.resolve(direct);
    var entry=null;
    try{entry=it.webkitGetAsEntry?it.webkitGetAsEntry():null;}catch(_e){}
    if(!entry||!entry.isFile)return Promise.resolve(null);
    return new Promise(function(resolve){
      var settled=false;
      function once(v){if(settled)return;settled=true;resolve(v);}
      setTimeout(function(){once(null);},8000);
      try{entry.file(function(f){once(f);},function(){once(null);});}
      catch(_e){once(null);}
    });
  });
  return Promise.all(jobs).then(function(list){
    var out=list.filter(function(f){return !!f;});
    return out.length?out:plain;
  });
}

function _impVeil(on,html){
  var v=document.getElementById('import-veil');if(!v)return;
  if(html!==undefined)document.getElementById('iv-card').innerHTML=html;
  v.classList.toggle('on',!!on);
}

function _impTarget(){
  /* One folder open -> that one. Anything else has no obvious answer, and
     guessing would drop files somewhere the user is not looking. */
  var f=(typeof selFolders==='function')?selFolders():[];
  return f.length===1?f[0]:'';
}

function _impPrompt(){
  var t=_impTarget();
  if(t)return '<div class="iv-title">Add to your library</div>'
    +'<div class="iv-where">'+esc(t)+'</div>'
    +'<div class="iv-note">The file is copied into this folder on your PC. '
    +'Nothing already there is replaced.</div>'
    +(NATIVE_DROP?('<div class="iv-note">'+(_impCopyHeld()
        ?'Holding Ctrl \u2014 the originals stay where they are.'
        :'The originals are moved here. Hold Ctrl to copy them instead.')+'</div>'):'');
  return '<div class="iv-title">Add to your library</div>'
    +'<div class="iv-note">Open a single folder first, and dropped files go straight into it. '
    +'Right now more than one folder is showing, so let go and pick where they should land.</div>';
}

function _impDropGuardTarget(e){
  var t=e.target;
  return !!(t&&t.closest&&t.closest('input,textarea,[contenteditable="true"]'));
}

async function _impChooseFolder(files){
  _impVeil(true,'<div class="iv-title">Where should these go?</div>'
    +'<div class="iv-note">Loading folders\u2026</div>');
  var d=null;
  try{d=await api('/api/import-targets');}catch(_e){}
  var list=(d&&d.folders)||[];
  if(!list.length){_impVeil(false);showToast('No folders are linked yet','error');return;}
  window._impPending=files;
  var h='<div class="iv-title">Where should these go?</div>'
    +'<div class="iv-note">'+files.length+' file'+(files.length!==1?'s':'')
    +' \u2014 pick the folder they belong in.</div><div class="iv-pick">';
  list.slice(0,400).forEach(function(f){
    h+='<button onclick="_impPick('+JSON.stringify(f.display).replace(/"/g,'&quot;')+')">'
      +esc(f.display)+'</button>';
  });
  h+='</div><div class="iv-note"><button class="btn btn-sm" onclick="_impCancel()">Cancel</button></div>';
  _impVeil(true,h);
}

function _impPick(display){
  var files=window._impPending||[];window._impPending=null;
  importFilesTo(display,files);
}

function _impCancel(){window._impPending=null;_impVeil(false);}

async function importFilesTo(display,files){
  if(!files||!files.length){_impVeil(false);return;}
  var copyMode=!!window._impCopyMode;window._impCopyMode=false;
  _impVeil(true,'<div class="iv-title">'+(NATIVE_DROP&&!copyMode?'Moving ':'Adding ')+files.length+' file'
    +(files.length!==1?'s':'')+'\u2026</div><div class="iv-where">'+esc(display)+'</div>'
    +'<div class="iv-note"><div class="spinner"></div></div>');
  /* v4.41: ask Python first. It saw the same drop from the Windows side and
     knows where the files actually live, which is the only way to move rather
     than copy them -- the drop event itself never carries a path. If it has no
     answer (a browser tab, a phone, an older pywebview) the upload below runs
     exactly as it always has. */
  if(NATIVE_DROP){
    var nr=null;
    try{
      nr=await api('/api/import/native-drop',{method:'POST',body:JSON.stringify({
        names:files.map(function(f){return f.name;}),folder:display,copy:copyMode})});
    }catch(_e){nr=null;}
    if(nr&&nr.ok){_impFinish(nr,display,copyMode?'copied':'moved');return;}
    if(nr&&nr.error){_impVeil(false);showToast(nr.error,'error');return;}
  }
  var fd=new FormData();
  fd.append('folder',display);
  files.forEach(function(f){fd.append('files',f,f.name);});
  var r=null;
  try{
    var resp=await fetch('/api/import-files',{method:'POST',body:fd});
    r=await resp.json();
  }catch(e){
    _impVeil(false);showToast('Import failed \u2014 '+e,'error');return;
  }
  _impFinish(r,display,'copied');
}

async function _impFinish(r,display,verb){
  _impVeil(false);
  if(r.error){showToast(r.error,'error');return;}
  var added=r.added||[],n=added.length,sk=(r.skipped||[]).length;
  var back=added.filter(function(a){return a.from_library;}).length;
  var msg=n?(n+' file'+(n!==1?'s':'')+' '+verb+' to '+display):'Nothing was added';
  if(back)msg+=' \u2014 '+back+' already in your library, moved rather than added twice';
  var renamed=added.filter(function(a){return a.renamed;}).length;
  if(renamed)msg+=' \u2014 '+renamed+' renamed to avoid replacing a file';
  if(sk)msg+=' \u2014 '+sk+' skipped';
  /* S2: an import that took the original out of its old folder is undoable.
     A copy has nothing to undo -- nothing was disturbed. */
  var undoable=false;
  if(r.undo&&r.undo.length){pushUndo({type:'import_move',entries:r.undo});undoable=true;}
  if(r.relocated&&r.relocated.length){
    r.relocated.forEach(function(m){pushUndo({type:'move',imageId:m.id,oldFolder:m.old_folder});});
    undoable=true;
  }
  showToast(msg,n?'success':'error',undoable);
  if(sk){
    setTimeout(function(){
      var s0=r.skipped[0];
      showToast('Not imported: '+s0.name+' \u2014 '+s0.why
        +(sk>1?(' (+'+(sk-1)+' more)'):''),'error');
    },1200);
  }
  if(r.duplicates&&r.duplicates.length){
    setTimeout(function(){
      var d=r.duplicates[0];
      showToast('Already in your library: '+d.match+' in '+d.folder
        +(r.duplicates.length>1?(' (+'+(r.duplicates.length-1)+' more)'):''),'error');
    },1800);
  }
  if(n){await loadImagesReset();render();}
}

function nativeDragOn(){return false;}

function setNativeDrag(on){}

function nativeDragHint(){
    if(!WINDOW_MODE)return 'In a browser tab the drag already carries the file itself \u2014 this switch only applies to the app window.';
    if(!nativeDragOn())return 'Off: a drag puts the originals on the clipboard, paste them with Ctrl+V.';
    if(IS_WINDOWS&&!NATIVE_DRAG)return 'pywin32 is missing, so the clipboard is used instead. The launcher installs it on the next start.';
    if(!IS_WINDOWS)return 'On: the drag passes the file:// address of the original, which is what a file manager here expects.';
    return 'On: dragging hands the original file straight to the other program.';
}

function useNativeDrag(){return false;}

function customDragOn(){return WINDOW_MODE&&IS_WINDOWS&&NATIVE_DRAG;}

function refreshDraggableAttr(){DRAGGABLE_ATTR=(useNativeDrag()||customDragOn())?'draggable="false"':'draggable="true"';}

var _localPaths={};

function primeLocalPaths(ids){
    if(!WINDOW_MODE||IS_WINDOWS||!ids||!ids.length)return;
    var need=ids.filter(function(i){return !(i in _localPaths);});
    if(!need.length)return;
    api('/api/localpath',{method:'POST',body:JSON.stringify({ids:need})}).then(function(r){
        if(!r||!r.ok||!r.paths)return;
        need.forEach(function(id,ix){if(r.paths[ix])_localPaths[id]=r.paths[ix];});
    }).catch(function(){});
}

function fileUri(p){
    if(!p)return null;
    var parts=String(p).replace(/\\/g,'/').split('/').map(function(seg,ix){
        /* A drive letter is not a name to escape: C: has to stay C:, or the
           address turns into a host called "C%3A" and points nowhere. */
        return (ix===0&&/^[A-Za-z]:$/.test(seg))?seg:encodeURIComponent(seg);
    });
    var joined=parts.join('/');
    if(joined.charAt(0)!=='/')joined='/'+joined;     /* file:/// for an absolute path */
    return 'file://'+joined;
}

var MIME_BY_EXT={jpg:'image/jpeg',jpeg:'image/jpeg',jfif:'image/jpeg',png:'image/png',webp:'image/webp',gif:'image/gif',bmp:'image/bmp',tiff:'image/tiff',tif:'image/tiff',avif:'image/avif',ico:'image/x-icon',svg:'image/svg+xml',mp4:'video/mp4',webm:'video/webm',mov:'video/quicktime',mkv:'video/x-matroska'};

function findImageAnywhere(imgId){
    var id=String(imgId),i,g,j;
    for(i=0;i<(S.images||[]).length;i++){if(String(S.images[i].id)===id)return S.images[i];}
    var gs=S.dupGroups||[];
    for(i=0;i<gs.length;i++){var arr=gs[i].images||gs[i]||[];
        for(j=0;j<arr.length;j++){if(String(arr[j].id)===id)return arr[j];}}
    return null;
}

function fillDragPayload(e,img){
    if(!img||!img.filename)return false;
    var ext=(img.filename.split('.').pop()||'').toLowerCase();
    var mime=MIME_BY_EXT[ext]||'application/octet-stream';
    var url=location.origin+'/file/'+img.id;
    /* v4.13: in the app window on Linux and macOS the webview IS a drag source,
       and what those systems hand a file manager is a file:// address. It points
       at the original on disk, so the drop is the file itself -- same name, same
       bytes -- with no download in between. */
    var local=(WINDOW_MODE&&!IS_WINDOWS)?fileUri(_localPaths[img.id]):null;
    try{e.dataTransfer.setData('DownloadURL',mime+':'+img.filename+':'+url);}catch(_a){}
    try{e.dataTransfer.setData('text/uri-list',local||url);}catch(_b){}
    try{e.dataTransfer.setData('text/html','<img src="'+url+'" alt="'+esc(img.filename)+'">');}catch(_c){}
    try{e.dataTransfer.setData('text/plain',img.filename);}catch(_d){}
    return true;
}

function onGalleryDragStart(e,imgId){
    if(!S.selectedImages.has(imgId)){S.selectedImages.clear();S.selectedImages.add(imgId);updateSelectionUI();}
    S.dragIds=Array.from(S.selectedImages);
    e.dataTransfer.effectAllowed='copyMove';
    /* The internal move between folders reads S.dragIds, never dataTransfer, so
       filling these formats cannot disturb it. */
    var single=S.dragIds.length===1?findImageAnywhere(imgId):null;
    primeLocalPaths(S.dragIds);
    if(single)fillDragPayload(e,single);
    else{try{e.dataTransfer.setData('text/plain',S.dragIds.length+' images');}catch(_e){}}
    /* A drag can carry exactly one file, and the app window cannot be a drag
       source at all. Both cases end at the clipboard, which holds every original. */
    /* v4.13: a native drag carries the whole file list itself, so there is nothing
       left for the clipboard to rescue. Only the cases that still cannot deliver a
       file fall back to it. */
    if(useNativeDrag())return;
    if(WINDOW_MODE||S.dragIds.length>1){
        var n=S.dragIds.length;
        osClipboard(S.dragIds,'file',true).then(function(ok){
            if(!ok)return;
            if(WINDOW_MODE){
                if(_dragHintShown)return;_dragHintShown=true;
                showToast('Dragging out is not possible in the app window \u2014 '+
                    (n>1?'the original files are':'the original file is')+
                    ' on the clipboard, paste with Ctrl+V','success');
            }else{
                showToast('A drag can carry one file only \u2014 all '+n+
                    ' originals are on the clipboard, paste with Ctrl+V','success');
            }
        });
    }
    requestAnimationFrame(function(){document.querySelectorAll('.gallery-item').forEach(function(el){if(S.selectedImages.has(parseInt(el.dataset.id)))el.classList.add('dragging');});});
}

function onGalleryDragEnd(){
    S.dragIds=null;
    document.querySelectorAll('.gallery-item.dragging').forEach(function(el){el.classList.remove('dragging');});
    document.querySelectorAll('.tree-toggle.drop-over').forEach(function(el){el.classList.remove('drop-over');});
}

function onFolderDrop(e,idx){
    e.preventDefault();e.currentTarget.classList.remove('drop-over');
    if(!S.dragIds||!S.dragIds.length)return;
    var fp=_folderPaths[idx];if(!fp)return;
    S.selectedImages=new Set(S.dragIds);
    doMoveToFolder(fp);
}

var _tiDrag={armed:false,active:false,handed:false,handedTs:0,ids:null,names:null,
         sx:0,sy:0,ghost:null,fidx:-1,seq:0,guard:0};

function _cdImg(id){return findImageAnywhere(id);}

function _cdThumb(id){var im=_cdImg(id);return '/thumb/'+id+(im&&im.fphash?('?h='+im.fphash):'');}

function _cdGhostMake(x,y){
    var g=document.createElement('div');g.className='ti-ghost';
    var im=document.createElement('img');im.src=_cdThumb(_tiDrag.ids[0]);im.alt='';g.appendChild(im);
    if(_tiDrag.ids.length>1){var b=document.createElement('span');b.className='ti-ghost-n';
        b.textContent=String(_tiDrag.ids.length);g.appendChild(b);}
    g.style.left=x+'px';g.style.top=y+'px';
    document.body.appendChild(g);_tiDrag.ghost=g;
}

function _cdGhostMove(x,y){if(_tiDrag.ghost){_tiDrag.ghost.style.left=x+'px';_tiDrag.ghost.style.top=y+'px';}}

function _cdClearHi(){document.querySelectorAll('.tree-toggle.drop-over').forEach(function(el){el.classList.remove('drop-over');});}

function _cdCleanup(){
    if(_tiDrag.guard){clearTimeout(_tiDrag.guard);_tiDrag.guard=0;}
    if(_tiDrag.ghost){try{_tiDrag.ghost.remove();}catch(_){}_tiDrag.ghost=null;}
    _cdClearHi();
    document.querySelectorAll('.gallery-item.dragging').forEach(function(el){el.classList.remove('dragging');});
    _tiDrag.armed=false;_tiDrag.active=false;_tiDrag.fidx=-1;S.dragIds=null;
}

function _cdDisarm(){try{api('/api/drag/disarm',{method:'POST',body:JSON.stringify({seq:_tiDrag.seq})});}catch(_){}}

function _cdHandOver(){
    if(!_tiDrag.active||_tiDrag.handed)return;
    _tiDrag.handed=true;_tiDrag.handedTs=Date.now();
    var ids=_tiDrag.ids?_tiDrag.ids.slice():[];
    _cdCleanup();
    api('/api/drag/handover',{method:'POST',body:JSON.stringify({seq:_tiDrag.seq})}).then(function(r){
        if(r&&r.ok)return;
        /* No native drag after all -- say so once and leave the originals on the
           clipboard, which is what v4.39 did for every drag. */
        if(ids.length)osClipboard(ids,'file',true).then(function(ok){
            if(ok)showToast('Dragging out is unavailable \u2014 '+(ids.length>1?'the files are':'the file is')+
                ' on the clipboard, paste with Ctrl+V','success');
        });
    }).catch(function(){});
}

function _cdHandedRecently(ms){return _tiDrag.handedTs&&(Date.now()-_tiDrag.handedTs)<ms;}

function _cdOwnFiles(files){
    if(!_tiDrag.names||!_tiDrag.names.length||!files||!files.length)return false;
    for(var i=0;i<files.length;i++)if(_tiDrag.names.indexOf(files[i].name)<0)return false;
    return true;
}

var _cdPressSelected=0;

function _cdStartable(e){
    if(!customDragOn())return null;
    if(e.button!==0||e.ctrlKey||e.shiftKey||e.altKey||e.metaKey)return null;
    var t=e.target;if(!t||!t.closest)return null;
    if(t.closest('button,input,select,textarea,a,.btn,.add-tag-btn,.ctx-menu'))return null;
    var tile=t.closest('.gallery-item');
    if(tile&&tile.dataset&&tile.dataset.id)return parseInt(tile.dataset.id);
    /* The full view: the picture itself, but not while it is zoomed -- there the
       mouse belongs to panning. A video element is never a drag source. */
    if(t.closest('#detail-img-area')&&t.tagName==='IMG'&&S.detailZoom<=1&&S.currentImageId)
        return S.currentImageId;
    return null;
}

function onDragHandover(d){
    var ids=(_tiDrag.ids||[]).slice();
    _tiDrag.handed=true;_tiDrag.handedTs=Date.now();
    _cdCleanup();
    if(d&&d.ok)return;
    if(ids.length)osClipboard(ids,'file',true).then(function(ok){
        if(ok)showToast('Dragging out is unavailable \u2014 '+(ids.length>1?'the files are':'the file is')+
            ' on the clipboard, paste with Ctrl+V','success');
    });
}

function dupCardInfo(img,st){var inner=cardInfoInner(img)+dupBadges(img,st);if(!inner)return '';return '<div class="card-info">'+inner+'</div>';}

function dupDrop(e){e.preventDefault();e.stopPropagation();var z=document.getElementById('dup-dropzone');if(z)z.style.borderColor='var(--border)';var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f&&f.type.indexOf('image')>=0)dupScanBlob(f);else showToast('Please drop an image file');}

function dupCardClick(e,id,groupIdx){
if(e.detail===2){openDupImage(id,groupIdx);return;}
if(e.ctrlKey||e.metaKey){if(S.selectedImages.has(id))S.selectedImages.delete(id);else S.selectedImages.add(id);}
else{if(S.selectedImages.size===1&&S.selectedImages.has(id)){S.selectedImages.clear();openDupImage(id,groupIdx);return;}
S.selectedImages.clear();S.selectedImages.add(id);}
updateDupSelectionUI();
}
