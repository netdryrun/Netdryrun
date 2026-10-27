"""Make the bad change in NetBox: a typo in r3's address on the r2-r3 link.

10.0.23.2/30 becomes 10.0.23.6/30, which is outside the link's /30. Run with
--revert to put it back.

    python bad_change.py            # make the change
    python bad_change.py --revert   # undo it
"""

import os
import sys

import pynetbox

GOOD, BAD = "10.0.23.2/30", "10.0.23.6/30"


def main():
    nb = pynetbox.api(os.environ["NB_API_URL"], token=os.environ["NB_API_TOKEN"])
    old, new = (BAD, GOOD) if "--revert" in sys.argv else (GOOD, BAD)
    ip = nb.ipam.ip_addresses.get(address=old)
    if ip is None:
        sys.exit(f"{old} not found in NetBox (already changed?)")
    ip.update({"address": new})
    print(f"r3 eth1: {old} -> {new}")


if __name__ == "__main__":
    main()
