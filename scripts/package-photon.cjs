const fs=require('fs');const path=require('path');const cp=require('child_process');
const root=path.resolve(__dirname,'..');const target=path.join(root,'runtime','photon-package');
fs.mkdirSync(target,{recursive:true});
const pkg=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
fs.writeFileSync(path.join(target,'package.json'),JSON.stringify({private:true,type:'module',dependencies:pkg.dependencies,overrides:pkg.overrides},null,2));
fs.copyFileSync(path.join(root,'integrations','photon','bridge.mjs'),path.join(target,'bridge.mjs'));
fs.copyFileSync(process.execPath,path.join(target,process.platform==='win32'?'node.exe':'node'));
const npm=process.platform==='win32'?'npm.cmd':'npm';
cp.execFileSync(npm,['install','--omit=dev','--ignore-scripts','--no-audit'],{cwd:target,stdio:'inherit',shell:process.platform==='win32'});
