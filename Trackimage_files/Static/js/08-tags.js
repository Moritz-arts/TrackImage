/* Tags and characters.
 *
 * File 08 of 13 — the page loads these in number order.
 */

async function loadIgnoreWords(){S.ignoreWords=await api('/api/ignore-words');}

function _tagAvail(){var t=S._tag||{};return !!(t.runtime&&t.model);}

function _tagInstallHint(pre){if(_tagAvail())return '';var t=S._tag||{},dl=t.model_download||{};if(dl.active)return '<div class="proc-hint tag-install-hint" data-pre="'+esc(pre||'')+'" style="padding:6px 10px">Auto-tagging is installing\u2026 '+(dl.phase==='runtime'?((dl.all_total?Math.min(99,Math.round(dl.all_done*100/dl.all_total)):0)+'% runtime'):((dl.total?Math.round(dl.done*100/dl.total):0)+'%'))+'</div>';return '<div class="proc-hint tag-install-hint" data-pre="'+esc(pre||'')+'" style="padding:6px 10px">'+(pre||'Auto-tagging not installed')+' \u2014 <a onclick="toggleSettings()" style="color:var(--accent);cursor:pointer">install it in Settings</a>. Manual tags still work (detail view \u2192 +).</div>';}

function filterByCharacter(n,e){closeDrawerAfterPick();detailExitToGallery();if(!n){S.filter.characters=[];S.filter.ratings=[];}else if(e&&(e.ctrlKey||e.metaKey)){var i=S.filter.characters.indexOf(n);if(i>=0)S.filter.characters.splice(i,1);else S.filter.characters.push(n);}else{/* v3.94: clicking the selected entry again clears it -- same rule as folders and star ratings. */S.filter.characters=(S.filter.characters.length===1&&S.filter.characters[0]===n)?[]:[n];}S.selectedImages.clear();if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedChars=null;render();return;}loadImagesReset().then(function(){renderMain();renderTagList();});}

function removeTagChip(n){detailExitToGallery();var i=S.filter.characters.indexOf(n);if(i>=0)S.filter.characters.splice(i,1);S.selectedImages.clear();if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedChars=null;render();return;}loadImagesReset().then(function(){renderMain();renderTagList();});}

async function editTagsSelected(){
    if(!S.selectedImages.size)return;
    var ids=Array.from(S.selectedImages);
    var info=await api('/api/images/tag-info',{method:'POST',body:JSON.stringify({ids:ids})});
    if(info.error)return showToast('Error: '+info.error);
    _renderTagEditor(ids,info);
}

function _renderTagEditor(ids,info){
    var existing=document.getElementById('tagedit-bg');if(existing)existing.remove();
    var bg=document.createElement('div');bg.className='modal-bg';bg.id='tagedit-bg';
    bg.onclick=function(e){if(e.target===bg)bg.remove();};
    var total=info.total||ids.length;
    var tags=info.tags||[];
    var common=tags.filter(function(t){return t.count===total;});
    var partial=tags.filter(function(t){return t.count<total;});
    function tagChip(t){
        var cat=t.category==='character'?' cat-character':(t.category==='rating'?' cat-rating':'');
        var pct=t.count===total?'':' <span class="tagedit-count" style="padding:0 5px">'+t.count+'/'+total+'</span>';
        return '<span class="mltag'+cat+'" title="'+(t.category==='character'?'character':'tag')+' \u00b7 on '+t.count+'/'+total+'">'+esc(t.name)+pct+'<span class="mltag-x" title="Remove from all selected" onclick="removeTagFromSelection(\''+esc(t.name).replace(/\x27/g,"\\\x27")+'\')">\u2715</span></span>';
    }
    var h='<div class="modal-box" style="width:520px"><div class="modal-body" style="max-height:70vh;overflow-y:auto">';
    h+='<h3 style="font-size:15px;margin-bottom:12px;color:var(--text-primary)">Tags ('+tags.length+') \u00b7 '+total+' image'+(total>1?'s':'')+'</h3>';
    h+='<div class="detail-tags">'+(tags.length?tags.map(tagChip).join(''):'<span style="color:var(--text-muted);font-size:12px">no tags</span>')
      +'<button class="add-tag-btn" onclick="var i=document.getElementById(\'tagedit-add-inline\');i.classList.toggle(\'open\');var f=document.getElementById(\'tagedit-add\');if(f)f.focus();" title="Add tag">+</button>'
      +'<div class="add-tag-inline" id="tagedit-add-inline"><input id="tagedit-add" placeholder="Tag name..." onkeydown="if(event.key===\'Enter\'&&!document.querySelector(\'#tagedit-bg .ac-list.open\')){event.preventDefault();addTagToSelection();}"/><button class="char-toggle'+(_charMode?' active':'')+'" onclick="toggleCharMode()" title="Add as character tag (known characters are auto-detected)">CHAR</button></div></div>';
    h+='</div><div class="modal-footer"><button class="modal-btn primary" onclick="document.getElementById(\'tagedit-bg\').remove()">Close</button></div></div>';
    bg.innerHTML=h;document.body.appendChild(bg);
    bg._ids=ids;
    var inp=document.getElementById('tagedit-add');if(inp){attachAutocomplete(inp,{mode:'search',fetchItems:async function(q){var r=await api('/api/suggest-tags?q='+encodeURIComponent(q));return Array.isArray(r)?r:[];}});inp.focus();}
}

