/* One picture, up close.
 *
 * File 06 of 13 — the page loads these in number order.
 */

function _ratingFilterRefresh(){S.selectedImages.clear();if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedChars=null;render();return;}loadImagesReset().then(function(){renderMain();renderTagList();});}

function openImage(id){var m=document.querySelector('.main');if(m)S.scrollPosition=m.scrollTop;S.currentImageIndex=S.images.findIndex(function(i){return i.id===id;});S.currentImageId=id;S.page='detail';S.tagsModified=false;try{api('/api/image/'+id+'/prioritize',{method:'POST'});}catch(_){}pushHistory('detail');showDetailOverlay();}

function closeDetail(){var ov=document.getElementById('detail-overlay');if(ov)ov.remove();var ret=S._returnPage||'gallery';S._returnPage=null;if(S.page==='detail')S.page=ret;updateNav();pushHistory(ret);if(ret==='duplicates'){if(S.tagsModified){S.tagsModified=false;S.dupGroups=null;S._dupCachedThreshold=null;navigate('duplicates');}return;}if(S.tagsModified){S.tagsModified=false;loadCharacters().then(renderTagList);loadImagesReset().then(renderMain);}}

var BROWSER_VIDEO = {'mp4':1,'webm':1,'m4v':1,'mov':1,'mkv':1,'ogv':1};

function videoPlaybackFailed(){var a=document.getElementById('detail-img-area');if(!a)return;a.innerHTML='<div style="color:var(--text-secondary);text-align:center;padding:40px"><div style="font-size:15px;margin-bottom:12px">This video codec can\u2019t be decoded by the browser.</div><button class="btn" onclick="openInExplorer('+S.currentImageId+')">\ud83d\udcc2 Open in Explorer</button></div>';}

function isBrowserPlayable(fn){var ext=fn.split('.').pop().toLowerCase();return !!BROWSER_VIDEO[ext];}

function showDetailOverlay(){var old=document.getElementById('detail-overlay');if(old)old.remove();var img=S.images[S.currentImageIndex];if(!img)return;
var ov=document.createElement('div');ov.id='detail-overlay';
/* v4.53: the library stays reachable while a picture is open. Its own collapsed
   state, kept apart from the gallery's, so folding it away here does not fold it
   away there. detail-bare is the other switch: nothing but the picture. */
ov.className='detail-overlay'+(S.detailLibCollapsed?' lib-collapsed':'')+(S.detailBare?' bare':'');
ov.style.setProperty('--folder-col-w',S.folderColW+'px');
ov.style.setProperty('--tag-col-w',S.tagColW+'px');
_folderPaths=[];
var libAll=S.filter.search?(S.filteredTotal||0):getFolderTotal();
var libHtml='<div class="detail-library">'+librarySidebarHtml(libAll)
  +'<div class="dl-collapsed-bar" onclick="toggleDetailLibrary()" title="Show the library"><span>\u25B6</span><span class="cc-label">Library</span></div></div>';
var mediaHtml;
if(img.is_video&&isBrowserPlayable(img.filename)){mediaHtml='<video id="detail-video" src="/full/'+img.id+'" controls autoplay onerror="videoPlaybackFailed()" style="max-width:100%;max-height:100%;object-fit:contain"></video>';}
else if(img.is_video){mediaHtml='<div style="display:flex;flex-direction:column;align-items:center;gap:16px"><img src="/thumb/'+img.id+'?h='+img.fphash+'" '+DRAGGABLE_ATTR+' ondragstart="onGalleryDragStart(event,'+img.id+')" onmousedown="ndPress(event,'+img.id+')" style="max-width:80%;max-height:70vh;border-radius:8px;object-fit:contain"/><button class="btn btn-primary" onclick="openInPlayer('+img.id+')" style="font-size:16px;padding:12px 32px">▶ Open in Player</button></div>';}
else{mediaHtml='<img id="detail-img" src="/full/'+img.id+'" alt="'+esc(img.filename)+'" '+DRAGGABLE_ATTR+' ondragstart="onGalleryDragStart(event,'+img.id+')" onmousedown="ndPress(event,'+img.id+')"/>';}
ov.innerHTML=libHtml+'<div class="detail-img-area" id="detail-img-area" oncontextmenu="showGalleryCtx(event,'+img.id+',true)">'+mediaHtml+'</div><div class="detail-sidebar'+(S.detailSidebarCollapsed?' collapsed':'')+'"><div class="ds-collapsed-bar" onclick="toggleDetailSidebar()" title="Expand panel"><span class="ds-arrow">\u25C0</span><span class="cc-label">Info</span></div><div class="detail-panel"><div style="display:flex;gap:6px;align-items:stretch"><div class="ac-wrap" style="position:relative;flex:1"><input class="detail-filename" id="rename-input" value="'+esc(img.filename)+'" onkeydown="if(event.key===\'Enter\'&&!document.querySelector(\'#detail-overlay .ac-list.open\')){this.blur();}" onblur="renameFile()"/></div><span class="ds-collapse-btn" onclick="toggleDetailSidebar()" title="Collapse panel">\u25B6</span></div><div class="detail-folder">'+(img.file_date?new Date(img.file_date*1000).toLocaleDateString():'')+'</div><div class="detail-folder">\ud83d\udcc1 '+esc(img.folder)+'</div><div id="detail-rating" style="font-size:13px;color:'+(img.rating?ratingColor(img.rating):'var(--accent-light)')+';font-weight:600;margin-top:2px">'+(img.rating?img.rating:'')+'</div><div style="display:flex;gap:6px;flex-wrap:wrap"><button class="btn btn-sm" onclick="openInExplorer('+img.id+')">\ud83d\udcc2 Explorer</button><button class="btn btn-sm" onclick="revealInLibrary('+img.id+')" title="Show this picture where it lives in TrackImage">\u25C6 TrackImage</button><button class="btn btn-sm" onclick="findSimilar('+img.id+')">\ud83d\udd0d Find Duplicates</button><button class="btn btn-sm btn-warning" onclick="removeMetadataSingle('+img.id+')" title="Strip EXIF / prompt / embedded metadata">Metadata</button><button class="btn btn-sm btn-danger" onclick="deleteImage('+img.id+')">Delete</button></div><div class="detail-nav"><button class="btn btn-sm" onclick="prevImage()" '+(S.currentImageIndex<=0?'disabled':'')+'>← Prev</button><button class="btn btn-sm" onclick="closeDetail()">Back</button><button class="btn btn-sm" onclick="nextImage()" '+(S.currentImageIndex>=S.images.length-1&&S.allLoaded?'disabled':'')+'>Next →</button></div><div class="tags-panel" id="tags-panel">'+tagsPanelHtml(img)+'</div></div><div class="meta-panel" id="meta-panel">'+metaHeaderHtml()+'<div id="meta-body" class="meta-body"'+(_metaOpen()?'':' style="display:none"')+'><div class="meta-empty">Loading...</div></div></div></div>';
document.body.appendChild(ov);S.detailZoom=1;S.detailPan={x:0,y:0};
var _zp=document.createElement('div');_zp.id='zoom-pct';_zp.title='Zoom \u2014 100% is one image pixel per screen pixel';
try{var _ia=ov.querySelector('.detail-img-area');if(_ia)_ia.appendChild(_zp);}catch(_){}
/* attach autocomplete to detail rename */
var dri=document.getElementById('rename-input');if(dri)attachAutocomplete(dri,{mode:'rename',fetchItems:globalNameSuggest});hookAddTagAC();if(!img.is_video)setupDetailZoom();else{var vid=document.getElementById('detail-video');if(vid){vid.volume=S.volume;vid.addEventListener('volumechange',function(){S.volume=vid.volume;localStorage.setItem('ti_volume',String(vid.volume));});}var area=document.getElementById('detail-img-area');if(area)area.addEventListener('click',function(e){if(e.target===area){closeDetail();}});}setTimeout(function(){loadMetadata(img.id);loadDetailTags(img.id);},50);}

