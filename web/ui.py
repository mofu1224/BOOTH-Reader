"""Image-first library UI, with no external scripts, fonts or UI dependencies."""

# ruff: noqa: RUF001 -- Japanese UI copy uses native punctuation.

from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import urlsplit

STYLE = """
:root{color-scheme:light;--bg:#fafafa;--surface:#fff;--ink:#1a1a1a;--muted:#666;--line:#e5e5e5;--accent:#1a1a1a;--soft:#ededed;--radius:2px;--danger:#a32929;--gutter:clamp(20px,4.2vw,64px)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);line-height:1.6}
button,input,select{font:inherit;color:inherit;border:1px solid var(--line);background:var(--surface)}button{cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}button.primary{background:var(--accent);border-color:var(--accent);color:white}
button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid var(--accent);outline-offset:3px}a{color:var(--accent)}[hidden]{display:none!important}
.skip{position:absolute;left:16px;top:-80px;padding:12px;z-index:10}.skip:focus{top:12px}
.shell{min-height:100vh}.sidebar{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:0 32px;align-items:center;background:var(--bg);border-bottom:1px solid var(--line);padding:24px var(--gutter) 0}
.brand{grid-column:1;grid-row:1;font-family:Arial,'Yu Gothic UI',sans-serif;font-size:20px;font-weight:600;letter-spacing:-.8px;line-height:1.2;padding-bottom:24px}.brand span{font-weight:400}
.nav button{text-align:left;border:0;background:transparent;display:flex;align-items:center;justify-content:space-between;gap:12px}.nav-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.count{font-variant-numeric:tabular-nums;color:var(--muted)}.sidebar-heading{display:flex;justify-content:space-between;align-items:center;color:var(--muted)}.sidebar-heading button{border:0;min-height:32px;padding:2px 8px}
.connection{grid-column:3;grid-row:1;display:flex;align-items:center;gap:16px;padding-bottom:24px}.connection button{font-size:12px;background:var(--soft);border-color:transparent}.auth-state{font-size:12px;color:var(--muted);font-weight:400}
main{min-width:0;width:100%;margin:0 auto}h2{font-size:21px;margin:0 0 8px}p{margin:0}.muted{color:var(--muted)}.actions{display:flex;gap:8px;flex-wrap:wrap}.toolbar{display:flex;align-items:center;flex-wrap:wrap}.search{flex:1;min-width:180px;position:relative}.search input{width:100%}.toolbar label{font-size:12px;color:var(--muted)}.toolbar select{margin-left:8px}.summary{display:flex;align-items:center;justify-content:space-between;color:var(--muted)}
.grid{display:grid}.product{min-width:0;display:flex;flex-direction:column}.cover{aspect-ratio:1;display:grid;place-items:center;position:relative;overflow:hidden}.cover img{width:100%;height:100%;object-fit:contain;position:absolute;inset:0}.no-image{font-size:12px;color:var(--muted)}.product-info{display:flex;flex-direction:column;flex:1}.shop{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.product h2{margin-top:0;overflow-wrap:anywhere}.meta{display:flex;flex-wrap:wrap;margin-top:auto;color:var(--muted)}.badge{max-width:100%;overflow-wrap:anywhere}.product-actions{display:flex;gap:6px}.move{display:flex;gap:6px;margin-top:8px}.move button{flex:1;min-height:36px}.product[draggable=true]{cursor:grab}.product.dragging{opacity:.5}
.empty{text-align:center;border:1px solid var(--line)}.pager{display:flex;gap:16px;align-items:center;justify-content:center;margin:32px 0;font-size:12px}.notice{font-size:13px;padding:12px 16px;border:1px solid var(--line);margin-bottom:20px;overflow-wrap:anywhere}.notice:empty{display:none}
.cover img{background:inherit}
#list-nav{flex-wrap:nowrap;overflow-x:auto;overflow-y:hidden;scrollbar-width:thin;overscroll-behavior-x:contain}#list-nav button{flex:0 0 auto;position:relative;touch-action:none;user-select:none;cursor:grab}#list-nav button.dragging{z-index:2;cursor:grabbing;background:var(--soft);box-shadow:0 2px 8px #0002;will-change:transform}#list-nav.sorting{cursor:grabbing}
details.downloads{border-top:1px solid var(--line)}summary{cursor:pointer}#download-rows{display:grid;gap:8px;margin:16px 0}.download-row{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;border-bottom:1px solid var(--line);padding:8px 0;overflow-wrap:anywhere}
dialog{border:1px solid var(--line);width:min(680px,calc(100% - 32px));max-height:85vh;color:var(--ink)}.dialog-header{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:18px}.dialog-header h2{margin:0}.dialog-header button{min-height:36px;padding:5px 12px}.field{display:grid;gap:8px;margin:18px 0}.field input{width:100%}.candidate{display:flex;gap:12px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line)}.candidate img{width:56px;height:56px;object-fit:contain;background:var(--bg)}.candidate-info{flex:1;min-width:0;font-size:13px;overflow-wrap:anywhere}.candidate-info small{display:block;color:var(--muted)}#candidate-rows{max-height:42vh;overflow:auto}.dialog-error{font-size:13px;margin:12px 0}.dialog-error:empty{display:none}
body{font-family:Arial,'Yu Gothic UI',Meiryo,system-ui,sans-serif;font-size:14px}
button,input,select{border-radius:var(--radius);font-size:13px;min-height:42px;padding:10px 16px}
button:hover{background:var(--soft);border-color:#aaa}button.primary{font-weight:400}button.primary:hover{background:#333;color:#fff}
.skip{background:var(--surface)}
.nav{display:flex;flex-wrap:wrap;gap:4px;min-width:0}.nav button{width:auto;max-width:100%;font-size:13px;padding:10px 14px;border-radius:2px}.nav button[aria-current=page]{color:var(--ink);font-weight:400;background:var(--soft)}.count{font-size:11px}
#main-nav{grid-column:2;grid-row:1;align-self:center;padding-bottom:24px}
.sidebar-heading{grid-column:1;grid-row:2;margin:0;padding:12px 0;font-size:11px;font-weight:400;border-top:1px solid var(--line);gap:20px}.sidebar-heading button{font-size:18px;background:transparent}
#list-nav{grid-column:2 / 4;grid-row:2;border-top:1px solid var(--line);padding:10px 0;align-self:stretch;align-items:center}.nav-label{max-width:320px}
main{padding:64px var(--gutter) 64px;max-width:1760px}.topbar{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:40px}.topbar>div:first-child{min-width:0}h1{font-size:36px;font-weight:400;letter-spacing:-.05em;line-height:1.2;margin:0;overflow-wrap:anywhere}h2{font-weight:400}.topbar .actions{gap:12px;flex-shrink:0}.topbar .actions button{min-width:120px}.topbar .actions .primary{min-width:180px;display:flex;align-items:center;justify-content:space-between;gap:24px}
.toolbar{border-top:1px solid var(--line);padding-top:24px;margin:0 0 24px;gap:16px}.search{max-width:520px}.search input{background:transparent;padding:13px 16px}.toolbar label{margin-left:auto}.toolbar select{background:transparent;max-width:100%}.summary{margin:0 0 24px;font-size:11px;letter-spacing:.02em}
.grid{grid-template-columns:repeat(auto-fill,minmax(min(220px,100%),1fr));gap:36px 24px}.product{background:transparent;border:0;border-radius:0;overflow:visible}.cover{background:#f0f0f0;border:1px solid var(--line)}.product-info{padding:16px 0 0}.shop{font-size:11px;margin-bottom:8px}.product h2{font-size:14px;font-weight:400;line-height:1.7;margin-bottom:14px}.meta{font-size:11px;gap:10px}.badge{border-radius:2px;background:var(--soft);padding:2px 6px}.product-actions{border-top:1px solid var(--line);padding-top:12px;margin-top:16px;flex-wrap:wrap}.product-actions button{background:transparent;font-size:11px;min-height:36px;padding:6px 12px}.product-actions button:hover{background:var(--soft)}.move button{font-size:11px}
.empty{padding:80px 24px;border-style:solid;border-radius:0;background:transparent}.empty h2{font-weight:400;font-size:24px;margin-bottom:12px}.empty button{min-width:180px}.steps{text-align:left;max-width:600px;margin:20px auto 28px;padding-left:1.5em;color:var(--muted);font-size:13px;line-height:1.9}.steps li{margin:0}.notice{border-radius:2px;background:var(--surface)}.notice.error{border-color:var(--danger);background:#fff5f5;color:var(--danger)}.dialog-error{color:var(--danger)}
details.downloads{margin-top:64px;padding-top:24px}#library-path{font-size:11px;overflow-wrap:anywhere;margin-top:8px}summary{font-size:13px;font-weight:400}
dialog{border-radius:4px;padding:32px;background:var(--surface)}dialog::backdrop{background:#0005}.dialog-header h2{font-size:22px;font-weight:400}.candidate img{border-radius:2px}.field{font-size:13px}
@media(min-width:1500px){.grid{grid-template-columns:repeat(auto-fill,minmax(min(240px,100%),1fr))}}
@media(max-width:1000px){.sidebar{gap:0 20px}.connection{flex-direction:column;align-items:flex-end;gap:8px}.topbar{display:block}.topbar .actions{margin-top:24px}.grid{grid-template-columns:repeat(auto-fill,minmax(min(190px,100%),1fr))}.nav-label{max-width:220px}}
@media(max-width:650px){.sidebar{grid-template-columns:minmax(0,1fr) auto;padding:20px 16px 0;gap:0 12px}.brand{font-size:18px}.connection{grid-column:2;grid-row:1 / 3;padding-bottom:20px;gap:6px}.connection button{padding:7px 12px;min-height:36px}.auth-state{font-size:10px}#main-nav{grid-column:1 / 3;grid-row:3;border-top:1px solid var(--line);padding:10px 0}.sidebar-heading{grid-column:1 / 3;grid-row:4;padding:10px 0 0;border-top:1px solid var(--line);justify-content:flex-start}#list-nav{grid-column:1 / 3;grid-row:5;border-top:0;padding:0 0 12px}.nav button{padding:8px 12px;font-size:12px}.nav-label{max-width:220px}main{padding:40px 16px 48px}h1{font-size:30px;margin:0}.topbar{margin-bottom:32px}.topbar .actions{margin-top:24px;gap:8px}.topbar .actions button{min-width:0}.topbar .actions .primary{min-width:170px;gap:20px}.toolbar{padding-top:20px;gap:12px}.search{flex-basis:100%;max-width:none}.toolbar label{margin-left:0;font-size:11px}.toolbar select{margin-left:6px;padding:8px}.grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:28px 14px}.product-info{padding:12px 0 0}.product h2{font-size:12px}.product-actions{gap:6px}.product-actions button{font-size:10px;padding:6px 8px;min-height:36px}.shop,.meta{font-size:10px}.summary{font-size:10px}.empty{padding:56px 16px}.empty h2{font-size:21px}dialog{padding:20px}.candidate{align-items:flex-start}.candidate button{font-size:12px;padding:6px 10px}}
@media(max-width:650px){.brand{padding-bottom:20px}.connection{grid-row:1}#main-nav{grid-row:2}.sidebar-heading{grid-row:3}#list-nav{grid-row:4}main{padding-top:32px}}
@media(prefers-reduced-motion:no-preference){button{transition:border-color .15s,background .15s}.cover{transition:border-color .15s}.product:hover .cover{border-color:#999}}
"""

