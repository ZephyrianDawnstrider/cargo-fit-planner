(() => {
'use strict';
let packed=JSON.parse(document.getElementById('packing-result').textContent);
const scene=document.getElementById('scene'), ns='http://www.w3.org/2000/svg';
const controls=document.getElementById('manual-controls'), status=document.getElementById('layout-status');
const palette=['#36b8b0','#f3bc5a','#94adf3','#d88dba','#80bd8d','#e8906e'];
let selected=null, azimuth=45, elevation=25, zoom=1, full=true, busy=false, drag=null, transform=null, previous=null;
const byId=id=>document.getElementById(id);
const layout=data=>data.placed.map(p=>({item_id:p.item_id,x:p.x,y:p.y,z:p.z,rotation_deg:p.rotation_deg||0}));
const el=(tag,attrs={},text=null)=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!==null)n.textContent=text;return n;};
function selection(){
 const p=packed.placed.find(p=>p.item_id===selected);controls.disabled=busy||!p;
 if(p){byId('manual-x').value=p.x;byId('manual-y').value=p.y;byId('manual-z').value=p.z;byId('manual-rotation').value=p.rotation_deg||0;}
 byId('selection-feedback').textContent=p?`${p.item_id} · ${p.name} · ${p.dx} × ${p.dy} × ${p.dz} mm · ${p.weight_kg} kg`:'No box selected. Click a box or its coordinate-table label.';
 document.querySelectorAll('.cargo-row[data-item-id]').forEach(n=>n.classList.toggle('is-highlighted',n.dataset.itemId===selected));
 document.querySelectorAll('.item-link[data-item-id]').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.itemId===selected)));
}
window.setCargoSelection=id=>{selected=id;selection();draw();};
function draw(){
 const c=packed.container.inside_mm;
 const bounds=full||!packed.placed.length?[c.length,c.width,c.height]:[Math.max(1,...packed.placed.map(p=>p.x+p.dx)),Math.max(1,...packed.placed.map(p=>p.y+p.dy)),Math.max(1,...packed.placed.map(p=>p.z+p.dz))];
 const a=azimuth*Math.PI/180,e=elevation*Math.PI/180,ca=Math.cos(a),sa=Math.sin(a),ce=Math.cos(e),se=Math.sin(e);
 const raw=([x,y,z])=>[ca*x-sa*y,-se*(sa*x+ca*y)+ce*z,ce*(sa*x+ca*y)+se*z];
 const corners=(x,y,z,dx,dy,dz)=>[[x,y,z],[x+dx,y,z],[x+dx,y+dy,z],[x,y+dy,z],[x,y,z+dz],[x+dx,y,z+dz],[x+dx,y+dy,z+dz],[x,y+dy,z+dz]];
 const fit=corners(0,0,0,...bounds).map(raw),xs=fit.map(p=>p[0]),ys=fit.map(p=>p[1]),cx=(Math.min(...xs)+Math.max(...xs))/2,cy=(Math.min(...ys)+Math.max(...ys))/2;
 const scale=zoom*Math.min(680/(Math.max(...xs)-Math.min(...xs)||1),340/(Math.max(...ys)-Math.min(...ys)||1));
 const project=p=>{const q=raw(p);return[380+(q[0]-cx)*scale,220-(q[1]-cy)*scale,q[2]];};
 transform={scale,ca,sa,ce,se};scene.replaceChildren(el('title',{id:'scene-title'},'Interactive 3D cargo layout'),el('desc',{id:'scene-description'},'Drag to orbit or choose planar box movement. Translucent walls show the equipment bounds. Manual moves require server validation.'));
 const faces=[],faceIndices=[[0,1,2,3],[4,7,6,5],[0,4,5,1],[3,2,6,7],[0,3,7,4],[1,5,6,2]];
 function cube(points,id,color,shell=false){faceIndices.forEach((indices,index)=>{const pts=indices.map(i=>project(points[i]));faces.push({points:pts,id,color,shell,index,depth:pts.reduce((sum,p)=>sum+p[2],0)/4});});}
 cube(corners(0,0,0,c.length,c.width,c.height),null,'#7db8ce',true);
 packed.placed.forEach((p,i)=>cube(corners(p.x,p.y,p.z,p.dx,p.dy,p.dz),p.item_id,palette[i%palette.length]));
 faces.sort((a,b)=>a.depth-b.depth).forEach(f=>{
  const n=el('polygon',{points:f.points.map(p=>p.slice(0,2).join(',')).join(' '),fill:f.color,'fill-opacity':f.shell?(f.index===0?.13:.045):.88,stroke:f.shell?'#5c91a8':f.id===selected?'#0e4e71':'#426373','stroke-opacity':f.shell?.6:.85,'stroke-width':f.id===selected?2.5:f.shell?1.1:.8});
  if(f.id){n.dataset.itemId=f.id;n.classList.add('box-face');n.append(el('title',{},f.id));}else n.style.pointerEvents='none';scene.append(n);
 });
 // Distinct door plane at x=length; it is an illustration, not loading-path clearance.
 const door=corners(c.length,0,0,0,c.width,c.height),doorLine=el('polyline',{points:[door[0],door[3],door[7],door[4],door[0]].map(p=>project(p).slice(0,2).join(',')).join(' '),fill:'none',stroke:'#e39c39','stroke-width':2,'stroke-dasharray':'6 4'});doorLine.style.pointerEvents='none';scene.append(doorLine);
 const d=project([c.length,c.width/2,c.height]);scene.append(el('text',{x:d[0],y:d[1]-8,'text-anchor':'middle',fill:'#9e6618','font-size':12,'pointer-events':'none'},'DOOR END'));
 packed.placed.forEach(p=>{if(p.item_id!==selected&&packed.placed.length>12)return;const q=project([p.x+p.dx/2,p.y+p.dy/2,p.z+p.dz]);scene.append(el('text',{x:q[0],y:q[1]-3,'text-anchor':'middle','font-size':p.item_id===selected?13:10,fill:'#173648','pointer-events':'none'},p.item_id));});
 const origin=project([0,0,0]);[[Math.min(c.length,1000),0,0,'X'],[0,Math.min(c.width,1000),0,'Y'],[0,0,Math.min(c.height,1000),'Z']].forEach(([x,y,z,label])=>{const q=project([x,y,z]);scene.append(el('line',{x1:origin[0],y1:origin[1],x2:q[0],y2:q[1],stroke:'#203f53','stroke-width':1.5,'pointer-events':'none'}),el('text',{x:q[0]+5,y:q[1],fill:'#203f53','font-size':12,'pointer-events':'none'},label));});
 byId('rendered-count').textContent=`${packed.placed.length} boxes · orbit ${Math.round(azimuth%360)}° / ${Math.round(elevation)}°`;
}
function setBusy(value){busy=value;controls.disabled=value||!selected;document.querySelectorAll('.export-form button').forEach(n=>n.disabled=value);byId('manual-undo').disabled=value||!previous;}
function reflect(){
 document.querySelectorAll('input[name="manual_layout_json"]').forEach(n=>n.value=JSON.stringify(layout(packed)));
 for(const row of document.querySelectorAll('.cargo-row[data-item-id]')){const p=packed.placed.find(p=>p.item_id===row.dataset.itemId);if(p){row.cells[2].textContent=`${p.x}, ${p.y}, ${p.z}`;row.cells[3].textContent=`${p.dx}, ${p.dy}, ${p.dz}`;}}
 const center=packed.mass_distribution?.center_mm;byId('mass-center-summary').textContent=center?`Estimated cargo centre from packing origin: X ${center.x.toFixed(1)} mm · Y ${center.y.toFixed(1)} mm · Z ${center.z.toFixed(1)} mm.`:'Centre is unknown: no positive placed cargo mass.';
 selection();draw();
}
async function validate(candidate){
 if(busy)return;const before=structuredClone(packed);setBusy(true);status.textContent='Validating bounds, collision, support, orientation and payload…';
 const data=new FormData(byId('export-json-form'));data.set('manual_layout_json',JSON.stringify(candidate));const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{const response=await fetch('{% url "validate-layout" %}',{method:'POST',body:data,credentials:'same-origin',signal:controller.signal});const text=await response.text();let value;try{value=JSON.parse(text);}catch(_){throw new Error(response.status===429?'Request limit reached. Wait and retry.':'Validation could not complete. The previous layout is retained.');}if(!response.ok)throw new Error(value.error||'Layout rejected.');previous=before;packed=value;status.textContent='Manual layout accepted by geometric checks. Exports now use this snapshot. Not a transport-safety approval.';reflect();}
 catch(error){packed=before;selection();draw();status.textContent=error.name==='AbortError'?'Validation timed out. Previous layout retained.':`Move rejected: ${error.message}`;}
 finally{clearTimeout(timer);setBusy(false);}
}
byId('manual-apply').addEventListener('click',()=>{if(!selected||busy)return;const inputs=['x','y','z'].map(k=>byId('manual-'+k).value);if(inputs.some(v=>!v.trim())){status.textContent='Enter all three coordinates.';return;}const values=inputs.map(Number);if(values.some(v=>!Number.isSafeInteger(v)||v<0)){status.textContent='Use non-negative whole millimetres.';return;}const edits=layout(packed),p=edits.find(p=>p.item_id===selected);[p.x,p.y,p.z]=values;p.rotation_deg=Number(byId('manual-rotation').value);validate(edits);});
const undo=document.createElement('button');undo.id='manual-undo';undo.type='button';undo.className='secondary';undo.textContent='Undo last accepted edit';undo.disabled=true;controls.after(undo);undo.addEventListener('click',()=>{if(previous)validate(layout(previous));});
function point(event){const matrix=scene.getScreenCTM();if(!matrix)return[0,0];const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());return[p.x,p.y];}
scene.addEventListener('pointerdown',event=>{if(busy||event.button!==0)return;const id=event.target.closest('[data-item-id]')?.dataset.itemId;if(id){selected=id;selection();}const [x,y]=point(event);drag={x,y,azimuth,elevation,mode:byId('scene-action').value,id,baseline:structuredClone(packed),transform:{...transform},moved:false};scene.setPointerCapture(event.pointerId);});
scene.addEventListener('pointermove',event=>{if(!drag)return;const [x,y]=point(event),dx=x-drag.x,dy=y-drag.y;if(Math.abs(dx)+Math.abs(dy)<3)return;drag.moved=true;if(drag.mode==='orbit'){azimuth=drag.azimuth+dx*.35;elevation=Math.max(10,Math.min(85,drag.elevation-dy*.25));byId('scene-elevation').value=elevation;draw();}else if(drag.id&&transform){const p=packed.placed.find(p=>p.item_id===drag.id),base=drag.baseline.placed.find(p=>p.item_id===drag.id),t=drag.transform,u=dx/t.scale,v=dy/(t.scale*t.se);p.x=Math.round((base.x+t.ca*u+t.sa*v)/10)*10;p.y=Math.round((base.y-t.sa*u+t.ca*v)/10)*10;draw();status.textContent='Tentative XY move · release to validate. Height is unchanged.';}});
scene.addEventListener('pointerup',event=>{if(!drag)return;const finished=drag;drag=null;scene.releasePointerCapture(event.pointerId);if(finished.mode==='move'&&finished.moved&&finished.id){const candidate=layout(packed);packed=finished.baseline;validate(candidate);}else{selection();draw();}});
scene.addEventListener('pointercancel',()=>{if(drag){packed=drag.baseline;drag=null;selection();draw();}});
scene.addEventListener('wheel',event=>{event.preventDefault();zoom=Math.max(.6,Math.min(3,zoom*(event.deltaY<0?1.1:.9)));byId('scene-zoom').value=zoom;draw();},{passive:false});
byId('scene-zoom').addEventListener('input',event=>{zoom=Number(event.target.value);draw();});byId('scene-elevation').addEventListener('input',event=>{elevation=Number(event.target.value);draw();});
byId('rotate-scene').addEventListener('click',()=>{azimuth=45;elevation=25;zoom=1;byId('scene-zoom').value=1;byId('scene-elevation').value=25;draw();});
byId('toggle-scene-scale').addEventListener('click',event=>{full=!full;event.currentTarget.textContent=full?'Fit loaded cargo':'Show full container';byId('scene-mode-note').textContent=full?'Full translucent equipment envelope. Door end marked in amber.':'Camera fitted to cargo; container remains visible and may extend beyond viewport.';draw();});
scene.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-'].includes(event.key)){event.preventDefault();if(event.key==='ArrowLeft')azimuth-=10;if(event.key==='ArrowRight')azimuth+=10;if(event.key==='ArrowUp')elevation=Math.min(85,elevation+5);if(event.key==='ArrowDown')elevation=Math.max(10,elevation-5);if(event.key==='+')zoom=Math.min(3,zoom+.1);if(event.key==='-')zoom=Math.max(.6,zoom-.1);draw();}});
// Capacity is distinct from geometric feasibility; empty volume may be fragmented.
const c=packed.container,volume=c.inside_mm.length*c.inside_mm.width*c.inside_mm.height/1e9,kg=packed.totals.placed_weight_kg,cbm=packed.totals.placed_volume_m3;
const capacity=document.createElement('p');capacity.className='note';capacity.textContent=`Payload: ${kg.toFixed(1)} / ${c.max_payload_kg.toFixed(1)} kg (${Math.max(0,c.max_payload_kg-kg).toFixed(1)} kg remaining). Volume: ${cbm.toFixed(2)} / ${volume.toFixed(2)} m³ (${Math.max(0,volume-cbm).toFixed(2)} m³ nominal remaining). ${kg/c.max_payload_kg>=cbm/volume?'Weight':'Volume'} has the higher utilization ratio; this is not proof of the binding constraint or usable space.`;scene.parentElement.before(capacity);
selection();draw();
})();
