/* The grid: laying it out, selecting in it, paging further into it.
 *
 * File 05 of 13 — the page loads these in number order.
 */

async function loadImagesReset(){var _ep=S.navEpoch||0;S.images=[];S.allLoaded=false;S.selectedImages.clear();invalidateIndexMap();var p=new URLSearchParams();S.filter.characters.forEach(function(c){p.append('character',c);});S.filter.ratings.forEach(function(r){p.append('rating',r);});(S.filter.tags||[]).forEach(function(t){p.append('tag',t);});folderParams(p);if(S.filter.search)p.set('search',S.filter.search);p.set('sort',S.sort);p.set('order',S.order);p.set('page',1);p.set('per_page',60);var d=await api('/api/images?'+p);if(_ep!==(S.navEpoch||0))return;S.images=d.images;S.total=d.total;S.filteredTotal=d.total;S.allLoaded=d.images.length>=d.total;}

async function loadMoreImages(){if(S.allLoaded||S.loadingMore)return;var _ep=S.navEpoch||0;S.loadingMore=true;var pg=Math.floor(S.images.length/60)+1;var p=new URLSearchParams();S.filter.characters.forEach(function(c){p.append('character',c);});S.filter.ratings.forEach(function(r){p.append('rating',r);});(S.filter.tags||[]).forEach(function(t){p.append('tag',t);});folderParams(p);if(S.filter.search)p.set('search',S.filter.search);p.set('sort',S.sort);p.set('order',S.order);p.set('page',pg);p.set('per_page',60);var d=await api('/api/images?'+p);if(_ep!==(S.navEpoch||0)){S.loadingMore=false;return;}if(!d.images.length)S.allLoaded=true;else{var ids=new Set(S.images.map(function(i){return i.id;}));d.images.forEach(function(img){if(!ids.has(img.id))S.images.push(img);});S.total=d.total;if(S.images.length>=d.total)S.allLoaded=true;}S.loadingMore=false;invalidateIndexMap();appendGalleryItems(d.images);}

function filterByRating(n,e){closeDrawerAfterPick();detailExitToGallery();n=parseInt(n)||0;if(!n){S.filter.ratings=[];}else if(e&&(e.ctrlKey||e.metaKey)){var i=S.filter.ratings.indexOf(n);if(i>=0)S.filter.ratings.splice(i,1);else S.filter.ratings.push(n);}else{S.filter.ratings=(S.filter.ratings.length===1&&S.filter.ratings[0]===n)?[]:[n];}_ratingFilterRefresh();}

function removeRatingChip(n){detailExitToGallery();var i=S.filter.ratings.indexOf(n);if(i>=0)S.filter.ratings.splice(i,1);_ratingFilterRefresh();}

function setGridCols(n){n=Math.max(1,Math.min(15,parseInt(n)||8));S.cols=n;document.documentElement.style.setProperty('--gallery-cols',n);localStorage.setItem('ti_grid_cols',String(n));document.querySelectorAll('.grid-slider-val').forEach(function(v){v.textContent=n;});
// v3.83: the duplicates page now has justified rows as well, so both views get
// the measuring pass; the heat overlay only needs repainting on the dup page.
layoutJustified();}

function setSort(s){if(S.sort===s)S.order=S.order==='asc'?'desc':'asc';else{S.sort=s;S.order=s==='newest'?'desc':'asc';}localStorage.setItem('ti_sort',S.sort);localStorage.setItem('ti_order',S.order);updateSortButtons();loadImagesReset().then(function(){renderMain();});}

function updateSortButtons(){document.querySelectorAll('.sort-btn').forEach(function(b){var s=b.dataset.sort;b.classList.toggle('active',s===S.sort);if(s==='filename')b.textContent=S.sort==='filename'?(S.order==='asc'?'A–Z':'Z–A'):'A–Z';if(s==='newest')b.textContent=S.sort==='newest'?(S.order==='desc'?'Newest':'Oldest'):'Newest';});}

