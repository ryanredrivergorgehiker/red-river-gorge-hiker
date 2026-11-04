"""Synthetic pagination and publisher-resume regression tests; no Cloud access."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

import rrgh_dispatcher as d

ROOT = Path(__file__).resolve().parents[2]
PRODUCER = '.github/workflows/' + d.WORKFLOW


def page(runs=(), total=None):
    return {'total_count': len(runs) if total is None else total,
            'workflow_runs': list(runs)}


def unrelated(first, count):
    return [dict(id=n, path='.github/workflows/ci.yml') for n in range(first, first+count)]


class ReadAPI:
    def __init__(self, respond=None):
        self.respond = respond or (lambda status, number, attempt: page())
        self.calls = []
        self.attempt = 0

    def call(self, method, path, payload=None):
        if method != 'GET' or not path.startswith('actions/runs?'):
            raise AssertionError('Inventory must never write or dispatch')
        query = parse_qs(path.split('?', 1)[1])
        status = query['status'][0]
        number = int(query['page'][0])
        if status == 'queued' and number == 1:
            self.attempt += 1
        self.calls.append((status, number, self.attempt))
        return self.respond(status, number, self.attempt)


class PaginationTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch.object(d.time, 'sleep').start()
        self.addCleanup(patch.stopall)

    def test_complete_empty_inventory_does_not_retry(self):
        api = ReadAPI()
        d.assert_no_other_producers(api)
        self.assertEqual(len(api.calls), 5)
        self.sleep.assert_not_called()

    def test_transient_empty_page_restarts_every_status_then_succeeds(self):
        def respond(status, number, attempt):
            return page(total=1) if status == 'in_progress' and attempt == 1 else page()
        api = ReadAPI(respond)
        d.assert_no_other_producers(api)
        self.assertEqual(api.calls[:3], [('queued',1,1),('in_progress',1,1),('queued',1,2)])
        self.sleep.assert_called_once_with(1)

    def test_two_transient_inventories_can_recover_on_third(self):
        api = ReadAPI(lambda status, number, attempt: page(total=1 if attempt < 3 else 0))
        d.assert_no_other_producers(api)
        self.assertEqual(api.attempt, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1, 2])

    def test_persistent_incomplete_snapshot_halts_without_writes(self):
        api = ReadAPI(lambda *args: page(total=1))
        with self.assertRaisesRegex(d.Halt, 'three read-only scans exhausted'):
            d.assert_no_other_producers(api)
        self.assertEqual(api.calls, [('queued',1,1),('queued',1,2),('queued',1,3)])

    def test_competitor_discovered_after_retry_still_blocks(self):
        for producer in (PRODUCER, d.ORIGINAL):
            with self.subTest(producer=producer):
                api = ReadAPI(lambda status, number, attempt:
                    page(total=1) if attempt == 1 else page([dict(id=9,path=producer)]))
                with self.assertRaisesRegex(d.Halt, 'Another producer is active'):
                    d.assert_no_other_producers(api, allowed_run=8)
                self.assertEqual(api.attempt, 2)

    def test_competitor_on_inconsistent_page_blocks_immediately(self):
        api = ReadAPI(lambda *args: page([dict(id=9,path=PRODUCER)],total=0))
        with self.assertRaisesRegex(d.Halt, 'Another producer is active'):
            d.assert_no_other_producers(api)
        self.assertEqual(api.attempt, 1)
        self.sleep.assert_not_called()

    def test_only_explicit_parent_can_remain_in_active_inventory(self):
        api = ReadAPI(lambda *args: page([dict(id=8,path=PRODUCER)]))
        d.assert_no_other_producers(api, allowed_run=8)
        self.assertEqual(api.attempt, 1)

    def test_competitor_on_later_page_is_not_missed(self):
        def respond(status, number, attempt):
            if status != 'in_progress': return page()
            return page(unrelated(100,100),101) if number == 1 else page([dict(id=9,path=PRODUCER)],101)
        api = ReadAPI(respond)
        with self.assertRaisesRegex(d.Halt, 'Another producer is active'):
            d.assert_no_other_producers(api)

    def test_complete_multi_page_inventory_passes(self):
        def respond(status, number, attempt):
            if status != 'waiting': return page()
            return page(unrelated(100,100),101) if number == 1 else page(unrelated(200,1),101)
        api = ReadAPI(respond)
        d.assert_no_other_producers(api)
        self.assertEqual(api.attempt, 1)

    def test_changed_count_and_duplicate_ids_cannot_count_as_complete(self):
        for failure in ('count','duplicate','within-page','overcount','missing'):
            with self.subTest(failure=failure):
                def respond(status, number, attempt):
                    if attempt > 1 or status != 'queued': return page()
                    if failure == 'within-page': return page(unrelated(100,1)*2,2)
                    if failure == 'overcount': return page(unrelated(100,2),1)
                    if number == 1: return page(unrelated(100,100),101)
                    if failure == 'count': return page(unrelated(200,1),102)
                    if failure == 'duplicate': return page(unrelated(100,1),101)
                    return page(total=101)
                api = ReadAPI(respond)
                d.assert_no_other_producers(api)
                self.assertEqual(api.attempt, 2)

    def test_malformed_response_never_becomes_empty_clearance(self):
        for data in (None, {}, {'total_count':False,'workflow_runs':[]},
                     {'total_count':-1,'workflow_runs':[]},
                     {'total_count':0,'workflow_runs':None},
                     page([{}]), page([dict(id=1)]),
                     page([dict(id=True,path=PRODUCER)]),
                     page(unrelated(1,101))):
            with self.subTest(data=data):
                api = ReadAPI(lambda *args: data)
                with self.assertRaisesRegex(d.Halt, 'Malformed'):
                    d.assert_no_other_producers(api)
                self.assertEqual(api.attempt, 1)

    def test_pagination_limit_remains_bounded(self):
        api = ReadAPI(lambda status, number, attempt: page(unrelated(number*100,100),2001))
        with self.assertRaisesRegex(d.Halt, 'pagination limit exceeded'):
            d.assert_no_other_producers(api)
        self.assertEqual(len(api.calls), 20)
        self.assertEqual(api.attempt, 1)

    def test_network_or_other_errors_do_not_repeat_mutations(self):
        api = ReadAPI()
        with patch.object(api, 'call', side_effect=TimeoutError('transport failure')) as call:
            with self.assertRaises(TimeoutError): d.assert_no_other_producers(api)
            self.assertEqual(call.call_count, 1)


class RecoveredResumeTests(unittest.TestCase):
    def setUp(self):
        self.state = dict(format='rrgh-controller-state-v1', owner='autonomous-v1',epoch=1,
            enabled=True,status='halted',mode='produce',sequence=239,runID=239,
            sourceSHA='a'*40,planSHA256='b'*64,dispatchID='c'*64,controlDigest=d.local_digest(ROOT))
        self.receipt = dict(bytes=1499,generation='123',key='exact-recovery',sha256='d'*64)
        self.state['recoveredResumeAuthorization'] = {
            **{k:self.state[k] for k in ('runID','sourceSHA','planSHA256','dispatchID')},
            'authorizedBy':'ryanredrivergorgehiker','authorizedOn':'2026-11-03',
            'recoveryReceipt':copy.deepcopy(self.receipt)}
        self.api = ReadAPI()
        self.api.state = lambda: ('state-sha', copy.deepcopy(self.state))
        self.inventory_call = self.api.call
        def call(method,path,payload=None):
            if method == 'GET' and path == 'git/ref/heads/'+d.SOURCE:
                return {'object':{'sha':self.state['sourceSHA']}}
            return self.inventory_call(method,path,payload)
        self.api.call = call
        self.caller = patch.object(d, 'caller').start()
        self.audit = patch.object(d, 'audit_state', return_value={'receiptRef':self.receipt}).start()
        self.addCleanup(patch.stopall)

    def test_exact_nov3_recovered_resume_reads_without_producer_replay(self):
        before = copy.deepcopy(self.state)
        self.assertEqual(d.audit_recovered(self.api,ROOT), {'receiptRef':self.receipt})
        self.assertEqual(self.state,before)
        self.caller.assert_called_once_with('launch')
        self.audit.assert_called_once_with(self.api,ROOT,self.state,allow_failed_controller=True)

    def test_each_authorization_pin_and_receipt_is_required(self):
        original = copy.deepcopy(self.state)
        for key in self.state['recoveredResumeAuthorization']:
            with self.subTest(key=key):
                self.state = copy.deepcopy(original)
                self.state['recoveredResumeAuthorization'][key]='changed'
                with self.assertRaises(d.Halt): d.audit_recovered(self.api,ROOT)

    def test_exact_nov4_owner_authorization_preserves_receipt_only_resume(self):
        self.state['recoveredResumeAuthorization']['authorizedOn']='2026-11-04'
        self.assertEqual(d.audit_recovered(self.api,ROOT),{'receiptRef':self.receipt})
        self.audit.assert_called_once_with(self.api,ROOT,self.state,allow_failed_controller=True)

    def test_claimed_or_unrecovered_modes_are_not_eligible(self):
        original = copy.deepcopy(self.state)
        for key,value in [('status','running'),('status','publishing'),('mode','recover'),('enabled',False)]:
            self.state = {**copy.deepcopy(original),key:value}
            with self.assertRaises(d.Halt): d.audit_recovered(self.api,ROOT)

    def test_persistent_incomplete_inventory_cannot_reach_recovery_audit(self):
        self.api.respond = lambda *args: page(total=1)
        with patch.object(d.time,'sleep'), self.assertRaisesRegex(d.Halt,'three read-only scans exhausted'):
            d.audit_recovered(self.api,ROOT)
        self.audit.assert_not_called()

    def test_changed_source_lease_blocks_resume(self):
        def call(method,path,payload=None):
            if path == 'git/ref/heads/'+d.SOURCE: return {'object':{'sha':'e'*40}}
            return self.inventory_call(method,path,payload)
        self.api.call=call
        with self.assertRaisesRegex(d.Halt,'Source lease changed'): d.audit_recovered(self.api,ROOT)


if __name__ == '__main__':
    unittest.main()
