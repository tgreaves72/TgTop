from datetime import datetime,timedelta
from test_workflows import env,project

def test_finite_weekly_series_dst_end_times_reminders_and_retry(env):
    s,c,_=env;p=project(c,True)
    s.store.set_config('settings',dict(s.settings(),calendar_sms=True))
    args={'project_id':p['id'],'title':'Philosophy book club meeting','due_at':'2026-10-19T19:00:00-04:00','end_at':'2026-10-19T20:15:00-04:00','count':4}
    result=s.execute_tool('create_task_series',args)
    assert len(result['tasks'])==4
    assert [t['due_at'] for t in result['tasks']]==['2026-10-19T23:00:00+00:00','2026-10-26T23:00:00+00:00','2026-11-03T00:00:00+00:00','2026-11-10T00:00:00+00:00']
    assert all(datetime.fromisoformat(t['end_at'])-datetime.fromisoformat(t['due_at'])==timedelta(minutes=75) for t in result['tasks'])
    assert len(s.store.list('reminder'))==4
    again=s.execute_tool('create_task_series',args)
    assert [t['id'] for t in again['tasks']]==[t['id'] for t in result['tasks']]
    assert len(s.store.list('task'))==4 and len(s.store.list('reminder'))==4
    utc=s.execute_tool('create_task_series',dict(args,due_at='2026-10-19T23:00:00Z',end_at='2026-10-20T00:15:00Z'))
    assert [t['id'] for t in utc['tasks']]==[t['id'] for t in result['tasks']]

def test_series_rejects_unauthorized_invalid_count_and_end(env):
    import pytest
    from fastapi import HTTPException
    s,c,_=env;p=project(c)
    args={'project_id':p['id'],'title':'Meeting','due_at':'2026-10-19T19:00:00-04:00','end_at':'2026-10-19T18:00:00-04:00','count':4}
    with pytest.raises(HTTPException):s.execute_tool('create_task_series',args)
    c.patch('/api/records/'+p['id'],json={'version':p['version'],'ai_allowed':True})
    with pytest.raises(HTTPException):s.execute_tool('create_task_series',args)
    with pytest.raises(HTTPException):s.execute_tool('create_task_series',dict(args,end_at=None,count=100))
    assert not s.store.list('task')
