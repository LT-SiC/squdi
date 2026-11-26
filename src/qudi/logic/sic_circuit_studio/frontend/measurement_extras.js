/* SiC Circuit Studio — demonstration-only spatial visualizations.
 * No actual spin coordinates, measured couplings, or experimental data here.
 */
'use strict';
const SPIN_SITES = (() => {
  const candidates=[];
  for(let x=-3;x<=3;x++)for(let y=-3;y<=3;y++)for(let z=-3;z<=3;z++){
    if(x===0&&y===0&&z===0)continue;
    const r2=x*x+y*y+z*z;
    if(r2<15 && (x+y+z)%2===0)candidates.push({x,y,z,r2});
  }
  candidates.sort((a,b)=>a.r2-b.r2 || (a.x*11+a.y*7+a.z*3)-(b.x*11+b.y*7+b.z*3));
  // Deterministic fictional sites, not the locations reconstructed in the register paper.
  return candidates.slice(0,25).map((p,i)=>({...p,id:i+1,species:i%5===2?'¹³C':'²⁹Si'}));
})();
const REG_LINKS = (()=>{
 const edges=[];
 for(let i=0;i<SPIN_SITES.length;i++){
  const nearest=[];
  for(let j=0;j<SPIN_SITES.length;j++)if(i!==j){
   const a=SPIN_SITES[i],b=SPIN_SITES[j];
   nearest.push({j,d:Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z)});
  }
  nearest.sort((a,b)=>a.d-b.d);
  nearest.slice(0,3).forEach(e=>{
   const a=Math.min(i,e.j),b=Math.max(i,e.j);
   if(!edges.some(v=>v[0]===a&&v[1]===b))edges.push([a,b,e.d]);
  });
 }
 return edges;
})();
let regMode='3d',regPlane='xy',regYaw=-.54,regPitch=.42,regZoom=1,regPick=0,regPoints=[];
const CLAMP=(x,a,b)=>Math.max(a,Math.min(b,x));
function projection(p,w,h,scale){
 let x,y,depth=0;
 if(regMode==='2d'){
  [x,y]=regPlane==='xy'?[p.x,p.y]:regPlane==='xz'?[p.x,p.z]:[p.y,p.z];
 }else{
  const cy=Math.cos(regYaw),sy=Math.sin(regYaw),cx=Math.cos(regPitch),sx=Math.sin(regPitch);
  const x1=p.x*cy+p.z*sy,z1=-p.x*sy+p.z*cy;
  x=x1;y=p.y*cx-z1*sx;depth=p.y*sx+z1*cx;
 }
 return {x:w*.50+x*scale,y:h*.51-y*scale,depth};
}
function renderRegister(){
 const canvas=document.getElementById('register-canvas');
 if(!canvas||document.getElementById('page-measurement')?.classList.contains('hidden'))return;
 const rect=canvas.getBoundingClientRect(),dpr=Math.min(2,window.devicePixelRatio||1);
 const w=Math.max(250,rect.width||800),h=Math.max(230,rect.height||340);
 canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
 const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
 const bg=ctx.createLinearGradient(0,0,w,h);bg.addColorStop(0,'#0d2332');bg.addColorStop(1,'#15232e');ctx.fillStyle=bg;ctx.fillRect(0,0,w,h);
 // Background grid: decorative lattice-grid only.
 ctx.save();ctx.strokeStyle='rgba(140,190,200,.07)';ctx.lineWidth=.7;
 for(let x=12;x<w;x+=28){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
 for(let y=12;y<h;y+=28){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
 ctx.restore();
 const scale=Math.min(w/9.7,h/8.3)*regZoom;
 const origin=projection({x:0,y:0,z:0},w,h,scale);
 // Projection axes, to make 2D and 3D orientation explicit.
 const dirs=[['X',{x:3,y:0,z:0},'#db9b83'],['Y',{x:0,y:3,z:0},'#7abeb1'],['Z',{x:0,y:0,z:3},'#9f9cdb']];
 ctx.font='12px system-ui';
 dirs.forEach(([label,dir,color])=>{
  const to=projection(dir,w,h,scale);
  ctx.strokeStyle=color;ctx.lineWidth=1.1;ctx.setLineDash([5,5]);ctx.beginPath();ctx.moveTo(origin.x,origin.y);ctx.lineTo(to.x,to.y);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle=color;ctx.fillText(label,to.x+5,to.y-4);
 });
 regPoints=SPIN_SITES.map(p=>({...p,...projection(p,w,h,scale)}));
 REG_LINKS.forEach(([i,j,d])=>{
  const a=regPoints[i],b=regPoints[j];ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);
  ctx.strokeStyle=`rgba(105,181,195,${Math.round(CLAMP(.55-.09*d,.15,.45)*100)/100})`;
  ctx.lineWidth=1.3;ctx.stroke();
 });
 // Central vacancy rendered as a hollow diamond marker, not a detected nucleus.
 ctx.save();ctx.translate(origin.x,origin.y);ctx.rotate(Math.PI/4);ctx.fillStyle='#152630';ctx.strokeStyle='#f3dfbf';ctx.lineWidth=2.6;ctx.fillRect(-10,-10,20,20);ctx.strokeRect(-10,-10,20,20);ctx.restore();
 ctx.font='600 10px system-ui';ctx.fillStyle='#f3dfbf';ctx.fillText('V₂',origin.x+17,origin.y-11);
 const points=[...regPoints].sort((a,b)=>a.depth-b.depth);
 points.forEach(p=>{
  const active=p.id===regPick,rad=active?8:5.5;
  ctx.beginPath();ctx.arc(p.x,p.y,rad+4,0,2*Math.PI);ctx.fillStyle=active?'rgba(250,248,228,.18)':'rgba(255,255,255,.06)';ctx.fill();
  ctx.beginPath();ctx.arc(p.x,p.y,rad,0,2*Math.PI);ctx.fillStyle=p.species==='¹³C'?'#e6b374':'#73c2c6';ctx.fill();
  ctx.strokeStyle=active?'#fff':p.species==='¹³C'?'#f2d1a2':'#afdadd';ctx.lineWidth=active?2.5:1;ctx.stroke();
  if(active){ctx.font='11px system-ui';ctx.fillStyle='#f1f8f8';ctx.fillText(`Spin ${p.id}`,p.x+12,p.y-13);}
 });
 const info=document.getElementById('register-selected');
 if(info){const p=SPIN_SITES.find(x=>x.id===regPick);info.textContent=p?`Selected: spin ${p.id} · ${p.species} · illustrative coordinates (${p.x}, ${p.y}, ${p.z}) a.u.`:'Click a nucleus to inspect · drag to rotate · wheel to zoom';}
}
function initRegister(){
 const can=document.getElementById('register-canvas');if(!can)return;
 const mode3=document.getElementById('reg-3d'),mode2=document.getElementById('reg-2d'),planes=document.getElementById('reg-planes');
 function mode(v){regMode=v;mode3.classList.toggle('active',v==='3d');mode2.classList.toggle('active',v==='2d');planes.classList.toggle('hidden',v!=='2d');renderRegister();}
 mode3.onclick=()=>mode('3d');mode2.onclick=()=>mode('2d');
 planes.querySelectorAll('button').forEach(b=>b.onclick=()=>{regPlane=b.dataset.plane;planes.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));renderRegister();});
 document.getElementById('reg-zoom-in').onclick=()=>{regZoom=CLAMP(regZoom*1.18,.45,3.2);renderRegister();};
 document.getElementById('reg-zoom-out').onclick=()=>{regZoom=CLAMP(regZoom/1.18,.45,3.2);renderRegister();};
 document.getElementById('reg-reset').onclick=()=>{regYaw=-.54;regPitch=.42;regZoom=1;regPick=0;renderRegister();};
 can.addEventListener('wheel',e=>{e.preventDefault();regZoom=CLAMP(regZoom*(e.deltaY>0?.9:1.1),.45,3.2);renderRegister();},{passive:false});
 let drag=null;
 can.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,dragged:false};can.setPointerCapture?.(e.pointerId);});
 can.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;
  const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
  if(Math.abs(dx)+Math.abs(dy)>2){drag.dragged=true;if(regMode==='3d'){regYaw+=dx*.009;regPitch=CLAMP(regPitch+dy*.009,-1.45,1.45);renderRegister();}}
  drag.x=e.clientX;drag.y=e.clientY;
 });
 can.addEventListener('pointerup',e=>{if(!drag||e.pointerId!==drag.id)return;
  if(!drag.dragged){const r=can.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;let nearest=null,dist=19;
   regPoints.forEach(p=>{const d=Math.hypot(x-p.x,y-p.y);if(d<dist){dist=d;nearest=p.id;}});if(nearest){regPick=nearest;renderRegister();}
  }drag=null;
 });
 can.addEventListener('pointercancel',()=>{drag=null;});
 window.addEventListener('resize',()=>{if(!document.getElementById('page-measurement').classList.contains('hidden')){renderRegister();if(scanView==='surface')renderScanSurface();}});
}
let scanView='map';
function renderScanSurface(){
 const can=document.getElementById('scan-surface');if(!can||!scanValues||scanView!=='surface')return;
 const ctx=can.getContext('2d');const w=can.width,h=can.height;
 const bg=ctx.createLinearGradient(0,0,w,h);bg.addColorStop(0,'#101e2a');bg.addColorStop(1,'#172938');ctx.fillStyle=bg;ctx.fillRect(0,0,w,h);
 const n=32,variant=document.getElementById('scan-sample').value;
 const project=(u,v,z)=>({x:w*.49+(u-v)*w*.43,y:h*.65+(u+v-1)*h*.22-z*h*.36});
 // Render mesh in back-to-front order for a synthetic height field.
 for(let sum=0;sum<2*(n-1);sum++){
  for(let i=0;i<n-1;i++){
   const j=sum-i;if(j<0||j>=n-1)continue;
   const u=i/(n-1),v=j/(n-1),u1=(i+1)/(n-1),v1=(j+1)/(n-1);
   const raw=[[u,v],[u1,v],[u1,v1],[u,v1]];
   const pts=raw.map(([a,b])=>project(a,b,scanField(a,b,variant)/scanPeak));
   const intensity=raw.reduce((acc,[a,b])=>acc+scanField(a,b,variant),0)/4;
   const col=scanColor(intensity);
   ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);for(let k=1;k<4;k++)ctx.lineTo(pts[k].x,pts[k].y);ctx.closePath();
   ctx.fillStyle=`rgb(${col.join(',')})`;ctx.fill();ctx.strokeStyle='rgba(6,22,33,.34)';ctx.lineWidth=.6;ctx.stroke();
  }
 }
 ctx.font='14px system-ui';ctx.fillStyle='#d2e7e9';ctx.fillText('Synthetic fluorescence height map',19,28);
 ctx.fillStyle='#9fbcc5';ctx.font='12px system-ui';ctx.fillText('X / Y → position · Z → relative photon rate',19,48);
}
function initScanView(){
 const map=document.getElementById('scan-map'),surface=document.getElementById('scan-surface');
 const mapbtn=document.getElementById('scan-map-mode'),surfacebtn=document.getElementById('scan-surface-mode');
 if(!map||!surface)return;
 const update=(v)=>{scanView=v;map.classList.toggle('hidden',v!=='map');surface.classList.toggle('hidden',v!=='surface');mapbtn.classList.toggle('active',v==='map');surfacebtn.classList.toggle('active',v==='surface');document.getElementById('scan-axis-caption').textContent=v==='map'?'X position (µm)':'X / Y position · height = intensity';renderScanSurface();};
 mapbtn.onclick=()=>update('map');surfacebtn.onclick=()=>update('surface');
 for(const id of ['scan-range','scan-resolution','scan-sample'])document.getElementById(id)?.addEventListener('change',()=>setTimeout(renderScanSurface,0));
}
document.addEventListener('DOMContentLoaded',()=>{initRegister();initScanView();});
