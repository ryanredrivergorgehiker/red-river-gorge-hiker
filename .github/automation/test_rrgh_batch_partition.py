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

    def test_resource_limit_clean_closure_preserves_only_unattempted_suffix(self):
        # A source/time/request limit may stop after a durable prefix.
        for reason in ('time', 'source-bytes', 'source-requests', 'output-bytes'):
            with self.subTest(reason=reason):
                result = partition(['a', 'b', 'c', 'd'], ['a', 'b'],
                                   ['a'], ['b'], clean_closed=True,
                                   receipt_verified=True)
                self.assertEqual(result.accepted, ('a',))
                self.assertEqual(result.attempted_not_accepted, ('b',))
                self.assertEqual(result.unattempted, ('c', 'd'))

    def test_consecutive_failures_are_consumed_not_reallocated(self):
        result = partition(['a', 'b', 'c', 'd'], ['a', 'b', 'c'],
                           [], ['a', 'b', 'c'], clean_closed=True,
                           receipt_verified=True)
        self.assertEqual(result.attempted_not_accepted, ('a', 'b', 'c'))
        self.assertEqual(result.unattempted, ('d',))

    def test_interrupted_or_unverified_close_never_reallocates(self):
        for closed, verified in ((False, False), (False, True), (True, False)):
            with self.subTest(closed=closed, verified=verified):
                with self.assertRaises(PartitionError):
                    partition(['a', 'b'], ['a'], ['a'], [],
                              clean_closed=closed, receipt_verified=verified)

    def test_replayed_or_ambiguous_reservation_is_rejected(self):
        cases = [
            (['a', 'b', 'c'], ['a', 'a'], [], []),
            (['a', 'b', 'c'], ['a', 'c'], ['a'], []),
            (['a', 'b', 'c'], ['a'], ['b'], []),
            (['a', 'b', 'c'], ['a'], [], ['b']),
            (['a', 'b', 'c'], [], [], []),
        ]
        for approved, attempted, accepted, quarantined in cases:
            with self.subTest(attempted=attempted), self.assertRaises(PartitionError):
                partition(approved, attempted, accepted, quarantined,
                          clean_closed=True, receipt_verified=True)

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
