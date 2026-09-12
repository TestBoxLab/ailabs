# Mission data and tool contract

Card.mission is server-owned. It contains objective, acceptance, owner, origin turn,
thread, workspace, model, status, turn limit/count, current checkpoint/next action,
and wait target. Mutations use the card revision and preserve card history.

Tools: start_mission(objective, acceptance, next_action, optional title/max_turns),
mission_status(optional card), checkpoint_mission(card, revision, summary,
status=continue|waiting|complete|blocked, optional next_action/wait_for),
control_mission(card, revision, action=steer|resume|stop, optional instruction).

Plugin integration exports worker_payload(genesis, card) -> chat payload, reconcile(genesis)
for watcher wake, plus TOOLS, PROTOCOL, PROMPT, ON_TURN. Root calls worker_payload
instead of the ordinary read-only work brief. The payload retains origin owner/model,
workspace, purpose=Genesis mission and card identity; root assigns worker id/work lease.
Waiting targets are experiment card ids. Completion requires terminal linked work and
fresh evidence reads for completed runs. Stop persists before requesting cancellation.
