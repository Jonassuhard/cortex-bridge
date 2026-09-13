// Reproducible SVG-to-GIF documentation rendering, no account or network.
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {resolve, dirname} from "node:path";
import {spawn} from "node:child_process";
import {once} from "node:events";
import {chromium} from "../frontend/node_modules/playwright/index.mjs";

const root=resolve(dirname(fileURLToPath(import.meta.url)),"..");
const browser=await chromium.launch({headless:true});
try {
  for (const name of ["chat","mission","interfaces"]) {
    const svg=readFileSync(resolve(root,"docs/media",name+"-flow.svg"),"utf8");
    const page=await browser.newPage({viewport:{width:1000,height:390},deviceScaleFactor:1});
    await page.route("**/*",route=>route.abort());
    await page.setContent('<style>body{margin:0}</style>'+svg);
    const ffmpeg=spawn("ffmpeg",["-y","-loglevel","error","-f","image2pipe","-framerate","4","-i","pipe:0","-filter_complex","split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse","-loop","0","-map_metadata","-1",resolve(root,"docs/media",name+"-flow.gif")],{stdio:["pipe","ignore","pipe"]});
    let errors="";ffmpeg.stderr.on("data",chunk=>{errors+=chunk.toString()});
    const finished=once(ffmpeg,"close");
    ffmpeg.stdin.on("error",()=>{});
    for (let frame=0;frame<32;frame++) {
      const step=Math.floor(frame/4)%(name==="interfaces"?3:4);
      await page.locator(".node").evaluateAll((nodes,{step,name})=>nodes.forEach((node,i)=>node.classList.toggle("active",name==="interfaces"?(step===0?i<2:step===1?i===2:i===3):i===step)),{step,name});
      const pixels=await page.screenshot({type:"png"});
      if(!ffmpeg.stdin.write(pixels)) await once(ffmpeg.stdin,"drain");
    }
    ffmpeg.stdin.end();
    const [code]=await finished;
    if(code!==0) throw new Error("ffmpeg failed: "+errors);
    await page.close();
    process.stdout.write(name+": 32 frames, 1000x390, synthetic diagram\n");
  }
} finally {await browser.close()}
