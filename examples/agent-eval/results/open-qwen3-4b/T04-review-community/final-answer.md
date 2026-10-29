```json
{
  "verdict": "harmful",
  "decision": "dont_apply",
  "netdryrun_status": "failed",
  "changed_files": [
    "configs/edge1.conf"
  ],
  "reason": "The dry run shows up1 is not receiving routes with the required 65200:100 community, indicating the change incorrectly configured the route-map."
}
```