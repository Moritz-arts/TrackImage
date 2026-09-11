/* The folder tree, linking folders, and scanning them.
 *
 * File 07 of 13 — the page loads these in number order.
 */

function selFolders(){return S.filter.folders||[];}

function curFolder(){var f=selFolders();return f.length===1?f[0]:'';}

function folderParams(p){selFolders().forEach(function(f){p.append('folder',f);});if(!S.inclSub)p.set('subfolders','0');return p;}

function folderQS(){var q=selFolders().map(function(f){return '&folder='+encodeURIComponent(f);}).join('');return q+(S.inclSub?'':'&subfolders=0');}

function folderKey(){return selFolders().join('|')+'#'+(S.inclSub?'1':'0');}

function unfilterFolder(fp){var i=selFolders().indexOf(fp);if(i>=0)S.filter.folders.splice(i,1);}

function folderLeaf(fp){return String(fp).split(/[\\/]/).pop();}

function folderLockBegin(label){if(S.folderBusy){showToast('A folder operation is already in progress — please wait until it finishes','error');return false;}S.folderBusy=true;document.body.classList.add('folder-busy');showFolderBusy(label||'Working…');return true;}

function folderLockEnd(){S.folderBusy=false;document.body.classList.remove('folder-busy');hideFolderBusy();}

function showFolderBusy(text){/* v3.19: footer progress bar is enough; no top overlay */}

function hideFolderBusy(){var el=document.getElementById('folder-busy-overlay');if(el)el.remove();}

function updateWatcherIndicator(){var el=document.getElementById('watcher-dot');if(el){el.className='watcher-dot'+(S.autosync?' active':' off');el.title=S.autosync?'Autosync active':'Autosync off \u2014 refresh the opened folder via \u21bb';}updateWorkSpinner();}

async function loadFolders(){S.folders=await api('/api/folders');}

async function loadScanFolders(){S.scanFolders=await api('/api/scan-folders');}

var _scanPollTimer=null;

function showScanProgress(p){var el=document.getElementById('scan-progress');if(!p.active||!p.folders||!p.folders.length){if(el)el.remove();return;}if(!el){el=document.createElement('div');el.id='scan-progress';el.className='scan-progress';document.body.appendChild(el);}var h='';p.folders.forEach(function(f){if(f.phase==='Done'&&f.current>=f.total)return;var pct=f.total>0?Math.round(f.current/f.total*100):0;var done=f.phase==='Done';h+='<div class="sp-row'+(done?' done':'')+'"><span class="spinner" style="width:14px;height:14px"></span><span class="sp-text">'+esc(f.phase)+' "'+esc(f.name)+'" '+f.current+'/'+f.total+'</span><div class="sp-bar"><div class="sp-fill" style="width:'+pct+'%"></div></div></div>';});el.innerHTML=h;if(!h&&el)el.remove();}

async function pollScanProgress(){try{var p=await api('/api/scan-progress');showScanProgress(p);if(p.active){_scanPollTimer=setTimeout(pollScanProgress,500);}else{_scanPollTimer=null;}}catch(e){_scanPollTimer=null;}}

async function toggleAutosync(){try{var r=await api('/api/autosync',{method:'POST',body:JSON.stringify({on:!S.autosync})});S.autosync=!!r.on;updateWatcherIndicator();showToast(S.autosync?'Autosync ON \u2014 watcher, processing & tagging active':'Autosync OFF \u2014 refresh the opened folder manually via \u21bb','success');if(S.page==='settings')render();}catch(e){showToast('Could not toggle autosync');}}

async function rescan(){S.loading=true;render();_scanPollTimer=setTimeout(pollScanProgress,300);try{var r=await api('/api/scan',{method:'POST'});if(r.error)showToast('Error: '+r.error);else showToast('Scan: '+r.new+' new, '+r.removed+' removed','success');S.initialized=true;await Promise.all([loadStats(),loadCharacters(),loadFolders(),loadImagesReset()]);}catch(e){showToast('Scan failed');}S.loading=false;showScanProgress({active:false,folders:[]});if(_scanPollTimer){clearTimeout(_scanPollTimer);_scanPollTimer=null;}render();}

