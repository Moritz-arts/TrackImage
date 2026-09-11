/* Which page is showing, and drawing it.
 *
 * File 04 of 13 — the page loads these in number order.
 */

function navigate(page,opts){opts=opts||{};S.navEpoch=(S.navEpoch||0)+1;if(S.page==='detail')closeDetail();if(S.page==='duplicates'&&page!=='duplicates'){clearInterval(_hashPollTimer);clearInterval(_dupComputeTimer);S._hashAttempted=false;S._dupQuery=null;/* v3.93: stop the background pair compare too -- leaving the page means it is not needed any more. */try{api('/api/duplicates/cancel',{method:'POST'});}catch(e){}}if(S.page==='gallery'&&page!=='gallery'){var m=document.querySelector('.main');if(m)S.scrollPosition=m.scrollTop;}S.page=page;updateNav();pushHistory(page);render();if(page==='gallery'&&!opts.resetScroll)requestAnimationFrame(function(){var m=document.querySelector('.main');if(m)m.scrollTop=S.scrollPosition;});}

function updateNav(){document.querySelectorAll('.nav-link').forEach(function(el){el.classList.toggle('active',el.dataset&&el.dataset.page===S.page);});}

function countAll(node){var c=node.count||0;Object.keys(node.children).forEach(function(k){c+=countAll(node.children[k]);});return c;}

function renderMain(){var m=document.getElementById('main-area');if(!m){render();return;}var st=m.scrollTop;m.innerHTML=renderMainContent();requestAnimationFrame(function(){setupInfiniteScroll();layoutJustified();m.scrollTop=st;});updateSidebarActive();updateSelectionUI();}

function renderMainIncremental(){
    var m=document.getElementById('main-area');
    var grid=document.getElementById('gallery-grid');
    if(!m||!grid)return false;
    if(!S.images.length)return false;              /* empty state has its own markup */
    var st=m.scrollTop;
    var have={},n=grid.children,i;
    for(i=0;i<n.length;i++){var d=n[i].dataset;if(d&&d.id)have[d.id]=n[i];}
    var want={};S.images.forEach(function(im){want[String(im.id)]=1;});
    Object.keys(have).forEach(function(id){
        if(!want[id]){have[id].remove();delete have[id];}
    });
    var tpl=document.createElement('div');
    var cursor=grid.firstElementChild;
    for(i=0;i<S.images.length;i++){
        var img=S.images[i],id=String(img.id),node=have[id];
        var sig=String(img.fphash||'');
        if(node&&node.dataset.sig!==sig){         /* thumbnail changed -> rebuild this one */
            /* Step the cursor off it first: removing the node the cursor points at
               would leave insertBefore with a reference that is no longer a child. */
            if(cursor===node)cursor=cursor.nextElementSibling;
            node.remove();delete have[id];node=null;
        }
        if(cursor&&node&&cursor===node){cursor=cursor.nextElementSibling;continue;}
        if(!node){tpl.innerHTML=galleryItemHtml(img);node=tpl.firstElementChild;}
        if(cursor&&cursor.parentNode!==grid)cursor=null;   /* stale reference -> append */
        grid.insertBefore(node,cursor);
        have[id]=node;
    }
    /* the load-more sentinel lives outside the grid; keep it in step */
    var lm=m.querySelector('.load-more');
    if(S.allLoaded&&lm)lm.remove();
    else if(!S.allLoaded&&!lm)grid.insertAdjacentHTML('afterend','<div class="load-more"><div id="load-trigger"><span class="spinner"></span></div></div>');
    requestAnimationFrame(function(){setupInfiniteScroll();layoutJustified();m.scrollTop=st;});
    updateSidebarActive();updateSelectionUI();
    return true;
}

function renderMainSoft(){if(!renderMainIncremental())renderMain();}

function updateSidebarActive(){updateTagActive();updateFolderActive();}

