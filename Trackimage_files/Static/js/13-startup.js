/* Everything that runs. Last on purpose: by here the rest exists.
 *
 * File 13 of 13 — the page loads these in number order.
 */

document.addEventListener('keydown',function(e){if(e.key==='Control'||e.key==='Meta')_impCtrlHeld=true;},true);

document.addEventListener('keyup',function(e){if(e.key==='Control'||e.key==='Meta')_impCtrlHeld=false;},true);

window.addEventListener('blur',function(){_impCtrlHeld=false;});

['dragover','drop'].forEach(function(name){
  window.addEventListener(name,function(e){
    if(_impOurOwn())return;
    if(_impDropGuardTarget(e))return;
    e.preventDefault();
  },true);
});

window.addEventListener('dragend',function(){_impReset();},true);

window.addEventListener('blur',function(){_impReset();});

document.addEventListener('keydown',function(e){
  if(e.key==='Escape'&&_impDepth)_impReset();
},true);

document.addEventListener('dragenter',function(e){
  if(!_impFilesInEvent(e))return;
  if(_impOurOwn())return;
  if(S.page!=='gallery'||!S.initialized)return;
  if(e.target&&e.target.closest&&e.target.closest('#dup-dropzone'))return;
  _impDepth++;_impAlive();e.preventDefault();_impVeil(true,_impPrompt());
});

document.addEventListener('dragover',function(e){
  if(!_impFilesInEvent(e))return;
  if(_impOurOwn())return;
  if(S.page!=='gallery'||!S.initialized)return;
  if(e.target&&e.target.closest&&e.target.closest('#dup-dropzone'))return;
  _impAlive();
  e.preventDefault();if(e.dataTransfer)e.dataTransfer.dropEffect='copy';
});

document.addEventListener('dragleave',function(){
  _impDepth=Math.max(0,_impDepth-1);
  if(!_impDepth)_impReset();
});

document.addEventListener('drop',function(e){
  var hasFiles=_impFilesInEvent(e),hasLink=_impLinkInEvent(e);
  if(!hasFiles&&!hasLink){_impReset();return;}
  if(_impOurOwn()){_impReset();return;}
  if(S.page!=='gallery'||!S.initialized){_impReset();return;}
  if(e.target&&e.target.closest&&e.target.closest('#dup-dropzone')){_impReset();return;}
  e.preventDefault();
  _impDepth=0;
  if(_impWatch){clearInterval(_impWatch);_impWatch=null;}
  /* v4.41: Ctrl held at the moment of the drop means COPY, the way it does
     everywhere else in Windows. Without it the original is moved. Read now --
     the event is gone by the time the promised files arrive. */
  var copyMode=!!(e.ctrlKey||e.metaKey);
  _impCollectFiles(e.dataTransfer).then(function(files){
    if(!files.length){
      _impVeil(false);
      showToast('That picture came over as a link, not a file — save it first, '
        +'then drag it in','error');
      return;
    }
    /* v4.40: these may be OUR files coming home -- a drag that was handed to
       Windows and then let go over TrackImage's own window. Importing them
       would write a copy of each original next to itself. */
    if(_cdHandedRecently(60000)&&_cdOwnFiles(files)){_impVeil(false);return;}
    window._impCopyMode=copyMode;
    var t=_impTarget();
    if(t)return importFilesTo(t,files);
    _impChooseFolder(files);
  }).catch(function(){
    _impVeil(false);showToast('That drop could not be read','error');
  });
});

window.addEventListener('popstate',function(e){var pg=e.state?e.state.page:'gallery';S._skipPush=true;if(pg==='gallery'&&S.page==='detail'){closeDetail();pushHistory('gallery');}else navigate(pg);S._skipPush=false;});

document.addEventListener('mousedown',function(e){
    var g=e.target&&e.target.closest?e.target.closest('#con-grip'):null;
    if(!g)return;
    var box=document.getElementById('con-box');if(!box)return;
    e.preventDefault();e.stopPropagation();
    var startY=e.clientY,startH=box.offsetHeight;
    function mv(ev){conApplyHeight(startH+(startY-ev.clientY));}   /* pull up = taller */
    function up(){document.removeEventListener('mousemove',mv,true);
                  document.removeEventListener('mouseup',up,true);
                  document.body.style.cursor='';document.body.style.userSelect='';}
    document.body.style.cursor='ns-resize';document.body.style.userSelect='none';
    document.addEventListener('mousemove',mv,true);
    document.addEventListener('mouseup',up,true);
},true);

