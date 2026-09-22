/* Duplicates, and finding pictures like this one.
 *
 * File 09 of 13 — the page loads these in number order.
 */

function dupFolderParts(){var fs=selFolders();if(!fs.length)return ['All Folders'];if(fs.length<=2)return fs.slice();return [fs[0],(fs.length-1)+' more'];}

function dupFolderLabel(){return dupFolderParts().join(' & ');}

function dupApplyMove(ids,targetFolder){
    if(S.page!=='duplicates'||!S.dupGroups)return false;
    var idSet=new Set(ids);var f=curFolder();
    var inF=function(fold){return !f||fold===f||fold.indexOf(f+'\\')===0;};
    S.dupGroups.forEach(function(g){for(var i=g.images.length-1;i>=0;i--){var d=g.images[i];if(!idSet.has(d.id))continue;d.folder=targetFolder;if(!inF(targetFolder))g.images.splice(i,1);}});
    S.dupGroups=S.dupGroups.filter(function(g){return g.images.length>1;});
    var dr=document.getElementById('dup-results');if(dr)dr.innerHTML=renderDupGroups(S.dupGroups);
    var totalDups=S.dupGroups.reduce(function(a,g){return a+g.images.length;},0);
    var st=document.getElementById('dup-stats');if(st)st.textContent=S.dupGroups.length+' group'+(S.dupGroups.length!==1?'s':'')+' \u00b7 '+totalDups+' images';
    if(typeof updateDupSelectionUI==='function')updateDupSelectionUI();
    Promise.all([loadImagesPreserve(),loadFolders(),loadCharacters(),loadStats()]);
    return true;
}

function dupShellOpen(){_folderPaths=[];var tree=buildFolderTree();var allCount=S.filter.search?(S.filteredTotal||0):getFolderTotal();return '<div class="gallery-layout" style="--folder-col-w:'+S.folderColW+'px;--tag-col-w:'+S.tagColW+'px">'+renderTopbar()+'<div class="sidebar"><div class="sidebar-col-wrap folders-wrap'+(S.foldersCollapsed?' collapsed':'')+'" id="folders-wrap"><div class="col-collapsed-bar" onclick="toggleSidebarCol(\'folders\')" title="Expand"><span>\u25B6</span><span class="cc-label">Folders</span></div><div class="sidebar-col" id="folders-col"><div class="sidebar-title"><span>Folders</span><span class="col-collapse-btn" onclick="toggleSidebarCol(\'folders\')" title="Collapse">\u25C0</span></div>'+renderFolderNode(tree,0)+'<div class="link-folder-btn" onclick="pickAndAddFolder()">Link new folder</div></div><div class="col-resizer" onmousedown="startResize(event,\'folder\')"></div></div><div class="sidebar-col-wrap tags-wrap'+(S.tagsCollapsed?' collapsed':'')+'" id="tags-wrap"><div class="col-collapsed-bar" onclick="toggleSidebarCol(\'tags\')" title="Expand"><span>\u25B6</span><span class="cc-label">Tags</span></div><div class="sidebar-col" id="tags-col">'+tagColInner(allCount)+'</div><div class="col-resizer" onmousedown="startResize(event,\'tag\')"></div></div></div>';}

