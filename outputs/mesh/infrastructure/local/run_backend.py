"""Owned loopback API/Redis runtime, actual configured backend; no auth substitutions."""
import json,os,secrets,subprocess,sys,time
from uuid import UUID
from pathlib import Path
from urllib.parse import quote
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[4]
runtime=root/"work/final-integration-runtime";runtime.mkdir(exist_ok=True)
if (runtime/"owned-processes.json").exists():raise SystemExit("An owned backend runtime is already registered; stop it before starting another.")
stop=runtime/"stop";stop.unlink(missing_ok=True)
password=secrets.token_urlsafe(40)
config=runtime/"redis.private.conf"
config.write_text('bind 127.0.0.1\nport 6388\nprotected-mode yes\nrequirepass '+password+'\nsave ""\nappendonly no\n',encoding="utf-8")
env={**os.environ,**{k:v for k,v in dotenv_values(root/"outputs/mesh/.env",interpolate=False).items() if v is not None},"REDIS_URL":"redis://:"+quote(password,safe="")+"@127.0.0.1:6388/0","PYTHONPATH":str(root/"outputs/mesh/backend"),"TEST_MODE":"false"}
temporary=runtime/("tmp-"+secrets.token_hex(6));temporary.mkdir()
env.update(TEMP=str(temporary),TMP=str(temporary))
mail_scopes=runtime/"mail-organizations.json"
organizations=json.loads(mail_scopes.read_text()) if mail_scopes.exists() else []
if not isinstance(organizations,list) or len(organizations)>20:raise SystemExit("Invalid explicit mail worker scopes")
organizations=list(dict.fromkeys(str(UUID(value)) for value in organizations))
children=[];logs=[];failed=False
try:
 commands=[("redis",[str(root/"work/tools/redis/Redis-8.10.2-Windows-x64-msys2/redis-server.exe"),config.name]),("api",[sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000","--no-access-log"])]
 commands.extend(("mail-"+organization,[sys.executable,"-m","app.worker","--organization",organization,"--mail-only"]) for organization in organizations)
 for name,args in commands:
  log=(runtime/(name+".private.log")).open("w",encoding="utf-8");logs.append(log)
  child=subprocess.Popen(args,cwd=runtime if name=="redis" else root/"outputs/mesh",env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);children.append(child)
  time.sleep(1)
  if child.poll() is not None and not name.startswith("mail-"):raise RuntimeError("Owned "+name+" process did not start")
 from redis import Redis
 if Redis.from_url(env["REDIS_URL"],socket_timeout=3).ping() is not True:raise RuntimeError("Owned Redis readiness failed")
 (runtime/"owned-processes.json").write_text(json.dumps({"pids":[c.pid for c in children],"loopback_only":True,"test_auth_substitutions":False,"mail_worker_organizations":organizations}),encoding="utf-8")
 print("Actual configured backend and authenticated loopback Redis started; no fixture authentication.",flush=True)
 retry_after={}
 deadline=time.monotonic()+43200
 while not stop.exists() and time.monotonic()<deadline:
  if any(c.poll() is not None for c in children[:2]):raise RuntimeError("An owned core runtime process exited")
  for index in range(2,len(children)):
   if children[index].poll() is not None and time.monotonic()>=retry_after.get(index,0):
    retry_after[index]=time.monotonic()+30
    children[index]=subprocess.Popen(commands[index][1],cwd=root/"outputs/mesh",env=env,stdin=subprocess.DEVNULL,stdout=logs[index],stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    (runtime/"owned-processes.json").write_text(json.dumps({"pids":[c.pid for c in children],"loopback_only":True,"test_auth_substitutions":False,"mail_worker_organizations":organizations}),encoding="utf-8")
  time.sleep(1)
except Exception as error:
 failed=True
 print("Actual backend runtime unavailable: "+type(error).__name__+". No synthetic fallback was started.",flush=True)
finally:
 for child in reversed(children):
  if child.poll() is None:child.terminate();child.wait(timeout=20)
 for log in logs:log.close()
 (runtime/"owned-processes.json").unlink(missing_ok=True)
 config.unlink(missing_ok=True)

if failed:raise SystemExit(1)
