/* SiC Circuit Studio v0.3.3 — dependency-free editor, no laboratory hardware calls. */
'use strict';
const $ = id => document.getElementById(id);
const PI = Math.PI;
const CW = 110, RH = 76, LEFT = 94, TOP = 66;
// Physical meaning in conventional circuit notation; not a calibrated hardware instruction.
const GATE_INFO = {
 rx:'Single-qubit rotation about the Bloch-sphere X axis.',
 ry:'Single-qubit rotation about the Bloch-sphere Y axis.',
 ddrf:'Electron-state-conditioned nuclear rotation: +θ for electron |0⟩, −θ for |1⟩ (or reverse).',
 h:'Hadamard: maps Z-basis states into equal superpositions.',
 x:'Pauli X: flips |0⟩ and |1⟩ (quantum NOT).',
 y:'Pauli Y: π rotation about Y (up to global phase).',
 z:'Pauli Z: adds a − sign to the |1⟩ amplitude.',
 s:'Phase gate S: adds phase +π/2 to |1⟩.',
 sdg:'S†: inverse phase gate, adds −π/2 to |1⟩.',
 t:'T gate: adds phase +π/4 to |1⟩.',
 tdg:'T†: inverse T gate, adds −π/4 to |1⟩.',
 sx:'Square-root X: applying SX twice produces X.',
 sxdg:'SX†: inverse square-root X gate.',
 rz:'Single-qubit rotation about the Bloch-sphere Z axis.',
 id:'Identity: leaves the quantum state unchanged.',
 cx:'Controlled X (CNOT): flips the target if the control is |1⟩.',
 cy:'Controlled Y: applies Y to the target if control is |1⟩.',
 cz:'Controlled Z: changes the sign of the |11⟩ amplitude.',
 ch:'Controlled Hadamard: applies H to the target if control is |1⟩.',
 crz:'Controlled Rz: rotates the target about Z if control is |1⟩.',
 swap:'SWAP: exchanges two qubit states.',
 measure:'Computational-basis (Z) measurement. Not equivalent to the PI3 optical readout sequence.',
 reset:'Prepares the qubit in |0⟩ (idealized reset operation).',
 barrier:'Compiler fence on a wire; no physical quantum gate.'
};
const groups = {
 native: [{type:'rx', title:'R<sub>x</sub>'}, {type:'ry', title:'R<sub>y</sub>'}],
 ddrf: [{type:'ddrf',axis:'x',title:'DDRF X'}, {type:'ddrf',axis:'y',title:'DDRF Y'}],
 standard: [
  {type:'h',title:'H'}, {type:'x',title:'X'}, {type:'y',title:'Y'}, {type:'z',title:'Z'},
  {type:'s',title:'S'}, {type:'sdg',title:'S†'}, {type:'t',title:'T'}, {type:'tdg',title:'T†'},
  {type:'sx',title:'√X'}, {type:'sxdg',title:'√X†'}, {type:'rz',title:'R<sub>z</sub>'}, {type:'id',title:'I'},
  {type:'cx',title:'CX'}, {type:'cy',title:'CY'}, {type:'cz',title:'CZ'}, {type:'ch',title:'CH'},
  {type:'crz',title:'CR<sub>z</sub>'}, {type:'swap',title:'SWAP'},
  {type:'measure',title:'M'}, {type:'reset',title:'RESET'}, {type:'barrier',title:'│'}
 ]
};
const STANDARD_SECTIONS = [
 ['Pauli & basis', ['h','x','y','z','id']],
 ['Phase & inverse', ['s','sdg','t','tdg','rz']],
 ['Square-root', ['sx','sxdg']],
 ['Controlled & exchange', ['cx','cy','cz','ch','crz','swap']],
 ['Measurement & timing', ['measure','reset','barrier']]
];
function family(t){return t==='ddrf'?'ddrf':t==='rx'||t==='ry'?'native':t==='measure'||t==='reset'?'measurement':t==='barrier'?'timing':isTwo(t)?'controlled':['s','sdg','t','tdg','rz'].includes(t)?'phase':'standard';}
function gateHelp(g){return GATE_INFO[g.type]||'Quantum-circuit operation.';}
const isTwo = t => ['cx','cy','cz','ch','crz','swap','ddrf'].includes(t);
const isAngle = t => ['rx','ry','rz','crz','ddrf'].includes(t);
const deep = value => JSON.parse(JSON.stringify(value));
let cid = 1, circuit = {version:2,qubits:2,columns:12,gates:[]};
let selectedId = null, paletteSelection = null, history = [], future = [], dragging = null, dragHandled = false, skipClick = false, timer = null, exportSeq = 0, outputCode='';
const getGate = id => circuit.gates.find(g => g.id===id);
const snapshot = () => JSON.stringify(circuit);
function message(msg){$('status').textContent = msg;}
function remember(){try{localStorage.setItem('sic-circuit-studio-v2',snapshot());}catch{}}
function historyPush(){history.push(snapshot());if(history.length>80)history.shift();future=[];}
function newId(){return cid++;}
function route(page){
 $('page-home').classList.toggle('hidden',page!=='home');$('page-editor').classList.toggle('hidden',page!=='editor');$('page-measurement').classList.toggle('hidden',page!=='measurement');
 document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
 $('site-menu').open=false;
 location.hash=page==='editor'?'editor':page==='measurement'?'measurement':'workspace';
 if(page==='editor'){render();compile();setTimeout(()=>render(),30);} if(page==='measurement'){ensureScan();refreshMeasurementCode();renderRegister();}
}
function setTheme(pref){
 const dark=pref==='dark'||(pref==='auto'&&window.matchMedia('(prefers-color-scheme: dark)').matches);
 document.documentElement.dataset.theme=dark?'dark':'light';$('theme').value=pref;try{localStorage.setItem('sic-theme',pref);}catch{}
}
function createPalette(){
 function addGate(parent,spec){
  const b=document.createElement('button');b.type='button';b.className='palette-gate';b.draggable=true;
  b.dataset.family=family(spec.type);
  b.innerHTML=`<span class="symbol">${isAngle(spec.type)?gateLabel({type:spec.type,axis:spec.axis||'x',angle:PI/2,sign:1}):spec.title}</span>${spec.type==='ddrf'?'<span class="ddrf-warning" title="Confirm which electron spin state corresponds to + / − with Erik." aria-label="DDRF sign convention requires confirmation">!</span>':''}`;
  b.title=GATE_INFO[spec.type]||spec.title;
  b.setAttribute('aria-label',`${spec.title}: ${GATE_INFO[spec.type]||''}`);
  b.addEventListener('click',()=>{paletteSelection=spec;updatePalette();message(`${spec.title}: click a circuit slot to place.`);});
  b.addEventListener('dragstart',e=>{dragging={kind:'palette',spec};dragHandled=false;e.dataTransfer.effectAllowed='copy';e.dataTransfer.setData('text/plain','gate');});
  b.addEventListener('dragend',()=>{dragging=null;dragHandled=false;});
  parent.appendChild(b);b.dataset.key=`${spec.type}-${spec.axis||''}`;
 }
 for(const group of ['native','ddrf'])groups[group].forEach(spec=>addGate($(group+'-palette'),spec));
 const standard=$('standard-palette');standard.classList.add('standard-library');
 STANDARD_SECTIONS.forEach(([title,types])=>{
  const section=document.createElement('div');section.className='gate-subsection';
  const header=document.createElement('h4');header.textContent=title;section.appendChild(header);
  const list=document.createElement('div');list.className='gate-palette';
  types.forEach(t=>addGate(list,groups.standard.find(item=>item.type===t)));
  section.appendChild(list);standard.appendChild(section);
 });
 const select=$('setting-type');
 [['Spin rotations',groups.native],['DDRF control',[{type:'ddrf',title:'DDRF'}]],...STANDARD_SECTIONS.map(([label,types])=>[label,types.map(t=>groups.standard.find(g=>g.type===t))])].forEach(([label,entries])=>{
  const optgroup=document.createElement('optgroup');optgroup.label=label;
  entries.forEach(item=>{const opt=document.createElement('option');opt.value=item.type;opt.textContent=item.type==='rx'?'Rx':item.type==='ry'?'Ry':item.title.replace(/<[^>]*>/g,'');optgroup.appendChild(opt);});select.appendChild(optgroup);
 });
}
function updatePalette(){document.querySelectorAll('.palette-gate').forEach(el=>el.classList.toggle('active',!!paletteSelection && el.dataset.key===`${paletteSelection.type}-${paletteSelection.axis||''}`));}
function rowsFor(g){return Array.from({length:Math.abs((g.target??g.row)-g.row)+1},(_,i)=>Math.min(g.row,g.target??g.row)+i);}
function canPlace(candidate,oldId=null){
 if(candidate.row<0||candidate.row>=circuit.qubits||candidate.col<0||candidate.col>299)return false;
 if(isTwo(candidate.type)&&(candidate.target==null||candidate.target===candidate.row||candidate.target>=circuit.qubits||candidate.target<0))return false;
 const occupied=new Set(rowsFor(candidate).map(r=>`${candidate.col}-${r}`));
 return !circuit.gates.some(g=>g.id!==oldId&&rowsFor(g).some(r=>occupied.has(`${g.col}-${r}`)));
}
function makeGate(spec,row,col){
 const typ=spec.type, g={id:newId(),type:typ,row,col};
 if(isTwo(typ)){
   if(typ==='ddrf'){
    g.row=row===0?(circuit.qubits>1?1:0):0;g.target=row===0?0:row;
    // Canonical DDRF: electron control on q0, target is the dropped nuclear wire.
    g.row=0;g.target=row===0?Math.min(1,circuit.qubits-1):row;
   }else g.target=(row+1)%circuit.qubits;
 }
 if(isAngle(typ))g.angle=PI/2;
 if(typ==='ddrf'){g.axis=spec.axis||'x';g.sign=1;}
 return g;
}
function place(spec,row,col){
 if(isTwo(spec.type)&&circuit.qubits<2){message('Add at least two qubits for a controlled gate.');return;}
 const g=makeGate(spec,row,col);
 if(!canPlace(g)){message('This slot is occupied or does not fit the gate.');return;}
 historyPush();circuit.gates.push(g);selectedId=g.id;
 circuit.columns=Math.min(300,Math.max(circuit.columns,col+5)); // retained in JSON for backward compatibility; visible width follows placed gates
 paletteSelection=null;updatePalette();commit('Gate added');
}
function mutateGate(id,patch){
 const old=getGate(id);if(!old)return;
 const next={...old,...patch};
 if(!isTwo(next.type))delete next.target;
 if(isTwo(next.type)&&next.target==null)next.target=(next.row+1)%circuit.qubits;
 if(isAngle(next.type)&&next.angle==null)next.angle=PI/2;
 if(!isAngle(next.type))delete next.angle;
 if(next.type==='ddrf'){next.axis??='x';next.sign??=1;}
 else {delete next.axis;delete next.sign;}
 if(!canPlace(next,id)){message('This change would overlap another gate or use an invalid qubit.');refreshSettings();return;}
 historyPush();Object.assign(old,next);
 for(const key of ['target','angle','axis','sign'])if(!(key in next))delete old[key];
 commit('Gate updated');
}
function removeGate(id){const idx=circuit.gates.findIndex(g=>g.id===id);if(idx<0)return;historyPush();circuit.gates.splice(idx,1);if(selectedId===id)selectedId=null;commit('Gate removed');}
function commit(text='Saved'){remember();render();compile();renderPulsePreview();message(text);}
function changeQubits(n){if(!Number.isInteger(n)||n<1||n>25){message('Choose 1–25 qubits.');$('qubits-input').value=circuit.qubits;return;}
 if(n===circuit.qubits)return;historyPush();circuit.qubits=n;
 const old=circuit.gates.length;circuit.gates=circuit.gates.filter(g=>g.row<n&&(g.target==null||g.target<n));
 if(selectedId&&!getGate(selectedId))selectedId=null;
 commit(old===circuit.gates.length?'Register resized':'Register resized; out-of-range gates removed');
}
// Mathematical labels use HTML fractions and genuine typographic subscripts.
function angleMarkup(angle, signPrefix=''){
 const a=Number.isFinite(angle)?angle:PI/2;
 const abs=Math.abs(a),sign=a<0?'−':'';
 let core;
 if(Math.abs(abs-PI/2)<1e-8)core='<span class="math-frac"><span>π</span><span>2</span></span>';
 else if(Math.abs(abs-PI)<1e-8)core='π';
 else if(Math.abs(abs-2*PI)<1e-8)core='2π';
 else core=Number(abs.toFixed(3)).toString();
 return `<span class="math-arg"><span class="math-paren">(</span><span class="math-sign">${signPrefix||sign}</span>${core}<span class="math-paren">)</span></span>`;
}
function gateLabel(g){
 const axis=g.type==='ddrf'?g.axis:g.type?.slice(1);
 if(g.type==='ddrf')return `<span class="math-gate">R<sub>${axis||'x'}</sub>${angleMarkup(Math.abs(g.angle??PI/2),g.sign===-1?'∓':'±')}</span>`;
 if(['rx','ry','rz'].includes(g.type))return `<span class="math-gate">R<sub>${axis}</sub>${angleMarkup(g.angle??PI/2)}</span>`;
 if(g.type==='crz')return `<span class="math-gate">CR<sub>z</sub>${angleMarkup(g.angle??PI/2)}</span>`;
 const lookup={h:'H',x:'X',y:'Y',z:'Z',s:'S',sdg:'S†',t:'T',tdg:'T†',sx:'√X',sxdg:'√X†',id:'I',cx:'⊕',cy:'Y',cz:'●',ch:'H',swap:'×',measure:'M',reset:'|0⟩',barrier:'│'};
 return lookup[g.type]||g.type;
}
function effectiveColumns(){
 // Keep initially visible slots in the available panel width; extend only when used.
 const vw=$('circuit-viewport').clientWidth || 900;
 const initiallyVisible=Math.max(2,Math.floor((vw-LEFT-18)/CW));
 const last=Math.max(-1,...circuit.gates.map(g=>g.col));
 return Math.min(300,Math.max(initiallyVisible,last+3));
}
function pointInRect(e,r){return e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;}
function render(){
 if($('page-editor').classList.contains('hidden'))return;
 const n=circuit.qubits,cols=effectiveColumns(),height=TOP*2+(n-1)*RH,width=Math.max($('circuit-viewport').clientWidth,LEFT+cols*CW+18);
 $('qubits-input').value=n;
 const surface=$('circuit');surface.style.width=width+'px';surface.style.height=Math.max(height,240)+'px';
 $('wires').setAttribute('width',width);$('wires').setAttribute('height',Math.max(height,240));
 const wires=[];const colors=getComputedStyle(document.documentElement);const line=colors.getPropertyValue('--line').trim(),accent=colors.getPropertyValue('--accent').trim();
 for(let r=0;r<n;r++){
  const y=TOP+r*RH;wires.push(`<line x1="${LEFT-1}" y1="${y}" x2="${width-20}" y2="${y}" stroke="${line}" stroke-width="2"/>`);
 }
 for(const g of circuit.gates){if(!isTwo(g.type))continue;
  const x=LEFT+g.col*CW+CW/2,a=TOP+g.row*RH,b=TOP+g.target*RH;
  const endpoint=g.type==='ddrf' ? b+(a<b?-24:24) : b;
  wires.push(`<line x1="${x}" y1="${a}" x2="${x}" y2="${endpoint}" stroke="${accent}" stroke-width="2.3"/>`);
  if(g.type==='ddrf'||['cx','cy','cz','ch','crz'].includes(g.type))wires.push(`<circle cx="${x}" cy="${a}" r="6" fill="${accent}"/>`);
 }
 $('wires').innerHTML=wires.join('');
 const cells=$('cells');cells.innerHTML='';
 for(let r=0;r<n;r++){
  const l=document.createElement('div');l.className='wire-label';l.style.top=(TOP+r*RH)+'px';l.textContent=`q${String(r).replace(/[0-9]/g,c=>'₀₁₂₃₄₅₆₇₈₉'[Number(c)])}`;cells.appendChild(l);
  for(let c=0;c<cols;c++){
   const cell=document.createElement('div');cell.className='slot';cell.style.left=(LEFT+c*CW)+'px';cell.style.top=(TOP+r*RH-RH/2)+'px';cell.dataset.row=r;cell.dataset.col=c;
   cell.addEventListener('click',()=>{if(paletteSelection)place(paletteSelection,r,c);else{selectedId=null;render();}});
   cells.appendChild(cell);
  }
 }
 const gates=$('gates');gates.innerHTML='';
 for(const g of circuit.gates){
  const el=document.createElement('button');el.type='button';el.draggable=false;el.className='canvas-gate';
  if(selectedId===g.id)el.classList.add('selected');
  const drawRow=isTwo(g.type)?g.target:g.row;
  el.style.left=(LEFT+g.col*CW+CW/2)+'px';el.style.top=(TOP+drawRow*RH)+'px';el.innerHTML=gateLabel(g)+(g.type==='ddrf'?'<span class="ddrf-warning" title="Confirm which electron spin state corresponds to + / − with Erik.">!</span>':'');
  el.title=gateHelp(g);el.dataset.family=family(g.type);
  if(g.type==='cx'){el.classList.add('not-target');}
  el.addEventListener('click',e=>{e.stopPropagation();if(skipClick)return;selectedId=g.id;paletteSelection=null;updatePalette();render();});
  // Existing gates use pointer dragging rather than browser-native HTML drag.
  // This avoids inconsistent native dragstart behavior on nested circuit overlays.
  el.addEventListener('pointerdown',e=>{
    if(e.button!==0)return;
    e.stopPropagation();
    const pointerId=e.pointerId, x0=e.clientX, y0=e.clientY;
    let moving=false, ghost=null;
    if(el.setPointerCapture)el.setPointerCapture(pointerId);
    function move(ev){
      if(ev.pointerId!==pointerId)return;
      if(!moving && Math.hypot(ev.clientX-x0,ev.clientY-y0)>7){
        moving=true;el.classList.add('being-dragged');
        ghost=el.cloneNode(true);ghost.classList.add('drag-ghost');ghost.classList.remove('selected','being-dragged');
        document.body.appendChild(ghost);
      }
      if(moving){
        ev.preventDefault();
        if(ghost){ghost.style.left=(ev.clientX+14)+'px';ghost.style.top=(ev.clientY+12)+'px';}
        $('trash').classList.toggle('drag-over',pointInRect(ev,$('trash').getBoundingClientRect()));
      }
    }
    function cleanup(){
      document.removeEventListener('pointermove',move,true);
      document.removeEventListener('pointerup',up,true);
      document.removeEventListener('pointercancel',cancel,true);
      window.removeEventListener('blur',cancel);
      if(el.hasPointerCapture?.(pointerId))el.releasePointerCapture(pointerId);
      el.classList.remove('being-dragged');$('trash').classList.remove('drag-over');
      ghost?.remove();
    }
    function cancel(){cleanup();}
    function up(ev){
      if(ev.pointerId!==pointerId)return;
      cleanup();
      if(!moving)return;
      skipClick=true;setTimeout(()=>{skipClick=false;},0);
      const vr=$('circuit-viewport').getBoundingClientRect();
      const inside=ev.clientX>=vr.left&&ev.clientX<=vr.right&&ev.clientY>=vr.top&&ev.clientY<=vr.bottom;
      if(pointInRect(ev,$('trash').getBoundingClientRect()) || !inside){removeGate(g.id);return;}
      const rect=$('circuit').getBoundingClientRect();
      const row=Math.round((ev.clientY-rect.top-TOP)/RH),col=Math.floor((ev.clientX-rect.left-LEFT)/CW);
      if(row<0||row>=circuit.qubits||col<0||col>=300){message('Drag cancelled: invalid slot.');return;}
      const next={...g,col};
      if(g.type==='ddrf')next.target=row===0?g.target:row;
      else if(isTwo(g.type)){const delta=row-g.target;next.row=g.row+delta;next.target=row;}
      else next.row=row;
      if(!canPlace(next,g.id)){message('Gate cannot be placed there.');return;}
      historyPush();Object.assign(g,next);selectedId=g.id;commit('Gate moved');
    }
    document.addEventListener('pointermove',move,true);
    document.addEventListener('pointerup',up,true);
    document.addEventListener('pointercancel',cancel,true);
    window.addEventListener('blur',cancel);
  });
  gates.appendChild(el);
 }
 refreshSettings();$('undo').disabled=history.length===0;$('redo').disabled=future.length===0;
}
function refreshSettings(){
 const g=getGate(selectedId);$('settings-empty').classList.toggle('hidden',!!g);$('settings').classList.toggle('hidden',!g);if(!g)return;
 $('setting-type').value=g.type;$('setting-help').textContent=gateHelp(g);
 const rows=$('setting-row'),target=$('setting-target');rows.replaceChildren();target.replaceChildren();
 for(let i=0;i<circuit.qubits;i++){
  let opt=document.createElement('option');opt.value=i;opt.textContent=`q${i}`;rows.append(opt);
  opt=document.createElement('option');opt.value=i;opt.textContent=`q${i}`;target.append(opt);
 }
 rows.value=g.row;target.value=g.target??0;
 const two=isTwo(g.type),angle=isAngle(g.type);
 $('target-row').classList.toggle('hidden',!two);$('axis-row').classList.toggle('hidden',g.type!=='ddrf');$('sign-row').classList.toggle('hidden',g.type!=='ddrf');$('angle-row').classList.toggle('hidden',!angle);
 $('row-label').firstChild.textContent=g.type==='ddrf'?'Electron control qubit':'Qubit / control';
 if(g.type==='ddrf')document.querySelector(`input[name="axis"][value="${g.axis}"]`).checked=true;
 const val=Math.abs(g.angle??PI/2),a=Math.abs(val-PI/2)<1e-9?'half':Math.abs(val-PI)<1e-9?'full':'other';
 document.querySelector(`input[name="angle"][value="${a}"]`).checked=true;
 $('other-angle').classList.toggle('hidden',a!=='other');$('other-angle').value=g.angle??PI/2;
 if(g.type==='ddrf')document.querySelector(`input[name="sign"][value="${g.sign}"]`).checked=true;
}
function undo(){if(!history.length)return;future.push(snapshot());circuit=JSON.parse(history.pop());selectedId=null;commit('Undone');}
function redo(){if(!future.length)return;history.push(snapshot());circuit=JSON.parse(future.pop());selectedId=null;commit('Redone');}
function createExample(){
 historyPush();circuit={version:2,qubits:2,columns:12,gates:[
  {id:newId(),type:'ry',row:0,col:0,angle:PI/2},
  {id:newId(),type:'ddrf',row:0,target:1,col:1,axis:'x',angle:PI/2,sign:1},
  {id:newId(),type:'rx',row:0,col:2,angle:PI/2},
  {id:newId(),type:'ddrf',row:0,target:1,col:3,axis:'y',angle:PI/2,sign:-1}
 ]};selectedId=null;commit('Example loaded');
}
function highlightCode(code,fmt){
 const pattern=/(#[^\n]*|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:from|import|as|def|return|for|in|if|else|True|False|None|OPENQASM|include|qreg|creg|measure|reset|barrier|gate|opaque)\b|\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\b|\b[A-Za-z_][A-Za-z_0-9]*(?=\s*\())/g;
 const escapeHtml=t=>t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
 let html='',pos=0;
 for(const m of code.matchAll(pattern)){
  html+=escapeHtml(code.slice(pos,m.index));const token=m[0];
  const kind=token.startsWith('#')||token.startsWith('//')?'comment':token.startsWith('"')||token.startsWith("'")?'string':/^\d/.test(token)?'number':/^(from|import|as|def|return|for|in|if|else|True|False|None|OPENQASM|include|qreg|creg|measure|reset|barrier|gate|opaque)$/.test(token)?'keyword':'function';
  html+=`<span class="syntax-${kind}">${escapeHtml(token)}</span>`;pos=m.index+token.length;
 }
 return html+escapeHtml(code.slice(pos));
}
async function compile(){
 const seq=++exportSeq;const fmt=$('format').value;
 const clean={...circuit,gates:circuit.gates.map(({id,...g})=>g)};
 const out=$('output');out.classList.remove('error');out.textContent='Generating…';
 $('code-lang').textContent={qasm:'OpenQASM 2.0',qiskit:'Python · Qiskit',mcas:'Python · MCAS'}[fmt];
 try{
 const res=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({circuit:clean,format:fmt})});
 const payload=await res.json();if(seq!==exportSeq)return;
 if(!res.ok){outputCode='';out.classList.add('error');out.textContent=payload.error||'Export unavailable';}
 else{outputCode=payload.code;out.innerHTML=highlightCode(payload.code,fmt);}
 if(!$('page-measurement').classList.contains('hidden'))refreshMeasurementCode();
 $('export-note').textContent=fmt==='mcas'?'Legacy NV three-spin mapping only. This is not a SiC/squdi driver.':fmt==='qiskit'?'Qiskit Python source; requires Qiskit to execute. No hardware control.':'DDRF is decomposed into standard gates for OpenQASM 2.0.';
 }catch(error){if(seq!==exportSeq)return;outputCode='';out.classList.add('error');out.textContent=`Server unavailable: ${error.message}`;}
}
function loadSaved(){try{const s=JSON.parse(localStorage.getItem('sic-circuit-studio-v2'));if(!s)return;
 if(!Number.isInteger(s.qubits)||s.qubits<1||s.qubits>25||!Array.isArray(s.gates))return;
 circuit=s;circuit.gates.forEach(g=>g.id=newId());
 }catch{}}