async function pickAndAddFolder(){
    var r=null;
    try{r=await api('/api/pick-folder',{method:'POST'});}
    catch(e){r={error:'The folder dialog could not be reached',manual:true};}
    if(r&&r.error){
        if(r.manual)return addFolderByHand(r.error);
        showToast('Error: '+r.error,'error');return;
    }
    if(!r||!r.path)return;                 /* cancelled */
    await addFolderPath(r.path);
}

async function addFolderByHand(why){
    var typed=await showPrompt(
        '<div style="font-weight:600;margin-bottom:6px">Type the folder path</div>'
        +'<div style="color:var(--text-secondary);font-size:12px;margin-bottom:10px">'
        +esc(why||'No folder dialog is available on this computer')+'</div>','',
        'Paste or type the full path to the folder you want to link.');
    if(typed===null||typed===undefined)return;
    typed=String(typed).trim();
    if(!typed)return;
    await addFolderPath(typed);
}

async function addFolderPath(path){
    if(!folderLockBegin('Linking folder & scanning…'))return;
    try{
        var a=await api('/api/scan-folders',{method:'POST',body:JSON.stringify({path:path})});
        if(a&&a.error){showToast('Error: '+a.error,'error');return;}
        await loadScanFolders();showToast('Folder added! Scanning...','success');await rescan();
    }catch(e){showToast('Failed to link that folder','error');
    }finally{folderLockEnd();}
}

async function createFolderIn(parent){var name=await showPrompt('New folder name:','');if(!name||!name.trim())return;var r=await api('/api/create-folder',{method:'POST',body:JSON.stringify({parent:parent||'',name:name.trim()})});if(r.error)return showToast('Error: '+r.error);var displayFolder=parent?(parent+'\\'+name.trim()):name.trim();pushUndo({type:'folder_create',folder:displayFolder});showToast('Folder created!','success',true);await Promise.all([loadFolders(),loadImagesReset()]);render();}

async function deleteFolderIdx(idx){var fp=_folderPaths[idx];if(!fp)return;var node=findFolderNode(fp);var cnt=node?countAll(node):0;var msg='Delete folder <strong>'+esc(fp)+'</strong>?';if(cnt>0){msg+='\n\n<span class="warn">This folder contains '+cnt+' file'+(cnt>1?'s':'')+' that will be PERMANENTLY DELETED from your hard drive!</span>';var r1=await showConfirm(msg,[{label:'Cancel',key:'cancel'},{label:'Delete '+cnt+' files',key:'ok',cls:'danger'}]);if(!r1)return;}else{if(!await showConfirm(msg))return;}if(!folderLockBegin('Deleting folder…'))return;try{var r=await api('/api/delete-folder',{method:'POST',body:JSON.stringify({folder:fp})});if(r.error)return showToast('Error: '+r.error);showToast('Folder deleted ('+r.deleted_files+' files)','success');unfilterFolder(fp);await Promise.all([loadFolders(),loadCharacters(),loadImagesReset(),loadStats()]);render();}finally{folderLockEnd();}}