var searchTimeout;

function _applySearch(){var _t=S.searchChips.slice();var _p=(S.pendingSearch||'').trim();if(_p)_t.push(_p);S.filter.search=_t.join(',');S.selectedImages.clear();if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;render();return;}Promise.all([loadImagesReset(),loadCharacters()]).then(function(){renderMain();renderTagList();});}

function onSearch(v){S.pendingSearch=v;var x=document.getElementById('search-clear');if(x)x.classList.toggle('visible',!!v||S.searchChips.length>0);clearTimeout(searchTimeout);searchTimeout=setTimeout(_applySearch,300);}

function commitSearch(){clearTimeout(searchTimeout);var inp=document.getElementById('search-input');var v=(inp?inp.value:S.pendingSearch||'').trim();if(!v){_applySearch();return;}v.split(',').map(function(t){return t.trim();}).filter(Boolean).forEach(function(t){if(S.searchChips.indexOf(t)<0)S.searchChips.push(t);});S.pendingSearch='';if(inp)inp.value='';var x=document.getElementById('search-clear');if(x)x.classList.toggle('visible',S.searchChips.length>0);_applySearch();}

function clearSearch(){clearTimeout(searchTimeout);var inp=document.getElementById('search-input');if(inp)inp.value='';var x=document.getElementById('search-clear');if(x)x.classList.remove('visible');S.searchChips=[];S.pendingSearch='';S.filter.search='';S.selectedImages.clear();if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;render();if(inp)inp.focus();return;}Promise.all([loadImagesReset(),loadCharacters()]).then(function(){renderMain();renderTagList();});if(inp)inp.focus();}

function searchTerms(){return S.searchChips||[];}

function removeSearchTerm(i){detailExitToGallery();S.searchChips.splice(i,1);var x=document.getElementById('search-clear');if(x)x.classList.toggle('visible',S.searchChips.length>0||!!S.pendingSearch);_applySearch();}

var _clickTimer=null,_clickId=0,_imgIndexMap=null;

function getImgIndex(id){if(!_imgIndexMap){_imgIndexMap=new Map();S.images.forEach(function(img,i){_imgIndexMap.set(img.id,i);});}return _imgIndexMap.has(id)?_imgIndexMap.get(id):-1;}

function invalidateIndexMap(){_imgIndexMap=null;}

function onItemClick(imgId,e){
    e.preventDefault();e.stopPropagation();
    if(_clickTimer&&_clickId===imgId){clearTimeout(_clickTimer);_clickTimer=null;_clickId=0;S.selectedImages.clear();updateSelectionUI();openImage(imgId);return;}
    if(_clickTimer){clearTimeout(_clickTimer);_clickTimer=null;}
    _clickId=imgId;
    var shiftKey=e.shiftKey,ctrlKey=e.ctrlKey||e.metaKey;
    /* v4.46: read and clear it here, while this click is still the current one */
    var pressPicked=(_cdPressSelected===imgId);_cdPressSelected=0;
    _clickTimer=setTimeout(function(){_clickTimer=null;_clickId=0;
        var idx=getImgIndex(imgId);
        var prev=new Set(S.selectedImages);
        if(shiftKey&&S.lastSelectedIndex>=0){
            var a=Math.min(S.lastSelectedIndex,idx),b=Math.max(S.lastSelectedIndex,idx);
            for(var i=a;i<=b;i++)S.selectedImages.add(S.images[i].id);
        }else if(ctrlKey){
            if(S.selectedImages.has(imgId))S.selectedImages.delete(imgId);else S.selectedImages.add(imgId);
        }else if(pressPicked){
            S.selectedImages.clear();S.selectedImages.add(imgId);
        }else{
            if(S.selectedImages.size===1&&S.selectedImages.has(imgId))S.selectedImages.clear();
            else{S.selectedImages.clear();S.selectedImages.add(imgId);}
        }
        S.lastSelectedIndex=idx;
        updateSelectionDiff(prev);
    },230);
}

