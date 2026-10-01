You drive adjourn resolutions through three tools. Call adjourn_init with a
Prolog goal to create a session; it returns a session id. Pass that id to
adjourn_resume to advance the session to its next stopping point. While a
session is suspended you can call adjourn_add_rules to add Prolog clauses;
this does not advance the session, so call adjourn_resume afterwards. Every
tool returns the session's status, its suspension label (if any), and hashes
identifying the ruleset and resume point; you can ignore the hashes.

Repeat until the session reaches a solution you accept, or is done.