document.addEventListener('click',function(e){if(!e.target.closest('.ctx-menu'))hideCtx();});

document.addEventListener('contextmenu',function(e){if(!e.target.closest('.tree-toggle'))hideCtx();});

refreshDraggableAttr();

setInterval(function(){
    fetch('/api/processing/status').then(function(r){return r.json();}).then(function(d){
        S._proc=d;updateWorkSpinner();
        if(S.page==='settings')refreshSetNav();
    }).then(function(){
        return fetch('/api/tag-settings').then(function(r){return r.json();}).then(function(t){
            S._tag=Object.assign(S._tag||{},t);updateWorkSpinner();
            if(S.page==='settings')refreshSetNav();
        }).catch(function(){});
    }).catch(function(){});
},4000);

document.addEventListener('mouseover',function(e){
    if(!WINDOW_MODE||IS_WINDOWS)return;
    var el=e.target&&e.target.closest?e.target.closest('.gallery-item'):null;
    if(el&&el.dataset&&el.dataset.id)primeLocalPaths([parseInt(el.dataset.id)]);
},true);

document.addEventListener('mousedown',function(e){
    var id=_cdStartable(e);if(id===null||isNaN(id))return;
    /* v4.47: clear it first. The note below is spent by the click that follows,
       and a press that ended in a drag never has one -- the stale note was then
       spent by the NEXT click on the same picture, which therefore refused to
       unselect it. */
    _cdPressSelected=0;
    if(!S.selectedImages.has(id)){S.selectedImages.clear();S.selectedImages.add(id);updateSelectionUI();
        /* v4.46: remember that THIS press did the selecting. The click that
           follows is the other half of the same gesture and toggles, so it
           would find the picture selected and clear it again -- which is why a
           single click appeared to select nothing and only Ctrl-click worked
           (the press leaves Ctrl-clicks alone). */
        _cdPressSelected=id;}
    var ids=Array.from(S.selectedImages);
    if(ids.indexOf(id)<0)ids=[id];
    _tiDrag.armed=true;_tiDrag.active=false;_tiDrag.handed=false;_tiDrag.ids=ids;_tiDrag.sx=e.clientX;_tiDrag.sy=e.clientY;
    _tiDrag.names=ids.map(function(i){var im=_cdImg(i);return im&&im.filename?im.filename:'';})
                 .filter(function(n){return !!n;});
    e.preventDefault();   /* no text selection, and no HTML5 drag either */
    /* preventDefault also holds focus where it was, and a search box that keeps
       the caret would swallow every keyboard shortcut after a click. */
    try{var af=document.activeElement;
        if(af&&/^(INPUT|TEXTAREA|SELECT)$/.test(af.tagName))af.blur();}catch(_){}
},true);

document.addEventListener('mousemove',function(e){
    if(!_tiDrag.armed)return;
    var x=e.clientX,y=e.clientY;
    if(!_tiDrag.active){
        if(Math.abs(x-_tiDrag.sx)<6&&Math.abs(y-_tiDrag.sy)<6)return;
        _tiDrag.active=true;_tiDrag.seq++;S.dragIds=_tiDrag.ids.slice();
        document.querySelectorAll('.gallery-item').forEach(function(el){
            if(_tiDrag.ids.indexOf(parseInt(el.dataset.id))>=0)el.classList.add('dragging');});
        _cdGhostMake(x,y);
        /* Arming tells Python which files are in flight and starts the watch for
           the cursor leaving TrackImage. */
        api('/api/drag/arm',{method:'POST',body:JSON.stringify({ids:_tiDrag.ids,seq:_tiDrag.seq})}).catch(function(){});
        _tiDrag.guard=setTimeout(function(){if(_tiDrag.active){_cdDisarm();_cdCleanup();}},45000);
    }
    _cdGhostMove(x,y);
    /* Out of the window is unambiguous, so it hands over here directly instead of
       waiting for the watch in Python to notice. */
    if(x<0||y<0||x>window.innerWidth||y>window.innerHeight){_cdHandOver();return;}
    var el=document.elementFromPoint(x,y);
    var tt=el&&el.closest?el.closest('.tree-toggle'):null;
    var fi=(tt&&tt.dataset&&tt.dataset.fidx!=null)?parseInt(tt.dataset.fidx):-1;
    if(fi!==_tiDrag.fidx){_cdClearHi();if(tt)tt.classList.add('drop-over');_tiDrag.fidx=fi;}
},true);

