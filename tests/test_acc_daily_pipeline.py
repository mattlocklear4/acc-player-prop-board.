"""Regression tests for short-name KenPom opponent resolution and grading fields."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from supabase_kenpom import resolve_opponent
from research_engine import canon

class OpponentTests(unittest.TestCase):
    def test_njit_mascot(self):
        kp={canon('NJIT'):{'Team':'NJIT'}}
        self.assertEqual(resolve_opponent('NJIT Highlanders',kp),'NJIT')
    def test_unknown_is_not_guessed(self):
        kp={canon('NJIT'):{'Team':'NJIT'}}
        self.assertIsNone(resolve_opponent('Other Highlanders',kp))
    def test_long_school_name(self):
        kp={canon('Boston College'):{'Team':'Boston College'}}
        self.assertEqual(resolve_opponent('Boston College Eagles',kp),'Boston College')

    def test_ole_miss_kenpom_name(self):
        kp={canon('Mississippi'):{'Team':'Mississippi'}, canon('Mississippi State'):{'Team':'Mississippi State'}}
        self.assertEqual(resolve_opponent('Ole Miss Rebels',kp),'Mississippi')
        self.assertEqual(resolve_opponent('Mississippi Rebels',kp),'Mississippi')

if __name__=='__main__':unittest.main()