async function addTagToSelection(){
    var bg=document.getElementById('tagedit-bg');if(!bg)return;
    var inp=document.getElementById('tagedit-add');if(!inp)return;
    var tag=inp.value.trim();if(!tag)return;
    var ids=bg._ids;
    var r=await api('/api/images/bulk-add-tag',{method:'POST',body:JSON.stringify({ids:ids,tag:tag,type:(_charMode?'character':'auto')})});
    if(r.error)return showToast('Error: '+r.error);
    showToast(r.added+' image'+(r.added!==1?'s':'')+' tagged '+(r.added===0?'(already had it)':'with "'+r.tag+'"'),'success');
    inp.value='';
    // Refresh the list
    var info=await api('/api/images/tag-info',{method:'POST',body:JSON.stringify({ids:ids})});
    _renderTagEditor(ids,info);
    S.tagsModified=true;
    await Promise.all([loadCharacters(),loadImagesReset()]);if(S.page==='gallery')renderMain();renderTagList();
}

async function removeTagFromSelection(tag){
    var bg=document.getElementById('tagedit-bg');if(!bg)return;
    var ids=bg._ids;
    var ok=await showConfirm('Remove tag <strong>'+esc(tag)+'</strong> from all selected images that have it?',[{label:'Cancel',key:'cancel'},{label:'Remove',key:'ok',cls:'danger'}]);
    if(!ok)return;
    var r=await api('/api/images/bulk-remove-tag',{method:'POST',body:JSON.stringify({ids:ids,tag:tag})});
    if(r.error)return showToast('Error: '+r.error);
    var msg=r.removed+' image'+(r.removed!==1?'s':'')+' updated';
    if(r.protected)msg+=' · '+r.protected+' kept (last tag)';
    showToast(msg,'success');
    var info=await api('/api/images/tag-info',{method:'POST',body:JSON.stringify({ids:ids})});
    _renderTagEditor(ids,info);
    S.tagsModified=true;
    await Promise.all([loadCharacters(),loadImagesReset()]);if(S.page==='gallery')renderMain();renderTagList();
}

function addTagBtnHtml(imgId){return '<button class="add-tag-btn" onclick="toggleAddTag('+imgId+')" id="add-tag-toggle" title="Add tag">+</button><div class="add-tag-inline" id="add-tag-inline"><input id="add-tag-input" placeholder="Tag name..." onkeydown="if(event.key===\'Enter\')addTag('+imgId+');if(event.key===\'Escape\')toggleAddTag()"/><button class="char-toggle'+(_charMode?' active':'')+'" onclick="toggleCharMode()" title="Add as character tag (known characters are auto-detected)">CHAR</button></div>';}

