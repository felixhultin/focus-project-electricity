
'use strict';
(()=>{
 const select=document.getElementById('word-select');
 if(!select)return;
 const sections=[...document.querySelectorAll('section[id^="word-"]')];
 const choose=()=>{sections.forEach(section=>{section.hidden=section.id!==select.value;});};
 const restore=()=>{
  const word=new URLSearchParams(location.search).get('word');
  const byWord=[...select.options].find(option=>option.textContent===word);
  const byHash=[...select.options].find(option=>'#'+option.value===location.hash);
  select.value=(byHash||byWord||select.options[0]).value;choose();
 };
 select.addEventListener('change',()=>{
  choose();const url=new URL(location.href);
  url.searchParams.set('word',select.selectedOptions[0].textContent);
  url.hash=select.value;history.replaceState(null,'',url);
 });
 window.addEventListener('hashchange',restore);
 window.addEventListener('popstate',restore);
 restore();
})();