function findFolderNode(fullPath){var tree=buildFolderTree();var parts=fullPath.replace(/\//g,'\\').split('\\');var node=tree;for(var i=0;i<parts.length;i++){if(!node.children[parts[i]])return null;node=node.children[parts[i]];}return node;}

async function renameFolderIdx(idx){var fp=_folderPaths[idx];if(!fp)return;var parts=fp.replace(/\//g,'\\').split('\\');var old=parts[parts.length-1];var name=await showPrompt('Rename folder:',old);if(!name||!name.trim()||name.trim()===old)return;var r=await api('/api/rename-folder',{method:'POST',body:JSON.stringify({folder:fp,new_name:name.trim()})});if(r.error)return showToast('Error: '+r.error);showToast('Renamed!','success');unfilterFolder(fp);await Promise.all([loadScanFolders(),loadFolders(),loadCharacters(),loadImagesReset(),loadStats()]);render();}

function showFolderCtx(e,idx){hideCtx();var fp=_folderPaths[idx];var sel=S.selectedFolders;var isInSel=sel.has(fp);var multi=sel.size>1&&isInSel;var n=multi?sel.size:1;var m=document.createElement('div');m.className='ctx-menu';m.id='ctx-menu';var html='';if(multi){html+='<div class="ctx-menu-item" onclick="hideCtx();bulkMoveFolders()">'+ICO.move+'Move '+n+' folders into…</div>';html+='<div class="ctx-menu-sep"></div>';html+='<div class="ctx-menu-item danger" onclick="hideCtx();bulkDeleteFolders()">'+ICO.trash+'Delete '+n+' folders from disk</div>';}else{html+='<div class="ctx-menu-item" onclick="hideCtx();createFolderIn(_folderPaths['+idx+'])">'+ICO.sub+'New subfolder</div>';html+='<div class="ctx-menu-item" onclick="hideCtx();renameFolderIdx('+idx+')">'+ICO.rename+'Rename</div>';if(S.clipboard&&S.clipboard.ids.length){html+='<div class="ctx-menu-sep"></div>';html+='<div class="ctx-menu-item" onclick="hideCtx();pasteIntoFolder(\''+esc(fp).replace(/\\/g,"\\\\").replace(/\x27/g,"\\\x27")+'\')">'+ICO.paste+'Paste '+S.clipboard.ids.length+' item'+(S.clipboard.ids.length>1?'s':'')+' ('+(S.clipboard.mode==='cut'?'move':'copy')+')</div>';}html+='<div class="ctx-menu-sep"></div>';html+='<div class="ctx-menu-item" onclick="hideCtx();unlinkFolderIdx('+idx+')">'+ICO.explorer+'Unlink</div>';html+='<div class="ctx-menu-item danger" onclick="hideCtx();deleteFolderIdx('+idx+')">'+ICO.trash+'Delete from disk</div>';}m.innerHTML=html;document.body.appendChild(m);var x=e.clientX,y=e.clientY;if(x+m.offsetWidth>window.innerWidth)x=window.innerWidth-m.offsetWidth-4;if(y+m.offsetHeight>window.innerHeight)y=window.innerHeight-m.offsetHeight-4;m.style.left=x+'px';m.style.top=y+'px';}

async function bulkDeleteFolders(){var folders=Array.from(S.selectedFolders);if(!folders.length)return;var totalFiles=0;folders.forEach(function(fp){var node=findFolderNode(fp);if(node)totalFiles+=countAll(node);});var msg='Delete <strong>'+folders.length+' folders</strong> from disk?';if(totalFiles>0)msg+='\n\n<span class="warn">These folders contain '+totalFiles+' file'+(totalFiles>1?'s':'')+' that will be PERMANENTLY DELETED from your hard drive!</span>';var r1=await showConfirm(msg,[{label:'Cancel',key:'cancel'},{label:'Delete '+folders.length+' folders',key:'ok',cls:'danger'}]);if(!r1)return;var r=await api('/api/folders/bulk-delete',{method:'POST',body:JSON.stringify({folders:folders})});if(r.error)return showToast('Error: '+r.error);showToast((r.deleted?r.deleted.length:0)+' folders deleted ('+(r.deleted_files||0)+' files)'+(r.errors&&r.errors.length?' · '+r.errors.length+' errors':''),'success');S.selectedFolders.clear();folders.forEach(unfilterFolder);await Promise.all([loadScanFolders(),loadFolders(),loadCharacters(),loadImagesReset(),loadStats()]);render();}

async function bulkMoveFolders(){var folders=Array.from(S.selectedFolders);if(!folders.length)return;_moveModalOpen=Object.assign({},S.openFolders);_renderMoveModal(null,new Set(folders));}

async function doBulkMoveFolders(target){var folders=Array.from(S.selectedFolders);var r=await api('/api/folders/bulk-move',{method:'POST',body:JSON.stringify({folders:folders,target:target})});if(r.error)return showToast('Error: '+r.error);showToast((r.moved?r.moved.length:0)+' folders moved'+(r.errors&&r.errors.length?' · '+r.errors.length+' errors':''),'success');S.selectedFolders.clear();await Promise.all([loadScanFolders(),loadFolders(),loadCharacters(),loadImagesReset(),loadStats()]);render();}

async function onUnlinkDone(d){showToast('Unlinked'+((d&&d.root)?" \u2014 "+esc(d.root):''),'success');await Promise.all([loadScanFolders(),loadFolders(),loadCharacters(),loadImagesReset(),loadStats()]);render();}

async function unlinkFolderIdx(idx){var fp=_folderPaths[idx];if(!fp)return;if(!await showConfirm('Unlink <strong>'+esc(fp)+'</strong>?\n\nFiles will NOT be deleted from disk \u2014 only removed from TrackImage.'))return;var r=await api('/api/unlink-folder',{method:'POST',body:JSON.stringify({folder:fp})});if(r.error)return showToast('Error: '+r.error);unfilterFolder(fp);showToast('Unlinking '+(r.count||0)+' images in the background \u2014 progress in Settings','success');}

async function filterByFolder(f){var cur=selFolders().slice();var i=cur.indexOf(f);if(i>=0)cur.splice(i,1);else cur.push(f);return setFolderFilter(cur);}

async function setFolderFilter(list){closeDrawerAfterPick();S.filter.folders=list;S.selectedFolders=new Set(list);S.selectedImages.clear();if(S.page==='duplicates'){S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;S._dupCachedFolder=null;S._dupCachedChars=null;updateFolderActive();render();return;}await Promise.all([loadCharacters(),loadImagesReset()]);renderMain();renderTagList();updateFolderActive();}

function onFolderDragOver(e,idx){
    if(!S.dragIds)return;
    e.preventDefault();e.dataTransfer.dropEffect='move';
    e.currentTarget.classList.add('drop-over');
}

function onFolderDragLeave(e){e.currentTarget.classList.remove('drop-over');}

function buildFolderTree(){var tree={children:{},count:0,fullPath:''};S.folders.forEach(function(f){var parts=f.folder.replace(/\//g,'\\').split('\\');var node=tree;var path='';for(var i=0;i<parts.length;i++){path+=(i?'\\':'')+parts[i];if(!node.children[parts[i]])node.children[parts[i]]={children:{},count:0,fullPath:path,name:parts[i]};node=node.children[parts[i]];}node.count=f.image_count;});return tree;}

var _folderPaths=[];

function natSort(a,b){var ka=a.toLowerCase().replace(/\d+/g,function(n){return n.padStart(10,'0');});var kb=b.toLowerCase().replace(/\d+/g,function(n){return n.padStart(10,'0');});return ka<kb?-1:ka>kb?1:a<b?-1:a>b?1:0;}

function renderFolderNode(node,depth){var keys=Object.keys(node.children).sort(natSort);var h='';keys.forEach(function(k){var n=node.children[k];var hasKids=Object.keys(n.children).length>0;var isActive=selFolders().indexOf(n.fullPath)>=0;var isOpen=S.openFolders[n.fullPath];var isMulti=S.selectedFolders.size>1&&S.selectedFolders.has(n.fullPath);var totalCount=countAll(n);var idx=_folderPaths.length;_folderPaths.push(n.fullPath);h+='<div class="tree-node">';h+='<div class="tree-toggle'+(isActive?' active':'')+(isMulti?' multi-selected':'')+'" data-fidx="'+idx+'" data-folder="'+esc(n.fullPath)+'" onclick="clickFolder('+idx+',event)" ondblclick="event.stopPropagation();toggleFolderIdx('+idx+')" oncontextmenu="event.preventDefault();event.stopPropagation();showFolderCtx(event,'+idx+')" ondragover="onFolderDragOver(event,'+idx+')" ondragleave="onFolderDragLeave(event)" ondrop="onFolderDrop(event,'+idx+')" style="padding-left:'+(depth*14+12)+'px">';if(hasKids)h+='<span class="arrow'+(isOpen?' open':'')+'" onclick="event.stopPropagation();toggleFolderIdx('+idx+')" id="fa-'+idx+'">▶</span>';else h+='<span style="width:18px;display:inline-block;flex-shrink:0"></span>';h+='<span style="flex:1;overflow:hidden;text-overflow:ellipsis">'+esc(k)+'</span>';h+='<span class="tcnt">'+totalCount+'</span>';h+='</div>';if(hasKids){h+='<div class="tree-children'+(isOpen?' open':'')+'" id="fc-'+idx+'">';h+=renderFolderNode(n,depth+1);h+='</div>';}h+='</div>';});return h;}

function clickFolder(idx,e){var fp=_folderPaths[idx];if(!fp)return;var cur=selFolders().slice();if(e&&(e.ctrlKey||e.metaKey)){e.preventDefault();var i=cur.indexOf(fp);if(i>=0)cur.splice(i,1);else cur.push(fp);S.lastSelectedFolderIdx=idx;}else if(e&&e.shiftKey&&S.lastSelectedFolderIdx>=0){e.preventDefault();var a=Math.min(S.lastSelectedFolderIdx,idx),b=Math.max(S.lastSelectedFolderIdx,idx);for(var j=a;j<=b;j++){var p=_folderPaths[j];if(!p||cur.indexOf(p)>=0)continue;/* v3.93: skip rows sitting inside a collapsed parent -- the range covers what the tree shows, nothing else. */var _el=document.querySelector('.tree-toggle[data-fidx="'+j+'"]');if(_el&&_el.offsetParent===null)continue;cur.push(p);}}else{cur=(cur.length===1&&cur[0]===fp)?[]:[fp];S.lastSelectedFolderIdx=idx;}return setFolderFilter(cur);}

/* v4.56: by class, not by id -- the open picture carries its own copy of the
   folder column and the count belongs in both. */
function updateFolderSelection(){var many=S.selectedFolders.size>1;document.querySelectorAll('.sel-count-folders').forEach(function(ct){if(many){ct.style.display='';ct.textContent=S.selectedFolders.size+' sel';}else ct.style.display='none';});document.querySelectorAll('.tree-toggle[data-folder]').forEach(function(el){el.classList.toggle('multi-selected',S.selectedFolders.size>1&&S.selectedFolders.has(el.dataset.folder));});}

function toggleFolderIdx(idx){var key=_folderPaths[idx];S.openFolders[key]=!S.openFolders[key];if(!S.openFolders[key])delete S.openFolders[key];_lsSave('ti_open_folders',S.openFolders);var ch=document.getElementById('fc-'+idx);var ar=document.getElementById('fa-'+idx);if(ch)ch.classList.toggle('open',S.openFolders[key]);if(ar)ar.classList.toggle('open',S.openFolders[key]);}

/* v4.56: every copy of the folder column is rewritten, not just the first one
   the document happens to hold. The open picture shows its own copy, which used
   to keep the tree it was built with while the gallery behind it updated. */
function renderFolderSidebar(){var cols=document.querySelectorAll('.folders-col');if(!cols.length){render();return;}_folderPaths=[];var tree=buildFolderTree();var html='<div class="sidebar-title"><span>Folders</span><span class="sel-count-folders" style="display:none;font-family:\'Space Mono\',monospace;font-size:10px;color:var(--accent-light)"></span><span class="col-collapse-btn" onclick="toggleSidebarCol(\'folders\')" title="Collapse">\u25C0</span></div>'+renderFolderNode(tree,0)+'<div class="link-folder-btn" onclick="pickAndAddFolder()">Link new folder</div>';for(var i=0;i<cols.length;i++)cols[i].innerHTML=html;updateFolderActive();updateFolderSelection();}

function getFolderTotal(){var fs=selFolders();if(!fs.length)return S.stats.total_images||0;var c=0;S.folders.forEach(function(f){var hit=fs.some(function(sel){return f.folder===sel||(S.inclSub&&(f.folder.indexOf(sel+'\\')===0||f.folder.indexOf(sel+'/')===0));});if(hit)c+=f.image_count;});return c||S.filteredTotal;}
