"""Loopback-only browser-test fixture; never used by the user preview launcher.

Uses the real MESH routers and persistence with an isolated SQLite test database.
Only identity-provider verification is explicitly substituted; no hosted account,
database, CAPTCHA, email or AWS success is represented by these tests.
"""
import os
import sys
from pathlib import Path
from uuid import uuid4

root=Path(__file__).resolve().parents[3]
keep=os.environ.get('MESH_KEEP_LOCAL_SANDBOX')=='true'
database=root/'work/mesh-preview-runtime/sandbox.db' if keep else root/'work'/('mesh-browser-test-'+uuid4().hex+'.db')
database.parent.mkdir(parents=True,exist_ok=True)
os.environ.update(TEST_MODE='true',ENVIRONMENT='development',DATABASE_URL='sqlite:///'+database.as_posix(),REDIS_URL='redis://127.0.0.1:6387/15',SUPABASE_URL='https://fixture.invalid',SUPABASE_ANON_KEY='fixture-public-key',AUTH_RATE_SECRET='browser-fixture-only-protection-key-123456789',REQUIRE_PRIVILEGED_MFA='false')
os.environ.update(SCIM_BINDINGS='{}',AWS_ROLE_BINDINGS='{}',AWS_BILLING_ROLE_BINDINGS='{}',GITHUB_INSTALLATIONS='{}',SUPABASE_STORAGE_KEY='',CLAMAV_HOST='',DOCUMENT_OCR_ENABLED='false',AI_PROVIDER='local',AI_ALLOW_EXTERNAL='false',AI_URL='',AI_API_KEY='',SMTP_HOST='')
sys.path.insert(0,str(root/'outputs/mesh/backend'))
import uvicorn
from fastapi import Header, HTTPException
from sqlalchemy import event
from app.auth import Identity,identity
from app.core.db import Base,SessionFactory,engine
from app.main import app
import logging
logging.getLogger("mesh").setLevel(logging.ERROR)
from app.identity_provider import SupabaseAuth,Tokens
from app.models import Employee,Membership,Organization

ORG='11111111-1111-4111-8111-111111111111'
FOREIGN='22222222-2222-4222-8222-222222222222'
roles=['owner','hr','senior_developer','junior_developer','security_analyst']
users={role:f'aaaaaaaa-aaaa-4aaa-8aaa-{index+1:012d}' for index,role in enumerate(roles)}
@event.listens_for(engine,'connect')
def foreign_keys(connection,_):connection.execute('PRAGMA foreign_keys=ON')
import atexit

def cleanup_owned_database():
    if not keep:
        engine.dispose()
        database.unlink(missing_ok=True)
atexit.register(cleanup_owned_database)
Base.metadata.create_all(engine)
with SessionFactory() as db:
    existing=db.get(Organization,ORG)
    if existing:
        assert existing.name=='Synthetic browser test', 'Unrecognized sandbox database'
    else:
        db.add_all([Organization(id=ORG,name='Synthetic browser test'),Organization(id=FOREIGN,name='Separate browser-test tenant')]);db.flush()
        for index,(role,user) in enumerate(users.items()):
            db.add(Membership(organization_id=ORG,user_id=user,email=role+'@example.invalid',role=role))
        db.flush()
        for index,(role,user) in enumerate(users.items()):
            db.add(Employee(id=f'bbbbbbbb-bbbb-4bbb-8bbb-{index+1:012d}',organization_id=ORG,user_id=user,name='Fixture '+role,department='Engineering',status='active',verification_status='pending'))
        db.commit()
# Second tenant exists only in the disposable local test database.
users["foreign_senior"]="cccccccc-cccc-4ccc-8ccc-000000000001"
with SessionFactory() as db:
    db.add(Membership(organization_id=FOREIGN,user_id=users["foreign_senior"],email="foreign_senior@example.invalid",role="senior_developer"))
    db.flush()
    db.add(Employee(id="dddddddd-dddd-4ddd-8ddd-000000000001",organization_id=FOREIGN,user_id=users["foreign_senior"],name="Foreign fixture developer",department="Engineering",status="active",verification_status="pending"))
    db.commit()

def tokens(role):return Tokens(access_token='fixture-only-'+role,refresh_token='fixture-refresh-'+role,token_type='bearer',expires_in=3600)
def login(self,data):
    if data.email=='chunked@example.invalid' and data.password.get_secret_value()=='fixture-password-only':
        return Tokens(access_token='fixture-only-owner:'+('p'*6000),refresh_token='fixture-refresh-owner',token_type='bearer',expires_in=3600)
    role=data.email.split('@')[0]
    if role not in users or data.password.get_secret_value()!='fixture-password-only':raise HTTPException(401,'Fixture credentials rejected')
    return tokens(role)
def refresh(self,data):
    role=data.refresh_token.get_secret_value().removeprefix('fixture-refresh-')
    if role not in users:raise HTTPException(401,'Fixture session rejected')
    return tokens(role)
def fixture_identity(authorization: str | None = Header(default=None)):
    role=(authorization or '').removeprefix('Bearer fixture-only-').split(':',1)[0]
    if role not in users:raise HTTPException(401,'Fixture identity rejected')
    return Identity(users[role],role+'@example.invalid')
SupabaseAuth.login=login
SupabaseAuth.refresh=refresh
SupabaseAuth.request=lambda self,*a,**kw:{}
app.dependency_overrides[identity]=fixture_identity
import threading
stop_file=root/"work/final-integration-test.stop"
stop_file.unlink(missing_ok=True)
done=threading.Event()
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8011,access_log=False,log_level='warning'))
lease=threading.Timer(900,lambda:setattr(server,'should_exit',True));lease.daemon=True;lease.start()
def watch_stop():
    while not done.wait(0.2):
        if stop_file.exists():
            server.should_exit=True
            return
threading.Thread(target=watch_stop,daemon=True).start()
try:server.run()
finally:
    done.set()
    stop_file.unlink(missing_ok=True)
    lease.cancel()
    engine.dispose()
    if not keep:database.unlink(missing_ok=True)
