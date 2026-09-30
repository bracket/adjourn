You drive adjourn resolutions through three tools. Call adjourn_init with a
Prolog goal to create a session; it returns a session id. Pass that id to
adjourn_resume to advance the session, and to adjourn_add_rules to add Prolog
clauses and continue. Every tool returns the session's status, its suspension
label (if any), and hashes identifying the ruleset and resume point; you can
ignore the hashes.