function activeFilterChipsHtml(){
    var h='',n=0;
    searchTerms().forEach(function(t,i){n++;h+='<span class="search-chip" title="Search term">'+esc(t)+'<span class="chip-x" onclick="removeSearchTerm('+i+')">\u2715</span></span>';});
    selFolders().forEach(function(fp){n++;h+='<span class="search-chip" title="Folder: '+esc(fp)+'">'+esc(folderLeaf(fp))+'<span class="chip-x" onclick="filterByFolder(&quot;'+esc(fp).replace(/\\/g,'\\\\')+'&quot;)">\u2715</span></span>';});
    S.filter.characters.forEach(function(c){n++;h+='<span class="search-chip" data-tag="'+esc(c)+'" title="Name">'+esc(c)+'<span class="chip-x" onclick="removeTagChip(this.parentElement.dataset.tag)">\u2715</span></span>';});
    S.filter.ratings.forEach(function(rv){n++;h+='<span class="search-chip" title="Rating"><span style="color:'+ratingColor(rv)+';font-weight:700">\u2605 '+rv+'</span><span class="chip-x" onclick="removeRatingChip('+rv+')">\u2715</span></span>';});
    (S.filter.tags||[]).forEach(function(c){n++;h+='<span class="search-chip" title="Tag">'+esc(c)+'<span class="chip-x" onclick="removeTagFilterChip(\''+esc(c)+'\')">\u2715</span></span>';});
    if(!n)return '';
    return '<div class="search-chips" style="position:sticky;top:0;z-index:5;background:var(--bg-secondary);margin:0;border-bottom:1px solid var(--accent-glow)">'+h+'</div>';
}

async function render(){var el=document.getElementById('content');requestAnimationFrame(function(){try{updateWorkSpinner();refreshSetNav();}catch(_){}});var prevScroll=0;var pm=document.querySelector('.main');if(pm)prevScroll=pm.scrollTop;switch(S.page){case 'gallery':el.innerHTML=renderGallery();requestAnimationFrame(function(){setupInfiniteScroll();hookSearchAC();var m=document.querySelector('.main');if(m)m.scrollTop=prevScroll;});break;case 'detail':el.innerHTML=renderGallery();requestAnimationFrame(function(){setupInfiniteScroll();hookSearchAC();var m=document.querySelector('.main');if(m)m.scrollTop=prevScroll;});showDetailOverlay();break;case 'settings':
/* v4.18: the page is drawn first and filled in afterwards.

   It used to be assigned only once renderSettings() had resolved, so a slow call
   delayed the whole page -- and an exception inside it meant the page never
   appeared at all, silently, because nothing catches a rejected render(). That is
   exactly what happened: a stray reference threw every time and Settings simply
   would not open, during an import or otherwise. Now something is on screen
   immediately, whatever the data does. */
el.innerHTML=settingsShellHtml();
(async function(){
    var _ep=S.navEpoch||0,h;
    try{h=await renderSettings();}
    catch(err){
        console.error('renderSettings failed',err);
        var b=document.getElementById('set-boot');
        if(b)b.innerHTML='<div class="settings-card"><h3>Settings could not be built</h3>'+
            '<p>'+esc(String(err&&err.message||err))+'</p>'+
            '<p style="color:var(--text-muted);font-size:12px">The rest of TrackImage is unaffected. '+
            'Please report this message \u2014 it names the cause exactly.</p></div>';
        return;
    }
    if(_ep!==(S.navEpoch||0)||S.page!=='settings')return;
    el.innerHTML=h;
    requestAnimationFrame(function(){updateSettingsProc(S._proc);
        loadVenv(false);});
})();
break;case 'duplicates':el.innerHTML=dupShellOpen()+'<div class="main" id="main-area"><div class="page-title">Duplicates</div><div class="dup-loading"><div class="spinner"></div>Scanning for duplicates...</div></div></div>';el.innerHTML=await renderDuplicates();if(document.getElementById('hash-progress-bar'))startHashPoll();requestAnimationFrame(function(){var m=document.querySelector('.main');if(m)m.scrollTop=prevScroll;});break;default:el.innerHTML=renderGallery();requestAnimationFrame(function(){setupInfiniteScroll();hookSearchAC();var m=document.querySelector('.main');if(m)m.scrollTop=prevScroll;});}}