async function renderDuplicates(){
var hs=await api('/api/hash-status');
if(!hs.available&&!S.simMode)return dupShellOpen()+'<div class="main" id="main-area"><div class="page-title">Duplicates</div>'+dupModeToggle()+'<div style="padding:40px;text-align:center;color:var(--text-muted)"><h2>Duplicate Detection</h2><p>numpy is not installed.</p><p>Run: <code>pip install numpy</code> then restart.</p></div><div class="footer">TrackImage v' + TI_VERSION + '</div></div></div>';
var unhashed=hs.total-hs.hashed;
if(!S.simMode&&(hs.hashing||(unhashed>0&&!S._hashAttempted))){
if(!S._hashAttempted){S._hashAttempted=true;await api('/api/compute-hashes',{method:'POST'});}
return dupShellOpen()+'<div class="main" id="main-area"><div class="page-title">Duplicates</div>'+dupModeToggle()+'<div class="dup-loading"><div class="spinner"></div><span id="hash-progress-text">'+(hs.phase==='comparing'?'Comparing images... ':'Hashing images... ')+(hs.hashing?hs.hash_current+' / '+hs.hash_total:hs.hashed+' / '+hs.total)+'</span>'+(hs.phase==='comparing'?' <button class="btn btn-sm" id="dup-cancel-btn" onclick="cancelDupScan()" style="margin-left:12px;padding:3px 10px;font-size:12px" title="Stop the comparison. Everything already computed is kept.">Stop</button>':'')+'</div><div style="padding:0 40px"><div style="background:var(--bg-primary);border-radius:6px;height:8px;overflow:hidden;border:1px solid var(--border)"><div id="hash-progress-bar" style="height:100%;background:var(--accent);width:'+(hs.hashing&&hs.hash_total?hs.hash_current/hs.hash_total*100:(hs.total?hs.hashed/hs.total*100:0))+'%;transition:width .3s"></div></div></div></div></div>';
}
S._lastHashed=hs.hashed||0;                       /* v4.33: for the query stats line */
var threshold=S.simMode?(S.simMatch||70):_dupThr();
var dupFolder=folderKey();
var folderLabel=dupFolderLabel();
// v3.28: unified query view -- a dropped image OR a single-image "Find similar"
if(S._dupQuery){
if(S._dupQuery.imgId&&S._dupQuery.allMatches==null){
var sr=await api((S._dupQuery.mode==='tags'?'/api/similar-tags/':'/api/similar/')+S._dupQuery.imgId+'?threshold=128'+((S._dupQuery.mode!=='tags'&&S.dupVerify)?'&verify=1':''));
if(sr&&sr.error){
if(sr.error.indexOf('computing')>=0||sr.error.indexOf('wait')>=0){startDupComputePoll();return dupShellOpen()+'<div class="main" id="main-area">'+dupQueryTitle(S._dupQuery.mode==='tags')+dupModeToggle()+dupQueryBox()+'<div class="dup-loading"><div class="spinner"></div>Comparing images\u2026</div></div></div>';}
var _em=sr.error;S._dupQuery=null;return dupShellOpen()+'<div class="main" id="main-area"><div class="page-title">Duplicates</div>'+dupModeToggle()+'<div style="padding:40px;text-align:center;color:var(--text-muted)">'+esc(_em)+'</div></div></div>';
}
S._dupQuery.allMatches=(sr&&sr.similar)||[];
var _best=0;S._dupQuery.allMatches.forEach(function(m){if((m.similarity||0)>_best)_best=m.similarity;});
if(S._dupQuery.mode!=='tags')S.dupThreshold=S._dupQuery.allMatches.length?Math.min(50,dupSnap(Math.max(0,100-_best))):30;
}
var _isTagQ=S._dupQuery.mode==='tags';
var _qt=_isTagQ?(S.simMatch||70):(S.dupThreshold!=null?S.dupThreshold:30);
var _qm=sortQueryMatches((S._dupQuery.allMatches||[]).filter(function(m){return m.similarity>=(_isTagQ?_qt:100-_qt);}));
S.dupGroups=[{images:_qm,similarity:null}];S.selectedImages.clear();
/* v4.33: identical to the folder view apart from the title. */
var _qh=dupShellOpen()+'<div class="main" id="main-area">'+dupQueryTitle(_isTagQ)+dupModeToggle();
_qh+=dupQueryBox();
_qh+=dupControlsRow(_isTagQ,_qt,dupQueryStats(_qm.length,_isTagQ,hs.hashed),false);
_qh+='<div id="dup-results">'+renderDupGroups(S.dupGroups)+'</div><div class="footer">TrackImage v' + TI_VERSION + '</div></div></div>';
return _qh;
}
var sort=S.dupSort||'size';
var d;
var _mode=dupModeKey();if(S.dupGroups&&S._dupCachedMode===_mode&&S._dupCachedThreshold===threshold&&S._dupCachedSort===sort&&S._dupCachedFolder===dupFolder&&S._dupCachedChars===(S.filter.ratings.join(',')+'|'+S.filter.characters.join('|'))&&S._dupCachedSearch===S.filter.search){d={groups:S.dupGroups,total_groups:S.dupGroups.length,total_duplicates:S.dupGroups.reduce(function(a,g){return a+g.images.length;},0),hashed:hs.hashed};}
else{d=await api(dupApiUrl(threshold,sort,dupFolder,true));
if(S.simMode&&d&&d.error==='no_tags'){return dupShellOpen()+'<div class="main" id="main-area">'+dupPageTitle(folderLabel)+dupModeToggle()+'<div style="padding:40px;text-align:center;color:var(--text-muted);line-height:1.7">'+(_tagAvail()?'<b style="color:var(--text-secondary)">No auto-tags yet.</b><br>Run the ML tagger first \u2014 <a onclick="toggleSettings()" style="color:var(--accent);cursor:pointer">Settings \u2192 Auto-tagging</a> \u2014 then come back.':'<b style="color:var(--text-secondary)">Tag-based matching needs auto-tagging.</b><br>Install it in <a onclick="toggleSettings()" style="color:var(--accent);cursor:pointer">Settings \u2192 Auto-tagging</a>, then come back.')+'<br><span style="font-size:12px">Manual tags still work \u2014 detail view \u2192 +</span></div><div class="footer">TrackImage v' + TI_VERSION + '</div></div></div>';}
if(d.computing){startDupComputePoll();
return dupShellOpen()+'<div class="main" id="main-area">'+dupPageTitle(folderLabel)+dupModeToggle()+'<div class="dup-loading"><div class="spinner"></div><span id="dup-compute-text">'+(d.phase==='processing'?('Processing '+d.pending+' images first… '+d.progress+'%'+etaText(d)):('Comparing images... '+d.progress+'%'+etaText(d)))+'</span></div><div style="padding:0 40px"><div style="background:var(--bg-primary);border-radius:6px;height:8px;overflow:hidden;border:1px solid var(--border)"><div id="dup-compute-bar" style="height:100%;background:var(--accent);width:'+d.progress+'%;transition:width .3s"></div></div></div></div></div>';
}
S.dupGroups=d.groups;S._dupCachedMode=_mode;S._dupCachedThreshold=threshold;S._dupCachedSort=sort;S._dupCachedFolder=dupFolder;S._dupCachedChars=S.filter.ratings.join(',')+'|'+S.filter.characters.join('|');S._dupCachedSearch=S.filter.search;}
S.selectedImages.clear();
var h=dupShellOpen()+'<div class="main" id="main-area">'+dupPageTitle(folderLabel)+dupModeToggle();
if(!S.simMode&&hs.total>0&&hs.hashed===0)h+='<div style="margin:0 20px 12px;padding:10px 14px;border:1px solid var(--danger);border-radius:8px;color:var(--danger);font-size:13px"><b>No image hashes yet.</b> Background processing may still be running \u2014 or Pillow failed to load (check the console window for a \u26a0 Pillow warning; deep install paths can break DLL loading).</div>';
h+=dupQueryBox();
h+=dupControlsRow(S.simMode,threshold,
   d.total_groups+' group'+(d.total_groups!==1?'s':'')+' \u00b7 '+d.total_duplicates+' images \u00b7 '+d.hashed+(S.simMode?' tagged':' hashed')+(d.ignored_pairs?(' \u00b7 '+d.ignored_pairs+' ignored pair'+(d.ignored_pairs!==1?'s':'')):''),
   true);
h+='<div id="dup-results">'+renderDupGroups(d.groups)+'</div>';
h+='<div class="footer">TrackImage v' + TI_VERSION + '</div></div></div>';
return h;
}

