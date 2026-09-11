/* Dialogs.
 *
 * File 12 of 13 — the page loads these in number order.
 */

function pushUndo(entry){S.undoStack.push(entry);if(S.undoStack.length>50)S.undoStack.shift();}

function showModal(opts){
    /* opts: {body, buttons:[{label,key,cls}], input:bool}
       Returns Promise → clicked button key, or null on Escape/backdrop.
       If input:true, returns {key,value} or null. */
    return new Promise(function(resolve){
        var bg=document.createElement('div');bg.className='modal-bg';bg.id='modal-bg';
        var h='<div class="modal-box"><div class="modal-body">'+opts.body+'</div><div class="modal-footer">';
        (opts.buttons||[]).forEach(function(b){h+='<button class="modal-btn '+(b.cls||'')+'" data-key="'+esc(b.key)+'">'+esc(b.label)+'</button>';});
        h+='</div></div>';bg.innerHTML=h;
        function done(key){bg.remove();document.removeEventListener('keydown',onKey,true);resolve(key);}
        function onKey(e){
            if(e.key==='Escape'){var acl=bg.querySelector('.ac-list.open');if(acl){acl.classList.remove('open');e.stopPropagation();return;}e.stopPropagation();done(null);return;}
            if(e.key==='Enter'&&opts.input){var acl2=bg.querySelector('.ac-list.open');if(acl2)return;var inp=bg.querySelector('.modal-input');if(inp){e.preventDefault();var pk=(opts.buttons.find(function(b){return b.cls&&b.cls.indexOf('primary')>=0;})||opts.buttons[0]);done({key:pk.key,value:inp.value});return;}}
            if(e.key==='Enter'&&!opts.input){var pk=(opts.buttons.find(function(b){return b.cls&&b.cls.indexOf('primary')>=0;}));if(pk){e.preventDefault();done(pk.key);}}
        }
        bg.addEventListener('click',function(e){
            if(e.target===bg){done(null);return;}
            var btn=e.target.closest('.modal-btn');if(!btn)return;
            var key=btn.dataset.key;
            if(opts.input){var inp=bg.querySelector('.modal-input');done(key==='cancel'?null:{key:key,value:inp?inp.value:''});}
            else done(key);
        });
        document.addEventListener('keydown',onKey,true);
        document.body.appendChild(bg);
        var focus=bg.querySelector('.modal-input');
        if(focus){focus.focus();focus.select();}
        else{var btns=bg.querySelectorAll('.modal-btn');if(btns.length)btns[btns.length-1].focus();}
        if(opts.afterMount)opts.afterMount(bg);
    });
}

async function showConfirm(msg,buttons){
    if(!buttons)buttons=[{label:'Cancel',key:'cancel'},{label:'OK',key:'ok',cls:'primary'}];
    var r=await showModal({body:msg,buttons:buttons});
    if(!buttons||(buttons.length===2&&buttons[1].key==='ok'))return r==='ok';
    return r;
}

async function showPrompt(msg,defaultVal,hint,acOpts){
    var body=msg+'<input class="modal-input" value="'+(defaultVal!=null?esc(String(defaultVal)):'')+'">'+(hint?'<div class="modal-hint">'+hint+'</div>':'');
    var r=await showModal({body:body,input:true,buttons:[{label:'Cancel',key:'cancel'},{label:'OK',key:'ok',cls:'primary'}],
        afterMount:acOpts?function(bg){var inp=bg.querySelector('.modal-input');if(inp)attachAutocomplete(inp,acOpts);}:null});
    return r&&r.key==='ok'?r.value:null;
}

