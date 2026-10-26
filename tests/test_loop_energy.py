import unittest
from analyzer import analyze
from branch_pass import optimize_branches
from pycparser import c_parser, c_generator
class LoopTests(unittest.TestCase):
 def test_fold_inside_while(self):
  r=analyze('int main(){int x=0;while(x<5){x=x+(2*3);}return x;}')
  self.assertIn('x + 6',r['optimized'])
 def test_fold_inside_for(self):
  r=analyze('int main(){int x=0;for(int i=0;i<3;i++){x=x+(2*3);}return x;}')
  self.assertIn('x + 6',r['optimized'])
 def test_zero_trip_for_without_initializer(self):
  r=analyze('int main(){for(;0;){return 2;}return 1;}')
  self.assertNotIn('return 2',r['optimized'])
 def test_nonconstant_loop_preserved(self):
  r=analyze('int main(){int x=0;while(x<3){x++;}return x;}')
  self.assertIn('while (',r['optimized'])
 def test_energy_benchmark_is_fixed(self):
  from energy_dashboard import BENCH
  self.assertTrue((BENCH/'baseline.c').exists())
  self.assertTrue((BENCH/'optimized.c').exists())
if __name__=='__main__': unittest.main()