function dupControlsRow(tagMode,threshold,stats,showIgnored){
var h='<div style="padding:0 20px 10px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">';
h+='<div style="display:flex;align-items:center;gap:8px;flex:1 1 260px;min-width:260px"><span style="font-size:13px;color:var(--text-secondary);white-space:nowrap">'+(tagMode?'Same tags:':'Max difference:')+'</span>';
/* v4.42: the pixel slider starts at 0, not 5. 0 means a bit-for-bit identical
   hash -- the only setting that answers "which of these are the SAME file"
   rather than "which look alike". The server already accepted it; the control
   simply never offered it. */
/* Pixel mode walks DUP_STEPS by position: single percent steps up to 10, where
   a copy and a near-copy are told apart, fives beyond. */
h+='<input type="range" style="flex:1;min-width:100px" class="dup-slider" min="'+(tagMode?50:0)+'" max="'+(tagMode?95:DUP_STEPS.length-1)+'" step="'+(tagMode?5:1)+'" value="'+(tagMode?threshold:dupStepIdx(threshold))+'" oninput="onDupSlider(this.value)" />';
h+='<span style="font-size:13px;font-weight:600;color:var(--accent);min-width:30px" id="dup-threshold-val">'+threshold+'%</span></div>';
if(!tagMode)h+='<label style="display:flex;align-items:center;gap:5px;flex:none;font-size:12px;color:var(--text-secondary);cursor:pointer;white-space:nowrap" title="Only keep matches that also share at least 30% of their tags"><input type="checkbox" '+(S.dupVerify?'checked':'')+' onchange="toggleDupVerify(this.checked)">Verify with tags</label>';
var sortMode=S.dupSort||'size';
h+='<div style="display:flex;gap:4px;align-items:center;flex:none;white-space:nowrap"><span style="font-size:13px;color:var(--text-secondary)">Sort:</span>';
h+='<button class="btn btn-sm'+(sortMode==='size'?' btn-primary':'')+'" onclick="setDupSort(\'size\')" style="padding:3px 8px;font-size:12px">Size</button>';
h+='<button class="btn btn-sm'+(sortMode==='similarity_desc'?' btn-primary':'')+'" onclick="setDupSort(\'similarity_desc\')" style="padding:3px 8px;font-size:12px">Most similar</button>';
h+='<button class="btn btn-sm'+(sortMode==='similarity_asc'?' btn-primary':'')+'" onclick="setDupSort(\'similarity_asc\')" style="padding:3px 8px;font-size:12px">Least similar</button></div>';
if(showIgnored&&(S.dupIgnoredCount||S.dupShowIgnored)){h+='<span style="display:flex;align-items:center;gap:6px;margin-left:14px;flex:none;white-space:nowrap;font-size:12px">'+'<button class="btn btn-sm'+(S.dupShowIgnored?' btn-primary':'')+'" onclick="dupToggleShowIgnored()" title="Switch between the normal list and the groups you marked as wanted variants">'+(S.dupShowIgnored?'Showing ignored':'Ignored')+'</button>'+(S.dupShowIgnored?'<button class="btn btn-sm" onclick="dupRestoreAll()" title="Restore every ignored group at once">Restore all</button>':'')+'</span>';}
h+='<span style="margin-left:auto;flex:none;white-space:nowrap;font-size:13px;color:var(--text-secondary)" id="dup-stats">'+stats+'</span></div>';
return h;}