function attachAutocomplete(input,opts){
    /* opts: {getItems:fn→[{name,count}], onPick:fn(name,input), mode:'search'|'rename'} */
    var list=document.createElement('div');list.className='ac-list';
    input.parentElement.classList.add('ac-wrap');
    input.parentElement.appendChild(list);
    var idx=-1,items=[];
    function getSegment(){
        if(opts.mode==='rename'){
            var v=input.value,c=input.selectionStart||v.length;
            var before=v.substring(0,c);
            var sepMatch=before.match(/.*[+\-,]/);
            var start=sepMatch?sepMatch[0].length:0;
            var after=v.substring(c);
            var endMatch=after.match(/[+\-,]/);
            var end=c+(endMatch?endMatch.index:after.length);
            return {text:v.substring(start,end).replace(/_/g,' ').trim(),start:start,end:end};
        }
        /* search mode (v3.46): the WHOLE box is one term — spaces belong to it */
        var v2=input.value;
        return {text:v2.trim(),start:0,end:v2.length};
    }
    function render(){
        if(!items.length){list.classList.remove('open');return;}
        var seg=getSegment();
        var q=seg.text.toLowerCase();
        var h='';items.forEach(function(it,i){
            var n=it.name,nl=n.toLowerCase(),pos=nl.indexOf(q);
            var display=pos>=0?esc(n.substring(0,pos))+'<mark>'+esc(n.substring(pos,pos+q.length))+'</mark>'+esc(n.substring(pos+q.length)):esc(n);
            var typeLabel=it.type==='meta'?'<span class="ac-type">meta</span>':it.type==='folder'?'<span class="ac-type ac-t-folder">folder</span>':it.type==='tag'?'<span class="ac-type ac-t-char">name</span>':it.type==='name'?'<span class="ac-type ac-t-char">character</span>':(it.type==='mltag'||it.type==='auto')?'<span class="ac-type ac-t-tag">tag</span>':'';
            h+='<div class="ac-item'+(i===idx?' active':'')+'" data-idx="'+i+'"'+(it.hint?' title="'+esc(it.hint)+'"':'')+'><span class="ac-name">'+display+typeLabel+'</span><span class="ac-count">'+it.count+'</span></div>';
        });
        list.innerHTML=h;list.classList.add('open');
    }
    var _fetchTimer=null;
    function update(){
        var seg=getSegment();var q=seg.text.toLowerCase();
        idx=-1;
        if(q.length<1){items=[];list.classList.remove('open');return;}
        if(opts.fetchItems){
            /* Remote async fetch with debounce */
            clearTimeout(_fetchTimer);
            _fetchTimer=setTimeout(async function(){
                try{
                    items=await opts.fetchItems(q);
                    if(items.length===1&&items[0].name.toLowerCase()===q){items=[];list.classList.remove('open');return;}
                    render();
                }catch(e){items=[];list.classList.remove('open');}
            },120);
            return;
        }
        var all=opts.getItems();
        items=all.filter(function(it){return it.name.toLowerCase().indexOf(q)>=0&&it.name.toLowerCase()!=='unknown';});
        items.sort(function(a,b){
            var al=a.name.toLowerCase(),bl=b.name.toLowerCase();
            var aStart=al.indexOf(q)===0?0:1,bStart=bl.indexOf(q)===0?0:1;
            if(aStart!==bStart)return aStart-bStart;
            return b.count-a.count;
        });
        items=items.slice(0,8);
        if(items.length===1&&items[0].name.toLowerCase()===q){items=[];list.classList.remove('open');return;}
        render();
    }
    function pick(i){
        var it=items[i];if(!it)return;
        var seg=getSegment();
        if(opts.mode==='rename'){
            var underscored=it.name.replace(/ /g,'_');
            input.value=input.value.substring(0,seg.start)+underscored+input.value.substring(seg.end);
            input.focus();
            var newPos=seg.start+underscored.length;
            input.setSelectionRange(newPos,newPos);
        }else{
            var prefix=input.value.substring(0,seg.start);
            input.value=prefix+it.name;
            input.focus();
        }
        items=[];list.classList.remove('open');idx=-1;
        if(opts.onPick)opts.onPick(it.name,it);
    }
    input.addEventListener('input',update);
    input.addEventListener('keydown',function(e){
        if(!items.length||!list.classList.contains('open'))return;
        if(e.key==='ArrowDown'){e.preventDefault();idx=Math.min(idx+1,items.length-1);render();}
        else if(e.key==='ArrowUp'){e.preventDefault();idx=Math.max(idx-1,0);render();}
        else if(e.key==='Tab'){if(idx<0)idx=0;e.preventDefault();e.stopPropagation();pick(idx);}
        else if(e.key==='Enter'){if(idx>=0){e.preventDefault();e.stopPropagation();pick(idx);}else{items=[];list.classList.remove('open');idx=-1;}}
        else if(e.key==='Escape'){items=[];list.classList.remove('open');idx=-1;}
    },true);
    list.addEventListener('mousedown',function(e){
        e.preventDefault();/* prevent blur */
        var el=e.target.closest('.ac-item');if(!el)return;
        pick(parseInt(el.dataset.idx));
    });
    input.addEventListener('blur',function(){setTimeout(function(){items=[];list.classList.remove('open');idx=-1;},150);});
    return {update:update,destroy:function(){list.remove();}};
}

async function globalNameSuggest(q){var r=await api('/api/suggest?q='+encodeURIComponent(q));return (Array.isArray(r)?r:[]).filter(function(it){return it.type==='tag';});}

