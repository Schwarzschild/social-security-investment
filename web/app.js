'use strict';
const money = value => new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',maximumFractionDigits:2}).format(value);
const percent = value => `${(100 * value).toFixed(2)}%`;
function futureValue(payment, months, r_annual) {
  const r_month = Math.expm1(Math.log1p(r_annual) / 12);
  const value = r_month === 0 ? payment * months : payment * (1 + r_month) * Math.expm1(months * Math.log1p(r_month)) / r_month;
  if (!Number.isFinite(value)) throw new Error('These inputs exceed numerical limits. Reduce the PIA, return, or duration.');
  return value;
}
function calculate(config, age, r_annual) {
  const months = (config.end - age) * 12;
  const payment = config.pia * (1 + .08 * (age - 67));
  const netPayment = payment * (1 - config.benefitTax);
  const principal = netPayment * months;
  const invested = futureValue(netPayment, months, r_annual);
  const gainsTax = Math.max(invested - principal, 0) * config.gainsTax;
  const result = {months,payment,netPayment,principal,growth:invested-principal,gainsTax,net:invested-gainsTax,gross:futureValue(payment,months,r_annual)};
  if (!Object.values(result).every(Number.isFinite)) throw new Error('These inputs exceed numerical limits.');
  return result;
}
function crossing(config, taxed) {
  if (config.start === 70) return null;
  const delta = rate => { const a=calculate(config,config.start,rate),b=calculate(config,70,rate); return taxed ? a.net-b.net : a.gross-b.gross; };
  let low=.035, high=.20, first=delta(low), last=delta(high);
  if (first === 0 && last === 0) return null;
  if (first === 0) return low;
  if (last === 0) return high;
  if (Math.sign(first) === Math.sign(last)) return null;
  for(let k=0;k<65;k++) { const mid=(low+high)/2, value=delta(mid); if(value===0)return mid; if(Math.sign(value)===Math.sign(first)){low=mid;first=value;}else high=mid; }
  return (low+high)/2;
}
function table(headers, rows) {
  return `<table><thead><tr>${headers.map(x=>`<th scope="col">${x}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map((x,k)=>k===0?`<th scope="row">${x}</th>`:`<td>${x}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}
function chart(title, series, root, delta) {
  const width=640,height=340,left=90,right=20,top=32,bottom=55;
  let min=Math.min(0,...series.flatMap(s=>s.values)),max=Math.max(0,...series.flatMap(s=>s.values));
  if(min===max)max=min+1;
  const padding=(max-min)*.06;max+=padding;if(min<0)min-=padding;
  const x=rate=>left+(rate-.035)/.165*(width-left-right),y=value=>top+(max-value)/(max-min)*(height-top-bottom);
  let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${title}"><title>${title}</title>`;
  for(let k=0;k<=4;k++){const v=min+(max-min)*k/4;svg+=`<line x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}" stroke="#dce5eb"/><text x="${left-8}" y="${y(v)+4}" text-anchor="end" font-size="12" fill="#526777">${new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:1}).format(v)}</text>`;}
  for(const rate of [.035,.05,.10,.15,.20])svg+=`<text x="${x(rate)}" y="${height-29}" text-anchor="middle" font-size="12" fill="#526777">${percent(rate)}</text>`;
  if(delta)svg+=`<line x1="${left}" x2="${width-right}" y1="${y(0)}" y2="${y(0)}" stroke="#536570"/>`;
  for(const s of series)svg+=`<path d="${s.values.map((v,k)=>`${k?'L':'M'}${x(.035+.165*k/600).toFixed(2)},${y(v).toFixed(2)}`).join(' ')}" fill="none" stroke="${s.color}" stroke-width="2.5"/>`;
  if(root!==null)svg+=`<line x1="${x(root)}" x2="${x(root)}" y1="${top}" y2="${height-bottom}" stroke="#536570" stroke-dasharray="5 4"/><text x="${x(root)+5}" y="20" font-size="12">Equal FV: ${percent(root)}</text>`;
  svg+=`<text x="${(left+width-right)/2}" y="${height-4}" text-anchor="middle" font-size="13">Investment Rate (effective annual)</text></svg>`;
  return `<div class="chart"><h3>${title}</h3>${svg}<p>${series.map(s=>`<span style="color:${s.color}">━ ${s.name}</span>`).join(' &nbsp; ')}</p><p>601 returns from 3.50% to 20.00%. Values in dollars; linear scale.</p></div>`;
}
function readForm(form) {
  const config={};
  for(const [key,raw] of new FormData(form)){if(raw.trim()===''||!Number.isFinite(Number(raw)))throw new Error('Enter a finite number in every field.');config[key]=Number(raw);}
  if(config.pia<=0||![67,68,69,70].includes(config.start)||!Number.isInteger(config.end)||config.end<=70||config.end>150||config.annual<=-100)throw new Error('Use a positive PIA, start age 67–70, whole end age 71–150, and annual return greater than −100%.');
  const taxes=['fedShare','fedIncome','stateShare','stateIncome','localIncome','fedGains','niit','stateGains','localGains','surtax'];
  if(taxes.some(key=>config[key]<0||config[key]>100))throw new Error('Each tax percentage must be between 0% and 100%.');
  config.benefitTax=(config.fedShare*config.fedIncome+config.stateShare*(config.stateIncome+config.localIncome))/10000;
  config.gainsTax=taxes.slice(5).reduce((sum,key)=>sum+config[key],0)/100;
  if(config.benefitTax>1||config.gainsTax>1)throw new Error('Combined benefit and capital-gains tax rates must each be at most 100%.');
  config.annual/=100;return config;
}
function render(config) {
  const a=calculate(config,config.start,config.annual),b=calculate(config,70,config.annual);
  const roots=[crossing(config,false),crossing(config,true)];
  const samples=Array.from({length:601},(_,k)=>{const rate=.035+.165*k/600;return [calculate(config,config.start,rate),calculate(config,70,rate)];});
  const rows=[['Gross monthly benefit','payment'],['Net monthly investment','netPayment'],['Net contributions (cost basis)','principal'],['Growth before endpoint tax','growth'],['Endpoint tax on positive growth','gainsTax'],['Before-tax future value','gross'],['After-tax future value','net']].map(([label,key])=>[label,money(a[key]),money(b[key])]);
  rows.unshift(['Monthly payments',a.months,b.months]);
  const rates=[...new Set([.05,.10,.15,.20,config.annual])].sort((a,b)=>a-b);
  const comparison=rates.map(rate=>{const first=calculate(config,config.start,rate),second=calculate(config,70,rate);return [percent(rate)+(rate===config.annual?' (selected)':''),money(first.gross),money(second.gross),money(first.gross-second.gross),money(first.net),money(second.net),money(first.net-second.net),second.net===0?'Undefined':(first.net/second.net).toFixed(4)];});
  const charts=[['Future values versus annual investment rate of return',false,false],['Delta versus annual investment rate of return.',false,true],['Tax adjusted future values versus annual investment rate of return',true,false],['Tax adjusted delta versus annual investment rate of return.',true,true]].map(([title,taxed,delta])=>{const key=taxed?'net':'gross';const series=delta?[{name:`Delta: age ${config.start} minus age 70`,color:'#146b78',values:samples.map(pair=>pair[0][key]-pair[1][key])}]:[0,1].map(index=>({name:`FV at start age ${index?70:config.start}`,color:index?'#c26324':'#146b78',values:samples.map(pair=>pair[index][key])}));return chart(title,series,roots[taxed?1:0],delta);}).join('');
  document.getElementById('summary').textContent=`Start at ${config.start} versus 70, valued at age ${config.end}. Annual return: ${percent(config.annual)}. Benefit tax: ${percent(config.benefitTax)}; tax on positive growth: ${percent(config.gainsTax)}.`;
  document.getElementById('cards').innerHTML=[['After tax · start '+config.start,a.net],['After tax · start 70',b.net],['After-tax delta',a.net-b.net]].map(([label,value])=>`<div class="card">${label}<strong>${money(value)}</strong></div>`).join('');
  document.getElementById('details').innerHTML=table(['Measure',`Start ${config.start}`,'Start 70'],rows);
  document.getElementById('comparison').innerHTML=table(['Annual return',`Before tax ${config.start}`,'Before tax 70','Before-tax delta',`After tax ${config.start}`,'After tax 70','After-tax delta',`${config.start}:70 Ratio`],comparison);
  document.getElementById('crossing').textContent=config.start===70?'Identical strategies: values match at every return.':(config.benefitTax===1?'After-tax streams are both zero at every return. ':'')+roots.map((root,k)=>`${k?'After':'Before'}-tax chart crossing: ${root===null?'no unique crossing in 3.50%–20.00%':percent(root)}.`).join(' ')+' Crossings are searched only within chart bounds; this says nothing about solutions elsewhere.';
  document.getElementById('charts').innerHTML=charts;
}
if(typeof document!=='undefined') {
  const form=document.getElementById('calculator');
  function update(){const error=document.getElementById('error');try{render(readForm(form));error.hidden=true;document.getElementById('results').hidden=false;}catch(e){error.textContent=e.message;error.hidden=false;document.getElementById('results').hidden=true;}}
  form.addEventListener('submit',event=>{event.preventDefault();update();});
  form.addEventListener('reset',()=>setTimeout(update,0));update();
}
if(typeof module!=='undefined')module.exports={futureValue,calculate,crossing};