function hookAddTagAC(){var ati=document.getElementById('add-tag-input');if(!ati||ati._acAttached)return;ati._acAttached=true;attachAutocomplete(ati,{mode:'search',fetchItems:async function(q){var r=await api('/api/suggest-tags?q='+encodeURIComponent(q)+'&image_id='+S.currentImageId);return Array.isArray(r)?r:[];},onPick:function(name,it){var v=(it&&(it.value||it.name))||name;var inp=document.getElementById('add-tag-input');if(inp)inp.value=v;addTag(S.currentImageId,(it&&it.type==='name')?'character':undefined);}});}

async function retagOne(id){showToast('Re-tagging\u2026','success',true);var r=await api('/api/image/'+id+'/retag',{method:'POST'});if(r&&r.error)return showToast('Error: '+r.error);showToast('Auto-tags reset','success',true);S.tagsModified=true;loadDetailTags(id);}

function toggleAddTag(id){var el=document.getElementById('add-tag-inline');var btn=document.getElementById('add-tag-toggle');if(!el)return;if(el.classList.contains('open')){el.classList.remove('open');if(btn)btn.style.display='';}else{el.classList.add('open');if(btn)btn.style.display='none';var inp=document.getElementById('add-tag-input');if(inp)inp.focus();}}

async function removeAutoTag(id,t,cat){var r=await api('/api/image/'+id+'/remove-tag',{method:'POST',body:JSON.stringify({tag:t})});if(r.error)return showToast('Error: '+r.error);pushUndo({type:'tag_remove',imageId:id,tag:t,cat:cat||''});showToast('"'+t+'" removed','success',true);S.tagsModified=true;loadDetailTags(id);}

var _charMode=false;

function toggleCharMode(){_charMode=!_charMode;document.querySelectorAll('.char-toggle').forEach(function(b){b.classList.toggle('active',_charMode);});}

async function addTag(id,type){var i=document.getElementById('add-tag-input');var t=i?i.value.trim():'';if(!t)return;var r=await api('/api/image/'+id+'/add-tag',{method:'POST',body:JSON.stringify({tag:t,type:type||(_charMode?'character':'auto')})});if(r.error)return showToast('Error: '+r.error);pushUndo({type:'tag_add',imageId:id,tag:t});showToast('Tag added','success',true);if(i)i.value='';toggleAddTag();S.tagsModified=true;loadDetailTags(id);}

async function addIgnoreWord(){var i=document.getElementById('ignore-word-input');var w=i.value.trim();if(!w)return;await api('/api/ignore-words',{method:'POST',body:JSON.stringify({word:w})});i.value='';await loadIgnoreWords();render();showToast('"'+w+'" added','success');}

async function removeIgnoreWord(w){await api('/api/ignore-words',{method:'DELETE',body:JSON.stringify({word:w})});await loadIgnoreWords();render();}

function toggleIgnoreAdd(){var el=document.getElementById('ignore-add-inline');var btn=document.getElementById('ignore-add-toggle');if(!el)return;if(el.classList.contains('open')){el.classList.remove('open');if(btn)btn.style.display='';}else{el.classList.add('open');if(btn)btn.style.display='none';var inp=document.getElementById('ignore-word-input');if(inp)inp.focus();}}

function _tagsOpen(){return localStorage.getItem('ti_tags_open')!=='0';}

function tagsPanelHtml(img){var h='<div class="detail-section-title meta-toggle" onclick="toggleTagsPanel()" style="margin-bottom:10px;cursor:pointer;user-select:none"><span id="tags-arrow">'+(_tagsOpen()?'\u25be':'\u25b8')+'</span> Tags (<span id="tags-count">\u2026</span>) <span title="Reset auto-tags \u2014 re-tag this image (manual tags survive)" onclick="event.stopPropagation();retagOne('+img.id+')" style="margin-left:6px;cursor:pointer;color:var(--text-muted)">\u21bb</span></div>';h+=_tagInstallHint();
h+='<div id="tags-body"'+(_tagsOpen()?'':' style="display:none"')+'><div class="detail-tags" id="detail-tags-box"></div></div>';return h;}

