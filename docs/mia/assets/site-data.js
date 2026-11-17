'use strict';
(()=>{
 const bundles=new Map();
 const mapping=fetch('data/asset-map.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('Data map: HTTP '+r.status);return r.json();});
 async function read(path,gzip=false){
  const response=await fetch(path,{cache:'no-cache'});
  if(!response.ok)throw Error('HTTP '+response.status+': '+path);
  if(!gzip)return response.json();
  const bytes=await response.arrayBuffer(),header=new Uint8Array(bytes,0,Math.min(2,bytes.byteLength));
  // Some hosts decompress a .gz response automatically through Content-Encoding.
  if(header[0]!==31||header[1]!==139)return JSON.parse(new TextDecoder().decode(bytes));
  if(typeof DecompressionStream==='undefined')throw Error('This browser needs gzip decompression support; please use a current browser.');
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).json();
 }
 window.siteDataJSON=async path=>{
  const map=await mapping;
  if(map.files?.[path])return read(map.files[path],true);
  const bundle=(map.bundles||[]).find(b=>b.paths ? b.paths.includes(path) : path.startsWith(b.prefix));
  if(bundle){
   if(!bundles.has(bundle.url))bundles.set(bundle.url,read(bundle.url,true).catch(error=>{bundles.delete(bundle.url);throw error;}));
   const values=await bundles.get(bundle.url);
   if(!Object.prototype.hasOwnProperty.call(values,path))throw Error('Missing bundled data: '+path);
   return values[path];
  }
  return read(path);
 };
})();
