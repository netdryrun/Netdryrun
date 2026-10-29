```json
{
  "verdict": "dont_apply",
  "decision": "dont_apply",
  "netdryrun_status": "failed",
  "changed_files": [
    "configs/edge1.conf"
  ],
  "reason": "The new prefix 10.101.0.0/24 was added to CUSTOMER-IN but not to OUR-ROUTES, so it's not advertised to up1 and peer1."
}
```