async function performUndo(){
    if(!S.undoStack.length){showToast('Nothing to undo');return;}
    var u=S.undoStack.pop();
    try{
    if(u.type==='rename'){
        await api('/api/image/'+u.imageId+'/rename',{method:'POST',body:JSON.stringify({filename:u.oldFilename})});
        showToast('Undo: renamed back to '+u.oldFilename,'success');
        if(S.page==='detail'){S.images[S.currentImageIndex].filename=u.oldFilename;showDetailOverlay();}
    }else if(u.type==='rename_bulk'){
        var fail=0;
        for(var i=0;i<u.entries.length;i++){
            var rr=await api('/api/image/'+u.entries[i].id+'/rename',{method:'POST',body:JSON.stringify({filename:u.entries[i].old_filename,auto_increment:true})});
            if(rr.error)fail++;
        }
        showToast('Undo: '+u.entries.length+' files renamed back'+(fail?' ('+fail+' failed)':''),'success');
    }else if(u.type==='move'){
        await api('/api/image/'+u.imageId+'/move',{method:'POST',body:JSON.stringify({folder:u.oldFolder})});
        showToast('Undo: moved back','success');
    }else if(u.type==='import_move'){
        var ur=await api('/api/import/undo-move',{method:'POST',body:JSON.stringify({entries:u.entries})});
        var okN=(ur&&ur.restored)||0,bad=(ur&&ur.failed)||[];
        showToast('Undo: '+okN+' file'+(okN!==1?'s':'')+' put back where '+(okN!==1?'they':'it')+' came from'
            +(bad.length?(' \u2014 '+bad.length+' could not be'):''),bad.length?'error':'success');
        await loadImagesReset();render();
    }else if(u.type==='move_bulk'){
        for(var i=0;i<u.moves.length;i++){await api('/api/image/'+u.moves[i].id+'/move',{method:'POST',body:JSON.stringify({folder:u.moves[i].folder})});}
        showToast('Undo: '+u.moves.length+' files moved back','success');
    }else if(u.type==='delete'){
        await api('/api/restore/'+u.trashId,{method:'POST'});
        showToast('Undo: restored','success');
    }else if(u.type==='delete_bulk'){
        await api('/api/bulk-restore',{method:'POST',body:JSON.stringify({trash_ids:u.trashIds})});
        showToast('Undo: '+u.trashIds.length+' files restored','success');
    }else if(u.type==='tag_add'){
        await api('/api/image/'+u.imageId+'/remove-tag',{method:'POST',body:JSON.stringify({tag:u.tag})});
        showToast('Undo: tag "'+u.tag+'" removed','success');
        if(S.page==='detail'&&S.currentImageId===u.imageId)loadDetailTags(u.imageId);
    }else if(u.type==='tag_remove'){
        await api('/api/image/'+u.imageId+'/add-tag',{method:'POST',body:JSON.stringify({tag:u.tag,type:(u.cat==='character')?'character':(u.cat==='general'?'general':'auto')})});
        showToast('Undo: tag "'+u.tag+'" restored','success');
        if(S.page==='detail'&&S.currentImageId===u.imageId)loadDetailTags(u.imageId);
    }else if(u.type==='folder_create'){
        await api('/api/delete-folder',{method:'POST',body:JSON.stringify({folder:u.folder})});
        showToast('Undo: folder deleted','success');
    }
    S.tagsModified=true;
    await Promise.all([loadImagesReset(),loadCharacters(),loadFolders(),loadStats()]);
    if(S.page==='gallery'){renderMain();renderTagList();renderFolderSidebar();}else if(S.page==='detail'){renderTagList();}
    }catch(e){showToast('Undo failed: '+e.message);}
}

function hideCtx(){var m=document.getElementById('ctx-menu');if(m)m.remove();}

async function bulkDeleteSelected(){
    var n=S.selectedImages.size;if(!n)return;
    if(!await showConfirm('Delete <strong>'+n+' image'+(n>1?'s':'')+'</strong>?',[{label:'Cancel',key:'cancel'},{label:'Delete',key:'ok',cls:'danger'}]))return;
    var ids=Array.from(S.selectedImages);
    var r=await api('/api/images/bulk-delete',{method:'POST',body:JSON.stringify({ids:ids})});
    if(r.error)return showToast('Error: '+r.error);
    if(r.trash_ids&&r.trash_ids.length)pushUndo({type:'delete_bulk',trashIds:r.trash_ids});
    showToast(r.deleted+' deleted','success',true);
    S.selectedImages.clear();
    if(S.page==='duplicates'&&S.dupGroups){var idSet=new Set(ids);S.dupGroups.forEach(function(g){for(var i=g.images.length-1;i>=0;i--){if(idSet.has(g.images[i].id))g.images.splice(i,1);}});S.dupGroups=S.dupGroups.filter(function(g){return g.images.length>1;});var dr=document.getElementById('dup-results');if(dr)dr.innerHTML=renderDupGroups(S.dupGroups);var totalDups=S.dupGroups.reduce(function(a,g){return a+g.images.length;},0);var st=document.getElementById('dup-stats');if(st)st.textContent=S.dupGroups.length+' group'+(S.dupGroups.length!==1?'s':'')+' \u00b7 '+totalDups+' images';updateDupSelectionUI();return;}
    await Promise.all([loadImagesReset(),loadCharacters(),loadFolders(),loadStats()]);
    renderMain();renderTagList();renderFolderSidebar();
}