function init(){
 const theme=localStorage.getItem('sic-theme')||'auto';setTheme(['auto','dark','light'].includes(theme)?theme:'auto');
 $('theme').addEventListener('change',e=>setTheme(e.target.value));
 window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{if($('theme').value==='auto')setTheme('auto')});
 document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>route(b.dataset.page)));
 $('brand-home').onclick=()=>route('home');$('back-home').onclick=()=>route('home');$('measurement-home').onclick=()=>route('home');$('home-circuit-card').onclick=()=>route('editor');$('home-measurement-card').onclick=()=>route('measurement');
 document.addEventListener('click',e=>{if(!$('site-menu').contains(e.target))$('site-menu').open=false;});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')$('site-menu').open=false;});
 createPalette();loadSaved();
 $('minus-qubits').onclick=()=>changeQubits(circuit.qubits-1);$('plus-qubits').onclick=()=>changeQubits(circuit.qubits+1);
 $('qubits-input').addEventListener('change',e=>changeQubits(Number(e.target.value)));
 $('qubits-input').addEventListener('keydown',e=>{if(e.key==='Enter'){e.target.blur();changeQubits(Number(e.target.value));}});
 $('example').onclick=createExample;$('clear').onclick=()=>{historyPush();circuit.gates=[];selectedId=null;commit('Circuit cleared');};
 $('undo').onclick=undo;$('redo').onclick=redo;
 $('setting-type').onchange=e=>mutateGate(selectedId,{type:e.target.value});
 $('setting-row').onchange=e=>mutateGate(selectedId,{row:Number(e.target.value)});
 $('setting-target').onchange=e=>mutateGate(selectedId,{target:Number(e.target.value)});
 document.querySelectorAll('input[name="axis"]').forEach(i=>i.onchange=e=>mutateGate(selectedId,{axis:e.target.value}));
 document.querySelectorAll('input[name="sign"]').forEach(i=>i.onchange=e=>mutateGate(selectedId,{sign:Number(e.target.value)}));
 document.querySelectorAll('input[name="angle"]').forEach(i=>i.onchange=e=>{if(e.target.value==='other'){$('other-angle').classList.remove('hidden');$('other-angle').focus();return;}
  const g=getGate(selectedId);mutateGate(selectedId,{angle:(g?.angle<0?-1:1)*(e.target.value==='half'?PI/2:PI)});
 });
 $('other-angle').onchange=e=>{const val=Number(e.target.value);if(Number.isFinite(val)&&Math.abs(val)<=4*PI)mutateGate(selectedId,{angle:val});else message('Invalid angle.');};
 $('remove-selected').onclick=()=>removeGate(selectedId);
 $('trash').onclick=()=>{if(selectedId)removeGate(selectedId);};
 // Native button keyboard behavior supports Enter and Space automatically.
 for(const area of [$('trash'),$('circuit-viewport')]){
  area.addEventListener('dragover',e=>{if(!dragging)return;e.preventDefault();e.dataTransfer.dropEffect=area.id==='trash'?'move':dragging.kind==='palette'?'copy':'move';if(area.id==='trash')area.classList.add('drag-over');});
  area.addEventListener('dragleave',()=>{if(area.id==='trash')area.classList.remove('drag-over');});
 }
 $('trash').addEventListener('drop',e=>{e.preventDefault();dragHandled=true;$('trash').classList.remove('drag-over');if(dragging?.kind==='existing')removeGate(dragging.id);dragging=null;});
 $('gates').addEventListener('click',e=>{
   if(e.target.closest('.canvas-gate'))return;
   const rect=$('circuit').getBoundingClientRect();
   const row=Math.round((e.clientY-rect.top-TOP)/RH),col=Math.floor((e.clientX-rect.left-LEFT)/CW);
   if(row<0||row>=circuit.qubits||col<0||col>=effectiveColumns()){return;}
   if(paletteSelection)place(paletteSelection,row,col);
   else {selectedId=null;render();}
 });
 $('circuit-viewport').addEventListener('drop',e=>{
  if(!dragging)return;e.preventDefault();dragHandled=true;
  const rect=$('circuit').getBoundingClientRect();const x=e.clientX-rect.left,y=e.clientY-rect.top;
  const row=Math.round((y-TOP)/RH),col=Math.floor((x-LEFT)/CW);
  if(row<0||row>=circuit.qubits||col<0||col>=300){dragHandled=false;return;}
  if(dragging.kind==='palette')place(dragging.spec,row,col);
  else{
    const g=getGate(dragging.id);if(g){const next={...g,col};if(g.type==='ddrf')next.target=row===0?g.target:row;
     else if(isTwo(g.type)){const delta=row-g.target;next.row=g.row+delta;next.target=row;}
     else next.row=row;
     if(canPlace(next,g.id)){historyPush();Object.assign(g,next);selectedId=g.id;commit('Gate moved');}else message('Gate cannot be placed there.');
    }
  }
  dragging=null;
 });
 $('format').addEventListener('change',compile);$('pulse-envelope').addEventListener('change',renderPulsePreview);$('pulse-panel').addEventListener('toggle',()=>{if($('pulse-panel').open)renderPulsePreview();});
 window.addEventListener('resize',()=>{if(!$('page-editor').classList.contains('hidden'))render();});
 $('copy').onclick=async()=>{if(!outputCode){message('Nothing to copy.');return;}try{await navigator.clipboard.writeText(outputCode);message('Code copied');}catch{message('Clipboard unavailable. Select text in export panel and copy manually.');}};
 $('save').onclick=()=>{const clean={...circuit,gates:circuit.gates.map(({id,...g})=>g)};
  const blob=new Blob([JSON.stringify(clean,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='sic-circuit.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);message('JSON saved');};
 $('import').onclick=()=>$('file-input').click();
 $('file-input').addEventListener('change',async e=>{
  const file=e.target.files?.[0];if(!file)return;
  try{const data=JSON.parse(await file.text());const resp=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({circuit:data,format:'qasm'})});const result=await resp.json();if(!resp.ok)throw Error(result.error);
   historyPush();circuit=result.circuit;circuit.gates.forEach(g=>g.id=newId());selectedId=null;commit('JSON loaded');
  }catch(error){message(`Import rejected: ${error.message}`);}finally{e.target.value='';}
 });
 document.addEventListener('keydown',e=>{
   if($('page-editor').classList.contains('hidden'))return;
   if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))return;
   if((e.key==='Delete'||e.key==='Backspace')&&selectedId){e.preventDefault();removeGate(selectedId);}
   if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?redo():undo();}
   if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();redo();}
   if(e.key==='Escape'){selectedId=null;paletteSelection=null;updatePalette();render();}
 });
 window.addEventListener('hashchange',()=>{const page=location.hash==='#editor'?'editor':location.hash==='#measurement'?'measurement':'home';const el=$('page-'+page);if(el&&el.classList.contains('hidden'))route(page);});
 initScanPreview();
 route(location.hash==='#editor'?'editor':location.hash==='#measurement'?'measurement':'home');
}