function updateTagActive(){var sel=(S.tagMode==='tags')?(S.filter.tags||[]):S.filter.characters;document.querySelectorAll('.tag-item').forEach(function(el){var t=el.dataset.tag||'';if(t.indexOf('__r')===0){el.classList.toggle('active',S.filter.ratings.indexOf(parseInt(t.slice(3)))>=0);return;}el.classList.toggle('active',(t==='__all')?(!sel.length&&!S.filter.ratings.length):sel.indexOf(t)>=0);});}

/* Same as the folder tree: both copies of the column fold together. */
function toggleTagGroup(letter){S.openTagGroups[letter]=!S.openTagGroups[letter];_lsSave('ti_open_taggroups',S.openTagGroups);var open=S.openTagGroups[letter]!==false;document.querySelectorAll('.tag-group[data-letter="'+letter+'"],.tl-arrow[data-letter="'+letter+'"]').forEach(function(el){el.classList.toggle('open',open);});}

function buildTagsHtml(allCount){
    var h=activeFilterChipsHtml();
    if(S.tagMode==='tags'){
        var sel=S.filter.tags||[];
        h+=_tagInstallHint();
        h+='<div class="tag-item'+((!sel.length&&!S.filter.ratings.length)?' active':'')+'" data-tag="__all" onclick="filterByTag(\'\')"><span>All</span><span class="count">'+allCount+'</span></div>';
        var tags=S.tags||[];
        var _crc={general:'hsl(120,65%,45%)',sensitive:'hsl(35,85%,50%)',explicit:'hsl(0,65%,45%)'};
        var _cro={general:0,sensitive:1,explicit:2};
        var ratingTags=tags.filter(function(t){return t.category==='rating'&&t.name!=='questionable';}).sort(function(a,b){return (_cro[a.name]!=null?_cro[a.name]:9)-(_cro[b.name]!=null?_cro[b.name]:9);});
        /* v3.94: the star ratings are shown here too, pinned above the auto-tag
           ratings, so they can be combined with tags without switching column. */
        var starRows=(S.characters||[]).filter(function(c){return c.id<0;});
        if(starRows.length||ratingTags.length){h+='<div class="tag-fixed">';}
        starRows.forEach(function(c){h+='<div class="tag-item'+(S.filter.ratings.indexOf(parseInt(c.name))>=0?' active':'')+'" data-tag="__r'+c.name+'" onclick="filterByRating('+c.name+',event)"><span style="color:'+ratingColor(c.name)+';font-weight:700">\u2605 '+c.name+'</span><span class="count">'+c.image_count+'</span></div>';});
        if(ratingTags.length){ratingTags.forEach(function(t){h+='<div class="tag-item'+(sel.indexOf(t.name)>=0?' active':'')+'" data-tag="'+esc(t.name)+'" onclick="filterByTag(this.dataset.tag,event)"><span style="color:'+(_crc[t.name]||'inherit')+';font-weight:700">'+esc(t.name)+'</span><span class="count">'+t.image_count+'</span></div>';});}
        if(starRows.length||ratingTags.length){h+='</div>';}
        tags=tags.filter(function(t){return t.category!=='rating';});
        if(!tags.length&&!ratingTags.length&&_tagAvail()){h+='<div style="padding:10px 12px;color:var(--text-muted);font-size:12px;line-height:1.5">No auto-tags yet \u2014 tagging runs automatically in the background.</div>';}
        tags.forEach(function(t){
            var cat=(t.category&&t.category!=='general')?'<span class="tcat">'+esc(String(t.category).slice(0,4))+'</span>':'';
            h+='<div class="tag-item'+(sel.indexOf(t.name)>=0?' active':'')+'" data-tag="'+esc(t.name)+'" onclick="filterByTag(this.dataset.tag,event)"><span>'+esc(t.name)+cat+'</span><span class="count">'+t.image_count+'</span></div>';
        });
        return h;
    }
    h+='<div class="tag-item'+((!S.filter.characters.length&&!S.filter.ratings.length)?' active':'')+'" data-tag="__all" onclick="filterByCharacter(\'\')"><span>All</span><span class="count">'+allCount+'</span></div>';
    var unknowns=[];var grouped={};var ratingRows=[];
    S.characters.forEach(function(c){
        if(c.id<0){ratingRows.push(c);return;}
        if(c.name.toLowerCase()==='unknown'){unknowns.push(c);return;}
        var first=c.name.charAt(0).toUpperCase();
        if(!/[A-Z]/.test(first))first='#';
        if(!grouped[first])grouped[first]=[];
        grouped[first].push(c);
    });
    if(ratingRows.length){h+='<div class="tag-fixed">';ratingRows.forEach(function(c){h+='<div class="tag-item'+(S.filter.ratings.indexOf(parseInt(c.name))>=0?' active':'')+'" data-tag="__r'+c.name+'" onclick="filterByRating('+c.name+',event)"><span style="color:'+ratingColor(c.name)+';font-weight:700">\u2605 '+c.name+'</span><span class="count">'+c.image_count+'</span></div>';});h+='</div>';}
    unknowns.forEach(function(c){
        h+='<div class="tag-item'+(S.filter.characters.indexOf(c.name)>=0?' active':'')+'" data-tag="'+esc(c.name)+'" onclick="filterByCharacter(this.dataset.tag,event)"><span>'+esc(c.name)+'</span><span class="count">'+c.image_count+'</span></div>';
    });
    var letters=Object.keys(grouped).sort();
    letters.forEach(function(letter){
        var isOpen=S.openTagGroups[letter]!==false;
        h+='<div class="tag-letter" onclick="toggleTagGroup(\''+letter+'\')"><span class="tl-arrow'+(isOpen?' open':'')+'" id="tga-'+letter+'" data-letter="'+letter+'">\u25b6</span>'+letter+'</div>';
        h+='<div class="tag-group'+(isOpen?' open':'')+'" data-letter="'+letter+'">';
        grouped[letter].forEach(function(c){
            h+='<div class="tag-item'+(S.filter.characters.indexOf(c.name)>=0?' active':'')+'" data-tag="'+esc(c.name)+'" onclick="filterByCharacter(this.dataset.tag,event)"><span>'+esc(c.name)+'</span><span class="count">'+c.image_count+'</span></div>';
        });
        h+='</div>';
    });
    return h;
}