function dupQueryStats(n,tagMode,hashed){return '1 group \u00b7 '+n+' image'+(n!==1?'s':'')+' \u00b7 '+(hashed||0)+(tagMode?' tagged':' hashed');}

function dupQueryTitle(tagMode){var q=S._dupQuery||{};
return '<div class="page-title">'+(tagMode?'Similar to ':'Duplicates of ')+'<span style="color:var(--accent)">'+esc(q.label||'query image')+'</span></div>';}

function dupModeKey(){return S.simMode?'tags':('phash'+(S.dupVerify?'+v':''));}

function dupApiUrl(threshold,sort,dupFolder,withFilters){var u=S.simMode?('/api/similar-tags?threshold='+threshold):('/api/duplicates?threshold='+Math.round(threshold/100*256)+(S.dupVerify?'&verify=1':''));u+='&sort='+sort+folderQS()+(S.dupShowIgnored?'&show_ignored=1':'');if(withFilters)u+=S.filter.characters.map(function(c){return '&character='+encodeURIComponent(c);}).join('')+S.filter.ratings.map(function(r){return '&rating='+r;}).join('')+(S.filter.search?'&search='+encodeURIComponent(S.filter.search):'');return u;}

var _hashPollTimer;

var _dupComputeTimer;

function dupGroupStats(imgs){
function mm(a){if(!a.length)return null;var mn=Math.min.apply(null,a),mx=Math.max.apply(null,a);return {min:mn,max:mx,same:(mn===mx&&a.length>1)};}
var pxs=[],szs=[];
imgs.forEach(function(im){var p=(im.width||0)*(im.height||0);if(p>0)pxs.push(p);if(im.file_size>0)szs.push(im.file_size);});
return {px:mm(pxs),sz:mm(szs)};
}

function dupRank(v,m){
if(!v||!m)return 'b-mid';
if(m.same)return 'b-same';
if(v===m.max)return 'b-best';
if(v===m.min)return 'b-lower';
return 'b-mid';
}

