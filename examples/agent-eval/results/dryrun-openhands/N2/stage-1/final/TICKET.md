# Incident INC-4410: is the upstream session flapping?

The NOC sees short traffic drops to the internet from our edge router **edge1** (AS 65000) since 06:00 today. Nothing was changed in the last week. [edge1-syslog.txt](edge1-syslog.txt) is edge1's log from this morning.

Questions from the on-call lead:

1. Is our BGP session to the upstream **up1** (10.0.2.2, AS 65200) flapping, and since when?
2. From the log, is the cause on our side or the upstream's? Should we open a ticket with the upstream?

- Don't change any configuration. This is production; nothing is to be applied.
