"""Read the active controller, never infer health from the retired producer."""
import base64
import hashlib
import json
import os
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO = 'ryanredrivergorgehiker/red-river-gorge-hiker'
BRANCH = 'lane20/offline-production-preflight-20261029'
STATE = '.github/automation/rrgh-controller-state.json'


def verified_phase_wait(state, run, jobs):
    previous = state.get('lastRecovered', {})
    progress = state.get('completionProgress', {})
    if not isinstance(previous, dict) or not isinstance(progress, dict):
        return False
    ref = previous.get('recoveryReceipt')
    accepted = previous.get('acceptedRasterTiles')
    required = progress.get('requiredRasterTiles')
    verifiers = [j for j in jobs if j.get('name') == 'independent-recovery']
    return bool(run and run.get('status') == 'completed' and run.get('conclusion') == 'success' and
                state.get('mode') == 'produce' and run.get('display_title') ==
                'RRGH production '+str(state.get('sequence'))+' '+str(state.get('dispatchID')) and
                len(verifiers) == 1 and verifiers[0].get('conclusion') == 'success' and
                all(previous.get(k) is not None and previous.get(k) == state.get(k)
                    for k in ('sequence', 'runID', 'dispatchID', 'planSHA256', 'sourceSHA')) and
                isinstance(ref, dict) and ref.get('key') == 'engineering/map-production/plans/' +
                str(state.get('planSHA256')) + '/slots/00002/receipt.json' and
                ref == state.get('checkpoint') == progress.get('recoveryReceipt') and
                progress.get('sequence') == state.get('sequence') and
                progress.get('planSHA256') == state.get('planSHA256') and
                type(accepted) is int and type(required) is int and required == 278278 and
                0 <= accepted <= required and progress.get('acceptedRasterTiles') == accepted and
                progress.get('remainingRasterTiles') == required - accepted and
                progress.get('fullRasterCoverageComplete') is (accepted == required))


def evaluate(state, run, jobs, delivery=None):
    previous = state.get('lastRecovered', {})
    report = dict(controllerStatus=state.get('status'), sequence=state.get('sequence'),
                  mode=state.get('mode'), runID=state.get('runID'),
                  lastVerifiedSequence=previous.get('sequence'),
                  acceptedJobs=previous.get('acceptedJobs'),
                  acceptedRasterTiles=previous.get('acceptedRasterTiles'),
                  receipt=previous.get('recoveryReceipt'), healthy=False)
    accepted = previous.get('acceptedRasterTiles')
    if type(accepted) is int and 0 <= accepted <= 278278:
        report['remainingRasterTiles'] = 278278 - accepted
    package = state.get('package', {})
    if isinstance(package, dict) and state.get('mode') == 'package':
        verified = package.get('lastVerified', {})
        report.update(packageOperation=package.get('operation', {}).get('kind'),
                      verifiedPackageParts=verified.get('verifiedParts', 0),
                      verifiedPackageIndexes=verified.get('verifiedIndexes', 0),
                      finalPackageDeliveryComplete=False, physicalIPhoneTestComplete=False)
    if run:
        report.update(run=run.get('html_url'), runStatus=run.get('status'),
                      conclusion=run.get('conclusion'),
                      jobs={j['name']: j.get('conclusion') or j.get('status') for j in jobs})
    if state.get('owner') != 'autonomous-v1' or state.get('enabled') is not True:
        report['reason'] = 'Controller disabled or unexpected owner'
    elif state.get('status') in ('halted', 'auth-required'):
        report['reason'] = 'Production paused; the last verified inventory is retained'
    elif run and (run.get('id') != state.get('runID') or
                  run.get('head_branch') != BRANCH or
                  run.get('path') != '.github/workflows/offline-map-restricted-dispatch.yml' or
                  run.get('event') != 'workflow_dispatch' or
                  not run.get('display_title', '').endswith(' '+str(state.get('dispatchID')))):
        report['reason'] = 'Current run identity does not match controller ownership'
    elif run and run.get('conclusion') in ('failure', 'cancelled', 'timed_out', 'action_required'):
        report['reason'] = 'Current production/recovery run failed'
    elif state.get('status') == 'completion-waiting' and verified_phase_wait(state, run, jobs):
        report.update(healthy=True, intentionallyPaused=True,
                      remainingRasterTiles=state['completionProgress']['remainingRasterTiles'],
                      reason='Verified phase finished; production is intentionally paused for the remaining completion work')
    elif state.get('status') == 'package-validation-waiting' and verified_package_wait(state, run, jobs):
        if state.get('finalDelivery') is not None:
            if verified_final_delivery(state, delivery):
                report.update(healthy=True, intentionallyPaused=True, remainingRasterTiles=0,
                              finalPackageDeliveryComplete=True, physicalIPhoneTestComplete=False,
                              deliveryRun=delivery['run']['html_url'],
                              reason='All tiles, regional packages and required Day Hike downloads are verified; ready for physical iPhone testing')
            else:
                report['reason'] = 'Final delivery evidence does not match successful authenticated verification'
        else:
            report.update(healthy=True, intentionallyPaused=True, remainingRasterTiles=0,
                          reason='All raster tiles and offline package bytes are verified; authenticated delivery validation is pending')
    elif run and run.get('status') == 'completed':
        report['reason'] = 'Current run ended but controller ownership has not advanced'
    elif state.get('status') in ('running', 'probing', 'publishing') and run:
        report.update(healthy=True, reason='Current controller run is active; only the last independently verified inventory is counted')
    elif state.get('status') in ('ready', 'dispatching', 'recovery-ready', 'completion-ready', 'package-ready') and not state.get('runID'):
        report.update(healthy=True, reason='Controller is handing off the exact next allocation; no new output is yet counted')
    else:
        report['reason'] = 'Controller is not in a recognized advancing state'
    return report