async function openInPlayer(id){var r=await api('/api/image/'+id+'/open-file',{method:'POST'});if(r.error)showToast('Error: '+r.error);}

function prevImage(){if(S.currentImageIndex>0){S.currentImageIndex--;S.currentImageId=S.images[S.currentImageIndex].id;showDetailOverlay();}}

async function nextImage(){
    // Auto-load more images if we're near the end and there are more available
    if(S.currentImageIndex>=S.images.length-3&&!S.allLoaded&&!S.loadingMore){
        await loadMoreImages();
    }
    if(S.currentImageIndex<S.images.length-1){S.currentImageIndex++;S.currentImageId=S.images[S.currentImageIndex].id;showDetailOverlay();}
}

function setupDetailZoom(){var area=document.getElementById('detail-img-area');var imgEl=document.getElementById('detail-img');if(!area||!imgEl)return;var startX,startY,moved=false;
area.addEventListener('wheel',function(e){e.preventDefault();var oldZ=S.detailZoom;var d=e.deltaY>0?0.85:1.15;S.detailZoom=Math.max(1,Math.min(12,S.detailZoom*d));if(S.detailZoom<=1){S.detailPan={x:0,y:0};}else{var areaRect=area.getBoundingClientRect();var cx=areaRect.left+areaRect.width/2;var cy=areaRect.top+areaRect.height/2;var mx=e.clientX-cx;var my=e.clientY-cy;var ratio=S.detailZoom/oldZ;S.detailPan.x=mx-(mx-S.detailPan.x)*ratio;S.detailPan.y=my-(my-S.detailPan.y)*ratio;}applyZoom();},{passive:false});
/* v4.35: one place decides what a double-tap or a double-click does, so the
   mouse and the finger cannot disagree about it. */
function toggleZoomAt(clientX,clientY){
  if(S.detailZoom>1){S.detailZoom=1;S.detailPan={x:0,y:0};}
  else{S.detailZoom=2.5;
    var r=area.getBoundingClientRect();
    var mx=clientX-(r.left+r.width/2),my=clientY-(r.top+r.height/2);
    S.detailPan.x=mx-mx*S.detailZoom;S.detailPan.y=my-my*S.detailZoom;}
  applyZoom();
}
area.addEventListener('dblclick',function(e){
  if(e.target!==imgEl)return;
  if(Date.now()-_tpTouchTs<800)return;   /* a finger already handled this one */
  toggleZoomAt(e.clientX,e.clientY);
});
area.addEventListener('mousedown',function(e){if(S.detailZoom<=1)return;if(e.target.tagName==='BUTTON')return;S.detailPanning=true;moved=false;startX=e.clientX-S.detailPan.x;startY=e.clientY-S.detailPan.y;area.classList.add('panning');e.preventDefault();});
window.addEventListener('mousemove',function(e){if(!S.detailPanning)return;S.detailPan.x=e.clientX-startX;S.detailPan.y=e.clientY-startY;moved=true;applyZoom();});
window.addEventListener('mouseup',function(){if(S.detailPanning){S.detailPanning=false;var a=document.getElementById('detail-img-area');if(a)a.classList.remove('panning');}});
/* v4.34: the same thing, for a finger.
   Everything above listens for a mouse. A phone synthesises mousedown for a
   tap but not for a drag, so a picture zoomed in by double-tapping could not be
   moved at all -- the only way to look around it was the browser's own pinch,
   which magnifies the whole page instead of the photograph. One finger drags,
   two fingers zoom, and the point between them stays where it was put. Below
   1x the browser keeps its own gestures; from there on the picture answers to
   the finger directly. */
var _tp={id:null,x:0,y:0,px:0,py:0,d0:0,z0:1,cx:0,cy:0,sx:0,sy:0,st:0,tap:0,tx:0,ty:0};
var _tpTouchTs=0;
function _tpDist(t){var dx=t[0].clientX-t[1].clientX,dy=t[0].clientY-t[1].clientY;return Math.sqrt(dx*dx+dy*dy);}
area.addEventListener('touchstart',function(e){
  if(e.target&&e.target.tagName==='BUTTON')return;
  _tpTouchTs=Date.now();
  if(e.touches.length===1){
    _tp.sx=e.touches[0].clientX;_tp.sy=e.touches[0].clientY;_tp.st=Date.now();moved=false;
  }
  /* v4.35: below 1x the finger is still tracked -- a double-tap has to be
     recognised here rather than left to the browser, because once the picture is
     zoomed this handler swallows the events the synthetic dblclick was built
     from. That is why the second double-tap did nothing in v4.34. */
  if(S.detailZoom<=1)return;
  var t=e.touches;
  if(t.length===2){
    var r=area.getBoundingClientRect();
    _tp.d0=_tpDist(t);_tp.z0=S.detailZoom;
    _tp.cx=(t[0].clientX+t[1].clientX)/2-(r.left+r.width/2);
    _tp.cy=(t[0].clientY+t[1].clientY)/2-(r.top+r.height/2);
    _tp.px=S.detailPan.x;_tp.py=S.detailPan.y;_tp.id=null;
    e.preventDefault();return;
  }
  if(t.length===1){
    _tp.id=t[0].identifier;
    _tp.x=t[0].clientX-S.detailPan.x;_tp.y=t[0].clientY-S.detailPan.y;
    area.classList.add('panning');moved=false;e.preventDefault();
  }
},{passive:false});
area.addEventListener('touchmove',function(e){
  var t=e.touches;
  if(_tp.d0&&t.length===2){
    var k=_tpDist(t)/(_tp.d0||1);
    var nz=Math.max(1,Math.min(12,_tp.z0*k));
    var ratio=nz/_tp.z0;
    S.detailZoom=nz;
    if(nz<=1){S.detailPan={x:0,y:0};}
    else{S.detailPan.x=_tp.cx-(_tp.cx-_tp.px)*ratio;
         S.detailPan.y=_tp.cy-(_tp.cy-_tp.py)*ratio;}
    moved=true;applyZoom();e.preventDefault();return;
  }
  if(_tp.id!==null&&t.length===1&&S.detailZoom>1){
    S.detailPan.x=t[0].clientX-_tp.x;
    S.detailPan.y=t[0].clientY-_tp.y;
    moved=true;applyZoom();e.preventDefault();
  }
},{passive:false});
function _tpEnd(e){
  var t=e.touches||[];
  _tpTouchTs=Date.now();
  if(t.length===1){                          /* one finger lifted off a pinch */
    _tp.d0=0;_tp.id=t[0].identifier;
    _tp.x=t[0].clientX-S.detailPan.x;_tp.y=t[0].clientY-S.detailPan.y;return;
  }
  if(t.length)return;
  _tp.id=null;_tp.d0=0;area.classList.remove('panning');
  var ct=e.changedTouches&&e.changedTouches[0];
  if(ct){
    var dx=ct.clientX-_tp.sx,dy=ct.clientY-_tp.sy,dt=Date.now()-_tp.st;
    if(S.detailZoom<=1&&Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)*1.5&&dt<700){
      /* Sideways, at rest: the same thing the arrow keys do on a desktop.
         Pulling the picture to the left brings the next one in from the right;
         pulling it to the right goes back. Once zoomed in, sideways means
         moving around inside the picture instead. */
      if(dx<0)nextImage();else prevImage();
      _tp.tap=0;moved=false;return;
    }
    if(Math.abs(dx)<24&&Math.abs(dy)<24&&dt<400){
      var now=Date.now();
      if(now-_tp.tap<320&&Math.abs(ct.clientX-_tp.tx)<48&&Math.abs(ct.clientY-_tp.ty)<48){
        _tp.tap=0;toggleZoomAt(ct.clientX,ct.clientY);
        setTimeout(function(){moved=false;},60);return;
      }
      _tp.tap=now;_tp.tx=ct.clientX;_tp.ty=ct.clientY;
    }
  }
  setTimeout(function(){moved=false;},60);
}
area.addEventListener('touchend',_tpEnd);
area.addEventListener('touchcancel',_tpEnd);
area.addEventListener('click',function(e){if(!moved&&S.detailZoom<=1){var close=false;if(e.target===area){close=true;}else if(e.target===imgEl){var r=imgEl.getBoundingClientRect();var s=Math.min(r.width/(imgEl.naturalWidth||1),r.height/(imgEl.naturalHeight||1));var vw=(imgEl.naturalWidth||1)*s,vh=(imgEl.naturalHeight||1)*s;var vl=r.left+(r.width-vw)/2,vt=r.top+(r.height-vh)/2;if(e.clientX<vl||e.clientX>vl+vw||e.clientY<vt||e.clientY>vt+vh)close=true;}if(close){closeDetail();}}moved=false;});
/* Fit factor: how much the natural-size image must shrink to sit inside the
   window. Images smaller than the window are scaled UP to fill it, keeping
   their aspect ratio, exactly as before. */
