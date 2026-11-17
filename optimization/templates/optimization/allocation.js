(() => {
'use strict';
const enabled=document.getElementById('allocation-enabled'),rows=document.getElementById('allocation-rows'),hidden=document.getElementById('allocation-json'),feedback=document.getElementById('allocation-feedback');
function add(customer={}){
 if(rows.children.length>=8){feedback.textContent='At most eight customer allocations.';return;}
 const card=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='Customer allocation';card.append(legend);card.className='profile-card';
 function field(label,key,value,type='text'){const l=document.createElement('label');l.textContent=label;const n=document.createElement('input');n.type=type;n.dataset.key=key;n.value=value;n.maxLength=key==='sources'?8000:64;if(type==='number'){n.min=0;n.max=100;n.step='.01';}l.append(n);card.append(l);return n;}
 field('Customer reference','id',customer.id||'');field('Source Item IDs (comma list, or JSON array for IDs containing commas)','sources',JSON.stringify(customer.source_item_ids||[]));field('Payload allocation %','weight_percent',customer.weight_percent??50,'number');field('Volume allocation %','volume_percent',customer.volume_percent??50,'number');
 const l=document.createElement('label');l.textContent='Physical reservation';const select=document.createElement('select');select.dataset.key='region';
 for(const [value,label] of [['','Shared space (quota only)'],...['x','y','z'].flatMap(axis=>[2,3,4].flatMap(parts=>Array.from({length:parts},(_,index)=>[`${axis}:${parts}:${index}`,`${axis.toUpperCase()} ${axis==='x'?'length':axis==='y'?'width':'height'} · segment ${index+1} of ${parts}`])))]){const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option);}
 const r=customer.region;select.value=r?`${r.axis}:${r.parts}:${r.index}`:'';l.append(select);card.append(l);
 const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent='Remove allocation';remove.addEventListener('click',()=>card.remove());card.append(remove);rows.append(card);
}
document.getElementById('allocation-add').addEventListener('click',()=>add());
try{if(hidden.value){const cfg=JSON.parse(hidden.value);if(Array.isArray(cfg.customers)){enabled.checked=true;cfg.customers.forEach(add);}}}catch(_){feedback.textContent='Previous allocation data could not be restored. Re-enter it before packing.';}
if(!rows.children.length)add();
document.getElementById('cargo-form').addEventListener('submit',event=>{
 feedback.textContent='';if(!enabled.checked){hidden.value='';return;}
 try{const customers=Array.from(rows.children).map(card=>{const value=k=>card.querySelector(`[data-key="${k}"]`).value.trim();if(!value('id')||!value('sources')||!value('weight_percent')||!value('volume_percent'))throw new Error('Complete customer reference, source IDs and both percentages.');const region=value('region').split(':');return{id:value('id'),source_item_ids:value('sources').startsWith('[')?JSON.parse(value('sources')):value('sources').split(',').map(x=>x.trim()).filter(Boolean),weight_percent:Number(value('weight_percent')),volume_percent:Number(value('volume_percent')),region:region[0]?{axis:region[0],parts:Number(region[1]),index:Number(region[2])}:null};});if(!customers.length)throw new Error('Add at least one customer.');hidden.value=JSON.stringify({customers});}
 catch(error){event.preventDefault();feedback.textContent=error.message;}
});
})();
