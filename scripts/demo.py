"""Create isolated fictional data for UI QA; never runs on user storage."""
import os
from pathlib import Path
from datetime import datetime,timedelta,timezone
os.environ['TGTOP_DATA']=str(Path(__file__).resolve().parent.parent/'runtime'/'ui-sandbox')
os.environ['TGTOP_ORIGIN']='http://127.0.0.1:8766'
os.environ['TGTOP_PORT']='8766'
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.server import store,app
from app.security import hasher
if not store.config('account'):
    store.set_config('account',{'name':'Demo','password_hash':hasher.hash('demo-workspace-2026')})
    for name,space in [('Website refresh','personal'),('Fall semester','school'),('Client work','work')]:
        p=store.put('project',{'title':name,'space':space,'description':{'personal':'A thoughtful new home for my ideas.','school':'Assignments, study notes, and the next milestone.','work':'Deliverables and details that keep work moving.'}[space],'ai_allowed':space=='personal'})
        for i,title in enumerate({'personal':['Sketch the homepage structure','Collect design references','Review the launch checklist'],'school':['Finish chemistry assignment','Prepare discussion notes','Read the next chapter'],'work':['Send project update','Review feedback','Plan next week’s priorities']}[space]):
            due=(datetime.now(timezone.utc)+timedelta(hours=i*18-3)).isoformat()
            store.put('task',{'title':title,'project_id':p['id'],'priority':['high','normal','low'][i],'due_at':due,'status':'open'})
        store.put('note',{'title':'Project direction','project_id':p['id'],'body':'Keep the next step clear. Capture decisions here and link the context that matters.'})
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=8766,access_log=False,log_level='warning')