function fitScale(){
var nw=imgEl.naturalWidth||1, nh=imgEl.naturalHeight||1;
var r=area.getBoundingClientRect();
if(!r.width||!r.height)return 1;
return Math.min(r.width/nw, r.height/nh);
}
function applyZoom(){
area.classList.toggle('zoomed',S.detailZoom>1);
var base=fitScale();
var eff=base*S.detailZoom;
imgEl.style.transform='translate(-50%,-50%) translate('+S.detailPan.x+'px,'+S.detailPan.y+'px) scale('+eff+')';
/* v4.32: past 1:1 there is no more detail in the file. Showing real pixels is
   the honest rendering, but switching at 1.15x made ordinary zooming look blocky
   almost immediately -- at that point you are still looking at the picture, not
   inspecting it. The threshold is a setting now (Interface & Gallery), and
   'off' keeps smooth interpolation at every zoom level. */
imgEl.style.imageRendering=(pixelPeepAt()>0&&S.detailZoom>1&&eff>=pixelPeepAt()?'pixelated':'auto');
var pct=document.getElementById('zoom-pct');
if(pct){pct.textContent=Math.round(eff*100)+'%';
        pct.classList.toggle('one-to-one',Math.abs(eff-1)<0.02);
        pct.style.display=(S.detailZoom>1?'block':'none');}
}
window._applyZoomNow=applyZoom;   /* so the settings slider updates a view that is already open */
syncPanelHidden();
imgEl.addEventListener('load',function(){applyZoom();});
window.addEventListener('resize',function(){if(S.page==='detail')applyZoom();});
applyZoom();}

