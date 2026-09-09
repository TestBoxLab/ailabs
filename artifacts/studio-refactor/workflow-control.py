from pathlib import Path
p=Path('monarch-benchmark/workflowbench/wb_studio/app.py');s=p.read_text(encoding='utf8')
s=s.replace('        result = self.studio.component(self.identity, "brain")(gateway, system=system, brief=ep.task["prompt"][1]["content"], execute_tool=self.studio.component(self.identity, "action_builder")(ep), emit=self.emit,', '''        workflow_track = self.studio.job(self.identity)["settings"].get("track") == "create-and-run"
        execute = self.studio.component(self.identity, "action_builder")(ep)
        if workflow_track:
            from wb_studio.workflows import WORKFLOW_GUIDE, discovery_executor
            system += "\\n\\nWorkflow artifact requirement:\\n" + WORKFLOW_GUIDE
            authoring_execute = discovery_executor(execute)
        else:
            authoring_execute = execute
        result = self.studio.component(self.identity, "brain")(gateway, system=system, brief=ep.task["prompt"][1]["content"], execute_tool=authoring_execute, emit=self.emit,''')
s=s.replace('        self.output = result.final_text or ""\n        return result\n\n\ndef handler', '''        if workflow_track and result.termination == "completed":
            from wb_studio.workflows import execute_workflow
            execution = execute_workflow(result.final_text or "", execute=execute, emit=self.emit,
                                         record=ep.record_agent_event, cancel=self.cancel, deadline=deadline)
            result.tool_calls += execution.tool_calls
            result.termination, result.error = execution.termination, execution.error
            result.final_text = execution.final_text or execution.error
        self.output = result.final_text or ""
        return result


def handler''')
# Track-specific artifact contract is distinct from the business task hash.
s=s.replace('                job["component_manifest"] = pins', '''                if track == "create-and-run":
                    import hashlib
                    from wb_studio import workflows
                    job["workflow_contract"] = {"format": "studio-workflow-v1", "runtime_sha256": hashlib.sha256(Path(workflows.__file__).read_bytes()).hexdigest(),
                                                "requirement": "saved workflow artifact plus execution"}
                job["component_manifest"] = pins''')
p.write_text(s,encoding='utf8')
p=Path('monarch-benchmark/workflowbench/wb_studio/leaderboard.py');s=p.read_text(encoding='utf8').replace("'world': job.get('world_manifest', 'historical-unpinned')", "'world': job.get('world_manifest', 'historical-unpinned'),\n                    'workflow_contract': job.get('workflow_contract', 'historical-unpinned') if settings.get('track')=='create-and-run' else None");p.write_text(s,encoding='utf8')
