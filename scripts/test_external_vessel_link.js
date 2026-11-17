const assert=require('node:assert/strict'); const nodes={};const document={getElementById:id=>nodes[id]??=( {hidden:true,value:'',textContent:'',addEventListener(type,fn){this[type]=fn;},removeAttribute(key){delete this[key];}})};
const template=require('node:fs').readFileSync('optimization/templates/optimization/mvp.html','utf8');
eval(template.slice(template.indexOf('  const externalVesselForm='),template.indexOf('  const vfForm=')));
const form=nodes['external-vessel-form'], input=nodes['external-vessel-imo'],link=nodes['external-vessel-link'];
function run(value){input.value=value;form.submit({preventDefault(){}});}
for(const bad of ['','123','9320478','93204770','9320477&x=1','javascript:alert(1)','0000000','９３２０４７７']){run(bad);assert.equal(link.hidden,true);assert.equal(link.href,undefined);}
run('9320477');assert.equal(link.href,'https://www.vesselfinder.com/?imo=9320477');assert.equal(link.hidden,false);
input.value='9320478';input.input();assert.equal(link.hidden,true);assert.equal(link.href,undefined);
run(' 9320477 ');assert.equal(link.href,'https://www.vesselfinder.com/?imo=9320477');
console.log('External link format/checksum, fixed host, invalid input, stale link reset passed');
