const notes=[...document.querySelectorAll('details.playtest')];
const toggle=document.querySelector('#notes-toggle');
if(toggle) toggle.addEventListener('click',()=>{const open=toggle.getAttribute('aria-pressed')!=='true';notes.forEach(n=>n.open=open);toggle.setAttribute('aria-pressed',String(open));toggle.textContent=open?'Collapse evidence & recovery':'Expand evidence & recovery';});
const cards=[...document.querySelectorAll('[data-search]')],search=document.querySelector('#search');
let group='All';
function filter(){let visible=0;const q=search.value.trim().toLowerCase();cards.forEach(c=>{const show=(group==='All'||c.dataset.group===group)&&c.dataset.search.includes(q);c.hidden=!show;if(show)visible++;});document.querySelector('#result-count').textContent=`${visible} of 8 adventures`;document.querySelector('#empty').hidden=visible!==0;}
if(search){search.addEventListener('input',filter);document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{group=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));filter();}));}
const printDetails=[...document.querySelectorAll('details')];
let printStates=[];
addEventListener('beforeprint',()=>{printStates=printDetails.map(n=>n.open);printDetails.forEach(n=>n.open=true);});
addEventListener('afterprint',()=>printDetails.forEach((n,i)=>n.open=printStates[i]??false));
