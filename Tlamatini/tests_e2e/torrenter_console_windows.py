# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1

"""Observe real console windows, including transient SHOW events, from a visible coordinator."""
import ctypes,json,subprocess,sys,time
from ctypes import wintypes
from pathlib import Path
import psutil
u=ctypes.WinDLL("user32",use_last_error=True)
u.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
u.IsWindowVisible.argtypes=[wintypes.HWND]
u.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
callback_type=ctypes.WINFUNCTYPE(None,ctypes.c_void_p,wintypes.DWORD,wintypes.HWND,wintypes.LONG,wintypes.LONG,wintypes.DWORD,wintypes.DWORD)
u.SetWinEventHook.argtypes=[wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,callback_type,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD]
u.SetWinEventHook.restype=ctypes.c_void_p
u.UnhookWinEvent.argtypes=[ctypes.c_void_p]
enum_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
u.EnumWindows.argtypes=[enum_type,wintypes.LPARAM]
# Product callers are intentionally windowless. The test coordinator is visible.
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.GetConsoleWindow.restype=wintypes.HWND
u.GetForegroundWindow.restype=wintypes.HWND
console=k.GetConsoleWindow()
if not console or not u.IsWindowVisible(console) or console!=u.GetForegroundWindow():
    raise SystemExit('Run this check in a visible foreground PowerShell console and keep it open afterward.')
events=[]
def observe(hwnd):
    if not u.IsWindowVisible(hwnd):return
    pid=wintypes.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    name=ctypes.create_unicode_buffer(256);u.GetClassNameW(hwnd,name,256)
    events.append((pid.value,name.value))
@callback_type
def shown(hook,event,hwnd,obj,child,thread,ms):
    if obj==0 and child==0:observe(hwnd)
@enum_type
def enumerated(hwnd,_):
    observe(hwnd);return True
hook=u.SetWinEventHook(0x8002,0x8002,None,shown,0,0,0)
assert hook,ctypes.get_last_error()
def pump():
    message=wintypes.MSG()
    while u.PeekMessageW(ctypes.byref(message),None,0,0,1):
        u.TranslateMessage(ctypes.byref(message));u.DispatchMessageW(ctypes.byref(message))
def run(mode):
    events.clear()
    root=Path(__file__).resolve().parents[1]
    code="import sys,json;sys.path.insert(0,"+repr(str(root))+");from agent.agents.torrenter import client\n"
    if mode == "old_client":
        code+="original=client.subprocess.run\ndef baseline(*args,**kw):\n kw['creationflags']=0\n return original(*args,**kw)\nclient.subprocess.run=baseline\n"
    if mode == "calibration":
        code += "import subprocess; subprocess.run([sys.executable.replace('pythonw.exe','python.exe'),'-c','import time; time.sleep(.4)'],check=True)"
    else:
        code+="for n in range("+("1" if mode=="old_client" else "20")+"): print(json.dumps({'request':n+1,'reply':client.native({'op':'status'}).get('provider')}),flush=True)\n"
    child=subprocess.Popen([str(Path(sys.executable).with_name("pythonw.exe")),"-u","-c",code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    processes={child.pid:{"name":"pythonw.exe"}}
    while child.poll() is None:
        pump();u.EnumWindows(enumerated,0)
        try:
            for p in psutil.Process(child.pid).children(recursive=True):
                if p.pid not in processes:
                    processes[p.pid]={"name":p.name(),"command":p.cmdline()}
        except psutil.Error:pass
        time.sleep(.004)
    pump()
    out,err=child.communicate(timeout=5)
    assert child.returncode==0,err
    windows=sorted(set(event for event in events if event[0] in processes))
    print(mode,"responses",len(out.splitlines()),"visible windows",windows,flush=True)
    hosts=[v for v in processes.values() if v["name"].lower()=="conhost.exe"]
    print("Console helper sample:",hosts[:2],flush=True)
    return windows
try:
    assert run("calibration"),"Window detection could not observe a real console."
    legacy=run("old_client")
    print("Older client with installed Jobs:","visible helper" if legacy else "no visible helper",flush=True)
    patched=run("patched")
    assert not patched,patched
    print("PASS: positive control observed; 20 corrected calls produced no visible child windows.",flush=True)
finally:u.UnhookWinEvent(hook)
