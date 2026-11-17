const assert=require('node:assert/strict'),fs=require('node:fs');
function node(){return {hidden:true,value:'',textContent:'',children:[],addEventListener(type,fn){const previous=this[type];this[type]=(...args)=>{if(previous)previous(...args);return fn(...args);};},removeAttribute(key){delete this[key];},replaceChildren(){this.children=[];},append(...children){this.children.push(...children);},requestSubmit(){this.submit({preventDefault(){}});}};}
const nodes={},document={getElementById:id=>nodes[id]??=node(),createElement:node};
class FormData{constructor(){}};
let response={ok:true,json:async()=>({results:[],notice:'Incomplete directory.'})};
let fetch=async()=>response;
const template=fs.readFileSync('optimization/templates/optimization/mvp.html','utf8');
eval(template.slice(template.indexOf('  const externalVesselForm='),template.indexOf('  const vfForm=')));
const form=nodes['ship-directory-form'],results=nodes['ship-directory-results'],status=nodes['ship-directory-status'],imo=nodes['external-vessel-imo'],link=nodes['external-vessel-link'];
const submit=()=>form.submit({preventDefault(){}});
(async()=>{
 await submit();assert.match(status.textContent,/No checksum-valid/);
 response={ok:true,json:async()=>({results:[{id:'Q11082034',name:'<img src=x onerror=bad()>',description:'Synthetic text',imo:'9320477'},{id:'evil',name:'bad',imo:'9320477'},{id:'Q2',name:'bad checksum',imo:'9320478'}],notice:'Incomplete.'})};
 await submit();assert.equal(results.children.length,1);assert.equal(link.href,undefined);
 const button=results.children[0].children[0];assert.match(button.textContent,/<img/);button.click();assert.equal(imo.value,'9320477');assert.equal(link.href,'https://www.vesselfinder.com/?imo=9320477');assert.match(status.textContent,/No position has been fetched/);
 form.input();assert.equal(results.children.length,0);assert.equal(link.href,undefined);assert.equal(imo.value,'');
 response={ok:false,status:429,json:async()=>({error:{message:'Try later.'}})};await submit();assert.equal(status.textContent,'Try later.');
 response={ok:false,status:403,json:async()=>{throw new Error('html');}};await submit();assert.match(status.textContent,/Security check/);
 let resolve;fetch=()=>new Promise(r=>resolve=r);const pending=submit();form.input();resolve({ok:true,json:async()=>({results:[{id:'Q11082034',name:'Old',imo:'9320477'}],notice:'Old'})});await pending;assert.equal(results.children.length,0);assert.equal(status.textContent,'');
 console.log('Directory empty, disambiguation, safe text/links, invalid identity, selection, failures and stale response tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