async function bulkOpenExplorer(){
    var ids=Array.from(S.selectedImages);if(!ids.length)return;
    for(var i=0;i<ids.length;i++){await api('/api/image/'+ids[i]+'/open-explorer',{method:'POST'});}
}

async function bulkRenameSelected(){
    var n=S.selectedImages.size;if(!n)return;
    var hint='<b>_</b> connects name parts → John_Doe = <i>John Doe</i><br><b>+ - ,</b> separate characters → John_Doe+Jane = <i>John Doe, Jane</i>'+(n>1?'<br>'+n+' files will be numbered.':'');
    var base=await showPrompt('New filename base:','',hint,{mode:'rename',fetchItems:globalNameSuggest});
    if(!base||!base.trim())return;
    base=base.trim();
    var ids=Array.from(S.selectedImages);
    var ordered=[];document.querySelectorAll('.gallery-item[data-id]').forEach(function(el){var did=parseInt(el.dataset.id);if(ids.indexOf(did)>=0)ordered.push(did);});if(!ordered.length)ordered=S.images.filter(function(img){return ids.indexOf(img.id)>=0;}).map(function(img){return img.id;});
    var contNum=true;
    var customStart=null;
    var firstImg=S.images.find(function(img){return ordered.indexOf(img.id)>=0;});
    var mt=firstImg?firstImg.media_type||'image':'image';
    var nn=await api('/api/next-number',{method:'POST',body:JSON.stringify({base_name:base,exclude_ids:ordered,media_type:mt})});
    if(nn.next&&nn.next>1){
        var label=n>1?n+' files will be renamed as':'File will be renamed as';
        var choice=await showConfirm(label+' <strong>'+esc(base)+' (N)</strong>',
            [{label:'Cancel',key:'cancel'},{label:'Start from (1)',key:'restart'},{label:'Start from …',key:'custom'},{label:'Continue from ('+nn.next+')',key:'continue',cls:'primary'}]);
        if(!choice||choice==='cancel')return;
        if(choice==='custom'){
            var num=await showPrompt('Start numbering from:',String(nn.next>1?nn.next-1:1));
            if(!num)return;
            num=parseInt(num);
            if(isNaN(num)||num<1){showToast('Invalid number');return;}
            customStart=num;contNum=false;
        } else {
            contNum=(choice==='continue');
        }
    }
    var body={ids:ordered,base_name:base,continue_numbering:contNum};
    if(customStart!==null)body.start_number=customStart;
    var r=await api('/api/images/bulk-rename',{method:'POST',body:JSON.stringify(body)});
    if(r.error)return showToast('Error: '+r.error);
    if(r.old_names&&r.old_names.length)pushUndo({type:'rename_bulk',entries:r.old_names});
    showToast(r.renamed+' renamed','success',true);
    S.selectedImages.clear();
    await Promise.all([loadImagesPreserve(),loadCharacters(),loadStats()]);
    renderMain();renderTagList();
}

async function bulkRemoveMetadata(){
    var n=S.selectedImages.size;if(!n)return;
    var msg='Remove metadata from <strong>'+n+' image'+(n>1?'s':'')+'</strong>?\n\n<span class="warn">This permanently strips EXIF, prompts, and other embedded data from the original files. Cannot be undone.</span>';
    var r1=await showConfirm(msg,[{label:'Cancel',key:'cancel'},{label:'Remove Metadata',key:'ok',cls:'danger'}]);
    if(!r1)return;
    var ids=Array.from(S.selectedImages);
    var r=await api('/api/images/bulk-remove-metadata',{method:'POST',body:JSON.stringify({ids:ids})});
    if(r.error)return showToast('Error: '+r.error);
    var msg2=(r.stripped||0)+' cleaned';
    if(r.skipped)msg2+=' · '+r.skipped+' skipped';
    showToast(msg2,'success');
    if(r.errors&&r.errors.length)console.warn('Remove metadata issues:',r.errors);
    await loadImagesPreserve();if(S.page==='gallery')renderMain();
}

