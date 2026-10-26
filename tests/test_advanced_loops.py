import unittest
from analyzer import analyze

class AdvancedLoopTests(unittest.TestCase):
    def test_unroll(self):
        r=analyze('int main(){unsigned int sum=0;for(unsigned int i=0;i<3;i++){sum+=i;}return sum;}')
        self.assertIn('Loop unrolling',r['summary'])
        self.assertNotIn('for (',r['optimized'])
    def test_licm(self):
        r=analyze('int main(){unsigned int a=2;unsigned int b=3;unsigned int sum=0;for(unsigned int i=0;i<30;i++){sum+=a*b;}return sum;}')
        self.assertIn('Loop-invariant code motion',r['summary'])
        self.assertIn('__cf_invariant_',r['optimized'])
    def test_induction(self):
        r=analyze('int main(){unsigned int sum=0;for(unsigned int i=0;i<30;i++){sum+=i*4;}return sum;}')
        self.assertIn('Induction-variable optimization',r['summary'])
        self.assertIn('__cf_induction_',r['optimized'])
    def test_unsafe_preserved(self):
        r=analyze('int main(){unsigned int sum=0;for(unsigned int i=0;i<4;i++){sum+=i;sum++;}return sum;}')
        self.assertIn('for (',r['optimized'])
    def test_large_loop_not_unrolled(self):
        r=analyze('int main(){unsigned int sum=0;for(unsigned int i=0;i<300;i++){sum+=i;}return sum;}')
        self.assertIn('for (',r['optimized'])

if __name__=='__main__':unittest.main()
