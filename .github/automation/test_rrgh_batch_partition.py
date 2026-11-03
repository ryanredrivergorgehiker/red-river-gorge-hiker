import unittest
from rrgh_batch_partition import partition, PartitionError


class PartitionTests(unittest.TestCase):
    def test_clean_suffix(self):
        self.assertEqual(partition(['a','b','c'], ['a','b'], ['a'], ['b'],
                                   clean_closed=True, receipt_verified=True).unattempted, ('c',))

    def test_consumed_unknown_is_not_replayed(self):
        x = partition(['a','b','c'], ['a','b'], ['a'], [],
                      clean_closed=True, receipt_verified=True)
        self.assertEqual(x.attempted_not_accepted, ('b',))
        self.assertEqual(x.unattempted, ('c',))

    def test_reject_unsafe(self):
        cases = [(['a','b'],['b'],[],[]), (['a','b'],['a','a'],[],[]),
                 (['a','b'],['a'],['b'],[]), (['a','b'],['a'],['a'],['a']),
                 (['a','b'],[],[],[])]
        for a,t,s,q in cases:
            with self.subTest(a=a,t=t,s=s,q=q), self.assertRaises(PartitionError):
                partition(a,t,s,q,clean_closed=True,receipt_verified=True)
        for closed, verified in [(False,True),(True,False),(False,False)]:
            with self.assertRaises(PartitionError):
                partition(['a','b'],['a'],['a'],[],
                          clean_closed=closed,receipt_verified=verified)


if __name__ == '__main__':
    unittest.main()
