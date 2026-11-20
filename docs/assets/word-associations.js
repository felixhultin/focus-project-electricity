'use strict';
(()=>{
 const $=id=>document.getElementById(id),params=new URLSearchParams(location.search);
 const NS='http://www.w3.org/2000/svg';let catalog,corpusMeta,meta,data,points=[],highlight=null,request=0;
 const svgNode=(tag,attrs={},text)=>{const node=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))node.setAttribute(k,v);if(text!==undefined)node.textContent=text;return node;};
 const options=(node,values,selected)=>{node.replaceChildren(...values.map(([value,label])=>{const o=document.createElement('option');o.value=value;o.textContent=label;return o;}));node.value=values.some(([v])=>v===selected)?selected:values[0][0];};
 async function json(path){return window.siteDataJSON(path);}
 function busy(value){for(const id of ['word','corpus','resource','measure'])$(id).disabled=value;}
 function isSimilarity(){return $('measure').value==='similarity';}
 function score(point){return isSimilarity()?point.cosine:point.share;}
 function format(point){return isSimilarity()?point.cosine.toFixed(3):(100*point.share).toFixed(1)+'%';}
 function updateURL(){const q=new URLSearchParams({word:data.word,corpus:data.corpus,measure:$('measure').value});if($('resource').value!=='all')q.set('resource',$('resource').value);for(const id of ['from','to'])if($(id).value)q.set(id,$(id).value);if($('top').value!=='3')q.set('top',$('top').value);if($('minimum').value!=='5')q.set('minimum',$('minimum').value);history.replaceState(null,'','?'+q);}
 async function loadCorpus(desired){
  const version=++request;busy(true);$('status').setAttribute('role','status');$('status').textContent='Loading association data…';
  try{
   const entry=catalog.corpora.find(c=>c.corpus===$('corpus').value);const next=await json(entry.data);if(version!==request)return;
   corpusMeta=next;
   options($('resource'),[['all','All resources'],...(corpusMeta.resources||[]).map(r=>[r.id,r.label])],params.get('resource')||'all');
   params.delete('resource');await loadResource(desired||params.get('word'),version);
  }catch(error){fail(error);}
 }
 async function loadResource(desired,version=++request){
  busy(true);$('status').textContent='Loading resource data…';
  try{
   const selected=$('resource').value;
   const next=selected==='all'?corpusMeta:await json(corpusMeta.resources.find(r=>r.id===selected).data);
   if(version!==request)return;
   meta=next;options($('word'),meta.words.map(w=>[w,w]),desired||'ström');
   const available=meta.embedding_status==='ready';$('measure').querySelector('[value=similarity]').disabled=!available;
   const desiredMeasure=params.get('measure');if(desiredMeasure&&['similarity','cooccurrence'].includes(desiredMeasure))$('measure').value=desiredMeasure;
   if(!available)$('measure').value='cooccurrence';
   params.delete('measure');await loadWord(version);
  }catch(error){fail(error);}
 }
 async function loadWord(version=++request){
  busy(true);$('status').textContent='Loading '+$('word').value+'…';
  try{const next=await json(meta.files[$('word').value]);if(version!==request)return;data=next;highlight=null;$('selection').hidden=true;busy(false);$('status').textContent=meta.embedding_status==='ready'?'Both association measures are available.':'Co-occurrence is available. Word2Vec models are training in the background; reload later to enable similarity.';render();}
  catch(error){fail(error);}
 }
 function fail(error){$('status').setAttribute('role','alert');$('status').textContent='Could not load associations: '+error.message+'. Serve the docs folder over HTTP.';busy(false);}
 function render(){
  if(!data)return;
  const low=$('from').value===''?-Infinity:Number($('from').value),high=$('to').value===''?Infinity:Number($('to').value),minimum=Number($('minimum').value),top=Number($('top').value);
  const years=data.years.filter(r=>r.year>=low&&r.year<=high&&r.n>=minimum);
  points=years.flatMap(row=>(row[isSimilarity()?'similarity':'cooccurrence']||[]).slice(0,top).map((point,rank)=>({...point,year:row.year,n:row.n,model:row.model,rank})));
  $('headingWord').textContent='“'+data.word+'”';$('chartTitle').textContent=(isSimilarity()?'Embedding neighbours':'Nearby words')+' · '+data.corpus.toUpperCase()+(meta.resource?' · '+meta.resource.label:' · All resources');
  const allUsages=meta.sampling.selection==='all_available';
  const selectionNote=allUsages?'All available valid dated target usages are included, with no yearly cap. Years and resources have different amounts of data.':`Up to ${meta.sampling.per_word_year_cap} usages per term/year were selected across the whole corpus; resource subsets are not separately balanced.`;
  $('resourceNote').textContent=(meta.resource?`Resource: ${meta.resource.label} (${meta.resource.kind}). Counts, excerpts and model training use only this resource’s usages. `:'All resources in the selected corpus are included. Choose a resource to analyse one newspaper, author or document collection separately. ')+selectionNote+' Sparse years may have no results.';
  $('methodNote').textContent=isSimilarity()?'Cosine similarity from Word2Vec models trained on Mats target contexts in a five-year window centred on each displayed year. Neighbours can be semantically similar without occurring next to the target in that year.':'Percentage of this term’s analysed usages in each year containing the labelled word within ten tokens of the selected occurrence. Each word counts at most once per usage; at least two supporting usages are required.';
  const withPoints=new Set(points.map(p=>p.year)).size;
  $('stats').textContent=`${points.length.toLocaleString()} word–year points · ${withPoints} years · ${years.reduce((n,r)=>n+r.n,0).toLocaleString()} analysed usages in eligible years`+(isSimilarity()&&withPoints<years.length?` · ${years.length-withPoints} eligible years have no embedding neighbours`:'');
  $('settings').textContent=JSON.stringify({resource:meta.resource,sampling:meta.sampling,settings:meta.settings,source_digest:meta.source_digest,gensim_version:meta.gensim_version},null,2);
  $('clear').hidden=!highlight;$('save').disabled=!points.length;
  draw(years);table();updateURL();
 }
 function draw(years){
  const chart=$('chart');chart.replaceChildren();
  if(!points.length){const message=document.createElement('p');message.className='plot-empty';message.textContent='No associations meet these filters. Try a wider year range, a lower minimum sample size, or the other measure.';chart.append(message);return;}
  const first=Math.min(...years.map(r=>r.year)),last=Math.max(...years.map(r=>r.year));
  const width=$('expanded').checked?Math.max(1000,(last-first+1)*28):Math.max(1000,chart.clientWidth);
  const height=660,L=90,R=40,T=48,B=110,plotW=width-L-R,plotH=height-T-B;
  const values=points.map(score),lo=isSimilarity()?Math.max(-1,Math.floor((Math.min(...values)-.03)*20)/20):0,hi=isSimilarity()?Math.min(1,Math.ceil((Math.max(...values)+.03)*20)/20):1;
  const x=year=>L+(year-first+.5)/(last-first+1)*plotW,y=value=>T+plotH-(value-lo)/(hi-lo||1)*plotH;
  const scope=data.corpus.toUpperCase()+(meta.resource?' · '+meta.resource.label:' · All resources');
  const svg=svgNode('svg',{xmlns:NS,viewBox:`0 0 ${width} ${height}`,'font-family':'system-ui,Arial,sans-serif',role:'img','aria-label':`${data.word}: ${isSimilarity()?'Word2Vec similarity':'co-occurrence share'} by year in ${scope}`});
  svg.style.width=width+'px';svg.append(svgNode('title',{},`${data.word} · ${scope} · ${$('measure').selectedOptions[0].textContent}`));svg.append(svgNode('rect',{width,height,fill:'white'}));
  for(let i=0;i<=5;i++){const v=lo+(hi-lo)*i/5,gy=y(v);svg.append(svgNode('line',{x1:L,y1:gy,x2:width-R,y2:gy,stroke:'#e0e6eb'}),svgNode('text',{x:L-12,y:gy+4,'text-anchor':'end','font-size':12,fill:'#526170'},isSimilarity()?v.toFixed(2):Math.round(v*100)+'%'));}
  const step=Math.max(1,Math.ceil((last-first+1)/16));
  for(let year=first;year<=last;year+=step){const gx=x(year);svg.append(svgNode('line',{x1:gx,y1:T,x2:gx,y2:T+plotH,stroke:'#f0f3f5'}),svgNode('text',{x:gx,y:T+plotH+24,'text-anchor':'middle','font-size':11,fill:'#526170'},year));}
  svg.append(svgNode('text',{x:L+plotW/2,y:height-57,'text-anchor':'middle','font-size':14},'Year'));
  svg.append(svgNode('text',{transform:`translate(22 ${T+plotH/2}) rotate(-90)`,'text-anchor':'middle','font-size':13},isSimilarity()?'Cosine similarity to '+data.word:'Analysed usages containing the nearby word'));
  svg.append(svgNode('text',{x:L,y:height-22,'font-size':11,fill:'#526170'},`${scope} · Mats target usages · ${isSimilarity()?'Word2Vec; centred five-year training window':'±10-word co-occurrence; one count per usage'} · minimum n=${$('minimum').value}/year`));
  const boxes=[];
  const priority=[...points].sort((a,b)=>Number(b.word===highlight)-Number(a.word===highlight)||score(b)-score(a)||a.year-b.year||a.rank-b.rank);
  for(const point of priority){
   const px=x(point.year)+(point.rank%3-1)*2,py=y(score(point));
   const group=svgNode('g',{class:'point'+(highlight&&point.word!==highlight?' dimmed':''),tabindex:0,role:'button','aria-label':`${point.year}, ${point.word}, ${format(point)}, ${point.count} of ${point.n} nearby usages`});
   group.append(svgNode('title',{},`${point.word} · ${point.year}\n${$('measure').selectedOptions[0].textContent}: ${format(point)}\nNearby in ${point.count}/${point.n} analysed usages`),svgNode('circle',{cx:px,cy:py,r:4.5,fill:point.word===highlight?'#b45e20':'#2678a9',opacity:.78}));
   if($('labels').checked){
    const textW=point.word.length*7.1+5,textH=14;
    const choices=[[7,-8],[7,17],[-textW-7,-8],[-textW-7,17],[7,-24],[7,32]];
    for(const [dx,dy] of choices){
     const box={x:px+dx,y:py+dy-textH,w:textW,h:textH+3};
     if(box.x<L||box.x+box.w>width-R||box.y<T-18||box.y+box.h>T+plotH)continue;
     if(boxes.some(b=>box.x<b.x+b.w&&box.x+box.w>b.x&&box.y<b.y+b.h&&box.y+box.h>b.y))continue;
     boxes.push(box);group.append(svgNode('text',{x:px+dx,y:py+dy,'font-size':12,fill:'#263747','paint-order':'stroke',stroke:'white','stroke-width':3},point.word));break;
    }
   }
   const select=()=>{highlight=point.word;showSelection(point);render();};group.addEventListener('click',select);group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select();}});svg.append(group);
  }
  chart.append(svg);
 }
 function showSelection(point){
  $('selection').hidden=false;$('selectedTitle').textContent=point.word+' · '+point.year;
  $('selectedStats').textContent=`${$('measure').selectedOptions[0].textContent}: ${format(point)}. Nearby in ${point.count} of ${point.n} analysed target usages.`+(isSimilarity()&&point.model?` Model training: ${point.model.training_from}–${point.model.training_through}, ${point.model.training_contexts.toLocaleString()} target contexts.`:'');
  $('passages').replaceChildren();
  for(const example of point.examples||[]){const item=document.createElement('div');item.className='passage';const p=document.createElement('p');p.textContent=example.text;const small=document.createElement('small');small.textContent=example.date+' · '+example.id;item.append(p,small);if(example.url&&/^https?:\/\//.test(example.url)){const a=document.createElement('a');a.href=example.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=' · Open source';small.append(a);}$('passages').append(item);}
  if(!(point.examples||[]).length){const p=document.createElement('p');p.className='note';p.textContent='No immediate co-occurrence excerpt is available for this neighbour in this target year. Embedding neighbours are based on the wider training window.';$('passages').append(p);}
  $('examplesLink').href='examples.html?'+new URLSearchParams({word:data.word,resource:data.corpus});
 }
 function table(){
  $('scoreHeading').textContent=isSimilarity()?'Cosine similarity':'Co-occurrence share';$('values').replaceChildren();
  for(const point of [...points].sort((a,b)=>a.year-b.year||score(b)-score(a))){const tr=document.createElement('tr');for(const value of [point.year,point.word,format(point),point.count+' / '+point.n]){const td=document.createElement('td');td.textContent=value;tr.append(td);}$('values').append(tr);}
 }
 async function start(){
  try{catalog=await json('data/associations/manifest.json');options($('corpus'),catalog.corpora.map(c=>[c.corpus,c.corpus.toUpperCase()]),params.get('corpus')||'tkr');for(const id of ['from','to'])if(params.get(id)&&/^\d+$/.test(params.get(id)))$(id).value=params.get(id);for(const id of ['top','minimum'])if([...$(id).options].some(o=>o.value===params.get(id)))$(id).value=params.get(id);await loadCorpus();}
  catch(error){fail(error);}
 }
 $('corpus').addEventListener('change',()=>loadCorpus($('word').value));$('resource').addEventListener('change',()=>loadResource($('word').value));$('word').addEventListener('change',()=>loadWord());
 for(const id of ['measure','top','minimum','from','to','labels','expanded'])$(id).addEventListener('change',()=>{highlight=null;$('selection').hidden=true;render();});
 $('clear').addEventListener('click',()=>{highlight=null;$('selection').hidden=true;render();});
 $('reset').addEventListener('click',()=>{$('from').value='';$('to').value='';$('top').value='3';$('minimum').value='5';highlight=null;$('selection').hidden=true;render();});
 $('save').addEventListener('click',()=>{const svg=$('chart').querySelector('svg');if(!svg)return;const blob=new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${data.word}-${data.corpus}-${$('resource').value.replace(/[^\p{L}\p{N}-]/gu,'-')}-${$('measure').value}.svg`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 start();
})();
