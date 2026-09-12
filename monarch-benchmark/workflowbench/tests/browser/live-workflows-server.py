"""Disposable offline stream fixture. /test/advance exists only in this server.

All competitor traffic is disabled by server.build. Synthetic events are named
as fixture data in the UI and never enter a real benchmark results directory.
"""
import argparse
import tempfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread

from server import build
from wb_studio.app import handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8779)
    args = parser.parse_args()
    workspace = tempfile.TemporaryDirectory(prefix='ailabs-live-workflows-')
    studio = build(Path(workspace.name) / 'studio', live=True)
    job = studio.job('fixture-live')
    job['title'] = 'Offline fixture: streamed workflow comparison'
    job['results'] = [e for e in studio.events(job['id']) if e['type'] == 'attempt_finished']
    job['completed'] = len(job['results'])
    studio.save(job)
    task, model = job['settings']['tasks'][0], 'sloppy'
    def emit(kind, **data):
        studio.emit(job['id'], kind, task=task, model=model, **data)
    emit('attempt_started')
    emit('model_started', node='demo:model', label='Read the request', turn=1)
    emit('model_delta', node='demo:model', text='Reading the office relocation email. ')
    lock = Lock()
    stage = 0
    class FixtureHandler(handler(studio)):
        def do_POST(self):
            nonlocal stage
            if self.path == '/test/shutdown':
                self.send_json({'stopping': True})
                Thread(target=server.shutdown, daemon=True).start()
                return
            if self.path != '/test/advance':
                return super().do_POST()
            with lock:
                stage += 1
                if stage == 1:
                    emit('node_started', node='demo:tool', label='api_fetch', arguments={'method':'GET','url':'https://salesforce.mock/contacts'})
                    emit('node_finished', node='demo:tool', label='api_fetch', status='completed', output={'records':[{'Name':'Lisa Park','City':'Denver'},{'Name':'Amir Hassan','City':'Boston'}]})
                    emit('model_delta', node='demo:model', text='Found two contact records. Checking the requested change.')
                elif stage == 2:
                    emit('model_finished', node='demo:model', status='completed', output='Fixture attempt finished without applying the requested change.')
                    result = {'task':task,'model':model,'passed':False,'termination':'completed','error':None,'cost_usd':0,'tokens':{},'seconds':12.5,'tool_calls':1,'checks':[{'type':'field_equals','passed':False},{'type':'allowed_changes_only','passed':True}],'unexpected_changes':[],'count_violations':[],'flags':['synthetic_fixture'],'output':'Fixture attempt finished without applying the requested change.'}
                    current = studio.job(job['id'])
                    current['results'].append(result)
                    current['completed'] += 1
                    studio.save(current)
                    studio.emit(job['id'], 'attempt_finished', **result)
            return self.send_json({'stage':stage})
    server = ThreadingHTTPServer(('127.0.0.1', args.port), FixtureHandler)
    print(f'READY http://127.0.0.1:{args.port} (offline fixture only)', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        workspace.cleanup()


if __name__ == '__main__':
    main()
