#!/usr/bin/env python3
"""Offline, no-network arithmetic smoke tests for BetOnline value calculations."""
import math
from acc_betonline_value import profit, over_probability

def close(actual, expected, tolerance=1e-9):
    assert abs(actual-expected)<tolerance,(actual,expected)

close(profit(-110),100/110)
close(profit(120),1.2)
close(over_probability(2,'Threes',1.5,None),1-math.exp(-2)*(1+2))
close(over_probability(10,'Points',9.5,2),0.5)
assert over_probability(10,'Points',9.5,None) is None
assert over_probability(11,'Points',9.5,2)>0.5
print('BetOnline value self-tests: 6 passed; zero network calls')