async function removeMetadataSingle(id){
    var r1=await showConfirm('Remove metadata from this image?\n\n<span class="warn">Permanently strips EXIF, prompts, and embedded data. Cannot be undone.</span>',[{label:'Cancel',key:'cancel'},{label:'Remove Metadata',key:'ok',cls:'danger'}]);
    if(!r1)return;
    var r=await api('/api/image/'+id+'/remove-metadata',{method:'POST'});
    if(r.error)return showToast('Error: '+r.error);
    showToast('Metadata removed','success');
    if(S.page==='detail'){await loadMetadata(id);}
    await loadImagesPreserve();if(S.page==='gallery')renderMain();
}

function bustImageCaches(id){var t=Date.now();document.querySelectorAll('img').forEach(function(im){var s=im.getAttribute('src')||'';if(s.indexOf('/thumb/'+id+'?')===0||s.indexOf('/full/'+id)===0){s=s.replace(/[?&]v=\d+/,'');im.src=s+(s.indexOf('?')>=0?'&':'?')+'v='+t;}});}

function copyToClipboard(){var ids=Array.from(S.selectedImages);if(!ids.length)return;osClipboard(ids,'file',true);S.clipboard={ids:ids,mode:'copy'};updateClipboardUI();showToast(ids.length+' item'+(ids.length>1?'s':'')+' copied','success');}

function cutToClipboard(){var ids=Array.from(S.selectedImages);if(!ids.length)return;S.clipboard={ids:ids,mode:'cut'};updateClipboardUI();showToast(ids.length+' item'+(ids.length>1?'s':'')+' cut','success');}

function clearClipboard(){S.clipboard={ids:[],mode:null};updateClipboardUI();}

function updateClipboardUI(){updateQaState();var el=document.getElementById('cb-info');var chip=document.getElementById('cb-chip');if(!el||!chip)return;if(S.clipboard.ids.length){el.style.display='flex';chip.textContent=(S.clipboard.mode==='cut'?'':'')+S.clipboard.ids.length+' clipboard';chip.className='cb-chip'+(S.clipboard.mode==='cut'?' cut':'');}else el.style.display='none';}

async function pasteIntoFolder(targetFolder){
    if(!S.clipboard.ids.length)return showToast('Clipboard is empty');
    var ids=S.clipboard.ids.slice();var mode=S.clipboard.mode;
    var r;
    if(mode==='cut'){r=await api('/api/images/bulk-move',{method:'POST',body:JSON.stringify({ids:ids,folder:targetFolder})});}
    else{r=await api('/api/images/bulk-copy',{method:'POST',body:JSON.stringify({ids:ids,folder:targetFolder})});}
    if(r.error)return showToast('Error: '+r.error);
    showToast((r.moved||r.copied||0)+' item'+((r.moved||r.copied||0)!==1?'s':'')+' '+(mode==='cut'?'moved':'copied'),'success');
    if(mode==='cut')clearClipboard();
    S.selectedImages.clear();
    if(S.page==='duplicates'){if(mode!=='cut'||!dupApplyMove(ids,targetFolder))Promise.all([loadImagesPreserve(),loadFolders(),loadCharacters(),loadStats()]);return;}
    await Promise.all([loadImagesPreserve(),loadFolders(),loadCharacters(),loadStats()]);
    renderMain();renderTagList();renderFolderSidebar();
}

async function pasteAtCurrent(){
    if(!S.clipboard.ids.length)return showToast('Clipboard is empty');
    // Prefer active folder filter; if none, infer from first visible image
    var target=curFolder();
    if(!target&&S.images.length)target=S.images[0].folder;
    if(!target)return showToast('Open a folder first to paste into');
    await pasteIntoFolder(target);
}

