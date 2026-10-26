"""Local-only opt-in measurements of bundled, reviewed C benchmarks."""
import os, platform, shutil, subprocess, tempfile
from pathlib import Path
from measure_energy import linux_measure, mac_measure

BENCH = Path(__file__).parent/'energy_benchmarks'
def run_energy_pair():
    compiler=shutil.which('clang') or shutil.which('gcc')
    if not compiler: raise RuntimeError('Install clang or gcc to compile the bundled benchmark.')
    if platform.system() not in ('Darwin','Linux'):
        raise RuntimeError('Energy counters supported on macOS and Linux only.')
    with tempfile.TemporaryDirectory(prefix='compiler_energy_') as d:
        paths=[]
        for name in ('baseline','optimized'):
            executable=Path(d)/name
            subprocess.run([compiler,'-O0','-std=c11',str(BENCH/(name+'.c')),'-o',str(executable)],check=True,capture_output=True,timeout=15)
            paths.append(str(executable))
        results=[]
        for executable in paths:
            if platform.system()=='Darwin':
                result=mac_measure([executable],timeout=35,interval_ms=100)
            else:
                result=linux_measure([executable],timeout=35)
            if result['exit_code']!=0: raise RuntimeError('Benchmark execution failed.')
            results.append(result)
        if results[0]['stdout'] != results[1]['stdout']:
            raise RuntimeError('Benchmark output mismatch: cannot compare results.')
        return {'baseline':results[0],'optimized':results[1],
                'relative_change_percent':round(100*(results[1]['joules']-results[0]['joules'])/results[0]['joules'],2) if results[0]['joules'] else None,
                'warning':'System/package energy includes background processes. One pair is not statistically meaningful. Repeat measurements, alternate order, and report uncertainty.',
                'benchmark':'Bundled fixed-input C benchmark, compiled at -O0; not arbitrary code pasted into the editor.'}
