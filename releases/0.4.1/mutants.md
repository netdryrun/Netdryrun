# Surviving mutants, Netdryrun 0.4.1

Each mutant below is a deliberate change to the code that no test noticed. In verdict logic each is a BLOCKER until a test kills it or it is accepted as harmless in accepted.json with a reason.

## `faults.conflicts` (17)

`netdryrun.faults.x_conflicts__mutmut_13`: survived; diff fingerprint `90721534a1a1f4a7`

```diff
# netdryrun.faults.x_conflicts__mutmut_13: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 or w[0] in ("ip", "ipv6") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_14`: survived; diff fingerprint `d5bbc1e4d79c4359`

```diff
# netdryrun.faults.x_conflicts__mutmut_14: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) >= 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_15`: survived; diff fingerprint `723ba193dd7d57ca`

```diff
# netdryrun.faults.x_conflicts__mutmut_15: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 3 and w[0] in ("ip", "ipv6") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_16`: survived; diff fingerprint `663093a2ce56b808`

```diff
# netdryrun.faults.x_conflicts__mutmut_16: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[1] in ("ip", "ipv6") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_17`: survived; diff fingerprint `b4e5be81757123f4`

```diff
# netdryrun.faults.x_conflicts__mutmut_17: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] not in ("ip", "ipv6") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_18`: survived; diff fingerprint `2e8b956e0874df25`

```diff
# netdryrun.faults.x_conflicts__mutmut_18: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] in ("XXipXX", "ipv6") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_19`: survived; diff fingerprint `0eedc2e4e7dd089d`

```diff
# netdryrun.faults.x_conflicts__mutmut_19: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] in ("IP", "ipv6") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_20`: survived; diff fingerprint `a58302d23a642053`

```diff
# netdryrun.faults.x_conflicts__mutmut_20: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] in ("ip", "XXipv6XX") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_21`: survived; diff fingerprint `3e40c7e42e530fb5`

```diff
# netdryrun.faults.x_conflicts__mutmut_21: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] in ("ip", "IPV6") and w[1] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_22`: survived; diff fingerprint `1c87ffb8ae491898`

```diff
# netdryrun.faults.x_conflicts__mutmut_22: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[2] == "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_23`: survived; diff fingerprint `f0086a367122f122`

```diff
# netdryrun.faults.x_conflicts__mutmut_23: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] != "route":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_24`: survived; diff fingerprint `8da9401794ef6074`

```diff
# netdryrun.faults.x_conflicts__mutmut_24: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "XXrouteXX":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_25`: survived; diff fingerprint `bdedc7ebc84411f8`

```diff
# netdryrun.faults.x_conflicts__mutmut_25: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,6 +5,6 @@
         w = line.split()
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
-        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
+        elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "ROUTE":
             taken.add(w[2])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_26`: survived; diff fingerprint `dfe8dadfbecaa958`

```diff
# netdryrun.faults.x_conflicts__mutmut_26: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -6,5 +6,5 @@
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
         elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
-            taken.add(w[2])
+            taken.add(None)
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_27`: survived; diff fingerprint `44c03b4c9b3edb37`

```diff
# netdryrun.faults.x_conflicts__mutmut_27: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -6,5 +6,5 @@
         if w[:1] == ["network"] and len(w) > 1:
             taken.add(w[1])
         elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
-            taken.add(w[2])
+            taken.add(w[3])
     return [p for p in prefixes if p in taken]
```

`netdryrun.faults.x_conflicts__mutmut_3`: survived; diff fingerprint `e37cbe63b7bc3c9a`

```diff
# netdryrun.faults.x_conflicts__mutmut_3: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,7 +3,7 @@
     taken = set()
     for line in running_config.splitlines():
         w = line.split()
-        if w[:1] == ["network"] and len(w) > 1:
+        if w[:1] == ["network"] or len(w) > 1:
             taken.add(w[1])
         elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
             taken.add(w[2])
```

`netdryrun.faults.x_conflicts__mutmut_8`: survived; diff fingerprint `35bbeb305828e60c`

```diff
# netdryrun.faults.x_conflicts__mutmut_8: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,7 +3,7 @@
     taken = set()
     for line in running_config.splitlines():
         w = line.split()
-        if w[:1] == ["network"] and len(w) > 1:
+        if w[:1] == ["network"] and len(w) >= 1:
             taken.add(w[1])
         elif len(w) > 2 and w[0] in ("ip", "ipv6") and w[1] == "route":
             taken.add(w[2])
```

## `faults.RouteInjection._apply_config` (13)

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_12`: survived; diff fingerprint `cbbfef4edfa91a53`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_12: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,6 +1,6 @@
 def _apply_config(self, lines: list[str]) -> None:
     path = "/tmp/netdryrun-inject.conf"
-    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
+    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", )
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
     self._vtysh("-f", path, timeout=300)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_2`: survived; diff fingerprint `27a50455c7eba20d`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_2: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _apply_config(self, lines: list[str]) -> None:
-    path = "/tmp/netdryrun-inject.conf"
+    path = "XX/tmp/netdryrun-inject.confXX"
     r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_20`: survived; diff fingerprint `137260f8543c57d1`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_20: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,6 +1,6 @@
 def _apply_config(self, lines: list[str]) -> None:
     path = "/tmp/netdryrun-inject.conf"
-    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
+    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "XX\nXX", timeout=30)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
     self._vtysh("-f", path, timeout=300)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_21`: survived; diff fingerprint `097c4992a4865a59`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_21: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,6 +1,6 @@
 def _apply_config(self, lines: list[str]) -> None:
     path = "/tmp/netdryrun-inject.conf"