SCRIPT = r"""
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const imageURL = v => {try {const u=new URL(v);return u.protocol==='https:' ? u.href : '';}catch{return '';}};
let data=JSON.parse($('initial-data').textContent), view='all', page=1, busy=false, lastAuth=null, listDrag=null;
const size=48, collator=new Intl.Collator('ja',{numeric:true,sensitivity:'base'});
let memberMap=new Map(), listMap=new Map();
function indexData(){
  memberMap=new Map();
  listMap=new Map(data.lists.map(l=>[String(l.list_id),l]));
  for(const m of data.members){
    if(!memberMap.has(m.item_id)) memberMap.set(m.item_id,[]);
    memberMap.get(m.item_id).push(m);
  }
}
const current=()=>listMap.get(view);
const memberships=id=>memberMap.get(id)||[];
const unclassified=()=>data.items.filter(i=>!memberships(i.item_id).length);
function say(text,error=false){$('msg').textContent=text;$('msg').classList.toggle('error',error);}
async function request(url,body){const r=await fetch(url,body===undefined?{headers:{Accept:'application/json'}}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const j=await r.json();if(!r.ok){const base=j.error||'処理に失敗しました';throw new Error(j.hint&&!String(base).includes(j.hint)?base+' '+j.hint:base);}return j;}
async function action(label,fn){if(busy||listDrag)return;busy=true;say(label);updateDisabled();try{await fn();}catch(e){say(e.message,true);if($('add-dialog').open)$('add-error').textContent=e.message;if($('cookie-dialog').open)$('cookie-error').textContent=e.message;if($('create-dialog').open)$('create-error').textContent=e.message;}finally{busy=false;updateDisabled();}}
function updateDisabled(){document.querySelectorAll('[data-write]').forEach(b=>b.disabled=busy);$('sel-sort').disabled=busy;$('b-delete-list').disabled=busy;}
function navButton(key,label,count){const list=listMap.has(key);return `<button data-view="${esc(key)}" ${list?'title="横にドラッグで並べ替え・自動保存（Alt＋左右キーでも移動）"':''} aria-current="${key===view?'page':'false'}"><span class="nav-label">${esc(label)}</span><span class="count">${count}</span></button>`;}
function renderNav(){ $('main-nav').innerHTML=navButton('all','すべての商品',data.items.length)+navButton('unclassified','未分類',unclassified().length);$('list-nav').innerHTML=data.lists.map(l=>navButton(String(l.list_id),l.name,data.members.filter(m=>m.list_id===l.list_id).length)).join('');$('c-lists').textContent=data.lists.length;}
function sortedRows(filter=true) {
  let rows=data.items.slice();
  const list=current(), sort=$('sel-sort').value;
  if(view==='unclassified') rows=unclassified();
  if(list) rows=rows.filter(i=>memberships(i.item_id).some(m=>m.list_id===list.list_id));
  rows.sort((a,b)=>{
    if(sort==='name') return collator.compare(a.title,b.title)||collator.compare(a.item_id,b.item_id);
    if(sort==='shop') return collator.compare(a.shop,b.shop)||collator.compare(a.title,b.title);
    // BOOTH's library is newest-first even when it omits purchase dates.
    const date=collator.compare(a.purchase_date||'',b.purchase_date||'');
    const order=(b.library_order||0)-(a.library_order||0);
    return (sort==='oldest'?1:-1)*(date||order)||collator.compare(a.item_id,b.item_id);
  });
  const q=$('search').value.trim().toLocaleLowerCase('ja');
  return filter&&q?rows.filter(i=>(i.title+' '+i.shop).toLocaleLowerCase('ja').includes(q)):rows;
}
function card(i){const list=current();const owner=memberships(i.item_id).map(m=>data.lists.find(l=>l.list_id===m.list_id)?.name).filter(Boolean).join(' / ');const img=imageURL(i.thumbnail);return `<article class="product" data-item="${esc(i.item_id)}"><div class="cover"><span class="no-image">画像なし</span>${img?`<img src="${esc(img)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">`:''}</div><div class="product-info"><p class="shop">${esc(i.shop||'ショップ名未取得')}</p><h2>${esc(i.title)}</h2><div class="meta"><span>${esc(i.purchase_date||'購入日未取得')}</span><span class="badge">${esc(owner||'未分類')}</span></div><div class="product-actions"><button data-write data-dl="${esc(i.item_id)}">ダウンロード</button>${list?`<button data-write data-remove="${esc(i.item_id)}" aria-label="${esc(i.title)}をリストから外す">外す</button>`:!owner?`<button data-write data-choose="${esc(i.item_id)}">リストへ</button>`:''}</div></div></article>`;}
function render(){const list=current();$('view-title').textContent=list?list.name:view==='all'?'すべての商品':'未分類';$('b-add-items').hidden=!list;$('b-delete-list').hidden=!list;renderNav();const rows=sortedRows(),pages=Math.max(1,Math.ceil(rows.length/size));page=Math.min(page,pages);$('result-count').textContent=rows.length+' 商品';$('library-total').textContent=data.items.length+' 商品のライブラリ';$('grid').innerHTML=rows.slice((page-1)*size,page*size).map(card).join('');$('empty').hidden=rows.length>0;$('empty-title').textContent=$('search').value?'該当する商品がありません':list?'このリストはまだ空です':view==='unclassified'?'すべての商品が分類済みです':'ライブラリをはじめましょう';$('empty-cookie').hidden=!!data.items.length||!!list;$('empty-steps').hidden=!!data.items.length||!!list||!!$('search').value;$('page-label').textContent=page+' / '+pages;$('page-prev').disabled=page===1;$('page-next').disabled=page===pages;$('pager').hidden=pages===1;updateDisabled();}
function selectView(key){view=key;page=1;$('search').value='';const sort=current()?.sort;$('sel-sort').value=sort&&sort!=='manual'?sort:'newest';render();}
async function reload(){data=await request('/library');indexData();if(view!=='all'&&view!=='unclassified'&&!current())view='all';render();}
async function sync(){await action('BOOTHの全ページを同期しています…',async()=>{const j=await request('/purchases/update',{});await reload();const n=j.updated??j.count??0;say(n>0?n+' 商品を同期しました。':'同期しましたが購入が見つかりませんでした。Cookieが正しいか、BOOTHに購入履歴があるか確認してください。');});}
function openCookie(){if(lastAuth&&!confirm('登録済みのCookieを置き換えますか？'))return;$('cookie-error').textContent='';$('cookie-dialog').showModal();}
let candidatePage=1, candidateItem=null;
function renderCandidates(){if(candidateItem){$('candidate-search-field').hidden=true;$('candidate-rows').innerHTML=data.lists.map(l=>`<div class="candidate"><span class="candidate-info">${esc(l.name)}</span><button data-write data-add-to="${l.list_id}" data-add-id="${esc(candidateItem)}">追加</button></div>`).join('')||'<p class="muted">先にリストを作成してください。</p>';$('candidate-pager').hidden=true;return;}$('candidate-search-field').hidden=false;const q=$('candidate-search').value.toLowerCase();const rows=unclassified().filter(i=>(i.title+' '+i.shop).toLowerCase().includes(q));const pages=Math.max(1,Math.ceil(rows.length/30));candidatePage=Math.min(candidatePage,pages);$('candidate-rows').innerHTML=rows.slice((candidatePage-1)*30,candidatePage*30).map(i=>`<div class="candidate">${imageURL(i.thumbnail)?`<img src="${esc(imageURL(i.thumbnail))}" alt="" loading="lazy" referrerpolicy="no-referrer">`:''}<span class="candidate-info">${esc(i.title)}<small>${esc(i.shop)}</small></span><button data-write data-add-to="${esc(view)}" data-add-id="${esc(i.item_id)}">追加</button></div>`).join('')||'<p class="muted">追加できる未分類の商品がありません。</p>';$('candidate-page-label').textContent=candidatePage+' / '+pages;$('candidate-prev').disabled=candidatePage===1;$('candidate-next').disabled=candidatePage===pages;$('candidate-pager').hidden=pages===1;updateDisabled();}
function openAdd(item=null){candidateItem=item;candidatePage=1;$('candidate-search').value='';$('add-error').textContent='';$('add-title').textContent=item?'追加先のリストを選ぶ':'商品を追加';renderCandidates();$('add-dialog').showModal();}
async function saveListOrder(ids,keepNav=false){await action('マイリストの並び順を保存しています…',async()=>{const previous=data.lists.slice(),byId=new Map(data.lists.map(l=>[l.list_id,l]));data.lists=ids.map(id=>byId.get(id));if(!keepNav)renderNav();try{await request('/lists',{action:'reorder-lists',list_ids:ids});say('マイリストの並び順を保存しました。');}catch(e){data.lists=previous;renderNav();throw e;}});}
document.addEventListener('click',ev=>{const b=ev.target.closest('button');if(!b||b.disabled)return;if(b.dataset.view){selectView(b.dataset.view);return;}if(b.dataset.close){$(b.dataset.close).close();return;}if(b.dataset.dl){action('ダウンロードを開始しています…',async()=>{await request('/download',{item_id:b.dataset.dl});say('ダウンロードを開始しました。下部の進捗で確認できます。');$('downloads-panel').open=true;await pollDownloads();});return;}if(b.dataset.choose){openAdd(b.dataset.choose);return;}if(b.dataset.remove){action('商品をリストから外しています…',async()=>{await request('/lists',{action:'remove',list:view,item_id:b.dataset.remove});await reload();say('リストから外しました。未分類から再追加できます。');});return;}if(b.dataset.addTo){action('商品を追加しています…',async()=>{await request('/lists',{action:'add',list:b.dataset.addTo,item_id:b.dataset.addId});await reload();if(candidateItem)$('add-dialog').close();else renderCandidates();say('商品をリストに追加しました。');});return;}});
$('b-update').onclick=sync;$('b-refresh').onclick=()=>action('表示を更新しています…',async()=>{await reload();say('表示を更新しました。');});
$('b-cookie').onclick=openCookie;$('empty-cookie').onclick=openCookie;
$('cookie-form').onsubmit=async ev=>{ev.preventDefault();const f=$('cookie-file').files[0];if(!f)return;if(f.size>1048576){$('cookie-error').textContent='Cookieファイルは1MB以下にしてください。';return;}let imported=false;await action('Cookieを登録しています…',async()=>{const content=await f.text();await request('/auth/import',{content});$('cookie-file').value='';$('cookie-dialog').close();$('auth-state').textContent='Cookie登録済み';lastAuth='imported';imported=true;say('Cookieを登録しました。');});if(imported){try{const a=await request('/auth/status');lastAuth=authKey(a);}catch{}await sync();}};
$('b-new-list').onclick=()=>{$('create-error').textContent='';$('create-dialog').showModal();};
$('create-form').onsubmit=ev=>{ev.preventDefault();const name=$('in-listname').value.trim();if(!name)return;action('リストを作成しています…',async()=>{await request('/lists',{action:'create',name});await reload();selectView(String(data.lists.find(l=>l.name===name).list_id));$('create-dialog').close();$('in-listname').value='';say('リストを作成しました。');});};
$('b-add-items').onclick=()=>openAdd();$('candidate-search').oninput=()=>{candidatePage=1;renderCandidates();};$('candidate-prev').onclick=()=>{candidatePage--;renderCandidates();};$('candidate-next').onclick=()=>{candidatePage++;renderCandidates();};
$('b-delete-list').onclick=()=>{const list=current();if(!list||!confirm('「'+list.name+'」を削除しますか？商品は未分類に戻ります。'))return;action('リストを削除しています…',async()=>{await request('/lists',{action:'delete',name:String(list.list_id)});selectView('all');await reload();say('リストを削除しました。商品は保持しています。');});};
$('search').oninput=()=>{page=1;render();};$('sel-sort').onchange=()=>{page=1;if(current()){action('並び順を保存しています…',async()=>{await request('/lists',{action:'sort',list:view,sort:$('sel-sort').value});await reload();say('並び順を保存しました。');});}else render();};
$('page-prev').onclick=()=>{page--;render();$('view-title').scrollIntoView();};$('page-next').onclick=()=>{page++;render();$('view-title').scrollIntoView();};
const listBar=$('list-nav'), reduceMotion=matchMedia('(prefers-reduced-motion:reduce)');
let suppressListClick=false;
function slideList(button,from){if(!reduceMotion.matches&&Math.abs(from)>.5)button.animate([{transform:`translateX(${from}px)`},{transform:'translateX(0)'}],{duration:180,easing:'cubic-bezier(.2,.8,.2,1)'});}
function stepListDrag(time){
  const d=listDrag;if(!d||!d.active)return;
  const bar=listBar.getBoundingClientRect(),dt=Math.min(32,time-(d.time||time));d.time=time;
  if(d.x<bar.left+28)listBar.scrollLeft-=dt*.45;
  else if(d.x>bar.right-28)listBar.scrollLeft+=dt*.45;
  const left=Math.max(bar.left,Math.min(bar.right-d.width,d.left+d.x-d.startX)),center=left+d.width/2;
  const buttons=[...listBar.children],index=buttons.indexOf(d.button);
  const natural=b=>{const r=b.getBoundingClientRect();const x=new DOMMatrixReadOnly(getComputedStyle(b).transform).m41;return r.left-x;};
  const next=buttons[index+1],previous=buttons[index-1];
  let neighbor=null;
  if(next&&center>natural(next)+next.offsetWidth/2)neighbor=next;
  else if(previous&&center<natural(previous)+previous.offsetWidth/2)neighbor=previous;
  if(neighbor){
    const before=neighbor.getBoundingClientRect().left;
    neighbor.getAnimations().forEach(a=>a.cancel());
    if(neighbor===next)listBar.insertBefore(next,d.button);else listBar.insertBefore(d.button,previous);
    slideList(neighbor,before-neighbor.getBoundingClientRect().left);
  }
  d.button.style.transform=`translateX(${left-natural(d.button)}px)`;
  d.frame=requestAnimationFrame(stepListDrag);
}
function finishListDrag(cancel=false){
  const d=listDrag;if(!d)return;cancelAnimationFrame(d.frame);
  if(d.active&&!cancel){stepListDrag(performance.now());cancelAnimationFrame(d.frame);}
  listDrag=null;
  if(listBar.hasPointerCapture(d.pointer))listBar.releasePointerCapture(d.pointer);
  listBar.classList.remove('sorting');d.button.classList.remove('dragging');
  const shift=new DOMMatrixReadOnly(getComputedStyle(d.button).transform).m41;d.button.style.transform='';
  if(!d.active)return;
  suppressListClick=true;setTimeout(()=>{suppressListClick=false;},0);
  if(cancel){renderNav();return;}
  slideList(d.button,shift);
  const ids=[...listBar.children].map(b=>Number(b.dataset.view));
  if(ids.some((id,i)=>id!==data.lists[i].list_id))saveListOrder(ids,true);
}
listBar.addEventListener('pointerdown',ev=>{
  const button=ev.target.closest('[data-view]');if(!button||busy||listDrag||ev.button!==0||!ev.isPrimary)return;
  button.getAnimations().forEach(a=>a.cancel());const rect=button.getBoundingClientRect();
  listDrag={button,pointer:ev.pointerId,startX:ev.clientX,x:ev.clientX,left:rect.left,width:rect.width,active:false,frame:0,time:0};
  listBar.setPointerCapture(ev.pointerId);
});
listBar.addEventListener('pointermove',ev=>{
  const d=listDrag;if(!d||ev.pointerId!==d.pointer)return;d.x=ev.clientX;
  if(!d.active&&Math.abs(d.x-d.startX)>5){d.active=true;d.button.classList.add('dragging');listBar.classList.add('sorting');d.frame=requestAnimationFrame(stepListDrag);}
  if(d.active)ev.preventDefault();
});
listBar.addEventListener('pointerup',ev=>{if(listDrag?.pointer===ev.pointerId)finishListDrag();});
listBar.addEventListener('pointercancel',()=>finishListDrag(true));
listBar.addEventListener('lostpointercapture',()=>finishListDrag(true));
listBar.addEventListener('dragstart',ev=>ev.preventDefault());
listBar.addEventListener('click',ev=>{if(suppressListClick){ev.preventDefault();ev.stopPropagation();}else if(ev.target===listBar){const b=[...listBar.children].find(b=>{const r=b.getBoundingClientRect();return ev.clientX>=r.left&&ev.clientX<=r.right&&ev.clientY>=r.top&&ev.clientY<=r.bottom;});if(b)selectView(b.dataset.view);}},true);
document.addEventListener('keydown',ev=>{if(ev.key==='Escape'&&listDrag){ev.preventDefault();finishListDrag(true);}});
window.addEventListener('blur',()=>finishListDrag(true));window.addEventListener('resize',()=>finishListDrag(true));
$('list-nav').addEventListener('keydown',ev=>{if(!ev.altKey||!['ArrowLeft','ArrowRight'].includes(ev.key)||busy||listDrag)return;const b=ev.target.closest('[data-view]');if(!b)return;ev.preventDefault();const id=Number(b.dataset.view),ids=data.lists.map(l=>l.list_id),from=ids.indexOf(id),to=from+(ev.key==='ArrowLeft'?-1:1);if(from<0||to<0||to>=ids.length)return;ids.splice(to,0,ids.splice(from,1)[0]);saveListOrder(ids).then(()=>$('list-nav').querySelector(`[data-view="${id}"]`)?.focus());});
$('b-dlall').onclick=()=>{if(!confirm('全商品をダウンロードしますか？'))return;action('ダウンロードを開始しています…',async()=>{await request('/download',{all:true,concurrent:3});say('全商品のダウンロードを開始しました。');$('downloads-panel').open=true;await pollDownloads();});};
$('b-dlclear').onclick=()=>{if(!confirm('未完了のダウンロード (.part) を削除しますか？完了済みファイルと展開済みファイルは残ります。'))return;action('未完了ファイルを削除しています…',async()=>{await request('/downloads/cleanup',{});say('未完了ファイルを削除しました。');await pollDownloads();});};
async function pollDownloads(){if(!$('downloads-panel').open)return;try{const [d,h]=await Promise.all([request('/downloads?limit=1000'),request('/health')]);const labels={done:'完了',failed:'失敗',downloading:'ダウンロード中',pending:'待機中'};$('download-state').textContent=h.download.running?'実行中':h.download.ok===false?'失敗: '+h.download.error:'ダウンロード進捗';$('download-rows').innerHTML=d.downloads.map(r=>`<div class="download-row"><strong>${esc(labels[r.status]||r.status)}</strong><span>${esc(r.item_id)}</span><span>${esc(r.file_name)}</span></div>`).join('')||'<p class="muted">ダウンロード履歴はありません。</p>';}catch(e){$('download-state').textContent=e.message;}}
$('downloads-panel').ontoggle=pollDownloads;
const authKey=a=>String(a.revision??a.count);
async function checkAuth(){if(busy||listDrag||document.querySelector('dialog[open]'))return;try{const a=await request('/auth/status');if(listDrag)return;const key=authKey(a);$('auth-state').textContent='Cookie登録済み';$('b-cookie').textContent='Cookieを更新';if(key!==lastAuth){lastAuth=key;await sync();}}catch{$('auth-state').textContent='Cookie未登録';$('b-cookie').textContent='Cookieを登録';lastAuth=null;}}
document.addEventListener('error',ev=>{if(ev.target.tagName==='IMG')ev.target.hidden=true;},true);
indexData();render();checkAuth();setInterval(checkAuth,8000);setInterval(pollDownloads,3000);
"""


