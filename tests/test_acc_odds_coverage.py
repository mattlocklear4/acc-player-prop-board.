"""Offline bookmaker coverage diagnostics: no paid requests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from acc_stage8b_multibook import BOOKS, prop_coverage


class CoverageTests(unittest.TestCase):
    def test_bookmaker_coverage_is_based_only_on_returned_quotes(self):
        props=[{'bookmaker':'fanduel','market':'player_points','player':'Ace Buckner'},
               {'bookmaker':'fanduel','market':'player_points','player':'Ace Buckner'},
               {'bookmaker':'fanduel','market':'player_assists','player':'Cole Certa'}]
        result=prop_coverage(props)
        self.assertEqual(result['quotes'], 3)
        self.assertEqual(result['unique_players'], 2)
        self.assertEqual(result['quotes_by_bookmaker'], {'fanduel':3})
        self.assertEqual(result['quotes_by_market'], {'player_assists':1,'player_points':2})
        self.assertIn('draftkings', result['requested_books_with_no_returned_quotes'])
        self.assertIn('betonlineag', result['requested_books_with_no_returned_quotes'])
        self.assertNotIn('fanduel', result['requested_books_with_no_returned_quotes'])

    def test_empty_market_does_not_imply_sportsbook_unavailability(self):
        result=prop_coverage([])
        self.assertEqual(result['quotes'],0)
        self.assertEqual(result['requested_books_with_no_returned_quotes'],sorted(BOOKS))


if __name__=='__main__': unittest.main()
