import { createInterface } from 'node:readline';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const kaynak=process.env.OPENCODE_SOURCE || join(homedir(),'Documents','opencode2');
const {estimate}=await import(pathToFileURL(join(kaynak,'packages/core/src/util/token.ts')).href);
for await(const satir of createInterface({input:process.stdin})){
 try{process.stdout.write(String(estimate(JSON.parse(satir)))+'\n');}
 catch{process.stdout.write('-1\n');}
}
