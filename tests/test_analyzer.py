import unittest
from analyzer import analyze
class AnalyzerTests(unittest.TestCase):
    def test_constant_fold(self):
        r=analyze('int main(){int x=4*5;return x;}')
        self.assertIn('x = 20',r['optimized'])
    def test_dead_code(self):
        r=analyze('int main(){int x=2;int unused=3*4;return x;}')
        self.assertNotIn('unused',r['optimized'])
    def test_cse(self):
        r=analyze('int main(){int x=2;int a=x+3;int b=x+3;return a+b;}')
        self.assertIn('b = a',r['optimized'])
    def test_invalidate(self):
        r=analyze('int main(){int x=2;int a=x+3;x=4;int b=x+3;return a+b;}')
        self.assertNotIn('b = a',r['optimized'])
    def test_strength(self):
        r=analyze('int main(){unsigned int x=7u;unsigned int y=x*8;return y;}')
        self.assertIn('x << 3',r['optimized'])
    def test_skip_loop(self):
        r=analyze('int main(){int x=0;while(x<3){x=x+1;}return x;}')
        self.assertEqual(r['before'],r['after'])
    def test_parse_error(self):
        self.assertIn('error',analyze('#include <stdio.h>\nint main(){return 0;}'))
if __name__=='__main__': unittest.main()

class RegressionTests(unittest.TestCase):
    def test_overwritten_initializer(self):
        r=analyze('int main(){int x=5;x=8;return x;}')
        self.assertIn('x = 8',r['optimized'])
        self.assertNotIn('x = 5',r['optimized'])
    def test_dead_assignment(self):
        r=analyze('int main(){int x=5;x=8;x=9;return x;}')
        self.assertNotIn('x = 8',r['optimized'])
    def test_uninitialized_skipped(self):
        r=analyze('int main(){int x;int y=x+1;return y;}')
        self.assertTrue(r['notices'])
    def test_globals_skipped(self):
        r=analyze('int g=5;int main(){int x=4*5;return x+g;}')
        self.assertIn('4 * 5',r['optimized'])
    def test_params_skipped(self):
        r=analyze('int f(int x){int y=4*5;return y+x;}')
        self.assertIn('4 * 5',r['optimized'])
    def test_side_effects_skipped(self):
        r=analyze('int f(){int x=foo();return 1;}')
        self.assertIn('foo()',r['optimized'])
    def test_cse_reassigned_destination(self):
        r=analyze('int main(){int x=1;int a=x+2;a=9;int b=x+2;return b;}')
        self.assertNotIn('b = a',r['optimized'])
    def test_cost_model_metadata(self):
        r=analyze('int main(){int x=4*5;return x;}')
        self.assertEqual(r['cost_model']['unit'],'illustrative weighted static operation score')
