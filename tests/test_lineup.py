"""Contract tests for the optimizer without invoking CLI/public-file writes.

Run with the same NumPy/SciPy environment as simulate_season.py.
"""
import ast
import copy
from pathlib import Path
import unittest
import numpy as np
from scipy.optimize import linear_sum_assignment

source = ast.parse((Path(__file__).resolve().parents[1]/'scripts/simulate_season.py').read_text())
function = next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=='lineup')

class LineupContract(unittest.TestCase):
    def setUp(self):
        self.data = {
            'slots':['QB','RB','FLEX'],
            'players':{sid:{'name':sid,'positions':[pos],'injury':injury} for sid,pos,injury in [('qb','QB',None),('locked','RB','Out'),('bench','WR',None),('rb','RB','Questionable')]},
            'projections':{'10':{'qb':10,'locked':40,'bench':100,'rb':9},'11':{'qb':10,'locked':40,'bench':100,'rb':9}},
            'unavailable':['locked','bench'],
            'replacements':{str(w):{pos:{'points':5} for pos in ('QB','RB','WR','TE')} for w in (10,11)},
            'uncertainty':{pos:{'scaled_rmse':2} for pos in ('QB','RB','WR','TE')},
        }
        self.team={'players':['qb','locked','bench','rb'],'reserve':[],'locked':{'1':{'id':'locked','points':-2}}}
        self.env={'D':self.data,'FIRST':10,'np':np,'linear_sum_assignment':linear_sum_assignment}
        exec(compile(ast.Module(body=[function],type_ignores=[]),'lineup','exec'),self.env)
    def test_earned_negative_points_stay_in_slot_and_are_not_redrawn(self):
        result=self.env['lineup'](self.team,10)
        self.assertEqual([p['id'] for p in result['players']],['qb','locked','rb'])
        self.assertEqual(result['points'],17)
        self.assertEqual(result['players'][1]['variance'],0)
        self.assertEqual(result['variance'],76)
    def test_zero_point_starter_without_projection_is_retained(self):
        self.team['locked']['1']['points']=0
        del self.data['projections']['10']['locked']
        self.assertEqual(self.env['lineup'](self.team,10)['players'][1]['points'],0)
    def test_future_weeks_release_locks_and_allow_returns(self):
        result=self.env['lineup'](self.team,11)
        self.assertEqual(result['points'],150)
        self.assertFalse(any(p['actual'] for p in result['players']))
    def test_unplayed_reserve_and_out_players_are_excluded(self):
        self.team['locked']={};self.data['unavailable']=[];self.team['reserve']=['bench']
        ids=[p['id'] for p in self.env['lineup'](self.team,10)['players']]
        self.assertNotIn('bench',ids);self.assertNotIn('locked',ids)
        self.assertIn('rb',ids)
    def test_vacancies_get_positional_replacements_without_duplication(self):
        self.team['players']=['qb'];self.team['locked']={}
        result=self.env['lineup'](self.team,10)
        self.assertEqual(result['points'],20)
        self.assertEqual(sum(p['replacement'] for p in result['players']),2)
        self.assertTrue(all(p['variance']>0 for p in result['players']))

if __name__=='__main__':unittest.main()
