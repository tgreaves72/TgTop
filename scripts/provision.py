"""Initialize hosted service locally without exposing unauthenticated account setup."""
import getpass
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.store import Store
from app.paths import data_root
from app.security import hasher
s=Store(data_root())
if s.config('account'):
    print('Account already exists. No changes made.');sys.exit(1)
password=getpass.getpass('Create account password (12+ characters): ')
if len(password)<12 or password!=getpass.getpass('Confirm password: '):
    print('Passwords did not match or were too short.');sys.exit(1)
from app.accounts import Accounts
username=Accounts.username(input('Username: '))
s.set_config('account',{'username':username,'name':input('Name: ').strip() or 'Tyler','password_hash':hasher.hash(password)})
phone=input('Private phone number (optional, international format): ').strip()
if phone:
    import re
    if not re.fullmatch(r'\+[1-9]\d{7,14}',phone): raise ValueError('Invalid international format')
    s.set_config('settings',{'timezone':'America/New_York','quiet_start':'22:00','quiet_end':'07:00','channels':['desktop'],'phone':phone,'phone_verified':False})
for space in ('personal','school','work'):
    s.put('project',{'title':space.title(),'space':space,'ai_allowed':False,'description':''})
print('Private account provisioned. Verify phone ownership in Connections.')