function dupBadges(img,st){
var px=(img.width||0)*(img.height||0);
if(!px&&!img.file_size)return '';
var b='<div class="dup-badges">';
if(px)b+='<span class="dup-badge '+dupRank(px,st&&st.px)+'" title="Resolution, ranked inside this group \u2014 green: highest, red: lowest, blue: all members identical">'+img.width+'\u00d7'+img.height+'</span>';
if(img.file_size)b+='<span class="dup-badge '+dupRank(img.file_size,st&&st.sz)+'" title="File size, ranked inside this group \u2014 green: largest, red: smallest, blue: all members identical">'+fmtBytes(img.file_size)+'</span>';
return b+'</div>';
}

function dupToggleShowIgnored(){
  S.dupShowIgnored=!S.dupShowIgnored;
  S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;render();
}

async function dupRestoreAll(){
  try{
    await api('/api/duplicates/ignore',{method:'POST',body:JSON.stringify({all:true,ignore:false})});
    S.dupIgnoredCount=0;S.dupShowIgnored=false;
    showToast('All ignored groups restored','success');
    S._dupQuery=null;S.dupGroups=null;S._dupCachedThreshold=null;render();
  }catch(e){showToast('Could not restore');}
}

var _dupSliderTimer;

var _dupReqSeq=0;

function _dupThr(){return S.dupThreshold!=null?S.dupThreshold:5;}

/* Max difference, in percent of the 256-bit hash. Below 10 one step is about
   2.5 bits: measured on real photographs a recompressed or downscaled copy
   lands 2-6 bits away -- 1-3% -- which the old steps of five jumped straight
   over from 0 to 5. */
var DUP_STEPS=[0,1,2,3,4,5,6,7,8,9,10,15,20,25,30,35,40,45,50];

function dupStepIdx(p){p=+p||0;for(var i=0;i<DUP_STEPS.length;i++)if(DUP_STEPS[i]>=p)return i;return DUP_STEPS.length-1;}

function dupSnap(p){return DUP_STEPS[dupStepIdx(p)];}

/* Smart clean decides by the pixels, not by the slider -- but beyond this the
   groups fill with pictures that are merely alike, and nobody should have to
   read a list of those to find the three copies in it. */
var SMART_MAX=5;

function dupQueryBox(){
var q=S._dupQuery;var inner;
if(q){
inner='<div style="position:relative;flex-shrink:0"><img src="'+q.thumb+'" style="height:150px;max-width:240px;object-fit:contain;border-radius:10px;border:1px solid var(--border);display:block;background:var(--bg-primary)"/><div onclick="event.stopPropagation();clearDupQuery()" title="Remove" style="position:absolute;top:-10px;right:-10px;width:28px;height:28px;border-radius:50%;background:var(--bg-secondary);border:1px solid var(--accent-glow);color:var(--text-secondary);display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:15px;line-height:1;box-shadow:0 2px 8px rgba(0,0,0,.45)">\u2715</div></div><div style="flex:1;min-width:0;align-self:center;font-weight:600;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(q.label||'query image')+'</div>';
}else{
inner='<div style="display:flex;align-items:center;gap:16px;color:var(--text-muted);font-size:14px"><span style="font-size:36px">\u2b07</span><div><div style="font-weight:600;color:var(--text-secondary);font-size:15px">Drop, click, or paste (Ctrl+V) an image to scan</div><div style="font-size:12px;margin-top:3px">Right-click to paste \u00b7 '+(S.simMode?'auto-tagged':'hashed')+' in memory, never imported \u2014 temporary.</div></div></div>';
}
return '<div id="dup-dropzone" ondragover="dupDragOver(event)" ondragleave="dupDragLeave(event)" ondrop="dupDrop(event)" oncontextmenu="dupBoxCtx(event)" onclick="'+(q?'':'dupPickFile()')+'" style="margin:0 20px 16px;padding:18px;border:2px dashed var(--border);border-radius:12px;display:flex;align-items:center;gap:20px;cursor:'+(q?'default':'pointer')+';min-height:96px">'+inner+'<input type="file" id="dup-file-input" accept="image/*" style="display:none" onchange="dupPickedFile(event)"/></div>';
}

function dupPickFile(){var i=document.getElementById('dup-file-input');if(i)i.click();}

function dupPickedFile(e){var f=e.target.files&&e.target.files[0];if(f)dupScanBlob(f);}

function dupDragOver(e){e.preventDefault();e.stopPropagation();var z=document.getElementById('dup-dropzone');if(z)z.style.borderColor='var(--accent)';}