function updateSelectionDiff(prev){
    /* only toggle items that changed */
    var all=new Set([...prev,...S.selectedImages]);
    all.forEach(function(id){
        var wasIn=prev.has(id),nowIn=S.selectedImages.has(id);
        if(wasIn!==nowIn){var el=document.querySelector('.gallery-item[data-id="'+id+'"]');if(el)el.classList.toggle('selected',nowIn);}
    });
    updateSelectionBar();
}

function updateSelectionUI(){
    updateQaState();
    document.querySelectorAll('.gallery-item').forEach(function(el){
        el.classList.toggle('selected',S.selectedImages.has(parseInt(el.dataset.id)));
    });
    updateSelectionBar();
}

function updateSelectionBar(){
    var si=document.getElementById('sel-info');
    if(si){if(S.selectedImages.size>0){si.style.display='flex';si.querySelector('.sel-count').textContent=S.selectedImages.size+' selected';}else si.style.display='none';}
    var eb=document.getElementById('btn-explorer-sel'),mb=document.getElementById('btn-move-sel'),rb=document.getElementById('btn-rename-sel'),tb=document.getElementById('btn-tags-sel'),sm=document.getElementById('btn-stripmeta-sel'),db=document.getElementById('btn-delete-sel');
    var dis=S.selectedImages.size===0;
    if(eb)eb.disabled=dis;
    if(mb)mb.disabled=dis;
    if(rb)rb.disabled=dis;
    if(tb)tb.disabled=dis;
    if(sm)sm.disabled=dis;
    if(db)db.disabled=dis;
    updateClipboardUI();
}

function clearSelection(){S.selectedImages.clear();updateSelectionUI();}

var _resizeState=null;

/* v4.56: both copies of this column carry the same id, so getElementById used
   to resize whichever came first in the document -- in full screen the hidden
   one. The grabbed handle sits inside the column that is meant, and every copy
   follows it so the two never drift apart in width. */
function startResize(e,kind){e.preventDefault();e.stopPropagation();var cls=(kind==='folder'?'folders':'tags')+'-wrap';var wrap=e.target.closest?e.target.closest('.'+cls):null;if(!wrap)wrap=e.target.parentNode;if(!wrap||!wrap.classList||!wrap.classList.contains(cls))wrap=document.querySelector('.'+cls);if(!wrap)return;var all=document.querySelectorAll('.'+cls);_resizeState={kind:kind,startX:e.clientX,startW:wrap.offsetWidth,wrap:wrap,all:all};document.body.style.cursor='col-resize';document.body.style.userSelect='none';e.target.classList.add('dragging');var handle=e.target;function move(ev){if(!_resizeState)return;var dw=ev.clientX-_resizeState.startX;var nw=Math.max(120,Math.min(600,_resizeState.startW+dw));for(var i=0;i<_resizeState.all.length;i++)_resizeState.all[i].style.width=nw+'px';}function up(){if(!_resizeState)return;var nw=_resizeState.wrap.offsetWidth;if(_resizeState.kind==='folder'){S.folderColW=nw;localStorage.setItem('ti_folder_col_w',String(nw));}else{S.tagColW=nw;localStorage.setItem('ti_tag_col_w',String(nw));}document.body.style.cursor='';document.body.style.userSelect='';handle.classList.remove('dragging');document.removeEventListener('mousemove',move);document.removeEventListener('mouseup',up);_resizeState=null;}document.addEventListener('mousemove',move);document.addEventListener('mouseup',up);}

var scrollObs;

function setupInfiniteScroll(){layoutJustified();if(scrollObs)scrollObs.disconnect();var t=document.getElementById('load-trigger');if(!t||S.allLoaded)return;scrollObs=new IntersectionObserver(function(e){if(e[0].isIntersecting&&!S.loadingMore&&!S.allLoaded)loadMoreImages();},{root:document.querySelector('.main'),rootMargin:'400px'});scrollObs.observe(t);}