-    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
+    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=31)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
     self._vtysh("-f", path, timeout=300)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_24`: survived; diff fingerprint `fa5fe6269ba88b3f`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_24: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -2,5 +2,5 @@
     path = "/tmp/netdryrun-inject.conf"
     r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
+        raise LabError(None)
     self._vtysh("-f", path, timeout=300)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_25`: survived; diff fingerprint `563fd91ebc175c09`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_25: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -2,5 +2,5 @@
     path = "/tmp/netdryrun-inject.conf"
     r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
+        raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr and r.stdout).strip()}")
     self._vtysh("-f", path, timeout=300)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_28`: survived; diff fingerprint `ee610d6274f4f56e`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_28: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,4 +3,4 @@
     r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
-    self._vtysh("-f", path, timeout=300)
+    self._vtysh("-f", path, timeout=None)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_3`: survived; diff fingerprint `6564a662d9dbdde0`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_3: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _apply_config(self, lines: list[str]) -> None:
-    path = "/tmp/netdryrun-inject.conf"
+    path = "/TMP/NETDRYRUN-INJECT.CONF"
     r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_30`: survived; diff fingerprint `61c8376bfaf11ba3`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_30: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,4 +3,4 @@
     r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
-    self._vtysh("-f", path, timeout=300)
+    self._vtysh("-f", timeout=300)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_31`: survived; diff fingerprint `3a626f171a32907d`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_31: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,4 +3,4 @@
     r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
-    self._vtysh("-f", path, timeout=300)
+    self._vtysh("-f", path, )
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_34`: survived; diff fingerprint `e2e6ae1a450ad102`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_34: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,4 +3,4 @@
     r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
-    self._vtysh("-f", path, timeout=300)
+    self._vtysh("-f", path, timeout=301)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_5`: survived; diff fingerprint `8bc3e5044f28e54a`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_5: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,6 +1,6 @@
 def _apply_config(self, lines: list[str]) -> None:
     path = "/tmp/netdryrun-inject.conf"
-    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
+    r = self.lab.exec(None, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
     self._vtysh("-f", path, timeout=300)
```

`netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_8`: survived; diff fingerprint `0a11ce1b7942a34d`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_apply_config__mutmut_8: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,6 +1,6 @@
 def _apply_config(self, lines: list[str]) -> None:
     path = "/tmp/netdryrun-inject.conf"
-    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=30)
+    r = self.lab.exec(self.node, ["sh", "-c", f"cat > {path}"], input="\n".join(lines) + "\n", timeout=None)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: could not write {path}: {(r.stderr or r.stdout).strip()}")
     self._vtysh("-f", path, timeout=300)
```

## `faults.RouteInjection._vtysh` (11)

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_1`: survived; diff fingerprint `a55a8259856464fc`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_1: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,4 +1,4 @@
-def _vtysh(self, *args: str, timeout: float = 120) -> str:
+def _vtysh(self, *args: str, timeout: float = 121) -> str:
     r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_13`: survived; diff fingerprint `029d7b5fcba532a1`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_13: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
     r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
+        raise LabError(None)
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_14`: survived; diff fingerprint `9bcab2da015201c2`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_14: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
     r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
+        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(None)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_15`: survived; diff fingerprint `cf6989de5ed7f3c2`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_15: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
     r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
+        raise LabError(f"inject_routes on {self.node}: vtysh {'XX XX'.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_16`: survived; diff fingerprint `d08b0ee94e1fbb6b`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_16: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
     r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
+        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:81]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_17`: survived; diff fingerprint `9983224498b181db`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_17: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
     r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
+        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr and r.stdout).strip()[-300:]}")
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_18`: survived; diff fingerprint `2ff682fb9568bf95`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_18: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
     r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
+        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[+300:]}")
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_19`: survived; diff fingerprint `592e49f394d2fc14`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_19: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
     r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
-        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
+        raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-301:]}")
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_3`: survived; diff fingerprint `dc0e18e92bf33d68`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_3: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
-    r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
+    r = self.lab.exec(None, ["vtysh", *args], timeout=timeout)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_5`: survived; diff fingerprint `02f51c4516981178`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_5: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
-    r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
+    r = self.lab.exec(self.node, ["vtysh", *args], timeout=None)
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
     return r.stdout
```

`netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_8`: survived; diff fingerprint `11a5a16a4e457d7c`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_vtysh__mutmut_8: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _vtysh(self, *args: str, timeout: float = 120) -> str:
-    r = self.lab.exec(self.node, ["vtysh", *args], timeout=timeout)
+    r = self.lab.exec(self.node, ["vtysh", *args], )
     if r.rc != 0:
         raise LabError(f"inject_routes on {self.node}: vtysh {' '.join(args)[:80]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
     return r.stdout
```

## `faults.parse_inject` (11)

`netdryrun.faults.x_parse_inject__mutmut_109`: survived; diff fingerprint `5600ade816f2c9d7`

```diff
# netdryrun.faults.x_parse_inject__mutmut_109: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -31,6 +31,6 @@
     as_path = item.get("as_path") or []
     as_path = as_path if isinstance(as_path, list) else [as_path]
     for asn in as_path:
-        if isinstance(asn, bool) or not isinstance(asn, int) or not 1 <= asn <= 4294967295:
+        if isinstance(asn, bool) or not isinstance(asn, int) or not 2 <= asn <= 4294967295:
             raise ValueError(f"{where}: inject_routes as_path must be a list of AS numbers")
     return {"node": str(item["node"]), "prefixes": prefixes, "as_path": [int(a) for a in as_path]}
```

`netdryrun.faults.x_parse_inject__mutmut_110`: survived; diff fingerprint `48c8cb2b2dffac82`

```diff
# netdryrun.faults.x_parse_inject__mutmut_110: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -31,6 +31,6 @@
     as_path = item.get("as_path") or []
     as_path = as_path if isinstance(as_path, list) else [as_path]
     for asn in as_path:
-        if isinstance(asn, bool) or not isinstance(asn, int) or not 1 <= asn <= 4294967295:
+        if isinstance(asn, bool) or not isinstance(asn, int) or not 1 < asn <= 4294967295:
             raise ValueError(f"{where}: inject_routes as_path must be a list of AS numbers")
     return {"node": str(item["node"]), "prefixes": prefixes, "as_path": [int(a) for a in as_path]}
```

`netdryrun.faults.x_parse_inject__mutmut_111`: survived; diff fingerprint `c079da9df535bfc2`

```diff
# netdryrun.faults.x_parse_inject__mutmut_111: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -31,6 +31,6 @@
     as_path = item.get("as_path") or []
     as_path = as_path if isinstance(as_path, list) else [as_path]
     for asn in as_path:
-        if isinstance(asn, bool) or not isinstance(asn, int) or not 1 <= asn <= 4294967295:
+        if isinstance(asn, bool) or not isinstance(asn, int) or not 1 <= asn < 4294967295:
             raise ValueError(f"{where}: inject_routes as_path must be a list of AS numbers")
     return {"node": str(item["node"]), "prefixes": prefixes, "as_path": [int(a) for a in as_path]}
```

`netdryrun.faults.x_parse_inject__mutmut_112`: survived; diff fingerprint `29723abfa9869052`

```diff
# netdryrun.faults.x_parse_inject__mutmut_112: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -31,6 +31,6 @@
     as_path = item.get("as_path") or []
     as_path = as_path if isinstance(as_path, list) else [as_path]
     for asn in as_path:
-        if isinstance(asn, bool) or not isinstance(asn, int) or not 1 <= asn <= 4294967295:
+        if isinstance(asn, bool) or not isinstance(asn, int) or not 1 <= asn <= 4294967296:
             raise ValueError(f"{where}: inject_routes as_path must be a list of AS numbers")
     return {"node": str(item["node"]), "prefixes": prefixes, "as_path": [int(a) for a in as_path]}
```

`netdryrun.faults.x_parse_inject__mutmut_37`: survived; diff fingerprint `281b013eac82bb83`

```diff
# netdryrun.faults.x_parse_inject__mutmut_37: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -11,7 +11,7 @@
     try:
         if "prefixes" in item:
             if "from" in item:
-                raise ValueError("from only goes with count")
+                raise ValueError("XXfrom only goes with countXX")
             raw = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
             if not raw:
                 raise ValueError("prefixes is empty")
```

`netdryrun.faults.x_parse_inject__mutmut_47`: survived; diff fingerprint `3b20ed4481cb58af`

```diff
# netdryrun.faults.x_parse_inject__mutmut_47: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -14,7 +14,7 @@
                 raise ValueError("from only goes with count")
             raw = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
             if not raw:
-                raise ValueError("prefixes is empty")
+                raise ValueError(None)
             nets = [explicit_network("prefixes", p) for p in raw]
         else:
             count = item["count"]
```

`netdryrun.faults.x_parse_inject__mutmut_48`: survived; diff fingerprint `a6e9c9f293f9be89`

```diff
# netdryrun.faults.x_parse_inject__mutmut_48: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -14,7 +14,7 @@
                 raise ValueError("from only goes with count")
             raw = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
             if not raw:
-                raise ValueError("prefixes is empty")
+                raise ValueError("XXprefixes is emptyXX")
             nets = [explicit_network("prefixes", p) for p in raw]
         else:
             count = item["count"]
```

`netdryrun.faults.x_parse_inject__mutmut_49`: survived; diff fingerprint `f8bc51a193835f1d`

```diff
# netdryrun.faults.x_parse_inject__mutmut_49: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -14,7 +14,7 @@
                 raise ValueError("from only goes with count")
             raw = item["prefixes"] if isinstance(item["prefixes"], list) else [item["prefixes"]]
             if not raw:
-                raise ValueError("prefixes is empty")
+                raise ValueError("PREFIXES IS EMPTY")
             nets = [explicit_network("prefixes", p) for p in raw]
         else:
             count = item["count"]
```

`netdryrun.faults.x_parse_inject__mutmut_64`: survived; diff fingerprint `29aef3990c322090`

```diff
# netdryrun.faults.x_parse_inject__mutmut_64: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -18,7 +18,7 @@
             nets = [explicit_network("prefixes", p) for p in raw]
         else:
             count = item["count"]
-            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
+            if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= MAX_COUNT:
                 raise ValueError(f"count must be an integer from 1 to {MAX_COUNT}")
             first = explicit_network("from", item.get("from", DEFAULT_FROM))
             nets = [first]
```

`netdryrun.faults.x_parse_inject__mutmut_65`: survived; diff fingerprint `e9043f165c8ccba0`

```diff
# netdryrun.faults.x_parse_inject__mutmut_65: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -18,7 +18,7 @@
             nets = [explicit_network("prefixes", p) for p in raw]
         else:
             count = item["count"]
-            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
+            if isinstance(count, bool) or not isinstance(count, int) or not 1 < count <= MAX_COUNT:
                 raise ValueError(f"count must be an integer from 1 to {MAX_COUNT}")
             first = explicit_network("from", item.get("from", DEFAULT_FROM))
             nets = [first]
```

`netdryrun.faults.x_parse_inject__mutmut_66`: survived; diff fingerprint `ca4fae978967f41e`

```diff
# netdryrun.faults.x_parse_inject__mutmut_66: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -18,7 +18,7 @@
             nets = [explicit_network("prefixes", p) for p in raw]
         else:
             count = item["count"]
-            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
+            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count < MAX_COUNT:
                 raise ValueError(f"count must be an integer from 1 to {MAX_COUNT}")
             first = explicit_network("from", item.get("from", DEFAULT_FROM))
             nets = [first]
```

## `faults.RouteInjection.__init__` (10)

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_1`: survived; diff fingerprint `fe4aee6ba8362da6`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_1: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,4 +1,4 @@
-def __init__(self, lab: Lab, node: str, prefixes: list[str], as_path: list[int], budget: float = 60):
+def __init__(self, lab: Lab, node: str, prefixes: list[str], as_path: list[int], budget: float = 61):
     self.lab, self.node, self.prefixes, self.as_path, self.budget = lab, node, prefixes, as_path, budget
     self.asn = ""
     self.applied = False   # set before the config goes in: restore even if applying half-fails
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_12`: survived; diff fingerprint `8edb747cd09e22ca`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_12: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -8,6 +8,6 @@
     self.late: set[str] = set()   # established peers not advertised every prefix before the checks ran
     self.listed_before: dict[str, set[str]] = {}   # peer -> injected prefixes it already had an entry for
     # whether the routes left the node: True, False, or None when the advertised routes couldn't be read at restore
-    self.left: bool | None = None
+    self.left: bool | None = ""
     self.quiet: dict[str, list[str]] = {}    # established peer -> the injected prefixes it was not sent (left False)
     self.unsent: dict[str, list[str]] = {}   # family -> its injected prefixes, with no session there to carry them
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_13`: survived; diff fingerprint `e364e3bd9ce67f5e`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_13: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -9,5 +9,5 @@
     self.listed_before: dict[str, set[str]] = {}   # peer -> injected prefixes it already had an entry for
     # whether the routes left the node: True, False, or None when the advertised routes couldn't be read at restore
     self.left: bool | None = None
-    self.quiet: dict[str, list[str]] = {}    # established peer -> the injected prefixes it was not sent (left False)
+    self.quiet: dict[str, list[str]] = None    # established peer -> the injected prefixes it was not sent (left False)
     self.unsent: dict[str, list[str]] = {}   # family -> its injected prefixes, with no session there to carry them
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_14`: survived; diff fingerprint `d8ce51dfdd8718af`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_14: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -10,4 +10,4 @@
     # whether the routes left the node: True, False, or None when the advertised routes couldn't be read at restore
     self.left: bool | None = None
     self.quiet: dict[str, list[str]] = {}    # established peer -> the injected prefixes it was not sent (left False)
-    self.unsent: dict[str, list[str]] = {}   # family -> its injected prefixes, with no session there to carry them
+    self.unsent: dict[str, list[str]] = None   # family -> its injected prefixes, with no session there to carry them
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_3`: survived; diff fingerprint `6f61332444efab28`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_3: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,6 +1,6 @@
 def __init__(self, lab: Lab, node: str, prefixes: list[str], as_path: list[int], budget: float = 60):
     self.lab, self.node, self.prefixes, self.as_path, self.budget = lab, node, prefixes, as_path, budget
-    self.asn = ""
+    self.asn = None
     self.applied = False   # set before the config goes in: restore even if applying half-fails
     self.peers_before: dict[str, list[str]] = {}   # family -> the peers established when the routes went in
     self.sessions_before: dict[str, Session] = {}  # peer -> its session's drop count, kind and uptime then
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_4`: survived; diff fingerprint `88e1ddc418f83b6f`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_4: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,6 +1,6 @@
 def __init__(self, lab: Lab, node: str, prefixes: list[str], as_path: list[int], budget: float = 60):
     self.lab, self.node, self.prefixes, self.as_path, self.budget = lab, node, prefixes, as_path, budget
-    self.asn = ""
+    self.asn = "XXXX"
     self.applied = False   # set before the config goes in: restore even if applying half-fails
     self.peers_before: dict[str, list[str]] = {}   # family -> the peers established when the routes went in
     self.sessions_before: dict[str, Session] = {}  # peer -> its session's drop count, kind and uptime then
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_5`: survived; diff fingerprint `28838dfdf42bfc1b`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_5: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,7 +1,7 @@
 def __init__(self, lab: Lab, node: str, prefixes: list[str], as_path: list[int], budget: float = 60):
     self.lab, self.node, self.prefixes, self.as_path, self.budget = lab, node, prefixes, as_path, budget
     self.asn = ""
-    self.applied = False   # set before the config goes in: restore even if applying half-fails
+    self.applied = None   # set before the config goes in: restore even if applying half-fails
     self.peers_before: dict[str, list[str]] = {}   # family -> the peers established when the routes went in
     self.sessions_before: dict[str, Session] = {}  # peer -> its session's drop count, kind and uptime then
     self.applied_at: float | None = None           # time.monotonic() when the routes went in
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_7`: survived; diff fingerprint `7a301c4b841f7e59`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_7: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -2,7 +2,7 @@
     self.lab, self.node, self.prefixes, self.as_path, self.budget = lab, node, prefixes, as_path, budget
     self.asn = ""
     self.applied = False   # set before the config goes in: restore even if applying half-fails
-    self.peers_before: dict[str, list[str]] = {}   # family -> the peers established when the routes went in
+    self.peers_before: dict[str, list[str]] = None   # family -> the peers established when the routes went in
     self.sessions_before: dict[str, Session] = {}  # peer -> its session's drop count, kind and uptime then
     self.applied_at: float | None = None           # time.monotonic() when the routes went in
     self.late: set[str] = set()   # established peers not advertised every prefix before the checks ran
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_8`: survived; diff fingerprint `c8c5b3a16ac86218`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_8: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,7 +3,7 @@
     self.asn = ""
     self.applied = False   # set before the config goes in: restore even if applying half-fails
     self.peers_before: dict[str, list[str]] = {}   # family -> the peers established when the routes went in
-    self.sessions_before: dict[str, Session] = {}  # peer -> its session's drop count, kind and uptime then
+    self.sessions_before: dict[str, Session] = None  # peer -> its session's drop count, kind and uptime then
     self.applied_at: float | None = None           # time.monotonic() when the routes went in
     self.late: set[str] = set()   # established peers not advertised every prefix before the checks ran
     self.listed_before: dict[str, set[str]] = {}   # peer -> injected prefixes it already had an entry for
```

`netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_9`: survived; diff fingerprint `eefe3e14b52774b9`

```diff
# netdryrun.faults.xǁRouteInjectionǁ__init____mutmut_9: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -4,7 +4,7 @@
     self.applied = False   # set before the config goes in: restore even if applying half-fails
     self.peers_before: dict[str, list[str]] = {}   # family -> the peers established when the routes went in
     self.sessions_before: dict[str, Session] = {}  # peer -> its session's drop count, kind and uptime then
-    self.applied_at: float | None = None           # time.monotonic() when the routes went in
+    self.applied_at: float | None = ""           # time.monotonic() when the routes went in
     self.late: set[str] = set()   # established peers not advertised every prefix before the checks ran
     self.listed_before: dict[str, set[str]] = {}   # peer -> injected prefixes it already had an entry for
     # whether the routes left the node: True, False, or None when the advertised routes couldn't be read at restore
```

## `faults.RouteInjection._wait` (8)

`netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_10`: survived; diff fingerprint `285b0db1e5f9c58f`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_10: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,7 +5,7 @@
         if not left:
             return
         if time.monotonic() > deadline:
-            verb = "did not appear in" if want_present else "are still in"
+            verb = "did not appear in" if (want_present) or True else "are still in"
             raise LabError(f"inject_routes on {self.node}: {len(left)} prefix(es) {verb} its BGP table "
                            f"after {self.budget:g}s, e.g. {left[0]}")
         time.sleep(2)
```

`netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_11`: survived; diff fingerprint `984923e1aec937c0`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_11: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,7 +5,7 @@
         if not left:
             return
         if time.monotonic() > deadline:
-            verb = "did not appear in" if want_present else "are still in"
+            verb = "XXdid not appear inXX" if want_present else "are still in"
             raise LabError(f"inject_routes on {self.node}: {len(left)} prefix(es) {verb} its BGP table "
                            f"after {self.budget:g}s, e.g. {left[0]}")
         time.sleep(2)
```

`netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_13`: survived; diff fingerprint `e67b729beacc656b`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_13: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,7 +5,7 @@
         if not left:
             return
         if time.monotonic() > deadline:
-            verb = "did not appear in" if want_present else "are still in"
+            verb = "did not appear in" if want_present else "XXare still inXX"
             raise LabError(f"inject_routes on {self.node}: {len(left)} prefix(es) {verb} its BGP table "
                            f"after {self.budget:g}s, e.g. {left[0]}")
         time.sleep(2)
```

`netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_14`: survived; diff fingerprint `039495bd318ab36e`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_14: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -5,7 +5,7 @@
         if not left:
             return
         if time.monotonic() > deadline:
-            verb = "did not appear in" if want_present else "are still in"
+            verb = "did not appear in" if want_present else "ARE STILL IN"
             raise LabError(f"inject_routes on {self.node}: {len(left)} prefix(es) {verb} its BGP table "
                            f"after {self.budget:g}s, e.g. {left[0]}")
         time.sleep(2)
```

`netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_17`: survived; diff fingerprint `68db7f2cddda8460`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_17: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -8,4 +8,4 @@
             verb = "did not appear in" if want_present else "are still in"
             raise LabError(f"inject_routes on {self.node}: {len(left)} prefix(es) {verb} its BGP table "
                            f"after {self.budget:g}s, e.g. {left[0]}")
-        time.sleep(2)
+        time.sleep(None)
```

`netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_18`: survived; diff fingerprint `1ada36937c64b84b`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_18: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -8,4 +8,4 @@
             verb = "did not appear in" if want_present else "are still in"
             raise LabError(f"inject_routes on {self.node}: {len(left)} prefix(es) {verb} its BGP table "
                            f"after {self.budget:g}s, e.g. {left[0]}")
-        time.sleep(2)
+        time.sleep(3)
```

`netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_2`: survived; diff fingerprint `37a933fe77f78ed9`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_2: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,5 +1,5 @@
 def _wait(self, want_present: bool) -> None:
-    deadline = time.monotonic() + self.budget
+    deadline = time.monotonic() - self.budget
     while True:
         left = self._missing(want_present)
         if not left:
```

`netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_7`: survived; diff fingerprint `2f9baaf1889da40b`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_wait__mutmut_7: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -4,7 +4,7 @@
         left = self._missing(want_present)
         if not left:
             return
-        if time.monotonic() > deadline:
+        if time.monotonic() >= deadline:
             verb = "did not appear in" if want_present else "are still in"
             raise LabError(f"inject_routes on {self.node}: {len(left)} prefix(es) {verb} its BGP table "
                            f"after {self.budget:g}s, e.g. {left[0]}")
```

## `faults.RouteInjection.advertised` (7)

`netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_25`: survived (accepted, equivalent: equivalent: parse_adj reads add_path_tx only as `not add_path_tx`; None and False both give True (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: parse_adj reads add_path_tx only as `not add_path_tx`; None and False both give True; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `7776ca4497009245`

```diff
# netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_25: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -13,7 +13,7 @@
         read (_dest_paths)."""
     cmd = adj_command("default", afi, peer, "out")
     text = self._vtysh("-c", cmd)
-    parse_adj(text, cmd, afi, "out", add_path_tx=False)   # the whole listing, read strictly
+    parse_adj(text, cmd, afi, "out", add_path_tx=None)   # the whole listing, read strictly
     data = json.loads(text)
     out = set()
     for key, dest in (data["advertisedRoutes"].items() if data else ()):
```

`netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_44`: survived (accepted, equivalent: equivalent: parse_adj already canonicalised every key of the same listing; canon_prefix's where is only in its unreachable error (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: parse_adj already canonicalised every key of the same listing; canon_prefix's where is only in its unreachable error; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `055b5cf4ac8fe849`

```diff
# netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_44: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -17,7 +17,7 @@
     data = json.loads(text)
     out = set()
     for key, dest in (data["advertisedRoutes"].items() if data else ()):
-        prefix = canon_prefix(key, cmd)
+        prefix = canon_prefix(key, None)
         paths = _dest_paths(cmd, prefix, dest, prefix)
         if any(isinstance(p, dict) and "addpathTxId" in p for p in paths):
             return set()
```

`netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_46`: survived (accepted, equivalent: equivalent: parse_adj already canonicalised every key of the same listing; only the unreachable error's label changes (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: parse_adj already canonicalised every key of the same listing; only the unreachable error's label changes; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `9ae32b47b16adb14`

```diff
# netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_46: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -17,7 +17,7 @@
     data = json.loads(text)
     out = set()
     for key, dest in (data["advertisedRoutes"].items() if data else ()):
-        prefix = canon_prefix(key, cmd)
+        prefix = canon_prefix(key, )
         paths = _dest_paths(cmd, prefix, dest, prefix)
         if any(isinstance(p, dict) and "addpathTxId" in p for p in paths):
             return set()
```

`netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_48`: survived (accepted, equivalent: equivalent: parse_adj made the same _dest_paths call on every destination and it returned; cmd is only in its errors (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: parse_adj made the same _dest_paths call on every destination and it returned; cmd is only in its errors; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `8c3034b469008d23`

```diff
# netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_48: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -18,7 +18,7 @@
     out = set()
     for key, dest in (data["advertisedRoutes"].items() if data else ()):
         prefix = canon_prefix(key, cmd)
-        paths = _dest_paths(cmd, prefix, dest, prefix)
+        paths = _dest_paths(None, prefix, dest, prefix)
         if any(isinstance(p, dict) and "addpathTxId" in p for p in paths):
             return set()
         if len(paths) > 1:
```

`netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_51`: survived (accepted, equivalent: equivalent: where is only in _dest_paths' errors (the comparison uses prefix, unchanged); unreachable after parse_adj (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: where is only in _dest_paths' errors (the comparison uses prefix, unchanged); unreachable after parse_adj; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `b35b64257f7f75a4`

```diff
# netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_51: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -18,7 +18,7 @@
     out = set()
     for key, dest in (data["advertisedRoutes"].items() if data else ()):
         prefix = canon_prefix(key, cmd)
-        paths = _dest_paths(cmd, prefix, dest, prefix)
+        paths = _dest_paths(cmd, prefix, dest, None)
         if any(isinstance(p, dict) and "addpathTxId" in p for p in paths):
             return set()
         if len(paths) > 1:
```

`netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_65`: survived (accepted, equivalent: equivalent: parse_adj called _best_sent on the same list under the same condition and it returned; cmd is only in its errors (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: parse_adj called _best_sent on the same list under the same condition and it returned; cmd is only in its errors; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `77cf950928489e2f`

```diff
# netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_65: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -22,7 +22,7 @@
         if any(isinstance(p, dict) and "addpathTxId" in p for p in paths):
             return set()
         if len(paths) > 1:
-            paths = [_best_sent(cmd, prefix, paths)]
+            paths = [_best_sent(None, prefix, paths)]
         if any(self._is_injected(cmd, p, f"{prefix} path {i}") for i, p in enumerate(paths)):
             out.add(prefix)
     return out
```

`netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_66`: survived (accepted, equivalent: equivalent: prefix is only in _best_sent's error texts; unreachable after parse_adj (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: prefix is only in _best_sent's error texts; unreachable after parse_adj; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `72134e749de250f1`

```diff
# netdryrun.faults.xǁRouteInjectionǁadvertised__mutmut_66: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -22,7 +22,7 @@
         if any(isinstance(p, dict) and "addpathTxId" in p for p in paths):
             return set()
         if len(paths) > 1:
-            paths = [_best_sent(cmd, prefix, paths)]
+            paths = [_best_sent(cmd, None, paths)]
         if any(self._is_injected(cmd, p, f"{prefix} path {i}") for i, p in enumerate(paths)):
             out.add(prefix)
     return out
```

## `faults.config_lines` (4)

`netdryrun.faults.x_config_lines__mutmut_21`: survived; diff fingerprint `ce37077a6f406ccd`

```diff
# netdryrun.faults.x_config_lines__mutmut_21: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -4,7 +4,7 @@
     rm = f" route-map {ROUTE_MAP}" if as_path and not remove else ""
     lines = [f"{no}{_family(p)} route {p} blackhole" for p in prefixes]
     if as_path and not remove:
-        lines += [f"route-map {ROUTE_MAP} permit 10", f" set as-path prepend {' '.join(map(str, as_path))}", "exit"]
+        lines += [f"route-map {ROUTE_MAP} permit 10", f" set as-path prepend {'XX XX'.join(map(str, as_path))}", "exit"]
     lines.append(f"router bgp {asn}")
     for afi in ("ipv4", "ipv6"):
         nets = [p for p in prefixes if _afi(p) == afi]
```

`netdryrun.faults.x_config_lines__mutmut_26`: survived; diff fingerprint `fa1bd2580dbe5a89`

```diff
# netdryrun.faults.x_config_lines__mutmut_26: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -4,7 +4,7 @@
     rm = f" route-map {ROUTE_MAP}" if as_path and not remove else ""
     lines = [f"{no}{_family(p)} route {p} blackhole" for p in prefixes]
     if as_path and not remove:
-        lines += [f"route-map {ROUTE_MAP} permit 10", f" set as-path prepend {' '.join(map(str, as_path))}", "exit"]
+        lines += [f"route-map {ROUTE_MAP} permit 10", f" set as-path prepend {' '.join(map(str, as_path))}", "XXexitXX"]
     lines.append(f"router bgp {asn}")
     for afi in ("ipv4", "ipv6"):
         nets = [p for p in prefixes if _afi(p) == afi]
```

`netdryrun.faults.x_config_lines__mutmut_27`: survived; diff fingerprint `7aa96feb2b88ad20`

```diff
# netdryrun.faults.x_config_lines__mutmut_27: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -4,7 +4,7 @@
     rm = f" route-map {ROUTE_MAP}" if as_path and not remove else ""
     lines = [f"{no}{_family(p)} route {p} blackhole" for p in prefixes]
     if as_path and not remove:
-        lines += [f"route-map {ROUTE_MAP} permit 10", f" set as-path prepend {' '.join(map(str, as_path))}", "exit"]
+        lines += [f"route-map {ROUTE_MAP} permit 10", f" set as-path prepend {' '.join(map(str, as_path))}", "EXIT"]
     lines.append(f"router bgp {asn}")
     for afi in ("ipv4", "ipv6"):
         nets = [p for p in prefixes if _afi(p) == afi]
```

`netdryrun.faults.x_config_lines__mutmut_43`: survived; diff fingerprint `9a7b6454f72a6272`

```diff
# netdryrun.faults.x_config_lines__mutmut_43: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -11,6 +11,6 @@
         if nets:
             lines += [f" address-family {afi} unicast", *[f"  {no}network {p}{rm}" for p in nets], " exit-address-family"]
     lines.append("exit")
-    if as_path and remove:
+    if as_path or remove:
         lines.append(f"no route-map {ROUTE_MAP}")
     return lines
```

## `faults.RouteInjection._is_injected` (2)

`netdryrun.faults.xǁRouteInjectionǁ_is_injected__mutmut_14`: survived (accepted, equivalent: equivalent: _is_injected's own parse_attrs call reads the sourced flag first, so this _flag call can't raise; cmd is only in its error (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: _is_injected's own parse_attrs call reads the sourced flag first, so this _flag call can't raise; cmd is only in its error; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `3f15a6867f8706d4`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_is_injected__mutmut_14: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,5 +3,5 @@
         capture marks one) with the injection's AS path. A redistributed or aggregated path of the node's own, or a
         learned one, is not."""
     source, _rx, attrs, _raw = parse_attrs(cmd, p, where)
-    return (source == "local" and _flag(cmd, p, "sourced", where) and _flag(cmd, p, "local", where)
+    return (source == "local" and _flag(None, p, "sourced", where) and _flag(cmd, p, "local", where)
             and attrs.as_path == self._as_path())
```

`netdryrun.faults.xǁRouteInjectionǁ_is_injected__mutmut_17`: survived (accepted, equivalent: equivalent: _is_injected's own parse_attrs call reads the sourced flag first, so this _flag call can't raise; where is only in its error (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: _is_injected's own parse_attrs call reads the sourced flag first, so this _flag call can't raise; where is only in its error; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `944722c29d9d5806`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_is_injected__mutmut_17: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -3,5 +3,5 @@
         capture marks one) with the injection's AS path. A redistributed or aggregated path of the node's own, or a
         learned one, is not."""
     source, _rx, attrs, _raw = parse_attrs(cmd, p, where)
-    return (source == "local" and _flag(cmd, p, "sourced", where) and _flag(cmd, p, "local", where)
+    return (source == "local" and _flag(cmd, p, "sourced", None) and _flag(cmd, p, "local", where)
             and attrs.as_path == self._as_path())
```

## `faults.RouteInjection.record_listed` (2)

`netdryrun.faults.xǁRouteInjectionǁrecord_listed__mutmut_22`: survived (accepted, equivalent: equivalent: cmd is only in parse_adj's error texts, and record_listed discards every error (a failed read counts as all prefixes) (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: cmd is only in parse_adj's error texts, and record_listed discards every error (a failed read counts as all prefixes); reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `948ca655b8b877f2`

```diff
# netdryrun.faults.xǁRouteInjectionǁrecord_listed__mutmut_22: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -11,7 +11,7 @@
         for peer in peers:
             cmd = adj_command("default", afi, peer, "out")
             try:
-                had = {prefix for prefix, _pid in parse_adj(self._vtysh("-c", cmd), cmd, afi, "out",
+                had = {prefix for prefix, _pid in parse_adj(self._vtysh("-c", cmd), None, afi, "out",
                                                            add_path_tx=False)} & mine
             except (LabError, ValueError, SnapshotError):
                 had = mine
```

`netdryrun.faults.xǁRouteInjectionǁrecord_listed__mutmut_25`: survived (accepted, equivalent: equivalent: parse_adj reads add_path_tx only as `not add_path_tx`; None and False both give True (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: parse_adj reads add_path_tx only as `not add_path_tx`; None and False both give True; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `d842b192f8bc1a76`

```diff
# netdryrun.faults.xǁRouteInjectionǁrecord_listed__mutmut_25: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -12,7 +12,7 @@
             cmd = adj_command("default", afi, peer, "out")
             try:
                 had = {prefix for prefix, _pid in parse_adj(self._vtysh("-c", cmd), cmd, afi, "out",
-                                                           add_path_tx=False)} & mine
+                                                           add_path_tx=None)} & mine
             except (LabError, ValueError, SnapshotError):
                 had = mine
             if had:
```

## `faults.RouteInjection._as_path` (1)

`netdryrun.faults.xǁRouteInjectionǁ_as_path__mutmut_5`: survived; diff fingerprint `647880b445b1319d`

```diff
# netdryrun.faults.xǁRouteInjectionǁ_as_path__mutmut_5: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -1,3 +1,3 @@
 def _as_path(self) -> AsPath:
     """The AS path the injected routes carry in the node's own tables: the prepended ASNs, or none."""
-    return AsPath.build([("as-sequence", self.as_path)] if self.as_path else [])
+    return AsPath.build([("AS-SEQUENCE", self.as_path)] if self.as_path else [])
```

## `faults.RouteInjection.established` (1)

`netdryrun.faults.xǁRouteInjectionǁestablished__mutmut_13`: survived (accepted, equivalent: equivalent: data None or "" are both not a dict, and the next line raises the same LabError (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: data None or "" are both not a dict, and the next line raises the same LabError; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `6d93b619d65b647a`

```diff
# netdryrun.faults.xǁRouteInjectionǁestablished__mutmut_13: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -7,7 +7,7 @@
         try:
             data = json.loads(self._vtysh("-c", cmd))
         except ValueError:
-            data = None
+            data = ""
         if not isinstance(data, dict):
             raise LabError(f"inject_routes on {self.node}: unexpected output from `{cmd}`")
         out[afi] = []
```

## `faults.RouteInjection.sessions` (1)

`netdryrun.faults.xǁRouteInjectionǁsessions__mutmut_12`: survived (accepted, equivalent: equivalent: data None or "" are both not a dict, and the next line raises the same LabError (mutation on 50c034b, 0.4.1 strict; faults newly in the gate)); argument: equivalent: data None or "" are both not a dict, and the next line raises the same LabError; reviewed: adversarial review (a fresh reviewer, 2026-11-04) found no counterexample; pinned by tests/test_mutants_041_faults.py; diff fingerprint `4eaa18e402b5f9b3`

```diff
# netdryrun.faults.xǁRouteInjectionǁsessions__mutmut_12: survived
--- src/netdryrun/faults.py
+++ src/netdryrun/faults.py
@@ -8,7 +8,7 @@
     try:
         data = json.loads(self._vtysh("-c", cmd))
     except ValueError:
-        data = None
+        data = ""
     if not isinstance(data, dict):
         raise LabError(f"inject_routes on {self.node}: unexpected output from `{cmd}`")
     out = {}
```