def verified_final_delivery(state, delivery):
    try:
        evidence = state['finalDelivery']; run = delivery['run']; jobs = delivery['jobs']; request = delivery['request']
        package = state['package']; previous = package['lastVerified']; report = evidence['verification']
        body = {k: v for k, v in request.items() if k != 'requestSHA256'}
        request_sha = hashlib.sha256((json.dumps(body, sort_keys=True, separators=(',', ':'))+'\n').encode()).hexdigest()
        return bool(evidence['format'] == 'rrgh-final-delivery-evidence-v1' and
            evidence['finalPackageDeliveryComplete'] is True and evidence['physicalIPhoneTestComplete'] is False and
            evidence['requestSHA256'] == request['requestSHA256'] == request_sha ==
            state['finalDeliveryReservation']['requestSHA256'] and
            request['format'] == 'rrgh-final-catalog-request-v1' and request['action'] == 'activate-and-verify' and
            request['authorizedBy'] == 'ryanredrivergorgehiker' and request['projectId'] == 'rrgh-nonproduction' and
            request['bucket'] == 'rrgh-nonproduction-protected-packages' and request['automaticRollback'] is True and
            request['authoritySHA256'] == package['authoritySHA256'] and
            request['packagePlanSHA256'] == previous['planSHA256'] and
            request['catalogCandidates'] == previous['catalogCandidates'] and
            request['verifiedCheckpoint'] == previous['checkpoint'] == package['verifiedCheckpoint'] and
            run['id'] == evidence['runID'] and run['head_sha'] == evidence['headSHA'] and
            re.fullmatch('[0-9a-f]{40}', evidence['headSHA']) and
            run['repository']['full_name'] == REPO and run['head_branch'] == 'backend/phase-3-nonprod' and
            run['path'] == '.github/workflows/rrgh-final-catalog.yml' and run['event'] == 'push' and
            run['actor']['login'] == 'ryanredrivergorgehiker' and run['run_attempt'] == 1 and
            run['status'] == 'completed' and run['conclusion'] == 'success' and
            all(len([j for j in jobs if j.get('name') == name]) == 1 and
                next(j for j in jobs if j.get('name') == name).get('conclusion') == 'success'
                for name in ('contracts', 'admission', 'activate', 'verify')) and
            len([j for j in jobs if j.get('name') == 'rollback']) == 1 and
            next(j for j in jobs if j.get('name') == 'rollback').get('conclusion') == 'skipped' and
            report['format'] == 'rrgh-final-authenticated-delivery-v1' and
            report['requestSHA256'] == request_sha and report['authoritySHA256'] == package['authoritySHA256'] and
            report['authenticatedIndexes'] == 3 and report['authenticatedPackages'] == previous['verifiedParts']+3 and
            report['fullyHashedSampleParts'] == 3 and report['everyPackageIdentityAndRangeVerified'] is True and
            report['currentStorageGenerationsVerified'] is True and report['offlineLeaseVerified'] is True and
            report['unauthenticatedDeliveryDenied'] is True and report['physicalIPhoneTestComplete'] is False and
            report['requiredDayHikesVerified'] is True and
            [r['routeID'] for r in report['authenticatedDayHikes']] == ['RTE-0001', 'RTE-0002'] and
            all(r['packageID'] == 'route-'+r['routeID'].lower() and
                isinstance(r['version'], str) and len(r['version']) > 0 and
                re.fullmatch('[0-9a-f]{64}', r['sha256']) and type(r['byteCount']) is int and
                0 < r['byteCount'] <= 8388608 for r in report['authenticatedDayHikes']))
    except (KeyError, TypeError, ValueError, StopIteration):
        return False


