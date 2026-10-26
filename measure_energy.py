"""Opt-in, local-only energy measurement for trusted compiled benchmark executables.
macOS: powermetrics CPU power samples; Linux: Intel RAPL energy counter.
Do not invoke this from Flask or on untrusted uploaded code.
"""
import argparse, json, os, platform, re, subprocess, time
from pathlib import Path

def rapl_path():
    root=Path('/sys/class/powercap')
    for p in root.glob('intel-rapl:*'):
        if (p/'energy_uj').exists(): return p
    return None

def linux_measure(command, timeout):
    p=rapl_path()
    if not p: raise RuntimeError('Intel RAPL energy_uj not available/readable on this machine.')
    maximum=int((p/'max_energy_range_uj').read_text())
    start=int((p/'energy_uj').read_text());t=time.perf_counter()
    run=subprocess.run(command,timeout=timeout,capture_output=True,text=True)
    elapsed=time.perf_counter()-t;end=int((p/'energy_uj').read_text())
    return {'method':'Linux Intel RAPL package energy counter','joules':(end-start)%maximum/1e6,
            'seconds':elapsed,'exit_code':run.returncode,'stdout':run.stdout[-1000:],
            'scope':'CPU package/domain energy during wall-clock interval; includes unrelated system activity.'}

def mac_measure(command,timeout,interval_ms):
    # sudo must be configured by user in advance. Never request/store a password.
    probe=subprocess.run(['sudo','-n','true'],capture_output=True)
    if probe.returncode: raise RuntimeError('powermetrics needs sudo. Run `sudo -v` in this terminal first, then retry promptly.')
    meter=subprocess.Popen(['sudo','-n','powermetrics','--samplers','cpu_power','-i',str(interval_ms)],
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        time.sleep(interval_ms/1000)
        t=time.perf_counter()
        run=subprocess.run(command,timeout=timeout,capture_output=True,text=True)
        elapsed=time.perf_counter()-t
    finally:
        meter.terminate()
        try: stdout,stderr=meter.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            meter.kill();stdout,stderr=meter.communicate()
    samples=[float(x) for x in re.findall(r'CPU Power:\s*([\d.]+)\s*mW',stdout,re.I)]
    if not samples:
        raise RuntimeError('No CPU Power samples from powermetrics. Run a longer workload; check macOS support. '+stderr[-250:])
    # Average sampled CPU power times elapsed wall time: approximate, not per-process energy.
    avg=sum(samples)/len(samples)
    return {'method':'macOS powermetrics CPU Power sampling','joules':avg/1000*elapsed,
            'average_cpu_power_mw':avg,'samples':len(samples),'seconds':elapsed,
            'exit_code':run.returncode,'stdout':run.stdout[-1000:],
            'scope':'Approximate CPU energy from sampled system CPU power; not isolated per-process energy.'}

def main():
    ap=argparse.ArgumentParser(description='Measure trusted, local benchmark executable energy')
    ap.add_argument('--timeout',type=float,default=30)
    ap.add_argument('--interval-ms',type=int,default=100)
    ap.add_argument('--output',default='energy_result.json')
    ap.add_argument('command',nargs=argparse.REMAINDER,help='Command after -- (e.g. -- ./benchmark)')
    a=ap.parse_args();cmd=a.command
    if cmd and cmd[0]=='--':cmd=cmd[1:]
    if not cmd:ap.error('Provide a trusted executable after --')
    if a.timeout<=0 or a.interval_ms<50:ap.error('Invalid timeout/interval')
    if platform.system()=='Linux': result=linux_measure(cmd,a.timeout)
    elif platform.system()=='Darwin':result=mac_measure(cmd,a.timeout,a.interval_ms)
    else:raise SystemExit('Only macOS powermetrics and Linux Intel RAPL supported')
    Path(a.output).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