function showGalleryCtx(e,imgId,inDetail){
    e.preventDefault();e.stopPropagation();hideCtx();
    var _cd=inDetail?'closeDetail();':'';
    if(!S.selectedImages.has(imgId)){S.selectedImages.clear();S.selectedImages.add(imgId);if(S.page==='duplicates')updateDupSelectionUI();else updateSelectionUI();}
    var n=S.selectedImages.size;var label=n>1?n+' images':'image';
    var m=document.createElement('div');m.className='ctx-menu';m.id='ctx-menu';
    var html='<div class="ctx-menu-item" onclick="hideCtx();bulkOpenExplorer()">'+ICO.explorer+'Open in Explorer</div>'
        +'<div class="ctx-menu-item" onclick="hideCtx();'+_cd+'showMoveModal()">'+ICO.move+'Move to folder…</div>'
        +'<div class="ctx-menu-sep"></div>'
        +'<div class="ctx-menu-item" onclick="hideCtx();copyToClipboard()">'+ICO.copy+'Copy '+label+'</div>'
        +'<div class="ctx-menu-item" onclick="hideCtx();copyImageToOS()">'+ICO.osimg+'Copy as picture</div>'
        +'<div class="ctx-menu-item" onclick="hideCtx();cutToClipboard()">'+ICO.cut+'Cut '+label+'</div>';
    if(S.clipboard&&S.clipboard.ids.length){
        var img=S.images.find(function(i){return i.id===imgId;});
        var target=img?img.folder:curFolder();
        html+='<div class="ctx-menu-item" onclick="hideCtx();pasteIntoFolder(\''+esc(target).replace(/\\/g,"\\\\").replace(/\x27/g,"\\\x27")+'\')">'+ICO.paste+'Paste '+S.clipboard.ids.length+' item'+(S.clipboard.ids.length>1?'s':'')+' into '+esc(target||'current')+'</div>';
    }
    html+='<div class="ctx-menu-sep"></div>'
        +(n===1?'<div class="ctx-menu-item" onclick="hideCtx();'+_cd+'renameFromCtx('+imgId+')">'+ICO.rename+'Rename</div>':'<div class="ctx-menu-item" onclick="hideCtx();'+_cd+'bulkRenameSelected()">'+ICO.rename+'Rename '+n+' files</div>')
        +'<div class="ctx-menu-item" onclick="hideCtx();'+_cd+'editTagsSelected()">'+ICO.tags+'Edit tags'+(n>1?' for '+n+' files':'')+'</div>'
        +(n===1?'<div class="ctx-menu-item gold" onclick="hideCtx();removeMetadataSingle('+imgId+')">'+ICO.meta+'Remove metadata</div>':'<div class="ctx-menu-item gold" onclick="hideCtx();bulkRemoveMetadata()">'+ICO.meta+'Remove metadata from '+n+' files</div>')
        
        +(n===1?'<div class="ctx-menu-item" onclick="hideCtx();findSimilar('+imgId+')">'+ICO.dup+'Find Duplicates (pixel-based)</div><div class="ctx-menu-item" onclick="hideCtx();findSimilarTags('+imgId+')">'+ICO.dupt+'Find Duplicates (tag-based)</div>':'')
        +'<div class="ctx-menu-sep"></div>'
        +'<div class="ctx-menu-item danger" onclick="hideCtx();'+_cd+(n===1?'deleteSingleFromCtx('+imgId+')':'bulkDeleteSelected()')+'">'+ICO.trash+'Delete '+label+'</div>';
    m.innerHTML=html;
    document.body.appendChild(m);
    var x=e.clientX,y=e.clientY;
    if(x+m.offsetWidth>window.innerWidth)x=window.innerWidth-m.offsetWidth-4;
    if(y+m.offsetHeight>window.innerHeight)y=window.innerHeight-m.offsetHeight-4;
    m.style.left=x+'px';m.style.top=y+'px';
}

async function renameFromCtx(imgId){
    var img=S.images.find(function(i){return i.id===imgId;});
    if(!img&&S.dupGroups){S.dupGroups.forEach(function(g){g.images.forEach(function(d){if(d.id===imgId)img=d;});});}
    if(!img){img=await api('/api/image/'+imgId);if(img.error)return showToast('Error: '+img.error);}
    var name=await showPrompt('Rename file:',img.filename,'<b>_</b> connects name parts → John_Doe = <i>John Doe</i><br><b>+ - ,</b> separate characters → John_Doe+Jane = <i>John Doe, Jane</i>',{mode:'rename',fetchItems:globalNameSuggest});if(!name||!name.trim()||name.trim()===img.filename)return;
    var r=await api('/api/image/'+imgId+'/rename',{method:'POST',body:JSON.stringify({filename:name.trim()})});
    if(r.error){
        if(r.suggestion){var ok=await showConfirm('File <strong>'+esc(name.trim())+'</strong> already exists.\nRename to <strong>'+esc(r.suggestion)+'</strong> instead?');if(ok){r=await api('/api/image/'+imgId+'/rename',{method:'POST',body:JSON.stringify({filename:name.trim(),auto_increment:true})});if(r.error)return showToast('Error: '+r.error);}else return;}
        else return showToast('Error: '+r.error);
    }
    pushUndo({type:'rename',imageId:imgId,oldFilename:img.filename,newFilename:r.filename});
    showToast('Renamed!','success',true);
    if(S.page==='duplicates'&&S.dupGroups){
        S.dupGroups.forEach(function(g){g.images.forEach(function(d){if(d.id===imgId){d.filename=r.filename;d.fphash=r.fphash||d.fphash;}});});
        var dr=document.getElementById('dup-results');if(dr)dr.innerHTML=renderDupGroups(S.dupGroups);
        return;
    }
    await Promise.all([loadImagesPreserve(),loadCharacters(),loadStats()]);renderMain();renderTagList();
}

