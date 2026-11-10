import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire('/tmp/cs3263-report-browser/package.json');
const {chromium}=require('playwright-core');
const out=new URL('./figures/',import.meta.url).pathname;
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
for(const [name,height] of [['architecture',735],['task',500]]){
 const page=await browser.newPage({viewport:{width:1200,height},deviceScaleFactor:2});
 const svg=await fs.readFile(out+name+'.svg','utf8');
 await page.setContent('<html><head><style>html,body{margin:0;padding:0;width:1200px;height:'+height+'px}svg{display:block}</style></head><body>'+svg+'</body></html>');
 await page.pdf({path:out+name+'.pdf',width:'1200px',height:height+'px',printBackground:true,margin:{top:0,right:0,bottom:0,left:0}});
 await page.screenshot({path:out+name+'.png'});
 await page.close();
}
await browser.close();
