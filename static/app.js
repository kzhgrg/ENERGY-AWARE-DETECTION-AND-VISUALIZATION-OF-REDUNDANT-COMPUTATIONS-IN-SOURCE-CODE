let lastReport=null;
const $=id=>document.getElementById(id);
const sample=$('code').value;
$('sample').onclick=()=>{$('code').value=sample};
$('file').onchange=async e=>{const f=e.target.files[0];if(f){$('code').value=await f.text();$('status').textContent='Loaded '+f.name;}};
$('save').onclick=()=>{if(!lastReport){alert('Analyze code first.');return;}const blob=new Blob([JSON.stringify(lastReport,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='analysis_report.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
// Layered SVG renderer: CFG flows top-to-bottom; expression DAG flows operands-to-results.
function drawGraph(graph, target='graph') {
  const svg=$(target), ns='http://www.w3.org/2000/svg';
  svg.replaceChildren();
  const isCFG=target==='cfg';
  const nodes=(graph?.nodes||[]).slice(0,100);
  const ids=new Set(nodes.map(n=>n.id));
  const edges=(graph?.edges||[]).filter(e=>ids.has(e.from)&&ids.has(e.to));
  const byId=new Map(nodes.map(n=>[n.id,n]));
  const el=(tag,attrs={},parent=svg)=>{const x=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>x.setAttribute(k,v));parent.appendChild(x);return x;};
  if(!nodes.length){svg.setAttribute('viewBox','0 0 800 180');el('text',{x:400,y:90,'text-anchor':'middle',fill:'#8189a3'}).textContent='Analyze a program to see its graph.';return;}
  const out=new Map(nodes.map(n=>[n.id,[]]));
  const incoming=new Map(nodes.map(n=>[n.id,[]]));
  edges.forEach(e=>{out.get(e.from).push(e.to);incoming.get(e.to).push(e.from);});
  // For CFG, start at ENTRY. For DAG, start at operands (no incoming edges).
  const starts=isCFG?nodes.filter(n=>n.kind==='entry').map(n=>n.id):nodes.filter(n=>!incoming.get(n.id).length).map(n=>n.id);
  const order=[],state=new Map(),backEdges=new Set();
  function visit(id){if(state.get(id)===2)return;if(state.get(id)===1)return;state.set(id,1);order.push(id);
    for(const to of out.get(id)){if(state.get(to)===1)backEdges.add(id+'|'+to);else visit(to);}
    state.set(id,2);
  }
  starts.forEach(visit);nodes.forEach(n=>visit(n.id));
  // Remove DFS back-edges for ranking so loop cycles don't destroy layout.
  const rank=new Map(nodes.map(n=>[n.id,0]));
  for(let pass=0;pass<nodes.length;pass++){
    let changed=false;
    for(const e of edges){if(backEdges.has(e.from+'|'+e.to))continue;
      const next=rank.get(e.from)+1;
      if(next>rank.get(e.to)){rank.set(e.to,next);changed=true;}
    }
    if(!changed)break;
  }
  // For CFGs with a linear chain, each statement gets its own readable row.
  const layers=new Map();nodes.forEach(n=>{const r=Math.min(rank.get(n.id),nodes.length);if(!layers.has(r))layers.set(r,[]);layers.get(r).push(n);});
  const ranks=[...layers.keys()].sort((a,b)=>a-b);
  const maxCount=Math.max(...[...layers.values()].map(x=>x.length));
  const nodeW=isCFG?240:138, nodeH=isCFG?49:45, gapX=isCFG?52:45, gapY=isCFG?42:56;
  const width=Math.max(720,maxCount*(nodeW+gapX)+110);
  const height=Math.max(250,(Math.max(...ranks)+1)*(nodeH+gapY)+75);
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  svg.setAttribute('width',width);svg.setAttribute('height',height);
  const defs=el('defs');
  for(const [id,color] of [['arrow','#a5a8d8'],['arrowBack','#dc9d6c']]){
    const marker=el('marker',{id:target+'-'+id,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'},defs);
    el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:color},marker);
  }
  const positions=new Map();
  for(const r of ranks){const layer=layers.get(r);
    // Keep order deterministic and readable; children inherit rough order from parents.
    layer.sort((a,b)=>order.indexOf(a.id)-order.indexOf(b.id));
    const total=layer.length*nodeW+(layer.length-1)*gapX;
    layer.forEach((n,i)=>positions.set(n.id,{x:(width-total)/2+i*(nodeW+gapX)+nodeW/2,y:46+r*(nodeH+gapY)}));
  }
  // Draw edges behind boxes; return edges curve along the right side.
  for(const [i,e] of edges.entries()){
    const a=positions.get(e.from),b=positions.get(e.to),back=backEdges.has(e.from+'|'+e.to)||b.y<=a.y;
    let d;
    if(back){const lane=width-24-(i%5)*13;d=`M ${a.x+nodeW/2-6} ${a.y} C ${lane} ${a.y}, ${lane} ${b.y}, ${b.x+nodeW/2-6} ${b.y}`;}
    else {const y1=a.y+nodeH/2,y2=b.y-nodeH/2,mid=(y1+y2)/2;d=`M ${a.x} ${y1} C ${a.x} ${mid}, ${b.x} ${mid}, ${b.x} ${y2}`;}
    el('path',{d,fill:'none',stroke:back?'#dc9d6c':'#a5a8d8','stroke-width':1.9,'stroke-dasharray':back?'6 4':'none','marker-end':`url(#${target}-${back?'arrowBack':'arrow'})`});
    if(e.label){const x=back?Math.min(width-50,Math.max(a.x,b.x)+nodeW/2+12):(a.x+b.x)/2+10;const y=(a.y+b.y)/2;
      const t=el('text',{x,y,'font-size':11,fill:back?'#b7774a':'#7774b5','font-weight':650});t.textContent=e.label;
    }
  }
  for(const n of nodes){const p=positions.get(n.id),decision=n.kind==='decision',op=n.group==='operation';
    const fill=decision?'#fff2e7':op?'#efedff':n.kind==='entry'?'#e7f7f0':n.kind==='exit'?'#e9ecfa':'#ffffff';
    const stroke=decision?'#e5ad78':op?'#8d87e5':n.kind==='entry'?'#75c4a4':'#b5b9e6';
    el('rect',{x:p.x-nodeW/2,y:p.y-nodeH/2,width:nodeW,height:nodeH,rx:12,fill,stroke,'stroke-width':1.6});
    const label=String(n.label||'');const limit=isCFG?31:17;
    const shown=label.length>limit?label.slice(0,limit-1)+'…':label;
    const textNode=el('text',{x:p.x,y:p.y+4,'text-anchor':'middle',fill:'#42446f','font-size':isCFG?13:14,'font-family':'ui-monospace, SFMono-Regular, Menlo, monospace','font-weight':decision||op?700:500});
    textNode.textContent=shown;
    el('title',{},textNode).textContent=label;
  }
  if(nodes.length<(graph?.nodes||[]).length){el('text',{x:width/2,y:height-12,'text-anchor':'middle',fill:'#8d93a7','font-size':12}).textContent='Showing first 100 nodes';}
}

$('run').onclick=async()=>{$('status').textContent='Analyzing…';try{const response=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('code').value})});const r=await response.json();if(r.error){$('status').textContent='Parse error';$('findings').textContent=r.error;return;}lastReport=r;$('optimized').textContent=r.optimized;$('before').textContent=r.before;$('after').textContent=r.after;$('reduction').textContent=r.reduction+'%';$('count').textContent=r.findings.filter(x=>x.applied).length;$('beforeLabel').textContent=r.before;$('afterLabel').textContent=r.after;$('barBefore').style.width=r.before?'100%':'0%';$('barAfter').style.width=r.before?(100*r.after/r.before)+'%':'0%';$('note').textContent=r.note;$('findings').replaceChildren();if(!r.findings.length)$('findings').textContent='No supported optimizations found.';for(const f of r.findings){const div=document.createElement('div');div.className='finding';const tag=document.createElement('span');tag.className='tag';tag.textContent=f.kind;const detail=document.createElement('small');detail.textContent=`Line ${f.line}: ${f.detail}`;div.append(tag,detail);$('findings').appendChild(div);}$('notices').textContent=r.notices.length?r.notices.join('\n'):'Analysis completed on supported blocks.';$('ops').textContent=JSON.stringify({before:r.operations_before,after:r.operations_after},null,2);drawGraph(r.graph);drawGraph(r.cfg,'cfg');$('status').textContent='Analysis complete';}catch(e){$('status').textContent='Error';$('findings').textContent=e.message;}};

