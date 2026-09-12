import json

import pytest

from wb_world.episode import contract_hash
from tests.test_studio_reports import studio, finished_run
from tests.test_studio_app import server_for, request


def test_guide_download_is_an_attachment_with_saved_attempts(studio):
    job = finished_run(studio)
    with server_for(studio) as port:
        status, headers, body = request(port, "GET", f"/api/reports/run/{job['id']}/downloads/guide")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert "attachment;" in headers["Content-Disposition"]
    assert "Expected result checks" in body


def test_guide_uses_only_hash_verified_tasks_and_saved_attempts():
    from wb_studio.evidence_guide import build
    task = {"task": "example", "prompt": [{"role": "user", "content": "Create <one> record."}],
            "info": {"assertions": [{"type": "record_exists", "name": "</script>"}], "initial_state": {}}}
    job = {"id": "run-1", "task_hashes": {"example": contract_hash(task)}}
    rows = [{"episode_id": "attempt-1", "task_id": "example", "arm": "monarch@build", "trial": 0,
             "passed": False, "termination": "completed", "check_results": [{"passed": False}]}]
    html = build(job, rows, {"example": task})
    data = json.loads(html.split('<script id="guide-data" type="application/json">')[1].split('</script>')[0])
    assert data["attempts"][0]["attempt_id"] == "attempt-1"
    assert data["tasks"][0]["assertions"] == task["info"]["assertions"]
    assert data["attempts"][0]["passed"] is False
    assert '</script>' not in html.split('type="application/json">')[1].split('</script>')[0]
    job["settings"] = {"repetitions": 2}
    rows[0]["trial"] = 1
    repeated = build(job, rows, {"example": task})
    repeated_data = json.loads(repeated.split('<script id="guide-data" type="application/json">')[1].split('</script>')[0])
    assert repeated_data["attempts"][0]["initial_repetitions"] == 2
    task["prompt"][0]["content"] = "Changed request"
    with pytest.raises(ValueError, match="hash"):
        build(job, rows, {"example": task})