def verified_package_wait(state, run, jobs):
    package = state.get('package', {})
    previous = package.get('lastVerified', {})
    progress = state.get('completionProgress', {})
    raster = state.get('lastRecovered', {})
    if not all(isinstance(x, dict) for x in (package, previous, progress, raster)):
        return False
    return bool(run and run.get('status') == 'completed' and run.get('conclusion') == 'success' and
        state.get('mode') == 'package' and run.get('display_title') ==
        'RRGH package '+str(state.get('sequence'))+' '+str(state.get('dispatchID')) and
        package.get('status') == 'verified-awaiting-catalog' and previous.get('runID') == state.get('runID') and
        previous.get('planSHA256') == package.get('planSHA256') and
        previous.get('packageBytesIndependentlyVerified') is True and previous.get('verifiedIndexes') == 3 and
        isinstance(previous.get('verifiedParts'), int) and 3 <= previous['verifiedParts'] <= 192 and
        isinstance(previous.get('catalogCandidates'), dict) and isinstance(previous.get('checkpoint'), dict) and
        previous['checkpoint'] == package.get('verifiedCheckpoint') and
        progress.get('format') == 'rrgh-raster-complete-package-wait-v1' and
        progress.get('fullRasterCoverageComplete') is True and progress.get('acceptedRasterTiles') == 278278 and
        progress.get('remainingRasterTiles') == 0 and raster.get('acceptedRasterTiles') == 278278 and
        all(len([j for j in jobs if j.get('name') == name]) == 1 and
            next(j for j in jobs if j.get('name') == name).get('conclusion') == 'success'
            for name in ('package-stage', 'package-verify', 'package-advance')))


def gh(path):
    req = Request('https://api.github.com/repos/'+REPO+'/'+path,
                  headers={'Accept': 'application/vnd.github+json',
                           'Authorization': 'Bearer '+os.environ['GH_TOKEN'],
                           'X-GitHub-Api-Version': '2022-11-28'})
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def read_state():
    blob = gh('contents/'+STATE+'?ref='+quote(BRANCH, safe=''))
    return blob['sha'], json.loads(base64.b64decode(blob['content']))


def main():
    # A wave can advance during these reads. Resample once instead of reporting
    # a predecessor against its successor's ownership record.
    for attempt in range(2):
        sha, state = read_state()
        rid = state.get('runID')
        run = gh('actions/runs/'+str(rid)) if rid else None
        data = gh('actions/runs/'+str(rid)+'/jobs?per_page=100') if rid else {'total_count': 0, 'jobs': []}
        if data['total_count'] != len(data['jobs']):
            raise ValueError('Incomplete current-run job inventory')
        delivery = None
        if state.get('finalDelivery') is not None:
            evidence = state['finalDelivery']; delivery_run = gh('actions/runs/'+str(evidence['runID']))
            delivery_jobs = gh('actions/runs/'+str(evidence['runID'])+'/jobs?per_page=100')
            if delivery_jobs['total_count'] != len(delivery_jobs['jobs']):
                raise ValueError('Incomplete final-delivery job inventory')
            request_blob = gh('contents/operations/rrgh-final-catalog-request.json?ref='+quote(delivery_run['head_sha'], safe=''))
            raw = base64.b64decode(''.join(request_blob['content'].splitlines()), validate=True)
            if len(raw) > 16384:
                raise ValueError('Final delivery request exceeds bounded owner request')
            delivery = dict(run=delivery_run, jobs=delivery_jobs['jobs'], request=json.loads(raw))
        after, _ = read_state()
        if sha == after:
            break
    else:
        raise ValueError('Controller changed during both snapshots; no stable health claim')
    report = evaluate(state, run, data['jobs'], delivery)
    print(json.dumps(report, sort_keys=True))
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
        out.write('### Red River Gorge Hiker production\n\n')
        out.write('Controller: **'+str(report['controllerStatus'])+'**, wave '+str(report['sequence'])+'\n\n')
        out.write(report['reason']+'\n\n')
        if run:
            out.write('[Current run]('+report['run']+')\n\n')
        out.write('Last independently verified: wave '+str(report['lastVerifiedSequence'])+
                  ', '+str(report['acceptedJobs'])+' jobs, '+str(report['acceptedRasterTiles'])+' raster tiles.\n')
        if 'remainingRasterTiles' in report:
            out.write('\nRemaining raster tiles: **'+str(report['remainingRasterTiles'])+'**.\n')
        if report.get('finalPackageDeliveryComplete') is True:
            out.write('\n[Authenticated delivery verification]('+report['deliveryRun']+')\n\nPhysical iPhone testing: **pending**.\n')
    if not report['healthy']:
        print('::error::RRGH_MAP_PRODUCER_STOPPED: '+report['reason'])
        raise SystemExit(1)


if __name__ == '__main__':
    main()