function cardInfoInner(img){var inner='';if(S.info.name)inner+='<div class="card-filename-row"><div class="card-filename">'+esc(img.filename)+'</div>'+(img.rating?'<span class="rating-badge" style="color:'+ratingColor(img.rating)+'">'+img.rating+'</span>':'')+'</div>';if(S.info.date&&img.file_date)inner+='<div class="card-date">'+new Date(img.file_date*1000).toLocaleDateString()+'</div>';if(S.info.folder)inner+='<div class="card-folder" title="'+esc(img.folder)+'">\ud83d\udcc1 '+esc(img.folder).split('\\').join('\\<wbr>')+'</div>';return inner;}

function cardInfoHtml(img){var inner=cardInfoInner(img);if(!inner)return '';return '<div class="card-info">'+inner+'</div>';}

function wrapStyle(img){if(S.thumbMode!=='ratio')return '';var w=img.width||0,h=img.height||0;if(!w||!h)return '';return ' style="aspect-ratio:'+w+'/'+h+'"';}

function thumbLoaded(el){
    var item=el.closest('.gallery-item');if(!item)return;
    if(+item.dataset.w>0&&+item.dataset.h>0)return;
    var w=el.naturalWidth,h=el.naturalHeight;if(!w||!h)return;
    item.dataset.w=w;item.dataset.h=h;
    if(S.thumbMode==='ratio'){clearTimeout(_ljTimer);_ljTimer=setTimeout(layoutJustified,150);}
}

function layoutJustified(){
    /* v3.83: the duplicates page renders one real gallery grid per group, so the
       justified pass runs over every .gallery container instead of a single id. */
    var gs=document.querySelectorAll('.gallery');
    for(var _li=0;_li<gs.length;_li++)layoutJustifiedGrid(gs[_li]);
}

function _ljRuler(g){
    var host=(g.closest&&g.closest('.main'))||g.parentElement;
    if(!host)return 0;
    var r=host._ljRuler;
    if(!r||r.parentElement!==host){
        r=document.createElement('div');
        r.className='lj-ruler';r.setAttribute('aria-hidden','true');
        r.style.cssText='align-self:stretch;height:0;margin:0;padding:0;border:0;flex:none;';
        host.insertBefore(r,host.firstChild);
        host._ljRuler=r;
    }
    return r.getBoundingClientRect().width;
}

