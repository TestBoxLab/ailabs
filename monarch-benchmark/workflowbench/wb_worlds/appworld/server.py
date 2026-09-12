"""Private runtime identity endpoint around the unchanged AppWorld environment."""
from importlib.metadata import version
from pathlib import Path
import os
import uvicorn
from appworld import update_root
from appworld.serve.environment import app


@app.get('/workflowbench-runtime')
def runtime_identity():
    root = Path(os.environ.get('APPWORLD_ROOT', '/run'))
    return {'package':'appworld', 'version':version('appworld'),
            'data_version':(root / 'data/version.txt').read_text().strip()}


if __name__ == '__main__':
    update_root(os.environ.get('APPWORLD_ROOT', '/run'))
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8000')))