function renderTagList(){var els=document.querySelectorAll('.tag-list');if(!els.length)return;var allCount=S.filter.search?(S.filteredTotal||0):getFolderTotal();var html=buildTagsHtml(allCount);for(var i=0;i<els.length;i++)els[i].innerHTML=html;}

function setTagMode(m){m=(m==='tags')?'tags':'names';if(S.tagMode===m)return;S.tagMode=m;localStorage.setItem('ti_tagmode',m);loadCharacters().then(function(){rerenderTagCol();});}

function tagColInner(allCount){var nm=S.tagMode!=='tags';return '<div class="sidebar-title sidebar-toggle"><span class="seg'+(nm?' active':'')+'" onclick="setTagMode(\'names\')">Names'+(S.filter.characters.length?'<span class="seg-dot"></span>':'')+'</span><span class="seg'+(!nm?' active':'')+'" onclick="setTagMode(\'tags\')">Tags'+((S.filter.tags&&S.filter.tags.length)?'<span class="seg-dot"></span>':'')+'</span><span class="col-collapse-btn" onclick="toggleSidebarCol(\'tags\')" title="Collapse">\u25C0</span></div><div class="tag-list" id="tag-list-container">'+buildTagsHtml(allCount)+'</div>';}

/* v4.56: same as the folder column -- the open picture has its own copy. */
function rerenderTagCol(){var cols=document.querySelectorAll('.tags-col');if(!cols.length)return;var allCount=S.filter.search?(S.filteredTotal||0):getFolderTotal();var html=tagColInner(allCount);for(var i=0;i<cols.length;i++)cols[i].innerHTML=html;}

