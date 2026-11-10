"""Read the active controller, never infer health from the retired producer."""
import base64
import json
import os
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


def evaluate(state, run, jobs):
    previous = state.get('lastRecovered', {})
    report = dict(controllerStatus=state.get('status'), sequence=state.get('sequence'),
                  mode=state.get('mode'), runID=state.get('runID'),
                  lastVerifiedSequence=previous.get('sequence'),
                  acceptedJobs=previous.get('acceptedJobs'),
                  acceptedRasterTiles=previous.get('acceptedRasterTiles'),
                  receipt=previous.get('recoveryReceipt'), healthy=False)
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
    elif run and run.get('status') == 'completed':
        report['reason'] = 'Current run ended but controller ownership has not advanced'
    elif state.get('status') in ('running', 'probing', 'publishing') and run:
        report.update(healthy=True, reason='Current controller run is active; only the last independently verified inventory is counted')
    elif state.get('status') in ('ready', 'dispatching', 'recovery-ready', 'completion-ready') and not state.get('runID'):
        report.update(healthy=True, reason='Controller is handing off the exact next allocation; no new output is yet counted')
    else:
        report['reason'] = 'Controller is not in a recognized advancing state'
    return report


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
        after, _ = read_state()
        if sha == after:
            break
    else:
        raise ValueError('Controller changed during both snapshots; no stable health claim')
    report = evaluate(state, run, data['jobs'])
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
    if not report['healthy']:
        print('::error::RRGH_MAP_PRODUCER_STOPPED: '+report['reason'])
        raise SystemExit(1)


if __name__ == '__main__':
    main()
