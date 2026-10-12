import json
import shutil
import subprocess
from pathlib import Path

def test_official_callable_platform_binding_and_private_rpc(tmp_path):
    """Contract fixture has no app.imessage; the SDK exports imessage(app)."""
    source=(Path(__file__).resolve().parent.parent/'integrations/photon/bridge.mjs').read_text(encoding='utf-8')
    source=source.replace("import {Spectrum} from '@spectrum-ts/core';", "const Spectrum=async()=>({messages:(async function*(){})(),stop:async()=>{}});")
    source=source.replace("import {imessage} from '@spectrum-ts/imessage';", "const imessage=app=>({space:{create:async phone=>({send:async text=>({id:phone==='recipient'&&text==='reminder'?'sent-id':null})})},getMessage:async()=>({isDelivered:true})});imessage.config=()=>({});")
    script=tmp_path/'bridge.mjs';script.write_text(source,encoding='utf-8')
    requests=[{'id':'start','action':'start','project_id':'test','project_secret':'fictional-secret'}, {'id':'send','action':'send','phone':'recipient','text':'reminder'}, {'id':'receipt','action':'message','phone':'recipient','guid':'sent-id'}, {'id':'invalid','action':'invalid'}]
    result=subprocess.run([shutil.which('node'),str(script)],input=''.join(json.dumps(r)+'\n' for r in requests),capture_output=True,text=True,timeout=10)
    assert result.returncode==0
    responses=[json.loads(line) for line in result.stdout.splitlines()]
    assert responses==[{'id':'start','ok':True},{'id':'send','ok':True,'sid':'sent-id'},{'id':'receipt','ok':True,'delivered':True},{'id':'invalid','ok':False}]
    assert 'fictional-secret' not in result.stdout+result.stderr