document.addEventListener('mouseup',function(e){
    if(!_tiDrag.armed)return;
    var wasActive=_tiDrag.active,fi=_tiDrag.fidx,ids=_tiDrag.ids?_tiDrag.ids.slice():[];
    _cdCleanup();
    if(!wasActive)return;
    _cdDisarm();
    if(fi>=0&&_folderPaths[fi]&&ids.length){S.selectedImages=new Set(ids);doMoveToFolder(_folderPaths[fi]);}
},true);

document.addEventListener('keydown',function(e){
    if(e.key==='Escape'&&_tiDrag.active){_cdDisarm();_cdCleanup();}
},true);

document.addEventListener('click',function(e){
    if(e.target.closest('.tag-item')){setSbFocus('tags',e.target.closest('.tag-item'));return;}
    if(e.target.closest('.tree-toggle')){setSbFocus('folders',e.target.closest('.tree-toggle'));return;}
    if(e.target.closest('.main')||e.target.closest('.topbar')){_sbFocus=null;_sbIdx=-1;clearSbHighlight();}
},true);

document.addEventListener('keydown',function(e){
    /* v4.57: what a key means is resolved once, in keyAction (02-util.js), so a
       binding changed in Settings takes effect here without this handler
       knowing anything about which key it was. The guards around each branch
       are unchanged -- they are about context, not about the key. */
    var _act=keyAction(e);
    if(_act==='undo'){e.preventDefault();performUndo();return;}
    if(_act==='copy'&&S.page==='detail'&&S.currentImageId){if(inTextField())return;
    /* v4.30: if the user has selected text, Ctrl+C means that text. This branch
       used to fire unconditionally in the detail view, so highlighting the
       dimensions or the creation date and pressing Ctrl+C put the IMAGE FILE on
       the clipboard instead -- the one thing that was not selected. Only copy
       the file when nothing is selected. */
    if(hasTextSelection())return;
    e.preventDefault();copyFileToOS();return;}
    if(_act==='copy'&&S.page==='gallery'&&S.selectedImages.size){if(inTextField())return;e.preventDefault();copyToClipboard();return;}
    if(_act==='cut'&&S.page==='gallery'&&S.selectedImages.size){if(inTextField())return;e.preventDefault();cutToClipboard();return;}
    if(_act==='paste'&&S.page==='gallery'&&S.clipboard.ids.length){if(inTextField())return;e.preventDefault();pasteAtCurrent();return;}
    if(_act==='info'&&(S.page==='gallery'||S.page==='detail')){
        if(inTextField())return;
        e.preventDefault();
        if(S.page==='detail'){toggleDetailSidebar();return;}
        toggleInfoVisible();return;
    }
    // Quick rating: 0-9 keys
    if(!e.ctrlKey&&!e.metaKey&&!e.altKey&&e.key>='0'&&e.key<='9'){
        if(document.activeElement&&(document.activeElement.tagName==='INPUT'||document.activeElement.tagName==='TEXTAREA'))return;
        var ratingVal=parseInt(e.key);
        if(S.page==='detail'&&S.currentImageId){e.preventDefault();setRating([S.currentImageId],ratingVal);return;}
        if(S.page==='gallery'&&S.selectedImages.size){e.preventDefault();setRating([...S.selectedImages],ratingVal);return;}
    }
    /* v4.53: F is the whole-screen switch \u2014 library and info panel step
       aside, F brings them back. L folds just the library away. */
    if(S.page==='detail'&&!inTextField()){
        if(_act==='bare'){e.preventDefault();toggleDetailBare();return;}
        if(_act==='library'){e.preventDefault();toggleDetailLibrary();return;}
    }
    if(S.page==='detail'){if(e.key==='Escape'){if(document.activeElement&&document.activeElement.tagName==='INPUT'){document.activeElement.blur();return;}closeDetail();return;}if(document.activeElement&&document.activeElement.tagName==='INPUT')return;if(_act==='del'){e.preventDefault();deleteImage(S.currentImageId);return;}if(_act==='prev')prevImage();else if(_act==='next')nextImage();}
    if(S.page==='gallery'){if(document.activeElement&&document.activeElement.tagName==='INPUT')return;if(e.key==='Escape'){if(_sbFocus){_sbFocus=null;_sbIdx=-1;clearSbHighlight();}else if(S.selectedFolders.size){S.selectedFolders.clear();updateFolderSelection();}else if(S.clipboard.ids.length){clearClipboard();}else clearSelection();}if(_act==='del'&&S.selectedImages.size)bulkDeleteSelected();if((e.key==='ArrowUp'||e.key==='ArrowDown')&&_sbFocus){e.preventDefault();sbNavigate(e.key==='ArrowUp'?-1:1);}if(e.key==='Enter'&&_sbFocus){e.preventDefault();sbActivate();}if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&_sbFocus){e.preventDefault();sbLeftRight(e.key==='ArrowRight');}}
    if(S.page==='settings'){if(document.activeElement&&document.activeElement.tagName==='INPUT')return;if(e.key==='Escape')navigate('gallery');}
    if(S.page==='duplicates'){if(e.key==='Escape')navigate('gallery');}
});