function dupDragLeave(e){e.preventDefault();var z=document.getElementById('dup-dropzone');if(z)z.style.borderColor='var(--border)';}

async function dupScanBlob(file,modeOverride){var _tagQ=(modeOverride!==undefined)?(modeOverride==='tags'):!!S.simMode;S.simMode=_tagQ;
var z=document.getElementById('dup-dropzone');if(z)z.innerHTML='<div class="spinner"></div> Scanning '+esc(file.name||'image')+'\u2026';var fd=new FormData();fd.append('image',file);var r;try{var resp=await fetch(_tagQ?'/api/scan-image-tags':('/api/scan-image?threshold=128'+(S.dupVerify?'&verify=1':'')),{method:'POST',body:fd});r=await resp.json();}catch(e){showToast('Scan failed');render();return;}if(r.error){showToast(r.error);render();return;}
/* v4.33: the file itself is kept so the same scan can be repeated in the other
   mode without asking for it again. It lives in this tab and nowhere else --
   it is never uploaded to storage, never written to the database, and it is
   dropped the moment the query is cleared or the page is left. */
S._dupQuery={thumb:r.thumb,label:r.filename,allMatches:r.matches,file:file,mode:_tagQ?'tags':undefined};if(!S.simMode)S.dupThreshold=r.best_similarity!=null?Math.min(50,Math.max(5,dupSnap(100-r.best_similarity))):30;S._collapsedGroups=new Set();render();}

function dupBoxCtx(e){e.preventDefault();e.stopPropagation();hideCtx();var m=document.createElement('div');m.className='ctx-menu';m.id='ctx-menu';m.innerHTML='<div class="ctx-menu-item" onclick="hideCtx();dupPasteFromClipboard()">Paste image to scan</div>';document.body.appendChild(m);var x=e.clientX,y=e.clientY;if(x+m.offsetWidth>window.innerWidth)x=window.innerWidth-m.offsetWidth-4;if(y+m.offsetHeight>window.innerHeight)y=window.innerHeight-m.offsetHeight-4;m.style.left=x+'px';m.style.top=y+'px';}

async function dupPasteFromClipboard(){if(!navigator.clipboard||!navigator.clipboard.read){showToast('Clipboard paste not supported here \u2014 use Ctrl+V');return;}try{var items=await navigator.clipboard.read();for(var i=0;i<items.length;i++){var types=items[i].types||[];for(var j=0;j<types.length;j++){if(types[j].indexOf('image')>=0){var blob=await items[i].getType(types[j]);dupScanBlob(blob);return;}}}showToast('No image found in clipboard');}catch(err){showToast('Clipboard access denied \u2014 try Ctrl+V instead');}}

function dupModeToggle(){var d=!S.simMode;return '<div style="padding:0 20px 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap"><div style="display:flex;border:1px solid var(--border);border-radius:8px;overflow:hidden"><button class="btn btn-sm'+(d?' btn-primary':'')+'" style="border-radius:0;padding:5px 14px" onclick="gotoDup(false)">Pixel-based</button><button class="btn btn-sm'+(d?'':' btn-primary')+'" style="border-radius:0;padding:5px 14px" onclick="gotoDup(true)">Tag-based</button></div><span style="font-size:12px;color:var(--text-muted)">'+(d?'Same image \u2014 other file or version (pixel-based)':'Same subject \u2014 different images (tag-based)')+'</span>'+'</div>';}

function dupPageTitle(fl){var body;
if(fl===dupFolderLabel()){/* v3.93: gold folder names, the "&" stays in the title colour */
body=dupFolderParts().map(function(p){return '<span style="color:var(--accent)">'+esc(p)+'</span>';}).join('<span> &amp; </span>');}
else body='<span style="color:var(--accent)">'+esc(fl)+'</span>';
return '<div class="page-title">'+(S.simMode?'Similar':'Duplicates')+' in '+body+'</div>';}

async function findSimilarTags(imgId){
var _fn='image';try{if(S.dupGroups)S.dupGroups.forEach(function(g){g.images.forEach(function(d){if(d.id===imgId&&d.filename)_fn=d.filename;});});if(S.images){var _i=S.images.find(function(x){return x.id===imgId;});if(_i&&_i.filename)_fn=_i.filename;}}catch(e){}
closeDetail();
S.page='duplicates';S.simMode=true;S._dupQuery={thumb:'/thumb/'+imgId,label:_fn,imgId:imgId,allMatches:null,mode:'tags'};S._collapsedGroups=new Set();updateNav();pushHistory('duplicates');render();
}

