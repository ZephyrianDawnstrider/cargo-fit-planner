(() => {
'use strict';
const enabled=document.getElementById('allowances-enabled'),hidden=document.getElementById('allowances-json'),feedback=document.getElementById('allowance-feedback');
const fields={dimension_tolerance_mm:'tolerance',horizontal_gap_mm:'gap',wall_clearance_mm:'wall',roof_clearance_mm:'roof',door_clearance_mm:'door'};
try{if(hidden.value){const cfg=JSON.parse(hidden.value);enabled.checked=true;for(const [key,id] of Object.entries(fields))document.getElementById('allowance-'+id).value=cfg[key]??0;document.getElementById('allowance-source').value=cfg.source_reference||'';}}catch(_){feedback.textContent='Previous allowances could not be restored; re-enter them before packing.';}
document.getElementById('cargo-form').addEventListener('submit',event=>{
 feedback.textContent='';if(!enabled.checked){hidden.value='';return;}
 try{const cfg={};for(const [key,id] of Object.entries(fields)){const raw=document.getElementById('allowance-'+id).value;if(!raw.trim())throw new Error('Enter all five allowances, including explicit zeros.');const value=Number(raw);if(!Number.isInteger(value)||value<0||value>100)throw new Error('Allowances must be whole millimetres between 0 and 100.');cfg[key]=value;}cfg.source_reference=document.getElementById('allowance-source').value.trim();if(Object.values(fields).some(id=>Number(document.getElementById('allowance-'+id).value)>0)&&!cfg.source_reference)throw new Error('Identify the measurement or handling source for positive allowances.');hidden.value=JSON.stringify(cfg);}
 catch(error){event.preventDefault();feedback.textContent=error.message;}
});
})();
