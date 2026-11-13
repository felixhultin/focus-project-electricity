'use strict';
let catalog=[],activeData=null,request=0,initialState=true;
const dataCache=new Map(),params=new URLSearchParams(location.search);
const readJSON=path=>window.siteDataJSON(path);
let desiredWord=params.get('word');
let desiredResource=params.get('source');
const $=id=>document.getElementById(id), esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const option=(value,label)=>`<option value="${esc(value)}">${esc(label)}</option>`;
let scoped=[], filtered=[], topClusters=[], page=0;
const pageSize=50, color=c=>c==='other'?'#94a3b8':`hsl(${(Number(c)*137.508+210)%360} 58% 48%)`;
function current(){return activeData;}
function setupWords(){const old=desiredWord||$('lemma').value, words=(current().words||[...new Set(current().rows.map(r=>r.lemma))]).slice().sort((a,b)=>a.localeCompare(b,'sv'));$('lemma').innerHTML=words.map(w=>option(w,w)).join('');$('lemma').value=words.includes(old)?old:(words.includes('ström')?'ström':words[0]);desiredWord=null;$('cluster').value='all';render();}
function chosenCluster(c){return $('cluster').value==='other'?!topClusters.includes(c):$('cluster').value==='all'||String(c)===$('cluster').value;}
function setupResources(){
 const select=$('resource');if(!select)return;
 const old=desiredResource||select.value||'all';desiredResource=null;
 const resources=new Map(current().rows.filter(r=>r.lemma===$('lemma').value&&r.resource_id).map(r=>[r.resource_id,r.resource_label||r.resource_id]));
 select.innerHTML=option('all','All resources')+[...resources].sort((a,b)=>a[1].localeCompare(b[1],'sv')).map(([id,label])=>option(id,label)).join('');
 select.value=resources.has(old)?old:'all';$('resourceControl').hidden=resources.size===0;
}
function render(){
 if(!current())return;
 const d=current(), low=$('from').value===''?null:Number($('from').value), high=$('to').value===''?null:Number($('to').value);
 setupResources();const resource=$('resource')?.value||'all';
 scoped=d.rows.filter(r=>r.lemma===$('lemma').value&&(resource==='all'||r.resource_id===resource)&&(low===null||(r.year!==null&&r.year>=low))&&(high===null||(r.year!==null&&r.year<=high)));
 const counts=new Map();scoped.forEach(r=>counts.set(r.cluster,(counts.get(r.cluster)||0)+1));
 const ordered=[...counts.keys()].sort((a,b)=>counts.get(b)-counts.get(a)||a-b);topClusters=ordered.slice(0,10);
 const old=$('cluster').value;
 $('cluster').innerHTML=option('all','All clusters')+ordered.map(c=>option(c,`Cluster ${c} · n=${counts.get(c)}`)).join('')+(ordered.length>10?option('other','Other clusters (outside largest ten)'):'');
 $('cluster').value=[...$('cluster').options].some(o=>o.value===old)?old:'all';
 const unknown=scoped.filter(r=>r.year===null).length;
 $('stats').textContent=`${d.pipeline_label} · ${d.corpus.toUpperCase()} · ${scoped.length.toLocaleString()} sampled usages · ${counts.size} clusters${unknown?' · '+unknown+' without a year':''}`;
 const sampling=d.manifest.sampling;
 const note=sampling?.sampling_period==='year'
  ?`Sampled up to ${sampling.per_word_year_cap} eligible usages per word per year; years with fewer available usages retain all of them. Counts are not full-corpus frequencies.`
  :'Annual bars regroup the previous sample, capped at 30 usages per word per decade. These results have not yet been replaced by yearly-balanced samples.';
 const sharing=d.manifest.shared_clustering;
 $('samplingNote').textContent=note+(sharing
  ?' Shared clustering across '+sharing.corpora.map(c=>c.toUpperCase()).join(', ')+': the same cluster ID and color identify the same pooled cluster for this word and generator/encoder combination. IDs are not aligned across words or combinations. '+sharing.weighting
  :' Cluster IDs are local to each combination, word, and corpus; matching colors or IDs do not establish equivalent senses.');
 const coverage=d.manifest.definition_coverage;
 if(d.manifest.preview)$('samplingNote').textContent='Provisional '+d.corpus.toUpperCase()+'-only clustering preview. Definition generation is complete for this corpus. Cluster IDs may change when shared clustering across all corpora finishes. '+$('samplingNote').textContent;
 if(coverage)$('samplingNote').textContent+=` Definition generation for this corpus: ${coverage.usable_definition_count.toLocaleString()} of ${coverage.source_usage_count.toLocaleString()} sampled usages have usable definitions; ${coverage.empty_definition_count.toLocaleString()} remained empty after an individual retry and were excluded. Charts show successful definitions only, so yearly balance can be affected.`;
 if(d.method==='cooccurrence')$('samplingNote').textContent+=' TF–IDF weights describe nearby word forms within ±10 tokens. K-means groups contexts; candidate counts 2–12 are assessed by cosine silhouette, with one informative cluster when separation is weak. Cluster 0 contains contexts with no retained vocabulary. These groups may reflect topics, spelling, genre or OCR as well as meaning.';
 if(resource!=='all')$('samplingNote').textContent+=' Resource: '+$('resource').selectedOptions[0].textContent+'. The yearly cap applies across the whole corpus; this resource subset is not separately balanced. Cluster IDs and characteristic words come from the shared fit.';
 $('settings').textContent=JSON.stringify(d.manifest,null,2);
 drawClusterOverview(ordered,counts);drawChart(counts);page=0;showRows();updateURL();
}
function summarizeClusters(rows){
 const groups=new Map();
 rows.forEach(row=>{
  if(!groups.has(row.cluster))groups.set(row.cluster,{cluster:row.cluster,n:0,definitions:new Map(),years:[]});
  const group=groups.get(row.cluster);group.n++;
  const definition=(row.definition||'').replace(/\s+/g,' ').trim();
  if(definition)group.definitions.set(definition,(group.definitions.get(definition)||0)+1);
  if(Number.isInteger(row.year))group.years.push(row.year);
 });
 return new Map([...groups].map(([cluster,group])=>[cluster,{
  cluster,n:group.n,
  definitions:[...group.definitions].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])),
  firstYear:group.years.length?Math.min(...group.years):null,
  lastYear:group.years.length?Math.max(...group.years):null
 }]));
}
function drawClusterOverview(ordered,counts){
 const cooccurrence=current().method==='cooccurrence';
 const panel=$('clusterOverview');panel.hidden=!['definitions','cooccurrence'].includes(current().method);
 $('clusterCards').innerHTML='';
 if(panel.hidden)return;
 if($('overviewNote'))$('overviewNote').textContent=cooccurrence?'Characteristic words are the highest-weight TF–IDF features in each pooled cluster centroid. Example passages come from the current selection. These are context groups, not validated sense labels. Cluster 0, when present, has no retained context vocabulary.':'Each summary shows the most frequent generated definition in that cluster, with up to two alternatives. These are representative model outputs, not validated sense labels; mixed meanings or languages may occur. Counts and shares describe the selected sample. Choose a cluster to read its passages.';
 $('summaryScope').textContent=`${$('lemma').value} · ${current().corpus.toUpperCase()} · ${ordered.length} clusters in the selected years. Ordered by sampled usage count.`;
 const summaries=summarizeClusters(scoped);
 const card=cluster=>{
  const group=summaries.get(cluster),definitions=group.definitions;
  const years=group.firstYear===null?'Year unknown':group.firstYear===group.lastYear?String(group.firstYear):`${group.firstYear}–${group.lastYear}`;
  const keywords=current().manifest.characteristic_words?.[$('lemma').value]?.[String(cluster)]||[];
  const representative=cooccurrence?(keywords.length?'Characteristic words: '+esc(keywords.join(' · ')):'No retained context vocabulary.'):(definitions.length?esc(definitions[0][0]):'No definition available.');
  const alternatives=cooccurrence?[]:definitions.slice(1,3);
  const example=cooccurrence?scoped.find(r=>r.cluster===cluster):null;
  return `<article class="cluster-card"><button class="cluster-heading" data-summary-cluster="${cluster}"><span class="dot" style="background:${color(cluster)}"></span>Cluster ${cluster} · Inspect passages</button><p class="cluster-size">${counts.get(cluster).toLocaleString()} usages · ${(group.n/scoped.length*100).toFixed(1)}% of selected sample · ${years}</p><p class="representative">${representative}</p>${example?'<p class="note">Example: '+esc(example.text)+'</p>':''}${alternatives.length?`<details><summary>Other frequent definitions</summary><ul>${alternatives.map(([text,n])=>`<li>${esc(text)} <small>(n=${n})</small></li>`).join('')}</ul></details>`:''}</article>`;
 };
 $('clusterCards').innerHTML=ordered.length?`<div class="cluster-grid">${ordered.slice(0,10).map(card).join('')}</div>`+(ordered.length>10?`<details class="remaining-clusters"><summary>Show ${ordered.length-10} smaller clusters</summary><div class="cluster-grid">${ordered.slice(10).map(card).join('')}</div></details>`:''):'<p>No clusters match these years.</p>';
 panel.querySelectorAll('[data-summary-cluster]').forEach(button=>button.onclick=()=>{
  $('cluster').value=button.dataset.summaryCluster;page=0;showRows();drawChart(counts);updateURL();
  $('passages').scrollIntoView({block:'start'});$('cluster').focus({preventScroll:true});
 });
}
function buildYearBins(rows, groups){
 const byYear=new Map();
 rows.forEach(row=>{const year=Number.isInteger(row.year)?row.year:'Unknown';if(!byYear.has(year))byYear.set(year,[]);byYear.get(year).push(row);});
 const known=[...byYear.keys()].filter(Number.isInteger).sort((a,b)=>a-b);
 const periods=known.length?Array.from({length:known[known.length-1]-known[0]+1},(_,i)=>known[0]+i):[];
 if(byYear.has('Unknown'))periods.push('Unknown');
 return periods.map(year=>{const usages=byYear.get(year)||[],values=new Map(groups.map(g=>[g,0]));usages.forEach(row=>{const group=groups.includes(row.cluster)?row.cluster:'other';values.set(group,(values.get(group)||0)+1);});return{year,n:usages.length,values};});
}
function drawChart(counts){
 const groups=[...topClusters];if(counts.size>10)groups.push('other');
 const bins=buildYearBins(scoped,groups);
 const percent=$('metric').value==='share',max=percent?100:Math.max(1,...bins.map(b=>b.n));
 const width=Math.max(720,bins.length*46+80),height=320,left=52,base=260,plot=225,step=(width-left-20)/Math.max(1,bins.length),bar=Math.min(34,step*.75);
 let svg=`<svg viewBox="0 0 ${width} ${height}" style="width:${width}px;height:${height}px;max-width:none" role="group" aria-label="Cluster distribution by year">`;
 for(let i=0;i<=4;i++){const value=max*i/4,y=base-plot*i/4;svg+=`<line x1="${left}" x2="${width-15}" y1="${y}" y2="${y}" stroke="#e2e8f0"/><text x="${left-8}" y="${y+4}" text-anchor="end" font-size="12" fill="#64748b">${Math.round(value)}${percent?'%':''}</text>`;}
 bins.forEach((b,i)=>{
  let y=base;const x=left+i*step+(step-bar)/2;
  svg+=`<g class="year-bin" data-year="${esc(b.year)}" data-count="${b.n}">`;
  if(!b.n)svg+=`<title>${esc(b.year)}: no sampled usages</title><text x="${x+bar/2}" y="${base-8}" text-anchor="middle" fill="#94a3b8">–</text>`;
  groups.forEach(g=>{const n=b.values.get(g)||0;if(!n)return;const value=percent?n/b.n*100:n,h=value/max*plot;y-=h;const selected=$('cluster').value==='all'||String(g)===$('cluster').value;svg+=`<rect x="${x}" y="${y}" width="${bar}" height="${h}" fill="${color(g)}" opacity="${selected?1:.3}" data-cluster="${g}" tabindex="0" role="button" aria-label="${esc(b.year)} ${g==='other'?'other clusters':'cluster '+g}: ${n} usages"><title>${esc(b.year)} · ${g==='other'?'Other clusters':'Cluster '+g}: ${n} usages (${(n/b.n*100).toFixed(1)}%)</title></rect>`;});
  svg+=`<text x="${x+bar/2}" y="283" text-anchor="middle" font-size="12">${esc(b.year)}</text><text x="${x+bar/2}" y="302" text-anchor="middle" font-size="11" fill="#64748b">n=${b.n}</text></g>`;
 });
 $('chart').innerHTML=bins.length?svg+'</svg>':'<p>No usages match these years.</p>';
 $('legend').innerHTML=groups.map(g=>`<button data-cluster="${g}" class="${String(g)===$('cluster').value?'selected':''}"><span class="dot" style="background:${color(g)}"></span>${g==='other'?'Other clusters':'Cluster '+g}</button>`).join('')+'<button data-cluster="all">Show all</button>';
 document.querySelectorAll('[data-cluster]').forEach(el=>{const choose=()=>{$('cluster').value=el.dataset.cluster;page=0;showRows();drawChart(counts);};el.onclick=choose;if(el.tagName.toLowerCase()==='rect')el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}};});
}
function showRows(){
 if(!current())return;
 const query=$('query').value.toLocaleLowerCase();
 filtered=scoped.filter(r=>chosenCluster(r.cluster)&&(!query||[r.definition,r.text,r.id,r.source].some(t=>t.toLocaleLowerCase().includes(query)))).sort((a,b)=>(a.year??9999)-(b.year??9999)||a.cluster-b.cluster);
 const pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.max(0,Math.min(page,pages-1));
 $('count').textContent=`${filtered.length.toLocaleString()} matching usages`;
 $('page').textContent=`Page ${page+1} of ${pages}`;$('prev').disabled=page===0;$('next').disabled=page>=pages-1;
 const definitions=new Map();filtered.forEach(r=>definitions.set(r.definition,(definitions.get(r.definition)||0)+1));
 const frequent=[...definitions].sort((a,b)=>b[1]-a[1]).slice(0,3);
 $('clusterSummary').textContent=$('cluster').value==='all'?'Choose a cluster to inspect recurring definitions.':`Most frequent definitions in this selection: ${frequent.map(([d,n])=>`${d} (n=${n})`).join(' · ')}`;
 if(current().method==='usages')$('clusterSummary').textContent='XL-LEXEME clusters source passages directly and does not generate definitions. Inspect the highlighted usages to interpret each cluster.';
 if(current().method==='cooccurrence')$('clusterSummary').textContent='Co-occurrence clusters group usages by TF–IDF-weighted nearby words. Characteristic words are pooled cluster features; read passages to assess the possible meanings. No definitions are generated.';
 $('rows').innerHTML=filtered.slice(page*pageSize,(page+1)*pageSize).map(r=>{
 const text=esc(r.text.slice(0,r.start))+'<mark>'+esc(r.text.slice(r.start,r.end))+'</mark>'+esc(r.text.slice(r.end));
 const link=typeof r.url==='string'&&/^https?:\/\//i.test(r.url)?`<br><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Open source</a>`:'';
 return `<tr><td>${esc(r.year??'Unknown')}<br><span class="dot" style="background:${color(r.cluster)}"></span>Cluster ${r.cluster}</td><td class="definition">${esc(r.definition)}</td><td class="context">${text}</td><td><small>${esc(r.id)}<br>${esc(r.source)}</small>${link}</td></tr>`;}).join('');
}