function filterByTag(n,e){closeDrawerAfterPick();detailExitToGallery();if(!S.filter.tags)S.filter.tags=[];if(!n){S.filter.tags=[];}else if(e&&(e.ctrlKey||e.metaKey)){var i=S.filter.tags.indexOf(n);if(i>=0)S.filter.tags.splice(i,1);else S.filter.tags.push(n);}else{/* v3.94: clicking the selected entry again clears it -- same rule as folders and star ratings. */S.filter.tags=(S.filter.tags.length===1&&S.filter.tags[0]===n)?[]:[n];}S.selectedImages.clear();if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;render();return;}loadImagesReset().then(function(){renderMain();renderTagList();});}

function removeTagFilterChip(n){if(!S.filter.tags)return;detailExitToGallery();var i=S.filter.tags.indexOf(n);if(i>=0)S.filter.tags.splice(i,1);S.selectedImages.clear();if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedChars=null;render();return;}loadImagesReset().then(function(){renderMain();renderTagList();});}

function _crColor(n){return n==='general'?'hsl(120,65%,45%)':(n==='sensitive'?'hsl(35,85%,50%)':'hsl(0,65%,45%)');}

function buildDetailMLTagsHtml(tags,tagged,imgId){if(!tags||!tags.length){return (tagged?'<span style="color:var(--text-muted);font-size:12px">no tags</span>':'')+addTagBtnHtml(imgId);}var q=((S.filter&&S.filter.search)||'').trim().toLowerCase();var rank={rating:0,character:1,general:2,other:3};var sorted=tags.slice().sort(function(a,b){if(q){var am=(a.name||'').toLowerCase().indexOf(q)>=0?0:1,bm=(b.name||'').toLowerCase().indexOf(q)>=0?0:1;if(am!==bm)return am-bm;}var ar=(rank[a.category]!=null?rank[a.category]:9),br=(rank[b.category]!=null?rank[b.category]:9);if(ar!==br)return ar-br;return (b.score||0)-(a.score||0);});var h='';sorted.forEach(function(t){var cat=t.category==='character'?' cat-character':(t.category==='rating'?' cat-rating':'');var hl=(q&&(t.name||'').toLowerCase().indexOf(q)>=0)?' mltag-match':'';var st=t.category==='rating'?' style="color:'+_crColor(t.name)+';font-weight:700"':'';h+='<span class="mltag'+cat+hl+'"'+st+' title="'+(t.category==='character'?'character':'tag')+(t.score!=null?(' \u00b7 score '+t.score):'')+'" onclick="tagFromDetail(\''+esc(t.name)+'\')">'+esc(t.name)+'<span class="mltag-x" title="Remove tag" onclick="event.stopPropagation();removeAutoTag('+imgId+',\''+esc(t.name)+'\',\''+esc(t.category||'')+'\')">\u2715</span></span>';});return h+addTagBtnHtml(imgId);}

async function loadDetailTags(id){try{var r=await api('/api/image/'+id);if(r&&S.currentImageId===id){var box=document.getElementById('detail-tags-box');if(box){box.innerHTML=buildDetailMLTagsHtml(r.tags,r.tagged,id);hookAddTagAC();}var tc=document.getElementById('tags-count');if(tc)tc.textContent=(r.tags&&r.tags.length)||0;}}catch(_){}}

function tagFromDetail(name){closeDetail();S.tagMode='tags';S.filter.tags=[name];S.selectedImages.clear();Promise.all([loadCharacters(),loadImagesReset()]).then(function(){render();});}

function _tagStatusHtml(tg){tg=tg||{};return '<span class="tag-status-line">'+_tagStatusInner(tg)+'</span>'+benchLine(tg);}