async function findSimilar(imgId){
var _fn='image';try{if(S.dupGroups)S.dupGroups.forEach(function(g){g.images.forEach(function(d){if(d.id===imgId&&d.filename)_fn=d.filename;});});if(S.images){var _i=S.images.find(function(x){return x.id===imgId;});if(_i&&_i.filename)_fn=_i.filename;}}catch(e){}
closeDetail();
S.page='duplicates';S.simMode=false;S._dupQuery={thumb:'/thumb/'+imgId,label:_fn,imgId:imgId,allMatches:null};S._collapsedGroups=new Set();updateNav();pushHistory('duplicates');render();
}

/* ---- Smart clean -----------------------------------------------------------
   One group at a time, on purpose: the dialog shows every picture of that group
   -- the one that stays, the ones that go and why the rest stay too -- and a
   list of that is something one can actually read before saying yes.

   The copy that stays has the most pixels AND the least compression. The
   compression is measured in the pixels (the JPEG grid, see _sc_blockiness),
   not guessed from the file size, which says nothing between formats: a PNG
   saved from a JPEG 50 is three times the size and exactly as damaged. Where
   one copy has more pixels and another less compression, both stay. Up to Max
   difference SMART_MAX, and even there the hash is not taken at its word: the
   server compares every copy with the one that stays, pixel against pixel, and
   a copy that is moved by a pixel or changed anywhere stays. GIFs, videos and
   animated pictures are never candidates. Ctrl+Z brings back what went. */
function dupSmartOn(){return !(S.simMode||(S._dupQuery&&S._dupQuery.mode==='tags')||S.dupShowIgnored);}

function dupSmartThr(){return S._dupQuery?S.dupThreshold:_dupThr();}

function dupSmartBtn(gi){
if(!dupSmartOn())return '';
var ok=dupSmartThr()<=SMART_MAX;
return '<button class="btn btn-sm btn-warning" onclick="event.stopPropagation();dupSmartCleanGroup('+gi+')" style="margin-right:6px'+(ok?'':';opacity:.5')+'" title="'+(ok?'Keep the best copy of this group and move the lesser copies to the trash — only copies that are the same picture, pixel for pixel':'Set Max difference to '+SMART_MAX+'% or less first')+'">✨ Smart clean</button>';}

/* How much JPEG damage the pixels show, in words. */
function _scGrade(g){if(g==null)return '';if(g<=1.03)return 'no visible compression';if(g<=1.15)return 'light compression';if(g<=1.35)return 'medium compression';if(g<=1.6)return 'strong compression';return 'heavy compression';}

function _scRow(c,note,col){
var im=findImageAnywhere(c.id);var th='/thumb/'+c.id+(im&&im.fphash?'?h='+im.fphash:'');
var bits=[];if(c.w)bits.push(c.w+'×'+c.h);if(c.size)bits.push(fmtBytes(c.size));if(c.fmt)bits.push(c.fmt);var gr=_scGrade(c.grid);if(gr)bits.push(gr);
return '<div style="display:flex;gap:10px;align-items:center;margin:6px 0"><img src="'+th+'" style="width:46px;height:46px;object-fit:cover;border-radius:5px;flex:none;border:1px solid var(--border)"/>'
 +'<div style="min-width:0;font-size:12px;line-height:1.45"><div style="font-weight:600;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(c.filename)+'</div>'
 +'<div style="color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">📁 '+esc(c.folder||'')+'</div>'
 +'<div style="color:var(--text-secondary)">'+esc(bits.join(' · '))+'</div>'
 +(note?'<div style="color:'+(col||'var(--text-secondary)')+'">'+esc(note)+'</div>':'')+'</div></div>';}

