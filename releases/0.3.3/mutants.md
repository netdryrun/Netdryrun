# Surviving mutants, Netdryrun 0.3.3

Each mutant below is a deliberate change to the code that no test noticed. In verdict logic each is a BLOCKER until a test kills it or it is accepted as harmless in accepted.json with a reason.

## `config._describe` (91)

`netdryrun.config.x__describe__mutmut_10`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `119883003608ce08`

```diff
# netdryrun.config.x__describe__mutmut_10: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
-        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
+        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('established')}"
     if ctype == "bgp_prefixes":
         rng = []
         if "exact" in p:
```

`netdryrun.config.x__describe__mutmut_109`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `be516ffa1f60add1`

```diff
# netdryrun.config.x__describe__mutmut_109: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -20,7 +20,7 @@
         parts = []
         if p.get("communities"):
             parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
-        if p.get("without_communities"):
+        if p.get(None):
             parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
         if "as_path" in p:
             parts.append(f"as-path '{p['as_path']}'")
```

`netdryrun.config.x__describe__mutmut_11`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `d7b11751bd2d98a1`

```diff
# netdryrun.config.x__describe__mutmut_11: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
-        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
+        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', )}"
     if ctype == "bgp_prefixes":
         rng = []
         if "exact" in p:
```

`netdryrun.config.x__describe__mutmut_110`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `5dc028f6f0f80f8c`

```diff
# netdryrun.config.x__describe__mutmut_110: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -20,7 +20,7 @@
         parts = []
         if p.get("communities"):
             parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
-        if p.get("without_communities"):
+        if p.get("XXwithout_communitiesXX"):
             parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
         if "as_path" in p:
             parts.append(f"as-path '{p['as_path']}'")
```

`netdryrun.config.x__describe__mutmut_111`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `79bfc099077352f1`

```diff
# netdryrun.config.x__describe__mutmut_111: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -20,7 +20,7 @@
         parts = []
         if p.get("communities"):
             parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
-        if p.get("without_communities"):
+        if p.get("WITHOUT_COMMUNITIES"):
             parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
         if "as_path" in p:
             parts.append(f"as-path '{p['as_path']}'")
```

`netdryrun.config.x__describe__mutmut_114`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `b23cac60bb962b3d`

```diff
# netdryrun.config.x__describe__mutmut_114: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -21,7 +21,7 @@
         if p.get("communities"):
             parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
         if p.get("without_communities"):
-            parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
+            parts.append("XXno communities XX" + " ".join(community_name(c) for c in p["without_communities"]))
         if "as_path" in p:
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
```

`netdryrun.config.x__describe__mutmut_115`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `a4f5076d3a1abf07`

```diff
# netdryrun.config.x__describe__mutmut_115: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -21,7 +21,7 @@
         if p.get("communities"):
             parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
         if p.get("without_communities"):
-            parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
+            parts.append("NO COMMUNITIES " + " ".join(community_name(c) for c in p["without_communities"]))
         if "as_path" in p:
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
```

`netdryrun.config.x__describe__mutmut_117`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `425d313b5c0632b1`

```diff
# netdryrun.config.x__describe__mutmut_117: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -21,7 +21,7 @@
         if p.get("communities"):
             parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
         if p.get("without_communities"):
-            parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
+            parts.append("no communities " + "XX XX".join(community_name(c) for c in p["without_communities"]))
         if "as_path" in p:
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
```

`netdryrun.config.x__describe__mutmut_12`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `92a3d5ebe6413744`

```diff
# netdryrun.config.x__describe__mutmut_12: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
-        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
+        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('XXstateXX', 'established')}"
     if ctype == "bgp_prefixes":
         rng = []
         if "exact" in p:
```

`netdryrun.config.x__describe__mutmut_121`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `02e46c0bbf923a9d`

```diff
# netdryrun.config.x__describe__mutmut_121: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -22,7 +22,7 @@
             parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
         if p.get("without_communities"):
             parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
-        if "as_path" in p:
+        if "XXas_pathXX" in p:
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
```

`netdryrun.config.x__describe__mutmut_122`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `46d29fcd0d5f1988`

```diff
# netdryrun.config.x__describe__mutmut_122: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -22,7 +22,7 @@
             parts.append("communities " + " ".join(community_name(c) for c in p["communities"]))
         if p.get("without_communities"):
             parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
-        if "as_path" in p:
+        if "AS_PATH" in p:
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
```

`netdryrun.config.x__describe__mutmut_127`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `e7f275c554373380`

```diff
# netdryrun.config.x__describe__mutmut_127: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -24,7 +24,7 @@
             parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
         if "as_path" in p:
             parts.append(f"as-path '{p['as_path']}'")
-        if "as_path_regex" in p:
+        if "XXas_path_regexXX" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
         for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
```

`netdryrun.config.x__describe__mutmut_128`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `41a170e241487249`

```diff
# netdryrun.config.x__describe__mutmut_128: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -24,7 +24,7 @@
             parts.append("no communities " + " ".join(community_name(c) for c in p["without_communities"]))
         if "as_path" in p:
             parts.append(f"as-path '{p['as_path']}'")
-        if "as_path_regex" in p:
+        if "AS_PATH_REGEX" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
         for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
```

`netdryrun.config.x__describe__mutmut_13`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `864b4e2fa06f7140`

```diff
# netdryrun.config.x__describe__mutmut_13: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
-        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
+        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('STATE', 'established')}"
     if ctype == "bgp_prefixes":
         rng = []
         if "exact" in p:
```

`netdryrun.config.x__describe__mutmut_133`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `480a8263261bf31a`

```diff
# netdryrun.config.x__describe__mutmut_133: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("XXlocal_prefXX", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_134`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `92fe1f063e40778d`

```diff
# netdryrun.config.x__describe__mutmut_134: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("LOCAL_PREF", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_135`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `12ee689027933637`

```diff
# netdryrun.config.x__describe__mutmut_135: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "XXlocal-prefXX"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_136`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `277db75f2f94208e`

```diff
# netdryrun.config.x__describe__mutmut_136: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "LOCAL-PREF"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_137`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `90ba7efaaad59095`

```diff
# netdryrun.config.x__describe__mutmut_137: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "local-pref"), ("XXmedXX", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_138`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `8a8b5c96bb7f953c`

```diff
# netdryrun.config.x__describe__mutmut_138: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "local-pref"), ("MED", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_139`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `f03b52a600e84b59`

```diff
# netdryrun.config.x__describe__mutmut_139: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "local-pref"), ("med", "XXMEDXX"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_14`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `e68185333f9201ac`

```diff
# netdryrun.config.x__describe__mutmut_14: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
-        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
+        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'XXestablishedXX')}"
     if ctype == "bgp_prefixes":
         rng = []
         if "exact" in p:
```

`netdryrun.config.x__describe__mutmut_140`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `88884597233e7ec9`

```diff
# netdryrun.config.x__describe__mutmut_140: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "local-pref"), ("med", "med"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_141`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `80d7c9d64ee6eb85`

```diff
# netdryrun.config.x__describe__mutmut_141: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("XXnext_hopXX", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_142`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `232d0cab2391ee09`

```diff
# netdryrun.config.x__describe__mutmut_142: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("NEXT_HOP", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_143`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `15f88017d60f1018`

```diff
# netdryrun.config.x__describe__mutmut_143: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "XXnext hopXX")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_144`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `014c5f0c9d7b7240`

```diff
# netdryrun.config.x__describe__mutmut_144: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
             parts.append(f"as-path '{p['as_path']}'")
         if "as_path_regex" in p:
             parts.append(f"as-path matching /{p['as_path_regex']}/")
-        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
+        for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "NEXT HOP")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
```

`netdryrun.config.x__describe__mutmut_15`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `41dfeb9a744fddbe`

```diff
# netdryrun.config.x__describe__mutmut_15: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
-        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
+        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'ESTABLISHED')}"
     if ctype == "bgp_prefixes":
         rng = []
         if "exact" in p:
```

`netdryrun.config.x__describe__mutmut_153`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `fffbb7ac3a45c0e0`

```diff
# netdryrun.config.x__describe__mutmut_153: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -29,7 +29,7 @@
         for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
-        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
+        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if (parts) or True else "exists")
     if ctype == "ping":
         exp = p.get("expect", "success")
         src = f" from {p['source']}" if p.get("source") else ""
```

`netdryrun.config.x__describe__mutmut_155`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `22648212e7148f74`

```diff
# netdryrun.config.x__describe__mutmut_155: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -29,7 +29,7 @@
         for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
-        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
+        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {'XX, XX'.join(parts)}" if parts else "exists")
     if ctype == "ping":
         exp = p.get("expect", "success")
         src = f" from {p['source']}" if p.get("source") else ""
```

`netdryrun.config.x__describe__mutmut_156`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `92aee728800bdc76`

```diff
# netdryrun.config.x__describe__mutmut_156: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -29,7 +29,7 @@
         for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
-        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
+        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "XXexistsXX")
     if ctype == "ping":
         exp = p.get("expect", "success")
         src = f" from {p['source']}" if p.get("source") else ""
```

`netdryrun.config.x__describe__mutmut_157`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `ff99ff6f859b1603`

```diff
# netdryrun.config.x__describe__mutmut_157: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -29,7 +29,7 @@
         for key, label in (("local_pref", "local-pref"), ("med", "MED"), ("next_hop", "next hop")):
             if key in p:
                 parts.append(f"{label} {p[key]}")
-        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
+        return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "EXISTS")
     if ctype == "ping":
         exp = p.get("expect", "success")
         src = f" from {p['source']}" if p.get("source") else ""
```

`netdryrun.config.x__describe__mutmut_158`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `7e2126cd62b98444`

```diff
# netdryrun.config.x__describe__mutmut_158: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -30,7 +30,7 @@
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
-    if ctype == "ping":
+    if ctype != "ping":
         exp = p.get("expect", "success")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
```

`netdryrun.config.x__describe__mutmut_159`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `fc0cf270b64504b3`

```diff
# netdryrun.config.x__describe__mutmut_159: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -30,7 +30,7 @@
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
-    if ctype == "ping":
+    if ctype == "XXpingXX":
         exp = p.get("expect", "success")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
```

`netdryrun.config.x__describe__mutmut_160`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `4a7aa19c26a8d3ef`

```diff
# netdryrun.config.x__describe__mutmut_160: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -30,7 +30,7 @@
             if key in p:
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
-    if ctype == "ping":
+    if ctype == "PING":
         exp = p.get("expect", "success")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
```

`netdryrun.config.x__describe__mutmut_161`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `1246a1934c701631`

```diff
# netdryrun.config.x__describe__mutmut_161: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = None
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_162`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `c59252a488c5525c`

```diff
# netdryrun.config.x__describe__mutmut_162: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = p.get(None, "success")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_163`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `33d8161c5e455eee`

```diff
# netdryrun.config.x__describe__mutmut_163: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = p.get("expect", None)
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_164`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `bcd38edd8b3c3cab`

```diff
# netdryrun.config.x__describe__mutmut_164: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = p.get("success")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_165`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `b9b18df88aa81c13`

```diff
# netdryrun.config.x__describe__mutmut_165: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = p.get("expect", )
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_166`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `86175ceb2cd9dd7d`

```diff
# netdryrun.config.x__describe__mutmut_166: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = p.get("XXexpectXX", "success")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_167`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `a97bf2c99fc07dcd`

```diff
# netdryrun.config.x__describe__mutmut_167: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = p.get("EXPECT", "success")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_168`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `1b58a31b4c56b5ba`

```diff
# netdryrun.config.x__describe__mutmut_168: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = p.get("expect", "XXsuccessXX")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_169`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `7d3f338a853998fb`

```diff
# netdryrun.config.x__describe__mutmut_169: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -31,7 +31,7 @@
                 parts.append(f"{label} {p[key]}")
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
-        exp = p.get("expect", "success")
+        exp = p.get("expect", "SUCCESS")
         src = f" from {p['source']}" if p.get("source") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_17`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `011ececea33ab6f4`

```diff
# netdryrun.config.x__describe__mutmut_17: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
         return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
-    if ctype == "bgp_prefixes":
+    if ctype == "XXbgp_prefixesXX":
         rng = []
         if "exact" in p:
             rng.append(f"= {p['exact']}")
```

`netdryrun.config.x__describe__mutmut_170`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `ec19a9d31b6f3987`

```diff
# netdryrun.config.x__describe__mutmut_170: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,6 +32,6 @@
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
         exp = p.get("expect", "success")
-        src = f" from {p['source']}" if p.get("source") else ""
+        src = None
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_171`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `26748e0573d9fc3d`

```diff
# netdryrun.config.x__describe__mutmut_171: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,6 +32,6 @@
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
         exp = p.get("expect", "success")
-        src = f" from {p['source']}" if p.get("source") else ""
+        src = f" from {p['source']}" if (p.get("source")) and False else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_175`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `f78e7f8a6ad65335`

```diff
# netdryrun.config.x__describe__mutmut_175: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,6 +32,6 @@
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
         exp = p.get("expect", "success")
-        src = f" from {p['source']}" if p.get("source") else ""
+        src = f" from {p['source']}" if p.get(None) else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_176`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `2b8c9eb8e990c2bf`

```diff
# netdryrun.config.x__describe__mutmut_176: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,6 +32,6 @@
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
         exp = p.get("expect", "success")
-        src = f" from {p['source']}" if p.get("source") else ""
+        src = f" from {p['source']}" if p.get("XXsourceXX") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_177`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `3529a0a5c1bdd494`

```diff
# netdryrun.config.x__describe__mutmut_177: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,6 +32,6 @@
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
         exp = p.get("expect", "success")
-        src = f" from {p['source']}" if p.get("source") else ""
+        src = f" from {p['source']}" if p.get("SOURCE") else ""
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_178`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `4c8933d252c1a61b`

```diff
# netdryrun.config.x__describe__mutmut_178: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,6 +32,6 @@
         return f"{p['node']}: BGP best path for {p['prefix']} " + (f"has {', '.join(parts)}" if parts else "exists")
     if ctype == "ping":
         exp = p.get("expect", "success")
-        src = f" from {p['source']}" if p.get("source") else ""
+        src = f" from {p['source']}" if p.get("source") else "XXXX"
         return f"{p['node']}: ping {p['target']}{src} expects {exp}"
     return ctype
```

`netdryrun.config.x__describe__mutmut_18`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `c62cd25b12ab556d`

```diff
# netdryrun.config.x__describe__mutmut_18: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
         return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
-    if ctype == "bgp_prefixes":
+    if ctype == "BGP_PREFIXES":
         rng = []
         if "exact" in p:
             rng.append(f"= {p['exact']}")
```

`netdryrun.config.x__describe__mutmut_2`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `19563ae2c42d8b5d`

```diff
# netdryrun.config.x__describe__mutmut_2: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,5 +1,5 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
-    if ctype == "bgp_session":
+    if ctype == "XXbgp_sessionXX":
         return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
     if ctype == "bgp_prefixes":
         rng = []
```

`netdryrun.config.x__describe__mutmut_20`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `bb8a1b5f88e1cc22`

```diff
# netdryrun.config.x__describe__mutmut_20: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -3,7 +3,7 @@
         return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
     if ctype == "bgp_prefixes":
         rng = []
-        if "exact" in p:
+        if "XXexactXX" in p:
             rng.append(f"= {p['exact']}")
         if "min" in p:
             rng.append(f">= {p['min']}")
```

`netdryrun.config.x__describe__mutmut_21`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `69044af46d015465`

```diff
# netdryrun.config.x__describe__mutmut_21: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -3,7 +3,7 @@
         return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
     if ctype == "bgp_prefixes":
         rng = []
-        if "exact" in p:
+        if "EXACT" in p:
             rng.append(f"= {p['exact']}")
         if "min" in p:
             rng.append(f">= {p['min']}")
```

`netdryrun.config.x__describe__mutmut_26`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `923f0ee2c1138be3`

```diff
# netdryrun.config.x__describe__mutmut_26: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,7 +5,7 @@
         rng = []
         if "exact" in p:
             rng.append(f"= {p['exact']}")
-        if "min" in p:
+        if "XXminXX" in p:
             rng.append(f">= {p['min']}")
         if "max" in p:
             rng.append(f"<= {p['max']}")
```

`netdryrun.config.x__describe__mutmut_27`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `c22cbe79f0d0e71e`

```diff
# netdryrun.config.x__describe__mutmut_27: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,7 +5,7 @@
         rng = []
         if "exact" in p:
             rng.append(f"= {p['exact']}")
-        if "min" in p:
+        if "MIN" in p:
             rng.append(f">= {p['min']}")
         if "max" in p:
             rng.append(f"<= {p['max']}")
```

`netdryrun.config.x__describe__mutmut_3`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `15d69c1de9d9d8ca`

```diff
# netdryrun.config.x__describe__mutmut_3: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,5 +1,5 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
-    if ctype == "bgp_session":
+    if ctype == "BGP_SESSION":
         return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
     if ctype == "bgp_prefixes":
         rng = []
```

`netdryrun.config.x__describe__mutmut_32`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `ac71470945ecb139`

```diff
# netdryrun.config.x__describe__mutmut_32: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -7,7 +7,7 @@
             rng.append(f"= {p['exact']}")
         if "min" in p:
             rng.append(f">= {p['min']}")
-        if "max" in p:
+        if "XXmaxXX" in p:
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
```

`netdryrun.config.x__describe__mutmut_33`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `e480de9ce78d2329`

```diff
# netdryrun.config.x__describe__mutmut_33: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -7,7 +7,7 @@
             rng.append(f"= {p['exact']}")
         if "min" in p:
             rng.append(f">= {p['min']}")
-        if "max" in p:
+        if "MAX" in p:
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
```

`netdryrun.config.x__describe__mutmut_42`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `a567a67e1f332cb4`

```diff
# netdryrun.config.x__describe__mutmut_42: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -9,7 +9,7 @@
             rng.append(f">= {p['min']}")
         if "max" in p:
             rng.append(f"<= {p['max']}")
-        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
+        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) and 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
```

`netdryrun.config.x__describe__mutmut_44`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `290fccd6eaf67190`

```diff
# netdryrun.config.x__describe__mutmut_44: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -9,7 +9,7 @@
             rng.append(f">= {p['min']}")
         if "max" in p:
             rng.append(f"<= {p['max']}")
-        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
+        return f"{p['node']}: prefixes from {p['neighbor']} {'XX and XX'.join(rng) or 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
```

`netdryrun.config.x__describe__mutmut_45`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `b8efd68372132ea8`

```diff
# netdryrun.config.x__describe__mutmut_45: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -9,7 +9,7 @@
             rng.append(f">= {p['min']}")
         if "max" in p:
             rng.append(f"<= {p['max']}")
-        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
+        return f"{p['node']}: prefixes from {p['neighbor']} {' AND '.join(rng) or 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
```

`netdryrun.config.x__describe__mutmut_46`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `e011a852fca48323`

```diff
# netdryrun.config.x__describe__mutmut_46: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -9,7 +9,7 @@
             rng.append(f">= {p['min']}")
         if "max" in p:
             rng.append(f"<= {p['max']}")
-        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
+        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'XXcountedXX'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
```

`netdryrun.config.x__describe__mutmut_47`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `1d552928e18db97f`

```diff
# netdryrun.config.x__describe__mutmut_47: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -9,7 +9,7 @@
             rng.append(f">= {p['min']}")
         if "max" in p:
             rng.append(f"<= {p['max']}")
-        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
+        return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'COUNTED'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
```

`netdryrun.config.x__describe__mutmut_51`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `9b359a9d7a8d67b5`

```diff
# netdryrun.config.x__describe__mutmut_51: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = None
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_52`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `4c8bd2f11a703b5e`

```diff
# netdryrun.config.x__describe__mutmut_52: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if (p.get("present", True) is False) and False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_53`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `05b5984085885247`

```diff
# netdryrun.config.x__describe__mutmut_53: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if (p.get("present", True) is False) or True else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_54`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `be77d6b89f987716`

```diff
# netdryrun.config.x__describe__mutmut_54: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "XXabsentXX" if p.get("present", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_55`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `fd72a028b9c1bcf5`

```diff
# netdryrun.config.x__describe__mutmut_55: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "ABSENT" if p.get("present", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_56`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `5f06e8f3cca07716`

```diff
# netdryrun.config.x__describe__mutmut_56: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get(None, True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_57`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `1a0503ef804ae5b3`

```diff
# netdryrun.config.x__describe__mutmut_57: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("present", None) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_58`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `980576cbdcd6bd88`

```diff
# netdryrun.config.x__describe__mutmut_58: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get(True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_59`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `d7888f41171a1028`

```diff
# netdryrun.config.x__describe__mutmut_59: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("present", ) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_60`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `949075863cbf475e`

```diff
# netdryrun.config.x__describe__mutmut_60: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("XXpresentXX", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_61`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `a81da37cea9f311e`

```diff
# netdryrun.config.x__describe__mutmut_61: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("PRESENT", True) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_62`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `7a0bb32f2b45faab`

```diff
# netdryrun.config.x__describe__mutmut_62: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("present", False) is False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_63`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `640b4419a93b6287`

```diff
# netdryrun.config.x__describe__mutmut_63: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("present", True) is not False else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_64`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `4b7c873667162186`

```diff
# netdryrun.config.x__describe__mutmut_64: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("present", True) is True else "present"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_65`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `03d7c8cc1a1309c8`

```diff
# netdryrun.config.x__describe__mutmut_65: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("present", True) is False else "XXpresentXX"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_66`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `d6ffda7fc1a6d45d`

```diff
# netdryrun.config.x__describe__mutmut_66: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
             rng.append(f"<= {p['max']}")
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
-        verb = "absent" if p.get("present", True) is False else "present"
+        verb = "absent" if p.get("present", True) is False else "PRESENT"
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
```

`netdryrun.config.x__describe__mutmut_67`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `517aa5cdffcd0bce`

```diff
# netdryrun.config.x__describe__mutmut_67: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,7 +12,7 @@
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
-        via = f" via {p['protocol']}" if p.get("protocol") else ""
+        via = None
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
         if p.get("present", True) is False:
```

`netdryrun.config.x__describe__mutmut_68`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `82a367f01c2cbae1`

```diff
# netdryrun.config.x__describe__mutmut_68: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,7 +12,7 @@
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
-        via = f" via {p['protocol']}" if p.get("protocol") else ""
+        via = f" via {p['protocol']}" if (p.get("protocol")) and False else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
         if p.get("present", True) is False:
```

`netdryrun.config.x__describe__mutmut_72`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `314d76916233fadd`

```diff
# netdryrun.config.x__describe__mutmut_72: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,7 +12,7 @@
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
-        via = f" via {p['protocol']}" if p.get("protocol") else ""
+        via = f" via {p['protocol']}" if p.get(None) else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
         if p.get("present", True) is False:
```

`netdryrun.config.x__describe__mutmut_73`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `6e8b8b743a71cf27`

```diff
# netdryrun.config.x__describe__mutmut_73: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,7 +12,7 @@
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
-        via = f" via {p['protocol']}" if p.get("protocol") else ""
+        via = f" via {p['protocol']}" if p.get("XXprotocolXX") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
         if p.get("present", True) is False:
```

`netdryrun.config.x__describe__mutmut_74`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `eff1e5ef648b1bf1`

```diff
# netdryrun.config.x__describe__mutmut_74: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,7 +12,7 @@
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
-        via = f" via {p['protocol']}" if p.get("protocol") else ""
+        via = f" via {p['protocol']}" if p.get("PROTOCOL") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
         if p.get("present", True) is False:
```

`netdryrun.config.x__describe__mutmut_75`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `f4fb0b845b32737d`

```diff
# netdryrun.config.x__describe__mutmut_75: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,7 +12,7 @@
         return f"{p['node']}: prefixes from {p['neighbor']} {' and '.join(rng) or 'counted'}"
     if ctype == "route":
         verb = "absent" if p.get("present", True) is False else "present"
-        via = f" via {p['protocol']}" if p.get("protocol") else ""
+        via = f" via {p['protocol']}" if p.get("protocol") else "XXXX"
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
         if p.get("present", True) is False:
```

`netdryrun.config.x__describe__mutmut_8`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `9b901300fcef415f`

```diff
# netdryrun.config.x__describe__mutmut_8: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
-        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
+        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get(None, 'established')}"
     if ctype == "bgp_prefixes":
         rng = []
         if "exact" in p:
```

`netdryrun.config.x__describe__mutmut_84`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `c7964f0c3e690917`

```diff
# netdryrun.config.x__describe__mutmut_84: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -15,7 +15,7 @@
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
-        if p.get("present", True) is False:
+        if p.get("present", None) is False:
             return f"{p['node']}: no BGP path for {p['prefix']}"
         parts = []
         if p.get("communities"):
```

`netdryrun.config.x__describe__mutmut_86`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `6af6381b01d7f6b5`

```diff
# netdryrun.config.x__describe__mutmut_86: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -15,7 +15,7 @@
         via = f" via {p['protocol']}" if p.get("protocol") else ""
         return f"{p['node']}: route {p['prefix']}{via} is {verb}"
     if ctype == "bgp_route":
-        if p.get("present", True) is False:
+        if p.get("present", ) is False:
             return f"{p['node']}: no BGP path for {p['prefix']}"
         parts = []
         if p.get("communities"):
```

`netdryrun.config.x__describe__mutmut_9`: survived (accepted, message-text: message text only: the default check name shown in reports); diff fingerprint `98a4e10973239a81`

```diff
# netdryrun.config.x__describe__mutmut_9: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _describe(ctype: str, p: dict[str, Any]) -> str:
     if ctype == "bgp_session":
-        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', 'established')}"
+        return f"{p['node']}: BGP session to {p['neighbor']} is {p.get('state', None)}"
     if ctype == "bgp_prefixes":
         rng = []
         if "exact" in p:
```

## `runner._bgp_convergence_gate` (73)

`netdryrun.runner.x__bgp_convergence_gate__mutmut_129`: survived (accepted, message-text: message text only: the detail text of a failing gate sample; it is still an Unready detail, so the sample stays unready); argument: Changes only text: the detail text of a failing gate sample; it is still an Unready detail, so the sample stays unready. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `f558f63faac9328b`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_129: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -38,7 +38,7 @@
                 if first and all(c.type == "ping" for c in groups[g]):
                     pending.discard(g)   # not a BGP speaker; nothing to wait for
                     continue
-                s["streak"], s["detail"], s["empty"] = 0, Unready(f"BGP state unreadable on {node}: {e}"), False
+                s["streak"], s["detail"], s["empty"] = 0, Unready(None), False
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
             s["answered"] = True
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_153`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: On a non-default VRF with no neighbors, `where=None` is interpolated as the text `None`, so the detail remains an `Unready` and verdict/counts are unchanged; this is only a message (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `ee77631a3057eaa0`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_153: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -46,7 +46,7 @@
             if not nbrs:
                 # No neighbors at all is what a node answers before its BGP config is applied: not converged
                 # (a leak can arrive once it is), so keep waiting, up to the cap
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = None
                 s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_154`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `afe8e0ef1c70c717`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_154: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -46,7 +46,7 @@
             if not nbrs:
                 # No neighbors at all is what a node answers before its BGP config is applied: not converged
                 # (a leak can arrive once it is), so keep waiting, up to the cap
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if (vrf == "default") and False else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_155`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `5a7a32805de5fe28`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_155: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -46,7 +46,7 @@
             if not nbrs:
                 # No neighbors at all is what a node answers before its BGP config is applied: not converged
                 # (a leak can arrive once it is), so keep waiting, up to the cap
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if (vrf == "default") or True else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_156`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `2782258b74b4054c`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_156: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -46,7 +46,7 @@
             if not nbrs:
                 # No neighbors at all is what a node answers before its BGP config is applied: not converged
                 # (a leak can arrive once it is), so keep waiting, up to the cap
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "XXXX" if vrf == "default" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_157`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: On default VRF with no neighbors, the mutant adds `(vrf default)` to the detail; type remains `Unready`, so no verdict change. (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `b8d663b353c725d7`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_157: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -46,7 +46,7 @@
             if not nbrs:
                 # No neighbors at all is what a node answers before its BGP config is applied: not converged
                 # (a leak can arrive once it is), so keep waiting, up to the cap
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf != "default" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_158`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: On VRF `blue` with no neighbors, the mutant omits `(vrf blue)` from the detail; type remains `Unready`, so no verdict change. (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `734e87112b25e71d`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_158: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -46,7 +46,7 @@
             if not nbrs:
                 # No neighbors at all is what a node answers before its BGP config is applied: not converged
                 # (a leak can arrive once it is), so keep waiting, up to the cap
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf == "XXdefaultXX" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_159`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: On default VRF with no neighbors, the mutant adds `(vrf default)` to the detail; type remains `Unready`, so no verdict change. (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `31572a51f62417e2`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_159: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -46,7 +46,7 @@
             if not nbrs:
                 # No neighbors at all is what a node answers before its BGP config is applied: not converged
                 # (a leak can arrive once it is), so keep waiting, up to the cap
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf == "DEFAULT" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_166`: survived (accepted, message-text: message text only: the detail text of a failing gate sample; it is still an Unready detail, so the sample stays unready); argument: Changes only text: the detail text of a failing gate sample; it is still an Unready detail, so the sample stays unready. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `61c9ea5dd917527a`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_166: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -47,7 +47,7 @@
                 # No neighbors at all is what a node answers before its BGP config is applied: not converged
                 # (a leak can arrive once it is), so keep waiting, up to the cap
                 where = "" if vrf == "default" else f" (vrf {vrf})"
-                s["streak"], s["detail"] = 0, Unready(f"no BGP neighbors at all on {node}{where}")
+                s["streak"], s["detail"] = 0, Unready(None)
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
             down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_187`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: If a down session is observed on VRF `blue`, `where=None` is interpolated into the detail as `None`; it is a plain string in either version, not `Unready`. Verdict and gate state r (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `c0b82fe2f3382265`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_187: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -53,7 +53,7 @@
             down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
                           if n.state != "established" and (node, vrf, a) not in excluded)
             if down:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = None
                 s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_188`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `eb55ad8409bd3d25`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_188: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -53,7 +53,7 @@
             down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
                           if n.state != "established" and (node, vrf, a) not in excluded)
             if down:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if (vrf == "default") and False else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_189`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `927bfe7ad64f82d4`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_189: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -53,7 +53,7 @@
             down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
                           if n.state != "established" and (node, vrf, a) not in excluded)
             if down:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if (vrf == "default") or True else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_190`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `621361111e929dbd`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_190: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -53,7 +53,7 @@
             down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
                           if n.state != "established" and (node, vrf, a) not in excluded)
             if down:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "XXXX" if vrf == "default" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_191`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: For a down session in the default VRF, the mutant appends `(vrf default)` to the detail; it remains a plain string and does not alter streak or verdict. (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `ba56f671f597d5b8`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_191: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -53,7 +53,7 @@
             down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
                           if n.state != "established" and (node, vrf, a) not in excluded)
             if down:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf != "default" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_192`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: For a down session in VRF `blue`, the mutant omits `(vrf blue)` from the detail; it remains a plain string and does not alter streak or verdict. (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `fd6f6d13ed40a052`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_192: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -53,7 +53,7 @@
             down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
                           if n.state != "established" and (node, vrf, a) not in excluded)
             if down:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf == "XXdefaultXX" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_193`: survived (accepted, message-text: message text only: the VRF part of the no-neighbors detail text; it is still an Unready detail); argument: Changes only text: the VRF part of the no-neighbors detail text; it is still an Unready detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: For a down session in the default VRF, the mutant appends `(vrf default)` to the detail; it remains a plain string and does not alter streak or verdict. (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `5bea4b3e7790b58f`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_193: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -53,7 +53,7 @@
             down = sorted(f"{a} ({n.state})" for a, n in nbrs.items()
                           if n.state != "established" and (node, vrf, a) not in excluded)
             if down:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf == "DEFAULT" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_201`: survived (accepted, message-text: message text only: the detail text of a gate result or gate warning; same verdict, same passed/unready sample flags and counts); argument: Changes only text: the detail text of a gate result or gate warning; same verdict, same passed/unready sample flags and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `d5e9fb56b3a8acfb`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_201: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -54,7 +54,7 @@
                           if n.state != "established" and (node, vrf, a) not in excluded)
             if down:
                 where = "" if vrf == "default" else f" (vrf {vrf})"
-                s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
+                s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {'XX, XX'.join(down)}"
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
             counts = {a: dict(n.prefixes) for a, n in nbrs.items()}
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_207`: survived (accepted, message-text: message text only: the detail text of a down-session history sample (a plain string either way, never unready)); argument: Changes only text: the detail text of a down-session history sample (a plain string either way, never unready). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: On a down-session sample, `_sample(t, False, None)` stores detail `"None"` rather than the real explanation; the sample remains failing and not unready. The gate still resets strea (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `285890f8f983e833`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_207: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -55,7 +55,7 @@
             if down:
                 where = "" if vrf == "default" else f" (vrf {vrf})"
                 s["streak"], s["detail"] = 0, f"BGP session(s) on {node}{where} not established: {', '.join(down)}"
-                s["history"].append(_sample(t, False, s["detail"]))
+                s["history"].append(_sample(t, False, None))
                 continue
             counts = {a: dict(n.prefixes) for a, n in nbrs.items()}
             s["streak"] = s["streak"] + 1 if s["streak"] and counts == s["counts"] else 1
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_225`: survived (accepted, equivalent: equivalent: the streak is only compared with >= 2 and == 0, and a streak that grows by 2 instead of 1 crosses both on the same sample); argument: Same behaviour on every input the function can receive: the streak is only compared with >= 2 and == 0, and a streak that grows by 2 instead of 1 crosses both on the same sample. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: If BGP neighbor counts are stable on two successive answered samples, the real streak advances 1 then 2 and removes the group from `pending` after sample two. The mutant advances 1 (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `cddeed32544cd70d`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_225: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -58,7 +58,7 @@
                 s["history"].append(_sample(t, False, s["detail"]))
                 continue
             counts = {a: dict(n.prefixes) for a, n in nbrs.items()}
-            s["streak"] = s["streak"] + 1 if s["streak"] and counts == s["counts"] else 1
+            s["streak"] = s["streak"] + 2 if s["streak"] and counts == s["counts"] else 1
             s["counts"] = counts
             s["history"].append(_sample(t, True, "every BGP session established"))
             if s["streak"] >= 2:
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_241`: survived (accepted, message-text: message text only: the detail text of one history sample; its passed and unready flags are unchanged); argument: Changes only text: the detail text of one history sample; its passed and unready flags are unchanged. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: no verdict change in its own words: A successful gate history sample gets detail `"None"` rather than `"every BGP session established"`; `passed=True` and `unready` is absent in either case. Counts and verdict are un (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `a46cb9a76a26a1b5`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_241: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -60,7 +60,7 @@
             counts = {a: dict(n.prefixes) for a, n in nbrs.items()}
             s["streak"] = s["streak"] + 1 if s["streak"] and counts == s["counts"] else 1
             s["counts"] = counts
-            s["history"].append(_sample(t, True, "every BGP session established"))
+            s["history"].append(_sample(t, True, None))
             if s["streak"] >= 2:
                 pending.discard(g)
         first = False
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_246`: survived (accepted, message-text: message text only: the detail text of one history sample; its passed and unready flags are unchanged); argument: Changes only text: the detail text of one history sample; its passed and unready flags are unchanged. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `4ce2949d4dd53f3f`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_246: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -60,7 +60,7 @@
             counts = {a: dict(n.prefixes) for a, n in nbrs.items()}
             s["streak"] = s["streak"] + 1 if s["streak"] and counts == s["counts"] else 1
             s["counts"] = counts
-            s["history"].append(_sample(t, True, "every BGP session established"))
+            s["history"].append(_sample(t, True, "XXevery BGP session establishedXX"))
             if s["streak"] >= 2:
                 pending.discard(g)
         first = False
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_247`: survived (accepted, message-text: message text only: the detail text of one history sample; its passed and unready flags are unchanged); argument: Changes only text: the detail text of one history sample; its passed and unready flags are unchanged. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `0a12a4dd4421a015`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_247: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -60,7 +60,7 @@
             counts = {a: dict(n.prefixes) for a, n in nbrs.items()}
             s["streak"] = s["streak"] + 1 if s["streak"] and counts == s["counts"] else 1
             s["counts"] = counts
-            s["history"].append(_sample(t, True, "every BGP session established"))
+            s["history"].append(_sample(t, True, "every bgp session established"))
             if s["streak"] >= 2:
                 pending.discard(g)
         first = False
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_248`: survived (accepted, message-text: message text only: the detail text of one history sample; its passed and unready flags are unchanged); argument: Changes only text: the detail text of one history sample; its passed and unready flags are unchanged. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `11be0c19663fde7a`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_248: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -60,7 +60,7 @@
             counts = {a: dict(n.prefixes) for a, n in nbrs.items()}
             s["streak"] = s["streak"] + 1 if s["streak"] and counts == s["counts"] else 1
             s["counts"] = counts
-            s["history"].append(_sample(t, True, "every BGP session established"))
+            s["history"].append(_sample(t, True, "EVERY BGP SESSION ESTABLISHED"))
             if s["streak"] >= 2:
                 pending.discard(g)
         first = False
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_254`: survived (accepted, equivalent: equivalent: `first` is only tested for truth; None and False are both false); argument: Same behaviour on every input the function can receive: `first` is only tested for truth; None and False are both false. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `39bd4f7076e09175`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_254: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -63,7 +63,7 @@
             s["history"].append(_sample(t, True, "every BGP session established"))
             if s["streak"] >= 2:
                 pending.discard(g)
-        first = False
+        first = None
         if not pending:
             break
         t = _clock() - t0
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_268`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `c5367845bf4c1803`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_268: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -73,7 +73,7 @@
             pending.discard(g)
             s = st[g]
             if not s["answered"]:
-                log(f"warning: {g[0]} never returned BGP state; its post-convergence checks start without the BGP gate")
+                log(None)
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_269`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `8747ad78ef288ee8`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_269: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -73,7 +73,7 @@
             pending.discard(g)
             s = st[g]
             if not s["answered"]:
-                log(f"warning: {g[0]} never returned BGP state; its post-convergence checks start without the BGP gate")
+                log(f"warning: {g[1]} never returned BGP state; its post-convergence checks start without the BGP gate")
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_275`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `7704580a6d39f5a7`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_275: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -77,7 +77,7 @@
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = None
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_276`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `1e5b2542259d89d0`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_276: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -77,7 +77,7 @@
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if (g[1] == "default") and False else f" (vrf {g[1]})"
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_277`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `7e43d73b3db2c465`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_277: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -77,7 +77,7 @@
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if (g[1] == "default") or True else f" (vrf {g[1]})"
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_278`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `fd5766df744a9080`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_278: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -77,7 +77,7 @@
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "XXXX" if g[1] == "default" else f" (vrf {g[1]})"
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_280`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `f8e7515fe23996ae`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_280: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -77,7 +77,7 @@
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if g[1] != "default" else f" (vrf {g[1]})"
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_281`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `b3604f256ff882b9`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_281: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -77,7 +77,7 @@
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if g[1] == "XXdefaultXX" else f" (vrf {g[1]})"
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_282`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `b2cf598c05f86ef5`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_282: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -77,7 +77,7 @@
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if g[1] == "DEFAULT" else f" (vrf {g[1]})"
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_283`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `6534956c00321b3d`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_283: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -77,7 +77,7 @@
             elif s["empty"] and g[0] in bgp_nodes:
                 # Still no neighbors at the cap on a node the file says runs BGP: its config never loaded, and a
                 # leak guard would pass on the empty table. Not evaluated, every sample unready.
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if g[1] == "default" else f" (vrf {g[2]})"
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_287`: survived (accepted, message-text: message text only: the explanation in a not-evaluated detail; the result is still failed and unready); argument: Changes only text: the explanation in a not-evaluated detail; the result is still failed and unready. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `039ab250be58d127`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_287: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -81,7 +81,7 @@
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
-                                     "post-convergence check means nothing before the node's BGP sessions exist")
+                                     "XXpost-convergence check means nothing before the node's BGP sessions existXX")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                             s["history"][-50:], samples_passed=0,
                                             samples_unready=len(s["history"]))
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_288`: survived (accepted, message-text: message text only: the explanation in a not-evaluated detail; the result is still failed and unready); argument: Changes only text: the explanation in a not-evaluated detail; the result is still failed and unready. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `1ec62bfe261e0ab6`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_288: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -81,7 +81,7 @@
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
-                                     "post-convergence check means nothing before the node's BGP sessions exist")
+                                     "post-convergence check means nothing before the node's bgp sessions exist")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                             s["history"][-50:], samples_passed=0,
                                             samples_unready=len(s["history"]))
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_289`: survived (accepted, message-text: message text only: the explanation in a not-evaluated detail; the result is still failed and unready); argument: Changes only text: the explanation in a not-evaluated detail; the result is still failed and unready. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `09cac8378d372f0e`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_289: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -81,7 +81,7 @@
                 for c in groups[g]:
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
-                                     "post-convergence check means nothing before the node's BGP sessions exist")
+                                     "POST-CONVERGENCE CHECK MEANS NOTHING BEFORE THE NODE'S BGP SESSIONS EXIST")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                             s["history"][-50:], samples_passed=0,
                                             samples_unready=len(s["history"]))
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_310`: survived (accepted, equivalent: equivalent: Result.samples_passed defaults to 0, the value passed explicitly); argument: Same behaviour on every input the function can receive: Result.samples_passed defaults to 0, the value passed explicitly. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `1c94946ffcb7bf45`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_310: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -83,8 +83,7 @@
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
                                      "post-convergence check means nothing before the node's BGP sessions exist")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
-                                            s["history"][-50:], samples_passed=0,
-                                            samples_unready=len(s["history"]))
+                                            s["history"][-50:], samples_unready=len(s["history"]))
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_317`: survived (accepted, timing-only: report precision only: the duration of a not-evaluated result rounded to 2 decimals instead of 1; same verdict); argument: Changes only a reported duration: the duration of a not-evaluated result rounded to 2 decimals instead of 1; same verdict. No verdict reads it.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `9838a9f0caab3a8b`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_317: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -82,7 +82,7 @@
                     detail = Unready(f"not evaluated: {g[0]} reported no BGP neighbors{where} by the cap "
                                      f"({deadline[g]:g}s), although checks in the file expect BGP on it. A "
                                      "post-convergence check means nothing before the node's BGP sessions exist")
-                    blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
+                    blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 2), started, [],
                                             s["history"][-50:], samples_passed=0,
                                             samples_unready=len(s["history"]))
             elif s["empty"]:
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_325`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `04a41fbfa671f521`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_325: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -88,7 +88,7 @@
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = None
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_326`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `18f0998ac654ede7`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_326: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -88,7 +88,7 @@
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if (g[1] == "default") and False else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_327`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `24937f705a6f0135`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_327: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -88,7 +88,7 @@
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if (g[1] == "default") or True else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_328`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `1b2b82a7d53a7a8e`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_328: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -88,7 +88,7 @@
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "XXXX" if g[1] == "default" else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_330`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `5b1020c13f1290a5`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_330: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -88,7 +88,7 @@
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if g[1] != "default" else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_331`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `1b404554fa09fe8b`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_331: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -88,7 +88,7 @@
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if g[1] == "XXdefaultXX" else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_332`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `89e3f734f76176d5`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_332: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -88,7 +88,7 @@
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if g[1] == "DEFAULT" else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_333`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `4f0b22b6464c0fc8`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_333: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -88,7 +88,7 @@
             elif s["empty"]:
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
-                where = "" if g[1] == "default" else f" (vrf {g[1]})"
+                where = "" if g[1] == "default" else f" (vrf {g[2]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_335`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `aaa56ec4ef3a8c51`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_335: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -89,7 +89,7 @@
                 # Still no neighbors at the cap, and no BGP check on the node anywhere in the file: it may not run
                 # BGP at all (static routing). Go ahead, but say so on each check
                 where = "" if g[1] == "default" else f" (vrf {g[1]})"
-                text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
+                text = (f"{g[1]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
                 log(f"warning: {text}")
                 if warnings is not None:
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_336`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `42c77c6b64942829`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_336: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -90,7 +90,7 @@
                 # BGP at all (static routing). Go ahead, but say so on each check
                 where = "" if g[1] == "default" else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
-                        "without BGP convergence")
+                        "XXwithout BGP convergenceXX")
                 log(f"warning: {text}")
                 if warnings is not None:
                     for c in groups[g]:
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_337`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `0be2e83ef91cc84f`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_337: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -90,7 +90,7 @@
                 # BGP at all (static routing). Go ahead, but say so on each check
                 where = "" if g[1] == "default" else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
-                        "without BGP convergence")
+                        "without bgp convergence")
                 log(f"warning: {text}")
                 if warnings is not None:
                     for c in groups[g]:
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_338`: survived (accepted, message-text: message text only: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict); argument: Changes only text: the text of the no-BGP-neighbors warning (logged and added to the detail); the check still goes ahead with the same verdict. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `94105043b385b371`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_338: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -90,7 +90,7 @@
                 # BGP at all (static routing). Go ahead, but say so on each check
                 where = "" if g[1] == "default" else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
-                        "without BGP convergence")
+                        "WITHOUT BGP CONVERGENCE")
                 log(f"warning: {text}")
                 if warnings is not None:
                     for c in groups[g]:
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_339`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `8fd51b804806b27e`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_339: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -91,7 +91,7 @@
                 where = "" if g[1] == "default" else f" (vrf {g[1]})"
                 text = (f"{g[0]}{where} reported no BGP neighbors for {deadline[g]:g}s; the check was evaluated "
                         "without BGP convergence")
-                log(f"warning: {text}")
+                log(None)
                 if warnings is not None:
                     for c in groups[g]:
                         warnings[id(c)] = text
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_350`: survived (accepted, message-text: message text only: the text of a not-evaluated detail; the result is still failed with the same samples and counts); argument: Changes only text: the text of a not-evaluated detail; the result is still failed with the same samples and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `55f2e22fc8061390`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_350: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -98,7 +98,7 @@
             elif s["streak"] == 0:
                 for c in groups[g]:
                     detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
-                              "check only means something once every BGP session on its node is up (a leak can "
+                              "XXcheck only means something once every BGP session on its node is up (a leak can XX"
                               "arrive over any of them). If a session is down on purpose, add a bgp_session check "
                               "with state: down for it")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_351`: survived (accepted, message-text: message text only: the text of a not-evaluated detail; the result is still failed with the same samples and counts); argument: Changes only text: the text of a not-evaluated detail; the result is still failed with the same samples and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `ad522a4e7abad41c`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_351: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -98,7 +98,7 @@
             elif s["streak"] == 0:
                 for c in groups[g]:
                     detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
-                              "check only means something once every BGP session on its node is up (a leak can "
+                              "check only means something once every bgp session on its node is up (a leak can "
                               "arrive over any of them). If a session is down on purpose, add a bgp_session check "
                               "with state: down for it")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_352`: survived (accepted, message-text: message text only: the text of a not-evaluated detail; the result is still failed with the same samples and counts); argument: Changes only text: the text of a not-evaluated detail; the result is still failed with the same samples and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `ba3c49b1be946e4f`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_352: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -98,7 +98,7 @@
             elif s["streak"] == 0:
                 for c in groups[g]:
                     detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
-                              "check only means something once every BGP session on its node is up (a leak can "
+                              "CHECK ONLY MEANS SOMETHING ONCE EVERY BGP SESSION ON ITS NODE IS UP (A LEAK CAN "
                               "arrive over any of them). If a session is down on purpose, add a bgp_session check "
                               "with state: down for it")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_353`: survived (accepted, message-text: message text only: the text of a not-evaluated detail; the result is still failed with the same samples and counts); argument: Changes only text: the text of a not-evaluated detail; the result is still failed with the same samples and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `7240e7527b500da3`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_353: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -99,7 +99,7 @@
                 for c in groups[g]:
                     detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
                               "check only means something once every BGP session on its node is up (a leak can "
-                              "arrive over any of them). If a session is down on purpose, add a bgp_session check "
+                              "XXarrive over any of them). If a session is down on purpose, add a bgp_session check XX"
                               "with state: down for it")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                             s["history"][-50:], samples_passed=0,
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_354`: survived (accepted, message-text: message text only: the text of a not-evaluated detail; the result is still failed with the same samples and counts); argument: Changes only text: the text of a not-evaluated detail; the result is still failed with the same samples and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `5c94bd910166cb42`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_354: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -99,7 +99,7 @@
                 for c in groups[g]:
                     detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
                               "check only means something once every BGP session on its node is up (a leak can "
-                              "arrive over any of them). If a session is down on purpose, add a bgp_session check "
+                              "arrive over any of them). if a session is down on purpose, add a bgp_session check "
                               "with state: down for it")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                             s["history"][-50:], samples_passed=0,
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_355`: survived (accepted, message-text: message text only: the text of a not-evaluated detail; the result is still failed with the same samples and counts); argument: Changes only text: the text of a not-evaluated detail; the result is still failed with the same samples and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `e4d3a314f9b7455d`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_355: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -99,7 +99,7 @@
                 for c in groups[g]:
                     detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
                               "check only means something once every BGP session on its node is up (a leak can "
-                              "arrive over any of them). If a session is down on purpose, add a bgp_session check "
+                              "ARRIVE OVER ANY OF THEM). IF A SESSION IS DOWN ON PURPOSE, ADD A BGP_SESSION CHECK "
                               "with state: down for it")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                             s["history"][-50:], samples_passed=0,
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_356`: survived (accepted, message-text: message text only: the text of a not-evaluated detail; the result is still failed with the same samples and counts); argument: Changes only text: the text of a not-evaluated detail; the result is still failed with the same samples and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `9878bcf01c7736bc`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_356: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -100,7 +100,7 @@
                     detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
                               "check only means something once every BGP session on its node is up (a leak can "
                               "arrive over any of them). If a session is down on purpose, add a bgp_session check "
-                              "with state: down for it")
+                              "XXwith state: down for itXX")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                             s["history"][-50:], samples_passed=0,
                                             samples_unready=sum(bool(h.get("unready")) for h in s["history"]))
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_357`: survived (accepted, message-text: message text only: the text of a not-evaluated detail; the result is still failed with the same samples and counts); argument: Changes only text: the text of a not-evaluated detail; the result is still failed with the same samples and counts. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `97551dba510458a2`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_357: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -100,7 +100,7 @@
                     detail = (f"not evaluated: {s['detail']} after waiting {deadline[g]:g}s. A post-convergence "
                               "check only means something once every BGP session on its node is up (a leak can "
                               "arrive over any of them). If a session is down on purpose, add a bgp_session check "
-                              "with state: down for it")
+                              "WITH STATE: DOWN FOR IT")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
                                             s["history"][-50:], samples_passed=0,
                                             samples_unready=sum(bool(h.get("unready")) for h in s["history"]))
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_378`: survived (accepted, equivalent: equivalent: Result.samples_passed defaults to 0, the value passed explicitly); argument: Same behaviour on every input the function can receive: Result.samples_passed defaults to 0, the value passed explicitly. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `f2236fd0a4b31754`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_378: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -102,8 +102,7 @@
                               "arrive over any of them). If a session is down on purpose, add a bgp_session check "
                               "with state: down for it")
                     blocked[id(c)] = Result(c, False, detail, len(s["history"]), round(t, 1), started, [],
-                                            s["history"][-50:], samples_passed=0,
-                                            samples_unready=sum(bool(h.get("unready")) for h in s["history"]))
+                                            s["history"][-50:], samples_unready=sum(bool(h.get("unready")) for h in s["history"]))
             # established but prefix counts still moving at the deadline: go ahead
         if pending:
             nearest = min(deadline[g] for g in pending) - (_clock() - t0)
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_72`: survived (accepted, equivalent: equivalent: the default of a missing protocol only has to differ from 'bgp'; None, '' and any other text all do); argument: Same behaviour on every input the function can receive: the default of a missing protocol only has to differ from 'bgp'; None, '' and any other text all do. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `8d2ff21719f2ed97`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_72: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -18,7 +18,7 @@
     # nodes the file says run BGP: any BGP check on them, or a route check that names protocol bgp
     bgp_nodes = {c.node for c in all_checks
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
-                 or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
+                 or (c.type == "route" and str(c.params.get("protocol", None)).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
     st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
           for g in groups}
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_74`: survived (accepted, equivalent: equivalent: the default of a missing protocol only has to differ from 'bgp'; None, '' and any other text all do); argument: Same behaviour on every input the function can receive: the default of a missing protocol only has to differ from 'bgp'; None, '' and any other text all do. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `fe5e1fc6cf3d58d7`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_74: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -18,7 +18,7 @@
     # nodes the file says run BGP: any BGP check on them, or a route check that names protocol bgp
     bgp_nodes = {c.node for c in all_checks
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
-                 or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
+                 or (c.type == "route" and str(c.params.get("protocol", )).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
     st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
           for g in groups}
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_77`: survived (accepted, equivalent: equivalent: the default of a missing protocol only has to differ from 'bgp'; None, '' and any other text all do); argument: Same behaviour on every input the function can receive: the default of a missing protocol only has to differ from 'bgp'; None, '' and any other text all do. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `92a7caf8c00b0877`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_77: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -18,7 +18,7 @@
     # nodes the file says run BGP: any BGP check on them, or a route check that names protocol bgp
     bgp_nodes = {c.node for c in all_checks
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
-                 or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
+                 or (c.type == "route" and str(c.params.get("protocol", "XXXX")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
     st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
           for g in groups}
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_86`: survived (accepted, equivalent: equivalent: the initial streak is never read: every answer sets it, and the first established sample gets 1 because counts != None); argument: Same behaviour on every input the function can receive: the initial streak is never read: every answer sets it, and the first established sample gets 1 because counts != None. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `248f84716693174d`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_86: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 1, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_87`: survived (accepted, equivalent: equivalent: the initial counts are never read: they are compared only once the streak is > 0, which only an established sample that also sets counts makes); argument: Same behaviour on every input the function can receive: the initial counts are never read: they are compared only once the streak is > 0, which only an established sample that also sets counts makes. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `7843f768c3d58438`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_87: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 0, "XXcountsXX": None, "answered": False, "empty": False, "detail": "", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_88`: survived (accepted, equivalent: equivalent: the initial counts are never read: they are compared only once the streak is > 0, which only an established sample that also sets counts makes); argument: Same behaviour on every input the function can receive: the initial counts are never read: they are compared only once the streak is > 0, which only an established sample that also sets counts makes. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `e145ae06d6c255da`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_88: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 0, "COUNTS": None, "answered": False, "empty": False, "detail": "", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_92`: survived (accepted, equivalent: equivalent: the initial empty flag is never read: every answer sets it, and it is read only for a node that answered); argument: Same behaviour on every input the function can receive: the initial empty flag is never read: every answer sets it, and it is read only for a node that answered. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 3: confirmed after the code trace (research/model-reviews/release-0.3.3/adversarial-round3); diff fingerprint `465749804991003d`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_92: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 0, "counts": None, "answered": False, "XXemptyXX": False, "detail": "", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_93`: survived (accepted, equivalent: equivalent: the initial empty flag is never read: every answer sets it, and it is read only for a node that answered); argument: Same behaviour on every input the function can receive: the initial empty flag is never read: every answer sets it, and it is read only for a node that answered. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `0b97e79a37f0c814`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_93: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 0, "counts": None, "answered": False, "EMPTY": False, "detail": "", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_94`: survived (accepted, equivalent: equivalent: the initial empty flag is never read: every answer sets it, and it is read only for a node that answered); argument: Same behaviour on every input the function can receive: the initial empty flag is never read: every answer sets it, and it is read only for a node that answered. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `fdc205023ae84cff`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_94: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": True, "detail": "", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_95`: survived (accepted, equivalent: equivalent: the initial detail is never read: every failing sample sets it before it is used (and it is only message text)); argument: Same behaviour on every input the function can receive: the initial detail is never read: every failing sample sets it before it is used (and it is only message text). So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `511025f7bdc2aa4c`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_95: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "XXdetailXX": "", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_96`: survived (accepted, equivalent: equivalent: the initial detail is never read: every failing sample sets it before it is used (and it is only message text)); argument: Same behaviour on every input the function can receive: the initial detail is never read: every failing sample sets it before it is used (and it is only message text). So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `6eab5eaef1b3fd74`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_96: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "DETAIL": "", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

`netdryrun.runner.x__bgp_convergence_gate__mutmut_97`: survived (accepted, equivalent: equivalent: the initial detail is never read: every failing sample sets it before it is used (and it is only message text)); argument: Same behaviour on every input the function can receive: the initial detail is never read: every failing sample sets it before it is used (and it is only message text). So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `91915468578d18ce`

```diff
# netdryrun.runner.x__bgp_convergence_gate__mutmut_97: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
                  if c.type in ("bgp_session", "bgp_prefixes", "bgp_route")
                  or (c.type == "route" and str(c.params.get("protocol", "")).lower() == "bgp")}
     deadline = {g: max(c.timeout for c in cs) for g, cs in groups.items()}
-    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "", "history": []}
+    st = {g: {"streak": 0, "counts": None, "answered": False, "empty": False, "detail": "XXXX", "history": []}
           for g in groups}
     started = _now()
     t0 = _clock()
```

## `config._validate_check` (50)

`netdryrun.config.x__validate_check__mutmut_130`: survived (accepted, equivalent: equivalent: ipaddress.ip_network only tests strict for truth; None and False both normalize host bits); diff fingerprint `a7115318e66a6274`

```diff
# netdryrun.config.x__validate_check__mutmut_130: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -27,7 +27,7 @@
     try:
         # canonical spellings so 2001:db8:0::1 in YAML matches 2001:db8::1 on the device
         if ctype in ("route", "bgp_route"):
-            params["prefix"] = str(ipaddress.ip_network(params["prefix"], strict=False))
+            params["prefix"] = str(ipaddress.ip_network(params["prefix"], strict=None))
         for key in ("neighbor", "target", "source", "next_hop"):
             if key in params:
                 params[key] = str(ipaddress.ip_address(params[key]))
```

`netdryrun.config.x__validate_check__mutmut_154`: survived (accepted, equivalent: equivalent: next_hop was already parsed by ipaddress.ip_address, which keeps an IPv6 scope (fe80::1%eth1) and reports is_link_local for it; splitting the text on anything else gives the same address); diff fingerprint `34f73d96cb344f45`

```diff
# netdryrun.config.x__validate_check__mutmut_154: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -33,7 +33,7 @@
                 params[key] = str(ipaddress.ip_address(params[key]))
     except ValueError as e:
         raise ConfigError(f"{where}: {e}") from None
-    if "next_hop" in params and ipaddress.ip_address(params["next_hop"].split("%")[0]).is_link_local:
+    if "next_hop" in params and ipaddress.ip_address(params["next_hop"].split(None)[0]).is_link_local:
         # devices report a link-local next hop without its interface, and two sessions can share one (fe80::1 on
         # eth1 and on eth2): a path through either would match, so the check can't say which one it tests
         raise ConfigError(f"{where}: next_hop {params['next_hop']!r} is link-local: it names no interface, and two "
```

`netdryrun.config.x__validate_check__mutmut_157`: survived (accepted, equivalent: equivalent: next_hop was already parsed by ipaddress.ip_address, which keeps an IPv6 scope (fe80::1%eth1) and reports is_link_local for it; splitting the text on anything else gives the same address); diff fingerprint `c49ad08836f9b33d`

```diff
# netdryrun.config.x__validate_check__mutmut_157: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -33,7 +33,7 @@
                 params[key] = str(ipaddress.ip_address(params[key]))
     except ValueError as e:
         raise ConfigError(f"{where}: {e}") from None
-    if "next_hop" in params and ipaddress.ip_address(params["next_hop"].split("%")[0]).is_link_local:
+    if "next_hop" in params and ipaddress.ip_address(params["next_hop"].split("XX%XX")[0]).is_link_local:
         # devices report a link-local next hop without its interface, and two sessions can share one (fe80::1 on
         # eth1 and on eth2): a path through either would match, so the check can't say which one it tests
         raise ConfigError(f"{where}: next_hop {params['next_hop']!r} is link-local: it names no interface, and two "
```

`netdryrun.config.x__validate_check__mutmut_193`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `4541c347ff62ab10`

```diff
# netdryrun.config.x__validate_check__mutmut_193: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -44,7 +44,7 @@
             raise ConfigError(f"{where}: {key} must be a non-negative integer, got {params[key]!r}")
     for key in ("local_pref", "med"):
         if key in params and params[key] > UINT32:
-            raise ConfigError(f"{where}: {key} must be at most {UINT32}")
+            raise ConfigError(None)
     if "exact" in params and ({"min", "max"} & set(params)):
         raise ConfigError(f"{where}: use exact on its own, or min/max, not both")
     if params.get("min", 0) > params.get("max", float("inf")):
```

`netdryrun.config.x__validate_check__mutmut_221`: survived (accepted, equivalent: equivalent: float('INF') == float('inf'); float() parses infinity case-insensitively); diff fingerprint `3b1a6c5bae484ce2`

```diff
# netdryrun.config.x__validate_check__mutmut_221: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -47,7 +47,7 @@
             raise ConfigError(f"{where}: {key} must be at most {UINT32}")
     if "exact" in params and ({"min", "max"} & set(params)):
         raise ConfigError(f"{where}: use exact on its own, or min/max, not both")
-    if params.get("min", 0) > params.get("max", float("inf")):
+    if params.get("min", 0) > params.get("max", float("INF")):
         raise ConfigError(f"{where}: min is greater than max")
     for key in ("present", "active"):
         if key in params:
```

`netdryrun.config.x__validate_check__mutmut_242`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `bd826c2e77d9b61b`

```diff
# netdryrun.config.x__validate_check__mutmut_242: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -55,7 +55,7 @@
     if "vrf" in params:
         v = params["vrf"]
         if isinstance(v, bool) or not isinstance(v, (str, int)):
-            raise ConfigError(f"{where}: vrf must be a VRF name, got {v!r}")
+            raise ConfigError(None)
         params["vrf"] = str(v)
         if not VRF_NAME.fullmatch(params["vrf"]):
             raise ConfigError(f"{where}: bad vrf {params['vrf']!r}: use letters, digits and . _ : - (at most 64)")
```

`netdryrun.config.x__validate_check__mutmut_272`: survived (accepted, equivalent: equivalent: the default state is lowercased before it is checked and stored, so 'ESTABLISHED' gives 'established'); diff fingerprint `fa6087a238a57609`

```diff
# netdryrun.config.x__validate_check__mutmut_272: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -63,7 +63,7 @@
             # devices answer "vrf all" keyed by each VRF's name, which the drivers read as "no routes"
             raise ConfigError(f"{where}: vrf 'all' is not supported: name one VRF per check")
     if ctype == "bgp_session":
-        state = params.get("state", "established")
+        state = params.get("state", "ESTABLISHED")
         if not isinstance(state, str) or state.lower() not in BGP_STATES:
             raise ConfigError(f"{where}: state must be one of {', '.join(BGP_STATES)}, got {state!r}"
                               f"{_suggest(state, BGP_STATES)}")
```

`netdryrun.config.x__validate_check__mutmut_279`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `ea68f5b276f462e0`

```diff
# netdryrun.config.x__validate_check__mutmut_279: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -65,7 +65,7 @@
     if ctype == "bgp_session":
         state = params.get("state", "established")
         if not isinstance(state, str) or state.lower() not in BGP_STATES:
-            raise ConfigError(f"{where}: state must be one of {', '.join(BGP_STATES)}, got {state!r}"
+            raise ConfigError(f"{where}: state must be one of {'XX, XX'.join(BGP_STATES)}, got {state!r}"
                               f"{_suggest(state, BGP_STATES)}")
         params["state"] = state.lower()
     if ctype == "bgp_prefixes":
```

`netdryrun.config.x__validate_check__mutmut_280`: survived (accepted, message-text: message text only: the 'did you mean' hint of a ConfigError raised either way (_suggest(None) gives no hint; exit 2 either way)); diff fingerprint `2d515da234dbf753`

```diff
# netdryrun.config.x__validate_check__mutmut_280: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -66,7 +66,7 @@
         state = params.get("state", "established")
         if not isinstance(state, str) or state.lower() not in BGP_STATES:
             raise ConfigError(f"{where}: state must be one of {', '.join(BGP_STATES)}, got {state!r}"
-                              f"{_suggest(state, BGP_STATES)}")
+                              f"{_suggest(None, BGP_STATES)}")
         params["state"] = state.lower()
     if ctype == "bgp_prefixes":
         bounds = {"min", "max", "exact"} & set(params)
```

`netdryrun.config.x__validate_check__mutmut_323`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `0f0e35067240bc02`

```diff
# netdryrun.config.x__validate_check__mutmut_323: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -77,7 +77,7 @@
         if "afi" in params:
             afi = params["afi"]
             if not isinstance(afi, str) or afi.lower() not in AFIS:
-                raise ConfigError(f"{where}: afi must be one of {', '.join(AFIS)}, got {afi!r}"
+                raise ConfigError(f"{where}: afi must be one of {'XX, XX'.join(AFIS)}, got {afi!r}"
                                   f"{_suggest(afi, AFIS, AFI_HINTS)}")
             params["afi"] = afi.lower()
     if ctype == "route":
```

`netdryrun.config.x__validate_check__mutmut_347`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `c94153c12f56f3bd`

```diff
# netdryrun.config.x__validate_check__mutmut_347: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -84,8 +84,7 @@
         if "protocol" in params:
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
-                why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                why = None
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_348`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `bce6895957046120`

```diff
# netdryrun.config.x__validate_check__mutmut_348: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if (isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp")) and False else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_349`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `e0d06ad9f800dea4`

```diff
# netdryrun.config.x__validate_check__mutmut_349: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if (isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp")) or True else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_350`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `86548d1a6f095ef7`

```diff
# netdryrun.config.x__validate_check__mutmut_350: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -84,7 +84,7 @@
         if "protocol" in params:
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
-                why = (" (drivers report eBGP and iBGP routes alike as bgp)"
+                why = ("XX (drivers report eBGP and iBGP routes alike as bgp)XX"
                        if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
```

`netdryrun.config.x__validate_check__mutmut_351`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `ef04d34c548afe95`

```diff
# netdryrun.config.x__validate_check__mutmut_351: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -84,7 +84,7 @@
         if "protocol" in params:
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
-                why = (" (drivers report eBGP and iBGP routes alike as bgp)"
+                why = (" (drivers report ebgp and ibgp routes alike as bgp)"
                        if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
```

`netdryrun.config.x__validate_check__mutmut_352`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `a2913b25609e561c`

```diff
# netdryrun.config.x__validate_check__mutmut_352: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -84,7 +84,7 @@
         if "protocol" in params:
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
-                why = (" (drivers report eBGP and iBGP routes alike as bgp)"
+                why = (" (DRIVERS REPORT EBGP AND IBGP ROUTES ALIKE AS BGP)"
                        if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
```

`netdryrun.config.x__validate_check__mutmut_354`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `964e14da4d7fd5a8`

```diff
# netdryrun.config.x__validate_check__mutmut_354: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if isinstance(proto, str) and proto.upper() in ("ebgp", "ibgp") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_355`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `f70819ec5c4138c1`

```diff
# netdryrun.config.x__validate_check__mutmut_355: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if isinstance(proto, str) and proto.lower() not in ("ebgp", "ibgp") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_356`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `1f7a589cb102a5d5`

```diff
# netdryrun.config.x__validate_check__mutmut_356: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if isinstance(proto, str) and proto.lower() in ("XXebgpXX", "ibgp") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_357`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `9473809f6bd6767a`

```diff
# netdryrun.config.x__validate_check__mutmut_357: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if isinstance(proto, str) and proto.lower() in ("EBGP", "ibgp") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_358`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `126db8630955d43a`

```diff
# netdryrun.config.x__validate_check__mutmut_358: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if isinstance(proto, str) and proto.lower() in ("ebgp", "XXibgpXX") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_359`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `29cdfb80dea1230d`

```diff
# netdryrun.config.x__validate_check__mutmut_359: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if isinstance(proto, str) and proto.lower() in ("ebgp", "IBGP") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_360`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `12ddaa2e5567bcfb`

```diff
# netdryrun.config.x__validate_check__mutmut_360: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -85,7 +85,7 @@
             proto = params["protocol"]
             if not isinstance(proto, str) or proto.lower() not in PROTOCOLS:
                 why = (" (drivers report eBGP and iBGP routes alike as bgp)"
-                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
+                       if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "XXXX")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
```

`netdryrun.config.x__validate_check__mutmut_369`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `4b5e9ae0da0e37db`

```diff
# netdryrun.config.x__validate_check__mutmut_369: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -88,7 +88,7 @@
                        if isinstance(proto, str) and proto.lower() in ("ebgp", "ibgp") else "")
                 raise ConfigError(f"{where}: protocol {proto!r} is not a protocol name the drivers report"
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
-                                  f"use one of {', '.join(PROTOCOLS)}")
+                                  f"use one of {'XX, XX'.join(PROTOCOLS)}")
             params["protocol"] = proto.lower()
         if params.get("present", True) is False and "active" in params:
             raise ConfigError(f"{where}: active only applies to present: true (present: false already "
```

`netdryrun.config.x__validate_check__mutmut_376`: survived (accepted, equivalent: equivalent: only present `is False` matters; a missing key gives None or True, neither is False); diff fingerprint `78406f17b2f51886`

```diff
# netdryrun.config.x__validate_check__mutmut_376: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -90,7 +90,7 @@
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
             params["protocol"] = proto.lower()
-        if params.get("present", True) is False and "active" in params:
+        if params.get("present", None) is False and "active" in params:
             raise ConfigError(f"{where}: active only applies to present: true (present: false already "
                               "means no matching route at all, selected or not)")
     if ctype == "ping":
```

`netdryrun.config.x__validate_check__mutmut_378`: survived (accepted, equivalent: equivalent: only present `is False` matters; a missing key gives None or True, neither is False); diff fingerprint `fadad39fa19d7bf1`

```diff
# netdryrun.config.x__validate_check__mutmut_378: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -90,7 +90,7 @@
                                   f"{_suggest(proto, PROTOCOLS, PROTOCOL_HINTS)}{why}; "
                                   f"use one of {', '.join(PROTOCOLS)}")
             params["protocol"] = proto.lower()
-        if params.get("present", True) is False and "active" in params:
+        if params.get("present", ) is False and "active" in params:
             raise ConfigError(f"{where}: active only applies to present: true (present: false already "
                               "means no matching route at all, selected or not)")
     if ctype == "ping":
```

`netdryrun.config.x__validate_check__mutmut_388`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `865e7130918c736e`

```diff
# netdryrun.config.x__validate_check__mutmut_388: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -92,7 +92,7 @@
             params["protocol"] = proto.lower()
         if params.get("present", True) is False and "active" in params:
             raise ConfigError(f"{where}: active only applies to present: true (present: false already "
-                              "means no matching route at all, selected or not)")
+                              "XXmeans no matching route at all, selected or not)XX")
     if ctype == "ping":
         expect = params.get("expect", "success")
         if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
```

`netdryrun.config.x__validate_check__mutmut_389`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `737834ff170c4ac8`

```diff
# netdryrun.config.x__validate_check__mutmut_389: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -92,7 +92,7 @@
             params["protocol"] = proto.lower()
         if params.get("present", True) is False and "active" in params:
             raise ConfigError(f"{where}: active only applies to present: true (present: false already "
-                              "means no matching route at all, selected or not)")
+                              "MEANS NO MATCHING ROUTE AT ALL, SELECTED OR NOT)")
     if ctype == "ping":
         expect = params.get("expect", "success")
         if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
```

`netdryrun.config.x__validate_check__mutmut_401`: survived (accepted, equivalent: equivalent: the default expect is lowercased before it is checked and stored, so 'SUCCESS' gives 'success'); diff fingerprint `a2be18ada0c6221e`

```diff
# netdryrun.config.x__validate_check__mutmut_401: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -94,7 +94,7 @@
             raise ConfigError(f"{where}: active only applies to present: true (present: false already "
                               "means no matching route at all, selected or not)")
     if ctype == "ping":
-        expect = params.get("expect", "success")
+        expect = params.get("expect", "SUCCESS")
         if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
             raise ConfigError(f"{where}: expect must be 'success' or 'failure', got {expect!r}"
                               f"{_suggest(expect, ('success', 'failure'))}")
```

`netdryrun.config.x__validate_check__mutmut_411`: survived (accepted, message-text: message text only: the 'did you mean' hint of a ConfigError raised either way (_suggest(None) gives no hint; exit 2 either way)); diff fingerprint `10b0009c347f0cb6`

```diff
# netdryrun.config.x__validate_check__mutmut_411: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -97,7 +97,7 @@
         expect = params.get("expect", "success")
         if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
             raise ConfigError(f"{where}: expect must be 'success' or 'failure', got {expect!r}"
-                              f"{_suggest(expect, ('success', 'failure'))}")
+                              f"{_suggest(None, ('success', 'failure'))}")
         params["expect"] = expect.lower()
         if "count" in params and (not _is_int(params["count"]) or not 1 <= params["count"] <= MAX_PING_COUNT):
             raise ConfigError(f"{where}: count must be an integer from 1 to {MAX_PING_COUNT}, got {params['count']!r}")
```

`netdryrun.config.x__validate_check__mutmut_415`: survived (accepted, message-text: message text only: the 'did you mean' hint of a ConfigError raised either way (_suggest(None) gives no hint; exit 2 either way)); diff fingerprint `43b98a4e8466c443`

```diff
# netdryrun.config.x__validate_check__mutmut_415: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -97,7 +97,7 @@
         expect = params.get("expect", "success")
         if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
             raise ConfigError(f"{where}: expect must be 'success' or 'failure', got {expect!r}"
-                              f"{_suggest(expect, ('success', 'failure'))}")
+                              f"{_suggest(expect, ('XXsuccessXX', 'failure'))}")
         params["expect"] = expect.lower()
         if "count" in params and (not _is_int(params["count"]) or not 1 <= params["count"] <= MAX_PING_COUNT):
             raise ConfigError(f"{where}: count must be an integer from 1 to {MAX_PING_COUNT}, got {params['count']!r}")
```

`netdryrun.config.x__validate_check__mutmut_416`: survived (accepted, message-text: message text only: the 'did you mean' hint of a ConfigError raised either way (_suggest(None) gives no hint; exit 2 either way)); diff fingerprint `92590c549b8fdacf`

```diff
# netdryrun.config.x__validate_check__mutmut_416: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -97,7 +97,7 @@
         expect = params.get("expect", "success")
         if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
             raise ConfigError(f"{where}: expect must be 'success' or 'failure', got {expect!r}"
-                              f"{_suggest(expect, ('success', 'failure'))}")
+                              f"{_suggest(expect, ('SUCCESS', 'failure'))}")
         params["expect"] = expect.lower()
         if "count" in params and (not _is_int(params["count"]) or not 1 <= params["count"] <= MAX_PING_COUNT):
             raise ConfigError(f"{where}: count must be an integer from 1 to {MAX_PING_COUNT}, got {params['count']!r}")
```

`netdryrun.config.x__validate_check__mutmut_417`: survived (accepted, message-text: message text only: the 'did you mean' hint of a ConfigError raised either way (_suggest(None) gives no hint; exit 2 either way)); diff fingerprint `7ee03f0779d464bb`

```diff
# netdryrun.config.x__validate_check__mutmut_417: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -97,7 +97,7 @@
         expect = params.get("expect", "success")
         if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
             raise ConfigError(f"{where}: expect must be 'success' or 'failure', got {expect!r}"
-                              f"{_suggest(expect, ('success', 'failure'))}")
+                              f"{_suggest(expect, ('success', 'XXfailureXX'))}")
         params["expect"] = expect.lower()
         if "count" in params and (not _is_int(params["count"]) or not 1 <= params["count"] <= MAX_PING_COUNT):
             raise ConfigError(f"{where}: count must be an integer from 1 to {MAX_PING_COUNT}, got {params['count']!r}")
```

`netdryrun.config.x__validate_check__mutmut_418`: survived (accepted, message-text: message text only: the 'did you mean' hint of a ConfigError raised either way (_suggest(None) gives no hint; exit 2 either way)); diff fingerprint `9424135e5126d3db`

```diff
# netdryrun.config.x__validate_check__mutmut_418: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -97,7 +97,7 @@
         expect = params.get("expect", "success")
         if not isinstance(expect, str) or expect.lower() not in ("success", "failure"):
             raise ConfigError(f"{where}: expect must be 'success' or 'failure', got {expect!r}"
-                              f"{_suggest(expect, ('success', 'failure'))}")
+                              f"{_suggest(expect, ('success', 'FAILURE'))}")
         params["expect"] = expect.lower()
         if "count" in params and (not _is_int(params["count"]) or not 1 <= params["count"] <= MAX_PING_COUNT):
             raise ConfigError(f"{where}: count must be an integer from 1 to {MAX_PING_COUNT}, got {params['count']!r}")
```

`netdryrun.config.x__validate_check__mutmut_450`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `f08492146ecd22d4`

```diff
# netdryrun.config.x__validate_check__mutmut_450: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -104,7 +104,7 @@
         if "min_replies" in params:
             if params["expect"] == "failure":
                 raise ConfigError(f"{where}: min_replies only applies to expect: success "
-                                  "(expect: failure passes only with 0 replies)")
+                                  "XX(expect: failure passes only with 0 replies)XX")
             count = params.get("count", 3)
             if not _is_int(params["min_replies"]) or not 1 <= params["min_replies"] <= count:
                 raise ConfigError(f"{where}: min_replies must be an integer from 1 to count ({count}), "
```

`netdryrun.config.x__validate_check__mutmut_451`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `70c89cd8002aa122`

```diff
# netdryrun.config.x__validate_check__mutmut_451: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -104,7 +104,7 @@
         if "min_replies" in params:
             if params["expect"] == "failure":
                 raise ConfigError(f"{where}: min_replies only applies to expect: success "
-                                  "(expect: failure passes only with 0 replies)")
+                                  "(EXPECT: FAILURE PASSES ONLY WITH 0 REPLIES)")
             count = params.get("count", 3)
             if not _is_int(params["min_replies"]) or not 1 <= params["min_replies"] <= count:
                 raise ConfigError(f"{where}: min_replies must be an integer from 1 to count ({count}), "
```

`netdryrun.config.x__validate_check__mutmut_477`: survived (accepted, message-text: message text only: `where` appears only inside ConfigError texts; the same inputs are accepted or refused); diff fingerprint `23888cf949609f3b`

```diff
# netdryrun.config.x__validate_check__mutmut_477: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -110,7 +110,7 @@
                 raise ConfigError(f"{where}: min_replies must be an integer from 1 to count ({count}), "
                                   f"got {params['min_replies']!r}")
     if ctype == "bgp_route":
-        _validate_bgp_route(where, params)
+        _validate_bgp_route(None, params)
     timeout = _seconds(where, "timeout", raw["timeout"]) if "timeout" in raw else default_timeout
     hold = _seconds(where, "hold", raw["hold"]) if "hold" in raw else None
     check = Check(type=ctype, params=params, name=raw.get("name") or _describe(ctype, params), timeout=timeout,
```

`netdryrun.config.x__validate_check__mutmut_484`: survived (accepted, message-text: message text only: `where` appears only inside ConfigError texts; the same inputs are accepted or refused); diff fingerprint `c4d1a737c195d7e4`

```diff
# netdryrun.config.x__validate_check__mutmut_484: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -111,7 +111,7 @@
                                   f"got {params['min_replies']!r}")
     if ctype == "bgp_route":
         _validate_bgp_route(where, params)
-    timeout = _seconds(where, "timeout", raw["timeout"]) if "timeout" in raw else default_timeout
+    timeout = _seconds(None, "timeout", raw["timeout"]) if "timeout" in raw else default_timeout
     hold = _seconds(where, "hold", raw["hold"]) if "hold" in raw else None
     check = Check(type=ctype, params=params, name=raw.get("name") or _describe(ctype, params), timeout=timeout,
                   hold=hold)
```

`netdryrun.config.x__validate_check__mutmut_500`: survived (accepted, message-text: message text only: `where` appears only inside ConfigError texts; the same inputs are accepted or refused); diff fingerprint `3214fd43da5676d8`

```diff
# netdryrun.config.x__validate_check__mutmut_500: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -112,7 +112,7 @@
     if ctype == "bgp_route":
         _validate_bgp_route(where, params)
     timeout = _seconds(where, "timeout", raw["timeout"]) if "timeout" in raw else default_timeout
-    hold = _seconds(where, "hold", raw["hold"]) if "hold" in raw else None
+    hold = _seconds(None, "hold", raw["hold"]) if "hold" in raw else None
     check = Check(type=ctype, params=params, name=raw.get("name") or _describe(ctype, params), timeout=timeout,
                   hold=hold)
     if hold is not None:
```

`netdryrun.config.x__validate_check__mutmut_51`: survived (accepted, message-text: message text only: `where` appears only inside ConfigError texts; the same inputs are accepted or refused); diff fingerprint `a96f52be2b7147c7`

```diff
# netdryrun.config.x__validate_check__mutmut_51: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -13,7 +13,7 @@
         if key not in raw:
             raise ConfigError(f"{where}: missing required key {key!r}")
     if "name" in raw:
-        _string(where, "name", raw["name"])
+        _string(None, "name", raw["name"])
     params = {k: v for k, v in raw.items() if k not in COMMON_KEYS}
     _string(where, "node", params["node"])
     for key in ("prefix", "neighbor", "target", "source", "next_hop"):
```

`netdryrun.config.x__validate_check__mutmut_536`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `401909a0182cd625`

```diff
# netdryrun.config.x__validate_check__mutmut_536: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -119,7 +119,7 @@
         from .checks import is_post_convergence   # checks imports this module
         if not is_post_convergence(check):
             raise ConfigError(f"{where}: hold only applies to post-convergence checks (present: false, "
-                              "a bgp_route attribute, expect: failure, a state other than established, max "
+                              "XXa bgp_route attribute, expect: failure, a state other than established, max XX"
                               "or exact); this check passes after 2 consecutive passing samples, so hold would be "
                               "ignored")
     return check
```

`netdryrun.config.x__validate_check__mutmut_537`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `29f958df8867016a`

```diff
# netdryrun.config.x__validate_check__mutmut_537: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -119,7 +119,7 @@
         from .checks import is_post_convergence   # checks imports this module
         if not is_post_convergence(check):
             raise ConfigError(f"{where}: hold only applies to post-convergence checks (present: false, "
-                              "a bgp_route attribute, expect: failure, a state other than established, max "
+                              "A BGP_ROUTE ATTRIBUTE, EXPECT: FAILURE, A STATE OTHER THAN ESTABLISHED, MAX "
                               "or exact); this check passes after 2 consecutive passing samples, so hold would be "
                               "ignored")
     return check
```

`netdryrun.config.x__validate_check__mutmut_538`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `3d150e1211525329`

```diff
# netdryrun.config.x__validate_check__mutmut_538: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -120,6 +120,6 @@
         if not is_post_convergence(check):
             raise ConfigError(f"{where}: hold only applies to post-convergence checks (present: false, "
                               "a bgp_route attribute, expect: failure, a state other than established, max "
-                              "or exact); this check passes after 2 consecutive passing samples, so hold would be "
+                              "XXor exact); this check passes after 2 consecutive passing samples, so hold would be XX"
                               "ignored")
     return check
```

`netdryrun.config.x__validate_check__mutmut_539`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `ed31655dea2ff5f3`

```diff
# netdryrun.config.x__validate_check__mutmut_539: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -120,6 +120,6 @@
         if not is_post_convergence(check):
             raise ConfigError(f"{where}: hold only applies to post-convergence checks (present: false, "
                               "a bgp_route attribute, expect: failure, a state other than established, max "
-                              "or exact); this check passes after 2 consecutive passing samples, so hold would be "
+                              "OR EXACT); THIS CHECK PASSES AFTER 2 CONSECUTIVE PASSING SAMPLES, SO HOLD WOULD BE "
                               "ignored")
     return check
```

`netdryrun.config.x__validate_check__mutmut_540`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `0eeadf28ea1b3d79`

```diff
# netdryrun.config.x__validate_check__mutmut_540: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -121,5 +121,5 @@
             raise ConfigError(f"{where}: hold only applies to post-convergence checks (present: false, "
                               "a bgp_route attribute, expect: failure, a state other than established, max "
                               "or exact); this check passes after 2 consecutive passing samples, so hold would be "
-                              "ignored")
+                              "XXignoredXX")
     return check
```

`netdryrun.config.x__validate_check__mutmut_541`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `e6e688bbf49cce71`

```diff
# netdryrun.config.x__validate_check__mutmut_541: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -121,5 +121,5 @@
             raise ConfigError(f"{where}: hold only applies to post-convergence checks (present: false, "
                               "a bgp_route attribute, expect: failure, a state other than established, max "
                               "or exact); this check passes after 2 consecutive passing samples, so hold would be "
-                              "ignored")
+                              "IGNORED")
     return check
```

`netdryrun.config.x__validate_check__mutmut_63`: survived (accepted, message-text: message text only: `where` appears only inside ConfigError texts; the same inputs are accepted or refused); diff fingerprint `5c2f58e78e5774cb`

```diff
# netdryrun.config.x__validate_check__mutmut_63: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -15,7 +15,7 @@
     if "name" in raw:
         _string(where, "name", raw["name"])
     params = {k: v for k, v in raw.items() if k not in COMMON_KEYS}
-    _string(where, "node", params["node"])
+    _string(None, "node", params["node"])
     for key in ("prefix", "neighbor", "target", "source", "next_hop"):
         if key in params and not isinstance(params[key], str):
             raise ConfigError(f"{where}: {key} must be an IP {'prefix' if key == 'prefix' else 'address'} "
```

`netdryrun.config.x__validate_check__mutmut_88`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `60c3d66d569099d4`

```diff
# netdryrun.config.x__validate_check__mutmut_88: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -18,7 +18,7 @@
     _string(where, "node", params["node"])
     for key in ("prefix", "neighbor", "target", "source", "next_hop"):
         if key in params and not isinstance(params[key], str):
-            raise ConfigError(f"{where}: {key} must be an IP {'prefix' if key == 'prefix' else 'address'} "
+            raise ConfigError(f"{where}: {key} must be an IP {'prefix' if (key == 'prefix') or True else 'address'} "
                               f"written as a string, got {params[key]!r}")
     for key in ("neighbor", "target", "source", "next_hop"):
         # ipaddress accepts any text after % (spaces, newlines), and the address reaches device CLI commands
```

`netdryrun.config.x__validate_check__mutmut_94`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `db95230dd7889787`

```diff
# netdryrun.config.x__validate_check__mutmut_94: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -18,7 +18,7 @@
     _string(where, "node", params["node"])
     for key in ("prefix", "neighbor", "target", "source", "next_hop"):
         if key in params and not isinstance(params[key], str):
-            raise ConfigError(f"{where}: {key} must be an IP {'prefix' if key == 'prefix' else 'address'} "
+            raise ConfigError(f"{where}: {key} must be an IP {'prefix' if key == 'prefix' else 'XXaddressXX'} "
                               f"written as a string, got {params[key]!r}")
     for key in ("neighbor", "target", "source", "next_hop"):
         # ipaddress accepts any text after % (spaces, newlines), and the address reaches device CLI commands
```

`netdryrun.config.x__validate_check__mutmut_95`: survived (accepted, message-text: message text only: the text of a ConfigError raised either way (exit 2)); diff fingerprint `19a217a2c975fcd6`

```diff
# netdryrun.config.x__validate_check__mutmut_95: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -18,7 +18,7 @@
     _string(where, "node", params["node"])
     for key in ("prefix", "neighbor", "target", "source", "next_hop"):
         if key in params and not isinstance(params[key], str):
-            raise ConfigError(f"{where}: {key} must be an IP {'prefix' if key == 'prefix' else 'address'} "
+            raise ConfigError(f"{where}: {key} must be an IP {'prefix' if key == 'prefix' else 'ADDRESS'} "
                               f"written as a string, got {params[key]!r}")
     for key in ("neighbor", "target", "source", "next_hop"):
         # ipaddress accepts any text after % (spaces, newlines), and the address reaches device CLI commands
```

## `runner.run` (37)

`netdryrun.runner.x_run__mutmut_12`: survived (accepted, equivalent: equivalent: `deployed` is only tested for truth; None and False are both false); diff fingerprint `e07f9bfe552104df`

```diff
# netdryrun.runner.x_run__mutmut_12: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -3,7 +3,7 @@
         on_result: Callable[[Result], None] | None = None, log: Callable[[str], None] = lambda _: None) -> RunReport:
     report = RunReport(config=config, started=_now())
     lab = None
-    deployed = False      # this run started a deploy: only then is the lab its own to destroy
+    deployed = None      # this run started a deploy: only then is the lab its own to destroy
     interrupted = None    # the signal that ended the run, if any
     try:
         _check_duration("--settle", settle)
```

`netdryrun.runner.x_run__mutmut_120`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `4cfe589b5924c6c4`

```diff
# netdryrun.runner.x_run__mutmut_120: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -64,7 +64,7 @@
             if not positives:
                 # nothing has proven convergence yet; give the control plane time to come up
                 settle = max(settle, 30.0)
-            log(f"Convergence checks done; settling {settle:g}s before post-convergence checks...")
+            log(None)
             _sleep(settle)
             ready = [c for c in negatives if id(c) not in not_converged]
             report.results += hold_together(ready, drivers, hold=hold, on_result=_with_warnings(gate_warnings, on_result),
```

`netdryrun.runner.x_run__mutmut_19`: survived (accepted, message-text: message text only: the option name in the RunError text for a bad --settle/--hold (RunError, exit 2, either way)); diff fingerprint `f053812298a599c8`

```diff
# netdryrun.runner.x_run__mutmut_19: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -6,7 +6,7 @@
     deployed = False      # this run started a deploy: only then is the lab its own to destroy
     interrupted = None    # the signal that ended the run, if any
     try:
-        _check_duration("--settle", settle)
+        _check_duration("XX--settleXX", settle)
         _check_duration("--hold", hold)
         lab = Lab(config.lab)
         report.lab_name = lab.name
```

`netdryrun.runner.x_run__mutmut_203`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it (the break after it runs either way)); diff fingerprint `5fddb0a4e0fbbfd0`

```diff
# netdryrun.runner.x_run__mutmut_203: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -106,7 +106,7 @@
                     report.results.append(r)
                     if on_result:
                         on_result(r)
-                if sc is not config.scenarios[-1]:
+                if sc is config.scenarios[-1]:
                     log(f"The network did not recover after scenario '{sc.name}'; later scenarios skipped")
                 break
         rejected = rejected_config(lab, config)
```

`netdryrun.runner.x_run__mutmut_206`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it (the break after it runs either way)); diff fingerprint `2ef9ebd94e3bcfcf`

```diff
# netdryrun.runner.x_run__mutmut_206: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -107,7 +107,7 @@
                     if on_result:
                         on_result(r)
                 if sc is not config.scenarios[-1]:
-                    log(f"The network did not recover after scenario '{sc.name}'; later scenarios skipped")
+                    log(None)
                 break
         rejected = rejected_config(lab, config)
         if rejected:
```

`netdryrun.runner.x_run__mutmut_21`: survived (accepted, message-text: message text only: the option name in the RunError text for a bad --settle/--hold (RunError, exit 2, either way)); diff fingerprint `d823544d1da34df3`

```diff
# netdryrun.runner.x_run__mutmut_21: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -7,7 +7,7 @@
     interrupted = None    # the signal that ended the run, if any
     try:
         _check_duration("--settle", settle)
-        _check_duration("--hold", hold)
+        _check_duration(None, hold)
         lab = Lab(config.lab)
         report.lab_name = lab.name
         lab.check_tools()
```

`netdryrun.runner.x_run__mutmut_216`: survived (accepted, message-text: message text only: the signal name in report.error of an interrupted run (signal_name never raises; status error, exit 2, either way)); diff fingerprint `df6bbc6e1514984a`

```diff
# netdryrun.runner.x_run__mutmut_216: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -114,7 +114,7 @@
             report.error = rejected
     except KeyboardInterrupt as e:
         interrupted = e
-        report.error = f"interrupted by {signal_name(getattr(e, 'signum', signal.SIGINT))}: no verdict"
+        report.error = f"interrupted by {signal_name(None)}: no verdict"
         e.report = report
         raise
     except (LabError, DriverError, ConfigError, RunError) as e:
```

`netdryrun.runner.x_run__mutmut_217`: survived (accepted, message-text: message text only: the signal name in report.error of an interrupted run (signal_name never raises; status error, exit 2, either way)); diff fingerprint `50d4ce273b2f2a67`

```diff
# netdryrun.runner.x_run__mutmut_217: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -114,7 +114,7 @@
             report.error = rejected
     except KeyboardInterrupt as e:
         interrupted = e
-        report.error = f"interrupted by {signal_name(getattr(e, 'signum', signal.SIGINT))}: no verdict"
+        report.error = f"interrupted by {signal_name(getattr(None, 'signum', signal.SIGINT))}: no verdict"
         e.report = report
         raise
     except (LabError, DriverError, ConfigError, RunError) as e:
```

`netdryrun.runner.x_run__mutmut_219`: survived (accepted, message-text: message text only: the signal name in report.error of an interrupted run (signal_name never raises; status error, exit 2, either way)); diff fingerprint `6663d8260c914550`

```diff
# netdryrun.runner.x_run__mutmut_219: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -114,7 +114,7 @@
             report.error = rejected
     except KeyboardInterrupt as e:
         interrupted = e
-        report.error = f"interrupted by {signal_name(getattr(e, 'signum', signal.SIGINT))}: no verdict"
+        report.error = f"interrupted by {signal_name(getattr(e, 'signum', None))}: no verdict"
         e.report = report
         raise
     except (LabError, DriverError, ConfigError, RunError) as e:
```

`netdryrun.runner.x_run__mutmut_223`: survived (accepted, message-text: message text only: the signal name in report.error of an interrupted run (signal_name never raises; status error, exit 2, either way)); diff fingerprint `01210bfa92261c87`

```diff
# netdryrun.runner.x_run__mutmut_223: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -114,7 +114,7 @@
             report.error = rejected
     except KeyboardInterrupt as e:
         interrupted = e
-        report.error = f"interrupted by {signal_name(getattr(e, 'signum', signal.SIGINT))}: no verdict"
+        report.error = f"interrupted by {signal_name(getattr(e, 'XXsignumXX', signal.SIGINT))}: no verdict"
         e.report = report
         raise
     except (LabError, DriverError, ConfigError, RunError) as e:
```

`netdryrun.runner.x_run__mutmut_224`: survived (accepted, message-text: message text only: the signal name in report.error of an interrupted run (signal_name never raises; status error, exit 2, either way)); diff fingerprint `08e53c4042005490`

```diff
# netdryrun.runner.x_run__mutmut_224: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -114,7 +114,7 @@
             report.error = rejected
     except KeyboardInterrupt as e:
         interrupted = e
-        report.error = f"interrupted by {signal_name(getattr(e, 'signum', signal.SIGINT))}: no verdict"
+        report.error = f"interrupted by {signal_name(getattr(e, 'SIGNUM', signal.SIGINT))}: no verdict"
         e.report = report
         raise
     except (LabError, DriverError, ConfigError, RunError) as e:
```

`netdryrun.runner.x_run__mutmut_230`: survived (accepted, message-text: message text only: the internal-error text in report.error; status error, exit 2, either way); diff fingerprint `473cda5b045a8efd`

```diff
# netdryrun.runner.x_run__mutmut_230: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -122,7 +122,7 @@
     except Exception as e:
         # A crash must never look like "checks failed" (exit 1): it is an error (exit 2) with a report
         report.error = (f"internal error: {type(e).__name__}: {e}. This is a Netdryrun bug, not a verdict on the "
-                        "change; rerun with --debug (or NETDRYRUN_DEBUG=1) for the traceback, and please report it")
+                        "XXchange; rerun with --debug (or NETDRYRUN_DEBUG=1) for the traceback, and please report itXX")
         if _debug():
             traceback.print_exc(file=sys.stderr)
     finally:
```

`netdryrun.runner.x_run__mutmut_231`: survived (accepted, message-text: message text only: the internal-error text in report.error; status error, exit 2, either way); diff fingerprint `389651f2a641b7ef`

```diff
# netdryrun.runner.x_run__mutmut_231: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -122,7 +122,7 @@
     except Exception as e:
         # A crash must never look like "checks failed" (exit 1): it is an error (exit 2) with a report
         report.error = (f"internal error: {type(e).__name__}: {e}. This is a Netdryrun bug, not a verdict on the "
-                        "change; rerun with --debug (or NETDRYRUN_DEBUG=1) for the traceback, and please report it")
+                        "change; rerun with --debug (or netdryrun_debug=1) for the traceback, and please report it")
         if _debug():
             traceback.print_exc(file=sys.stderr)
     finally:
```

`netdryrun.runner.x_run__mutmut_233`: survived (accepted, equivalent: equivalent: traceback.print_exc(file=None) prints to sys.stderr, as file=sys.stderr does); diff fingerprint `5e0f321b77cf7cc6`

```diff
# netdryrun.runner.x_run__mutmut_233: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -124,7 +124,7 @@
         report.error = (f"internal error: {type(e).__name__}: {e}. This is a Netdryrun bug, not a verdict on the "
                         "change; rerun with --debug (or NETDRYRUN_DEBUG=1) for the traceback, and please report it")
         if _debug():
-            traceback.print_exc(file=sys.stderr)
+            traceback.print_exc(file=None)
     finally:
         with _signals_deferred() as pending:
             # An interrupted run has no verdict, so --keep-on-failure doesn't apply: only --keep keeps the lab
```

`netdryrun.runner.x_run__mutmut_246`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `fcf692396e0fe2a7`

```diff
# netdryrun.runner.x_run__mutmut_246: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -130,7 +130,7 @@
             # An interrupted run has no verdict, so --keep-on-failure doesn't apply: only --keep keeps the lab
             keep_now = keep or (keep_on_failure and interrupted is None and report.status != "passed")
             if lab is not None and deployed and not keep_now:
-                log("Destroying lab...")
+                log(None)
                 try:
                     d = lab.destroy()
                     if d.rc != 0:
```

`netdryrun.runner.x_run__mutmut_247`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `4d606f0d644b148d`

```diff
# netdryrun.runner.x_run__mutmut_247: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -130,7 +130,7 @@
             # An interrupted run has no verdict, so --keep-on-failure doesn't apply: only --keep keeps the lab
             keep_now = keep or (keep_on_failure and interrupted is None and report.status != "passed")
             if lab is not None and deployed and not keep_now:
-                log("Destroying lab...")
+                log("XXDestroying lab...XX")
                 try:
                     d = lab.destroy()
                     if d.rc != 0:
```

`netdryrun.runner.x_run__mutmut_248`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `c8653c10d7ee2dbe`

```diff
# netdryrun.runner.x_run__mutmut_248: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -130,7 +130,7 @@
             # An interrupted run has no verdict, so --keep-on-failure doesn't apply: only --keep keeps the lab
             keep_now = keep or (keep_on_failure and interrupted is None and report.status != "passed")
             if lab is not None and deployed and not keep_now:
-                log("Destroying lab...")
+                log("destroying lab...")
                 try:
                     d = lab.destroy()
                     if d.rc != 0:
```

`netdryrun.runner.x_run__mutmut_249`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `3410e01d9462a427`

```diff
# netdryrun.runner.x_run__mutmut_249: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -130,7 +130,7 @@
             # An interrupted run has no verdict, so --keep-on-failure doesn't apply: only --keep keeps the lab
             keep_now = keep or (keep_on_failure and interrupted is None and report.status != "passed")
             if lab is not None and deployed and not keep_now:
-                log("Destroying lab...")
+                log("DESTROYING LAB...")
                 try:
                     d = lab.destroy()
                     if d.rc != 0:
```

`netdryrun.runner.x_run__mutmut_25`: survived (accepted, message-text: message text only: the option name in the RunError text for a bad --settle/--hold (RunError, exit 2, either way)); diff fingerprint `c044d2b24be061b5`

```diff
# netdryrun.runner.x_run__mutmut_25: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -7,7 +7,7 @@
     interrupted = None    # the signal that ended the run, if any
     try:
         _check_duration("--settle", settle)
-        _check_duration("--hold", hold)
+        _check_duration("XX--holdXX", hold)
         lab = Lab(config.lab)
         report.lab_name = lab.name
         lab.check_tools()
```

`netdryrun.runner.x_run__mutmut_251`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `bb46296586abed9a`

```diff
# netdryrun.runner.x_run__mutmut_251: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -133,7 +133,7 @@
                 log("Destroying lab...")
                 try:
                     d = lab.destroy()
-                    if d.rc != 0:
+                    if d.rc == 0:
                         log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
                 except Exception as e:  # cleanup trouble must never hide the test results
                     log(f"warning: lab cleanup failed: {e}")
```

`netdryrun.runner.x_run__mutmut_252`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `29f7cb10935205d2`

```diff
# netdryrun.runner.x_run__mutmut_252: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -133,7 +133,7 @@
                 log("Destroying lab...")
                 try:
                     d = lab.destroy()
-                    if d.rc != 0:
+                    if d.rc != 1:
                         log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
                 except Exception as e:  # cleanup trouble must never hide the test results
                     log(f"warning: lab cleanup failed: {e}")
```

`netdryrun.runner.x_run__mutmut_253`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `28cac45251c0aa2c`

```diff
# netdryrun.runner.x_run__mutmut_253: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -134,7 +134,7 @@
                 try:
                     d = lab.destroy()
                     if d.rc != 0:
-                        log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
+                        log(None)
                 except Exception as e:  # cleanup trouble must never hide the test results
                     log(f"warning: lab cleanup failed: {e}")
             elif lab is not None and deployed:
```

`netdryrun.runner.x_run__mutmut_254`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `c05c0da5273b098b`

```diff
# netdryrun.runner.x_run__mutmut_254: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -134,7 +134,7 @@
                 try:
                     d = lab.destroy()
                     if d.rc != 0:
-                        log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
+                        log(f"warning: lab cleanup failed: {(d.stderr and d.stdout).strip()[-300:]}")
                 except Exception as e:  # cleanup trouble must never hide the test results
                     log(f"warning: lab cleanup failed: {e}")
             elif lab is not None and deployed:
```

`netdryrun.runner.x_run__mutmut_255`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `2c1ffd8abb5afaf0`

```diff
# netdryrun.runner.x_run__mutmut_255: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -134,7 +134,7 @@
                 try:
                     d = lab.destroy()
                     if d.rc != 0:
-                        log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
+                        log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[+300:]}")
                 except Exception as e:  # cleanup trouble must never hide the test results
                     log(f"warning: lab cleanup failed: {e}")
             elif lab is not None and deployed:
```

`netdryrun.runner.x_run__mutmut_256`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `5f2e273bd920fe70`

```diff
# netdryrun.runner.x_run__mutmut_256: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -134,7 +134,7 @@
                 try:
                     d = lab.destroy()
                     if d.rc != 0:
-                        log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
+                        log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-301:]}")
                 except Exception as e:  # cleanup trouble must never hide the test results
                     log(f"warning: lab cleanup failed: {e}")
             elif lab is not None and deployed:
```

`netdryrun.runner.x_run__mutmut_257`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `e557c2c2af4c6bdb`

```diff
# netdryrun.runner.x_run__mutmut_257: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -136,7 +136,7 @@
                     if d.rc != 0:
                         log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
                 except Exception as e:  # cleanup trouble must never hide the test results
-                    log(f"warning: lab cleanup failed: {e}")
+                    log(None)
             elif lab is not None and deployed:
                 log(f"Lab {lab.name} left running for debugging; destroy with: containerlab destroy -t {lab.topology} --cleanup")
             if lab is not None:
```

`netdryrun.runner.x_run__mutmut_259`: survived (accepted, message-text: message text only: deployed implies lab is set, so the changed branch can never run and only the 'left running' log line is lost); diff fingerprint `8490536ff0618672`

```diff
# netdryrun.runner.x_run__mutmut_259: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -137,7 +137,7 @@
                         log(f"warning: lab cleanup failed: {(d.stderr or d.stdout).strip()[-300:]}")
                 except Exception as e:  # cleanup trouble must never hide the test results
                     log(f"warning: lab cleanup failed: {e}")
-            elif lab is not None and deployed:
+            elif lab is None and deployed:
                 log(f"Lab {lab.name} left running for debugging; destroy with: containerlab destroy -t {lab.topology} --cleanup")
             if lab is not None:
                 _ACTIVE.discard(lab)
```

`netdryrun.runner.x_run__mutmut_26`: survived (accepted, message-text: message text only: the option name in the RunError text for a bad --settle/--hold (RunError, exit 2, either way)); diff fingerprint `79c4a3fbc9facb87`

```diff
# netdryrun.runner.x_run__mutmut_26: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -7,7 +7,7 @@
     interrupted = None    # the signal that ended the run, if any
     try:
         _check_duration("--settle", settle)
-        _check_duration("--hold", hold)
+        _check_duration("--HOLD", hold)
         lab = Lab(config.lab)
         report.lab_name = lab.name
         lab.check_tools()
```

`netdryrun.runner.x_run__mutmut_260`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `cfe4996601a0373e`

```diff
# netdryrun.runner.x_run__mutmut_260: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -138,7 +138,7 @@
                 except Exception as e:  # cleanup trouble must never hide the test results
                     log(f"warning: lab cleanup failed: {e}")
             elif lab is not None and deployed:
-                log(f"Lab {lab.name} left running for debugging; destroy with: containerlab destroy -t {lab.topology} --cleanup")
+                log(None)
             if lab is not None:
                 _ACTIVE.discard(lab)
                 lab.release_lock()
```

`netdryrun.runner.x_run__mutmut_268`: survived (accepted, message-text: message text only: the signal name in report.error of an interrupted run; status stays error and the exit code comes from the exception's signum); diff fingerprint `4277feea566dde3d`

```diff
# netdryrun.runner.x_run__mutmut_268: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -145,7 +145,7 @@
             report.finished = _now()
         if pending and interrupted is None:
             # a signal arrived during cleanup: the lab is gone, now honor it
-            report.error = report.error or f"interrupted by {signal_name(pending[0])}: no verdict"
+            report.error = report.error or f"interrupted by {signal_name(None)}: no verdict"
             e = Interrupted(pending[0])
             e.report = report
             raise e
```

`netdryrun.runner.x_run__mutmut_53`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `0965c8c33add1bc8`

```diff
# netdryrun.runner.x_run__mutmut_53: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -31,7 +31,7 @@
                     f"{sorted(existing)[0]}): another Netdryrun run, or a lab deployed by hand or kept with --keep. "
                     f"Netdryrun won't redeploy or destroy it. Wait for the other run to finish, or remove the lab "
                     f"with: containerlab destroy -t {lab.topology} --cleanup")
-            log(f"Deploying lab {lab.name} ({len(lab.nodes)} nodes); this usually takes 30-90 s, longer the first time images are pulled...")
+            log(None)
             deployed = True
             if not keep:
                 _ACTIVE.add(lab)
```

`netdryrun.runner.x_run__mutmut_60`: survived (accepted, message-text: message text only: the text of the 'containers not running' LabError (status error, exit 2)); diff fingerprint `9f21f8d4f120ef3d`

```diff
# netdryrun.runner.x_run__mutmut_60: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -38,7 +38,7 @@
             lab.deploy()
         missing = {n.container for n in lab.nodes.values()} - lab.running_containers()
         if missing:
-            raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")
+            raise LabError(None)
         if deploy:
             for node, cmds in config.setup.items():
                 log(f"Running setup on {node}...")
```

`netdryrun.runner.x_run__mutmut_61`: survived (accepted, message-text: message text only: building the 'containers not running' text fails with TypeError instead of LabError; run() reports it as an error either way (status error, exit 2)); diff fingerprint `12c169cddaecf570`

```diff
# netdryrun.runner.x_run__mutmut_61: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -38,7 +38,7 @@
             lab.deploy()
         missing = {n.container for n in lab.nodes.values()} - lab.running_containers()
         if missing:
-            raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")
+            raise LabError(f"lab containers not running: {', '.join(None)}")
         if deploy:
             for node, cmds in config.setup.items():
                 log(f"Running setup on {node}...")
```

`netdryrun.runner.x_run__mutmut_62`: survived (accepted, message-text: message text only: the text of the 'containers not running' LabError (status error, exit 2)); diff fingerprint `5b46a05fc46503a9`

```diff
# netdryrun.runner.x_run__mutmut_62: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -38,7 +38,7 @@
             lab.deploy()
         missing = {n.container for n in lab.nodes.values()} - lab.running_containers()
         if missing:
-            raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")
+            raise LabError(f"lab containers not running: {'XX, XX'.join(sorted(missing))}")
         if deploy:
             for node, cmds in config.setup.items():
                 log(f"Running setup on {node}...")
```

`netdryrun.runner.x_run__mutmut_63`: survived (accepted, message-text: message text only: building the 'containers not running' text fails with TypeError instead of LabError; run() reports it as an error either way (status error, exit 2)); diff fingerprint `0c72cf33a913e87d`

```diff
# netdryrun.runner.x_run__mutmut_63: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -38,7 +38,7 @@
             lab.deploy()
         missing = {n.container for n in lab.nodes.values()} - lab.running_containers()
         if missing:
-            raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")
+            raise LabError(f"lab containers not running: {', '.join(sorted(None))}")
         if deploy:
             for node, cmds in config.setup.items():
                 log(f"Running setup on {node}...")
```

`netdryrun.runner.x_run__mutmut_64`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); diff fingerprint `76fb8129209aea0d`

```diff
# netdryrun.runner.x_run__mutmut_64: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -41,7 +41,7 @@
             raise LabError(f"lab containers not running: {', '.join(sorted(missing))}")
         if deploy:
             for node, cmds in config.setup.items():
-                log(f"Running setup on {node}...")
+                log(None)
                 lab.run_setup(node, cmds, log=log)
 
         drivers = {}
```

`netdryrun.runner.x_run__mutmut_87`: survived (accepted, equivalent: equivalent: report.results is still empty here, so assigning the positive results equals appending them); diff fingerprint `599a5df6ec16c320`

```diff
# netdryrun.runner.x_run__mutmut_87: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -56,7 +56,7 @@
 
         positives = [c for c in config.checks if not is_post_convergence(c)]
         negatives = [c for c in config.checks if is_post_convergence(c)]
-        report.results += run_round_robin(positives, drivers, on_result=on_result, clock=_clock, sleep=_sleep)
+        report.results = run_round_robin(positives, drivers, on_result=on_result, clock=_clock, sleep=_sleep)
         if negatives:
             gate_warnings: dict[int, str] = {}
             not_converged = _bgp_convergence_gate(negatives, config.checks, drivers, log=log,
```

## `config._validate_scenario` (30)

`netdryrun.config.x__validate_scenario__mutmut_11`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `7baf08778fa84abe`

```diff
# netdryrun.config.x__validate_scenario__mutmut_11: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def _validate_scenario(i: int, raw: Any, default_timeout: float) -> Scenario:
     where = _check_where("scenarios", i, raw)
     if not isinstance(raw, dict):
-        raise ConfigError(f"{where}: must be a mapping")
+        raise ConfigError(None)
     _reject_unknown(where, raw, SCENARIO_KEYS)
     if "name" in raw:
         _string(where, "name", raw["name"])
```

`netdryrun.config.x__validate_scenario__mutmut_115`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `6b5d77bfc6570f2a`

```diff
# netdryrun.config.x__validate_scenario__mutmut_115: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,7 +26,7 @@
         else:
             node = item
         if not isinstance(node, str) or not node.strip():
-            raise ConfigError(f"{where}: node_isolated needs a node name, got {node!r}")
+            raise ConfigError(None)
         faults.append(Fault("node_isolated", node))
     for item in _as_list(raw.get("inject_routes")):
         if isinstance(item, dict):
```

`netdryrun.config.x__validate_scenario__mutmut_136`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `9fb446f6c568c67f`

```diff
# netdryrun.config.x__validate_scenario__mutmut_136: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,7 +32,7 @@
         if isinstance(item, dict):
             _reject_unknown(f"{where}: inject_routes", item, INJECT_KEYS)
             if "node" in item:
-                _string(f"{where}: inject_routes", "node", item["node"])
+                _string(None, "node", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
                 _string(f"{where}: inject_routes", "from", item["from"])
```

`netdryrun.config.x__validate_scenario__mutmut_137`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `38a4991883e4b6d1`

```diff
# netdryrun.config.x__validate_scenario__mutmut_137: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,7 +32,7 @@
         if isinstance(item, dict):
             _reject_unknown(f"{where}: inject_routes", item, INJECT_KEYS)
             if "node" in item:
-                _string(f"{where}: inject_routes", "node", item["node"])
+                _string(f"{where}: inject_routes", None, item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
                 _string(f"{where}: inject_routes", "from", item["from"])
```

`netdryrun.config.x__validate_scenario__mutmut_142`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `afc266016fbdd6b4`

```diff
# netdryrun.config.x__validate_scenario__mutmut_142: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,7 +32,7 @@
         if isinstance(item, dict):
             _reject_unknown(f"{where}: inject_routes", item, INJECT_KEYS)
             if "node" in item:
-                _string(f"{where}: inject_routes", "node", item["node"])
+                _string(f"{where}: inject_routes", "XXnodeXX", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
                 _string(f"{where}: inject_routes", "from", item["from"])
```

`netdryrun.config.x__validate_scenario__mutmut_143`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `323e8e6e18871f43`

```diff
# netdryrun.config.x__validate_scenario__mutmut_143: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -32,7 +32,7 @@
         if isinstance(item, dict):
             _reject_unknown(f"{where}: inject_routes", item, INJECT_KEYS)
             if "node" in item:
-                _string(f"{where}: inject_routes", "node", item["node"])
+                _string(f"{where}: inject_routes", "NODE", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
                 _string(f"{where}: inject_routes", "from", item["from"])
```

`netdryrun.config.x__validate_scenario__mutmut_146`: survived (accepted, equivalent: equivalent: parse_inject refuses the same values (a non-string prefix or from is never a valid network once str()-ed), so the config is still refused); diff fingerprint `205a27b838cb04c5`

```diff
# netdryrun.config.x__validate_scenario__mutmut_146: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -34,7 +34,7 @@
             if "node" in item:
                 _string(f"{where}: inject_routes", "node", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
-            if "from" in item:
+            if "XXfromXX" in item:
                 _string(f"{where}: inject_routes", "from", item["from"])
             if "prefixes" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
```

`netdryrun.config.x__validate_scenario__mutmut_147`: survived (accepted, equivalent: equivalent: parse_inject refuses the same values (a non-string prefix or from is never a valid network once str()-ed), so the config is still refused); diff fingerprint `a591d16fd91fb95c`

```diff
# netdryrun.config.x__validate_scenario__mutmut_147: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -34,7 +34,7 @@
             if "node" in item:
                 _string(f"{where}: inject_routes", "node", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
-            if "from" in item:
+            if "FROM" in item:
                 _string(f"{where}: inject_routes", "from", item["from"])
             if "prefixes" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
```

`netdryrun.config.x__validate_scenario__mutmut_149`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `7bc3079d8556d2a3`

```diff
# netdryrun.config.x__validate_scenario__mutmut_149: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -35,7 +35,7 @@
                 _string(f"{where}: inject_routes", "node", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
-                _string(f"{where}: inject_routes", "from", item["from"])
+                _string(None, "from", item["from"])
             if "prefixes" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
                 if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
```

`netdryrun.config.x__validate_scenario__mutmut_150`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `af1eab940eb3b488`

```diff
# netdryrun.config.x__validate_scenario__mutmut_150: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -35,7 +35,7 @@
                 _string(f"{where}: inject_routes", "node", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
-                _string(f"{where}: inject_routes", "from", item["from"])
+                _string(f"{where}: inject_routes", None, item["from"])
             if "prefixes" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
                 if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
```

`netdryrun.config.x__validate_scenario__mutmut_155`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `dd8261a3d5b22fb8`

```diff
# netdryrun.config.x__validate_scenario__mutmut_155: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -35,7 +35,7 @@
                 _string(f"{where}: inject_routes", "node", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
-                _string(f"{where}: inject_routes", "from", item["from"])
+                _string(f"{where}: inject_routes", "XXfromXX", item["from"])
             if "prefixes" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
                 if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
```

`netdryrun.config.x__validate_scenario__mutmut_156`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `4e6d74fb9cbb7e20`

```diff
# netdryrun.config.x__validate_scenario__mutmut_156: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -35,7 +35,7 @@
                 _string(f"{where}: inject_routes", "node", item["node"])
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
-                _string(f"{where}: inject_routes", "from", item["from"])
+                _string(f"{where}: inject_routes", "FROM", item["from"])
             if "prefixes" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
                 if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
```

`netdryrun.config.x__validate_scenario__mutmut_159`: survived (accepted, equivalent: equivalent: parse_inject refuses the same values (a non-string prefix or from is never a valid network once str()-ed), so the config is still refused); diff fingerprint `1d35579956c7ea4f`

```diff
# netdryrun.config.x__validate_scenario__mutmut_159: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -36,7 +36,7 @@
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
                 _string(f"{where}: inject_routes", "from", item["from"])
-            if "prefixes" in item:
+            if "XXprefixesXX" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
                 if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
                     raise ConfigError(f"{where}: inject_routes prefixes must be a prefix or a list of prefixes "
```

`netdryrun.config.x__validate_scenario__mutmut_160`: survived (accepted, equivalent: equivalent: parse_inject refuses the same values (a non-string prefix or from is never a valid network once str()-ed), so the config is still refused); diff fingerprint `3c55a3efc7ef6e5d`

```diff
# netdryrun.config.x__validate_scenario__mutmut_160: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -36,7 +36,7 @@
             # parse_inject reads these with str(), so a bare 1 would become the prefix 0.0.0.1/32
             if "from" in item:
                 _string(f"{where}: inject_routes", "from", item["from"])
-            if "prefixes" in item:
+            if "PREFIXES" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
                 if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
                     raise ConfigError(f"{where}: inject_routes prefixes must be a prefix or a list of prefixes "
```

`netdryrun.config.x__validate_scenario__mutmut_169`: survived (accepted, equivalent: equivalent: parse_inject refuses the same values (a non-string prefix or from is never a valid network once str()-ed), so the config is still refused); diff fingerprint `ceb60eab65babebf`

```diff
# netdryrun.config.x__validate_scenario__mutmut_169: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -38,7 +38,7 @@
                 _string(f"{where}: inject_routes", "from", item["from"])
             if "prefixes" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
-                if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
+                if not pfx and not all(isinstance(x, str) and x.strip() for x in pfx):
                     raise ConfigError(f"{where}: inject_routes prefixes must be a prefix or a list of prefixes "
                                       f"written as strings, got {item['prefixes']!r}")
             if "as_path" in item and item["as_path"] in (None, "", [], {}):
```

`netdryrun.config.x__validate_scenario__mutmut_174`: survived (accepted, message-text: message text only: the same ConfigError is raised, only its message changes); diff fingerprint `bb692c105a751ae1`

```diff
# netdryrun.config.x__validate_scenario__mutmut_174: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -39,8 +39,7 @@
             if "prefixes" in item:
                 pfx = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
                 if not pfx or not all(isinstance(x, str) and x.strip() for x in pfx):
-                    raise ConfigError(f"{where}: inject_routes prefixes must be a prefix or a list of prefixes "
-                                      f"written as strings, got {item['prefixes']!r}")
+                    raise ConfigError(None)
             if "as_path" in item and item["as_path"] in (None, "", [], {}):
                 raise ConfigError(f"{where}: inject_routes as_path is empty")
         try:
```

`netdryrun.config.x__validate_scenario__mutmut_185`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `a62efb3f975d3d16`

```diff
# netdryrun.config.x__validate_scenario__mutmut_185: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -42,7 +42,7 @@
                     raise ConfigError(f"{where}: inject_routes prefixes must be a prefix or a list of prefixes "
                                       f"written as strings, got {item['prefixes']!r}")
             if "as_path" in item and item["as_path"] in (None, "", [], {}):
-                raise ConfigError(f"{where}: inject_routes as_path is empty")
+                raise ConfigError(None)
         try:
             inj = parse_inject(where, item)
         except ValueError as e:
```

`netdryrun.config.x__validate_scenario__mutmut_21`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `7ffd11eec58fbb23`

```diff
# netdryrun.config.x__validate_scenario__mutmut_21: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         raise ConfigError(f"{where}: must be a mapping")
     _reject_unknown(where, raw, SCENARIO_KEYS)
     if "name" in raw:
-        _string(where, "name", raw["name"])
+        _string(None, "name", raw["name"])
     for key in ("link_down", "node_isolated", "inject_routes"):
         if key in raw and raw[key] in (None, "", [], {}):
             raise ConfigError(f"{where}: {key} is empty")
```

`netdryrun.config.x__validate_scenario__mutmut_217`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `632a00a3369bbf96`

```diff
# netdryrun.config.x__validate_scenario__mutmut_217: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -52,7 +52,7 @@
         raise ConfigError(f"{where}: define at least one fault (link_down, node_isolated or inject_routes)")
     raw_checks = raw.get("checks")
     if not raw_checks:
-        raise ConfigError(f"{where}: no checks defined")
+        raise ConfigError(None)
     if not isinstance(raw_checks, list):
         raise ConfigError(f"{where}: checks must be a list of checks")
     name = str(raw.get("name") or ", ".join(f.describe() for f in faults))
```

`netdryrun.config.x__validate_scenario__mutmut_22`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `1586706f9d1265c5`

```diff
# netdryrun.config.x__validate_scenario__mutmut_22: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         raise ConfigError(f"{where}: must be a mapping")
     _reject_unknown(where, raw, SCENARIO_KEYS)
     if "name" in raw:
-        _string(where, "name", raw["name"])
+        _string(where, None, raw["name"])
     for key in ("link_down", "node_isolated", "inject_routes"):
         if key in raw and raw[key] in (None, "", [], {}):
             raise ConfigError(f"{where}: {key} is empty")
```

`netdryrun.config.x__validate_scenario__mutmut_227`: survived (accepted, message-text: message text only: the default scenario name shown in reports); diff fingerprint `361274abec97985d`

```diff
# netdryrun.config.x__validate_scenario__mutmut_227: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -55,7 +55,7 @@
         raise ConfigError(f"{where}: no checks defined")
     if not isinstance(raw_checks, list):
         raise ConfigError(f"{where}: checks must be a list of checks")
-    name = str(raw.get("name") or ", ".join(f.describe() for f in faults))
+    name = str(raw.get("name") or "XX, XX".join(f.describe() for f in faults))
     checks = [_validate_check(j, c, default_timeout, prefix=f"scenarios[{i}].checks") for j, c in enumerate(raw_checks)]
     for c in checks:
         c.name = f"[{name}] {c.name}"
```

`netdryrun.config.x__validate_scenario__mutmut_27`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `8b11bc6a384bed42`

```diff
# netdryrun.config.x__validate_scenario__mutmut_27: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         raise ConfigError(f"{where}: must be a mapping")
     _reject_unknown(where, raw, SCENARIO_KEYS)
     if "name" in raw:
-        _string(where, "name", raw["name"])
+        _string(where, "XXnameXX", raw["name"])
     for key in ("link_down", "node_isolated", "inject_routes"):
         if key in raw and raw[key] in (None, "", [], {}):
             raise ConfigError(f"{where}: {key} is empty")
```

`netdryrun.config.x__validate_scenario__mutmut_28`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `08b54394b8fe2e4a`

```diff
# netdryrun.config.x__validate_scenario__mutmut_28: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         raise ConfigError(f"{where}: must be a mapping")
     _reject_unknown(where, raw, SCENARIO_KEYS)
     if "name" in raw:
-        _string(where, "name", raw["name"])
+        _string(where, "NAME", raw["name"])
     for key in ("link_down", "node_isolated", "inject_routes"):
         if key in raw and raw[key] in (None, "", [], {}):
             raise ConfigError(f"{where}: {key} is empty")
```

`netdryrun.config.x__validate_scenario__mutmut_40`: survived (accepted, equivalent: equivalent: an empty-string fault is refused further down: link_down needs a mapping, node_isolated a node name, inject_routes a mapping with a node); diff fingerprint `96d95837b67d95e9`

```diff
# netdryrun.config.x__validate_scenario__mutmut_40: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -6,7 +6,7 @@
     if "name" in raw:
         _string(where, "name", raw["name"])
     for key in ("link_down", "node_isolated", "inject_routes"):
-        if key in raw and raw[key] in (None, "", [], {}):
+        if key in raw and raw[key] in (None, "XXXX", [], {}):
             raise ConfigError(f"{where}: {key} is empty")
     faults = []
     for item in _as_list(raw.get("link_down")):
```

`netdryrun.config.x__validate_scenario__mutmut_48`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `e2c07a0e64101065`

```diff
# netdryrun.config.x__validate_scenario__mutmut_48: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
     faults = []
     for item in _as_list(raw.get("link_down")):
         if not isinstance(item, dict):
-            raise ConfigError(f"{where}: link_down needs node and interface, got {item!r}")
+            raise ConfigError(None)
         _reject_unknown(f"{where}: link_down", item, LINK_DOWN_KEYS)
         if not {"node", "interface"} <= set(item):
             raise ConfigError(f"{where}: link_down needs node and interface")
```

`netdryrun.config.x__validate_scenario__mutmut_62`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `a5f98ee689d9cbd5`

```diff
# netdryrun.config.x__validate_scenario__mutmut_62: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -14,7 +14,7 @@
             raise ConfigError(f"{where}: link_down needs node and interface, got {item!r}")
         _reject_unknown(f"{where}: link_down", item, LINK_DOWN_KEYS)
         if not {"node", "interface"} <= set(item):
-            raise ConfigError(f"{where}: link_down needs node and interface")
+            raise ConfigError(None)
         _string(f"{where}: link_down", "node", item["node"])
         if not isinstance(item["interface"], str) or not INTERFACE_NAME.fullmatch(item["interface"]):
             raise ConfigError(f"{where}: bad interface {item['interface']!r}: use a Linux interface name such as eth1")
```

`netdryrun.config.x__validate_scenario__mutmut_63`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `4a91fc8e59e3dffa`

```diff
# netdryrun.config.x__validate_scenario__mutmut_63: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -15,7 +15,7 @@
         _reject_unknown(f"{where}: link_down", item, LINK_DOWN_KEYS)
         if not {"node", "interface"} <= set(item):
             raise ConfigError(f"{where}: link_down needs node and interface")
-        _string(f"{where}: link_down", "node", item["node"])
+        _string(None, "node", item["node"])
         if not isinstance(item["interface"], str) or not INTERFACE_NAME.fullmatch(item["interface"]):
             raise ConfigError(f"{where}: bad interface {item['interface']!r}: use a Linux interface name such as eth1")
         faults.append(Fault("link_down", item["node"], item["interface"]))
```

`netdryrun.config.x__validate_scenario__mutmut_64`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `2f1ed6ec72b27ac7`

```diff
# netdryrun.config.x__validate_scenario__mutmut_64: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -15,7 +15,7 @@
         _reject_unknown(f"{where}: link_down", item, LINK_DOWN_KEYS)
         if not {"node", "interface"} <= set(item):
             raise ConfigError(f"{where}: link_down needs node and interface")
-        _string(f"{where}: link_down", "node", item["node"])
+        _string(f"{where}: link_down", None, item["node"])
         if not isinstance(item["interface"], str) or not INTERFACE_NAME.fullmatch(item["interface"]):
             raise ConfigError(f"{where}: bad interface {item['interface']!r}: use a Linux interface name such as eth1")
         faults.append(Fault("link_down", item["node"], item["interface"]))
```

`netdryrun.config.x__validate_scenario__mutmut_69`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `0ae5d178a9832a63`

```diff
# netdryrun.config.x__validate_scenario__mutmut_69: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -15,7 +15,7 @@
         _reject_unknown(f"{where}: link_down", item, LINK_DOWN_KEYS)
         if not {"node", "interface"} <= set(item):
             raise ConfigError(f"{where}: link_down needs node and interface")
-        _string(f"{where}: link_down", "node", item["node"])
+        _string(f"{where}: link_down", "XXnodeXX", item["node"])
         if not isinstance(item["interface"], str) or not INTERFACE_NAME.fullmatch(item["interface"]):
             raise ConfigError(f"{where}: bad interface {item['interface']!r}: use a Linux interface name such as eth1")
         faults.append(Fault("link_down", item["node"], item["interface"]))
```

`netdryrun.config.x__validate_scenario__mutmut_70`: survived (accepted, message-text: message text only: the location or key name shown in an error); diff fingerprint `9e3a0f2c00fdbe67`

```diff
# netdryrun.config.x__validate_scenario__mutmut_70: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -15,7 +15,7 @@
         _reject_unknown(f"{where}: link_down", item, LINK_DOWN_KEYS)
         if not {"node", "interface"} <= set(item):
             raise ConfigError(f"{where}: link_down needs node and interface")
-        _string(f"{where}: link_down", "node", item["node"])
+        _string(f"{where}: link_down", "NODE", item["node"])
         if not isinstance(item["interface"], str) or not INTERFACE_NAME.fullmatch(item["interface"]):
             raise ConfigError(f"{where}: bad interface {item['interface']!r}: use a Linux interface name such as eth1")
         faults.append(Fault("link_down", item["node"], item["interface"]))
```

## `drivers.frr._bgp_paths_raw` (26)

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_12`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `97d447da32b8a6d5`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_12: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -4,7 +4,7 @@
     if not data:
         return []
     if not isinstance(data.get("paths"), list) or "prefix" not in data:
-        raise unexpected(command, text)
+        raise unexpected(None, text)
     if network(command, data["prefix"]) != ipaddress.ip_network(prefix):
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_13`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `51538289ed3a8f90`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_13: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -4,7 +4,7 @@
     if not data:
         return []
     if not isinstance(data.get("paths"), list) or "prefix" not in data:
-        raise unexpected(command, text)
+        raise unexpected(command, None)
     if network(command, data["prefix"]) != ipaddress.ip_network(prefix):
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_14`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `18f801b369ff4a8e`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_14: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -4,7 +4,7 @@
     if not data:
         return []
     if not isinstance(data.get("paths"), list) or "prefix" not in data:
-        raise unexpected(command, text)
+        raise unexpected(text)
     if network(command, data["prefix"]) != ipaddress.ip_network(prefix):
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_15`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `a3d54de42703d41d`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_15: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -4,7 +4,7 @@
     if not data:
         return []
     if not isinstance(data.get("paths"), list) or "prefix" not in data:
-        raise unexpected(command, text)
+        raise unexpected(command, )
     if network(command, data["prefix"]) != ipaddress.ip_network(prefix):
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_16`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `7dce13effa42e90c`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_16: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -5,7 +5,7 @@
         return []
     if not isinstance(data.get("paths"), list) or "prefix" not in data:
         raise unexpected(command, text)
-    if network(command, data["prefix"]) != ipaddress.ip_network(prefix):
+    if network(None, data["prefix"]) != ipaddress.ip_network(prefix):
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
         if not isinstance(p, dict):
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_2`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `5b1331f53d60c448`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_2: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -1,6 +1,6 @@
 def _bgp_paths_raw(command: str, text: str, prefix: str) -> list[dict]:
     """Path objects for exactly `prefix` from `show bgp ... <prefix> json`. `{}` means no path."""
-    data = _bgp_json(command, text)
+    data = _bgp_json(None, text)
     if not data:
         return []
     if not isinstance(data.get("paths"), list) or "prefix" not in data:
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_27`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `77a30ef77715b1b3`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_27: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -9,7 +9,7 @@
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
         if not isinstance(p, dict):
-            raise unexpected(command, f"path: {str(p)[:150]}")
+            raise unexpected(None, f"path: {str(p)[:150]}")
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_28`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `072b8ea9b9443e6e`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_28: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -9,7 +9,7 @@
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
         if not isinstance(p, dict):
-            raise unexpected(command, f"path: {str(p)[:150]}")
+            raise unexpected(command, None)
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_29`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `2aade544b8a35086`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_29: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -9,7 +9,7 @@
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
         if not isinstance(p, dict):
-            raise unexpected(command, f"path: {str(p)[:150]}")
+            raise unexpected(f"path: {str(p)[:150]}")
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_30`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `521e4cc68d03b68f`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_30: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -9,7 +9,7 @@
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
         if not isinstance(p, dict):
-            raise unexpected(command, f"path: {str(p)[:150]}")
+            raise unexpected(command, )
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_31`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `10ff992640aa3969`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_31: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -9,7 +9,7 @@
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
         if not isinstance(p, dict):
-            raise unexpected(command, f"path: {str(p)[:150]}")
+            raise unexpected(command, f"path: {str(None)[:150]}")
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_32`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `2fe1a09324ab3b5d`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_32: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -9,7 +9,7 @@
         return []  # bgpd answered for another (covering) prefix: nothing for this one
     for p in data["paths"]:
         if not isinstance(p, dict):
-            raise unexpected(command, f"path: {str(p)[:150]}")
+            raise unexpected(command, f"path: {str(p)[:151]}")
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_37`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `c3c7ea8c6eb4a117`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_37: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get(None, '?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_38`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `e8db09c2d37ec7e6`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_38: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', None)} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_39`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `6ef6591857897e9c`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_39: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_40`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `1e19a061e416a7ee`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_40: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', )} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_41`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `3b46027635eab567`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_41: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') and {}).get('peerId', '?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_42`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `51804f2b3fb44be2`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_42: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get(None) or {}).get('peerId', '?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_43`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `93a41f7e41f53994`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_43: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('XXpeerXX') or {}).get('peerId', '?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_44`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `b0f1e9a2e984c3b0`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_44: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('PEER') or {}).get('peerId', '?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_45`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `eb62ae5ba3866ec3`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_45: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('XXpeerIdXX', '?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_46`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `0b7c38a29cd64c17`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_46: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerid', '?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_47`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `494b7d575551cf86`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_47: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('PEERID', '?')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_48`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `e85c692ed30c6d3a`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_48: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -13,6 +13,6 @@
         if p.get("stale"):
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
-            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
+            raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', 'XX?XX')} is stale "
                               "(graceful restart in progress): not settled")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_49`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `6a55dc277cf7a70d`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_49: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -14,5 +14,5 @@
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
             raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
-                              "(graceful restart in progress): not settled")
+                              "XX(graceful restart in progress): not settledXX")
     return data["paths"]
```

`netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_50`: survived (accepted, message-text: message text only: the stale path still raises the DriverError (the check is not settled, never a pass); only the peer named in its message changes); diff fingerprint `9cadc12335cd40c4`

```diff
# netdryrun.drivers.frr.x__bgp_paths_raw__mutmut_50: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -14,5 +14,5 @@
             # graceful restart: bgpd keeps the restarting peer's paths, marked stale, until it re-sends them or
             # the stale timer ends. Such a path is neither present nor gone yet, so no check can pass on it
             raise DriverError(f"{prefix}: BGP path from {(p.get('peer') or {}).get('peerId', '?')} is stale "
-                              "(graceful restart in progress): not settled")
+                              "(GRACEFUL RESTART IN PROGRESS): NOT SETTLED")
     return data["paths"]
```

## `drivers.eos._summary` (24)

`netdryrun.drivers.eos.x__summary__mutmut_1`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `004f76bff24d1f61`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_1: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,5 +1,5 @@
 def _summary(text: str, vrf: str, afi: str, into: dict[str, BgpNeighbor] | None):
-    command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
+    command = None
     out = into if into is not None else {}
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
```

`netdryrun.drivers.eos.x__summary__mutmut_100`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `d8a50595ada0b2b9`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_100: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -19,6 +19,6 @@
         if "prefixAccepted" in p:
             n.prefixes[afi] = as_int(command, p["prefixAccepted"])
         elif n.state == "established":  # a missing count would read as 0 prefixes, passing `max`
-            raise unexpected(command, f"{addr}: established without prefixAccepted")
+            raise unexpected(None, f"{addr}: established without prefixAccepted")
         out[key] = n
     return out
```

`netdryrun.drivers.eos.x__summary__mutmut_101`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `4d5ac93327c79e95`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_101: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -19,6 +19,6 @@
         if "prefixAccepted" in p:
             n.prefixes[afi] = as_int(command, p["prefixAccepted"])
         elif n.state == "established":  # a missing count would read as 0 prefixes, passing `max`
-            raise unexpected(command, f"{addr}: established without prefixAccepted")
+            raise unexpected(command, None)
         out[key] = n
     return out
```

`netdryrun.drivers.eos.x__summary__mutmut_102`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `bfd1b488cb4738de`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_102: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -19,6 +19,6 @@
         if "prefixAccepted" in p:
             n.prefixes[afi] = as_int(command, p["prefixAccepted"])
         elif n.state == "established":  # a missing count would read as 0 prefixes, passing `max`
-            raise unexpected(command, f"{addr}: established without prefixAccepted")
+            raise unexpected(f"{addr}: established without prefixAccepted")
         out[key] = n
     return out
```

`netdryrun.drivers.eos.x__summary__mutmut_103`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `3ae231b74d8335ab`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_103: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -19,6 +19,6 @@
         if "prefixAccepted" in p:
             n.prefixes[afi] = as_int(command, p["prefixAccepted"])
         elif n.state == "established":  # a missing count would read as 0 prefixes, passing `max`
-            raise unexpected(command, f"{addr}: established without prefixAccepted")
+            raise unexpected(command, )
         out[key] = n
     return out
```

`netdryrun.drivers.eos.x__summary__mutmut_11`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `daffb94d6dfe0b91`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_11: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,7 +1,7 @@
 def _summary(text: str, vrf: str, afi: str, into: dict[str, BgpNeighbor] | None):
     command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
     out = into if into is not None else {}
-    entry = _vrf(command, _json(command, text), vrf)
+    entry = _vrf(None, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
             raise unexpected(command, f"{addr}: {str(p)[:150]}")
```

`netdryrun.drivers.eos.x__summary__mutmut_17`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `9bacb10eacc9f4a7`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_17: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,7 +1,7 @@
 def _summary(text: str, vrf: str, afi: str, into: dict[str, BgpNeighbor] | None):
     command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
     out = into if into is not None else {}
-    entry = _vrf(command, _json(command, text), vrf)
+    entry = _vrf(command, _json(None, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
             raise unexpected(command, f"{addr}: {str(p)[:150]}")
```

`netdryrun.drivers.eos.x__summary__mutmut_2`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `a96fe3c15103f863`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_2: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,5 +1,5 @@
 def _summary(text: str, vrf: str, afi: str, into: dict[str, BgpNeighbor] | None):
-    command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
+    command = SUMMARY_CMD.get(None, f"show bgp {afi} summary | json")
     out = into if into is not None else {}
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
```

`netdryrun.drivers.eos.x__summary__mutmut_21`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `7ccb41104c55ab9e`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_21: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -2,7 +2,7 @@
     command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
     out = into if into is not None else {}
     entry = _vrf(command, _json(command, text), vrf)
-    for addr, p in _table(command, entry, "peers").items():
+    for addr, p in _table(None, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
             raise unexpected(command, f"{addr}: {str(p)[:150]}")
         key = _canon_addr(str(addr))
```

`netdryrun.drivers.eos.x__summary__mutmut_3`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `235d4c5d1d2a1e87`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_3: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,5 +1,5 @@
 def _summary(text: str, vrf: str, afi: str, into: dict[str, BgpNeighbor] | None):
-    command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
+    command = SUMMARY_CMD.get(afi, None)
     out = into if into is not None else {}
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
```

`netdryrun.drivers.eos.x__summary__mutmut_30`: survived (accepted, equivalent: equivalent: a non-mapping peer or a missing peerState still raises (AttributeError or KeyError, turned into a DriverError by the parser wrapper)); diff fingerprint `e37c8c806f69bc18`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_30: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,7 +3,7 @@
     out = into if into is not None else {}
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
-        if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
+        if not isinstance(p, dict) and not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
             raise unexpected(command, f"{addr}: {str(p)[:150]}")
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
```

`netdryrun.drivers.eos.x__summary__mutmut_37`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `52e2c0163e315774`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_37: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -4,7 +4,7 @@
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
-            raise unexpected(command, f"{addr}: {str(p)[:150]}")
+            raise unexpected(None, f"{addr}: {str(p)[:150]}")
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
         state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
```

`netdryrun.drivers.eos.x__summary__mutmut_38`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `2cde62b02df322ac`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_38: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -4,7 +4,7 @@
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
-            raise unexpected(command, f"{addr}: {str(p)[:150]}")
+            raise unexpected(command, None)
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
         state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
```

`netdryrun.drivers.eos.x__summary__mutmut_39`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `cdbc8f2550034043`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_39: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -4,7 +4,7 @@
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
-            raise unexpected(command, f"{addr}: {str(p)[:150]}")
+            raise unexpected(f"{addr}: {str(p)[:150]}")
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
         state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
```

`netdryrun.drivers.eos.x__summary__mutmut_4`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `9968af0993f5f16b`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_4: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,5 +1,5 @@
 def _summary(text: str, vrf: str, afi: str, into: dict[str, BgpNeighbor] | None):
-    command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
+    command = SUMMARY_CMD.get(f"show bgp {afi} summary | json")
     out = into if into is not None else {}
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
```

`netdryrun.drivers.eos.x__summary__mutmut_40`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `8efa6e11789db57e`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_40: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -4,7 +4,7 @@
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
-            raise unexpected(command, f"{addr}: {str(p)[:150]}")
+            raise unexpected(command, )
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
         state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
```

`netdryrun.drivers.eos.x__summary__mutmut_41`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `5b8329665b4c361c`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_41: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -4,7 +4,7 @@
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
-            raise unexpected(command, f"{addr}: {str(p)[:150]}")
+            raise unexpected(command, f"{addr}: {str(None)[:150]}")
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
         state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
```

`netdryrun.drivers.eos.x__summary__mutmut_42`: survived (accepted, message-text: message text only: the same parse error is still raised (with one argument, `unexpected` raises a TypeError, which the parser wrapper turns into a DriverError); only its message changes); diff fingerprint `5972f5b063b58bbd`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_42: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -4,7 +4,7 @@
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
         if not isinstance(p, dict) or not isinstance(p.get("peerState"), str) or not p["peerState"].strip():
-            raise unexpected(command, f"{addr}: {str(p)[:150]}")
+            raise unexpected(command, f"{addr}: {str(p)[:151]}")
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
         state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
```

`netdryrun.drivers.eos.x__summary__mutmut_5`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `0a27c1f003d41579`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_5: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,5 +1,5 @@
 def _summary(text: str, vrf: str, afi: str, into: dict[str, BgpNeighbor] | None):
-    command = SUMMARY_CMD.get(afi, f"show bgp {afi} summary | json")
+    command = SUMMARY_CMD.get(afi, )
     out = into if into is not None else {}
     entry = _vrf(command, _json(command, text), vrf)
     for addr, p in _table(command, entry, "peers").items():
```

`netdryrun.drivers.eos.x__summary__mutmut_53`: survived (accepted, equivalent: equivalent: only the first field of the split is used, and it is the same for any maxsplit); diff fingerprint `4f22711f95de4dbe`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_53: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -7,7 +7,7 @@
             raise unexpected(command, f"{addr}: {str(p)[:150]}")
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
-        state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
+        state = re.split(r"[\s(]", p["peerState"].strip(), )[0].lower()
         n = out.get(key) or BgpNeighbor(str(addr), state)
         if n.address != str(addr):
             # scoped link-locals sharing a key (one peer is also listed once per address family): ambiguous, and a
```

`netdryrun.drivers.eos.x__summary__mutmut_59`: survived (accepted, equivalent: equivalent: only the first field of the split is used, and it is the same for any maxsplit); diff fingerprint `aa28774e519531df`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_59: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -7,7 +7,7 @@
             raise unexpected(command, f"{addr}: {str(p)[:150]}")
         key = _canon_addr(str(addr))
         # "Idle(Admin)" (EOS prints no space) -> "idle": the first word is the FSM state
-        state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=1)[0].lower()
+        state = re.split(r"[\s(]", p["peerState"].strip(), maxsplit=2)[0].lower()
         n = out.get(key) or BgpNeighbor(str(addr), state)
         if n.address != str(addr):
             # scoped link-locals sharing a key (one peer is also listed once per address family): ambiguous, and a
```

`netdryrun.drivers.eos.x__summary__mutmut_82`: survived (accepted, equivalent: equivalent: the mutated test only adds the case where the new state is established too, and then 'established' is written over 'established'); diff fingerprint `7007702f6c774bd4`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_82: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -14,7 +14,7 @@
             # down session is never hidden by an up one
             if str(addr) not in n.ambiguous:
                 n.ambiguous = (n.ambiguous or [n.address]) + [str(addr)]
-            if n.state == "established" and state != "established":
+            if n.state == "established" and state != "XXestablishedXX":
                 n.state = state
         if "prefixAccepted" in p:
             n.prefixes[afi] = as_int(command, p["prefixAccepted"])
```

`netdryrun.drivers.eos.x__summary__mutmut_83`: survived (accepted, equivalent: equivalent: the mutated test only adds the case where the new state is established too, and then 'established' is written over 'established'); diff fingerprint `ece32b4c562237b9`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_83: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -14,7 +14,7 @@
             # down session is never hidden by an up one
             if str(addr) not in n.ambiguous:
                 n.ambiguous = (n.ambiguous or [n.address]) + [str(addr)]
-            if n.state == "established" and state != "established":
+            if n.state == "established" and state != "ESTABLISHED":
                 n.state = state
         if "prefixAccepted" in p:
             n.prefixes[afi] = as_int(command, p["prefixAccepted"])
```

`netdryrun.drivers.eos.x__summary__mutmut_90`: survived (accepted, message-text: message text only: the command is used only in as_int's error message; a bad count still raises DriverError); diff fingerprint `dc9fee4a7ff13518`

```diff
# netdryrun.drivers.eos.x__summary__mutmut_90: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -17,7 +17,7 @@
             if n.state == "established" and state != "established":
                 n.state = state
         if "prefixAccepted" in p:
-            n.prefixes[afi] = as_int(command, p["prefixAccepted"])
+            n.prefixes[afi] = as_int(None, p["prefixAccepted"])
         elif n.state == "established":  # a missing count would read as 0 prefixes, passing `max`
             raise unexpected(command, f"{addr}: established without prefixAccepted")
         out[key] = n
```

## `checks._ping` (23)

`netdryrun.checks.x__ping__mutmut_37`: survived (accepted, equivalent: equivalent: separator between evidence entries; no unreachable pattern contains a newline or 'XX', so no match can span or appear at a boundary); argument: Same behaviour on every input the function can receive: separator between evidence entries; no unreachable pattern contains a newline or 'XX', so no match can span or appear at a boundary. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 3: confirmed after the code trace (research/model-reviews/release-0.3.3/adversarial-round3); diff fingerprint `c7591a1d795d5755`

```diff
# netdryrun.checks.x__ping__mutmut_37: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -3,7 +3,7 @@
     obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
     sent, received = obs.value
     if sent == 0:
-        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
+        text = "XX\nXX".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
```

`netdryrun.checks.x__ping__mutmut_39`: survived (accepted, equivalent: equivalent: text used for a missing output key; 'None' matches no unreachable pattern); argument: Same behaviour on every input the function can receive: text used for a missing output key; 'None' matches no unreachable pattern. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `bcc965c30c19a214`

```diff
# netdryrun.checks.x__ping__mutmut_39: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -3,7 +3,7 @@
     obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
     sent, received = obs.value
     if sent == 0:
-        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
+        text = "\n".join(f"{e.get('output', None)}\n{e.get('stderr', '')}" for e in obs.evidence)
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
```

`netdryrun.checks.x__ping__mutmut_41`: survived (accepted, equivalent: equivalent: text used for a missing output key; 'None' matches no unreachable pattern); argument: Same behaviour on every input the function can receive: text used for a missing output key; 'None' matches no unreachable pattern. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `e443436a3ed7d743`

```diff
# netdryrun.checks.x__ping__mutmut_41: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -3,7 +3,7 @@
     obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
     sent, received = obs.value
     if sent == 0:
-        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
+        text = "\n".join(f"{e.get('output', )}\n{e.get('stderr', '')}" for e in obs.evidence)
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
```

`netdryrun.checks.x__ping__mutmut_44`: survived (accepted, equivalent: equivalent: text used for a missing output key; 'XXXX' matches no unreachable pattern); argument: Same behaviour on every input the function can receive: text used for a missing output key; 'XXXX' matches no unreachable pattern. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `9ceddfc80657f919`

```diff
# netdryrun.checks.x__ping__mutmut_44: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -3,7 +3,7 @@
     obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
     sent, received = obs.value
     if sent == 0:
-        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
+        text = "\n".join(f"{e.get('output', 'XXXX')}\n{e.get('stderr', '')}" for e in obs.evidence)
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
```

`netdryrun.checks.x__ping__mutmut_46`: survived (accepted, equivalent: equivalent: text used for a missing stderr key; 'None' matches no unreachable pattern); argument: Same behaviour on every input the function can receive: text used for a missing stderr key; 'None' matches no unreachable pattern. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `3426d07abdb75d1a`

```diff
# netdryrun.checks.x__ping__mutmut_46: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -3,7 +3,7 @@
     obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
     sent, received = obs.value
     if sent == 0:
-        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
+        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', None)}" for e in obs.evidence)
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
```

`netdryrun.checks.x__ping__mutmut_48`: survived (accepted, equivalent: equivalent: text used for a missing stderr key; 'None' matches no unreachable pattern); argument: Same behaviour on every input the function can receive: text used for a missing stderr key; 'None' matches no unreachable pattern. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `3e3c5bb2f3c0c41b`

```diff
# netdryrun.checks.x__ping__mutmut_48: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -3,7 +3,7 @@
     obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
     sent, received = obs.value
     if sent == 0:
-        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
+        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', )}" for e in obs.evidence)
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
```

`netdryrun.checks.x__ping__mutmut_51`: survived (accepted, equivalent: equivalent: text used for a missing stderr key; 'XXXX' matches no unreachable pattern); argument: Same behaviour on every input the function can receive: text used for a missing stderr key; 'XXXX' matches no unreachable pattern. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `68f8198d34915ad7`

```diff
# netdryrun.checks.x__ping__mutmut_51: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -3,7 +3,7 @@
     obs = d.ping(p["target"], p.get("source"), count, p.get("vrf", "default"))
     sent, received = obs.value
     if sent == 0:
-        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
+        text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', 'XXXX')}" for e in obs.evidence)
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
```

`netdryrun.checks.x__ping__mutmut_56`: survived (accepted, message-text: message text only: the text of a detail or error message); argument: Changes only text: the text of a detail or error message. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `1242e44765662cc8`

```diff
# netdryrun.checks.x__ping__mutmut_56: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -6,7 +6,7 @@
         text = "\n".join(f"{e.get('output', '')}\n{e.get('stderr', '')}" for e in obs.evidence)
         m = _UNREACHABLE.search(text)
         if m:
-            why = f"0/{count} replies (destination unreachable: {m.group(0)})"
+            why = f"0/{count} replies (destination unreachable: {m.group(1)})"
             if p.get("expect", "success") == "failure":
                 return True, why, obs.evidence
             return False, why, obs.evidence
```

`netdryrun.checks.x__ping__mutmut_58`: survived (accepted, equivalent: equivalent: default for a missing expect; any value but 'failure' means success, as 'success' does (config always sets expect)); argument: Same behaviour on every input the function can receive: default for a missing expect; any value but 'failure' means success, as 'success' does (config always sets expect). So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `d31744d77ab02484`

```diff
# netdryrun.checks.x__ping__mutmut_58: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -7,7 +7,7 @@
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
-            if p.get("expect", "success") == "failure":
+            if p.get("expect", None) == "failure":
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
```

`netdryrun.checks.x__ping__mutmut_60`: survived (accepted, equivalent: equivalent: default for a missing expect; any value but 'failure' means success, as 'success' does (config always sets expect)); argument: Same behaviour on every input the function can receive: default for a missing expect; any value but 'failure' means success, as 'success' does (config always sets expect). So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `8a95bb014039ee73`

```diff
# netdryrun.checks.x__ping__mutmut_60: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -7,7 +7,7 @@
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
-            if p.get("expect", "success") == "failure":
+            if p.get("expect", ) == "failure":
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
```

`netdryrun.checks.x__ping__mutmut_63`: survived (accepted, equivalent: equivalent: default for a missing expect; any value but 'failure' means success, as 'success' does (config always sets expect)); argument: Same behaviour on every input the function can receive: default for a missing expect; any value but 'failure' means success, as 'success' does (config always sets expect). So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `61fae5418dd35b57`

```diff
# netdryrun.checks.x__ping__mutmut_63: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -7,7 +7,7 @@
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
-            if p.get("expect", "success") == "failure":
+            if p.get("expect", "XXsuccessXX") == "failure":
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
```

`netdryrun.checks.x__ping__mutmut_64`: survived (accepted, equivalent: equivalent: default for a missing expect; any value but 'failure' means success, as 'success' does (config always sets expect)); argument: Same behaviour on every input the function can receive: default for a missing expect; any value but 'failure' means success, as 'success' does (config always sets expect). So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `bd66698206cc5d6a`

```diff
# netdryrun.checks.x__ping__mutmut_64: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -7,7 +7,7 @@
         m = _UNREACHABLE.search(text)
         if m:
             why = f"0/{count} replies (destination unreachable: {m.group(0)})"
-            if p.get("expect", "success") == "failure":
+            if p.get("expect", "SUCCESS") == "failure":
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
```

`netdryrun.checks.x__ping__mutmut_72`: survived (accepted, message-text: message text only: the stderr quoted in the 'ping did not run' detail); argument: Changes only text: the stderr quoted in the 'ping did not run' detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `b96d73dec294704d`

```diff
# netdryrun.checks.x__ping__mutmut_72: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
-        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
+        err = None
         return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
```

`netdryrun.checks.x__ping__mutmut_73`: survived (accepted, message-text: message text only: the stderr quoted in the 'ping did not run' detail); argument: Changes only text: the stderr quoted in the 'ping did not run' detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `de103690e3e24530`

```diff
# netdryrun.checks.x__ping__mutmut_73: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
-        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
+        err = obs.evidence[-1].get("stderr", "").strip() if (obs.evidence) and False else ""
         return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
```

`netdryrun.checks.x__ping__mutmut_75`: survived (accepted, message-text: message text only: the stderr quoted in the 'ping did not run' detail); argument: Changes only text: the stderr quoted in the 'ping did not run' detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `a2fd27cd72eae81e`

```diff
# netdryrun.checks.x__ping__mutmut_75: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
-        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
+        err = obs.evidence[-1].get(None, "").strip() if obs.evidence else ""
         return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
```

`netdryrun.checks.x__ping__mutmut_81`: survived (accepted, message-text: message text only: the stderr quoted in the 'ping did not run' detail); argument: Changes only text: the stderr quoted in the 'ping did not run' detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `592dce8496e84aba`

```diff
# netdryrun.checks.x__ping__mutmut_81: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
-        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
+        err = obs.evidence[-1].get("XXstderrXX", "").strip() if obs.evidence else ""
         return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
```

`netdryrun.checks.x__ping__mutmut_82`: survived (accepted, message-text: message text only: the stderr quoted in the 'ping did not run' detail); argument: Changes only text: the stderr quoted in the 'ping did not run' detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `bc504b531c23c544`

```diff
# netdryrun.checks.x__ping__mutmut_82: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
-        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
+        err = obs.evidence[-1].get("STDERR", "").strip() if obs.evidence else ""
         return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
```

`netdryrun.checks.x__ping__mutmut_83`: survived (accepted, message-text: message text only: the stderr quoted in the 'ping did not run' detail); argument: Changes only text: the stderr quoted in the 'ping did not run' detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `b307ca86822a2867`

```diff
# netdryrun.checks.x__ping__mutmut_83: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
-        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
+        err = obs.evidence[-1].get("stderr", "XXXX").strip() if obs.evidence else ""
         return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
```

`netdryrun.checks.x__ping__mutmut_84`: survived (accepted, message-text: message text only: the stderr quoted in the 'ping did not run' detail); argument: Changes only text: the stderr quoted in the 'ping did not run' detail. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `7ec2812d16c91f5d`

```diff
# netdryrun.checks.x__ping__mutmut_84: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
                 return True, why, obs.evidence
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
-        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
+        err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else "XXXX"
         return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
```

`netdryrun.checks.x__ping__mutmut_86`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `5511d05a5b0e53e9`

```diff
# netdryrun.checks.x__ping__mutmut_86: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
         err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
-        return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
+        return False, f"error: ping did not run{': ' + err if (err) and False else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
         return received >= need, f"{received}/{sent} replies (need {need})", obs.evidence
```

`netdryrun.checks.x__ping__mutmut_87`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `825e8177cd4c8917`

```diff
# netdryrun.checks.x__ping__mutmut_87: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
         err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
-        return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
+        return False, f"error: ping did not run{': ' + err if (err) or True else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
         return received >= need, f"{received}/{sent} replies (need {need})", obs.evidence
```

`netdryrun.checks.x__ping__mutmut_89`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `782421908c1d392e`

```diff
# netdryrun.checks.x__ping__mutmut_89: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
         err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
-        return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
+        return False, f"error: ping did not run{'XX: XX' + err if err else ''}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
         return received >= need, f"{received}/{sent} replies (need {need})", obs.evidence
```

`netdryrun.checks.x__ping__mutmut_90`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `7ec627e2a475b906`

```diff
# netdryrun.checks.x__ping__mutmut_90: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             return False, why, obs.evidence
     if sent == 0:  # ping never ran properly (bad source address, missing VRF, ...): not a result
         err = obs.evidence[-1].get("stderr", "").strip() if obs.evidence else ""
-        return False, f"error: ping did not run{': ' + err if err else ''}", obs.evidence
+        return False, f"error: ping did not run{': ' + err if err else 'XXXX'}", obs.evidence
     if p.get("expect", "success") == "success":
         need = int(p.get("min_replies", max(1, sent - 1)))  # tolerate one lost packet (first-packet ARP)
         return received >= need, f"{received}/{sent} replies (need {need})", obs.evidence
```

## `checks._route` (20)

`netdryrun.checks.x__route__mutmut_32`: survived (accepted, equivalent: equivalent: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'); argument: Same behaviour on every input the function can receive: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `69ae803e4824b276`

```diff
# netdryrun.checks.x__route__mutmut_32: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -5,7 +5,7 @@
     active = [r for r in matching if r.active]
     # `is not False`, the same test is_post_convergence uses, so the evaluator and the scheduler can never
     # disagree on what a check means (config validation already insists on a real boolean)
-    if p.get("present", True) is not False:
+    if p.get("present", None) is not False:
         if active:
             return True, f"active via {active[0].protocol}", obs.evidence
         if p.get("active", True) is False and matching:
```

`netdryrun.checks.x__route__mutmut_34`: survived (accepted, equivalent: equivalent: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'); argument: Same behaviour on every input the function can receive: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `ed34e860b4b14741`

```diff
# netdryrun.checks.x__route__mutmut_34: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -5,7 +5,7 @@
     active = [r for r in matching if r.active]
     # `is not False`, the same test is_post_convergence uses, so the evaluator and the scheduler can never
     # disagree on what a check means (config validation already insists on a real boolean)
-    if p.get("present", True) is not False:
+    if p.get("present", ) is not False:
         if active:
             return True, f"active via {active[0].protocol}", obs.evidence
         if p.get("active", True) is False and matching:
```

`netdryrun.checks.x__route__mutmut_44`: survived (accepted, equivalent: equivalent: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'); argument: Same behaviour on every input the function can receive: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `79c20ed0ddfaf432`

```diff
# netdryrun.checks.x__route__mutmut_44: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -8,7 +8,7 @@
     if p.get("present", True) is not False:
         if active:
             return True, f"active via {active[0].protocol}", obs.evidence
-        if p.get("active", True) is False and matching:
+        if p.get("active", None) is False and matching:
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
         seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
```

`netdryrun.checks.x__route__mutmut_46`: survived (accepted, equivalent: equivalent: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'); argument: Same behaviour on every input the function can receive: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `32255ffebb371b50`

```diff
# netdryrun.checks.x__route__mutmut_46: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -8,7 +8,7 @@
     if p.get("present", True) is not False:
         if active:
             return True, f"active via {active[0].protocol}", obs.evidence
-        if p.get("active", True) is False and matching:
+        if p.get("active", ) is False and matching:
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
         seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
```

`netdryrun.checks.x__route__mutmut_57`: survived (accepted, message-text: message text only: the text of a detail or error message); argument: Changes only text: the text of a detail or error message. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `1ba2110fc7d34fe8`

```diff
# netdryrun.checks.x__route__mutmut_57: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
         if p.get("active", True) is False and matching:
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
-        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
+        seen = "XX, XX".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
         return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
```

`netdryrun.checks.x__route__mutmut_58`: survived (accepted, message-text: message text only: the text of a detail or error message); argument: Changes only text: the text of a detail or error message. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `3af93d9cce0bb518`

```diff
# netdryrun.checks.x__route__mutmut_58: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
         if p.get("active", True) is False and matching:
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
-        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
+        seen = ", ".join(f"{r.protocol}{'' if (r.active) and False else ' (inactive)'}" for r in obs.value) or "nothing"
         return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
```

`netdryrun.checks.x__route__mutmut_60`: survived (accepted, message-text: message text only: the text of a detail or error message); argument: Changes only text: the text of a detail or error message. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `892953c2fb42d6e2`

```diff
# netdryrun.checks.x__route__mutmut_60: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
         if p.get("active", True) is False and matching:
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
-        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
+        seen = ", ".join(f"{r.protocol}{'XXXX' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
         return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
```

`netdryrun.checks.x__route__mutmut_61`: survived (accepted, message-text: message text only: the text of a detail or error message); argument: Changes only text: the text of a detail or error message. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `6bd3c1555c4ff862`

```diff
# netdryrun.checks.x__route__mutmut_61: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
         if p.get("active", True) is False and matching:
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
-        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
+        seen = ", ".join(f"{r.protocol}{'' if r.active else 'XX (inactive)XX'}" for r in obs.value) or "nothing"
         return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
```

`netdryrun.checks.x__route__mutmut_63`: survived (accepted, message-text: message text only: the text of a detail or error message); argument: Changes only text: the text of a detail or error message. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `054d9decca0eb7bd`

```diff
# netdryrun.checks.x__route__mutmut_63: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
         if p.get("active", True) is False and matching:
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
-        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
+        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "XXnothingXX"
         return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
```

`netdryrun.checks.x__route__mutmut_64`: survived (accepted, message-text: message text only: the text of a detail or error message); argument: Changes only text: the text of a detail or error message. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `0ecd1737e9af0350`

```diff
# netdryrun.checks.x__route__mutmut_64: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
         if p.get("active", True) is False and matching:
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
-        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
+        seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "NOTHING"
         return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
```

`netdryrun.checks.x__route__mutmut_66`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `1e9055e8e477cb19`

```diff
# netdryrun.checks.x__route__mutmut_66: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
         seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
-        return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
+        return False, f"not active{' via ' + want_proto if (want_proto) and False else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
     if matching:
```

`netdryrun.checks.x__route__mutmut_67`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `e679f4bd983ca5c8`

```diff
# netdryrun.checks.x__route__mutmut_67: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
         seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
-        return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
+        return False, f"not active{' via ' + want_proto if (want_proto) or True else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
     if matching:
```

`netdryrun.checks.x__route__mutmut_69`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `7648d4978cb45185`

```diff
# netdryrun.checks.x__route__mutmut_69: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
         seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
-        return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
+        return False, f"not active{'XX via XX' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
     if matching:
```

`netdryrun.checks.x__route__mutmut_70`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `459833adcb0f6ad9`

```diff
# netdryrun.checks.x__route__mutmut_70: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
         seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
-        return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
+        return False, f"not active{' VIA ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
     if matching:
```

`netdryrun.checks.x__route__mutmut_71`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `ddc4a38953bb8cb9`

```diff
# netdryrun.checks.x__route__mutmut_71: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -12,7 +12,7 @@
             # present in the routing table, selected or not (e.g. a BGP default losing to a local one)
             return True, f"present via {matching[0].protocol} (not selected)", obs.evidence
         seen = ", ".join(f"{r.protocol}{'' if r.active else ' (inactive)'}" for r in obs.value) or "nothing"
-        return False, f"not active{' via ' + want_proto if want_proto else ''}; seen: {seen}", obs.evidence
+        return False, f"not active{' via ' + want_proto if want_proto else 'XXXX'}; seen: {seen}", obs.evidence
     # Absent means not in the routing table at all: a received-but-not-selected route
     # (e.g. a leaked default losing to a local one) is still a leak.
     if matching:
```

`netdryrun.checks.x__route__mutmut_75`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `0d668104e6011fd5`

```diff
# netdryrun.checks.x__route__mutmut_75: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -17,5 +17,5 @@
     # (e.g. a leaked default losing to a local one) is still a leak.
     if matching:
         r = matching[0]
-        return False, f"unexpectedly present via {r.protocol}{'' if r.active else ' (not selected)'}", obs.evidence
+        return False, f"unexpectedly present via {r.protocol}{'' if (r.active) and False else ' (not selected)'}", obs.evidence
     return True, "absent", obs.evidence
```

`netdryrun.checks.x__route__mutmut_77`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `5fa2ee3a77630a7a`

```diff
# netdryrun.checks.x__route__mutmut_77: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -17,5 +17,5 @@
     # (e.g. a leaked default losing to a local one) is still a leak.
     if matching:
         r = matching[0]
-        return False, f"unexpectedly present via {r.protocol}{'' if r.active else ' (not selected)'}", obs.evidence
+        return False, f"unexpectedly present via {r.protocol}{'XXXX' if r.active else ' (not selected)'}", obs.evidence
     return True, "absent", obs.evidence
```

`netdryrun.checks.x__route__mutmut_78`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `af3d0000780c5f26`

```diff
# netdryrun.checks.x__route__mutmut_78: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -17,5 +17,5 @@
     # (e.g. a leaked default losing to a local one) is still a leak.
     if matching:
         r = matching[0]
-        return False, f"unexpectedly present via {r.protocol}{'' if r.active else ' (not selected)'}", obs.evidence
+        return False, f"unexpectedly present via {r.protocol}{'' if r.active else 'XX (not selected)XX'}", obs.evidence
     return True, "absent", obs.evidence
```

`netdryrun.checks.x__route__mutmut_81`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `e00117cd4cb5d2d8`

```diff
# netdryrun.checks.x__route__mutmut_81: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -18,4 +18,4 @@
     if matching:
         r = matching[0]
         return False, f"unexpectedly present via {r.protocol}{'' if r.active else ' (not selected)'}", obs.evidence
-    return True, "absent", obs.evidence
+    return True, "XXabsentXX", obs.evidence
```

`netdryrun.checks.x__route__mutmut_82`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `053b4b1c00ac88da`

```diff
# netdryrun.checks.x__route__mutmut_82: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -18,4 +18,4 @@
     if matching:
         r = matching[0]
         return False, f"unexpectedly present via {r.protocol}{'' if r.active else ' (not selected)'}", obs.evidence
-    return True, "absent", obs.evidence
+    return True, "ABSENT", obs.evidence
```

## `drivers.frr._route_table` (18)

`netdryrun.drivers.frr.x__route_table__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `7d96088b6aa52080`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_10: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     that isn't a prefix (a warning, output keyed by VRF name) is unexpected."""
     data = load_json(command, text)
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(command, )
     table = {}
     for key, entries in data.items():
         net = network(command, key)
```

`netdryrun.drivers.frr.x__route_table__mutmut_13`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `3dddfbc78098915e`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_13: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -6,7 +6,7 @@
         raise unexpected(command, text)
     table = {}
     for key, entries in data.items():
-        net = network(command, key)
+        net = network(None, key)
         if not isinstance(entries, list) or not entries:
             raise unexpected(command, f"{key}: {str(entries)[:150]}")
         for e in entries:
```

`netdryrun.drivers.frr.x__route_table__mutmut_2`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `e9e85b6faee88aa7`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_2: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -1,7 +1,7 @@
 def _route_table(command: str, text: str) -> dict[ipaddress._BaseNetwork, list[dict]]:
     """zebra's `show ip route ... json`: {prefix: [entry, ...]}. `{}` is a real empty answer; any key
     that isn't a prefix (a warning, output keyed by VRF name) is unexpected."""
-    data = load_json(command, text)
+    data = load_json(None, text)
     if not isinstance(data, dict):
         raise unexpected(command, text)
     table = {}
```

`netdryrun.drivers.frr.x__route_table__mutmut_20`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `e847ae102d35b869`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_20: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -8,7 +8,7 @@
     for key, entries in data.items():
         net = network(command, key)
         if not isinstance(entries, list) or not entries:
-            raise unexpected(command, f"{key}: {str(entries)[:150]}")
+            raise unexpected(None, f"{key}: {str(entries)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
                 raise unexpected(command, f"{key}: {str(e)[:150]}")
```

`netdryrun.drivers.frr.x__route_table__mutmut_21`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `ea6b726cca1236c2`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_21: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -8,7 +8,7 @@
     for key, entries in data.items():
         net = network(command, key)
         if not isinstance(entries, list) or not entries:
-            raise unexpected(command, f"{key}: {str(entries)[:150]}")
+            raise unexpected(command, None)
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
                 raise unexpected(command, f"{key}: {str(e)[:150]}")
```

`netdryrun.drivers.frr.x__route_table__mutmut_22`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `6d82d860c8b9c644`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_22: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -8,7 +8,7 @@
     for key, entries in data.items():
         net = network(command, key)
         if not isinstance(entries, list) or not entries:
-            raise unexpected(command, f"{key}: {str(entries)[:150]}")
+            raise unexpected(f"{key}: {str(entries)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
                 raise unexpected(command, f"{key}: {str(e)[:150]}")
```

`netdryrun.drivers.frr.x__route_table__mutmut_23`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `640de4f8e03240cf`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_23: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -8,7 +8,7 @@
     for key, entries in data.items():
         net = network(command, key)
         if not isinstance(entries, list) or not entries:
-            raise unexpected(command, f"{key}: {str(entries)[:150]}")
+            raise unexpected(command, )
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
                 raise unexpected(command, f"{key}: {str(e)[:150]}")
```

`netdryrun.drivers.frr.x__route_table__mutmut_24`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `bed2654ea13cecfa`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_24: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -8,7 +8,7 @@
     for key, entries in data.items():
         net = network(command, key)
         if not isinstance(entries, list) or not entries:
-            raise unexpected(command, f"{key}: {str(entries)[:150]}")
+            raise unexpected(command, f"{key}: {str(None)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
                 raise unexpected(command, f"{key}: {str(e)[:150]}")
```

`netdryrun.drivers.frr.x__route_table__mutmut_25`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `e4e57e58b1e77789`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_25: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -8,7 +8,7 @@
     for key, entries in data.items():
         net = network(command, key)
         if not isinstance(entries, list) or not entries:
-            raise unexpected(command, f"{key}: {str(entries)[:150]}")
+            raise unexpected(command, f"{key}: {str(entries)[:151]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
                 raise unexpected(command, f"{key}: {str(e)[:150]}")
```

`netdryrun.drivers.frr.x__route_table__mutmut_29`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `452f8d15ad9efbe4`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_29: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -11,6 +11,6 @@
             raise unexpected(command, f"{key}: {str(entries)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
-                raise unexpected(command, f"{key}: {str(e)[:150]}")
+                raise unexpected(None, f"{key}: {str(e)[:150]}")
         table[net] = entries
     return table
```

`netdryrun.drivers.frr.x__route_table__mutmut_30`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `f5840f1596252e1c`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_30: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -11,6 +11,6 @@
             raise unexpected(command, f"{key}: {str(entries)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
-                raise unexpected(command, f"{key}: {str(e)[:150]}")
+                raise unexpected(command, None)
         table[net] = entries
     return table
```

`netdryrun.drivers.frr.x__route_table__mutmut_31`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `b0e51fcee0470994`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_31: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -11,6 +11,6 @@
             raise unexpected(command, f"{key}: {str(entries)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
-                raise unexpected(command, f"{key}: {str(e)[:150]}")
+                raise unexpected(f"{key}: {str(e)[:150]}")
         table[net] = entries
     return table
```

`netdryrun.drivers.frr.x__route_table__mutmut_32`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `c3641fb643b37af8`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_32: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -11,6 +11,6 @@
             raise unexpected(command, f"{key}: {str(entries)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
-                raise unexpected(command, f"{key}: {str(e)[:150]}")
+                raise unexpected(command, )
         table[net] = entries
     return table
```

`netdryrun.drivers.frr.x__route_table__mutmut_33`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `82962ea5c566fe74`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_33: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -11,6 +11,6 @@
             raise unexpected(command, f"{key}: {str(entries)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
-                raise unexpected(command, f"{key}: {str(e)[:150]}")
+                raise unexpected(command, f"{key}: {str(None)[:150]}")
         table[net] = entries
     return table
```

`netdryrun.drivers.frr.x__route_table__mutmut_34`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `4b1151e845c5ae68`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_34: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -11,6 +11,6 @@
             raise unexpected(command, f"{key}: {str(entries)[:150]}")
         for e in entries:
             if not isinstance(e, dict) or not isinstance(e.get("protocol"), str):
-                raise unexpected(command, f"{key}: {str(e)[:150]}")
+                raise unexpected(command, f"{key}: {str(e)[:151]}")
         table[net] = entries
     return table
```

`netdryrun.drivers.frr.x__route_table__mutmut_7`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `9a3c76562c5914e5`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_7: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     that isn't a prefix (a warning, output keyed by VRF name) is unexpected."""
     data = load_json(command, text)
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(None, text)
     table = {}
     for key, entries in data.items():
         net = network(command, key)
```

`netdryrun.drivers.frr.x__route_table__mutmut_8`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `7245ec5215625baf`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_8: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     that isn't a prefix (a warning, output keyed by VRF name) is unexpected."""
     data = load_json(command, text)
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(command, None)
     table = {}
     for key, entries in data.items():
         net = network(command, key)
```

`netdryrun.drivers.frr.x__route_table__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `e9e8548b935149b6`

```diff
# netdryrun.drivers.frr.x__route_table__mutmut_9: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     that isn't a prefix (a warning, output keyed by VRF name) is unexpected."""
     data = load_json(command, text)
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(text)
     table = {}
     for key, entries in data.items():
         net = network(command, key)
```

## `config.load` (17)

`netdryrun.config.x_load__mutmut_11`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `44a8d15c79902e56`

```diff
# netdryrun.config.x_load__mutmut_11: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         path = path / "netdryrun.yml"
     if not path.exists():
         raise ConfigError(f"{path}: not found")
-    data = load_yaml(path.read_text(encoding="utf-8"), str(path))
+    data = load_yaml(path.read_text(encoding="utf-8"), None)
     if data is None:
         data = {}
     if not isinstance(data, dict):
```

`netdryrun.config.x_load__mutmut_13`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `076ab5a4fd650d79`

```diff
# netdryrun.config.x_load__mutmut_13: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         path = path / "netdryrun.yml"
     if not path.exists():
         raise ConfigError(f"{path}: not found")
-    data = load_yaml(path.read_text(encoding="utf-8"), str(path))
+    data = load_yaml(path.read_text(encoding="utf-8"), )
     if data is None:
         data = {}
     if not isinstance(data, dict):
```

`netdryrun.config.x_load__mutmut_16`: survived (accepted, equivalent: equivalent: 'UTF-8' and 'utf-8' are the same codec); diff fingerprint `3dc627cd37a9ef13`

```diff
# netdryrun.config.x_load__mutmut_16: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         path = path / "netdryrun.yml"
     if not path.exists():
         raise ConfigError(f"{path}: not found")
-    data = load_yaml(path.read_text(encoding="utf-8"), str(path))
+    data = load_yaml(path.read_text(encoding="UTF-8"), str(path))
     if data is None:
         data = {}
     if not isinstance(data, dict):
```

`netdryrun.config.x_load__mutmut_17`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `d75b8c6996b6031e`

```diff
# netdryrun.config.x_load__mutmut_17: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         path = path / "netdryrun.yml"
     if not path.exists():
         raise ConfigError(f"{path}: not found")
-    data = load_yaml(path.read_text(encoding="utf-8"), str(path))
+    data = load_yaml(path.read_text(encoding="utf-8"), str(None))
     if data is None:
         data = {}
     if not isinstance(data, dict):
```

`netdryrun.config.x_load__mutmut_19`: survived (accepted, message-text: message text only: an empty file is still refused (as 'top level must be a mapping' instead of 'missing lab')); diff fingerprint `dc684ec0867e5dd4`

```diff
# netdryrun.config.x_load__mutmut_19: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -6,7 +6,7 @@
         raise ConfigError(f"{path}: not found")
     data = load_yaml(path.read_text(encoding="utf-8"), str(path))
     if data is None:
-        data = {}
+        data = None
     if not isinstance(data, dict):
         raise ConfigError(f"{path}: top level must be a mapping")
     _reject_unknown(str(path), data, TOP_LEVEL_KEYS, "top-level key")
```

`netdryrun.config.x_load__mutmut_21`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `e6f5acdcc359b803`

```diff
# netdryrun.config.x_load__mutmut_21: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -8,7 +8,7 @@
     if data is None:
         data = {}
     if not isinstance(data, dict):
-        raise ConfigError(f"{path}: top level must be a mapping")
+        raise ConfigError(None)
     _reject_unknown(str(path), data, TOP_LEVEL_KEYS, "top-level key")
     if "lab" not in data:
         raise ConfigError(f"{path}: missing 'lab' (path to the containerlab topology file)")
```

`netdryrun.config.x_load__mutmut_22`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `71c6fcc93d1dcfde`

```diff
# netdryrun.config.x_load__mutmut_22: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -9,7 +9,7 @@
         data = {}
     if not isinstance(data, dict):
         raise ConfigError(f"{path}: top level must be a mapping")
-    _reject_unknown(str(path), data, TOP_LEVEL_KEYS, "top-level key")
+    _reject_unknown(None, data, TOP_LEVEL_KEYS, "top-level key")
     if "lab" not in data:
         raise ConfigError(f"{path}: missing 'lab' (path to the containerlab topology file)")
     _string(str(path), "lab", data["lab"])
```

`netdryrun.config.x_load__mutmut_30`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `e76ab9c921a6c193`

```diff
# netdryrun.config.x_load__mutmut_30: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -9,7 +9,7 @@
         data = {}
     if not isinstance(data, dict):
         raise ConfigError(f"{path}: top level must be a mapping")
-    _reject_unknown(str(path), data, TOP_LEVEL_KEYS, "top-level key")
+    _reject_unknown(str(None), data, TOP_LEVEL_KEYS, "top-level key")
     if "lab" not in data:
         raise ConfigError(f"{path}: missing 'lab' (path to the containerlab topology file)")
     _string(str(path), "lab", data["lab"])
```

`netdryrun.config.x_load__mutmut_36`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `da72fa9df9476e97`

```diff
# netdryrun.config.x_load__mutmut_36: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
         raise ConfigError(f"{path}: top level must be a mapping")
     _reject_unknown(str(path), data, TOP_LEVEL_KEYS, "top-level key")
     if "lab" not in data:
-        raise ConfigError(f"{path}: missing 'lab' (path to the containerlab topology file)")
+        raise ConfigError(None)
     _string(str(path), "lab", data["lab"])
     lab = (path.parent / data["lab"]).resolve()
     if not lab.is_file():
```

`netdryrun.config.x_load__mutmut_37`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `ab11ffd43ed2cba1`

```diff
# netdryrun.config.x_load__mutmut_37: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,7 +12,7 @@
     _reject_unknown(str(path), data, TOP_LEVEL_KEYS, "top-level key")
     if "lab" not in data:
         raise ConfigError(f"{path}: missing 'lab' (path to the containerlab topology file)")
-    _string(str(path), "lab", data["lab"])
+    _string(None, "lab", data["lab"])
     lab = (path.parent / data["lab"]).resolve()
     if not lab.is_file():
         raise ConfigError(f"{path}: lab file {lab} not found")
```

`netdryrun.config.x_load__mutmut_43`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `6b05de015549bcad`

```diff
# netdryrun.config.x_load__mutmut_43: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,7 +12,7 @@
     _reject_unknown(str(path), data, TOP_LEVEL_KEYS, "top-level key")
     if "lab" not in data:
         raise ConfigError(f"{path}: missing 'lab' (path to the containerlab topology file)")
-    _string(str(path), "lab", data["lab"])
+    _string(str(None), "lab", data["lab"])
     lab = (path.parent / data["lab"]).resolve()
     if not lab.is_file():
         raise ConfigError(f"{path}: lab file {lab} not found")
```

`netdryrun.config.x_load__mutmut_57`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `9b33d42f0469e977`

```diff
# netdryrun.config.x_load__mutmut_57: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -16,7 +16,7 @@
     lab = (path.parent / data["lab"]).resolve()
     if not lab.is_file():
         raise ConfigError(f"{path}: lab file {lab} not found")
-    timeout = _seconds(str(path), "timeout", data["timeout"]) if "timeout" in data else 120.0
+    timeout = _seconds(None, "timeout", data["timeout"]) if "timeout" in data else 120.0
     raw_checks = data.get("checks")
     if not raw_checks:
         raise ConfigError(f"{path}: no checks defined")
```

`netdryrun.config.x_load__mutmut_63`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `f7e9fc8311924b7d`

```diff
# netdryrun.config.x_load__mutmut_63: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -16,7 +16,7 @@
     lab = (path.parent / data["lab"]).resolve()
     if not lab.is_file():
         raise ConfigError(f"{path}: lab file {lab} not found")
-    timeout = _seconds(str(path), "timeout", data["timeout"]) if "timeout" in data else 120.0
+    timeout = _seconds(str(None), "timeout", data["timeout"]) if "timeout" in data else 120.0
     raw_checks = data.get("checks")
     if not raw_checks:
         raise ConfigError(f"{path}: no checks defined")
```

`netdryrun.config.x_load__mutmut_77`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `786db07ca07ec529`

```diff
# netdryrun.config.x_load__mutmut_77: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -19,7 +19,7 @@
     timeout = _seconds(str(path), "timeout", data["timeout"]) if "timeout" in data else 120.0
     raw_checks = data.get("checks")
     if not raw_checks:
-        raise ConfigError(f"{path}: no checks defined")
+        raise ConfigError(None)
     if not isinstance(raw_checks, list):
         raise ConfigError(f"{path}: checks must be a list of checks")
     checks = [_validate_check(i, c, timeout) for i, c in enumerate(raw_checks)]
```

`netdryrun.config.x_load__mutmut_8`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `80d8469d11928335`

```diff
# netdryrun.config.x_load__mutmut_8: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -3,7 +3,7 @@
     if path.is_dir():
         path = path / "netdryrun.yml"
     if not path.exists():
-        raise ConfigError(f"{path}: not found")
+        raise ConfigError(None)
     data = load_yaml(path.read_text(encoding="utf-8"), str(path))
     if data is None:
         data = {}
```

`netdryrun.config.x_load__mutmut_89`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `c7b481ca6b7220aa`

```diff
# netdryrun.config.x_load__mutmut_89: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -23,7 +23,7 @@
     if not isinstance(raw_checks, list):
         raise ConfigError(f"{path}: checks must be a list of checks")
     checks = [_validate_check(i, c, timeout) for i, c in enumerate(raw_checks)]
-    drivers, setup = _validate_nodes(str(path), data)
+    drivers, setup = _validate_nodes(None, data)
     scenarios: list[Scenario] = []
     if "scenarios" in data:
         if not isinstance(data["scenarios"], list) or not data["scenarios"]:
```

`netdryrun.config.x_load__mutmut_93`: survived (accepted, message-text: message text only: the file name shown in errors); diff fingerprint `d92d086f1e715714`

```diff
# netdryrun.config.x_load__mutmut_93: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -23,7 +23,7 @@
     if not isinstance(raw_checks, list):
         raise ConfigError(f"{path}: checks must be a list of checks")
     checks = [_validate_check(i, c, timeout) for i, c in enumerate(raw_checks)]
-    drivers, setup = _validate_nodes(str(path), data)
+    drivers, setup = _validate_nodes(str(None), data)
     scenarios: list[Scenario] = []
     if "scenarios" in data:
         if not isinstance(data["scenarios"], list) or not data["scenarios"]:
```

## `config.load_yaml` (15)

`netdryrun.config.x_load_yaml__mutmut_1`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `23d500ccb9c54ea8`

```diff
# netdryrun.config.x_load_yaml__mutmut_1: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,4 +1,4 @@
-def load_yaml(text: str, source: str = "<yaml>") -> Any:
+def load_yaml(text: str, source: str = "XX<yaml>XX") -> Any:
     """Parse YAML strictly (duplicate keys are an error); any YAML error becomes a ConfigError."""
     try:
         return yaml.load(text, Loader=_StrictLoader)  # a SafeLoader subclass: no arbitrary objects
```

`netdryrun.config.x_load_yaml__mutmut_13`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `b3ef67efbc685f43`

```diff
# netdryrun.config.x_load_yaml__mutmut_13: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         return yaml.load(text, Loader=_StrictLoader)  # a SafeLoader subclass: no arbitrary objects
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
-        mark = getattr(e, "problem_mark", None)
+        mark = getattr(e, "XXproblem_markXX", None)
         where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_14`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `235337d73c6f38e4`

```diff
# netdryrun.config.x_load_yaml__mutmut_14: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         return yaml.load(text, Loader=_StrictLoader)  # a SafeLoader subclass: no arbitrary objects
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
-        mark = getattr(e, "problem_mark", None)
+        mark = getattr(e, "PROBLEM_MARK", None)
         where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_15`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `7bb89f8a1fe5b9c9`

```diff
# netdryrun.config.x_load_yaml__mutmut_15: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,6 +5,6 @@
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
-        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
+        where = None
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_16`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `6d3b9266fdaad52e`

```diff
# netdryrun.config.x_load_yaml__mutmut_16: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,6 +5,6 @@
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
-        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
+        where = f" at line {mark.line + 1}, column {mark.column + 1}" if (mark is not None) and False else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_18`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `45989af125e1b302`

```diff
# netdryrun.config.x_load_yaml__mutmut_18: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,6 +5,6 @@
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
-        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
+        where = f" at line {mark.line - 1}, column {mark.column + 1}" if mark is not None else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_19`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `4bf543e57741a0f9`

```diff
# netdryrun.config.x_load_yaml__mutmut_19: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,6 +5,6 @@
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
-        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
+        where = f" at line {mark.line + 2}, column {mark.column + 1}" if mark is not None else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_2`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `76f084feb86953f3`

```diff
# netdryrun.config.x_load_yaml__mutmut_2: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,4 +1,4 @@
-def load_yaml(text: str, source: str = "<yaml>") -> Any:
+def load_yaml(text: str, source: str = "<YAML>") -> Any:
     """Parse YAML strictly (duplicate keys are an error); any YAML error becomes a ConfigError."""
     try:
         return yaml.load(text, Loader=_StrictLoader)  # a SafeLoader subclass: no arbitrary objects
```

`netdryrun.config.x_load_yaml__mutmut_20`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `4f730b0bfa7421d8`

```diff
# netdryrun.config.x_load_yaml__mutmut_20: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,6 +5,6 @@
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
-        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
+        where = f" at line {mark.line + 1}, column {mark.column - 1}" if mark is not None else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_21`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `ccaa6b2933c56b9f`

```diff
# netdryrun.config.x_load_yaml__mutmut_21: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,6 +5,6 @@
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
-        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
+        where = f" at line {mark.line + 1}, column {mark.column + 2}" if mark is not None else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_23`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `faaea59def5ace86`

```diff
# netdryrun.config.x_load_yaml__mutmut_23: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,6 +5,6 @@
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
-        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
+        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else "XXXX"
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_33`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `b25141ee8dcc079d`

```diff
# netdryrun.config.x_load_yaml__mutmut_33: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -6,5 +6,5 @@
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
         where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
-        problem = getattr(e, "problem", None) or str(e).splitlines()[0]
+        problem = getattr(e, "problem", None) or str(None).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_34`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `0d78e393aee354b5`

```diff
# netdryrun.config.x_load_yaml__mutmut_34: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -6,5 +6,5 @@
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
         mark = getattr(e, "problem_mark", None)
         where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
-        problem = getattr(e, "problem", None) or str(e).splitlines()[0]
+        problem = getattr(e, "problem", None) or str(e).splitlines()[1]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_7`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `5d6d958329c8a2c2`

```diff
# netdryrun.config.x_load_yaml__mutmut_7: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         return yaml.load(text, Loader=_StrictLoader)  # a SafeLoader subclass: no arbitrary objects
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
-        mark = getattr(e, "problem_mark", None)
+        mark = None
         where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

`netdryrun.config.x_load_yaml__mutmut_8`: survived (accepted, message-text: message text only: the position or wording of a YAML error, still a ConfigError); diff fingerprint `4c78c0940387ca39`

```diff
# netdryrun.config.x_load_yaml__mutmut_8: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         return yaml.load(text, Loader=_StrictLoader)  # a SafeLoader subclass: no arbitrary objects
     except yaml.YAMLError as e:
         # one line, with the position: PyYAML's own message spans several lines with a caret drawing
-        mark = getattr(e, "problem_mark", None)
+        mark = getattr(None, "problem_mark", None)
         where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
         problem = getattr(e, "problem", None) or str(e).splitlines()[0]
         raise ConfigError(f"{source}: not valid YAML{where}: {' '.join(str(problem).split())}") from None
```

## `drivers.eos._bgp_entries` (15)

`netdryrun.drivers.eos.x__bgp_entries__mutmut_13`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `b7448e0ee66b47cc`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_13: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,6 +1,6 @@
 def _bgp_entries(command: str, text: str, vrf: str) -> dict:
     entry = _vrf(command, _json(command, text), vrf)
-    entries = _table(command, entry, "bgpRouteEntries")
+    entries = _table(None, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
             raise unexpected(command, f"{key}: {str(e)[:150]}")
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_2`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `6c94c9ed500d8f30`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_2: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,5 +1,5 @@
 def _bgp_entries(command: str, text: str, vrf: str) -> dict:
-    entry = _vrf(command, _json(command, text), vrf)
+    entry = _vrf(None, _json(command, text), vrf)
     entries = _table(command, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_25`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `eee2c36d411c83f2`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_25: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,7 +3,7 @@
     entries = _table(command, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
-            raise unexpected(command, f"{key}: {str(e)[:150]}")
+            raise unexpected(None, f"{key}: {str(e)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
                 raise unexpected(command, f"{key} path: {str(p)[:150]}")
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_26`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `8d25975485893b08`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_26: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,7 +3,7 @@
     entries = _table(command, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
-            raise unexpected(command, f"{key}: {str(e)[:150]}")
+            raise unexpected(command, None)
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
                 raise unexpected(command, f"{key} path: {str(p)[:150]}")
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_27`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `c035994fbecb85f5`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_27: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,7 +3,7 @@
     entries = _table(command, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
-            raise unexpected(command, f"{key}: {str(e)[:150]}")
+            raise unexpected(f"{key}: {str(e)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
                 raise unexpected(command, f"{key} path: {str(p)[:150]}")
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_28`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `284817930db29970`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_28: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,7 +3,7 @@
     entries = _table(command, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
-            raise unexpected(command, f"{key}: {str(e)[:150]}")
+            raise unexpected(command, )
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
                 raise unexpected(command, f"{key} path: {str(p)[:150]}")
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_29`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `86b394403070735b`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_29: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,7 +3,7 @@
     entries = _table(command, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
-            raise unexpected(command, f"{key}: {str(e)[:150]}")
+            raise unexpected(command, f"{key}: {str(None)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
                 raise unexpected(command, f"{key} path: {str(p)[:150]}")
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_30`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `b6a5d6df296c70a1`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_30: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,7 +3,7 @@
     entries = _table(command, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
-            raise unexpected(command, f"{key}: {str(e)[:150]}")
+            raise unexpected(command, f"{key}: {str(e)[:151]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
                 raise unexpected(command, f"{key} path: {str(p)[:150]}")
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_35`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `b872e17f21d6a855`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_35: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -6,5 +6,5 @@
             raise unexpected(command, f"{key}: {str(e)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
-                raise unexpected(command, f"{key} path: {str(p)[:150]}")
+                raise unexpected(None, f"{key} path: {str(p)[:150]}")
     return entries
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_36`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `aa8a5916e8a80977`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_36: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -6,5 +6,5 @@
             raise unexpected(command, f"{key}: {str(e)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
-                raise unexpected(command, f"{key} path: {str(p)[:150]}")
+                raise unexpected(command, None)
     return entries
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_37`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `29d964f0aea2feca`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_37: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -6,5 +6,5 @@
             raise unexpected(command, f"{key}: {str(e)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
-                raise unexpected(command, f"{key} path: {str(p)[:150]}")
+                raise unexpected(f"{key} path: {str(p)[:150]}")
     return entries
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_38`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `ccd250d776eaea95`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_38: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -6,5 +6,5 @@
             raise unexpected(command, f"{key}: {str(e)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
-                raise unexpected(command, f"{key} path: {str(p)[:150]}")
+                raise unexpected(command, )
     return entries
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_39`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `d58462afbd8e2d2c`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_39: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -6,5 +6,5 @@
             raise unexpected(command, f"{key}: {str(e)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
-                raise unexpected(command, f"{key} path: {str(p)[:150]}")
+                raise unexpected(command, f"{key} path: {str(None)[:150]}")
     return entries
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_40`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `a316e9fec4e60f5b`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_40: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -6,5 +6,5 @@
             raise unexpected(command, f"{key}: {str(e)[:150]}")
         for p in e["bgpRoutePaths"]:
             if not isinstance(p, dict):
-                raise unexpected(command, f"{key} path: {str(p)[:150]}")
+                raise unexpected(command, f"{key} path: {str(p)[:151]}")
     return entries
```

`netdryrun.drivers.eos.x__bgp_entries__mutmut_8`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `08a2d94f2969d488`

```diff
# netdryrun.drivers.eos.x__bgp_entries__mutmut_8: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,5 +1,5 @@
 def _bgp_entries(command: str, text: str, vrf: str) -> dict:
-    entry = _vrf(command, _json(command, text), vrf)
+    entry = _vrf(command, _json(None, text), vrf)
     entries = _table(command, entry, "bgpRouteEntries")
     for key, e in entries.items():
         if not isinstance(e, dict) or not isinstance(e.get("bgpRoutePaths"), list):
```

## `runner._yaml_problem` (15)

`netdryrun.runner.x__yaml_problem__mutmut_1`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `7867679747eda80e`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_1: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
-    mark = getattr(e, "problem_mark", None)
+    mark = None
     where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_10`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `f92cacd2a4d8a86e`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_10: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
-    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
+    where = f" (line {mark.line + 1}, column {mark.column + 1})" if (mark) and False else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_12`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `1503163518353a41`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_12: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
-    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
+    where = f" (line {mark.line - 1}, column {mark.column + 1})" if mark else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_13`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `96cf77c3843645d3`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_13: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
-    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
+    where = f" (line {mark.line + 2}, column {mark.column + 1})" if mark else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_14`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `def09e7cf54b7761`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_14: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
-    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
+    where = f" (line {mark.line + 1}, column {mark.column - 1})" if mark else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_15`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `90e67865058711fc`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_15: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
-    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
+    where = f" (line {mark.line + 1}, column {mark.column + 2})" if mark else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_16`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `4fb34992484427b1`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_16: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
-    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
+    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else "XXXX"
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_17`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `add606766f48abae`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_17: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
     where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
-    return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
+    return f"not valid YAML{where}: {getattr(e, 'problem', None) and e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_18`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `fb4be10ca993508e`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_18: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
     where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
-    return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
+    return f"not valid YAML{where}: {getattr(None, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_2`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `7668ec12543b5501`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_2: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
-    mark = getattr(e, "problem_mark", None)
+    mark = getattr(None, "problem_mark", None)
     where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_23`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `9f87eabff9d0c057`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_23: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
     where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
-    return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
+    return f"not valid YAML{where}: {getattr(e, 'XXproblemXX', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_24`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `2d49cd34d392df0b`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_24: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
     where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
-    return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
+    return f"not valid YAML{where}: {getattr(e, 'PROBLEM', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_7`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `d3a623faac5692f6`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_7: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
-    mark = getattr(e, "problem_mark", None)
+    mark = getattr(e, "XXproblem_markXX", None)
     where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_8`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `3b943540fd5bda41`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_8: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
-    mark = getattr(e, "problem_mark", None)
+    mark = getattr(e, "PROBLEM_MARK", None)
     where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

`netdryrun.runner.x__yaml_problem__mutmut_9`: survived (accepted, message-text: message text only: the position or wording of a YAML error message); diff fingerprint `227982ab86b1ebb6`

```diff
# netdryrun.runner.x__yaml_problem__mutmut_9: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,4 +1,4 @@
 def _yaml_problem(e: yaml.YAMLError) -> str:
     mark = getattr(e, "problem_mark", None)
-    where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
+    where = None
     return f"not valid YAML{where}: {getattr(e, 'problem', None) or e}"
```

## `config._StrictLoader.construct_mapping` (13)

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_1`: survived (accepted, equivalent: equivalent: construction depth; keys are scalars and the constructed mapping is the same); diff fingerprint `6a6ebc4580c3e05d`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_1: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,4 +1,4 @@
-def construct_mapping(self, node, deep=False):
+def construct_mapping(self, node, deep=True):
     if isinstance(node, yaml.MappingNode):
         seen: dict[Any, int] = {}
         for key_node, _ in node.value:
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_11`: survived (accepted, equivalent: equivalent: construction depth; keys are scalars and the constructed mapping is the same); diff fingerprint `2c3e5f41f0391525`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_11: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         for key_node, _ in node.value:
             if key_node.tag == "tag:yaml.org,2002:merge":
                 continue   # `<<: *anchor` merges are allowed, and explicit keys override them
-            key = self.construct_object(key_node, deep=True)
+            key = self.construct_object(key_node, )
             try:
                 first = seen.get(key)
             except TypeError:
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_12`: survived (accepted, equivalent: equivalent: construction depth; keys are scalars and the constructed mapping is the same); diff fingerprint `c27ca04a05df391d`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_12: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         for key_node, _ in node.value:
             if key_node.tag == "tag:yaml.org,2002:merge":
                 continue   # `<<: *anchor` merges are allowed, and explicit keys override them
-            key = self.construct_object(key_node, deep=True)
+            key = self.construct_object(key_node, deep=False)
             try:
                 first = seen.get(key)
             except TypeError:
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_15`: survived (accepted, equivalent: equivalent: after an unhashable key SafeLoader refuses the mapping anyway, so stopping the duplicate scan there changes nothing); diff fingerprint `c385664d1ea4aa1c`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_15: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -8,7 +8,7 @@
             try:
                 first = seen.get(key)
             except TypeError:
-                continue   # unhashable key: SafeLoader reports it
+                break   # unhashable key: SafeLoader reports it
             if first is not None:
                 raise yaml.constructor.ConstructorError(
                     "while reading a mapping", node.start_mark,
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_17`: survived (accepted, message-text: message text only: the text or position of the duplicate-key error, still a ConfigError); diff fingerprint `6ab645810bf14441`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_17: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
                 continue   # unhashable key: SafeLoader reports it
             if first is not None:
                 raise yaml.constructor.ConstructorError(
-                    "while reading a mapping", node.start_mark,
+                    None, node.start_mark,
                     f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
             seen[key] = key_node.start_mark.line
     return super().construct_mapping(node, deep=deep)
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_18`: survived (accepted, message-text: message text only: the text or position of the duplicate-key error, still a ConfigError); diff fingerprint `add7e2910435ee30`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_18: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
                 continue   # unhashable key: SafeLoader reports it
             if first is not None:
                 raise yaml.constructor.ConstructorError(
-                    "while reading a mapping", node.start_mark,
+                    "while reading a mapping", None,
                     f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
             seen[key] = key_node.start_mark.line
     return super().construct_mapping(node, deep=deep)
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_20`: survived (accepted, message-text: message text only: the text or position of the duplicate-key error, still a ConfigError); diff fingerprint `dd097ebc90235510`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_20: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,6 +12,6 @@
             if first is not None:
                 raise yaml.constructor.ConstructorError(
                     "while reading a mapping", node.start_mark,
-                    f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
+                    f"duplicate key {key!r} (first defined on line {first + 1})", None)
             seen[key] = key_node.start_mark.line
     return super().construct_mapping(node, deep=deep)
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_24`: survived (accepted, message-text: message text only: the text or position of the duplicate-key error, still a ConfigError); diff fingerprint `7d4c7589cd2e1b80`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_24: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -12,6 +12,6 @@
             if first is not None:
                 raise yaml.constructor.ConstructorError(
                     "while reading a mapping", node.start_mark,
-                    f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
+                    f"duplicate key {key!r} (first defined on line {first + 1})", )
             seen[key] = key_node.start_mark.line
     return super().construct_mapping(node, deep=deep)
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_25`: survived (accepted, message-text: message text only: the text or position of the duplicate-key error, still a ConfigError); diff fingerprint `54a1068af7238e2c`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_25: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
                 continue   # unhashable key: SafeLoader reports it
             if first is not None:
                 raise yaml.constructor.ConstructorError(
-                    "while reading a mapping", node.start_mark,
+                    "XXwhile reading a mappingXX", node.start_mark,
                     f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
             seen[key] = key_node.start_mark.line
     return super().construct_mapping(node, deep=deep)
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_26`: survived (accepted, message-text: message text only: the text or position of the duplicate-key error, still a ConfigError); diff fingerprint `26cf6eeed59a14a7`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_26: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,7 +11,7 @@
                 continue   # unhashable key: SafeLoader reports it
             if first is not None:
                 raise yaml.constructor.ConstructorError(
-                    "while reading a mapping", node.start_mark,
+                    "WHILE READING A MAPPING", node.start_mark,
                     f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
             seen[key] = key_node.start_mark.line
     return super().construct_mapping(node, deep=deep)
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_31`: survived (accepted, equivalent: equivalent: construction depth; keys are scalars and the constructed mapping is the same); diff fingerprint `2eb201089dc32af8`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_31: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -14,4 +14,4 @@
                     "while reading a mapping", node.start_mark,
                     f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
             seen[key] = key_node.start_mark.line
-    return super().construct_mapping(node, deep=deep)
+    return super().construct_mapping(node, deep=None)
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_33`: survived (accepted, equivalent: equivalent: construction depth; keys are scalars and the constructed mapping is the same); diff fingerprint `845eb5235c2026fa`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_33: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -14,4 +14,4 @@
                     "while reading a mapping", node.start_mark,
                     f"duplicate key {key!r} (first defined on line {first + 1})", key_node.start_mark)
             seen[key] = key_node.start_mark.line
-    return super().construct_mapping(node, deep=deep)
+    return super().construct_mapping(node, )
```

`netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_9`: survived (accepted, equivalent: equivalent: construction depth; keys are scalars and the constructed mapping is the same); diff fingerprint `fb6d428b7177ce17`

```diff
# netdryrun.config.xǁ_StrictLoaderǁconstruct_mapping__mutmut_9: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,7 +4,7 @@
         for key_node, _ in node.value:
             if key_node.tag == "tag:yaml.org,2002:merge":
                 continue   # `<<: *anchor` merges are allowed, and explicit keys override them
-            key = self.construct_object(key_node, deep=True)
+            key = self.construct_object(key_node, deep=None)
             try:
                 first = seen.get(key)
             except TypeError:
```

## `drivers.eos._vrf` (12)

`netdryrun.drivers.eos.x__vrf__mutmut_12`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `f9f70159b8385cac`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_12: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -7,7 +7,7 @@
         raise unexpected(command, data)
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
-                          f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
+                          f"{', '.join(sorted(map(str, vrfs))) and 'none'}): it does not exist, or this "
                           "command has nothing configured in it")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
```

`netdryrun.drivers.eos.x__vrf__mutmut_14`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `3760c7fad85e833c`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_14: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -7,7 +7,7 @@
         raise unexpected(command, data)
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
-                          f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
+                          f"{'XX, XX'.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
                           "command has nothing configured in it")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
```

`netdryrun.drivers.eos.x__vrf__mutmut_20`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `fe214041462dd117`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_20: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -7,7 +7,7 @@
         raise unexpected(command, data)
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
-                          f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
+                          f"{', '.join(sorted(map(str, vrfs))) or 'XXnoneXX'}): it does not exist, or this "
                           "command has nothing configured in it")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
```

`netdryrun.drivers.eos.x__vrf__mutmut_21`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `627c74d0799cb825`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_21: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -7,7 +7,7 @@
         raise unexpected(command, data)
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
-                          f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
+                          f"{', '.join(sorted(map(str, vrfs))) or 'NONE'}): it does not exist, or this "
                           "command has nothing configured in it")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
```

`netdryrun.drivers.eos.x__vrf__mutmut_22`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `3969df2c5e2a4cce`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_22: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -8,7 +8,7 @@
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
                           f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
-                          "command has nothing configured in it")
+                          "XXcommand has nothing configured in itXX")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
         raise unexpected(command, f"vrf {vrf}: {str(entry)[:150]}")
```

`netdryrun.drivers.eos.x__vrf__mutmut_23`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `b6b4f59f02181930`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_23: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -8,7 +8,7 @@
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
                           f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
-                          "command has nothing configured in it")
+                          "COMMAND HAS NOTHING CONFIGURED IN IT")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
         raise unexpected(command, f"vrf {vrf}: {str(entry)[:150]}")
```

`netdryrun.drivers.eos.x__vrf__mutmut_26`: survived (accepted, message-text: message text only: the text of the unexpected-output DriverError raised either way); diff fingerprint `1574dfe3e983632f`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_26: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -11,5 +11,5 @@
                           "command has nothing configured in it")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
-        raise unexpected(command, f"vrf {vrf}: {str(entry)[:150]}")
+        raise unexpected(None, f"vrf {vrf}: {str(entry)[:150]}")
     return entry
```

`netdryrun.drivers.eos.x__vrf__mutmut_27`: survived (accepted, message-text: message text only: the text of the unexpected-output DriverError raised either way); diff fingerprint `0fd34b2a5fd921a1`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_27: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -11,5 +11,5 @@
                           "command has nothing configured in it")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
-        raise unexpected(command, f"vrf {vrf}: {str(entry)[:150]}")
+        raise unexpected(command, None)
     return entry
```

`netdryrun.drivers.eos.x__vrf__mutmut_30`: survived (accepted, message-text: message text only: the text of the unexpected-output DriverError raised either way); diff fingerprint `36c0d1736deed8e9`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_30: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -11,5 +11,5 @@
                           "command has nothing configured in it")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
-        raise unexpected(command, f"vrf {vrf}: {str(entry)[:150]}")
+        raise unexpected(command, f"vrf {vrf}: {str(None)[:150]}")
     return entry
```

`netdryrun.drivers.eos.x__vrf__mutmut_31`: survived (accepted, message-text: message text only: the text of the unexpected-output DriverError raised either way); diff fingerprint `5b75b1b56fb4dcbd`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_31: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -11,5 +11,5 @@
                           "command has nothing configured in it")
     entry = vrfs[vrf]
     if not isinstance(entry, dict):
-        raise unexpected(command, f"vrf {vrf}: {str(entry)[:150]}")
+        raise unexpected(command, f"vrf {vrf}: {str(entry)[:151]}")
     return entry
```

`netdryrun.drivers.eos.x__vrf__mutmut_6`: survived (accepted, message-text: message text only: the text of the unexpected-output DriverError raised either way); diff fingerprint `e2a7beea3a5abc6b`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_6: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -4,7 +4,7 @@
     can't be told apart from output this driver doesn't know, so it raises: never "no routes"."""
     vrfs = data.get("vrfs")
     if not isinstance(vrfs, dict):
-        raise unexpected(command, data)
+        raise unexpected(None, data)
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
                           f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
```

`netdryrun.drivers.eos.x__vrf__mutmut_7`: survived (accepted, message-text: message text only: the text of the unexpected-output DriverError raised either way); diff fingerprint `5bfc5879a0adab73`

```diff
# netdryrun.drivers.eos.x__vrf__mutmut_7: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -4,7 +4,7 @@
     can't be told apart from output this driver doesn't know, so it raises: never "no routes"."""
     vrfs = data.get("vrfs")
     if not isinstance(vrfs, dict):
-        raise unexpected(command, data)
+        raise unexpected(command, None)
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} is not in the output of `{command}` (VRFs listed: "
                           f"{', '.join(sorted(map(str, vrfs))) or 'none'}): it does not exist, or this "
```

## `runner.run_scenario` (12)

`netdryrun.runner.x_run_scenario__mutmut_105`: survived (accepted, equivalent: equivalent: results is still empty here, so binding it to pos_results equals extending it (same items returned)); argument: Same behaviour on every input the function can receive: results is still empty here, so binding it to pos_results equals extending it (same items returned). So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `25894bc7a1ed8027`

```diff
# netdryrun.runner.x_run_scenario__mutmut_105: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -44,7 +44,7 @@
         positives = [c for c in sc.checks if not is_post_convergence(c)]
         negatives = [c for c in sc.checks if is_post_convergence(c)]
         pos_results = _reach_then_hold(positives, drivers, hold, on_result=on_result)
-        results += pos_results
+        results = pos_results
         if negatives:
             # The same BGP gate as at the top level: every session on the node up (except those the fault
             # took down and those a check expects down), with stable prefix counts. For inject_routes, this
```

`netdryrun.runner.x_run_scenario__mutmut_120`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `dc9fb2f7e81bb3fd`

```diff
# netdryrun.runner.x_run_scenario__mutmut_120: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -53,8 +53,7 @@
             for c in negatives:
                 driver_for(c.node)
             gate_warnings: dict[int, str] = {}
-            blocked = _bgp_convergence_gate(negatives, list(baseline_checks) + sc.checks, drivers, log=log,
-                                            positive_results=pos_results, warnings=gate_warnings,
+            blocked = _bgp_convergence_gate(negatives, list(baseline_checks) + sc.checks, drivers, positive_results=pos_results, warnings=gate_warnings,
                                             expected_down=over_links)
             ready = [c for c in negatives if id(c) not in blocked]
             neg_results = hold_together(ready, drivers, hold=hold, on_result=_with_warnings(gate_warnings, on_result),
```

`netdryrun.runner.x_run_scenario__mutmut_169`: survived (accepted, message-text: message text only: the text of the 'could not restore' LabError raised either way (exit 2)); argument: Changes only text: the text of the 'could not restore' LabError raised either way (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `0d93d4e129f3aacc`

```diff
# netdryrun.runner.x_run_scenario__mutmut_169: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -76,7 +76,7 @@
             try:
                 inj.restore()
             except LabError as e:
-                not_restored.append(str(e))
+                not_restored.append(str(None))
         if not_restored:
             # A link left down or a route left injected would corrupt every later result: stop the run instead
             raise LabError("could not restore after scenario: " + "; ".join(not_restored))
```

`netdryrun.runner.x_run_scenario__mutmut_170`: survived (accepted, message-text: message text only: the text of the 'could not restore' LabError raised either way (exit 2)); argument: Changes only text: the text of the 'could not restore' LabError raised either way (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `2221a63e67d25759`

```diff
# netdryrun.runner.x_run_scenario__mutmut_170: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -79,7 +79,7 @@
                 not_restored.append(str(e))
         if not_restored:
             # A link left down or a route left injected would corrupt every later result: stop the run instead
-            raise LabError("could not restore after scenario: " + "; ".join(not_restored))
+            raise LabError(None)
         applied = sum(inj.applied for inj in injected)
         if downed or applied:
             log(f"Restored {len(downed)} link(s) and {applied} route injection(s); settling {settle:g}s")
```

`netdryrun.runner.x_run_scenario__mutmut_172`: survived (accepted, message-text: message text only: the text of the 'could not restore' LabError raised either way (exit 2)); argument: Changes only text: the text of the 'could not restore' LabError raised either way (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `3a90bc2fb9562e39`

```diff
# netdryrun.runner.x_run_scenario__mutmut_172: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -79,7 +79,7 @@
                 not_restored.append(str(e))
         if not_restored:
             # A link left down or a route left injected would corrupt every later result: stop the run instead
-            raise LabError("could not restore after scenario: " + "; ".join(not_restored))
+            raise LabError("XXcould not restore after scenario: XX" + "; ".join(not_restored))
         applied = sum(inj.applied for inj in injected)
         if downed or applied:
             log(f"Restored {len(downed)} link(s) and {applied} route injection(s); settling {settle:g}s")
```

`netdryrun.runner.x_run_scenario__mutmut_173`: survived (accepted, message-text: message text only: the text of the 'could not restore' LabError raised either way (exit 2)); argument: Changes only text: the text of the 'could not restore' LabError raised either way (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `234da78da8ed3f52`

```diff
# netdryrun.runner.x_run_scenario__mutmut_173: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -79,7 +79,7 @@
                 not_restored.append(str(e))
         if not_restored:
             # A link left down or a route left injected would corrupt every later result: stop the run instead
-            raise LabError("could not restore after scenario: " + "; ".join(not_restored))
+            raise LabError("COULD NOT RESTORE AFTER SCENARIO: " + "; ".join(not_restored))
         applied = sum(inj.applied for inj in injected)
         if downed or applied:
             log(f"Restored {len(downed)} link(s) and {applied} route injection(s); settling {settle:g}s")
```

`netdryrun.runner.x_run_scenario__mutmut_175`: survived (accepted, message-text: message text only: the text of the 'could not restore' LabError raised either way (exit 2)); argument: Changes only text: the text of the 'could not restore' LabError raised either way (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `7076bbe99146c26b`

```diff
# netdryrun.runner.x_run_scenario__mutmut_175: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -79,7 +79,7 @@
                 not_restored.append(str(e))
         if not_restored:
             # A link left down or a route left injected would corrupt every later result: stop the run instead
-            raise LabError("could not restore after scenario: " + "; ".join(not_restored))
+            raise LabError("could not restore after scenario: " + "XX; XX".join(not_restored))
         applied = sum(inj.applied for inj in injected)
         if downed or applied:
             log(f"Restored {len(downed)} link(s) and {applied} route injection(s); settling {settle:g}s")
```

`netdryrun.runner.x_run_scenario__mutmut_179`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `cdf0fcd7346b7863`

```diff
# netdryrun.runner.x_run_scenario__mutmut_179: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -82,6 +82,6 @@
             raise LabError("could not restore after scenario: " + "; ".join(not_restored))
         applied = sum(inj.applied for inj in injected)
         if downed or applied:
-            log(f"Restored {len(downed)} link(s) and {applied} route injection(s); settling {settle:g}s")
+            log(None)
             _sleep(settle)
     return results
```

`netdryrun.runner.x_run_scenario__mutmut_42`: survived (accepted, equivalent: equivalent: with no links, _link_sessions reads nothing and returns two empty lists, the else value); argument: Same behaviour on every input the function can receive: with no links, _link_sessions reads nothing and returns two empty lists, the else value. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `ba873bc762444035`

```diff
# netdryrun.runner.x_run_scenario__mutmut_42: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -24,7 +24,7 @@
     # watch: the established sessions over the downed links, which must go down (the fault took effect).
     # over_links: every session over them, established or not, expected down while the fault lasts: the
     # BGP gate for the scenario's post-convergence checks doesn't wait for those.
-    watch, over = _link_sessions(lab, links, vrfs, driver_for, log=log) if links else ([], [])
+    watch, over = _link_sessions(lab, links, vrfs, driver_for, log=log) if (links) or True else ([], [])
     over_links = set(over)
     try:
         for f, ifaces in plan:
```

`netdryrun.runner.x_run_scenario__mutmut_52`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `732388f8f58201a1`

```diff
# netdryrun.runner.x_run_scenario__mutmut_52: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -24,7 +24,7 @@
     # watch: the established sessions over the downed links, which must go down (the fault took effect).
     # over_links: every session over them, established or not, expected down while the fault lasts: the
     # BGP gate for the scenario's post-convergence checks doesn't wait for those.
-    watch, over = _link_sessions(lab, links, vrfs, driver_for, log=log) if links else ([], [])
+    watch, over = _link_sessions(lab, links, vrfs, driver_for, ) if links else ([], [])
     over_links = set(over)
     try:
         for f, ifaces in plan:
```

`netdryrun.runner.x_run_scenario__mutmut_68`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `ec1ab554c6f6bc14`

```diff
# netdryrun.runner.x_run_scenario__mutmut_68: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -31,7 +31,7 @@
             if f.kind == "inject_routes":
                 inj = RouteInjection(lab, f.node, f.prefixes, f.as_path)
                 injected.append(inj)   # recorded first: restore even if applying half-fails
-                log(f"Injecting {inj.describe()}")
+                log(None)
                 inj.apply()
                 continue
             for iface in ifaces:
```

`netdryrun.runner.x_run_scenario__mutmut_89`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `2bb1fbbbf917afc3`

```diff
# netdryrun.runner.x_run_scenario__mutmut_89: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -39,7 +39,7 @@
                 lab.set_link(f.node, iface, up=False)
         if links:
             _wait_fault_visible(watch, driver_for, max(c.timeout for c in sc.checks), sc, log=log)
-        log(f"  settling {settle:g}s before the scenario's checks")
+        log(None)
         _sleep(settle)
         positives = [c for c in sc.checks if not is_post_convergence(c)]
         negatives = [c for c in sc.checks if is_post_convergence(c)]
```

## `checks._describe_path` (11)

`netdryrun.checks.x__describe_path__mutmut_10`: survived (accepted, message-text: message text only: the description of a best path inside a detail); diff fingerprint `ea26769c5b005a6d`

```diff
# netdryrun.checks.x__describe_path__mutmut_10: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
     comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
-    as_path = "?" if path.as_path is None else f"'{path.as_path}'"
+    as_path = "?" if (path.as_path is None) or True else f"'{path.as_path}'"
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_11`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `716e1462b3c031d7`

```diff
# netdryrun.checks.x__describe_path__mutmut_11: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
     comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
-    as_path = "?" if path.as_path is None else f"'{path.as_path}'"
+    as_path = "XX?XX" if path.as_path is None else f"'{path.as_path}'"
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_12`: survived (accepted, message-text: message text only: the description of a best path inside a detail); diff fingerprint `2b3d8d002b6e85c1`

```diff
# netdryrun.checks.x__describe_path__mutmut_12: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
     comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
-    as_path = "?" if path.as_path is None else f"'{path.as_path}'"
+    as_path = "?" if path.as_path is not None else f"'{path.as_path}'"
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_13`: survived (accepted, message-text: message text only: the description of a best path inside a detail); diff fingerprint `1e41c3ebef974075`

```diff
# netdryrun.checks.x__describe_path__mutmut_13: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
     comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
     as_path = "?" if path.as_path is None else f"'{path.as_path}'"
-    return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
+    return (f"as-path {as_path}, next hop {path.next_hop and '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_14`: survived (accepted, message-text: message text only: the description of a best path inside a detail); diff fingerprint `af657a895342f594`

```diff
# netdryrun.checks.x__describe_path__mutmut_14: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
     comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
     as_path = "?" if path.as_path is None else f"'{path.as_path}'"
-    return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
+    return (f"as-path {as_path}, next hop {path.next_hop or 'XX?XX'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_16`: survived (accepted, message-text: message text only: part of an error or detail message string); diff fingerprint `c0bd37018c96e390`

```diff
# netdryrun.checks.x__describe_path__mutmut_16: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -2,4 +2,4 @@
     comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
     as_path = "?" if path.as_path is None else f"'{path.as_path}'"
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
-            f"MED {_opt(path.med)}, communities {comms}")
+            f"MED {_opt(None)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_4`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `567edc5041362507`

```diff
# netdryrun.checks.x__describe_path__mutmut_4: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
-    comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
+    comms = "XX XX".join(community_name(c) for c in path.all_communities()) or "none"
     as_path = "?" if path.as_path is None else f"'{path.as_path}'"
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_6`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `dec152bd7d240c71`

```diff
# netdryrun.checks.x__describe_path__mutmut_6: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
-    comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
+    comms = " ".join(community_name(c) for c in path.all_communities()) or "XXnoneXX"
     as_path = "?" if path.as_path is None else f"'{path.as_path}'"
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_7`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `2c70cbb203a08daf`

```diff
# netdryrun.checks.x__describe_path__mutmut_7: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
-    comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
+    comms = " ".join(community_name(c) for c in path.all_communities()) or "NONE"
     as_path = "?" if path.as_path is None else f"'{path.as_path}'"
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_8`: survived (accepted, message-text: message text only: the description of a best path inside a detail); diff fingerprint `a62c118fc04e6f18`

```diff
# netdryrun.checks.x__describe_path__mutmut_8: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
     comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
-    as_path = "?" if path.as_path is None else f"'{path.as_path}'"
+    as_path = None
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

`netdryrun.checks.x__describe_path__mutmut_9`: survived (accepted, message-text: message text only: the description of a best path inside a detail); diff fingerprint `a28fe64593a65fc7`

```diff
# netdryrun.checks.x__describe_path__mutmut_9: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,5 +1,5 @@
 def _describe_path(path) -> str:
     comms = " ".join(community_name(c) for c in path.all_communities()) or "none"
-    as_path = "?" if path.as_path is None else f"'{path.as_path}'"
+    as_path = "?" if (path.as_path is None) and False else f"'{path.as_path}'"
     return (f"as-path {as_path}, next hop {path.next_hop or '?'}, local-pref {_opt(path.local_pref)}, "
             f"MED {_opt(path.med)}, communities {comms}")
```

## `config._validate_bgp_route` (11)

`netdryrun.config.x__validate_bgp_route__mutmut_15`: survived (accepted, message-text: message text only: part of an error or detail message string); diff fingerprint `6d87bff12aebf777`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_15: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -2,7 +2,7 @@
     attrs = [k for k in BGP_ATTRIBUTES if k in params]
     if params.get("present", True) is False and attrs:
         raise ConfigError(f"{where}: present: false means no BGP path at all, so it can't be combined with "
-                          f"{', '.join(attrs)}; to forbid a community on the best path use without_communities")
+                          f"{'XX, XX'.join(attrs)}; to forbid a community on the best path use without_communities")
     for key in ("communities", "without_communities"):
         if key not in params:
             continue
```

`netdryrun.config.x__validate_bgp_route__mutmut_30`: survived (accepted, message-text: message text only: part of an error or detail message string); diff fingerprint `9193acf479f37024`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_30: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -13,7 +13,7 @@
             if isinstance(c, (int, float)) and not isinstance(c, bool):
                 # YAML 1.1 reads 65000:10 (and 65000:1:2) unquoted as a base-60 number
                 raise ConfigError(f"{where}: {key}: write communities as quoted strings, for example '65000:10'; "
-                                  "YAML reads some unquoted values like 65000:10 as numbers")
+                                  "XXYAML reads some unquoted values like 65000:10 as numbersXX")
             if not isinstance(c, str):
                 raise ConfigError(f"{where}: {key}: bad community {c!r}: write it as a quoted string")
         try:
```

`netdryrun.config.x__validate_bgp_route__mutmut_31`: survived (accepted, message-text: message text only: part of an error or detail message string); diff fingerprint `9ec7b51478983f22`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_31: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -13,7 +13,7 @@
             if isinstance(c, (int, float)) and not isinstance(c, bool):
                 # YAML 1.1 reads 65000:10 (and 65000:1:2) unquoted as a base-60 number
                 raise ConfigError(f"{where}: {key}: write communities as quoted strings, for example '65000:10'; "
-                                  "YAML reads some unquoted values like 65000:10 as numbers")
+                                  "yaml reads some unquoted values like 65000:10 as numbers")
             if not isinstance(c, str):
                 raise ConfigError(f"{where}: {key}: bad community {c!r}: write it as a quoted string")
         try:
```

`netdryrun.config.x__validate_bgp_route__mutmut_32`: survived (accepted, message-text: message text only: part of an error or detail message string); diff fingerprint `fb648a02f3a77cf5`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_32: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -13,7 +13,7 @@
             if isinstance(c, (int, float)) and not isinstance(c, bool):
                 # YAML 1.1 reads 65000:10 (and 65000:1:2) unquoted as a base-60 number
                 raise ConfigError(f"{where}: {key}: write communities as quoted strings, for example '65000:10'; "
-                                  "YAML reads some unquoted values like 65000:10 as numbers")
+                                  "YAML READS SOME UNQUOTED VALUES LIKE 65000:10 AS NUMBERS")
             if not isinstance(c, str):
                 raise ConfigError(f"{where}: {key}: bad community {c!r}: write it as a quoted string")
         try:
```

`netdryrun.config.x__validate_bgp_route__mutmut_34`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `d10805aa9c27987f`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_34: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -15,7 +15,7 @@
                 raise ConfigError(f"{where}: {key}: write communities as quoted strings, for example '65000:10'; "
                                   "YAML reads some unquoted values like 65000:10 as numbers")
             if not isinstance(c, str):
-                raise ConfigError(f"{where}: {key}: bad community {c!r}: write it as a quoted string")
+                raise ConfigError(None)
         try:
             params[key] = [parse_community(c) for c in raw]
         except ValueError as e:
```

`netdryrun.config.x__validate_bgp_route__mutmut_5`: survived (accepted, equivalent: equivalent: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'); diff fingerprint `7952f89a8dde1f6d`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_5: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _validate_bgp_route(where: str, params: dict[str, Any]) -> None:
     attrs = [k for k in BGP_ATTRIBUTES if k in params]
-    if params.get("present", True) is False and attrs:
+    if params.get("present", None) is False and attrs:
         raise ConfigError(f"{where}: present: false means no BGP path at all, so it can't be combined with "
                           f"{', '.join(attrs)}; to forbid a community on the best path use without_communities")
     for key in ("communities", "without_communities"):
```

`netdryrun.config.x__validate_bgp_route__mutmut_56`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `1fefe78eea0e4342`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_56: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -22,7 +22,7 @@
             raise ConfigError(f"{where}: {key}: {e}") from None
     both = set(params.get("communities", [])) & set(params.get("without_communities", []))
     if both:
-        raise ConfigError(f"{where}: {', '.join(sorted(both))} is in both communities and without_communities")
+        raise ConfigError(f"{where}: {'XX, XX'.join(sorted(both))} is in both communities and without_communities")
     if "as_path" in params:
         v = params["as_path"]
         if v is None or isinstance(v, (float, dict)) or (isinstance(v, list) and not v):
```

`netdryrun.config.x__validate_bgp_route__mutmut_65`: survived (accepted, equivalent: equivalent: a None, float or dict as_path is still refused, by normalize_as_path, as a ConfigError); diff fingerprint `1f49b2ce2eba3708`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_65: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -25,7 +25,7 @@
         raise ConfigError(f"{where}: {', '.join(sorted(both))} is in both communities and without_communities")
     if "as_path" in params:
         v = params["as_path"]
-        if v is None or isinstance(v, (float, dict)) or (isinstance(v, list) and not v):
+        if v is None and isinstance(v, (float, dict)) or (isinstance(v, list) and not v):
             raise ConfigError(f"{where}: as_path must be a string such as '65002 65003' (\"\" for the empty path), "
                               f"got {v!r}")
         try:
```

`netdryrun.config.x__validate_bgp_route__mutmut_69`: survived (accepted, message-text: message text only: the same ConfigError is raised, only its message changes); diff fingerprint `b65f7c548b278c33`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_69: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -26,8 +26,7 @@
     if "as_path" in params:
         v = params["as_path"]
         if v is None or isinstance(v, (float, dict)) or (isinstance(v, list) and not v):
-            raise ConfigError(f"{where}: as_path must be a string such as '65002 65003' (\"\" for the empty path), "
-                              f"got {v!r}")
+            raise ConfigError(None)
         try:
             params["as_path"] = normalize_as_path(v)
         except ValueError as e:
```

`netdryrun.config.x__validate_bgp_route__mutmut_7`: survived (accepted, equivalent: equivalent: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'); diff fingerprint `64bb0f9b0b255d23`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_7: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,6 +1,6 @@
 def _validate_bgp_route(where: str, params: dict[str, Any]) -> None:
     attrs = [k for k in BGP_ATTRIBUTES if k in params]
-    if params.get("present", True) is False and attrs:
+    if params.get("present", ) is False and attrs:
         raise ConfigError(f"{where}: present: false means no BGP path at all, so it can't be combined with "
                           f"{', '.join(attrs)}; to forbid a community on the best path use without_communities")
     for key in ("communities", "without_communities"):
```

`netdryrun.config.x__validate_bgp_route__mutmut_84`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `30fafc57c8754032`

```diff
# netdryrun.config.x__validate_bgp_route__mutmut_84: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -35,7 +35,7 @@
     if "as_path_regex" in params:
         v = params["as_path_regex"]
         if not isinstance(v, str) or not v:
-            raise ConfigError(f"{where}: as_path_regex must be a non-empty regular expression string, got {v!r}")
+            raise ConfigError(None)
         try:
             re.compile(v)
         except re.error as e:
```

## `runner._wait_fault_visible` (11)

`netdryrun.runner.x__wait_fault_visible__mutmut_2`: survived (accepted, logging: message text only: a progress or warning line in the log); argument: Changes only a line passed to log(): a progress or warning line in the log. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `89e6d4dd029c9fdb`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_2: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,7 +1,7 @@
 def _wait_fault_visible(watch: list[tuple[str, str, str]], driver_for, timeout: float, sc: Scenario,
                         log=lambda _: None) -> None:
     if not watch:
-        log("  no BGP session runs over the downed links; relying on the settle and hold windows")
+        log(None)
         return
     t0 = _clock()
     while True:
```

`netdryrun.runner.x__wait_fault_visible__mutmut_3`: survived (accepted, logging: message text only: a progress or warning line in the log); argument: Changes only a line passed to log(): a progress or warning line in the log. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `7d2cccde42e2ed2e`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_3: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,7 +1,7 @@
 def _wait_fault_visible(watch: list[tuple[str, str, str]], driver_for, timeout: float, sc: Scenario,
                         log=lambda _: None) -> None:
     if not watch:
-        log("  no BGP session runs over the downed links; relying on the settle and hold windows")
+        log("XX  no BGP session runs over the downed links; relying on the settle and hold windowsXX")
         return
     t0 = _clock()
     while True:
```

`netdryrun.runner.x__wait_fault_visible__mutmut_36`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `93f8bb3615235f0a`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_36: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
         if elapsed >= timeout:
             raise LabError(
                 f"scenario '{sc.name}': the fault did not take effect within {timeout:g}s: BGP session(s) over the "
-                f"downed links still established ({', '.join(still[:5])}). Netdryrun won't judge the scenario's "
+                f"downed links still established ({'XX, XX'.join(still[:5])}). Netdryrun won't judge the scenario's "
                 "checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) "
                 "to notice a failure: raise the checks' timeout, or lower the hold timers in the lab")
         _sleep(max(0.0, min(POLL, timeout - elapsed)))
```

`netdryrun.runner.x__wait_fault_visible__mutmut_37`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `d21813766bb3b115`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_37: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
         if elapsed >= timeout:
             raise LabError(
                 f"scenario '{sc.name}': the fault did not take effect within {timeout:g}s: BGP session(s) over the "
-                f"downed links still established ({', '.join(still[:5])}). Netdryrun won't judge the scenario's "
+                f"downed links still established ({', '.join(still[:6])}). Netdryrun won't judge the scenario's "
                 "checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) "
                 "to notice a failure: raise the checks' timeout, or lower the hold timers in the lab")
         _sleep(max(0.0, min(POLL, timeout - elapsed)))
```

`netdryrun.runner.x__wait_fault_visible__mutmut_38`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `3e64dc476f4b537d`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_38: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -24,6 +24,6 @@
             raise LabError(
                 f"scenario '{sc.name}': the fault did not take effect within {timeout:g}s: BGP session(s) over the "
                 f"downed links still established ({', '.join(still[:5])}). Netdryrun won't judge the scenario's "
-                "checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) "
+                "XXchecks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) XX"
                 "to notice a failure: raise the checks' timeout, or lower the hold timers in the lab")
         _sleep(max(0.0, min(POLL, timeout - elapsed)))
```

`netdryrun.runner.x__wait_fault_visible__mutmut_39`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `f5d1b3cb56f2b685`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_39: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -24,6 +24,6 @@
             raise LabError(
                 f"scenario '{sc.name}': the fault did not take effect within {timeout:g}s: BGP session(s) over the "
                 f"downed links still established ({', '.join(still[:5])}). Netdryrun won't judge the scenario's "
-                "checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) "
+                "checks on the state from before the fault. without bfd, bgp can take its hold time (up to 180 s) "
                 "to notice a failure: raise the checks' timeout, or lower the hold timers in the lab")
         _sleep(max(0.0, min(POLL, timeout - elapsed)))
```

`netdryrun.runner.x__wait_fault_visible__mutmut_4`: survived (accepted, logging: message text only: a progress or warning line in the log); argument: Changes only a line passed to log(): a progress or warning line in the log. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `14325e51db353bfc`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_4: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,7 +1,7 @@
 def _wait_fault_visible(watch: list[tuple[str, str, str]], driver_for, timeout: float, sc: Scenario,
                         log=lambda _: None) -> None:
     if not watch:
-        log("  no BGP session runs over the downed links; relying on the settle and hold windows")
+        log("  no bgp session runs over the downed links; relying on the settle and hold windows")
         return
     t0 = _clock()
     while True:
```

`netdryrun.runner.x__wait_fault_visible__mutmut_40`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `2f7b1a2c38a4ac63`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_40: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -24,6 +24,6 @@
             raise LabError(
                 f"scenario '{sc.name}': the fault did not take effect within {timeout:g}s: BGP session(s) over the "
                 f"downed links still established ({', '.join(still[:5])}). Netdryrun won't judge the scenario's "
-                "checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) "
+                "CHECKS ON THE STATE FROM BEFORE THE FAULT. WITHOUT BFD, BGP CAN TAKE ITS HOLD TIME (UP TO 180 S) "
                 "to notice a failure: raise the checks' timeout, or lower the hold timers in the lab")
         _sleep(max(0.0, min(POLL, timeout - elapsed)))
```

`netdryrun.runner.x__wait_fault_visible__mutmut_41`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `5076599b0b4039d4`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_41: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -25,5 +25,5 @@
                 f"scenario '{sc.name}': the fault did not take effect within {timeout:g}s: BGP session(s) over the "
                 f"downed links still established ({', '.join(still[:5])}). Netdryrun won't judge the scenario's "
                 "checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) "
-                "to notice a failure: raise the checks' timeout, or lower the hold timers in the lab")
+                "XXto notice a failure: raise the checks' timeout, or lower the hold timers in the labXX")
         _sleep(max(0.0, min(POLL, timeout - elapsed)))
```

`netdryrun.runner.x__wait_fault_visible__mutmut_42`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `3883985d8ebd4377`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_42: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -25,5 +25,5 @@
                 f"scenario '{sc.name}': the fault did not take effect within {timeout:g}s: BGP session(s) over the "
                 f"downed links still established ({', '.join(still[:5])}). Netdryrun won't judge the scenario's "
                 "checks on the state from before the fault. Without BFD, BGP can take its hold time (up to 180 s) "
-                "to notice a failure: raise the checks' timeout, or lower the hold timers in the lab")
+                "TO NOTICE A FAILURE: RAISE THE CHECKS' TIMEOUT, OR LOWER THE HOLD TIMERS IN THE LAB")
         _sleep(max(0.0, min(POLL, timeout - elapsed)))
```

`netdryrun.runner.x__wait_fault_visible__mutmut_5`: survived (accepted, logging: message text only: a progress or warning line in the log); argument: Changes only a line passed to log(): a progress or warning line in the log. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `cabc405acc9518db`

```diff
# netdryrun.runner.x__wait_fault_visible__mutmut_5: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,7 +1,7 @@
 def _wait_fault_visible(watch: list[tuple[str, str, str]], driver_for, timeout: float, sc: Scenario,
                         log=lambda _: None) -> None:
     if not watch:
-        log("  no BGP session runs over the downed links; relying on the settle and hold windows")
+        log("  NO BGP SESSION RUNS OVER THE DOWNED LINKS; RELYING ON THE SETTLE AND HOLD WINDOWS")
         return
     t0 = _clock()
     while True:
```

## `drivers.srlinux._rib_rows` (10)

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_11`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `595f0d4568550fab`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_11: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,6 +1,6 @@
 def _rib_rows(text: str, prefix: str) -> list[dict]:
     want = ipaddress.ip_network(prefix)
-    rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
+    rows = _list(RIB_CMD, _json(text, None), "route")
     for r in rows:
         if "prefix" not in r:
             raise unexpected(RIB_CMD, str(r)[:150])
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_13`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `4b1143b213bc504f`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_13: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,6 +1,6 @@
 def _rib_rows(text: str, prefix: str) -> list[dict]:
     want = ipaddress.ip_network(prefix)
-    rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
+    rows = _list(RIB_CMD, _json(text, ), "route")
     for r in rows:
         if "prefix" not in r:
             raise unexpected(RIB_CMD, str(r)[:150])
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_19`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `6a6193c731c35825`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_19: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -3,5 +3,5 @@
     rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
     for r in rows:
         if "prefix" not in r:
-            raise unexpected(RIB_CMD, str(r)[:150])
+            raise unexpected(None, str(r)[:150])
     return [r for r in rows if network(RIB_CMD, r["prefix"]) == want]
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_20`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `bcc9d04ace2bd0d6`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_20: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -3,5 +3,5 @@
     rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
     for r in rows:
         if "prefix" not in r:
-            raise unexpected(RIB_CMD, str(r)[:150])
+            raise unexpected(RIB_CMD, None)
     return [r for r in rows if network(RIB_CMD, r["prefix"]) == want]
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_21`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `d951ce431bac664f`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_21: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -3,5 +3,5 @@
     rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
     for r in rows:
         if "prefix" not in r:
-            raise unexpected(RIB_CMD, str(r)[:150])
+            raise unexpected(str(r)[:150])
     return [r for r in rows if network(RIB_CMD, r["prefix"]) == want]
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_22`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `4c146b75903c56a6`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_22: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -3,5 +3,5 @@
     rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
     for r in rows:
         if "prefix" not in r:
-            raise unexpected(RIB_CMD, str(r)[:150])
+            raise unexpected(RIB_CMD, )
     return [r for r in rows if network(RIB_CMD, r["prefix"]) == want]
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_23`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `0d3414006c4babf0`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_23: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -3,5 +3,5 @@
     rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
     for r in rows:
         if "prefix" not in r:
-            raise unexpected(RIB_CMD, str(r)[:150])
+            raise unexpected(RIB_CMD, str(None)[:150])
     return [r for r in rows if network(RIB_CMD, r["prefix"]) == want]
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_24`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `9d8b87afbf113535`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_24: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -3,5 +3,5 @@
     rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
     for r in rows:
         if "prefix" not in r:
-            raise unexpected(RIB_CMD, str(r)[:150])
+            raise unexpected(RIB_CMD, str(r)[:151])
     return [r for r in rows if network(RIB_CMD, r["prefix"]) == want]
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_25`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `4e13c8d4a06b79e1`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_25: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -4,4 +4,4 @@
     for r in rows:
         if "prefix" not in r:
             raise unexpected(RIB_CMD, str(r)[:150])
-    return [r for r in rows if network(RIB_CMD, r["prefix"]) == want]
+    return [r for r in rows if network(None, r["prefix"]) == want]
```

`netdryrun.drivers.srlinux.x__rib_rows__mutmut_4`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `6c4598e111047857`

```diff
# netdryrun.drivers.srlinux.x__rib_rows__mutmut_4: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,6 +1,6 @@
 def _rib_rows(text: str, prefix: str) -> list[dict]:
     want = ipaddress.ip_network(prefix)
-    rows = _list(RIB_CMD, _json(text, RIB_CMD), "route")
+    rows = _list(None, _json(text, RIB_CMD), "route")
     for r in rows:
         if "prefix" not in r:
             raise unexpected(RIB_CMD, str(r)[:150])
```

## `runner._link_sessions` (10)

`netdryrun.runner.x__link_sessions__mutmut_12`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `79f316540513a610`

```diff
# netdryrun.runner.x__link_sessions__mutmut_12: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
             except NoSuchInstance:
                 states[(node, vrf)] = {}   # the node has no such VRF or BGP instance: nothing to observe
             except Exception as e:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = None
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
                                "when the fault took effect") from None
```

`netdryrun.runner.x__link_sessions__mutmut_13`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `d588be6f0db5609a`

```diff
# netdryrun.runner.x__link_sessions__mutmut_13: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
             except NoSuchInstance:
                 states[(node, vrf)] = {}   # the node has no such VRF or BGP instance: nothing to observe
             except Exception as e:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if (vrf == "default") and False else f" (vrf {vrf})"
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
                                "when the fault took effect") from None
```

`netdryrun.runner.x__link_sessions__mutmut_14`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `3acbb02b2f9b4ca6`

```diff
# netdryrun.runner.x__link_sessions__mutmut_14: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
             except NoSuchInstance:
                 states[(node, vrf)] = {}   # the node has no such VRF or BGP instance: nothing to observe
             except Exception as e:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if (vrf == "default") or True else f" (vrf {vrf})"
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
                                "when the fault took effect") from None
```

`netdryrun.runner.x__link_sessions__mutmut_15`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `791244faeeab8dc0`

```diff
# netdryrun.runner.x__link_sessions__mutmut_15: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
             except NoSuchInstance:
                 states[(node, vrf)] = {}   # the node has no such VRF or BGP instance: nothing to observe
             except Exception as e:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "XXXX" if vrf == "default" else f" (vrf {vrf})"
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
                                "when the fault took effect") from None
```

`netdryrun.runner.x__link_sessions__mutmut_16`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `50ee31b34cc8a66e`

```diff
# netdryrun.runner.x__link_sessions__mutmut_16: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
             except NoSuchInstance:
                 states[(node, vrf)] = {}   # the node has no such VRF or BGP instance: nothing to observe
             except Exception as e:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf != "default" else f" (vrf {vrf})"
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
                                "when the fault took effect") from None
```

`netdryrun.runner.x__link_sessions__mutmut_17`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `872b4e90700344a8`

```diff
# netdryrun.runner.x__link_sessions__mutmut_17: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
             except NoSuchInstance:
                 states[(node, vrf)] = {}   # the node has no such VRF or BGP instance: nothing to observe
             except Exception as e:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf == "XXdefaultXX" else f" (vrf {vrf})"
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
                                "when the fault took effect") from None
```

`netdryrun.runner.x__link_sessions__mutmut_18`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `9be27a8fbd48113c`

```diff
# netdryrun.runner.x__link_sessions__mutmut_18: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -23,7 +23,7 @@
             except NoSuchInstance:
                 states[(node, vrf)] = {}   # the node has no such VRF or BGP instance: nothing to observe
             except Exception as e:
-                where = "" if vrf == "default" else f" (vrf {vrf})"
+                where = "" if vrf == "DEFAULT" else f" (vrf {vrf})"
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
                                "when the fault took effect") from None
```

`netdryrun.runner.x__link_sessions__mutmut_20`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `28fde9aab46bdff9`

```diff
# netdryrun.runner.x__link_sessions__mutmut_20: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -26,7 +26,7 @@
                 where = "" if vrf == "default" else f" (vrf {vrf})"
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
-                               "when the fault took effect") from None
+                               "XXwhen the fault took effectXX") from None
         return states[(node, vrf)]
 
     for node, iface in links:
```

`netdryrun.runner.x__link_sessions__mutmut_21`: survived (accepted, message-text: message text only: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2)); argument: Changes only text: the text of the LabError raised either way when BGP state can't be read before a fault (exit 2). The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `a1f76fc8fbe910a0`

```diff
# netdryrun.runner.x__link_sessions__mutmut_21: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -26,7 +26,7 @@
                 where = "" if vrf == "default" else f" (vrf {vrf})"
                 raise LabError(f"could not read BGP state on {node}{where} to find the BGP sessions over the links "
                                f"the scenario takes down: {e}. Netdryrun won't judge the scenario without knowing "
-                               "when the fault took effect") from None
+                               "WHEN THE FAULT TOOK EFFECT") from None
         return states[(node, vrf)]
 
     for node, iface in links:
```

`netdryrun.runner.x__link_sessions__mutmut_7`: survived (accepted, logging: message text only: a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it); argument: Changes only a line passed to log(): a progress or warning line passed to log(); nothing in the verdict, the report status or the exit code depends on it. log() output reaches no result field, status or exit code, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `f2a8ea13778f272d`

```diff
# netdryrun.runner.x__link_sessions__mutmut_7: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -15,7 +15,7 @@
             try:
                 driver = driver_for(node)
             except DriverError as e:
-                log(f"  {node}: no driver ({e}); no BGP session to observe there")
+                log(None)
                 states[(node, vrf)] = {}
                 return states[(node, vrf)]
             try:
```

## `checks._bgp_route` (9)

`netdryrun.checks.x__bgp_route__mutmut_129`: survived (accepted, message-text: message text only: the text of a failure detail, the verdict is unchanged); argument: Changes only text: the text of a failure detail, the verdict is unchanged. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `8766113b82390fa1`

```diff
# netdryrun.checks.x__bgp_route__mutmut_129: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -30,7 +30,7 @@
         if key in p and getattr(best, key) != p[key]:
             wrong.append(f"{label} is {_opt(getattr(best, key))}, expected {p[key]}")
     if "next_hop" in p and best.next_hop != p["next_hop"]:
-        wrong.append(f"next hop is {best.next_hop or '?'}, expected {p['next_hop']}")
+        wrong.append(f"next hop is {best.next_hop or 'XX?XX'}, expected {p['next_hop']}")
     if wrong:
         return False, f"{'; '.join(wrong)} (best path: {_describe_path(best)})", obs.evidence
     return True, f"best path: {_describe_path(best)}", obs.evidence
```

`netdryrun.checks.x__bgp_route__mutmut_134`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `7d3804f9332113aa`

```diff
# netdryrun.checks.x__bgp_route__mutmut_134: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -32,5 +32,5 @@
     if "next_hop" in p and best.next_hop != p["next_hop"]:
         wrong.append(f"next hop is {best.next_hop or '?'}, expected {p['next_hop']}")
     if wrong:
-        return False, f"{'; '.join(wrong)} (best path: {_describe_path(best)})", obs.evidence
+        return False, f"{'XX; XX'.join(wrong)} (best path: {_describe_path(best)})", obs.evidence
     return True, f"best path: {_describe_path(best)}", obs.evidence
```

`netdryrun.checks.x__bgp_route__mutmut_18`: survived (accepted, equivalent: equivalent: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'); argument: Same behaviour on every input the function can receive: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `85319e2fc2c4a348`

```diff
# netdryrun.checks.x__bgp_route__mutmut_18: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -2,7 +2,7 @@
     """Attributes of the BGP best path for a prefix, read from the BGP table (not the routing table)."""
     obs = d.bgp_paths(p["prefix"], p.get("vrf", "default"))
     paths = obs.value
-    if p.get("present", True) is False:
+    if p.get("present", None) is False:
         # Absent means no path at all in the BGP table, best or not. The router's own non-BGP routes
         # that a NOS lists there (SR Linux, whether exported or not) aren't BGP paths.
         paths = [x for x in paths if not x.local_candidate]
```

`netdryrun.checks.x__bgp_route__mutmut_20`: survived (accepted, equivalent: equivalent: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'); argument: Same behaviour on every input the function can receive: default of a key that config validation always sets or that only matters when it is a real False; None and True are both 'not False'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `3ce401d46427dd7a`

```diff
# netdryrun.checks.x__bgp_route__mutmut_20: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -2,7 +2,7 @@
     """Attributes of the BGP best path for a prefix, read from the BGP table (not the routing table)."""
     obs = d.bgp_paths(p["prefix"], p.get("vrf", "default"))
     paths = obs.value
-    if p.get("present", True) is False:
+    if p.get("present", ) is False:
         # Absent means no path at all in the BGP table, best or not. The router's own non-BGP routes
         # that a NOS lists there (SR Linux, whether exported or not) aren't BGP paths.
         paths = [x for x in paths if not x.local_candidate]
```

`netdryrun.checks.x__bgp_route__mutmut_32`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `886537b37c36745c`

```diff
# netdryrun.checks.x__bgp_route__mutmut_32: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -8,7 +8,7 @@
         paths = [x for x in paths if not x.local_candidate]
         if paths:
             return False, f"unexpectedly in the BGP table ({len(paths)} path(s); {_describe_path(paths[0])})", obs.evidence
-        return True, "no BGP path", obs.evidence
+        return True, "XXno BGP pathXX", obs.evidence
     if not paths:
         return False, "no BGP path", obs.evidence
     best = next((x for x in paths if x.best), None)
```

`netdryrun.checks.x__bgp_route__mutmut_33`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `1da19f8a7ecd8094`

```diff
# netdryrun.checks.x__bgp_route__mutmut_33: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -8,7 +8,7 @@
         paths = [x for x in paths if not x.local_candidate]
         if paths:
             return False, f"unexpectedly in the BGP table ({len(paths)} path(s); {_describe_path(paths[0])})", obs.evidence
-        return True, "no BGP path", obs.evidence
+        return True, "no bgp path", obs.evidence
     if not paths:
         return False, "no BGP path", obs.evidence
     best = next((x for x in paths if x.best), None)
```

`netdryrun.checks.x__bgp_route__mutmut_34`: survived (accepted, message-text: message text only: the detail text of a check result, same verdict and evidence); argument: Changes only text: the detail text of a check result, same verdict and evidence. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `dd0093f965de7715`

```diff
# netdryrun.checks.x__bgp_route__mutmut_34: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -8,7 +8,7 @@
         paths = [x for x in paths if not x.local_candidate]
         if paths:
             return False, f"unexpectedly in the BGP table ({len(paths)} path(s); {_describe_path(paths[0])})", obs.evidence
-        return True, "no BGP path", obs.evidence
+        return True, "NO BGP PATH", obs.evidence
     if not paths:
         return False, "no BGP path", obs.evidence
     best = next((x for x in paths if x.best), None)
```

`netdryrun.checks.x__bgp_route__mutmut_59`: survived (accepted, message-text: message text only: the text of a failure detail, the verdict is unchanged); argument: Changes only text: the text of a failure detail, the verdict is unchanged. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `950d73f5e77adb05`

```diff
# netdryrun.checks.x__bgp_route__mutmut_59: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -18,7 +18,7 @@
     have = set(best.all_communities())
     missing = [c for c in p.get("communities", []) if c not in have]
     if missing:
-        wrong.append(f"missing communities {' '.join(community_name(c) for c in missing)}")
+        wrong.append(f"missing communities {'XX XX'.join(community_name(c) for c in missing)}")
     extra = [c for c in p.get("without_communities", []) if c in have]
     if extra:
         wrong.append(f"carries communities {' '.join(community_name(c) for c in extra)}")
```

`netdryrun.checks.x__bgp_route__mutmut_71`: survived (accepted, message-text: message text only: the text of a failure detail, the verdict is unchanged); argument: Changes only text: the text of a failure detail, the verdict is unchanged. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `4fb7326c94111cf8`

```diff
# netdryrun.checks.x__bgp_route__mutmut_71: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -21,7 +21,7 @@
         wrong.append(f"missing communities {' '.join(community_name(c) for c in missing)}")
     extra = [c for c in p.get("without_communities", []) if c in have]
     if extra:
-        wrong.append(f"carries communities {' '.join(community_name(c) for c in extra)}")
+        wrong.append(f"carries communities {'XX XX'.join(community_name(c) for c in extra)}")
     if "as_path" in p and best.as_path != p["as_path"]:
         wrong.append(f"as-path is '{best.as_path}', expected '{p['as_path']}'")
     if "as_path_regex" in p and not re.search(p["as_path_regex"], best.as_path or ""):
```

## `drivers.srlinux.SrlDriver._read_path` (9)

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `1e921a78f33931ac`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_10: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -2,7 +2,7 @@
     # attr-id and neighbor come from device output and go back into a CLI string: only a number and an IP
     attr_id = str(row.get("attr-id"))
     if not attr_id.isdigit():
-        raise DriverError(f"unexpected attr-id {attr_id[:40]!r} for {row.get('prefix')}")
+        raise DriverError(f"unexpected attr-id {attr_id[:40]!r} for {row.get('XXprefixXX')}")
     attrs = self._cli(f"info from state /network-instance {vrf} bgp-rib attr-sets attr-set {attr_id}", ev)
     default_lp = None
     neighbor = _ip_or_none(row.get("neighbor"))
```

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_11`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `510da5dbb49fac3d`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_11: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -2,7 +2,7 @@
     # attr-id and neighbor come from device output and go back into a CLI string: only a number and an IP
     attr_id = str(row.get("attr-id"))
     if not attr_id.isdigit():
-        raise DriverError(f"unexpected attr-id {attr_id[:40]!r} for {row.get('prefix')}")
+        raise DriverError(f"unexpected attr-id {attr_id[:40]!r} for {row.get('PREFIX')}")
     attrs = self._cli(f"info from state /network-instance {vrf} bgp-rib attr-sets attr-set {attr_id}", ev)
     default_lp = None
     neighbor = _ip_or_none(row.get("neighbor"))
```

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_30`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `80b067b0fa5cf2e2`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_30: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -8,7 +8,7 @@
     neighbor = _ip_or_none(row.get("neighbor"))
     # The router's own routes (neighbor 0.0.0.0) have no neighbor to ask. For a learned path, a failing
     # lookup is an error, never a silently unknown local-pref.
-    if "local-pref" not in _json(attrs, ATTR_CMD) and neighbor and _bgp_learned(row) \
+    if "local-pref" not in _json(attrs, None) and neighbor and _bgp_learned(row) \
                 and not ipaddress.ip_address(neighbor).is_unspecified:
         state = _json(self._cli(f"info from state /network-instance {vrf} protocols bgp neighbor "
                                 f"{neighbor} local-preference", ev), NEIGHBORS_CMD)
```

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_32`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `8b51dfdc3e6d6ec3`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_32: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -8,7 +8,7 @@
     neighbor = _ip_or_none(row.get("neighbor"))
     # The router's own routes (neighbor 0.0.0.0) have no neighbor to ask. For a learned path, a failing
     # lookup is an error, never a silently unknown local-pref.
-    if "local-pref" not in _json(attrs, ATTR_CMD) and neighbor and _bgp_learned(row) \
+    if "local-pref" not in _json(attrs, ) and neighbor and _bgp_learned(row) \
                 and not ipaddress.ip_address(neighbor).is_unspecified:
         state = _json(self._cli(f"info from state /network-instance {vrf} protocols bgp neighbor "
                                 f"{neighbor} local-preference", ev), NEIGHBORS_CMD)
```

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_38`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `389a80466c6dd8ca`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_38: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -11,7 +11,7 @@
     if "local-pref" not in _json(attrs, ATTR_CMD) and neighbor and _bgp_learned(row) \
                 and not ipaddress.ip_address(neighbor).is_unspecified:
         state = _json(self._cli(f"info from state /network-instance {vrf} protocols bgp neighbor "
-                                f"{neighbor} local-preference", ev), NEIGHBORS_CMD)
+                                f"{neighbor} local-preference", ev), None)
         lp = state.get("local-preference")
         default_lp = as_int(NEIGHBORS_CMD, lp) if lp is not None else None
     return parse_attr_set(attrs, row, default_lp)
```

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_40`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `5a1198369fc60c13`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_40: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -11,7 +11,7 @@
     if "local-pref" not in _json(attrs, ATTR_CMD) and neighbor and _bgp_learned(row) \
                 and not ipaddress.ip_address(neighbor).is_unspecified:
         state = _json(self._cli(f"info from state /network-instance {vrf} protocols bgp neighbor "
-                                f"{neighbor} local-preference", ev), NEIGHBORS_CMD)
+                                f"{neighbor} local-preference", ev), )
         lp = state.get("local-preference")
         default_lp = as_int(NEIGHBORS_CMD, lp) if lp is not None else None
     return parse_attr_set(attrs, row, default_lp)
```

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_52`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `ae10172804a0d3b6`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_52: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -13,5 +13,5 @@
         state = _json(self._cli(f"info from state /network-instance {vrf} protocols bgp neighbor "
                                 f"{neighbor} local-preference", ev), NEIGHBORS_CMD)
         lp = state.get("local-preference")
-        default_lp = as_int(NEIGHBORS_CMD, lp) if lp is not None else None
+        default_lp = as_int(None, lp) if lp is not None else None
     return parse_attr_set(attrs, row, default_lp)
```

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_8`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `be4c81fbd4e0e253`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_8: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -2,7 +2,7 @@
     # attr-id and neighbor come from device output and go back into a CLI string: only a number and an IP
     attr_id = str(row.get("attr-id"))
     if not attr_id.isdigit():
-        raise DriverError(f"unexpected attr-id {attr_id[:40]!r} for {row.get('prefix')}")
+        raise DriverError(f"unexpected attr-id {attr_id[:41]!r} for {row.get('prefix')}")
     attrs = self._cli(f"info from state /network-instance {vrf} bgp-rib attr-sets attr-set {attr_id}", ev)
     default_lp = None
     neighbor = _ip_or_none(row.get("neighbor"))
```

`netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `fc71a8a8d0175c71`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁ_read_path__mutmut_9: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -2,7 +2,7 @@
     # attr-id and neighbor come from device output and go back into a CLI string: only a number and an IP
     attr_id = str(row.get("attr-id"))
     if not attr_id.isdigit():
-        raise DriverError(f"unexpected attr-id {attr_id[:40]!r} for {row.get('prefix')}")
+        raise DriverError(f"unexpected attr-id {attr_id[:40]!r} for {row.get(None)}")
     attrs = self._cli(f"info from state /network-instance {vrf} bgp-rib attr-sets attr-set {attr_id}", ev)
     default_lp = None
     neighbor = _ip_or_none(row.get("neighbor"))
```

## `runner._shape_problem` (9)

`netdryrun.runner.x__shape_problem__mutmut_18`: survived (accepted, message-text: message text only: the wording of a config-shape error); diff fingerprint `1454f76874c8eff6`

```diff
# netdryrun.runner.x__shape_problem__mutmut_18: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -12,7 +12,7 @@
             float(t)
         except (TypeError, ValueError):
             return f"{p}: timeout must be a number of seconds (for example 120), got {t!r}"
-    for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "a list of scenarios"),
+    for key, typ, what in (("checks", list, "XXa list of checksXX"), ("scenarios", list, "a list of scenarios"),
                            ("nodes", dict, "a mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}")):
         v = data.get(key)
         if v is not None and not isinstance(v, typ):
```

`netdryrun.runner.x__shape_problem__mutmut_19`: survived (accepted, message-text: message text only: the wording of a config-shape error); diff fingerprint `b78cfeb30c807370`

```diff
# netdryrun.runner.x__shape_problem__mutmut_19: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -12,7 +12,7 @@
             float(t)
         except (TypeError, ValueError):
             return f"{p}: timeout must be a number of seconds (for example 120), got {t!r}"
-    for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "a list of scenarios"),
+    for key, typ, what in (("checks", list, "A LIST OF CHECKS"), ("scenarios", list, "a list of scenarios"),
                            ("nodes", dict, "a mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}")):
         v = data.get(key)
         if v is not None and not isinstance(v, typ):
```

`netdryrun.runner.x__shape_problem__mutmut_22`: survived (accepted, message-text: message text only: the wording of a config-shape error); diff fingerprint `936514a9e6132a6b`

```diff
# netdryrun.runner.x__shape_problem__mutmut_22: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -12,7 +12,7 @@
             float(t)
         except (TypeError, ValueError):
             return f"{p}: timeout must be a number of seconds (for example 120), got {t!r}"
-    for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "a list of scenarios"),
+    for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "XXa list of scenariosXX"),
                            ("nodes", dict, "a mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}")):
         v = data.get(key)
         if v is not None and not isinstance(v, typ):
```

`netdryrun.runner.x__shape_problem__mutmut_23`: survived (accepted, message-text: message text only: the wording of a config-shape error); diff fingerprint `78ea5b4d8ddb1fb4`

```diff
# netdryrun.runner.x__shape_problem__mutmut_23: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -12,7 +12,7 @@
             float(t)
         except (TypeError, ValueError):
             return f"{p}: timeout must be a number of seconds (for example 120), got {t!r}"
-    for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "a list of scenarios"),
+    for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "A LIST OF SCENARIOS"),
                            ("nodes", dict, "a mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}")):
         v = data.get(key)
         if v is not None and not isinstance(v, typ):
```

`netdryrun.runner.x__shape_problem__mutmut_26`: survived (accepted, message-text: message text only: the wording of a config-shape error); diff fingerprint `2b1fd331132a789b`

```diff
# netdryrun.runner.x__shape_problem__mutmut_26: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -13,7 +13,7 @@
         except (TypeError, ValueError):
             return f"{p}: timeout must be a number of seconds (for example 120), got {t!r}"
     for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "a list of scenarios"),
-                           ("nodes", dict, "a mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}")):
+                           ("nodes", dict, "XXa mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}XX")):
         v = data.get(key)
         if v is not None and not isinstance(v, typ):
             return f"{p}: {key} must be {what}, not a {type(v).__name__}"
```

`netdryrun.runner.x__shape_problem__mutmut_27`: survived (accepted, message-text: message text only: the wording of a config-shape error); diff fingerprint `1d9894cdb4e11cbf`

```diff
# netdryrun.runner.x__shape_problem__mutmut_27: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -13,7 +13,7 @@
         except (TypeError, ValueError):
             return f"{p}: timeout must be a number of seconds (for example 120), got {t!r}"
     for key, typ, what in (("checks", list, "a list of checks"), ("scenarios", list, "a list of scenarios"),
-                           ("nodes", dict, "a mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}")):
+                           ("nodes", dict, "A MAPPING OF NODE NAME TO SETTINGS, E.G. NODES: {R1: {DRIVER: FRR}}")):
         v = data.get(key)
         if v is not None and not isinstance(v, typ):
             return f"{p}: {key} must be {what}, not a {type(v).__name__}"
```

`netdryrun.runner.x__shape_problem__mutmut_33`: survived (accepted, message-text: message text only: the wording of a config-shape error); diff fingerprint `0056b470ebef7aa9`

```diff
# netdryrun.runner.x__shape_problem__mutmut_33: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -16,7 +16,7 @@
                            ("nodes", dict, "a mapping of node name to settings, e.g. nodes: {r1: {driver: frr}}")):
         v = data.get(key)
         if v is not None and not isinstance(v, typ):
-            return f"{p}: {key} must be {what}, not a {type(v).__name__}"
+            return f"{p}: {key} must be {what}, not a {type(None).__name__}"
     for k, v in (data.get("nodes") or {}).items():
         if v is not None and not isinstance(v, dict):
             return f"{p}: nodes.{k} must be a mapping (driver:, setup:), not a {type(v).__name__}"
```

`netdryrun.runner.x__shape_problem__mutmut_41`: survived (accepted, message-text: message text only: the wording of a config-shape error); diff fingerprint `55cd2adfbe6615c4`

```diff
# netdryrun.runner.x__shape_problem__mutmut_41: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -19,5 +19,5 @@
             return f"{p}: {key} must be {what}, not a {type(v).__name__}"
     for k, v in (data.get("nodes") or {}).items():
         if v is not None and not isinstance(v, dict):
-            return f"{p}: nodes.{k} must be a mapping (driver:, setup:), not a {type(v).__name__}"
+            return f"{p}: nodes.{k} must be a mapping (driver:, setup:), not a {type(None).__name__}"
     return None
```

`netdryrun.runner.x__shape_problem__mutmut_5`: survived (accepted, equivalent: equivalent: 'UTF-8' and 'utf-8' are the same codec); diff fingerprint `ce4b591299e2ccee`

```diff
# netdryrun.runner.x__shape_problem__mutmut_5: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -1,7 +1,7 @@
 def _shape_problem(p: Path) -> str | None:
     """A clear message for a top-level value of the wrong type, which config.load can trip over."""
     try:
-        data = yaml.safe_load(p.read_text(encoding="utf-8"))
+        data = yaml.safe_load(p.read_text(encoding="UTF-8"))
     except Exception:
         return None
     if not isinstance(data, dict):
```

## `runner.load_config` (8)

`netdryrun.runner.x_load_config__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `f26dd7c85b09e259`

```diff
# netdryrun.runner.x_load_config__mutmut_10: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -8,4 +8,4 @@
         raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
     except Exception as e:
         p = _config_path(path)
-        raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
+        raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(None).__name__}: {e}") from None
```

`netdryrun.runner.x_load_config__mutmut_2`: survived (accepted, equivalent: equivalent: unreachable branch: config.load already turns every YAML error into a ConfigError); diff fingerprint `ccc1f436273e40b4`

```diff
# netdryrun.runner.x_load_config__mutmut_2: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -5,7 +5,7 @@
     except ConfigError:
         raise
     except yaml.YAMLError as e:
-        raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
+        raise ConfigError(None) from None
     except Exception as e:
         p = _config_path(path)
         raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
```

`netdryrun.runner.x_load_config__mutmut_3`: survived (accepted, equivalent: equivalent: unreachable branch: config.load already turns every YAML error into a ConfigError); diff fingerprint `d8cbe897e2d205da`

```diff
# netdryrun.runner.x_load_config__mutmut_3: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -5,7 +5,7 @@
     except ConfigError:
         raise
     except yaml.YAMLError as e:
-        raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
+        raise ConfigError(f"{_config_path(None)}: {_yaml_problem(e)}") from None
     except Exception as e:
         p = _config_path(path)
         raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
```

`netdryrun.runner.x_load_config__mutmut_4`: survived (accepted, equivalent: equivalent: unreachable branch: config.load already turns every YAML error into a ConfigError); diff fingerprint `f43e5852135091a5`

```diff
# netdryrun.runner.x_load_config__mutmut_4: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -5,7 +5,7 @@
     except ConfigError:
         raise
     except yaml.YAMLError as e:
-        raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
+        raise ConfigError(f"{_config_path(path)}: {_yaml_problem(None)}") from None
     except Exception as e:
         p = _config_path(path)
         raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
```

`netdryrun.runner.x_load_config__mutmut_5`: survived (accepted, message-text: message text only: the file name in the error; still a ConfigError); diff fingerprint `bd71b126a32cae4a`

```diff
# netdryrun.runner.x_load_config__mutmut_5: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -7,5 +7,5 @@
     except yaml.YAMLError as e:
         raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
     except Exception as e:
-        p = _config_path(path)
+        p = None
         raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
```

`netdryrun.runner.x_load_config__mutmut_7`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `3a2aed4befc8ad66`

```diff
# netdryrun.runner.x_load_config__mutmut_7: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -8,4 +8,4 @@
         raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
     except Exception as e:
         p = _config_path(path)
-        raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
+        raise ConfigError(None) from None
```

`netdryrun.runner.x_load_config__mutmut_8`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `1336685468cbd6c5`

```diff
# netdryrun.runner.x_load_config__mutmut_8: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -8,4 +8,4 @@
         raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
     except Exception as e:
         p = _config_path(path)
-        raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
+        raise ConfigError(_shape_problem(p) and f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
```

`netdryrun.runner.x_load_config__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `1b9158bc9ead26f4`

```diff
# netdryrun.runner.x_load_config__mutmut_9: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -8,4 +8,4 @@
         raise ConfigError(f"{_config_path(path)}: {_yaml_problem(e)}") from None
     except Exception as e:
         p = _config_path(path)
-        raise ConfigError(_shape_problem(p) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
+        raise ConfigError(_shape_problem(None) or f"{p}: cannot load the config: {type(e).__name__}: {e}") from None
```

## `config._reject_unknown` (7)

`netdryrun.config.x__reject_unknown__mutmut_10`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `87962a85cbe150a2`

```diff
# netdryrun.config.x__reject_unknown__mutmut_10: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def _reject_unknown(where: str, raw: dict, allowed: Any, what: str = "key", context: str = "") -> None:
     unknown = [k for k in raw if k not in allowed]
     if unknown:
-        hints = "".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
+        hints = "XXXX".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
                         for k in unknown) if len(unknown) > 1 else _suggest(unknown[0], allowed)
         raise ConfigError(f"{where}: unknown {what}s {[str(k) for k in unknown]}{context}{hints}; "
                           f"allowed: {', '.join(sorted(allowed))}")
```

`netdryrun.config.x__reject_unknown__mutmut_15`: survived (accepted, message-text: message text only: the did-you-mean hints in the error); diff fingerprint `7a913e8380d865f9`

```diff
# netdryrun.config.x__reject_unknown__mutmut_15: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def _reject_unknown(where: str, raw: dict, allowed: Any, what: str = "key", context: str = "") -> None:
     unknown = [k for k in raw if k not in allowed]
     if unknown:
-        hints = "".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
+        hints = "".join(_suggest(None, allowed).replace("; did you mean", f"; for {k!r} did you mean")
                         for k in unknown) if len(unknown) > 1 else _suggest(unknown[0], allowed)
         raise ConfigError(f"{where}: unknown {what}s {[str(k) for k in unknown]}{context}{hints}; "
                           f"allowed: {', '.join(sorted(allowed))}")
```

`netdryrun.config.x__reject_unknown__mutmut_19`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `119ee31514ce8fd3`

```diff
# netdryrun.config.x__reject_unknown__mutmut_19: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def _reject_unknown(where: str, raw: dict, allowed: Any, what: str = "key", context: str = "") -> None:
     unknown = [k for k in raw if k not in allowed]
     if unknown:
-        hints = "".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
+        hints = "".join(_suggest(k, allowed).replace("XX; did you meanXX", f"; for {k!r} did you mean")
                         for k in unknown) if len(unknown) > 1 else _suggest(unknown[0], allowed)
         raise ConfigError(f"{where}: unknown {what}s {[str(k) for k in unknown]}{context}{hints}; "
                           f"allowed: {', '.join(sorted(allowed))}")
```

`netdryrun.config.x__reject_unknown__mutmut_20`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `66b256e7f45e235c`

```diff
# netdryrun.config.x__reject_unknown__mutmut_20: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def _reject_unknown(where: str, raw: dict, allowed: Any, what: str = "key", context: str = "") -> None:
     unknown = [k for k in raw if k not in allowed]
     if unknown:
-        hints = "".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
+        hints = "".join(_suggest(k, allowed).replace("; DID YOU MEAN", f"; for {k!r} did you mean")
                         for k in unknown) if len(unknown) > 1 else _suggest(unknown[0], allowed)
         raise ConfigError(f"{where}: unknown {what}s {[str(k) for k in unknown]}{context}{hints}; "
                           f"allowed: {', '.join(sorted(allowed))}")
```

`netdryrun.config.x__reject_unknown__mutmut_22`: survived (accepted, message-text: message text only: the did-you-mean hints in the error); diff fingerprint `8fde1c1559e1a5d9`

```diff
# netdryrun.config.x__reject_unknown__mutmut_22: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -2,6 +2,6 @@
     unknown = [k for k in raw if k not in allowed]
     if unknown:
         hints = "".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
-                        for k in unknown) if len(unknown) > 1 else _suggest(unknown[0], allowed)
+                        for k in unknown) if len(unknown) > 2 else _suggest(unknown[0], allowed)
         raise ConfigError(f"{where}: unknown {what}s {[str(k) for k in unknown]}{context}{hints}; "
                           f"allowed: {', '.join(sorted(allowed))}")
```

`netdryrun.config.x__reject_unknown__mutmut_31`: survived (accepted, message-text: message text only: part of an error or detail message string); diff fingerprint `003575753bf70fd6`

```diff
# netdryrun.config.x__reject_unknown__mutmut_31: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -4,4 +4,4 @@
         hints = "".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
                         for k in unknown) if len(unknown) > 1 else _suggest(unknown[0], allowed)
         raise ConfigError(f"{where}: unknown {what}s {[str(k) for k in unknown]}{context}{hints}; "
-                          f"allowed: {', '.join(sorted(allowed))}")
+                          f"allowed: {'XX, XX'.join(sorted(allowed))}")
```

`netdryrun.config.x__reject_unknown__mutmut_7`: survived (accepted, message-text: message text only: the did-you-mean hints in the error); diff fingerprint `d609f2b47b6baa1f`

```diff
# netdryrun.config.x__reject_unknown__mutmut_7: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -2,6 +2,6 @@
     unknown = [k for k in raw if k not in allowed]
     if unknown:
         hints = "".join(_suggest(k, allowed).replace("; did you mean", f"; for {k!r} did you mean")
-                        for k in unknown) if len(unknown) > 1 else _suggest(unknown[0], allowed)
+                        for k in unknown) if (len(unknown) > 1) and False else _suggest(unknown[0], allowed)
         raise ConfigError(f"{where}: unknown {what}s {[str(k) for k in unknown]}{context}{hints}; "
                           f"allowed: {', '.join(sorted(allowed))}")
```

## `drivers.base.unexpected` (7)

`netdryrun.drivers.base.x_unexpected__mutmut_1`: survived (accepted, message-text: message text only: the output snippet in the error); diff fingerprint `dee42fc42263d0bc`

```diff
# netdryrun.drivers.base.x_unexpected__mutmut_1: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,4 +1,4 @@
 def unexpected(command: str, text: object) -> DriverError:
     """The error for output that doesn't have the structure the parser knows. Never read it as 'nothing'."""
-    snippet = " ".join(str(text).split())[:200] or "no output"
+    snippet = None
     return DriverError(f"unexpected output from `{command}`: {snippet}")
```

`netdryrun.drivers.base.x_unexpected__mutmut_2`: survived (accepted, message-text: message text only: the output snippet in the error); diff fingerprint `ebeeecadd073f0fd`

```diff
# netdryrun.drivers.base.x_unexpected__mutmut_2: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,4 +1,4 @@
 def unexpected(command: str, text: object) -> DriverError:
     """The error for output that doesn't have the structure the parser knows. Never read it as 'nothing'."""
-    snippet = " ".join(str(text).split())[:200] or "no output"
+    snippet = " ".join(str(text).split())[:200] and "no output"
     return DriverError(f"unexpected output from `{command}`: {snippet}")
```

`netdryrun.drivers.base.x_unexpected__mutmut_4`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `44cb3bf0f84ac898`

```diff
# netdryrun.drivers.base.x_unexpected__mutmut_4: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,4 +1,4 @@
 def unexpected(command: str, text: object) -> DriverError:
     """The error for output that doesn't have the structure the parser knows. Never read it as 'nothing'."""
-    snippet = " ".join(str(text).split())[:200] or "no output"
+    snippet = "XX XX".join(str(text).split())[:200] or "no output"
     return DriverError(f"unexpected output from `{command}`: {snippet}")
```

`netdryrun.drivers.base.x_unexpected__mutmut_5`: survived (accepted, message-text: message text only: the output snippet in the error); diff fingerprint `63f2eb05cc38b90a`

```diff
# netdryrun.drivers.base.x_unexpected__mutmut_5: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,4 +1,4 @@
 def unexpected(command: str, text: object) -> DriverError:
     """The error for output that doesn't have the structure the parser knows. Never read it as 'nothing'."""
-    snippet = " ".join(str(text).split())[:200] or "no output"
+    snippet = " ".join(str(None).split())[:200] or "no output"
     return DriverError(f"unexpected output from `{command}`: {snippet}")
```

`netdryrun.drivers.base.x_unexpected__mutmut_6`: survived (accepted, message-text: message text only: the output snippet in the error); diff fingerprint `95d108cdf6c9eea8`

```diff
# netdryrun.drivers.base.x_unexpected__mutmut_6: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,4 +1,4 @@
 def unexpected(command: str, text: object) -> DriverError:
     """The error for output that doesn't have the structure the parser knows. Never read it as 'nothing'."""
-    snippet = " ".join(str(text).split())[:200] or "no output"
+    snippet = " ".join(str(text).split())[:201] or "no output"
     return DriverError(f"unexpected output from `{command}`: {snippet}")
```

`netdryrun.drivers.base.x_unexpected__mutmut_7`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `33017b0e283901f0`

```diff
# netdryrun.drivers.base.x_unexpected__mutmut_7: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,4 +1,4 @@
 def unexpected(command: str, text: object) -> DriverError:
     """The error for output that doesn't have the structure the parser knows. Never read it as 'nothing'."""
-    snippet = " ".join(str(text).split())[:200] or "no output"
+    snippet = " ".join(str(text).split())[:200] or "XXno outputXX"
     return DriverError(f"unexpected output from `{command}`: {snippet}")
```

`netdryrun.drivers.base.x_unexpected__mutmut_8`: survived (accepted, message-text: message text only: the text of a detail or error message); diff fingerprint `c09ed68052896115`

```diff
# netdryrun.drivers.base.x_unexpected__mutmut_8: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,4 +1,4 @@
 def unexpected(command: str, text: object) -> DriverError:
     """The error for output that doesn't have the structure the parser knows. Never read it as 'nothing'."""
-    snippet = " ".join(str(text).split())[:200] or "no output"
+    snippet = " ".join(str(text).split())[:200] or "NO OUTPUT"
     return DriverError(f"unexpected output from `{command}`: {snippet}")
```

## `drivers.frr._bgp_json` (7)

`netdryrun.drivers.frr.x__bgp_json__mutmut_18`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `4299cd884cb945ed`

```diff
# netdryrun.drivers.frr.x__bgp_json__mutmut_18: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -4,7 +4,7 @@
         raise unexpected(command, text)
     if "warning" in data:  # e.g. {"warning": "View/Vrf is unknown"}
         if isinstance(data["warning"], str) and _NO_INSTANCE.search(data["warning"]):
-            raise NoSuchInstance(f"vtysh: {data['warning']}")
+            raise NoSuchInstance(None)
         raise DriverError(f"vtysh: {data['warning']}")
     if data.get("bgpNoSuchInstance"):
         raise NoSuchInstance("vtysh: no BGP instance in this VRF")
```

`netdryrun.drivers.frr.x__bgp_json__mutmut_2`: survived (accepted, message-text: message text only: the text of the DriverError raised either way); diff fingerprint `5229bbaf13963c07`

```diff
# netdryrun.drivers.frr.x__bgp_json__mutmut_2: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -1,5 +1,5 @@
 def _bgp_json(command: str, text: str) -> dict:
-    data = load_json(command, text)
+    data = load_json(None, text)
     if not isinstance(data, dict):
         raise unexpected(command, text)
     if "warning" in data:  # e.g. {"warning": "View/Vrf is unknown"}
```

`netdryrun.drivers.frr.x__bgp_json__mutmut_21`: survived (accepted, message-text: message text only: the text of the DriverError raised either way); diff fingerprint `1323bfb67756aebc`

```diff
# netdryrun.drivers.frr.x__bgp_json__mutmut_21: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -5,7 +5,7 @@
     if "warning" in data:  # e.g. {"warning": "View/Vrf is unknown"}
         if isinstance(data["warning"], str) and _NO_INSTANCE.search(data["warning"]):
             raise NoSuchInstance(f"vtysh: {data['warning']}")
-        raise DriverError(f"vtysh: {data['warning']}")
+        raise DriverError(None)
     if data.get("bgpNoSuchInstance"):
         raise NoSuchInstance("vtysh: no BGP instance in this VRF")
     return data
```

`netdryrun.drivers.frr.x__bgp_json__mutmut_29`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `f56d93f66c1e6958`

```diff
# netdryrun.drivers.frr.x__bgp_json__mutmut_29: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -7,5 +7,5 @@
             raise NoSuchInstance(f"vtysh: {data['warning']}")
         raise DriverError(f"vtysh: {data['warning']}")
     if data.get("bgpNoSuchInstance"):
-        raise NoSuchInstance("vtysh: no BGP instance in this VRF")
+        raise NoSuchInstance("XXvtysh: no BGP instance in this VRFXX")
     return data
```

`netdryrun.drivers.frr.x__bgp_json__mutmut_30`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `1b62d0ce9835dfbf`

```diff
# netdryrun.drivers.frr.x__bgp_json__mutmut_30: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -7,5 +7,5 @@
             raise NoSuchInstance(f"vtysh: {data['warning']}")
         raise DriverError(f"vtysh: {data['warning']}")
     if data.get("bgpNoSuchInstance"):
-        raise NoSuchInstance("vtysh: no BGP instance in this VRF")
+        raise NoSuchInstance("vtysh: no bgp instance in this vrf")
     return data
```

`netdryrun.drivers.frr.x__bgp_json__mutmut_7`: survived (accepted, message-text: message text only: the text of the DriverError raised either way); diff fingerprint `f86b68e146bf2555`

```diff
# netdryrun.drivers.frr.x__bgp_json__mutmut_7: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -1,7 +1,7 @@
 def _bgp_json(command: str, text: str) -> dict:
     data = load_json(command, text)
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(None, text)
     if "warning" in data:  # e.g. {"warning": "View/Vrf is unknown"}
         if isinstance(data["warning"], str) and _NO_INSTANCE.search(data["warning"]):
             raise NoSuchInstance(f"vtysh: {data['warning']}")
```

`netdryrun.drivers.frr.x__bgp_json__mutmut_8`: survived (accepted, message-text: message text only: the text of the DriverError raised either way); diff fingerprint `729e23e81a856286`

```diff
# netdryrun.drivers.frr.x__bgp_json__mutmut_8: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -1,7 +1,7 @@
 def _bgp_json(command: str, text: str) -> dict:
     data = load_json(command, text)
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(command, None)
     if "warning" in data:  # e.g. {"warning": "View/Vrf is unknown"}
         if isinstance(data["warning"], str) and _NO_INSTANCE.search(data["warning"]):
             raise NoSuchInstance(f"vtysh: {data['warning']}")
```

## `checks.is_post_convergence` (6)

`netdryrun.checks.x_is_post_convergence__mutmut_13`: survived (accepted, equivalent: equivalent: only present `is False` matters; a missing key gives None or True, neither is False); argument: Same behaviour on every input the function can receive: only present `is False` matters; a missing key gives None or True, neither is False. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `a54ee3b873eccce1`

```diff
# netdryrun.checks.x_is_post_convergence__mutmut_13: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -5,7 +5,7 @@
     about a best path's attributes (the best path can change when a slower session comes up)."""
     p = check.params
     return (
-        (check.type in ("route", "bgp_route") and p.get("present", True) is False)
+        (check.type in ("route", "bgp_route") and p.get("present", None) is False)
         # A best-path attribute (next hop, AS path, local-pref, MED, communities, or "must not carry") can
         # pass on a transient best path before the real one arrives: judge it after convergence and hold it
         or (check.type == "bgp_route" and any(k in p for k in BGP_ATTRIBUTES))
```

`netdryrun.checks.x_is_post_convergence__mutmut_15`: survived (accepted, equivalent: equivalent: only present `is False` matters; a missing key gives None or True, neither is False); argument: Same behaviour on every input the function can receive: only present `is False` matters; a missing key gives None or True, neither is False. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `f99b6607097f558f`

```diff
# netdryrun.checks.x_is_post_convergence__mutmut_15: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -5,7 +5,7 @@
     about a best path's attributes (the best path can change when a slower session comes up)."""
     p = check.params
     return (
-        (check.type in ("route", "bgp_route") and p.get("present", True) is False)
+        (check.type in ("route", "bgp_route") and p.get("present", ) is False)
         # A best-path attribute (next hop, AS path, local-pref, MED, communities, or "must not carry") can
         # pass on a transient best path before the real one arrives: judge it after convergence and hold it
         or (check.type == "bgp_route" and any(k in p for k in BGP_ATTRIBUTES))
```

`netdryrun.checks.x_is_post_convergence__mutmut_32`: survived (accepted, equivalent: equivalent: only expect == 'failure' matters; a missing key gives a default that is not 'failure' either way); argument: Same behaviour on every input the function can receive: only expect == 'failure' matters; a missing key gives a default that is not 'failure' either way. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `f225b0c7e0661c7f`

```diff
# netdryrun.checks.x_is_post_convergence__mutmut_32: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -9,7 +9,7 @@
         # A best-path attribute (next hop, AS path, local-pref, MED, communities, or "must not carry") can
         # pass on a transient best path before the real one arrives: judge it after convergence and hold it
         or (check.type == "bgp_route" and any(k in p for k in BGP_ATTRIBUTES))
-        or (check.type == "ping" and p.get("expect", "success") == "failure")
+        or (check.type == "ping" and p.get("expect", None) == "failure")
         or (check.type == "bgp_session" and p.get("state", "established") != "established")
         or (check.type == "bgp_prefixes" and ("max" in p or "exact" in p))
     )
```

`netdryrun.checks.x_is_post_convergence__mutmut_34`: survived (accepted, equivalent: equivalent: only expect == 'failure' matters; a missing key gives a default that is not 'failure' either way); argument: Same behaviour on every input the function can receive: only expect == 'failure' matters; a missing key gives a default that is not 'failure' either way. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `31543023a1dd6a1e`

```diff
# netdryrun.checks.x_is_post_convergence__mutmut_34: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -9,7 +9,7 @@
         # A best-path attribute (next hop, AS path, local-pref, MED, communities, or "must not carry") can
         # pass on a transient best path before the real one arrives: judge it after convergence and hold it
         or (check.type == "bgp_route" and any(k in p for k in BGP_ATTRIBUTES))
-        or (check.type == "ping" and p.get("expect", "success") == "failure")
+        or (check.type == "ping" and p.get("expect", ) == "failure")
         or (check.type == "bgp_session" and p.get("state", "established") != "established")
         or (check.type == "bgp_prefixes" and ("max" in p or "exact" in p))
     )
```

`netdryrun.checks.x_is_post_convergence__mutmut_37`: survived (accepted, equivalent: equivalent: only expect == 'failure' matters; a missing key gives a default that is not 'failure' either way); argument: Same behaviour on every input the function can receive: only expect == 'failure' matters; a missing key gives a default that is not 'failure' either way. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `650cf5f3d9374b0a`

```diff
# netdryrun.checks.x_is_post_convergence__mutmut_37: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -9,7 +9,7 @@
         # A best-path attribute (next hop, AS path, local-pref, MED, communities, or "must not carry") can
         # pass on a transient best path before the real one arrives: judge it after convergence and hold it
         or (check.type == "bgp_route" and any(k in p for k in BGP_ATTRIBUTES))
-        or (check.type == "ping" and p.get("expect", "success") == "failure")
+        or (check.type == "ping" and p.get("expect", "XXsuccessXX") == "failure")
         or (check.type == "bgp_session" and p.get("state", "established") != "established")
         or (check.type == "bgp_prefixes" and ("max" in p or "exact" in p))
     )
```

`netdryrun.checks.x_is_post_convergence__mutmut_38`: survived (accepted, equivalent: equivalent: only expect == 'failure' matters; a missing key gives a default that is not 'failure' either way); argument: Same behaviour on every input the function can receive: only expect == 'failure' matters; a missing key gives a default that is not 'failure' either way. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `a8d7b82d1560029f`

```diff
# netdryrun.checks.x_is_post_convergence__mutmut_38: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -9,7 +9,7 @@
         # A best-path attribute (next hop, AS path, local-pref, MED, communities, or "must not carry") can
         # pass on a transient best path before the real one arrives: judge it after convergence and hold it
         or (check.type == "bgp_route" and any(k in p for k in BGP_ATTRIBUTES))
-        or (check.type == "ping" and p.get("expect", "success") == "failure")
+        or (check.type == "ping" and p.get("expect", "SUCCESS") == "failure")
         or (check.type == "bgp_session" and p.get("state", "established") != "established")
         or (check.type == "bgp_prefixes" and ("max" in p or "exact" in p))
     )
```

## `drivers.base.Driver._exec` (6)

`netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_28`: survived (accepted, message-text: message text only: the last output line quoted in the error); diff fingerprint `59f36e6254c686f0`

```diff
# netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_28: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -3,6 +3,6 @@
     r = self.lab.exec(self.node, cmd, timeout=timeout)
     evidence.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
     if r.rc != 0:
-        msg = (r.stderr or r.stdout).strip().splitlines()
+        msg = None
         raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
     return r.stdout
```

`netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_29`: survived (accepted, message-text: message text only: the last output line quoted in the error); diff fingerprint `ef66365799d488a0`

```diff
# netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_29: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -3,6 +3,6 @@
     r = self.lab.exec(self.node, cmd, timeout=timeout)
     evidence.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
     if r.rc != 0:
-        msg = (r.stderr or r.stdout).strip().splitlines()
+        msg = (r.stderr and r.stdout).strip().splitlines()
         raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
     return r.stdout
```

`netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_32`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `5de867ab931b6c89`

```diff
# netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_32: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -4,5 +4,5 @@
     evidence.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
     if r.rc != 0:
         msg = (r.stderr or r.stdout).strip().splitlines()
-        raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
+        raise DriverError(f"`{'XX XX'.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
     return r.stdout
```

`netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_33`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `68714f41c1b4d289`

```diff
# netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_33: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -4,5 +4,5 @@
     evidence.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
     if r.rc != 0:
         msg = (r.stderr or r.stdout).strip().splitlines()
-        raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
+        raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if (msg) and False else 'no output'}")
     return r.stdout
```

`netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_37`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `3254e442ac9c218b`

```diff
# netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_37: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -4,5 +4,5 @@
     evidence.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
     if r.rc != 0:
         msg = (r.stderr or r.stdout).strip().splitlines()
-        raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
+        raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'XXno outputXX'}")
     return r.stdout
```

`netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_38`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `9f2c29f2cb29e7e1`

```diff
# netdryrun.drivers.base.xǁDriverǁ_exec__mutmut_38: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -4,5 +4,5 @@
     evidence.append({"node": self.node, "cmd": " ".join(cmd), "rc": r.rc, "output": r.stdout[-20000:], "stderr": r.stderr[-2000:]})
     if r.rc != 0:
         msg = (r.stderr or r.stdout).strip().splitlines()
-        raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'no output'}")
+        raise DriverError(f"`{' '.join(cmd)}` failed on {self.node} (rc={r.rc}): {msg[-1] if msg else 'NO OUTPUT'}")
     return r.stdout
```

## `drivers.base.as_int` (6)

`netdryrun.drivers.base.x_as_int__mutmut_1`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `4427d58b48503dc0`

```diff
# netdryrun.drivers.base.x_as_int__mutmut_1: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,6 +1,6 @@
 def as_int(command: str, value: object) -> int:
     if isinstance(value, bool):
-        raise unexpected(command, f"not a number: {value!r}")
+        raise unexpected(None, f"not a number: {value!r}")
     try:
         return int(value)
     except (TypeError, ValueError):
```

`netdryrun.drivers.base.x_as_int__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `1f2cbbf811741ce1`

```diff
# netdryrun.drivers.base.x_as_int__mutmut_10: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -4,4 +4,4 @@
     try:
         return int(value)
     except (TypeError, ValueError):
-        raise unexpected(command, f"not a number: {str(value)[:80]!r}") from None
+        raise unexpected(command, f"not a number: {str(None)[:80]!r}") from None
```

`netdryrun.drivers.base.x_as_int__mutmut_11`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `8e2df5a5ce969623`

```diff
# netdryrun.drivers.base.x_as_int__mutmut_11: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -4,4 +4,4 @@
     try:
         return int(value)
     except (TypeError, ValueError):
-        raise unexpected(command, f"not a number: {str(value)[:80]!r}") from None
+        raise unexpected(command, f"not a number: {str(value)[:81]!r}") from None
```

`netdryrun.drivers.base.x_as_int__mutmut_2`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `023e389bcdefa468`

```diff
# netdryrun.drivers.base.x_as_int__mutmut_2: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,6 +1,6 @@
 def as_int(command: str, value: object) -> int:
     if isinstance(value, bool):
-        raise unexpected(command, f"not a number: {value!r}")
+        raise unexpected(command, None)
     try:
         return int(value)
     except (TypeError, ValueError):
```

`netdryrun.drivers.base.x_as_int__mutmut_6`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `f70a40405b13e0a6`

```diff
# netdryrun.drivers.base.x_as_int__mutmut_6: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -4,4 +4,4 @@
     try:
         return int(value)
     except (TypeError, ValueError):
-        raise unexpected(command, f"not a number: {str(value)[:80]!r}") from None
+        raise unexpected(None, f"not a number: {str(value)[:80]!r}") from None
```

`netdryrun.drivers.base.x_as_int__mutmut_7`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `471cfeb0ed310d76`

```diff
# netdryrun.drivers.base.x_as_int__mutmut_7: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -4,4 +4,4 @@
     try:
         return int(value)
     except (TypeError, ValueError):
-        raise unexpected(command, f"not a number: {str(value)[:80]!r}") from None
+        raise unexpected(command, None) from None
```

## `drivers.base.load_json` (6)

`netdryrun.drivers.base.x_load_json__mutmut_11`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `0618f2d0454b24f3`

```diff
# netdryrun.drivers.base.x_load_json__mutmut_11: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -6,4 +6,4 @@
     try:
         return json.loads(text)
     except (json.JSONDecodeError, RecursionError):
-        raise unexpected(command, text) from None
+        raise unexpected(None, text) from None
```

`netdryrun.drivers.base.x_load_json__mutmut_12`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `f06af9674e875e27`

```diff
# netdryrun.drivers.base.x_load_json__mutmut_12: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -6,4 +6,4 @@
     try:
         return json.loads(text)
     except (json.JSONDecodeError, RecursionError):
-        raise unexpected(command, text) from None
+        raise unexpected(command, None) from None
```

`netdryrun.drivers.base.x_load_json__mutmut_4`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `febb25c2bd1732fb`

```diff
# netdryrun.drivers.base.x_load_json__mutmut_4: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -2,7 +2,7 @@
     """JSON from a device command. Empty output is not an empty result: every supported NOS prints a
     JSON document (at least `{}`) for a state query that succeeded."""
     if not isinstance(text, str) or not text.strip():
-        raise unexpected(command, "no output")
+        raise unexpected(None, "no output")
     try:
         return json.loads(text)
     except (json.JSONDecodeError, RecursionError):
```

`netdryrun.drivers.base.x_load_json__mutmut_5`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `7909f3ded0abed43`

```diff
# netdryrun.drivers.base.x_load_json__mutmut_5: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -2,7 +2,7 @@
     """JSON from a device command. Empty output is not an empty result: every supported NOS prints a
     JSON document (at least `{}`) for a state query that succeeded."""
     if not isinstance(text, str) or not text.strip():
-        raise unexpected(command, "no output")
+        raise unexpected(command, None)
     try:
         return json.loads(text)
     except (json.JSONDecodeError, RecursionError):
```

`netdryrun.drivers.base.x_load_json__mutmut_8`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `0d6a48e6f5b438ad`

```diff
# netdryrun.drivers.base.x_load_json__mutmut_8: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -2,7 +2,7 @@
     """JSON from a device command. Empty output is not an empty result: every supported NOS prints a
     JSON document (at least `{}`) for a state query that succeeded."""
     if not isinstance(text, str) or not text.strip():
-        raise unexpected(command, "no output")
+        raise unexpected(command, "XXno outputXX")
     try:
         return json.loads(text)
     except (json.JSONDecodeError, RecursionError):
```

`netdryrun.drivers.base.x_load_json__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `952f3f86928013a9`

```diff
# netdryrun.drivers.base.x_load_json__mutmut_9: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -2,7 +2,7 @@
     """JSON from a device command. Empty output is not an empty result: every supported NOS prints a
     JSON document (at least `{}`) for a state query that succeeded."""
     if not isinstance(text, str) or not text.strip():
-        raise unexpected(command, "no output")
+        raise unexpected(command, "NO OUTPUT")
     try:
         return json.loads(text)
     except (json.JSONDecodeError, RecursionError):
```

## `drivers.eos._learned` (6)

`netdryrun.drivers.eos.x__learned__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `84cb212a3b0e39cd`

```diff
# netdryrun.drivers.eos.x__learned__mutmut_10: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,5 +3,5 @@
     network statements, redistribution). Valid or not, active or not, it was received."""
     peer = p.get("peerEntry")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerAddr"), str):  # "" for its own paths
-        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
+        raise unexpected(BGP_CMD, None)
     return bool(peer["peerAddr"])
```

`netdryrun.drivers.eos.x__learned__mutmut_11`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `a647465d1b48a427`

```diff
# netdryrun.drivers.eos.x__learned__mutmut_11: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,5 +3,5 @@
     network statements, redistribution). Valid or not, active or not, it was received."""
     peer = p.get("peerEntry")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerAddr"), str):  # "" for its own paths
-        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
+        raise unexpected(f"path without peerEntry: {str(p)[:150]}")
     return bool(peer["peerAddr"])
```

`netdryrun.drivers.eos.x__learned__mutmut_12`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `d1ecb114785edad2`

```diff
# netdryrun.drivers.eos.x__learned__mutmut_12: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,5 +3,5 @@
     network statements, redistribution). Valid or not, active or not, it was received."""
     peer = p.get("peerEntry")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerAddr"), str):  # "" for its own paths
-        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
+        raise unexpected(BGP_CMD, )
     return bool(peer["peerAddr"])
```

`netdryrun.drivers.eos.x__learned__mutmut_13`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `0bf369cc1565bc1d`

```diff
# netdryrun.drivers.eos.x__learned__mutmut_13: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,5 +3,5 @@
     network statements, redistribution). Valid or not, active or not, it was received."""
     peer = p.get("peerEntry")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerAddr"), str):  # "" for its own paths
-        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
+        raise unexpected(BGP_CMD, f"path without peerEntry: {str(None)[:150]}")
     return bool(peer["peerAddr"])
```

`netdryrun.drivers.eos.x__learned__mutmut_14`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `98c65e1f5596d662`

```diff
# netdryrun.drivers.eos.x__learned__mutmut_14: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,5 +3,5 @@
     network statements, redistribution). Valid or not, active or not, it was received."""
     peer = p.get("peerEntry")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerAddr"), str):  # "" for its own paths
-        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
+        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:151]}")
     return bool(peer["peerAddr"])
```

`netdryrun.drivers.eos.x__learned__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `b3529522c1f4ec07`

```diff
# netdryrun.drivers.eos.x__learned__mutmut_9: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,5 +3,5 @@
     network statements, redistribution). Valid or not, active or not, it was received."""
     peer = p.get("peerEntry")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerAddr"), str):  # "" for its own paths
-        raise unexpected(BGP_CMD, f"path without peerEntry: {str(p)[:150]}")
+        raise unexpected(None, f"path without peerEntry: {str(p)[:150]}")
     return bool(peer["peerAddr"])
```

## `drivers.frr._learned` (6)

`netdryrun.drivers.frr.x__learned__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `2ed470ee5d67b686`

```diff
# netdryrun.drivers.frr.x__learned__mutmut_10: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     aggregate). Validity and best-path selection don't matter: received but not selected is present."""
     peer = p.get("peer")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerId"), str):  # every path names its peer
-        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(p)[:150]}")
+        raise unexpected(f"path without peer: {str(p)[:150]}")
     if p.get("local") or p.get("sourced"):
         return False
     return peer["peerId"] not in ("", "0.0.0.0", "::")
```

`netdryrun.drivers.frr.x__learned__mutmut_11`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `6b374f7d584ef989`

```diff
# netdryrun.drivers.frr.x__learned__mutmut_11: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     aggregate). Validity and best-path selection don't matter: received but not selected is present."""
     peer = p.get("peer")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerId"), str):  # every path names its peer
-        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(p)[:150]}")
+        raise unexpected(BGP_PATHS_CMD, )
     if p.get("local") or p.get("sourced"):
         return False
     return peer["peerId"] not in ("", "0.0.0.0", "::")
```

`netdryrun.drivers.frr.x__learned__mutmut_12`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `2c1a202b3f35aaa0`

```diff
# netdryrun.drivers.frr.x__learned__mutmut_12: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     aggregate). Validity and best-path selection don't matter: received but not selected is present."""
     peer = p.get("peer")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerId"), str):  # every path names its peer
-        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(p)[:150]}")
+        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(None)[:150]}")
     if p.get("local") or p.get("sourced"):
         return False
     return peer["peerId"] not in ("", "0.0.0.0", "::")
```

`netdryrun.drivers.frr.x__learned__mutmut_13`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `bb38c5485fb2f855`

```diff
# netdryrun.drivers.frr.x__learned__mutmut_13: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     aggregate). Validity and best-path selection don't matter: received but not selected is present."""
     peer = p.get("peer")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerId"), str):  # every path names its peer
-        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(p)[:150]}")
+        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(p)[:151]}")
     if p.get("local") or p.get("sourced"):
         return False
     return peer["peerId"] not in ("", "0.0.0.0", "::")
```

`netdryrun.drivers.frr.x__learned__mutmut_8`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `8c5d09c080765daa`

```diff
# netdryrun.drivers.frr.x__learned__mutmut_8: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     aggregate). Validity and best-path selection don't matter: received but not selected is present."""
     peer = p.get("peer")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerId"), str):  # every path names its peer
-        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(p)[:150]}")
+        raise unexpected(None, f"path without peer: {str(p)[:150]}")
     if p.get("local") or p.get("sourced"):
         return False
     return peer["peerId"] not in ("", "0.0.0.0", "::")
```

`netdryrun.drivers.frr.x__learned__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `417966b6ad6b1194`

```diff
# netdryrun.drivers.frr.x__learned__mutmut_9: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -3,7 +3,7 @@
     aggregate). Validity and best-path selection don't matter: received but not selected is present."""
     peer = p.get("peer")
     if not isinstance(peer, dict) or not isinstance(peer.get("peerId"), str):  # every path names its peer
-        raise unexpected(BGP_PATHS_CMD, f"path without peer: {str(p)[:150]}")
+        raise unexpected(BGP_PATHS_CMD, None)
     if p.get("local") or p.get("sourced"):
         return False
     return peer["peerId"] not in ("", "0.0.0.0", "::")
```

## `drivers.srlinux._list` (6)

`netdryrun.drivers.srlinux.x__list__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `1d735876cf89afdd`

```diff
# netdryrun.drivers.srlinux.x__list__mutmut_10: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -7,5 +7,5 @@
         raise unexpected(command, data)
     for r in rows:
         if not isinstance(r, dict):
-            raise unexpected(command, f"{key}: {str(r)[:150]}")
+            raise unexpected(None, f"{key}: {str(r)[:150]}")
     return rows
```

`netdryrun.drivers.srlinux.x__list__mutmut_11`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `bd90ff21d9caf199`

```diff
# netdryrun.drivers.srlinux.x__list__mutmut_11: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -7,5 +7,5 @@
         raise unexpected(command, data)
     for r in rows:
         if not isinstance(r, dict):
-            raise unexpected(command, f"{key}: {str(r)[:150]}")
+            raise unexpected(command, None)
     return rows
```

`netdryrun.drivers.srlinux.x__list__mutmut_14`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `ebd8a8ba71c7620d`

```diff
# netdryrun.drivers.srlinux.x__list__mutmut_14: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -7,5 +7,5 @@
         raise unexpected(command, data)
     for r in rows:
         if not isinstance(r, dict):
-            raise unexpected(command, f"{key}: {str(r)[:150]}")
+            raise unexpected(command, f"{key}: {str(None)[:150]}")
     return rows
```

`netdryrun.drivers.srlinux.x__list__mutmut_15`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `e5322e26afbcc0fe`

```diff
# netdryrun.drivers.srlinux.x__list__mutmut_15: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -7,5 +7,5 @@
         raise unexpected(command, data)
     for r in rows:
         if not isinstance(r, dict):
-            raise unexpected(command, f"{key}: {str(r)[:150]}")
+            raise unexpected(command, f"{key}: {str(r)[:151]}")
     return rows
```

`netdryrun.drivers.srlinux.x__list__mutmut_5`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `219bb7ad7740e5a0`

```diff
# netdryrun.drivers.srlinux.x__list__mutmut_5: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -4,7 +4,7 @@
         return []
     rows = data.get(key)
     if not isinstance(rows, list):
-        raise unexpected(command, data)
+        raise unexpected(None, data)
     for r in rows:
         if not isinstance(r, dict):
             raise unexpected(command, f"{key}: {str(r)[:150]}")
```

`netdryrun.drivers.srlinux.x__list__mutmut_6`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `aacb0c0c88860c41`

```diff
# netdryrun.drivers.srlinux.x__list__mutmut_6: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -4,7 +4,7 @@
         return []
     rows = data.get(key)
     if not isinstance(rows, list):
-        raise unexpected(command, data)
+        raise unexpected(command, None)
     for r in rows:
         if not isinstance(r, dict):
             raise unexpected(command, f"{key}: {str(r)[:150]}")
```

## `config._suggest` (5)

`netdryrun.config.x__suggest__mutmut_14`: survived (accepted, message-text: message text only: the did-you-mean hint in an error); diff fingerprint `fb2f446c2f905724`

```diff
# netdryrun.config.x__suggest__mutmut_14: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,5 +5,5 @@
     low = word.lower()
     if hints and low in hints:
         return f"; did you mean {hints[low]!r}?"
-    close = difflib.get_close_matches(low, [str(c) for c in choices], n=1, cutoff=0.6)
+    close = difflib.get_close_matches(low, [str(c) for c in choices], cutoff=0.6)
     return f"; did you mean {close[0]!r}?" if close else ""
```

`netdryrun.config.x__suggest__mutmut_15`: survived (accepted, message-text: message text only: the did-you-mean hint in an error); diff fingerprint `a01d18dc8886b754`

```diff
# netdryrun.config.x__suggest__mutmut_15: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,5 +5,5 @@
     low = word.lower()
     if hints and low in hints:
         return f"; did you mean {hints[low]!r}?"
-    close = difflib.get_close_matches(low, [str(c) for c in choices], n=1, cutoff=0.6)
+    close = difflib.get_close_matches(low, [str(c) for c in choices], n=1, )
     return f"; did you mean {close[0]!r}?" if close else ""
```

`netdryrun.config.x__suggest__mutmut_17`: survived (accepted, message-text: message text only: the did-you-mean hint in an error); diff fingerprint `03baa33c8427e8d3`

```diff
# netdryrun.config.x__suggest__mutmut_17: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -5,5 +5,5 @@
     low = word.lower()
     if hints and low in hints:
         return f"; did you mean {hints[low]!r}?"
-    close = difflib.get_close_matches(low, [str(c) for c in choices], n=1, cutoff=0.6)
+    close = difflib.get_close_matches(low, [str(c) for c in choices], n=2, cutoff=0.6)
     return f"; did you mean {close[0]!r}?" if close else ""
```

`netdryrun.config.x__suggest__mutmut_2`: survived (accepted, message-text: message text only: the did-you-mean hint in an error); diff fingerprint `090986294ba479f8`

```diff
# netdryrun.config.x__suggest__mutmut_2: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def _suggest(word: Any, choices: Any, hints: dict[str, str] | None = None) -> str:
     """ "; did you mean 'x'?" for a misspelled key or value, or "" when nothing is close."""
     if not isinstance(word, str):
-        return ""
+        return "XXXX"
     low = word.lower()
     if hints and low in hints:
         return f"; did you mean {hints[low]!r}?"
```

`netdryrun.config.x__suggest__mutmut_22`: survived (accepted, message-text: message text only: the did-you-mean hint in an error); diff fingerprint `9cc27decf92e802e`

```diff
# netdryrun.config.x__suggest__mutmut_22: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -6,4 +6,4 @@
     if hints and low in hints:
         return f"; did you mean {hints[low]!r}?"
     close = difflib.get_close_matches(low, [str(c) for c in choices], n=1, cutoff=0.6)
-    return f"; did you mean {close[0]!r}?" if close else ""
+    return f"; did you mean {close[0]!r}?" if close else "XXXX"
```

## `drivers.base.network` (5)

`netdryrun.drivers.base.x_network__mutmut_11`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `7c71bcab7eb361ee`

```diff
# netdryrun.drivers.base.x_network__mutmut_11: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -3,4 +3,4 @@
     try:
         return ipaddress.ip_network(str(value), strict=False)
     except ValueError:
-        raise unexpected(command, f"not a prefix: {str(value)[:80]!r}") from None
+        raise unexpected(command, f"not a prefix: {str(None)[:80]!r}") from None
```

`netdryrun.drivers.base.x_network__mutmut_12`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `2d76887a5bd29299`

```diff
# netdryrun.drivers.base.x_network__mutmut_12: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -3,4 +3,4 @@
     try:
         return ipaddress.ip_network(str(value), strict=False)
     except ValueError:
-        raise unexpected(command, f"not a prefix: {str(value)[:80]!r}") from None
+        raise unexpected(command, f"not a prefix: {str(value)[:81]!r}") from None
```

`netdryrun.drivers.base.x_network__mutmut_2`: survived (accepted, equivalent: equivalent: strict=None is falsy, the same as strict=False); diff fingerprint `50af274eb8707675`

```diff
# netdryrun.drivers.base.x_network__mutmut_2: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,6 +1,6 @@
 def network(command: str, value: object):
     """A prefix from device output; output with a key that isn't one is unexpected."""
     try:
-        return ipaddress.ip_network(str(value), strict=False)
+        return ipaddress.ip_network(str(value), strict=None)
     except ValueError:
         raise unexpected(command, f"not a prefix: {str(value)[:80]!r}") from None
```

`netdryrun.drivers.base.x_network__mutmut_7`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `1cdeae623bc34399`

```diff
# netdryrun.drivers.base.x_network__mutmut_7: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -3,4 +3,4 @@
     try:
         return ipaddress.ip_network(str(value), strict=False)
     except ValueError:
-        raise unexpected(command, f"not a prefix: {str(value)[:80]!r}") from None
+        raise unexpected(None, f"not a prefix: {str(value)[:80]!r}") from None
```

`netdryrun.drivers.base.x_network__mutmut_8`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `1dd86904d0cb32f0`

```diff
# netdryrun.drivers.base.x_network__mutmut_8: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -3,4 +3,4 @@
     try:
         return ipaddress.ip_network(str(value), strict=False)
     except ValueError:
-        raise unexpected(command, f"not a prefix: {str(value)[:80]!r}") from None
+        raise unexpected(command, None) from None
```

## `drivers.srlinux._json` (5)

`netdryrun.drivers.srlinux.x__json__mutmut_1`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `9345465bc3e939fc`

```diff
# netdryrun.drivers.srlinux.x__json__mutmut_1: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,4 +1,4 @@
-def _json(text: str, command: str = "sr_cli") -> dict:
+def _json(text: str, command: str = "XXsr_cliXX") -> dict:
     data = load_json(command, text)
     if not isinstance(data, dict):
         raise unexpected(command, text)
```

`netdryrun.drivers.srlinux.x__json__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `18eefd073906ac1b`

```diff
# netdryrun.drivers.srlinux.x__json__mutmut_10: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,5 +1,5 @@
 def _json(text: str, command: str = "sr_cli") -> dict:
     data = load_json(command, text)
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(command, None)
     return data
```

`netdryrun.drivers.srlinux.x__json__mutmut_2`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `31335a870854b118`

```diff
# netdryrun.drivers.srlinux.x__json__mutmut_2: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,4 +1,4 @@
-def _json(text: str, command: str = "sr_cli") -> dict:
+def _json(text: str, command: str = "SR_CLI") -> dict:
     data = load_json(command, text)
     if not isinstance(data, dict):
         raise unexpected(command, text)
```

`netdryrun.drivers.srlinux.x__json__mutmut_4`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `7b8effee425d78a2`

```diff
# netdryrun.drivers.srlinux.x__json__mutmut_4: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,5 +1,5 @@
 def _json(text: str, command: str = "sr_cli") -> dict:
-    data = load_json(command, text)
+    data = load_json(None, text)
     if not isinstance(data, dict):
         raise unexpected(command, text)
     return data
```

`netdryrun.drivers.srlinux.x__json__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `8ba54a775f0b2766`

```diff
# netdryrun.drivers.srlinux.x__json__mutmut_9: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,5 +1,5 @@
 def _json(text: str, command: str = "sr_cli") -> dict:
     data = load_json(command, text)
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(None, text)
     return data
```

## `runner._reach_then_hold` (5)

`netdryrun.runner.x__reach_then_hold__mutmut_13`: survived (accepted, equivalent: equivalent: hold_together([]) returns [], the same as the {} it replaces); argument: Same behaviour on every input the function can receive: hold_together([]) returns [], the same as the {} it replaces. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `6ac3fbd352aab299`

```diff
# netdryrun.runner.x__reach_then_hold__mutmut_13: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -2,7 +2,7 @@
     """Positive scenario checks: pass on 2 consecutive samples, then keep passing for the hold window."""
     reached = run_round_robin(checks, drivers, clock=_clock, sleep=_sleep)
     ok = [r.check for r in reached if r.passed]
-    held = {id(r.check): r for r in hold_together(ok, drivers, hold=hold, clock=_clock, sleep=_sleep)} if ok else {}
+    held = {id(r.check): r for r in hold_together(ok, drivers, hold=hold, clock=_clock, sleep=_sleep)} if (ok) or True else {}
     out = []
     for r in reached:
         h = held.get(id(r.check))
```

`netdryrun.runner.x__reach_then_hold__mutmut_34`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `02eabb0b75355075`

```diff
# netdryrun.runner.x__reach_then_hold__mutmut_34: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -10,7 +10,7 @@
             window = r.check.hold or hold
             if not h.passed:
                 h.detail = (f"{h.detail} (it passed at first, then failed within the {window:g}s hold window: "
-                            "the fault took effect late)")
+                            "XXthe fault took effect late)XX")
             h.history = (r.history + [{**x, "t": round(x["t"] + r.duration, 1)} for x in h.history])[-50:]
             h.attempts += r.attempts
             h.samples_passed += r.samples_passed
```

`netdryrun.runner.x__reach_then_hold__mutmut_35`: survived (accepted, message-text: message text only: part of an error or detail message string); argument: Changes only text: part of an error or detail message string. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `4c010c36945fdf8a`

```diff
# netdryrun.runner.x__reach_then_hold__mutmut_35: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -10,7 +10,7 @@
             window = r.check.hold or hold
             if not h.passed:
                 h.detail = (f"{h.detail} (it passed at first, then failed within the {window:g}s hold window: "
-                            "the fault took effect late)")
+                            "THE FAULT TOOK EFFECT LATE)")
             h.history = (r.history + [{**x, "t": round(x["t"] + r.duration, 1)} for x in h.history])[-50:]
             h.attempts += r.attempts
             h.samples_passed += r.samples_passed
```

`netdryrun.runner.x__reach_then_hold__mutmut_47`: survived (accepted, equivalent: equivalent: the sum of two durations already rounded to 0.1 s rounds the same to 0.01 s); argument: Same behaviour on every input the function can receive: the sum of two durations already rounded to 0.1 s rounds the same to 0.01 s. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `b38a1d9cfde5300c`

```diff
# netdryrun.runner.x__reach_then_hold__mutmut_47: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -11,7 +11,7 @@
             if not h.passed:
                 h.detail = (f"{h.detail} (it passed at first, then failed within the {window:g}s hold window: "
                             "the fault took effect late)")
-            h.history = (r.history + [{**x, "t": round(x["t"] + r.duration, 1)} for x in h.history])[-50:]
+            h.history = (r.history + [{**x, "t": round(x["t"] + r.duration, 2)} for x in h.history])[-50:]
             h.attempts += r.attempts
             h.samples_passed += r.samples_passed
             h.samples_unready += r.samples_unready
```

`netdryrun.runner.x__reach_then_hold__mutmut_62`: survived (accepted, equivalent: equivalent: the sum of two durations already rounded to 0.1 s rounds the same to 0.01 s); argument: Same behaviour on every input the function can receive: the sum of two durations already rounded to 0.1 s rounds the same to 0.01 s. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `d229fc56dcb6ff50`

```diff
# netdryrun.runner.x__reach_then_hold__mutmut_62: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -15,7 +15,7 @@
             h.attempts += r.attempts
             h.samples_passed += r.samples_passed
             h.samples_unready += r.samples_unready
-            h.duration = round(r.duration + h.duration, 1)
+            h.duration = round(r.duration + h.duration, 2)
             h.started = r.started
             r = h
         out.append(r)
```

## `runner.preflight` (5)

`netdryrun.runner.x_preflight__mutmut_13`: survived (accepted, message-text: message text only: the node list in the unknown-node error; the same exception is raised); diff fingerprint `c54fe819218de9e1`

```diff
# netdryrun.runner.x_preflight__mutmut_13: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -9,7 +9,7 @@
         | {f.node for sc in config.scenarios for f in sc.faults} | set(config.setup)
     unknown = sorted(wanted - set(lab.nodes))
     if unknown:
-        raise LabError(f"unknown node(s) {', '.join(unknown)}; the topology has {', '.join(lab.nodes)}")
+        raise LabError(f"unknown node(s) {'XX, XX'.join(unknown)}; the topology has {', '.join(lab.nodes)}")
     all_checks = config.checks + [c for sc in config.scenarios for c in sc.checks]
     if full:
         for node in sorted({c.node for c in all_checks} - set(config.drivers)):
```

`netdryrun.runner.x_preflight__mutmut_15`: survived (accepted, message-text: message text only: the node list in the unknown-node error; the same exception is raised); diff fingerprint `5740501902a700c3`

```diff
# netdryrun.runner.x_preflight__mutmut_15: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -9,7 +9,7 @@
         | {f.node for sc in config.scenarios for f in sc.faults} | set(config.setup)
     unknown = sorted(wanted - set(lab.nodes))
     if unknown:
-        raise LabError(f"unknown node(s) {', '.join(unknown)}; the topology has {', '.join(lab.nodes)}")
+        raise LabError(f"unknown node(s) {', '.join(unknown)}; the topology has {'XX, XX'.join(lab.nodes)}")
     all_checks = config.checks + [c for sc in config.scenarios for c in sc.checks]
     if full:
         for node in sorted({c.node for c in all_checks} - set(config.drivers)):
```

`netdryrun.runner.x_preflight__mutmut_40`: survived (accepted, message-text: message text only: the inject_routes error text; the same exception is raised); diff fingerprint `1a33a9fb709914ea`

```diff
# netdryrun.runner.x_preflight__mutmut_40: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
         driver = config.drivers.get(f.node) or detect(lab.nodes[f.node])
         if driver != "frr":
             raise LabError(f"inject_routes on {f.node} ({driver}) is not supported yet: it needs an FRR node; "
-                           "inject the routes from an FRR neighbor instead")
+                           "XXinject the routes from an FRR neighbor insteadXX")
     if full:
         for f in (f for sc in config.scenarios for f in sc.faults if f.kind != "inject_routes"):
             lab._require_linux_links(f.node)
```

`netdryrun.runner.x_preflight__mutmut_41`: survived (accepted, message-text: message text only: the inject_routes error text; the same exception is raised); diff fingerprint `a34a2635436928eb`

```diff
# netdryrun.runner.x_preflight__mutmut_41: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
         driver = config.drivers.get(f.node) or detect(lab.nodes[f.node])
         if driver != "frr":
             raise LabError(f"inject_routes on {f.node} ({driver}) is not supported yet: it needs an FRR node; "
-                           "inject the routes from an FRR neighbor instead")
+                           "inject the routes from an frr neighbor instead")
     if full:
         for f in (f for sc in config.scenarios for f in sc.faults if f.kind != "inject_routes"):
             lab._require_linux_links(f.node)
```

`netdryrun.runner.x_preflight__mutmut_42`: survived (accepted, message-text: message text only: the inject_routes error text; the same exception is raised); diff fingerprint `eb990851dcb9cf63`

```diff
# netdryrun.runner.x_preflight__mutmut_42: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -20,7 +20,7 @@
         driver = config.drivers.get(f.node) or detect(lab.nodes[f.node])
         if driver != "frr":
             raise LabError(f"inject_routes on {f.node} ({driver}) is not supported yet: it needs an FRR node; "
-                           "inject the routes from an FRR neighbor instead")
+                           "INJECT THE ROUTES FROM AN FRR NEIGHBOR INSTEAD")
     if full:
         for f in (f for sc in config.scenarios for f in sc.faults if f.kind != "inject_routes"):
             lab._require_linux_links(f.node)
```

## `checks._evaluate_all` (4)

`netdryrun.checks.x__evaluate_all__mutmut_1`: survived (accepted, equivalent: equivalent: thread pool size; every check is still evaluated once and results keep input order); diff fingerprint `30e1f75d61ee9e5f`

```diff
# netdryrun.checks.x__evaluate_all__mutmut_1: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,4 +1,4 @@
-def _evaluate_all(checks: list[Check], drivers: dict, workers: int = 8) -> list[tuple]:
+def _evaluate_all(checks: list[Check], drivers: dict, workers: int = 9) -> list[tuple]:
     """One sample of every check, run concurrently (each is a docker exec), results in input order."""
     if len(checks) <= 1:
         return [_evaluate(c, drivers[c.node]) for c in checks]
```

`netdryrun.checks.x__evaluate_all__mutmut_2`: survived (accepted, equivalent: equivalent: one check evaluated through the pool instead of inline; same result); diff fingerprint `9a065e9a590d43a1`

```diff
# netdryrun.checks.x__evaluate_all__mutmut_2: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,6 +1,6 @@
 def _evaluate_all(checks: list[Check], drivers: dict, workers: int = 8) -> list[tuple]:
     """One sample of every check, run concurrently (each is a docker exec), results in input order."""
-    if len(checks) <= 1:
+    if len(checks) < 1:
         return [_evaluate(c, drivers[c.node]) for c in checks]
     with ThreadPoolExecutor(max_workers=min(workers, len(checks))) as pool:
         return list(pool.map(lambda c: _evaluate(c, drivers[c.node]), checks))
```

`netdryrun.checks.x__evaluate_all__mutmut_3`: survived (accepted, equivalent: equivalent: two checks evaluated inline instead of through the pool; same results, same order); diff fingerprint `f5599358fc010b5c`

```diff
# netdryrun.checks.x__evaluate_all__mutmut_3: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,6 +1,6 @@
 def _evaluate_all(checks: list[Check], drivers: dict, workers: int = 8) -> list[tuple]:
     """One sample of every check, run concurrently (each is a docker exec), results in input order."""
-    if len(checks) <= 1:
+    if len(checks) <= 2:
         return [_evaluate(c, drivers[c.node]) for c in checks]
     with ThreadPoolExecutor(max_workers=min(workers, len(checks))) as pool:
         return list(pool.map(lambda c: _evaluate(c, drivers[c.node]), checks))
```

`netdryrun.checks.x__evaluate_all__mutmut_8`: survived (accepted, equivalent: equivalent: thread pool size; every check is still evaluated once and results keep input order); diff fingerprint `81e46835f29009ac`

```diff
# netdryrun.checks.x__evaluate_all__mutmut_8: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -2,5 +2,5 @@
     """One sample of every check, run concurrently (each is a docker exec), results in input order."""
     if len(checks) <= 1:
         return [_evaluate(c, drivers[c.node]) for c in checks]
-    with ThreadPoolExecutor(max_workers=min(workers, len(checks))) as pool:
+    with ThreadPoolExecutor(max_workers=None) as pool:
         return list(pool.map(lambda c: _evaluate(c, drivers[c.node]), checks))
```

## `drivers.eos._json` (4)

`netdryrun.drivers.eos.x__json__mutmut_10`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `b28984661e329cdc`

```diff
# netdryrun.drivers.eos.x__json__mutmut_10: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,7 +1,7 @@
 def _json(command: str, text: str) -> dict:
     data = load_json(command, text)
     if isinstance(data, dict) and "errors" in data:
-        raise DriverError(f"EOS error from `{command}`: {data['errors']}")
+        raise DriverError(None)
     if not isinstance(data, dict):
         raise unexpected(command, text)
     return data
```

`netdryrun.drivers.eos.x__json__mutmut_14`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `73e7b937848eff66`

```diff
# netdryrun.drivers.eos.x__json__mutmut_14: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,5 +3,5 @@
     if isinstance(data, dict) and "errors" in data:
         raise DriverError(f"EOS error from `{command}`: {data['errors']}")
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(None, text)
     return data
```

`netdryrun.drivers.eos.x__json__mutmut_15`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `b9c986b9de7a7361`

```diff
# netdryrun.drivers.eos.x__json__mutmut_15: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -3,5 +3,5 @@
     if isinstance(data, dict) and "errors" in data:
         raise DriverError(f"EOS error from `{command}`: {data['errors']}")
     if not isinstance(data, dict):
-        raise unexpected(command, text)
+        raise unexpected(command, None)
     return data
```

`netdryrun.drivers.eos.x__json__mutmut_2`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `34ba1bda56bc6583`

```diff
# netdryrun.drivers.eos.x__json__mutmut_2: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,5 +1,5 @@
 def _json(command: str, text: str) -> dict:
-    data = load_json(command, text)
+    data = load_json(None, text)
     if isinstance(data, dict) and "errors" in data:
         raise DriverError(f"EOS error from `{command}`: {data['errors']}")
     if not isinstance(data, dict):
```

## `drivers.eos._table` (4)

`netdryrun.drivers.eos.x__table__mutmut_4`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `958eaa7ec28b0e07`

```diff
# netdryrun.drivers.eos.x__table__mutmut_4: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -2,5 +2,5 @@
     """A required map inside a VRF's answer (routes, peers, bgpRouteEntries); `{}` is a real empty one."""
     table = entry.get(key)
     if not isinstance(table, dict):
-        raise unexpected(command, f"no {key!r} map: {str(entry)[:150]}")
+        raise unexpected(None, f"no {key!r} map: {str(entry)[:150]}")
     return table
```

`netdryrun.drivers.eos.x__table__mutmut_5`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `bb7483b4271d2b51`

```diff
# netdryrun.drivers.eos.x__table__mutmut_5: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -2,5 +2,5 @@
     """A required map inside a VRF's answer (routes, peers, bgpRouteEntries); `{}` is a real empty one."""
     table = entry.get(key)
     if not isinstance(table, dict):
-        raise unexpected(command, f"no {key!r} map: {str(entry)[:150]}")
+        raise unexpected(command, None)
     return table
```

`netdryrun.drivers.eos.x__table__mutmut_8`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `181d29ffa881384e`

```diff
# netdryrun.drivers.eos.x__table__mutmut_8: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -2,5 +2,5 @@
     """A required map inside a VRF's answer (routes, peers, bgpRouteEntries); `{}` is a real empty one."""
     table = entry.get(key)
     if not isinstance(table, dict):
-        raise unexpected(command, f"no {key!r} map: {str(entry)[:150]}")
+        raise unexpected(command, f"no {key!r} map: {str(None)[:150]}")
     return table
```

`netdryrun.drivers.eos.x__table__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `db6ac3204953c6d9`

```diff
# netdryrun.drivers.eos.x__table__mutmut_9: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -2,5 +2,5 @@
     """A required map inside a VRF's answer (routes, peers, bgpRouteEntries); `{}` is a real empty one."""
     table = entry.get(key)
     if not isinstance(table, dict):
-        raise unexpected(command, f"no {key!r} map: {str(entry)[:150]}")
+        raise unexpected(command, f"no {key!r} map: {str(entry)[:151]}")
     return table
```

## `drivers.frr.FrrDriver._confirm_vrf` (4)

`netdryrun.drivers.frr.xǁFrrDriverǁ_confirm_vrf__mutmut_12`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `469e6af154216306`

```diff
# netdryrun.drivers.frr.xǁFrrDriverǁ_confirm_vrf__mutmut_12: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -6,6 +6,6 @@
     vrfs = parse_vrfs(self._vtysh(VRF_CMD, evidence))
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} does not exist on {self.node} "
-                          f"(`show vrf` lists: {', '.join(sorted(vrfs)) or 'none'})")
+                          f"(`show vrf` lists: {', '.join(sorted(vrfs)) and 'none'})")
     if not vrfs[vrf]:
         raise NoSuchInstance(f"VRF {vrf!r} is configured on {self.node} but inactive (no kernel VRF device)")
```

`netdryrun.drivers.frr.xǁFrrDriverǁ_confirm_vrf__mutmut_14`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `8fd8cb6ad10042f5`

```diff
# netdryrun.drivers.frr.xǁFrrDriverǁ_confirm_vrf__mutmut_14: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -6,6 +6,6 @@
     vrfs = parse_vrfs(self._vtysh(VRF_CMD, evidence))
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} does not exist on {self.node} "
-                          f"(`show vrf` lists: {', '.join(sorted(vrfs)) or 'none'})")
+                          f"(`show vrf` lists: {'XX, XX'.join(sorted(vrfs)) or 'none'})")
     if not vrfs[vrf]:
         raise NoSuchInstance(f"VRF {vrf!r} is configured on {self.node} but inactive (no kernel VRF device)")
```

`netdryrun.drivers.frr.xǁFrrDriverǁ_confirm_vrf__mutmut_16`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `ce67a4bedd07e98d`

```diff
# netdryrun.drivers.frr.xǁFrrDriverǁ_confirm_vrf__mutmut_16: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -6,6 +6,6 @@
     vrfs = parse_vrfs(self._vtysh(VRF_CMD, evidence))
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} does not exist on {self.node} "
-                          f"(`show vrf` lists: {', '.join(sorted(vrfs)) or 'none'})")
+                          f"(`show vrf` lists: {', '.join(sorted(vrfs)) or 'XXnoneXX'})")
     if not vrfs[vrf]:
         raise NoSuchInstance(f"VRF {vrf!r} is configured on {self.node} but inactive (no kernel VRF device)")
```

`netdryrun.drivers.frr.xǁFrrDriverǁ_confirm_vrf__mutmut_17`: survived (accepted, message-text: message text only: the text of the NoSuchInstance raised either way); diff fingerprint `55fac487bcc84d9b`

```diff
# netdryrun.drivers.frr.xǁFrrDriverǁ_confirm_vrf__mutmut_17: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -6,6 +6,6 @@
     vrfs = parse_vrfs(self._vtysh(VRF_CMD, evidence))
     if vrf not in vrfs:
         raise NoSuchInstance(f"VRF {vrf!r} does not exist on {self.node} "
-                          f"(`show vrf` lists: {', '.join(sorted(vrfs)) or 'none'})")
+                          f"(`show vrf` lists: {', '.join(sorted(vrfs)) or 'NONE'})")
     if not vrfs[vrf]:
         raise NoSuchInstance(f"VRF {vrf!r} is configured on {self.node} but inactive (no kernel VRF device)")
```

## `checks.run_round_robin` (3)

`netdryrun.checks.x_run_round_robin__mutmut_71`: survived (accepted, equivalent: equivalent: unreachable branch: the round-robin timeout only ends a check on a failing sample, so a finished check is never 'not passed but ok'); argument: Same behaviour on every input the function can receive: unreachable branch: the round-robin timeout only ends a check on a failing sample, so a finished check is never 'not passed but ok'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `cf30660ae75c2c65`

```diff
# netdryrun.checks.x_run_round_robin__mutmut_71: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -23,7 +23,7 @@
                 continue
             passed = st["streak"] >= confirm
             if not passed and ok:
-                detail = f"{detail}, but not stable ({st['streak']}/{confirm} consecutive passes)"
+                detail = None
             elif not passed and any(h["passed"] for h in st["history"]):
                 detail = f"{detail} (flapping: passed {sum(h['passed'] for h in st['history'])} of {len(st['history'])} samples)"
             done[id(c)] = Result(c, passed, detail, len(st["history"]), round(elapsed, 1), started, evidence,
```

`netdryrun.checks.x_run_round_robin__mutmut_72`: survived (accepted, equivalent: equivalent: unreachable branch: the round-robin timeout only ends a check on a failing sample, so a finished check is never 'not passed but ok'); argument: Same behaviour on every input the function can receive: unreachable branch: the round-robin timeout only ends a check on a failing sample, so a finished check is never 'not passed but ok'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 3: confirmed after the code trace (research/model-reviews/release-0.3.3/adversarial-round3); diff fingerprint `97ef2442d40cba83`

```diff
# netdryrun.checks.x_run_round_robin__mutmut_72: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -23,7 +23,7 @@
                 continue
             passed = st["streak"] >= confirm
             if not passed and ok:
-                detail = f"{detail}, but not stable ({st['streak']}/{confirm} consecutive passes)"
+                detail = f"{detail}, but not stable ({st['XXstreakXX']}/{confirm} consecutive passes)"
             elif not passed and any(h["passed"] for h in st["history"]):
                 detail = f"{detail} (flapping: passed {sum(h['passed'] for h in st['history'])} of {len(st['history'])} samples)"
             done[id(c)] = Result(c, passed, detail, len(st["history"]), round(elapsed, 1), started, evidence,
```

`netdryrun.checks.x_run_round_robin__mutmut_73`: survived (accepted, equivalent: equivalent: unreachable branch: the round-robin timeout only ends a check on a failing sample, so a finished check is never 'not passed but ok'); argument: Same behaviour on every input the function can receive: unreachable branch: the round-robin timeout only ends a check on a failing sample, so a finished check is never 'not passed but ok'. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 3: confirmed after the code trace (research/model-reviews/release-0.3.3/adversarial-round3); diff fingerprint `88dc0d8ad998e1b9`

```diff
# netdryrun.checks.x_run_round_robin__mutmut_73: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -23,7 +23,7 @@
                 continue
             passed = st["streak"] >= confirm
             if not passed and ok:
-                detail = f"{detail}, but not stable ({st['streak']}/{confirm} consecutive passes)"
+                detail = f"{detail}, but not stable ({st['STREAK']}/{confirm} consecutive passes)"
             elif not passed and any(h["passed"] for h in st["history"]):
                 detail = f"{detail} (flapping: passed {sum(h['passed'] for h in st['history'])} of {len(st['history'])} samples)"
             done[id(c)] = Result(c, passed, detail, len(st["history"]), round(elapsed, 1), started, evidence,
```

## `config.Fault.describe` (3)

`netdryrun.config.xǁFaultǁdescribe__mutmut_4`: survived (accepted, message-text: message text only: the default scenario name built from the faults); diff fingerprint `4d4d70e78cb721e7`

```diff
# netdryrun.config.xǁFaultǁdescribe__mutmut_4: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,4 +1,4 @@
 def describe(self) -> str:
     if self.kind == "inject_routes":
         return f"{self.node} injects {len(self.prefixes)} route(s)"
-    return f"{self.node} {self.interface} down" if self.kind == "link_down" else f"{self.node} isolated"
+    return f"{self.node} {self.interface} down" if (self.kind == "link_down") and False else f"{self.node} isolated"
```

`netdryrun.config.xǁFaultǁdescribe__mutmut_7`: survived (accepted, message-text: message text only: the default scenario name built from the faults); diff fingerprint `309956f4b36296cd`

```diff
# netdryrun.config.xǁFaultǁdescribe__mutmut_7: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,4 +1,4 @@
 def describe(self) -> str:
     if self.kind == "inject_routes":
         return f"{self.node} injects {len(self.prefixes)} route(s)"
-    return f"{self.node} {self.interface} down" if self.kind == "link_down" else f"{self.node} isolated"
+    return f"{self.node} {self.interface} down" if self.kind == "XXlink_downXX" else f"{self.node} isolated"
```

`netdryrun.config.xǁFaultǁdescribe__mutmut_8`: survived (accepted, message-text: message text only: the default scenario name built from the faults); diff fingerprint `1677e5aee66a4236`

```diff
# netdryrun.config.xǁFaultǁdescribe__mutmut_8: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,4 +1,4 @@
 def describe(self) -> str:
     if self.kind == "inject_routes":
         return f"{self.node} injects {len(self.prefixes)} route(s)"
-    return f"{self.node} {self.interface} down" if self.kind == "link_down" else f"{self.node} isolated"
+    return f"{self.node} {self.interface} down" if self.kind == "LINK_DOWN" else f"{self.node} isolated"
```

## `config.normalize_as_path` (3)

`netdryrun.config.x_normalize_as_path__mutmut_1`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `4c7a7dfdd213ec97`

```diff
# netdryrun.config.x_normalize_as_path__mutmut_1: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def normalize_as_path(value: Any) -> str:
     """An AS path as space-separated ASNs; AS sets as {a,b}. "" is the empty path (a locally originated route)."""
     if isinstance(value, bool):
-        raise ValueError("as_path must be a string such as '65002 65003'")
+        raise ValueError(None)
     if isinstance(value, int):
         return str(value)
     if isinstance(value, list):
```

`netdryrun.config.x_normalize_as_path__mutmut_2`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `0c641cac069061ce`

```diff
# netdryrun.config.x_normalize_as_path__mutmut_2: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def normalize_as_path(value: Any) -> str:
     """An AS path as space-separated ASNs; AS sets as {a,b}. "" is the empty path (a locally originated route)."""
     if isinstance(value, bool):
-        raise ValueError("as_path must be a string such as '65002 65003'")
+        raise ValueError("XXas_path must be a string such as '65002 65003'XX")
     if isinstance(value, int):
         return str(value)
     if isinstance(value, list):
```

`netdryrun.config.x_normalize_as_path__mutmut_3`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `e13fb204c30bf21d`

```diff
# netdryrun.config.x_normalize_as_path__mutmut_3: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -1,7 +1,7 @@
 def normalize_as_path(value: Any) -> str:
     """An AS path as space-separated ASNs; AS sets as {a,b}. "" is the empty path (a locally originated route)."""
     if isinstance(value, bool):
-        raise ValueError("as_path must be a string such as '65002 65003'")
+        raise ValueError("AS_PATH MUST BE A STRING SUCH AS '65002 65003'")
     if isinstance(value, int):
         return str(value)
     if isinstance(value, list):
```

## `drivers.base.Driver.all_routes` (3)

`netdryrun.drivers.base.xǁDriverǁall_routes__mutmut_1`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `ad9ef2abf022df26`

```diff
# netdryrun.drivers.base.xǁDriverǁall_routes__mutmut_1: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,3 +1,3 @@
-def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
+def all_routes(self, vrf: str = "XXdefaultXX", family: int = 4) -> Observation:
     """Every route in the table (used by `netdryrun record`)."""
     raise NotImplementedError
```

`netdryrun.drivers.base.xǁDriverǁall_routes__mutmut_2`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `b40a321059f2c012`

```diff
# netdryrun.drivers.base.xǁDriverǁall_routes__mutmut_2: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,3 +1,3 @@
-def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
+def all_routes(self, vrf: str = "DEFAULT", family: int = 4) -> Observation:
     """Every route in the table (used by `netdryrun record`)."""
     raise NotImplementedError
```

`netdryrun.drivers.base.xǁDriverǁall_routes__mutmut_3`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `679c76ae7178beb9`

```diff
# netdryrun.drivers.base.xǁDriverǁall_routes__mutmut_3: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,3 +1,3 @@
-def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
+def all_routes(self, vrf: str = "default", family: int = 5) -> Observation:
     """Every route in the table (used by `netdryrun record`)."""
     raise NotImplementedError
```

## `drivers.check_supported` (3)

`netdryrun.drivers.x_check_supported__mutmut_34`: survived (accepted, message-text: message text only: the unsupported-afi error text; the same exception is raised); diff fingerprint `bdd097102fce75ed`

```diff
# netdryrun.drivers.x_check_supported__mutmut_34: survived
--- src/netdryrun/drivers/__init__.py
+++ src/netdryrun/drivers/__init__.py
@@ -9,7 +9,7 @@
         if afi in getattr(DRIVERS.get(name), "unsupported_afis", ()):
             # the count would read as 0, which passes max and exact: refuse instead
             raise DriverError(f"{check.name}: afi {afi} is not supported on {name} (the {name} driver reads "
-                              "ipv4-unicast and ipv6-unicast prefix counts only)")
+                              "XXipv4-unicast and ipv6-unicast prefix counts only)XX")
         return
     cls = DRIVERS.get(name)
     keys = sorted(set(check.params) & set(cls.unsupported_bgp_attributes)) if cls else []
```

`netdryrun.drivers.x_check_supported__mutmut_35`: survived (accepted, message-text: message text only: the unsupported-afi error text; the same exception is raised); diff fingerprint `e200d1732c7222f9`

```diff
# netdryrun.drivers.x_check_supported__mutmut_35: survived
--- src/netdryrun/drivers/__init__.py
+++ src/netdryrun/drivers/__init__.py
@@ -9,7 +9,7 @@
         if afi in getattr(DRIVERS.get(name), "unsupported_afis", ()):
             # the count would read as 0, which passes max and exact: refuse instead
             raise DriverError(f"{check.name}: afi {afi} is not supported on {name} (the {name} driver reads "
-                              "ipv4-unicast and ipv6-unicast prefix counts only)")
+                              "IPV4-UNICAST AND IPV6-UNICAST PREFIX COUNTS ONLY)")
         return
     cls = DRIVERS.get(name)
     keys = sorted(set(check.params) & set(cls.unsupported_bgp_attributes)) if cls else []
```

`netdryrun.drivers.x_check_supported__mutmut_47`: survived (accepted, message-text: message text only: the key list in the unsupported-key error; the same exception is raised); diff fingerprint `180f0ddfb2212dd0`

```diff
# netdryrun.drivers.x_check_supported__mutmut_47: survived
--- src/netdryrun/drivers/__init__.py
+++ src/netdryrun/drivers/__init__.py
@@ -14,4 +14,4 @@
     cls = DRIVERS.get(name)
     keys = sorted(set(check.params) & set(cls.unsupported_bgp_attributes)) if cls else []
     if keys:
-        raise DriverError(f"{check.name}: {', '.join(keys)} is not supported on {name}")
+        raise DriverError(f"{check.name}: {'XX, XX'.join(keys)} is not supported on {name}")
```

## `drivers.for_node` (3)

`netdryrun.drivers.x_for_node__mutmut_2`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `d47d65c7450291d1`

```diff
# netdryrun.drivers.x_for_node__mutmut_2: survived
--- src/netdryrun/drivers/__init__.py
+++ src/netdryrun/drivers/__init__.py
@@ -1,6 +1,6 @@
 def for_node(lab: Lab, node: str, override: str | None = None) -> Driver:
     if node not in lab.nodes:
-        raise DriverError(f"node {node!r} is not in the topology (nodes: {', '.join(lab.nodes)})")
+        raise DriverError(None)
     name = override or detect(lab.nodes[node])
     if name not in DRIVERS:
         raise DriverError(f"unknown driver {name!r} for node {node}; expected one of {sorted(DRIVERS)}")
```

`netdryrun.drivers.x_for_node__mutmut_4`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `acd403462d346b59`

```diff
# netdryrun.drivers.x_for_node__mutmut_4: survived
--- src/netdryrun/drivers/__init__.py
+++ src/netdryrun/drivers/__init__.py
@@ -1,6 +1,6 @@
 def for_node(lab: Lab, node: str, override: str | None = None) -> Driver:
     if node not in lab.nodes:
-        raise DriverError(f"node {node!r} is not in the topology (nodes: {', '.join(lab.nodes)})")
+        raise DriverError(f"node {node!r} is not in the topology (nodes: {'XX, XX'.join(lab.nodes)})")
     name = override or detect(lab.nodes[node])
     if name not in DRIVERS:
         raise DriverError(f"unknown driver {name!r} for node {node}; expected one of {sorted(DRIVERS)}")
```

`netdryrun.drivers.x_for_node__mutmut_9`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `96d459bdaec6901f`

```diff
# netdryrun.drivers.x_for_node__mutmut_9: survived
--- src/netdryrun/drivers/__init__.py
+++ src/netdryrun/drivers/__init__.py
@@ -3,5 +3,5 @@
         raise DriverError(f"node {node!r} is not in the topology (nodes: {', '.join(lab.nodes)})")
     name = override or detect(lab.nodes[node])
     if name not in DRIVERS:
-        raise DriverError(f"unknown driver {name!r} for node {node}; expected one of {sorted(DRIVERS)}")
+        raise DriverError(None)
     return DRIVERS[name](lab, node)
```

## `checks._reach_view` (2)

`netdryrun.checks.x__reach_view__mutmut_15`: survived (accepted, equivalent: equivalent: min is assigned again on the next line (params['min'] = low), so not dropping the old one changes nothing); argument: Same behaviour on every input the function can receive: min is assigned again on the next line (params['min'] = low), so not dropping the old one changes nothing. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `54855ee173e29caa`

```diff
# netdryrun.checks.x__reach_view__mutmut_15: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -8,6 +8,6 @@
     low = p.get("exact", p.get("min"))
     if not low:
         return None
-    params = {k: v for k, v in p.items() if k not in ("min", "max", "exact")}
+    params = {k: v for k, v in p.items() if k not in ("XXminXX", "max", "exact")}
     params["min"] = low
     return replace(c, params=params, timeout=min(c.timeout, REACH_WINDOW))
```

`netdryrun.checks.x__reach_view__mutmut_16`: survived (accepted, equivalent: equivalent: min is assigned again on the next line (params['min'] = low), so not dropping the old one changes nothing); argument: Same behaviour on every input the function can receive: min is assigned again on the next line (params['min'] = low), so not dropping the old one changes nothing. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `66246b8f75b3189d`

```diff
# netdryrun.checks.x__reach_view__mutmut_16: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -8,6 +8,6 @@
     low = p.get("exact", p.get("min"))
     if not low:
         return None
-    params = {k: v for k, v in p.items() if k not in ("min", "max", "exact")}
+    params = {k: v for k, v in p.items() if k not in ("MIN", "max", "exact")}
     params["min"] = low
     return replace(c, params=params, timeout=min(c.timeout, REACH_WINDOW))
```

## `checks.inconclusive_reason` (2)

`netdryrun.checks.x_inconclusive_reason__mutmut_21`: survived (accepted, message-text: message text only: the text of a detail or error message); argument: Changes only text: the text of a detail or error message. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `5de5f52b5490290e`

```diff
# netdryrun.checks.x_inconclusive_reason__mutmut_21: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -24,6 +24,6 @@
     if not all(r.check.node in never_ready for r in failed):
         return None
     nodes = sorted({r.check.node for r in failed})
-    why = "; ".join(f"{n}: {never_ready[n]}" for n in nodes)
+    why = "XX; XX".join(f"{n}: {never_ready[n]}" for n in nodes)
     return (f"the lab did not reach a testable state: {', '.join(nodes)} never returned usable BGP state "
             f"({why}), and no check passed on any sample. Rerun with a longer timeout, or check that the lab boots")
```

`netdryrun.checks.x_inconclusive_reason__mutmut_23`: survived (accepted, message-text: message text only: the node list in the inconclusive reason); argument: Changes only text: the node list in the inconclusive reason. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `098155857408edf8`

```diff
# netdryrun.checks.x_inconclusive_reason__mutmut_23: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -25,5 +25,5 @@
         return None
     nodes = sorted({r.check.node for r in failed})
     why = "; ".join(f"{n}: {never_ready[n]}" for n in nodes)
-    return (f"the lab did not reach a testable state: {', '.join(nodes)} never returned usable BGP state "
+    return (f"the lab did not reach a testable state: {'XX, XX'.join(nodes)} never returned usable BGP state "
             f"({why}), and no check passed on any sample. Rerun with a longer timeout, or check that the lab boots")
```

## `config._validate_nodes` (2)

`netdryrun.config.x__validate_nodes__mutmut_17`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `638ef379d4a68d28`

```diff
# netdryrun.config.x__validate_nodes__mutmut_17: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -9,7 +9,7 @@
     for k, v in nodes_cfg.items():
         node_where = f"{where}: nodes.{k}"
         if not isinstance(k, str) or not k.strip():
-            raise ConfigError(f"{node_where}: node names must be strings")
+            raise ConfigError(None)
         if not isinstance(v, dict) or not v:
             raise ConfigError(f"{node_where}: must be a mapping with driver and/or setup, got {v!r}")
         _reject_unknown(node_where, v, NODE_KEYS)
```

`netdryrun.config.x__validate_nodes__mutmut_44`: survived (accepted, message-text: message text only: part of an error or detail message string); diff fingerprint `ba3931053d4f948b`

```diff
# netdryrun.config.x__validate_nodes__mutmut_44: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -16,7 +16,7 @@
         if "driver" in v:
             if v["driver"] not in DRIVER_NAMES:
                 raise ConfigError(f"{node_where}.driver: unknown driver {v['driver']!r}"
-                                  f"{_suggest(v['driver'], DRIVER_NAMES)}; use one of {', '.join(DRIVER_NAMES)}")
+                                  f"{_suggest(v['driver'], DRIVER_NAMES)}; use one of {'XX, XX'.join(DRIVER_NAMES)}")
             drivers[k] = v["driver"]
         if "setup" in v:
             cmds = v["setup"] if isinstance(v["setup"], list) else [v["setup"]]
```

## `drivers.base.Driver.bgp_neighbors` (2)

`netdryrun.drivers.base.xǁDriverǁbgp_neighbors__mutmut_1`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `6e942bf8e1424cf9`

```diff
# netdryrun.drivers.base.xǁDriverǁbgp_neighbors__mutmut_1: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,2 +1,2 @@
-def bgp_neighbors(self, vrf: str = "default") -> Observation:
+def bgp_neighbors(self, vrf: str = "XXdefaultXX") -> Observation:
     raise NotImplementedError
```

`netdryrun.drivers.base.xǁDriverǁbgp_neighbors__mutmut_2`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `c26c7c2807e89202`

```diff
# netdryrun.drivers.base.xǁDriverǁbgp_neighbors__mutmut_2: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,2 +1,2 @@
-def bgp_neighbors(self, vrf: str = "default") -> Observation:
+def bgp_neighbors(self, vrf: str = "DEFAULT") -> Observation:
     raise NotImplementedError
```

## `drivers.base.Driver.bgp_paths` (2)

`netdryrun.drivers.base.xǁDriverǁbgp_paths__mutmut_1`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `776c1657b3950962`

```diff
# netdryrun.drivers.base.xǁDriverǁbgp_paths__mutmut_1: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,3 +1,3 @@
-def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
+def bgp_paths(self, prefix: str, vrf: str = "XXdefaultXX") -> Observation:
     """Every path for exactly `prefix` in the BGP table (list[BgpPath]), best path flagged."""
     raise NotImplementedError
```

`netdryrun.drivers.base.xǁDriverǁbgp_paths__mutmut_2`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `bd8a7d5890fc4a72`

```diff
# netdryrun.drivers.base.xǁDriverǁbgp_paths__mutmut_2: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,3 +1,3 @@
-def bgp_paths(self, prefix: str, vrf: str = "default") -> Observation:
+def bgp_paths(self, prefix: str, vrf: str = "DEFAULT") -> Observation:
     """Every path for exactly `prefix` in the BGP table (list[BgpPath]), best path flagged."""
     raise NotImplementedError
```

## `drivers.base.Driver.ping` (2)

`netdryrun.drivers.base.xǁDriverǁping__mutmut_1`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `f9d238998e6c2f11`

```diff
# netdryrun.drivers.base.xǁDriverǁping__mutmut_1: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,2 +1,2 @@
-def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
+def ping(self, target: str, source: str | None, count: int, vrf: str = "XXdefaultXX") -> Observation:
     raise NotImplementedError
```

`netdryrun.drivers.base.xǁDriverǁping__mutmut_2`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `2478a27511284922`

```diff
# netdryrun.drivers.base.xǁDriverǁping__mutmut_2: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,2 +1,2 @@
-def ping(self, target: str, source: str | None, count: int, vrf: str = "default") -> Observation:
+def ping(self, target: str, source: str | None, count: int, vrf: str = "DEFAULT") -> Observation:
     raise NotImplementedError
```

## `drivers.base.Driver.routes` (2)

`netdryrun.drivers.base.xǁDriverǁroutes__mutmut_1`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `ed45c173dbf42783`

```diff
# netdryrun.drivers.base.xǁDriverǁroutes__mutmut_1: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,2 +1,2 @@
-def routes(self, prefix: str, vrf: str = "default") -> Observation:
+def routes(self, prefix: str, vrf: str = "XXdefaultXX") -> Observation:
     raise NotImplementedError
```

`netdryrun.drivers.base.xǁDriverǁroutes__mutmut_2`: survived (accepted, equivalent: equivalent: default argument of an abstract base-class method that only raises NotImplementedError); diff fingerprint `dca49e257c250c95`

```diff
# netdryrun.drivers.base.xǁDriverǁroutes__mutmut_2: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,2 +1,2 @@
-def routes(self, prefix: str, vrf: str = "default") -> Observation:
+def routes(self, prefix: str, vrf: str = "DEFAULT") -> Observation:
     raise NotImplementedError
```

## `drivers.base.check_vrf_name` (2)

`netdryrun.drivers.base.x_check_vrf_name__mutmut_6`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `ef55333e2827e4a0`

```diff
# netdryrun.drivers.base.x_check_vrf_name__mutmut_6: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,7 +1,7 @@
 def check_vrf_name(vrf: object) -> str:
     """The VRF name if a driver can ask for exactly that one VRF; DriverError otherwise."""
     if not isinstance(vrf, str) or not _VRF_NAME.fullmatch(vrf):
-        raise DriverError(f"bad VRF name {str(vrf)[:70]!r}: use letters, digits and . _ : - (at most 64)")
+        raise DriverError(f"bad VRF name {str(None)[:70]!r}: use letters, digits and . _ : - (at most 64)")
     if vrf.lower() in SPECIAL_VRF_NAMES:
         raise DriverError(f"VRF {vrf!r} means every VRF on the device, not one VRF; name the VRF to check")
     return vrf
```

`netdryrun.drivers.base.x_check_vrf_name__mutmut_7`: survived (accepted, message-text: message text only: the same exception is still raised, only its message changes); diff fingerprint `62658c245f999e7c`

```diff
# netdryrun.drivers.base.x_check_vrf_name__mutmut_7: survived
--- src/netdryrun/drivers/base.py
+++ src/netdryrun/drivers/base.py
@@ -1,7 +1,7 @@
 def check_vrf_name(vrf: object) -> str:
     """The VRF name if a driver can ask for exactly that one VRF; DriverError otherwise."""
     if not isinstance(vrf, str) or not _VRF_NAME.fullmatch(vrf):
-        raise DriverError(f"bad VRF name {str(vrf)[:70]!r}: use letters, digits and . _ : - (at most 64)")
+        raise DriverError(f"bad VRF name {str(vrf)[:71]!r}: use letters, digits and . _ : - (at most 64)")
     if vrf.lower() in SPECIAL_VRF_NAMES:
         raise DriverError(f"VRF {vrf!r} means every VRF on the device, not one VRF; name the VRF to check")
     return vrf
```

## `drivers.frr._bgp_paths_for_route_check` (2)

`netdryrun.drivers.frr.x__bgp_paths_for_route_check__mutmut_16`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `b75b25d3e782aff0`

```diff
# netdryrun.drivers.frr.x__bgp_paths_for_route_check__mutmut_16: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -6,4 +6,4 @@
         return []
     if isinstance(data, dict) and isinstance(data.get("warning"), str) and _NO_INSTANCE.search(data["warning"]):
         return []
-    return _bgp_paths_raw(BGP_PATHS_CMD, text, prefix)
+    return _bgp_paths_raw(None, text, prefix)
```

`netdryrun.drivers.frr.x__bgp_paths_for_route_check__mutmut_2`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `4c4930aaf5f9fa46`

```diff
# netdryrun.drivers.frr.x__bgp_paths_for_route_check__mutmut_2: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -1,7 +1,7 @@
 def _bgp_paths_for_route_check(text: str, prefix: str) -> list[dict]:
     """The BGP side of a route check. No BGP instance in the VRF means no BGP paths (the VRF itself is
     confirmed separately); any other warning or shape is an error."""
-    data = load_json(BGP_PATHS_CMD, text)
+    data = load_json(None, text)
     if isinstance(data, dict) and data.get("bgpNoSuchInstance"):
         return []
     if isinstance(data, dict) and isinstance(data.get("warning"), str) and _NO_INSTANCE.search(data["warning"]):
```

## `drivers.frr.parse_config_load_errors` (2)

`netdryrun.drivers.frr.x_parse_config_load_errors__mutmut_67`: survived (accepted, equivalent: equivalent: a vtysh line with no daemon is never cleared, so its stored daemon is never read); argument: The daemon stored here is read only by `explained`, which is reached only when every reported line was cleared. A vtysh line with no daemon (Unknown command, Warning) can't be cleared: clearing needs the daemon among the running configs read, and those are keyed by the daemon names communicate_daemons returns, never None. So `explained` never sees this value and the returned list is the same for every input.; reviewed: adversarial (fresh Opus agent), 2026-10-30: equivalent, no input differs; diff fingerprint `cbd7135846c5d28b`

```diff
# netdryrun.drivers.frr.x_parse_config_load_errors__mutmut_67: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -29,7 +29,7 @@
             done = (daemon in applied and daemon != "mgmtd" and 0 <= i < len(file) and file[i][1] == cmd.strip()
                     and applied[daemon][file[i]] >= in_file[file[i]] and not _is_header(config, i)
                     and _block_applied(config, i, running[daemon]))
-            lines.setdefault((int(n), ""), (done, daemon or "", f"line {n}: {cmd.strip()} ({why})"))
+            lines.setdefault((int(n), ""), (done, daemon or "XXXX", f"line {n}: {cmd.strip()} ({why})"))
             continue
         d = _DAEMON_LINE.match(raw.strip())
         if d:   # the daemon's own file, numbered on its own: kept apart from frr.conf's line N
```

`netdryrun.drivers.frr.x_parse_config_load_errors__mutmut_79`: survived (accepted, equivalent: equivalent: a per-daemon line is never cleared, so its stored daemon is never read); argument: The daemon stored here is read only by `explained`, which is reached only when every reported line was cleared. A per-daemon file line is always stored as not cleared, so when one exists the kept lines are returned first. So `explained` never sees this value and the returned list is the same for every input.; reviewed: adversarial (fresh Opus agent), 2026-10-30: equivalent, no input differs; diff fingerprint `70ef05d8d58c1c69`

```diff
# netdryrun.drivers.frr.x_parse_config_load_errors__mutmut_79: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -35,7 +35,7 @@
         if d:   # the daemon's own file, numbered on its own: kept apart from frr.conf's line N
             daemon, why, n, cmd = d.groups()
             lines.setdefault((int(n), daemon.lower()),
-                             (False, "", f"line {n}: {cmd.strip()} ({why.strip()}, {daemon.lower()})"))
+                             (False, "XXXX", f"line {n}: {cmd.strip()} ({why.strip()}, {daemon.lower()})"))
             continue
         f = _LOAD_FAILURE.match(raw.strip())
         if f:
```

## `drivers.srlinux.parse_instance_state` (2)

`netdryrun.drivers.srlinux.x_parse_instance_state__mutmut_7`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `c6a54b8cac4636ba`

```diff
# netdryrun.drivers.srlinux.x_parse_instance_state__mutmut_7: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,4 +1,4 @@
 def parse_instance_state(text: str) -> str | None:
     """`info from state /network-instance X oper-state`: the oper-state, None when the instance is absent."""
-    state = _find(_json(text, INSTANCE_CMD), "oper-state")
+    state = _find(_json(text, None), "oper-state")
     return state if isinstance(state, str) and state else None
```

`netdryrun.drivers.srlinux.x_parse_instance_state__mutmut_9`: survived (accepted, message-text: message text only: the command name passed only for error messages (and a missing one becomes a TypeError that the parser wrapper turns into the same DriverError)); diff fingerprint `ec5a68db6b855afe`

```diff
# netdryrun.drivers.srlinux.x_parse_instance_state__mutmut_9: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,4 +1,4 @@
 def parse_instance_state(text: str) -> str | None:
     """`info from state /network-instance X oper-state`: the oper-state, None when the instance is absent."""
-    state = _find(_json(text, INSTANCE_CMD), "oper-state")
+    state = _find(_json(text, ), "oper-state")
     return state if isinstance(state, str) and state else None
```

## `checks._not_configured` (1)

`netdryrun.checks.x__not_configured__mutmut_2`: survived (accepted, message-text: message text only: the detail stays an Unready instance, only its text changes); argument: Changes only text: the detail stays an Unready instance, only its text changes. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `f07a5abb19505536`

```diff
# netdryrun.checks.x__not_configured__mutmut_2: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -1,4 +1,4 @@
 def _not_configured(neighbor: str, seen: dict) -> str:
     if not seen:
-        return Unready(f"neighbor {neighbor} not configured (no BGP neighbors at all on this node)")
+        return Unready(None)
     return f"neighbor {neighbor} not configured (seen: {', '.join(seen)})"
```

## `checks.converge_then_hold` (1)

`netdryrun.checks.x_converge_then_hold__mutmut_55`: survived (accepted, equivalent: equivalent: the sum of two durations already rounded to 0.1 s rounds the same to 0.01 s); argument: Same behaviour on every input the function can receive: the sum of two durations already rounded to 0.1 s rounds the same to 0.01 s. So the verdict can't change.; reviewed: adversarial (ChatGPT), round 2: confirmed (research/model-reviews/release-0.3.3/adversarial-round2); diff fingerprint `cf966c70d92a4995`

```diff
# netdryrun.checks.x_converge_then_hold__mutmut_55: survived
--- src/netdryrun/checks.py
+++ src/netdryrun/checks.py
@@ -11,7 +11,7 @@
         return first
     held = hold_check(check, driver, hold=check.hold or hold, interval=interval, clock=clock, sleep=sleep)
     held.started = first.started
-    held.duration = round(first.duration + held.duration, 1)
+    held.duration = round(first.duration + held.duration, 2)
     held.attempts += first.attempts
     held.history = (first.history + held.history)[-50:]
     held.samples_passed += first.samples_passed
```

## `config.parse_community` (1)

`netdryrun.config.x_parse_community__mutmut_35`: survived (accepted, message-text: message text only: part of an error or detail message string); diff fingerprint `8f93f202822e4119`

```diff
# netdryrun.config.x_parse_community__mutmut_35: survived
--- src/netdryrun/config.py
+++ src/netdryrun/config.py
@@ -11,4 +11,4 @@
         if all(n <= limit for n in nums):
             return ":".join(str(n) for n in nums)
     raise ValueError(f"bad community {text!r}: use 65000:100 (standard), 65000:1:2 (large) or a well-known name "
-                     f"({', '.join(sorted(WELL_KNOWN_COMMUNITIES))})")
+                     f"({'XX, XX'.join(sorted(WELL_KNOWN_COMMUNITIES))})")
```

## `drivers.eos.EosDriver.all_routes` (1)

`netdryrun.drivers.eos.xǁEosDriverǁall_routes__mutmut_3`: survived (accepted, equivalent: equivalent: family default 4 vs 5: only family == 6 selects IPv6, every other value reads IPv4); diff fingerprint `1aeb2f2755355f04`

```diff
# netdryrun.drivers.eos.xǁEosDriverǁall_routes__mutmut_3: survived
--- src/netdryrun/drivers/eos.py
+++ src/netdryrun/drivers/eos.py
@@ -1,4 +1,4 @@
-def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
+def all_routes(self, vrf: str = "default", family: int = 5) -> Observation:
     vrf = check_vrf_name(vrf)
     ev: list[dict] = []
     fam = "ipv6" if family == 6 else "ip"
```

## `drivers.frr.FrrDriver.all_routes` (1)

`netdryrun.drivers.frr.xǁFrrDriverǁall_routes__mutmut_3`: survived (accepted, equivalent: equivalent: family default 4 vs 5: only family == 6 selects IPv6, every other value reads IPv4); diff fingerprint `f5868264b0c0342c`

```diff
# netdryrun.drivers.frr.xǁFrrDriverǁall_routes__mutmut_3: survived
--- src/netdryrun/drivers/frr.py
+++ src/netdryrun/drivers/frr.py
@@ -1,4 +1,4 @@
-def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
+def all_routes(self, vrf: str = "default", family: int = 5) -> Observation:
     vrf = check_vrf_name(vrf)
     ev: list[dict] = []
     fam = "ipv6" if family == 6 else "ip"
```

## `drivers.srlinux.SrlDriver.all_routes` (1)

`netdryrun.drivers.srlinux.xǁSrlDriverǁall_routes__mutmut_3`: survived (accepted, equivalent: equivalent: family default 4 vs 5: only family == 6 selects IPv6, every other value reads IPv4); diff fingerprint `2b21f88e9018806f`

```diff
# netdryrun.drivers.srlinux.xǁSrlDriverǁall_routes__mutmut_3: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -1,4 +1,4 @@
-def all_routes(self, vrf: str = "default", family: int = 4) -> Observation:
+def all_routes(self, vrf: str = "default", family: int = 5) -> Observation:
     vrf = check_vrf_name(vrf)
     ev: list[dict] = []
     table, key = ("ipv6-unicast", "ipv6-prefix") if family == 6 else ("ipv4-unicast", "ipv4-prefix")
```

## `drivers.srlinux._bgp_learned` (1)

`netdryrun.drivers.srlinux.x__bgp_learned__mutmut_10`: survived (accepted, equivalent: equivalent: the default origin-protocol is lower-cased before the comparison); diff fingerprint `97bbe3c55120e82f`

```diff
# netdryrun.drivers.srlinux.x__bgp_learned__mutmut_10: survived
--- src/netdryrun/drivers/srlinux.py
+++ src/netdryrun/drivers/srlinux.py
@@ -2,4 +2,4 @@
     """SR Linux lists the router's own static and interface routes in its BGP local-RIB as locally
     originated paths (neighbor 0.0.0.0, origin-protocol static, ...), whether or not an export policy
     advertises them. Only paths with origin-protocol bgp were learned over BGP."""
-    return str(row.get("origin-protocol", "bgp")).lower() == "bgp"
+    return str(row.get("origin-protocol", "BGP")).lower() == "bgp"
```

## `runner._sessions_over_links` (1)

`netdryrun.runner.x__sessions_over_links__mutmut_12`: survived (accepted, message-text: message text only: without log=, _link_sessions logs to its no-op default; only a log line is lost); argument: Changes only text: without log=, _link_sessions logs to its no-op default; only a log line is lost. The result's passed flag, its samples and the run status are computed from the observation, not from this text, so it can't turn a failure into a pass.; reviewed: adversarial (ChatGPT), round 1: checked and agreed (research/model-reviews/release-0.3.3/ndr-0.3.3-adversarial-mutants-*); diff fingerprint `16a2e80dca9f33cf`

```diff
# netdryrun.runner.x__sessions_over_links__mutmut_12: survived
--- src/netdryrun/runner.py
+++ src/netdryrun/runner.py
@@ -2,5 +2,5 @@
                          log=lambda _: None, any_state: bool = False) -> list[tuple[str, str, str]]:
     """The established BGP sessions (node, vrf, neighbor) that run over the given (node, interface) links
     (with any_state, every configured session over them, established or not)."""
-    established, every = _link_sessions(lab, links, vrfs, driver_for, log=log)
+    established, every = _link_sessions(lab, links, vrfs, driver_for, )
     return every if any_state else established
```