function busy(value){document.querySelectorAll('select,input,button').forEach(el=>el.disabled=value);}
function updateURL(){
 if(!current())return;
 const state=new URLSearchParams();state.set('model',current().model_alias);state.set('corpus',current().corpus);state.set('word',$('lemma').value);
 ['from','to','metric','cluster'].forEach(id=>{const v=$(id).value;if(v&&v!=='all'&&!(id==='metric'&&v==='share'))state.set(id,v);});
 if($('query').value)state.set('q',$('query').value);
 if($('resource')?.value&&$('resource').value!=='all')state.set('source',$('resource').value);
 history.replaceState(null,'','?'+state.toString());
 $('examplesLink').href='examples.html?word='+encodeURIComponent($('lemma').value)+'&resource='+encodeURIComponent(current().corpus);
}
function setupCorpora(desired){
 const available=catalog.filter(d=>d.pipeline_id===$('model').value);
 const order=['tkr','kubhist','kubhist2','lb','kvinnsam'];available.sort((a,b)=>order.indexOf(a.corpus)-order.indexOf(b.corpus));
 $('corpus').innerHTML=available.map(d=>option(d.corpus,d.corpus.toUpperCase())).join('');
 $('corpus').value=available.some(d=>d.corpus===desired)?desired:available[0].corpus;
 $('availability').textContent=available[0].pipeline_label+' results are available for '+available.map(d=>d.corpus.toUpperCase()).join(', ')+'. Check the sampling notice for whether cluster IDs are shared across corpora.';
 $('overview').innerHTML=available.map(d=>`<div class="card"><strong>${esc(d.corpus.toUpperCase())}</strong><br>${d.usage_count.toLocaleString()} usages · ${d.word_count} words</div>`).join('');
}
async function loadSelection(){
 const version=++request;
 const selected=catalog.find(d=>d.pipeline_id===$('model').value&&d.corpus===$('corpus').value);
 busy(true);activeData=null;scoped=[];filtered=[];$('clusterOverview').hidden=true;$('clusterCards').innerHTML='';
 $('loading').setAttribute('role','status');$('loading').textContent='Loading '+selected.pipeline_label+' / '+selected.corpus.toUpperCase()+'…';
 $('chart').innerHTML='';$('rows').innerHTML='';$('stats').textContent='';$('legend').innerHTML='';$('count').textContent='';$('clusterSummary').textContent='';
 try{
  let data=dataCache.get(selected.id);
  if(!data){data=await readJSON(selected.data);if(data.id!==selected.id||!Array.isArray(data.rows)||(!data.word_files&&data.rows.length!==selected.usage_count))throw new Error('Dataset does not match its manifest');dataCache.set(selected.id,data);}
  if(data.word_files){
   const word=[desiredWord,$('lemma').value,data.words[0]].find(w=>data.words.includes(w));
   const key=selected.id+'::'+word;let rows=dataCache.get(key);
   if(!rows){rows=await readJSON(data.word_files[word]);if(!Array.isArray(rows)||rows.length!==data.word_counts[word]||rows.some(r=>r.lemma!==word))throw new Error('Word data does not match its manifest');dataCache.set(key,rows);}
   data={...data,rows};desiredWord=word;
  }
  if(version!==request)return;
  activeData=data;document.body.classList.toggle('no-definitions',data.method!=='definitions');
  setupWords();
  if(initialState){const cluster=params.get('cluster');if(cluster&&[...$('cluster').options].some(o=>o.value===cluster)){$('cluster').value=cluster;render();}initialState=false;}
  $('loading').textContent='';busy(false);showRows();
 }catch(error){if(version!==request)return;$('loading').setAttribute('role','alert');$('loading').textContent='Could not load this result set: '+error.message+'. Serve the docs folder over HTTP, or try reloading the page.';busy(false);}
}
async function start(){
 busy(true);
 try{
  const manifest=await readJSON('data/clusters/manifest.json');catalog=manifest.datasets;
  if(!Array.isArray(catalog))throw new Error('Invalid result catalog');
  if(!catalog.length&&(manifest.pending||[]).length){
   $('model').innerHTML=manifest.pending.map(d=>option(d.pipeline_id,d.pipeline_label+' — results pending')).join('');
   $('loading').textContent='Analysis is running in the background. Results will appear here after generation and shared clustering finish; reload to check availability.';
   $('experimentStatus').textContent=manifest.pending.map(d=>d.pipeline_label+': results pending.').join(' ');return;
  }
  if(!catalog.length)throw new Error('No cluster result sets are available');
  const models=[...new Map(catalog.map(d=>[d.pipeline_id,d])).values()];
  $('model').innerHTML=models.map(d=>option(d.pipeline_id,d.pipeline_label)).join('')+(manifest.pending||[]).map(d=>`<option value="${esc(d.pipeline_id)}" disabled>${esc(d.pipeline_label)} — results pending</option>`).join('');
  $('experimentStatus').textContent=(manifest.pending||[]).map(d=>d.pipeline_label+': results pending.').join(' ');
  const requested=catalog.find(d=>d.pipeline_id===params.get('model')||d.model===params.get('model')||d.model_alias===params.get('model'));
  $('model').value=requested?requested.pipeline_id:models[0].pipeline_id;
  setupCorpora(params.get('corpus')||params.get('resource')||'tkr');
  ['from','to'].forEach(id=>{const value=params.get(id);if(value&&/^-?\d+$/.test(value))$(id).value=value;});
  $('metric').value=params.get('metric')==='count'?'count':'share';$('query').value=params.get('q')||'';
  await loadSelection();
 }catch(error){$('loading').setAttribute('role','alert');$('loading').textContent='Could not load available models: '+error.message+'. Serve this site over HTTP and try again.';}
}
$('model').onchange=()=>{setupCorpora($('corpus').value);loadSelection();};
$('corpus').onchange=loadSelection;
if($('resource'))$('resource').onchange=()=>{$('cluster').value='all';render();};
$('lemma').onchange=()=>{if(current()?.word_files){desiredWord=$('lemma').value;loadSelection();}else{$('cluster').value='all';render();}};['from','to','metric'].forEach(id=>$(id).onchange=render);
$('cluster').onchange=()=>{page=0;render();};$('query').oninput=()=>{page=0;showRows();updateURL();};
$('prev').onclick=()=>{page--;showRows();};$('next').onclick=()=>{page++;showRows();};
$('reset').onclick=()=>{$('from').value='';$('to').value='';$('query').value='';$('cluster').value='all';if($('resource'))$('resource').value='all';render();};

start();