function layoutJustifiedGrid(g,forceW){
    if(!g)return;
    if(S.thumbMode!=='ratio'){
        g.querySelectorAll('.gallery-item').forEach(function(el){el.style.width='';var wr=el.querySelector('.img-wrap');if(wr){wr.style.height='';wr.style.aspectRatio='';}});
        return;
    }
    var cs=getComputedStyle(g);var gap=parseFloat(cs.gap)||8;
    /* fractional content width (clientWidth is rounded -> sub-pixel overflow wraps items at browser zoom) */
    var W=g.getBoundingClientRect().width-(parseFloat(cs.paddingLeft)||0)-(parseFloat(cs.paddingRight)||0)-(parseFloat(cs.borderLeftWidth)||0)-(parseFloat(cs.borderRightWidth)||0)-0.5;
    /* v4.33: never lay out to a width that is not actually on screen.
       Measuring the gallery and then sizing its contents to that measurement is
       circular -- one row that spilled over kept every following pass spilling
       over with it. A desktop window has slack and it never showed; a phone has
       none, and tiles ran off the right edge. Take the smallest honest number
       of the three: the box itself, the box it sits in, and the viewport. */
    var _par=g.parentElement;
    if(_par){var _ps=getComputedStyle(_par);
        var _pw=_par.clientWidth-(parseFloat(_ps.paddingLeft)||0)-(parseFloat(_ps.paddingRight)||0);
        if(_pw>60&&_pw<W)W=_pw;}
    /* v4.34: a ruler, because asking the gallery how wide it is and then filling
       it to that answer is circular -- if the box is already too wide, every
       pass agrees with the mistake. The ruler is an empty block that simply
       stretches to whatever the surrounding column really offers, so it cannot
       inherit the error. Smallest of the three wins. */
    var _ru=_ljRuler(g);
    if(_ru>60&&_ru<W)W=_ru;
    var _vw=document.documentElement.clientWidth||0;
    if(_vw>60&&_vw<W)W=_vw;
    W-=1;                       /* never sit flush against the edge */
    if(forceW>60)W=forceW;
    if(W<60)return;
    /* The desktop rule, on every screen: honour the column count the user set,
       as long as a tile stays at least 48px wide. v4.32 gave phones their own
       count and then held the target at a 90px floor -- so it asked for rows
       the screen could not hold, and they overflowed instead of wrapping.
       Below the floor the count drops, never the fit. */
    var cols=Math.max(1,Math.min(S.cols,Math.floor((W+gap)/(48+gap))));
    var target=Math.max(24,(W-(cols-1)*gap)/cols);
    g._ljInfo={W:Math.round(W*10)/10,cols:cols,target:Math.round(target*10)/10,gap:gap,
               box:Math.round(g.getBoundingClientRect().width),ruler:Math.round(_ru),
               viewport:_vw,forced:Math.round(forceW||0)};
    window._ljLast=g._ljInfo;   /* Settings shows this; see updateLjReadout */
    var items=[].slice.call(g.querySelectorAll('.gallery-item'));
    var row=[],rw=0;
    function flush(last){
        if(!row.length)return;
        var gaps=gap*(row.length-1);
        var scale=(W-gaps)/rw;
        if(last&&scale>1.35)scale=1;               /* don't blow up a short last row */
        var h=target*scale;                         /* keep fractions: rounding caused zoom gaps */
        var ws=row.map(function(o){return h*o.ar;});
        if(!last){                                  /* full row: absorb rounding so the row fits EXACTLY */
            var rest=(W-gaps)-ws.reduce(function(a,b){return a+b;},0);
            ws[ws.length-1]+=rest;
        }
        /* Belt and braces: if the widths still exceed the container -- a single
           very wide image in the last row, say -- scale the whole row down so
           nothing can spill past the edge. */
        var sum=ws.reduce(function(a,b){return a+b;},0)+gaps;
        if(sum>W){var k=(W-gaps)/(sum-gaps);ws=ws.map(function(x){return x*k;});h=h*k;}
        row.forEach(function(o,i){
            o.el.style.width=Math.max(20,ws[i]).toFixed(2)+'px';
            var wr=o.el.querySelector('.img-wrap');
            if(wr){wr.style.height=h.toFixed(2)+'px';wr.style.aspectRatio='auto';}
        });
        row=[];rw=0;
    }
    items.forEach(function(el){
        var w=parseFloat(el.dataset.w)||0,hh=parseFloat(el.dataset.h)||0;
        var ar=(w>0&&hh>0)?Math.max(0.3,Math.min(4,w/hh)):1;
        var iw=target*ar;
        if(row.length&&(rw+iw+gap*row.length)>W)flush(false);
        row.push({el:el,ar:ar});rw+=iw;
    });
    flush(true);
    /* Last line of defence. If anything still sticks out -- a scrollbar that
       appeared halfway through, a rounding artefact -- redo the pass once
       against the width the browser really ended up with. Once, never a loop. */
    if(forceW==null&&g.scrollWidth>Math.ceil(W)+1){
        var _real=Math.min(W,g.clientWidth)-1;
        if(_real>60)return layoutJustifiedGrid(g,_real);
    }
    if(!g.classList.contains('laid'))requestAnimationFrame(function(){g.classList.add('laid');});
}

function updateLjReadout(){
var e=document.getElementById('lj-readout');if(!e)return;
var i=window._ljLast;
if(!i){e.textContent='open the gallery once';return;}
e.textContent='used '+i.W+' \u00b7 box '+i.box+' \u00b7 ruler '+i.ruler+' \u00b7 screen '+i.viewport
             +' \u00b7 '+i.cols+' cols \u00b7 tile '+i.target+'px';
}