async function deleteSingleFromCtx(imgId){
    if(!await showConfirm('Delete this image?',[{label:'Cancel',key:'cancel'},{label:'Delete',key:'ok',cls:'danger'}]))return;
    var r=await api('/api/image/'+imgId+'/delete',{method:'POST'});
    if(r.error)return showToast('Error: '+r.error);
    pushUndo({type:'delete',trashId:r.trash_id});
    showToast('Deleted','success',true);S.selectedImages.clear();
    if(S.page==='duplicates'&&S.dupGroups){S.dupGroups.forEach(function(g){var ix=g.images.findIndex(function(img){return img.id===imgId;});if(ix>=0)g.images.splice(ix,1);});S.dupGroups=S.dupGroups.filter(function(g){return g.images.length>1;});var dr=document.getElementById('dup-results');if(dr)dr.innerHTML=renderDupGroups(S.dupGroups);var totalDups=S.dupGroups.reduce(function(a,g){return a+g.images.length;},0);var st=document.getElementById('dup-stats');if(st)st.textContent=S.dupGroups.length+' group'+(S.dupGroups.length!==1?'s':'')+' \u00b7 '+totalDups+' images';updateDupSelectionUI();return;}
    await Promise.all([loadImagesReset(),loadCharacters(),loadFolders(),loadStats()]);renderMain();renderTagList();renderFolderSidebar();
}

var _moveModalOpen={};

function showMoveModal(){
    if(!S.selectedImages.size)return;
    _moveModalOpen=Object.assign({},S.openFolders); // seed from main sidebar state
    var currentFolders=new Set();
    S.selectedImages.forEach(function(id){var img=S.images.find(function(i){return i.id===id;});if(img)currentFolders.add(img.folder);});
    _renderMoveModal(currentFolders,null);
}

function _renderMoveModal(currentFolders,disabledSet){
    var existing=document.getElementById('move-modal-bg');if(existing)existing.remove();
    var bg=document.createElement('div');bg.className='move-modal-bg';bg.id='move-modal-bg';
    bg.onclick=function(e){if(e.target===bg)bg.remove();};
    var tree=buildFolderTree();
    function renderNode(node,depth){
        var keys=Object.keys(node.children).sort(natSort);
        var h='';
        keys.forEach(function(k){
            var n=node.children[k];
            var hasKids=Object.keys(n.children).length>0;
            var isOpen=!!_moveModalOpen[n.fullPath];
            var isCurrent=currentFolders&&currentFolders.size===1&&currentFolders.has(n.fullPath);
            var isDisabled=disabledSet&&disabledSet.has(n.fullPath);
            var pad=depth*16+12;
            var dim=isCurrent||isDisabled;
            h+='<div class="mm-item'+(dim?' current':'')+'" style="padding-left:'+pad+'px;display:flex;align-items:center;gap:4px">';
            if(hasKids)h+='<span class="mm-arrow'+(isOpen?' open':'')+'" onclick="event.stopPropagation();toggleMoveNode(\''+esc(n.fullPath).replace(/\\/g,"\\\\").replace(/\x27/g,"\\\x27")+'\')">▶</span>';
            else h+='<span style="width:12px;display:inline-block"></span>';
            if(dim){h+='<span style="flex:1">'+esc(k)+'</span>';if(isCurrent)h+='<span style="color:var(--text-muted);font-size:11px">(current)</span>';else h+='<span style="color:var(--text-muted);font-size:11px">(skipped)</span>';}
            else h+='<span style="flex:1;cursor:pointer" onclick="_moveModalSelect(this,\''+esc(n.fullPath).replace(/\\/g,"\\\\").replace(/\x27/g,"\\\x27")+'\')">'+esc(k)+'</span>';
            h+='</div>';
            if(hasKids&&isOpen)h+=renderNode(n,depth+1);
        });
        return h;
    }
    var title=(disabledSet?'Move '+S.selectedFolders.size+' folders into…':'Move '+S.selectedImages.size+' file'+(S.selectedImages.size>1?'s':'')+' to…');
    var h='<div class="move-modal"><h3>'+title+'</h3><div class="mm-list">'+renderNode(tree,0)+'</div><div class="mm-footer"><button class="btn btn-sm" onclick="document.getElementById(\'move-modal-bg\').remove()">Cancel</button> <button class="btn btn-sm btn-primary" id="mm-move-btn" disabled onclick="_moveModalConfirm()">Move</button></div></div>';
    bg.innerHTML=h;document.body.appendChild(bg);
    bg._mode=disabledSet?'folders':'images';
    bg._currentFolders=currentFolders;
    bg._disabledSet=disabledSet;
}

function toggleMoveNode(fp){_moveModalOpen[fp]=!_moveModalOpen[fp];var bg=document.getElementById('move-modal-bg');if(bg)_renderMoveModal(bg._currentFolders,bg._disabledSet);}