async function dupSmartCleanGroup(gi){
if(!dupSmartOn())return;
if(dupSmartThr()>SMART_MAX)return showToast('Smart clean works up to Max difference '+SMART_MAX+'% — beyond that a group is mostly pictures that are merely alike','error');
var g=S.dupGroups&&S.dupGroups[gi];if(!g)return;
var ids=(g.images||g).map(function(i){return i.id;});
if(S._dupQuery&&S._dupQuery.imgId&&ids.indexOf(S._dupQuery.imgId)<0)ids.push(S._dupQuery.imgId);
if(ids.length<2)return;
showToast('Comparing '+ids.length+' pictures pixel by pixel…');
var plan=null;
try{plan=await api('/api/duplicates/smart-clean',{method:'POST',body:JSON.stringify({groups:[ids]})});}catch(e){plan={error:String(e)};}
if(!plan||plan.error)return showToast('Smart clean: '+((plan&&plan.error)||'failed'),'error');
var rm=plan.remove||[],best=plan.best||[],stay=plan.skipped||[];
var h='<b>Smart clean — Group '+(gi+1)+'</b>';
h+='<div style="margin-top:12px;font-weight:600;color:var(--success)">Stays'+(best.length>1?' — '+best.length+' copies, none better on both counts':'')+'</div>'
 +(best.length>1?'<div style="font-size:12px;color:var(--text-muted)">More pixels in one, less compression in another — or formats whose compression cannot be compared (WebP, HEIC, AVIF). That is yours to decide.</div>':'');
best.forEach(function(c){h+=_scRow(c,best.length>1?'':'most pixels, least compression','var(--success)');});
if(rm.length){h+='<div style="margin-top:12px;font-weight:600;color:var(--danger)">Moves to the trash — '+rm.length+' ('+fmtBytes(plan.bytes||0)+')</div>';
  rm.forEach(function(c){h+=_scRow(c,'the same picture, pixel for pixel, at a lower quality','var(--danger)');});}
if(stay.length){h+='<div style="margin-top:12px;font-weight:600;color:var(--text-secondary)">Also stays</div>';
  stay.forEach(function(c){h+=_scRow(c,c.why);});}
if(!rm.length){await showConfirm('<div style="max-height:62vh;overflow:auto;padding-right:4px">'+h+'<div style="margin-top:12px">Nothing in this group can go without losing something.</div></div>',[{label:'OK',key:'ok',cls:'primary'}]);return;}
h+='<div style="margin-top:12px;font-size:12px;color:var(--text-muted)">GIFs, videos and animated pictures are never removed. Ctrl+Z brings everything back.</div>';
var ok=await showConfirm('<div style="max-height:62vh;overflow:auto;padding-right:4px">'+h+'</div>',[{label:'Cancel',key:'cancel'},{label:'Move '+rm.length+' to trash',key:'ok',cls:'danger'}]);
if(!ok)return;
var r=null;
try{r=await api('/api/duplicates/smart-clean',{method:'POST',body:JSON.stringify({apply:true,remove:rm.map(function(p){return {id:p.id,keep:p.keep};})})});}catch(e){r={error:String(e)};}
if(!r||r.error)return showToast('Smart clean: '+((r&&r.error)||'failed'),'error');
if(r.trash_ids&&r.trash_ids.length)pushUndo({type:'delete_bulk',trashIds:r.trash_ids});
showToast(r.deleted+' cop'+(r.deleted!==1?'ies':'y')+' moved to the trash'+((r.errors||[]).length?' — '+r.errors.length+' could not be moved':''),'success',true);
var gone=new Set(rm.map(function(p){return p.id;}));
S.selectedImages.clear();
var a=g.images||g;for(var i=a.length-1;i>=0;i--){if(gone.has(a[i].id))a.splice(i,1);}
if(S._dupQuery){
  /* the slider re-filters from allMatches, which would bring the deleted back */
  S._dupQuery.allMatches=(S._dupQuery.allMatches||[]).filter(function(m){return !gone.has(m.id);});
  if(gone.has(S._dupQuery.imgId)){clearDupQuery();Promise.all([loadImagesPreserve(),loadFolders(),loadCharacters(),loadStats()]);return;}
}else S.dupGroups=S.dupGroups.filter(function(x){return (x.images||x).length>1;});
var dr=document.getElementById('dup-results');if(dr)dr.innerHTML=renderDupGroups(S.dupGroups);
var tot=S.dupGroups.reduce(function(n,x){return n+(x.images||x).length;},0);
var st=document.getElementById('dup-stats');if(st)st.textContent=S.dupGroups.length+' group'+(S.dupGroups.length!==1?'s':'')+' · '+tot+' images';
updateDupSelectionUI();
Promise.all([loadImagesPreserve(),loadFolders(),loadCharacters(),loadStats()]);
}
