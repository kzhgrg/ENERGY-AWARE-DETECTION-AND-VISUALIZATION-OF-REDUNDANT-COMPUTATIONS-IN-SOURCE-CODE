import unittest
from pycparser import c_parser
from controlflow import build_cfg
from analyzer import analyze
class ControlFlowTests(unittest.TestCase):
    def test_if_edges(self):
        cfg=build_cfg(c_parser.CParser().parse('int main(){int x=1;if(x){x=2;}else{x=3;}return x;}'))
        self.assertTrue(any(e['label']=='true' for e in cfg['edges']))
        self.assertTrue(any(e['label']=='false' for e in cfg['edges']))
        self.assertTrue(cfg['dominators'])
    def test_loop_backedge(self):
        cfg=build_cfg(c_parser.CParser().parse('int main(){int i=0;while(i<3){i=i+1;}return i;}'))
        self.assertTrue(any('While' in n['label'] for n in cfg['nodes']))
    def test_constant_if(self):
        r=analyze('int main(){int x=1;if(2<3){x=4;}else{x=9;}return x;}')
        self.assertNotIn('x = 9',r['optimized'])
        self.assertIn('Constant branch elimination',r['summary'])
    def test_while_false(self):
        r=analyze('int main(){int x=1;while(0){x=9;}return x;}')
        self.assertNotIn('x = 9',r['optimized'])
    def test_for_preserved(self):
        r=analyze('int main(){int i;for(i=0;i<4;i++){;}return 0;}')
        self.assertIn('for (',r['optimized'])
if __name__=='__main__':unittest.main()