function _tagStatusInner(tg){tg=tg||{};var dl=tg.model_download||{};
/* Whether it is installed or not, the card and the runtime belong in this block
   -- see runtimeSelectHtml. */
if(dl.active){
  if(dl.phase==='runtime'){var am=Math.round((dl.all_done||0)/1048576),at=Math.round((dl.all_total||0)/1048576),ap=(dl.all_total?Math.min(99,Math.round(dl.all_done*100/dl.all_total)):0);if(dl.step==='installing')return '<div class="proc-hint" style="color:var(--accent-light)">Unpacking the packages into the venv \u2014 pip reports no progress for this step, it is the last one.</div>';var fp=(dl.total?Math.round(dl.done*100/dl.total):0),fm=Math.round((dl.done||0)/1048576),ft=Math.round((dl.total||0)/1048576);return '<div class="proc-hint" style="color:var(--accent-light)">Installing the runtime: <b>'+esc(dl.file||'onnxruntime')+'</b>'+(dl.total?(' \u2014 '+fp+'% ('+fm+' / '+ft+' MB)'):'')+'<br>Total '+am+' / ~'+at+' MB \u00b7 '+ap+'% \u2014 one-time, this can take a few minutes.'+(dl.error?' \u00b7 <span style="color:var(--danger)">'+esc(dl.error)+'</span>':'')+'</div>';}
  var mb=Math.round((dl.done||0)/1048576),tot=Math.round((dl.total||0)/1048576),pc=dl.total?Math.round(dl.done*100/dl.total):0;
  return '<div class="proc-hint" style="color:var(--accent-light)">Downloading the model: <b>'+esc(dl.file||'')+'</b> \u2014 '+pc+'% ('+mb+(tot?' / '+tot:'')+' MB)'+(dl.error?' \u00b7 <span style="color:var(--danger)">'+esc(dl.error)+'</span>':'')+' \u2014 the whole library is tagged automatically when done.</div>';
}
if(!tg.runtime||!tg.model){
  /* v4.23: the size depends on which runtime is going to be fetched, so the
     choice belongs on the same line as the button rather than in a card of its
     own further up. CUDA is ~2.5 GB, DirectML ~25 MB, the processor ~15 MB. */
  var rtk=(_venv&&_venv.runtime)||'cuda';
  var rtMB={cuda:2500,dml:25,cpu:15}[rtk]||2500;
  var modMB=1200;
  var totMB=(!tg.runtime?rtMB:0)+(!tg.model?modMB:0);
  var sz=(totMB>=1000?('~'+(totMB/1000).toFixed(1)+' GB'):('~'+totMB+' MB'));
  var what=(!tg.runtime&&!tg.model)?'runtime + model':(!tg.runtime?'the runtime':'the model');
  return '<div class="proc-hint">Auto-tagging is <b>not installed</b>.'+(dl.error?' <span style="color:var(--danger)">'+esc(dl.error)+'</span>':'')+
    '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0">'+
    '<button class="btn btn-sm btn-primary" onclick="installTagging()">Install auto-tagging ('+sz+')</button>'+
    runtimeSelectHtml()+'</div>'+
    'Installs '+what+' into this folder only \u2014 nothing else on the machine is touched. Existing images are tagged retroactively.'+
    hardwareLineHtml()+'</div>';
}
return '<div class="proc-hint">Runtime ready \u00b7 device <b>'+esc(tg.device||'\u2014')+'</b>'+(tg.error?' \u00b7 <span style="color:var(--danger)">'+esc(tg.error)+'</span>':'')+
  '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0">'+runtimeSelectHtml()+
  '<button class="btn btn-sm" onclick="installTagging()">Reinstall with this runtime</button></div>'+
  hardwareLineHtml()+'</div>';}

function _tagStatText(d){d=d||{};var done=d.done||0,total=d.total||0,pend=d.pending||0;if(d.running){var s='<b>'+done+'</b> / '+total+' tagged \u00b7 '+pend+' pending';var r=_fpsRate(_tagRate,done);if(pend>0&&r>=0.2){s+=' \u00b7 <b>'+(r>=10?Math.round(r):r.toFixed(1))+'</b>/s';var et=_fmtEta(pend/r);if(et)s+=' \u00b7 ~'+et+' left';}else if(d.active){s+=' \u00b7 working\u2026';}return s;}_resetRate(_tagRate);if(pend>0)return '<b>'+done+'</b> / '+total+' tagged \u00b7 '+pend+' pending';return total>0?('\u2713 All '+total+' images tagged'):'No images yet';}