async function renameFile(){var inp=document.getElementById('rename-input');if(!inp)return;var val=inp.value.trim();if(!val)return;var img=S.images[S.currentImageIndex];if(!img||val===img.filename)return;
    // Strip extension for base name check
    var dot=val.lastIndexOf('.');var base=dot>0?val.substring(0,dot):val;
    // Strip existing (N) to get clean base
    var numMatch=base.match(/^(.*?)\s*\(\d+\)$/);
    var checkBase=numMatch?numMatch[1].trim():base;
    var mt=img.media_type||'image';
    var nn=await api('/api/next-number',{method:'POST',body:JSON.stringify({base_name:checkBase,exclude_ids:[S.currentImageId],media_type:mt})});
    var extraBody={};
    if(nn.next&&nn.next>1&&!numMatch){
        var choice=await showConfirm('File will be renamed as <strong>'+esc(checkBase)+' (N)</strong>',
            [{label:'Cancel',key:'cancel'},{label:'Start from (1)',key:'restart'},{label:'Start from …',key:'custom'},{label:'Continue from ('+nn.next+')',key:'continue',cls:'primary'}]);
        if(!choice||choice==='cancel'){inp.value=img.filename;return;}
        if(choice==='custom'){
            var num=await showPrompt('Start numbering from:',String(nn.next>1?nn.next-1:1));
            if(!num){inp.value=img.filename;return;}
            num=parseInt(num);
            if(isNaN(num)||num<1){showToast('Invalid number');inp.value=img.filename;return;}
            extraBody.start_number=num;
        } else if(choice==='restart'){
            extraBody.start_number=1;
        }
        // continue: let backend auto-assign
    }
    var body=Object.assign({filename:val},extraBody);
    var r=await api('/api/image/'+S.currentImageId+'/rename',{method:'POST',body:JSON.stringify(body)});if(r.error){if(r.suggestion){var ok=await showConfirm('File <strong>'+esc(val)+'</strong> already exists.\nRename to <strong>'+esc(r.suggestion)+'</strong> instead?');if(ok){r=await api('/api/image/'+S.currentImageId+'/rename',{method:'POST',body:JSON.stringify({filename:val,auto_increment:true})});if(r.error){showToast('Error: '+r.error);inp.value=img.filename;return;}}else{inp.value=img.filename;return;}}else{showToast('Error: '+r.error);inp.value=img.filename;return;}}pushUndo({type:'rename',imageId:S.currentImageId,oldFilename:img.filename,newFilename:r.filename});showToast('Renamed!','success',true);S.images[S.currentImageIndex].filename=r.filename;S.tagsModified=true;inp.value=r.filename;loadCharacters().then(renderTagList);}

