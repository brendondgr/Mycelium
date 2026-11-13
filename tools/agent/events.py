"""Events the agent publishes (``tools._framework.events.publish``).

``agent.thread_quiet`` — a thread has been quiet long enough for the learning
pass and its owner has learning on. Payload:

    thread_id: str          the thread
    user_id: int            its owner (the only speaker whose words are sent)
    scope: str              personal | lab | department | project
    lab_id, department_id, project_id: the scope object's id, or None
    messages: list[dict]    {"seq", "ts", "text"} — the person's own messages
                            since the last pass, never the agent's
    title, purpose: str     the thread's title and purpose line

A subscriber (``apps.ambient``) records the messages as an ``agent_chat``
source. Handlers that raise make the pass back off and retry.

``agent.thread_deleted`` — the owner deleted a thread. Payload:

    thread_id: str          the deleted thread
    user_id: int            its owner

A subscriber (``apps.ambient``) retracts every message of that thread it
recorded, through the same path as a message deleted on a platform: the
observations go, a pending edge left without evidence goes, and what the
person already confirmed stays (they said yes to it, not to the chat).
Published before the thread row is deleted; a handler that raises stops the
deletion, so nothing is deleted while its evidence is left behind.
"""

THREAD_QUIET = "agent.thread_quiet"
THREAD_DELETED = "agent.thread_deleted"