function tiGridInfo(){var o=[];document.querySelectorAll('.gallery').forEach(function(g){if(g._ljInfo)o.push(g._ljInfo);});return o.length===1?o[0]:o;}

var _ljTimer=null,_ljW=0;

var _ljRO=new ResizeObserver(function(en){var w=en[0]&&en[0].contentRect?en[0].contentRect.width:0;if(Math.abs(w-_ljW)<2)return;_ljW=w;clearTimeout(_ljTimer);_ljTimer=setTimeout(layoutJustified,60);});

function appendGalleryItems(items){var g=document.getElementById('gallery-grid');if(!g)return;var ids=new Set();g.querySelectorAll('.gallery-item').forEach(function(el){ids.add(el.dataset.id);});items.forEach(function(img){if(ids.has(String(img.id)))return;var d=document.createElement('div');d.className='gallery-item';d.dataset.id=img.id;d.dataset.w=img.width||0;d.dataset.h=img.height||0;if(img.rating)d.style.borderColor=ratingColor(img.rating);d.onclick=function(e){onItemClick(img.id,e);};d.oncontextmenu=function(e){showGalleryCtx(e,img.id);};d.draggable=true;d.ondragstart=function(e){onGalleryDragStart(e,img.id);};d.ondragend=onGalleryDragEnd;d.innerHTML='<div class="img-wrap"'+wrapStyle(img)+'>'+cardMediaHtml(img)+'</div>'+cardInfoHtml(img);g.appendChild(d);});if(S.allLoaded){var lt=document.getElementById('load-trigger');if(lt)lt.parentElement.remove();}else setupInfiniteScroll();layoutJustified();}

function cardMediaHtml(img){if(img.is_video||img.media_type==='video')return '<img src="/thumb/'+img.id+'?h='+img.fphash+'" alt="'+esc(img.filename)+'" loading="lazy" draggable="false" onload="thumbLoaded(this)"/><span class="video-badge">▶ VIDEO</span>';if(img.media_type==='gif')return '<img src="/thumb/'+img.id+'?h='+img.fphash+'" alt="'+esc(img.filename)+'" loading="lazy" draggable="false" onload="thumbLoaded(this)"/><span class="video-badge">GIF</span>';var ext=img.filename.split('.').pop().toLowerCase();if(ext==='gif')return '<img src="/thumb/'+img.id+'?h='+img.fphash+'" alt="'+esc(img.filename)+'" loading="lazy" draggable="false" onload="thumbLoaded(this)"/><span class="video-badge">GIF</span>';return '<img src="/thumb/'+img.id+'?h='+img.fphash+'" alt="'+esc(img.filename)+'" loading="lazy" draggable="false" onload="thumbLoaded(this)"/>';}

function galleryItemHtml(img){
    var sel=S.selectedImages.has(img.id)?' selected':'';
    return '<div class="gallery-item'+sel+'" data-id="'+img.id+'" data-sig="'+esc(String(img.fphash||''))+'" data-w="'+(img.width||0)+'" data-h="'+(img.height||0)+'" onclick="onItemClick('+img.id+',event)" oncontextmenu="showGalleryCtx(event,'+img.id+')" '+DRAGGABLE_ATTR+' ondragstart="onGalleryDragStart(event,'+img.id+')" onmousedown="ndPress(event,'+img.id+')" ondragend="onGalleryDragEnd()"><div class="img-wrap"'+wrapStyle(img)+'>'+cardMediaHtml(img)+'</div>'+cardInfoHtml(img)+'</div>';
}