async function deleteImage(id){if(!await showConfirm('Delete this image?',[{label:'Cancel',key:'cancel'},{label:'Delete',key:'ok',cls:'danger'}]))return;var r=await api('/api/image/'+id+'/delete',{method:'POST'});if(r.error)return showToast('Error: '+r.error);pushUndo({type:'delete',trashId:r.trash_id});showToast('Image deleted','success',true);if(S._returnPage==='duplicates'&&S.dupGroups){var gi=-1,ii=-1;S.dupGroups.forEach(function(g,gx){var ix=g.images.findIndex(function(img){return img.id===id;});if(ix>=0){gi=gx;ii=ix;}});if(gi>=0){S.dupGroups[gi].images.splice(ii,1);if(S.dupGroups[gi].images.length<=1)S.dupGroups.splice(gi,1);var dr=document.getElementById('dup-results');if(dr)dr.innerHTML=renderDupGroups(S.dupGroups);var totalDups=S.dupGroups.reduce(function(a,g){return a+g.images.length;},0);var st=document.getElementById('dup-stats');if(st)st.textContent=S.dupGroups.length+' group'+(S.dupGroups.length!==1?'s':'')+' \u00b7 '+totalDups+' images';S.images.splice(S.currentImageIndex,1);S.total--;if(S.images.length===0){closeDetail();return;}if(S.currentImageIndex>=S.images.length)S.currentImageIndex=S.images.length-1;S.currentImageId=S.images[S.currentImageIndex].id;showDetailOverlay();return;}}S.dupGroups=null;S._dupCachedThreshold=null;S.images.splice(S.currentImageIndex,1);S.total--;S.tagsModified=true;if(S.images.length===0){closeDetail();if(S.page==='duplicates'){render();return;}pushHistory('gallery');loadImagesReset().then(function(){render();loadCharacters();loadFolders();loadStats();});return;}if(S.currentImageIndex>=S.images.length)S.currentImageIndex=S.images.length-1;S.currentImageId=S.images[S.currentImageIndex].id;showDetailOverlay();}

async function revealInLibrary(id){
    var img=(S.images||[]).find(function(i){return i.id===id;});
    if(!img){showToast('That picture is not in the current view','error');return;}
    var folder=img.folder||'';
    /* v4.47: the gallery is the only page that can show a picture. Opened from
       the duplicates page the detail view returns there, and setFolderFilter
       leaves that page alone without loading anything -- so there was never a
       tile to scroll to and the search below ran its whole count for nothing.
       navigate closes the detail view on the way. */
    if(S.page!=='gallery')navigate('gallery');
    if(folder){
        var parts=folder.replace(/\//g,'\\').split('\\').filter(Boolean);
        var walk='';
        for(var i=0;i<parts.length;i++){walk+=(i?'\\':'')+parts[i];S.openFolders[walk]=true;}
    }
    await setFolderFilter(folder?[folder]:[]);
    renderFolderSidebar();
    await _revealScrollTo(id);
}

async function _revealScrollTo(id){
    /* v4.47: loadMoreImages returns at once while a scroll-triggered load is
       already running, so without a pause this spent every round in the same
       instant and gave up with the picture still on its way in. */
    for(var tries=0;tries<60;tries++){
        var el=document.querySelector('.gallery-item[data-id="'+id+'"]');
        if(el){
            S.selectedImages=new Set([id]);
            S.lastSelectedIndex=getImgIndex(id);
            updateSelectionUI();
            el.classList.add('selected');
            try{el.scrollIntoView({block:'center',behavior:'smooth'});}
            catch(_e){el.scrollIntoView();}
            return;
        }
        if(S.allLoaded&&!S.loadingMore)break;
        if(S.loadingMore)await new Promise(function(r){setTimeout(r,120);});
        else await loadMoreImages();
    }
    showToast('That picture is not in this folder view any more','error');
}

async function openInExplorer(id){var r=await api('/api/image/'+id+'/open-explorer',{method:'POST'});if(r.error)showToast('Error: '+r.error);}

function copyMeta(id,btn){var el=document.getElementById(id);if(!el)return;var t=el.textContent||'';function ok(){btn.classList.add('copied');var o=btn.textContent;btn.textContent='Copied';setTimeout(function(){btn.classList.remove('copied');btn.textContent=o;},1200);}if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(ok).catch(function(){fallbackCopy(t);ok();});}else{fallbackCopy(t);ok();}}