// ---------------------------------------------------------------------------------
// Pulse sequence preview: qualitative visualization only, NOT a qudi pulse compiler.
// ---------------------------------------------------------------------------------
function previewEnvelope(u, mode){
 if(u<=0||u>=1)return 0;
 if(mode==='gauss'){const z=(u-.5)/.19;return Math.exp(-.5*z*z);}
 if(mode==='soft'){const edge=Math.min(u,1-u);return .5*(1+Math.tanh((edge-.12)/.042));}
 return 1;
}
function svgEscape(x){return String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');}
function pulseShapePath(x,baseline,width,height,mode){
 let d=`M ${x.toFixed(2)} ${baseline.toFixed(2)}`;
 // For a rectangular pulse the corners must be vertical, not a horizontal line at the peak.
 if(mode==='rect')return d+` L ${x.toFixed(2)} ${(baseline-height).toFixed(2)} L ${(x+width).toFixed(2)} ${(baseline-height).toFixed(2)} L ${(x+width).toFixed(2)} ${baseline.toFixed(2)}`;
 for(let k=0;k<=64;k++){
  const u=k/64, yy=baseline-height*previewEnvelope(u,mode);
  d+=` L ${(x+width*u).toFixed(2)} ${yy.toFixed(2)}`;
 }
 return d+` L ${(x+width).toFixed(2)} ${baseline.toFixed(2)}`;
}
function renderPulsePreview(){
 const root=$('pulse-svg-container');if(!root||!$('pulse-panel')?.open)return;
 const gates=[...circuit.gates].sort((a,b)=>a.col-b.col||a.row-b.row);
 if(!gates.length){root.innerHTML='<div class="pulse-placeholder">Add gates or load an example circuit to see illustrative pulses.</div>';return;}
 const cols=[...new Set(gates.map(g=>g.col))].sort((a,b)=>a-b);
 // Separate illustrative lanes for electron and each nuclear-spin wire.
 const lanes=Array.from({length:circuit.qubits},(_,i)=>({wire:i,y:83+i*92,color:i===0?'#51afa8':['#b295df','#e3ab62','#65addd','#cf8eab'][(i-1)%4]}));
 const H=lanes.at(-1).y+67,W=Math.max(620,150+cols.length*166),mode=$('pulse-envelope').value;
 let out=`<svg class="pulse-plot" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Illustrative per-qubit pulse envelopes"><defs><pattern id="ddrf-stripes" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><path d="M0 0V7" stroke="#b295df" stroke-opacity=".24" stroke-width="2"/></pattern></defs>`;
 lanes.forEach((lane,i)=>{
  out+=`<rect x="0" y="${lane.y-43}" width="${W}" height="${85}" class="pulse-lane"/><text x="14" y="${lane.y-16}" class="pulse-axis-label">${i===0?'MW · electron q₀':'RF · nuclear q'+String(i).replace(/[0-9]/g,d=>'₀₁₂₃₄₅₆₇₈₉'[+d])}</text><line x1="14" y1="${lane.y}" x2="${W-16}" y2="${lane.y}" class="pulse-baseline"/>`;
 });
 for(let i=0;i<cols.length;i++){
   const col=cols[i],items=gates.filter(g=>g.col===col),x=128+i*166;
   out+=`<rect x="${x-9}" y="27" width="143" height="${H-52}" rx="6" class="pulse-window"/><text x="${x+60}" y="17" text-anchor="middle" class="pulse-gate-caption">t${i+1}</text>`;
   for(const g of items){
    if(!['rx','ry','rz','ddrf'].includes(g.type)){
      const lane=lanes[g.target??g.row];out+=`<text x="${x+60}" y="${lane.y-19}" text-anchor="middle" class="pulse-none">${svgEscape(g.type.toUpperCase())} (logical)</text>`;continue;
    }
    const lane=lanes[g.type==='ddrf'?g.target:g.row],amplitude=Math.min(1,Math.max(.35,Math.abs(g.angle??PI/2)/PI));
    const x0=x+9,w=112,height=33*amplitude;
    const path=pulseShapePath(x0,lane.y,w,height,mode);
    out+=`<path d="${path}" fill="${lane.color}" fill-opacity=".18" stroke="${lane.color}" stroke-width="2.5" stroke-linejoin="round"/>`;
    if(g.type==='ddrf'){
      // Four illustrative electron echoes; real DDRF pulse count/phase/timing comes from squdi.
      const e=lanes[0];
      for(const frac of [.10,.34,.60,.84]){
        const pw=15,xx=x0+frac*w;
        const echo=pulseShapePath(xx,e.y,pw,27,mode);
        out+=`<path d="${echo}" fill="${e.color}" fill-opacity=".16" stroke="${e.color}" stroke-width="2"/>`;
      }
      out+=`<text x="${x+65}" y="${lane.y+27}" text-anchor="middle" class="pulse-hint">DDRF ${svgEscape(g.axis.toUpperCase())}, ${g.sign===-1?'∓':'±'}θ</text>`;
    }else out+=`<text x="${x+65}" y="${lane.y+27}" text-anchor="middle" class="pulse-hint">${svgEscape(g.type.toUpperCase())}</text>`;
   }
 }
 out+=`<text x="${W/2}" y="${H-10}" text-anchor="middle" class="pulse-axis-label">Conceptual slot order · equal widths are not physical durations</text></svg>`;
 root.innerHTML=out;
}

// ---------------------------------------------------------------------------------
// Synthetic confocal XY scan demonstration. No qudi, network hardware or scan output.
// ---------------------------------------------------------------------------------
let scanValues=null,scanN=64,scanExtent=5,scanCross={x:.5,y:.5};
let scanAnimation=null,scanDrawnRows=0,scanPeak=1,scanStarted=false;
function scanField(u,v,variant){
  const gauss=(x,y,s)=>Math.exp(-(x*x+y*y)/(2*s*s));
  let z=3400+16800*gauss(u-.36,v-.58,.085)+11800*gauss(u-.74,v-.30,.11);
  if(variant==='three')z+=8500*gauss(u-.23,v-.23,.065);
  // Deterministic texture / photon-count-like variation, not random experimental data.
  z+=530*Math.sin(113*u+55*v)*Math.cos(37*v-69*u)+250*Math.sin(149*v+11*u);
  return Math.max(0,z);
}
function scanColor(value){
 const stops=[[12,27,49],[24,74,103],[37,141,142],[114,190,127],[224,208,105],[252,239,185]];
 const k=Math.max(0,Math.min(4.999,(value/scanPeak)*5)),i=Math.min(4,Math.floor(k)),a=k-i;
 return stops[i].map((v,c)=>Math.round(v+(stops[i+1][c]-v)*a));
}
function generateScanData(){
 scanN=Number($('scan-resolution').value);scanExtent=Number($('scan-range').value);
 scanValues=new Float64Array(scanN*scanN);scanPeak=0;
 const variant=$('scan-sample').value;
 for(let y=0;y<scanN;y++)for(let x=0;x<scanN;x++){
   const val=scanField((x+.5)/scanN,(y+.5)/scanN,variant);
   scanValues[y*scanN+x]=val;scanPeak=Math.max(scanPeak,val);
 }
 $('scale-high').textContent=Math.round(scanPeak).toLocaleString('en-US');
 $('scale-low').textContent='0';scanDrawnRows=scanN;
 drawScan();updateScanCrosshair();
}
function drawScan(){
 const canvas=$('scan-canvas'),ctx=canvas.getContext('2d');if(!ctx||!scanValues)return;
 const pixels=ctx.createImageData(scanN,scanN);
 for(let y=0;y<scanN;y++)for(let x=0;x<scanN;x++){
   const k=(y*scanN+x)*4,visible=y<scanDrawnRows;
   const c=visible?scanColor(scanValues[y*scanN+x]):[19,37,48];
   for(let j=0;j<3;j++)pixels.data[k+j]=c[j];pixels.data[k+3]=255;
 }
 const off=document.createElement('canvas');off.width=scanN;off.height=scanN;off.getContext('2d').putImageData(pixels,0,0);
 ctx.clearRect(0,0,canvas.width,canvas.height);ctx.imageSmoothingEnabled=false;
 ctx.drawImage(off,0,0,canvas.width,canvas.height);
}
function profilePath(values,max){
 const left=32,right=445,top=17,bottom=146;
 let points=values.map((v,i)=>`${(left+(right-left)*i/Math.max(1,values.length-1)).toFixed(1)},${(bottom-(bottom-top)*v/max).toFixed(1)}`).join(' ');
 return `<path d="M${left} ${top}V${bottom}H${right}" class="profile-axes"/>`+
 `<path d="M${left} ${bottom-50}H${right}M${left} ${bottom-100}H${right}" class="profile-gridlines"/>`+
 `<polyline points="${points}" class="profile-curve"/>`+
 `<text x="${left}" y="167" class="profile-label">−${(scanExtent/2).toFixed(1)} µm</text><text x="${right}" y="167" text-anchor="end" class="profile-label">+${(scanExtent/2).toFixed(1)} µm</text>`+
 `<text x="${left+6}" y="${top+8}" class="profile-label">${Math.round(max).toLocaleString('en-US')} counts/s</text>`;
}
function updateScanCrosshair(){
 if(!scanValues)return;
 const ix=Math.max(0,Math.min(scanN-1,Math.round(scanCross.x*(scanN-1))));
 const iy=Math.max(0,Math.min(scanN-1,Math.round(scanCross.y*(scanN-1))));
 $('scan-crosshair-x').style.top=(scanCross.y*100)+'%';$('scan-crosshair-y').style.left=(scanCross.x*100)+'%';
 $('scan-x').textContent=((scanCross.x-.5)*scanExtent).toFixed(2)+' µm';
 $('scan-y').textContent=((.5-scanCross.y)*scanExtent).toFixed(2)+' µm';
 $('scan-count').textContent=Math.round(scanValues[iy*scanN+ix]).toLocaleString('en-US')+' /s';
 const xvals=Array.from({length:scanN},(_,i)=>scanValues[iy*scanN+i]);
 const yvals=Array.from({length:scanN},(_,i)=>scanValues[i*scanN+ix]);
 $('profile-x').innerHTML=profilePath(xvals,scanPeak);
 $('profile-y').innerHTML=profilePath(yvals,scanPeak);
}
function stopScan(){if(scanAnimation!=null){clearInterval(scanAnimation);scanAnimation=null;}
 scanStarted=false;$('scan-start').disabled=false;$('scan-stop').disabled=true;}
function startScan(){
 if(scanStarted)return;stopScan();generateScanData();scanDrawnRows=0;drawScan();scanStarted=true;
 $('scan-start').disabled=true;$('scan-stop').disabled=false;$('scan-status').textContent='Simulating XY scan…';
 const demoInterval=Math.max(18,Math.min(100,Number($('scan-dwell').value)*9));
 scanAnimation=setInterval(()=>{
   scanDrawnRows=Math.min(scanN,scanDrawnRows+Math.max(1,Math.ceil(scanN/28)));
   drawScan();$('scan-progress-fill').style.width=(100*scanDrawnRows/scanN)+'%';
   if(scanDrawnRows>=scanN){stopScan();$('scan-status').textContent='Simulation completed · generated data';}
 },demoInterval);
}
function ensureScan(){if(!scanValues)generateScanData();}
function initScanPreview(){
 $('scan-start').onclick=startScan;
 $('scan-stop').onclick=()=>{stopScan();$('scan-status').textContent='Simulation stopped';};
 ['scan-resolution','scan-range','scan-sample'].forEach(id=>$(id).addEventListener('change',()=>{stopScan();generateScanData();$('scan-progress-fill').style.width='100%';$('scan-status').textContent='Ready · generated sample';}));
 $('scan-map').addEventListener('click',e=>{const r=$('scan-map').getBoundingClientRect();scanCross={x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))};updateScanCrosshair();});
}

document.addEventListener('DOMContentLoaded',init);

// Code preview only: same editable circuit, no connection to hardware.
let measurementCodeRequest=0;
async function refreshMeasurementCode(){
 const seq=++measurementCodeRequest, el=$('measurement-code');if(!el)return;
 const fmt=$('format').value;
 $('measurement-code-format').textContent={qasm:'OpenQASM 2.0',qiskit:'Python · Qiskit',mcas:'Python · MCAS'}[fmt];
 el.textContent='Generating…';
 try{
  const clean={...circuit,gates:circuit.gates.map(({id,...g})=>g)};
  const resp=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({circuit:clean,format:fmt})});
  const result=await resp.json();if(seq!==measurementCodeRequest)return;
  el.innerHTML=resp.ok?highlightCode(result.code,fmt):svgEscape(result.error||'Export unavailable');
 }catch(e){if(seq===measurementCodeRequest)el.textContent='Export server unavailable';}
}
