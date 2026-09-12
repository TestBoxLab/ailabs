"""Feature 027 browser fixture: reuse the scripted server, excluding metadata manifests."""
import importlib.util
from pathlib import Path

path = Path(__file__).with_name('server.py')
spec = importlib.util.spec_from_file_location('report_fixture_server', path)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
load = server.load_suite
server.load_suite = lambda folder: [task for task in load(folder) if task.get('task')]
server.main()