function hasTextSelection(){
try{var sel=window.getSelection();
if(!sel||sel.isCollapsed)return false;
return String(sel).replace(/\s+/g,'').length>0;}catch(e){return false;}
}

function fallbackCopy(t){var ta=document.createElement('textarea');ta.value=t;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{document.execCommand('copy');}catch(e){}document.body.removeChild(ta);}

function prettyLabel(k){return k.replace(/_/g,' ').replace(/\b\w/g,function(c){return c.toUpperCase();});}

async function loadMetadata(id){var p=document.getElementById('meta-panel');if(!p)return;try{var m=await api('/api/image/'+id+'/metadata');var h='';var has=false;
/* Date - EXIF first, fallback to file_date */
var dateVal=m.date_original||m.date_time||m.date_created||'';var img=S.images[S.currentImageIndex];if(dateVal){has=true;h+='<div class="meta-row"><div class="meta-label">Date</div><div class="meta-value">'+esc(dateVal)+'</div></div>';}else if(img&&img.file_date){has=true;var ds=new Date(img.file_date*1000).toLocaleDateString('en-GB',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});h+='<div class="meta-row"><div class="meta-label">Date</div><div class="meta-value">'+ds+'</div></div>';}
/* Dimensions */
var _aw=(img&&img.width)||m.actual_width,_ah=(img&&img.height)||m.actual_height;if(_aw){has=true;h+='<div class="meta-row"><div class="meta-label">Dimensions</div><div class="meta-value">'+_aw+' × '+_ah+' px</div></div>';}
/* File size */
if(m.file_size){has=true;var mb=m.file_size/(1024*1024);var fs=mb>=1?mb.toFixed(1)+' MB':(m.file_size/1024).toFixed(0)+' KB';h+='<div class="meta-row"><div class="meta-label">File Size</div><div class="meta-value">'+fs+'</div></div>';}
/* Ordered fields */
var ord=[['prompt','Prompt'],['negative_prompt','Negative'],['model','Model'],['vae','VAE'],['steps','Steps'],['sampler','Sampler'],['scheduler','Scheduler'],['cfg_scale','CFG Scale'],['seed','Seed'],['size','Size'],['hires_size','Size (Hires)'],['clip_skip','Clip Skip'],['denoising','Denoise'],['hires_upscaler','Hires Up.'],['hires_steps','Hires Steps'],['hires_upscale','Hires Scale'],['hires_cfg','Hires CFG'],['hires_sampler','Hires Sampler'],['hires_checkpoint','Hires Ckpt'],['model_hash','Model Hash'],['artist','Artist'],['title','Title'],['description','Description'],['keywords','Keywords'],['copyright','Copyright'],['original_filename','Original Name'],['camera_make','Camera'],['camera_model','Camera Model'],['lens_make','Lens'],['lens_model','Lens Model'],['focal_length','Focal Length'],['focal_length_35mm','Focal 35mm'],['f_number','Aperture'],['exposure_time','Exposure'],['iso','ISO'],['flash','Flash'],['gps','GPS'],['software','Software']];
for(var i=0;i<ord.length;i++){var k=ord[i][0],l=ord[i][1];if(m[k]!=null&&m[k]!==''){has=true;if(k==='prompt'||k==='negative_prompt'){var mvid='mv-'+k;h+='<div class="meta-row"><div class="meta-label">'+l+'</div><div style="flex:1;min-width:0;display:flex;flex-direction:column;align-items:flex-start"><div class="meta-value prompt" id="'+mvid+'">'+esc(String(m[k]))+'</div><button class="meta-copy-btn" onclick="copyMeta(\''+mvid+'\',this)">Copy</button></div></div>';}else{h+='<div class="meta-row"><div class="meta-label">'+l+'</div><div class="meta-value">'+esc(String(m[k]))+'</div></div>';}}}
/* Skip list */
var skip={'actual_width':1,'actual_height':1,'file_size':1,'error':1,'raw_parameters':1,'comfyui_prompt':1,'comfyui_workflow':1,'pixel_x':1,'pixel_y':1,'orientation':1,'x_resolution':1,'y_resolution':1,'resolution_unit':1,'date_digitized':1,'date_original':1,'date_time':1,'date_created':1,'color_space':1,'sensing_method':1,'spectral_sensitivity':1,'gain_control':1,'file_source':1,'serial_number':1,'digital_zoom':1,'max_aperture':1,'exposure_bias':1,'exposure_mode':1,'exposure_program':1,'metering_mode':1,'scene_type':1,'contrast':1,'saturation':1,'sharpness':1,'white_balance':1,'subject_distance':1,'shutter_speed':1,'aperture':1,'lens_info':1,'ExifOffset':1,'tag_34665':1};ord.forEach(function(o){skip[o[0]]=1;});
Object.keys(m).forEach(function(k){if(!skip[k]&&m[k]!=null&&m[k]!==''){has=true;h+='<div class="meta-row"><div class="meta-label">'+esc(prettyLabel(k))+'</div><div class="meta-value">'+esc(String(m[k]).substring(0,500))+'</div></div>';}});
if(!has)h+='<div class="meta-empty">No metadata found.</div>';p.innerHTML=metaHeaderHtml()+'<div id="meta-body" class="meta-body"'+(_metaOpen()?'':' style="display:none"')+'>'+h+'</div>';}catch(e){p.innerHTML=metaHeaderHtml()+'<div id="meta-body" class="meta-body"'+(_metaOpen()?'':' style="display:none"')+'><div class="meta-empty">Could not load.</div></div>';}}