$('measureEnergy').onclick=async()=>{
  const btn=$('measureEnergy'),target=$('energyResult');
  btn.disabled=true;target.textContent='Measuring trusted bundled benchmarks; this may take up to a minute…';
  try{
    const response=await fetch('/measure-energy',{method:'POST'});
    const result=await response.json();
    if(result.error){target.textContent='Measurement unavailable: '+result.error;return;}
    target.replaceChildren();
    const p=document.createElement('p');
    p.textContent=`Baseline: ${result.baseline.joules.toFixed(4)} J (${result.baseline.seconds.toFixed(2)} s) | Optimized: ${result.optimized.joules.toFixed(4)} J (${result.optimized.seconds.toFixed(2)} s) | Change: ${result.relative_change_percent}%`;
    const note=document.createElement('p');note.textContent=result.warning;
    target.append(p,note);
  }catch(err){target.textContent='Measurement error: '+err.message;}
  finally{btn.disabled=false;}
};

// Compact tabbed visualization workspace.
document.querySelectorAll('.tab').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('.tab').forEach(tab=>{const selected=tab===button;tab.classList.toggle('active',selected);tab.setAttribute('aria-selected',String(selected));});
  document.querySelectorAll('.tab-content').forEach(panel=>{const selected=panel.id===button.dataset.tab;panel.hidden=!selected;panel.classList.toggle('active',selected);});
}));
// Keep navigation state in sync with the selected section.
document.querySelectorAll('.nav-link').forEach(link=>link.addEventListener('click',()=>{document.querySelectorAll('.nav-link').forEach(item=>item.classList.toggle('active',item===link));}));
