/* The one object every other file reads and writes, and the flags the server set.
 *
 * File 01 of 13 — the page loads these in number order.
 */

function _svgIcon(d){return '<svg class="mi" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'+d+'</svg>';}

var ICO={
explorer:_svgIcon('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
move:_svgIcon('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 13h6"/><path d="M13.5 11l2 2-2 2"/>'),
copy:_svgIcon('<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'),
cut:_svgIcon('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.12 15.88"/><path d="M14.47 14.48 20 20"/><path d="M8.12 8.12 12 12"/>'),
paste:_svgIcon('<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>'),
rename:_svgIcon('<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>'),
tags:_svgIcon('<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><circle cx="7" cy="7" r="1.3"/>'),
meta:_svgIcon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 15h6"/>'),
dup:_svgIcon('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>'),
dupt:_svgIcon('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/><path d="M8 11h6"/>'),
osimg:_svgIcon('<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15l-5-5L5 21"/>'),
trash:_svgIcon('<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'),
sub:_svgIcon('<path d="M3 6a2 2 0 0 1 2-2h3l2 2h4"/><path d="M7 12a2 2 0 0 1 2-2h3l2 2h5a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2z"/>')
};

var _dragHintShown = false;

function _lsJson(k){try{var v=JSON.parse(localStorage.getItem(k)||'{}');return (v&&typeof v==='object')?v:{};}catch(e){return {};}}

/* v4.57: the user's key bindings, filled from the server at start. Empty means
   every action uses the default in KEY_ACTIONS (02-util.js). */
var TI_KEYMAP={};

var S={page:'gallery',navEpoch:0,folderBusy:false,scanFolders:[],characters:[],folders:[],images:[],stats:{},ignoreWords:[],searchChips:[],pendingSearch:'',filter:{characters:[],ratings:[],folders:[],search:''},sort:localStorage.getItem('ti_sort')||'newest',order:localStorage.getItem('ti_order')||'desc',total:0,allLoaded:false,loadingMore:false,currentImageId:null,currentImageIndex:-1,scrollPosition:0,initialized:false,loading:false,_skipPush:false,openFolders:_lsJson('ti_open_folders'),filteredTotal:0,detailZoom:1,detailPan:{x:0,y:0},detailPanning:false,selectedImages:new Set(),selectedFolders:new Set(),lastSelectedFolderIdx:-1,lastSelectedIndex:-1,openTagGroups:_lsJson('ti_open_taggroups'),tagsModified:false,volume:parseFloat(localStorage.getItem('ti_volume'))||0.5,uiScale:Math.max(80,Math.min(150,parseInt(localStorage.getItem('ti_ui_scale'))||100)),dragIds:null,undoStack:[],watcherActive:false,clipboard:{ids:[],mode:null},folderColW:parseInt(localStorage.getItem('ti_folder_col_w'))||200,tagColW:parseInt(localStorage.getItem('ti_tag_col_w'))||200,cols:Math.max(1,Math.min(15,parseInt(localStorage.getItem('ti_grid_cols'))||8)),simMatch:Math.max(50,Math.min(95,parseInt(localStorage.getItem('ti_sim_match'))||70)),dupVerify:localStorage.getItem('ti_dup_verify')!=='0',dupShowIgnored:false,dupIgnoredCount:0,foldersCollapsed:localStorage.getItem('ti_folders_collapsed')==='1',tagsCollapsed:localStorage.getItem('ti_tags_collapsed')==='1',detailLibCollapsed:localStorage.getItem('ti_detail_lib')==='1',
detailBare:false,
detailSidebarCollapsed:localStorage.getItem('ti_ds_collapsed')==='1',inclSub:localStorage.getItem('ti_incl_sub')!=='0',thumbMode:localStorage.getItem('ti_thumb_mode')==='fixed'?'fixed':'ratio',tagMode:localStorage.getItem('ti_tagmode')==='tags'?'tags':'names',info:{visible:localStorage.getItem('ti_info_visible')!=='0',name:localStorage.getItem('ti_info_name')!=='0',folder:localStorage.getItem('ti_info_folder')!=='0',date:localStorage.getItem('ti_info_date')!=='0'}};

var DRAGGABLE_ATTR='draggable="true"';