var _sbFocus=null;

var _sbIdx=-1;

function getSbItems(col){
    if(col==='tags'){
        var items=[];
        document.querySelectorAll('#tag-list-container .tag-item').forEach(function(el){
            if(el.offsetParent!==null)items.push(el);
        });
        return items;
    }
    if(col==='folders'){
        var items=[];
        /* Collect all visible tree-toggles */
        document.querySelectorAll('.sidebar-col .tree-toggle').forEach(function(el){
            if(el.offsetParent!==null)items.push(el);
        });
        return items;
    }
    return [];
}

function clearSbHighlight(){
    document.querySelectorAll('.kb-hl').forEach(function(el){el.classList.remove('kb-hl');});
}

function applySbHighlight(){
    clearSbHighlight();
    if(!_sbFocus||_sbIdx<0)return;
    var items=getSbItems(_sbFocus);
    if(_sbIdx>=items.length)_sbIdx=items.length-1;
    if(_sbIdx<0)return;
    var el=items[_sbIdx];
    el.classList.add('kb-hl');
    el.scrollIntoView({block:'nearest'});
}

function sbNavigate(dir){
    if(!_sbFocus)return false;
    var items=getSbItems(_sbFocus);
    if(!items.length)return false;
    _sbIdx=Math.max(0,Math.min(items.length-1,_sbIdx+dir));
    applySbHighlight();
    return true;
}

function sbActivate(){
    if(!_sbFocus||_sbIdx<0)return false;
    var items=getSbItems(_sbFocus);
    if(_sbIdx>=items.length)return false;
    items[_sbIdx].click();
    return true;
}

function sbLeftRight(right){
    if(_sbFocus==='folders'){
        var items=getSbItems('folders');
        var el=items[_sbIdx];
        if(el){
            var fidx=el.dataset.fidx;
            var ch=document.getElementById('fc-'+fidx);
            if(ch){
                var isOpen=ch.classList.contains('open');
                if(right&&!isOpen){toggleFolderIdx(parseInt(fidx));return;}
                if(!right&&isOpen){toggleFolderIdx(parseInt(fidx));return;}
            }
        }
        if(right){sbSwitchCol('tags',el);}
    }else if(_sbFocus==='tags'){
        if(!right){var items=getSbItems('tags');sbSwitchCol('folders',items[_sbIdx]);}
    }
}

function sbSwitchCol(toCol,fromEl){
    var targetY=0;
    if(fromEl){var r=fromEl.getBoundingClientRect();targetY=r.top+r.height/2;}
    _sbFocus=toCol;
    var items=getSbItems(toCol);
    if(!items.length){_sbIdx=0;applySbHighlight();return;}
    var bestIdx=0,bestDist=Infinity;
    for(var i=0;i<items.length;i++){
        var r2=items[i].getBoundingClientRect();
        var mid=r2.top+r2.height/2;
        var d=Math.abs(mid-targetY);
        if(d<bestDist){bestDist=d;bestIdx=i;}
    }
    _sbIdx=bestIdx;
    applySbHighlight();
}

function setSbFocus(col,el){
    _sbFocus=col;
    var items=getSbItems(col);
    _sbIdx=items.indexOf(el);
    if(_sbIdx<0)_sbIdx=0;
    applySbHighlight();
}

var _ratingLatest={},_ratingChain={};

async function setRating(ids,rating){
    /* v3.65: optimistic UI first; per-image serialized requests, last press wins (fixes rapid-keypress race) */
    for(var id of ids){
        _ratingLatest[id]=rating;
        var idx=getImgIndex(id);if(idx>=0)S.images[idx].rating=rating;
        (function(iid){_ratingChain[iid]=(_ratingChain[iid]||Promise.resolve()).then(function(){if(_ratingLatest[iid]!==rating)return;return api('/api/image/'+iid+'/rating',{method:'POST',body:JSON.stringify({rating:rating})});});})(id);
    }
    if(rating>0)showToast('Rating '+rating+' set','success');
    else showToast('Rating cleared','success');
    // Update badges in gallery
    ids.forEach(function(id){
        var tile=document.querySelector('.gallery-item[data-id="'+id+'"]');
        var el=tile?tile.querySelector('.rating-badge'):null;
        var row=tile?tile.querySelector('.card-filename-row'):null;
        if(rating>0){var col=ratingColor(rating);if(el){el.textContent=rating;el.style.color=col;}else if(row)row.insertAdjacentHTML('beforeend','<span class="rating-badge" style="color:'+col+'">'+rating+'</span>');if(tile)tile.style.borderColor=col;}
        else{if(el)el.remove();if(tile)tile.style.borderColor='';}
    });
    // Update detail view if open
    if(S.page==='detail'){var di=document.getElementById('detail-rating');if(di){di.textContent=rating>0?rating:'';di.style.color=rating>0?ratingColor(rating):'var(--accent-light)';}}
    await loadCharacters();renderTagList();
}

