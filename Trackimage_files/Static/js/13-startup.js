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

/* Losing focus clears a veil nobody is dragging over any more -- but not one
   that belongs to a drag in progress: a drag entering a window that is not in
   front can take the page's focus away with it, and tearing the veil down
   there put the gesture back to looking broken. The watchdog in _impAlive
   removes a stale one a second and a half later anyway. */
window.addEventListener('blur',function(){if(!_impDepth)_impReset();});

document.addEventListener('keydown',function(e){
  if(e.key==='Escape'&&_impDepth)_impReset();
},true);

/* The three below are one gesture, so they answer the same question the same
   way -- see _impRefuse. What they must never do is disagree: dragenter and
   dragover are the only things that make the browser accept a drop, and a page
   state either of them refuses over turns the drop into nothing at all. */
document.addEventListener('dragenter',function(e){
  if(!_impMaybeFiles(e))return;
  if(_impRefuse(e))return;
  _impDepth=1;_impAlive();e.preventDefault();_impVeil(true,_impPrompt());
});

document.addEventListener('dragover',function(e){
  if(!_impMaybeFiles(e))return;
  if(_impRefuse(e))return;
  /* The veil is raised here too, not only on dragenter. A window that was not
     in front when the drag started can miss that first event entirely, and
     then nothing on screen said the drop would be taken -- which is what made
     dropping into an unfocused TrackImage look like it did not work. */
  if(!_impDepth){_impDepth=1;_impVeil(true,_impPrompt());}
  _impAlive();
  e.preventDefault();if(e.dataTransfer)e.dataTransfer.dropEffect='copy';
});

document.addEventListener('dragleave',function(e){
  /* relatedTarget is empty only where the pointer has left the page itself.
     Every other dragleave is one element handing the drag to the next, and
     counting those is why the veil could fall away in the middle of a drag
     over a grid of thumbnails. */
  if(e.relatedTarget)return;
  _impReset();
});

document.addEventListener('drop',function(e){
  var hasFiles=_impFilesInEvent(e),hasLink=_impLinkInEvent(e);
  if(!hasFiles&&!hasLink){_impReset();return;}
  if(_impRefuse(e)){_impReset();return;}
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
    /* A drop is answered wherever it lands. It used to be thrown away unless
       the gallery happened to be the open page, so files dropped while
       Settings, the duplicates list or a picture was open disappeared without
       a word -- and going back to the gallery first looked like "it only works
       when the window is active". */
    if(S.page!=='gallery')navigate('gallery');
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

/* v4.68: the spinner used to keep turning for up to four seconds after the work
   had finished, because that was how long it took to ask again -- and the two
   questions were asked one after the other, so the tag state was a further round
   trip behind that. They go together now, and the rhythm follows the work: brisk
   while something is running, unhurried once nothing is. */
var _WORK_POLL_BUSY=1200, _WORK_POLL_IDLE=5000, _workPollTimer=null;

function pollWork(){
    Promise.all([
        fetch('/api/processing/status').then(function(r){return r.json();}).catch(function(){return null;}),
        fetch('/api/tag-settings').then(function(r){return r.json();}).catch(function(){return null;})
    ]).then(function(r){
        if(r[0])S._proc=r[0];
        if(r[1])S._tag=Object.assign(S._tag||{},r[1]);
        updateWorkSpinner();
        if(S.page==='settings')refreshSetNav();
    }).catch(function(){}).then(function(){
        clearTimeout(_workPollTimer);
        _workPollTimer=setTimeout(pollWork,workBusy()?_WORK_POLL_BUSY:_WORK_POLL_IDLE);
    });
}
/* Not right now: startup already has a queue of its own, and one more pair of
   requests in the middle of it helps nobody. */
_workPollTimer=setTimeout(pollWork,1200);

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