window.addEventListener('focus',function(){if(S.page==='detail'){var img=S.images[S.currentImageIndex];var di=document.getElementById('detail-rating');if(img&&di){di.textContent=img.rating?img.rating:'';di.style.color=img.rating?ratingColor(img.rating):'var(--accent-light)';}}});

window.addEventListener('orientationchange',function(){setTimeout(dsArrows,80);});

window.tiGridInfo=tiGridInfo;

window.addEventListener('resize',function(){clearTimeout(_ljTimer);_ljTimer=setTimeout(layoutJustified,120);try{dsArrows();}catch(_e){}});

setInterval(function(){document.querySelectorAll('.gallery').forEach(function(g){if(!g._ljObserved){g._ljObserved=true;_ljRO.observe(g);}});},500);

if(S.uiScale!==100){try{document.documentElement.style.zoom=S.uiScale/100;}catch(_e){}}

window.addEventListener('resize',function(){if(!isPhone())closeDrawer();});

document.addEventListener('click',function(e){if(!S.selectedImages.size)return;if(S.page==='gallery'){if(!e.target.closest('.gallery-item')&&!e.target.closest('.topbar')&&!e.target.closest('.sidebar')&&e.target.closest('.main')){clearSelection();}}if(S.page==='duplicates'){if(!e.target.closest('.gallery-item')&&!e.target.closest('.topbar')&&e.target.closest('.main')){S.selectedImages.clear();updateDupSelectionUI();}}});

(function(){
  syncViewportVars();
  var t=null,go=function(){clearTimeout(t);t=setTimeout(syncViewportVars,40);};
  window.addEventListener('resize',go);
  window.addEventListener('orientationchange',function(){setTimeout(syncViewportVars,120);go();});
  if(window.visualViewport){
    window.visualViewport.addEventListener('resize',go);
    window.visualViewport.addEventListener('scroll',go);
  }
})();

(function(){
  var h=location.hostname||'';
  /* Only a device that came in over the network is watched. The app window and
     a browser tab on the same machine are the server itself -- there is nothing
     to lose contact with. */
  if(h==='localhost'||h==='127.0.0.1'||h==='::1'||h==='trackimage'||h==='')return;
  _netW.remote=true;
  setInterval(netHeartbeat,3000);
  /* Coming back to the app after it sat in a pocket is the moment most likely
     to find the server gone, so that check does not wait for the next tick. */
  document.addEventListener('visibilitychange',function(){if(!document.hidden)netHeartbeat();});
  window.addEventListener('focus',function(){netHeartbeat();});
  window.addEventListener('pageshow',function(){netHeartbeat();});
  setTimeout(netHeartbeat,1200);
})();

document.documentElement.style.setProperty('--gallery-cols',S.cols);

history.replaceState({page:'gallery'},'','/');

init();