def render_index(data: dict[str, Any], error: str = "", library_path: str = "") -> str:
    data = {
        "items": data.get("items", []),
        "lists": data.get("lists", []),
        "members": data.get("members", []),
    }
    library_note = (
        f'<p class="muted" id="library-path">購入ファイルの保存先: {html.escape(library_path)}</p>'
        if library_path
        else ""
    )
    initial = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace("&", "\\u0026")
    cards = []
    for item in data["items"][:48]:
        title = html.escape(str(item.get("title", "")))
        shop = html.escape(str(item.get("shop", "")))
        thumbnail = str(item.get("thumbnail", ""))
        try:
            safe_image = urlsplit(thumbnail).scheme == "https" and bool(
                urlsplit(thumbnail).hostname
            )
        except ValueError:
            safe_image = False
        image = (
            f'<img src="{html.escape(thumbnail, quote=True)}" alt="" loading="lazy" referrerpolicy="no-referrer">'
            if safe_image
            else ""
        )
        cards.append(
            f'<article class="product"><div class="cover"><span class="no-image">画像なし</span>{image}</div><div class="product-info"><p class="shop">{shop}</p><h2>{title}</h2></div></article>'
        )
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BOOTH-Reader — ライブラリ</title><style>{STYLE}</style></head>
<body><a class="skip" href="#main">商品一覧へ移動</a><div class="shell">
<aside class="sidebar"><div class="brand">BOOTH<span> Reader</span></div>
<nav aria-label="ライブラリ" id="main-nav" class="nav"></nav>
<div class="sidebar-heading"><span>マイリスト <span id="c-lists">0</span></span><button id="b-new-list" data-write aria-label="リストを作成">＋</button></div><nav aria-label="マイリスト" id="list-nav" class="nav"></nav>
<div class="connection"><span class="auth-state" id="auth-state">Cookieを確認中</span><button id="b-cookie" data-write>Cookieを登録</button><a href="/third-party-terms" target="_blank" rel="noopener">第三者ソフトウェアの利用条件・データ通知</a></div></aside>
<main id="main"><header class="topbar"><div><h1 id="view-title">すべての商品</h1></div><div class="actions"><button id="b-update" class="primary" data-write><span>BOOTHと同期</span><span aria-hidden="true">→</span></button><button id="b-refresh" data-write>表示更新</button></div></header>
<div id="msg" class="notice" role="status" aria-live="polite">{html.escape(error)}</div>
<div class="toolbar"><div class="search"><input id="search" type="search" placeholder="商品名・ショップ名で検索" aria-label="商品を検索"></div><label for="sel-sort">商品の並び順<select id="sel-sort"><option value="newest">購入順（新しい順）</option><option value="oldest">購入順（古い順）</option><option value="name">名前順</option><option value="shop">ショップ順</option></select></label><button id="b-add-items" class="primary" data-write hidden>商品を追加</button><button id="b-delete-list" hidden>リスト削除</button></div>
<div class="summary"><span id="result-count">{len(data["items"])} 商品</span><span id="library-total"></span></div>
<section id="grid" class="grid" aria-label="商品一覧">{"".join(cards)}</section><div id="empty" class="empty" hidden><h2 id="empty-title"></h2><ol id="empty-steps" class="steps" hidden><li>「Cookieを登録」から、BOOTH / pixiv の Cookie JSON を選びます（登録済みならこの手順は不要です）。</li><li>「BOOTHと同期」で購入一覧を取り込みます。</li><li>商品を「リストへ」で分類し、「ダウンロード」で保存します。</li></ol><button id="empty-cookie" class="primary" data-write>Cookieを登録</button></div>
<div id="pager" class="pager" hidden><button id="page-prev">前のページ</button><span id="page-label"></span><button id="page-next">次のページ</button></div>
<details id="downloads-panel" class="downloads"><summary id="download-state">ダウンロード進捗</summary><div id="download-rows"></div>{library_note}<div class="actions"><button id="b-dlall" data-write>全商品をダウンロード</button><button id="b-dlclear" data-write>未完了ファイルを削除</button></div></details>
</main></div>
<dialog id="create-dialog"><div class="dialog-header"><h2>リストを作成</h2><button data-close="create-dialog" aria-label="リスト作成を閉じる">閉じる</button></div><form id="create-form"><label class="field" for="in-listname">リスト名<input id="in-listname" maxlength="128" required placeholder="例：アバター、衣装、あとで読む"></label><p id="create-error" class="dialog-error" role="alert"></p><button id="b-list-create" class="primary" data-write>リストを作成</button></form></dialog>
<dialog id="add-dialog"><div class="dialog-header"><h2 id="add-title">商品を追加</h2><button data-close="add-dialog" aria-label="商品追加を閉じる">閉じる</button></div><label class="field" id="candidate-search-field" for="candidate-search">未分類の商品を検索<input id="candidate-search" type="search" placeholder="商品名・ショップ名"></label><p id="add-error" class="dialog-error" role="alert"></p><div id="candidate-rows"></div><div id="candidate-pager" class="pager" hidden><button id="candidate-prev">前へ</button><span id="candidate-page-label"></span><button id="candidate-next">次へ</button></div></dialog>
<dialog id="cookie-dialog"><div class="dialog-header"><h2>Cookieを登録</h2><button data-close="cookie-dialog" aria-label="Cookie登録を閉じる">閉じる</button></div><form id="cookie-form"><label class="field" for="cookie-file">Cookieファイル（JSON・1MBまで）<input id="cookie-file" type="file" accept=".json,application/json" required></label><p id="cookie-error" class="dialog-error" role="alert"></p><button class="primary" data-write>登録して同期</button></form></dialog>
<noscript><p>リスト管理と自動同期にはJavaScriptを有効にしてください。</p></noscript><script id="initial-data" type="application/json">{initial}</script><script>{SCRIPT}</script></body></html>"""