function ratingColor(r){r=parseInt(r)||0;if(r<1)return '';var h=Math.round((r-1)/8*120);return 'hsl('+h+',65%,45%)';}

function _metaOpen(){return localStorage.getItem('ti_meta_open')!=='0';}

function toggleTagsPanel(){var o=!_tagsOpen();localStorage.setItem('ti_tags_open',o?'1':'0');var b=document.getElementById('tags-body');if(b)b.style.display=o?'':'none';var a=document.getElementById('tags-arrow');if(a)a.textContent=o?'\u25be':'\u25b8';}

function metaHeaderHtml(){return '<div class="detail-section-title meta-toggle" onclick="toggleMetaPanel()" style="margin-bottom:10px;cursor:pointer;user-select:none"><span id="meta-arrow">'+(_metaOpen()?'\u25be':'\u25b8')+'</span> Metadata</div>';}

function toggleMetaPanel(){var open=!_metaOpen();localStorage.setItem('ti_meta_open',open?'1':'0');var b=document.getElementById('meta-body');if(b)b.style.display=open?'':'none';var a=document.getElementById('meta-arrow');if(a)a.textContent=open?'\u25be':'\u25b8';}

/* v4.56: the gallery and the open picture each hold a copy of this column
   under the same id, so getElementById only ever reached the first one. In full
   screen that was the hidden gallery copy, and folding the column away changed
   nothing on screen until the picture was closed and opened again. Every copy
   is toggled, which also keeps the two in step. */
function toggleSidebarCol(which){var key=which==='folders'?'foldersCollapsed':'tagsCollapsed';S[key]=!S[key];try{localStorage.setItem('ti_'+which+'_collapsed',S[key]?'1':'0');}catch(e){}var n=document.querySelectorAll('.'+which+'-wrap');for(var i=0;i<n.length;i++)n[i].classList.toggle('collapsed',S[key]);}

function dsPanelEdge(){
var narrow=false;try{narrow=window.matchMedia('(max-width:820px)').matches;}catch(_e){narrow=window.innerWidth<=820;}
return (narrow&&window.innerHeight>=window.innerWidth)?'bottom':'right';
}

function dsArrows(){
var ov=document.querySelector('.detail-overlay');if(!ov)return;
var edge=dsPanelEdge();
var away=(edge==='bottom')?'\u25BC':'\u25B6';      /* send the panel away */
var back=(edge==='bottom')?'\u25B2':'\u25C0';      /* bring it back */
ov.setAttribute('data-edge',edge);
ov.querySelectorAll('.ds-collapse-btn').forEach(function(e){e.textContent=away;});
ov.querySelectorAll('.ds-collapsed-bar .ds-arrow').forEach(function(e){e.textContent=back;});
var r=ov.querySelector('.ds-reopen');if(r)r.textContent=back;
}

function syncPanelHidden(){
var ov=document.querySelector('.detail-overlay');if(!ov)return;
var sb=ov.querySelector('.detail-sidebar');
var hidden=!!(sb&&sb.classList.contains('collapsed'));
ov.classList.toggle('panel-hidden',hidden);
if(hidden&&!ov.querySelector('.ds-reopen')){
  var b=document.createElement('button');
  b.className='ds-reopen';b.title='Show details';b.setAttribute('aria-label','Show details');
  b.textContent='\u25C0';
  b.onclick=function(e){e.stopPropagation();toggleDetailSidebar();};
  ov.appendChild(b);
}
dsArrows();
if(typeof window._applyZoomNow==='function'){try{window._applyZoomNow();}catch(_){}}
}

function toggleDetailSidebar(){var sb=document.querySelector('#detail-overlay .detail-sidebar');if(!sb)return;S.detailSidebarCollapsed=!S.detailSidebarCollapsed;try{localStorage.setItem('ti_ds_collapsed',S.detailSidebarCollapsed?'1':'0');}catch(e){}sb.classList.toggle('collapsed',S.detailSidebarCollapsed);syncPanelHidden();}

function pixelPeepAt(){
var v=parseFloat(localStorage.getItem('ti_pixel_peep'));
if(isNaN(v))return 4;                 /* 400%: well past 1:1, so it never
                                         intrudes during ordinary zooming */
return Math.max(0,Math.min(16,v));
}

function setPixelPeep(v){
v=parseFloat(v);if(isNaN(v))v=4;
localStorage.setItem('ti_pixel_peep',String(v));
var lab=document.getElementById('pp-val');
if(lab)lab.textContent=(v<=0?'Off':Math.round(v*100)+'%');
if(typeof window._applyZoomNow==='function'){try{window._applyZoomNow();}catch(_){}}
}
