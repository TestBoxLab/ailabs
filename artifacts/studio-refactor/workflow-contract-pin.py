from pathlib import Path
p=Path('monarch-benchmark/workflowbench/wb_studio/app.py');s=p.read_text(encoding='utf8').replace('{"format": "studio-workflow-v1", "runtime_sha256":', '{"formats": {"experimental": "studio-workflow-v1", "monarch": "native-recipe"}, "runtime_sha256":')
s=s.replace('    def _arm(self, job, arm, task_id, cancel):\n        maximum', '''    def _arm(self, job, arm, task_id, cancel):
        if job["settings"].get("track") == "create-and-run":
            import hashlib
            from wb_studio import workflows
            if job.get("workflow_contract", {}).get("runtime_sha256") != hashlib.sha256(Path(workflows.__file__).read_bytes()).hexdigest():
                raise ValueError("The workflow artifact contract changed; create a new run with the current contract")
        maximum''')
p.write_text(s,encoding='utf8')