function renderMainContent(){var h='<div class="gallery'+(S.thumbMode==='ratio'?' justified':'')+(S.info.visible?'':' no-info')+'" id="gallery-grid" oncontextmenu="showMainCtx(event)">'+S.images.map(galleryItemHtml).join('')+'</div>';if(!S.images.length)h='<div class="empty-state" oncontextmenu="showMainCtx(event)"><div class="icon">◈</div><div>No images found.</div></div>';if(!S.allLoaded&&S.images.length)h+='<div class="load-more"><div id="load-trigger"><span class="spinner"></span></div></div>';return h;}

function drawerEl(){return document.querySelector('.sidebar');}

function scrimEl(){
var el=document.getElementById('drawer-scrim');
if(!el){el=document.createElement('div');el.id='drawer-scrim';
        el.addEventListener('click',closeDrawer);document.body.appendChild(el);}
return el;
}

function renderGallery(){if(!S.initialized)return renderSetup();_folderPaths=[];var tree=buildFolderTree();var allCount=S.filter.search?(S.filteredTotal||0):getFolderTotal();var fw=S.folderColW,tw=S.tagColW;return '<div class="gallery-layout" style="--folder-col-w:'+fw+'px;--tag-col-w:'+tw+'px">'+renderTopbar()+'<div class="sidebar"><div class="sidebar-col-wrap folders-wrap'+(S.foldersCollapsed?' collapsed':'')+'" id="folders-wrap"><div class="col-collapsed-bar" onclick="toggleSidebarCol(\'folders\')" title="Expand"><span>\u25B6</span><span class="cc-label">Folders</span></div><div class="sidebar-col folders-col" id="folders-col"><div class="sidebar-title"><span>Folders</span><span class="sel-count-folders" style="display:none;font-family:\'Space Mono\',monospace;font-size:10px;color:var(--accent-light)"></span><span class="col-collapse-btn" onclick="toggleSidebarCol(\'folders\')" title="Collapse">\u25C0</span></div>'+renderFolderNode(tree,0)+'<div class="link-folder-btn" onclick="pickAndAddFolder()">Link new folder</div></div><div class="col-resizer" onmousedown="startResize(event,\'folder\')"></div></div><div class="sidebar-col-wrap tags-wrap'+(S.tagsCollapsed?' collapsed':'')+'" id="tags-wrap"><div class="col-collapsed-bar" onclick="toggleSidebarCol(\'tags\')" title="Expand"><span>\u25B6</span><span class="cc-label">Tags</span></div><div class="sidebar-col tags-col" id="tags-col">'+tagColInner(allCount)+'</div><div class="col-resizer" onmousedown="startResize(event,\'tag\')"></div></div></div><div class="main" id="main-area">'+renderMainContent()+'</div></div>';}

/* Ctrl+A: every picture the view holds. The grid only ever has the first pages
   loaded, so selecting what is on screen would quietly leave the rest out --
   the ids of the whole filter are asked for once instead. */
async function selectAllInView(){
    if(S.page==='duplicates'){
        (S.dupGroups||[]).forEach(function(g){(g.images||g).forEach(function(im){S.selectedImages.add(im.id);});});
        updateDupSelectionUI();showToast(S.selectedImages.size+' selected');return;
    }
    if(S.page!=='gallery')return;
    S.images.forEach(function(i){S.selectedImages.add(i.id);});updateSelectionUI();
    if(!S.allLoaded){
        var _ep=S.navEpoch||0;
        var p=new URLSearchParams();S.filter.characters.forEach(function(c){p.append('character',c);});S.filter.ratings.forEach(function(r){p.append('rating',r);});(S.filter.tags||[]).forEach(function(t){p.append('tag',t);});folderParams(p);if(S.filter.search)p.set('search',S.filter.search);p.set('ids_only','1');
        var d=null;try{d=await api('/api/images?'+p);}catch(_e){}
        if(_ep!==(S.navEpoch||0)||S.page!=='gallery')return;
        if(d&&d.ids)d.ids.forEach(function(id){S.selectedImages.add(id);});
        updateSelectionUI();
    }
    showToast(S.selectedImages.size+' selected');
}
