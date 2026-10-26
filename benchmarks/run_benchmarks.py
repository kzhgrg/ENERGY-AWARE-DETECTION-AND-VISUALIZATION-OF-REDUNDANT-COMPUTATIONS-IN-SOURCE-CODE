"""Evaluate static cost on sample inputs; does not claim measured energy."""
import csv
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyzer import analyze

SAMPLES = {
    'constant_fold': 'int main(){int x=4*5;return x;}',
    'dead_code': 'int main(){int x=4;int unused=x*7;return x;}',
    'cse': 'int main(){int x=4;int a=x+5;int b=x+5;return a+b;}',
    'strength': 'int main(){unsigned int x=4;unsigned int y=x*8;return y;}',
    'mixed': 'int main(){int x=4*5;int a=x+3;int b=x+3;int unused=8*9;return a+b;}',
    'loop_unsupported': 'int main(){int x=0;while(x<5){x=x+1;}return x;}',
}
output = Path(__file__).with_name('results.csv')
with output.open('w', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=['program','before','after','reduction_percent','applied_transformations','notices'])
    writer.writeheader()
    for name, code in SAMPLES.items():
        result = analyze(code)
        writer.writerow({'program':name,'before':result['before'],'after':result['after'],
                         'reduction_percent':result['reduction'],
                         'applied_transformations':len(result['findings']),
                         'notices':'; '.join(result['notices'])})
print('Wrote', output)
