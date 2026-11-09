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
"""

THREAD_QUIET = "agent.thread_quiet"