function _moveModalSelect(el,fp){
    var bg=document.getElementById('move-modal-bg');if(!bg)return;
    bg._picked=fp;
    bg.querySelectorAll('.mm-item.picked').forEach(function(x){x.classList.remove('picked');});
    var row=el.closest('.mm-item');if(row)row.classList.add('picked');
    var btn=document.getElementById('mm-move-btn');if(btn)btn.disabled=false;
}

function _moveModalConfirm(){
    var bg=document.getElementById('move-modal-bg');if(!bg||!bg._picked)return;
    _moveModalPick(bg._picked);
}

function _moveModalPick(fp){
    var bg=document.getElementById('move-modal-bg');
    var mode=bg?bg._mode:'images';
    if(bg)bg.remove();
    if(mode==='folders')doBulkMoveFolders(fp);
    else doMoveToFolder(fp);
}

async function doMoveToFolder(targetFolder){
    var ids=Array.from(S.selectedImages);
    var moves=ids.map(function(id){var img=S.images.find(function(i){return i.id===id;});return {id:id,folder:img?img.folder:''};});
    var r;
    if(ids.length===1){r=await api('/api/image/'+ids[0]+'/move',{method:'POST',body:JSON.stringify({folder:targetFolder})});}
    else{r=await api('/api/images/bulk-move',{method:'POST',body:JSON.stringify({ids:ids,folder:targetFolder})});}
    if(r.error)return showToast('Error: '+r.error);
    var cnt=r.moved||1;
    if(ids.length===1)pushUndo({type:'move',imageId:ids[0],oldFolder:moves[0].folder});
    else pushUndo({type:'move_bulk',moves:moves});
    showToast(cnt+' file'+(cnt>1?'s':'')+' moved','success',true);
    S.selectedImages.clear();
    if(dupApplyMove(ids,targetFolder))return;
    if(S.page==='duplicates'){Promise.all([loadImagesPreserve(),loadFolders(),loadCharacters(),loadStats()]);return;}
    await Promise.all([loadImagesPreserve(),loadFolders(),loadCharacters(),loadStats()]);renderMain();renderTagList();renderFolderSidebar();
}

function showMainCtx(e){
    if(e.target.closest('.gallery-item'))return; // let card handler win
    e.preventDefault();e.stopPropagation();hideCtx();
    if(!S.clipboard||!S.clipboard.ids.length)return; // nothing to show
    var target=curFolder()||(S.images.length?S.images[0].folder:'');
    if(!target)return;
    var m=document.createElement('div');m.className='ctx-menu';m.id='ctx-menu';
    m.innerHTML='<div class="ctx-menu-item" onclick="hideCtx();pasteIntoFolder(\''+esc(target).replace(/\\/g,"\\\\").replace(/\x27/g,"\\\x27")+'\')">'+ICO.paste+'Paste '+S.clipboard.ids.length+' item'+(S.clipboard.ids.length>1?'s':'')+' into '+esc(target)+'</div>'
        +'<div class="ctx-menu-item" onclick="hideCtx();clearClipboard()">✕ Clear clipboard</div>';
    document.body.appendChild(m);
    var x=e.clientX,y=e.clientY;
    if(x+m.offsetWidth>window.innerWidth)x=window.innerWidth-m.offsetWidth-4;
    if(y+m.offsetHeight>window.innerHeight)y=window.innerHeight-m.offsetHeight-4;
    m.style.left=x+'px';m.style.top=y+'px';
}

function qaSel(){return Array.from(S.selectedImages);}

async function osClipboard(ids,mode,quiet){
if(!ids||!ids.length)return false;
try{var r=await api('/api/clipboard',{method:'POST',body:JSON.stringify({ids:ids,mode:mode||'file'})});
if(r&&r.ok){if(!quiet)showToast(mode==='image'?'Picture copied to the clipboard':
 (r.count>1?r.count+' files copied to the clipboard':'File copied to the clipboard'),'success');return true;}
/* v4.11: quiet suppresses the SUCCESS message only. A failure was swallowed
   completely before, so a broken clipboard looked like nothing happening. */
showToast('Clipboard: '+((r&&r.error)||'failed'));}
catch(e){showToast('Clipboard: '+e);}
return false;}

function detailOrSelection(){
if(S.page==='detail'&&S.currentImageId)return [S.currentImageId];
return Array.from(S.selectedImages);}

async function copyFileToOS(){var ids=detailOrSelection();if(!ids.length)return qaHint();return osClipboard(ids,'file');}

async function copyImageToOS(){var ids=detailOrSelection();if(!ids.length)return qaHint();
if(ids.length>1)showToast('Only the first picture goes to the clipboard as a bitmap');
return osClipboard(ids.slice(0,1),'image');}

function qaHint(){showToast('Select one or more images first');}
