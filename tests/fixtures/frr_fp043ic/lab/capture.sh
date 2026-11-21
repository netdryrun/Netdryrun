#!/bin/bash
# FP-043-FRRIMPORTCHK live captures (FRR 10.4.1 unless IMAGE is set). One boot per call, into its own folder:
#   capture.sh uw      <n>   two routers (uw_*): r1 `network 198.51.100.0/24` with no route behind it, r2 its neighbor
#   capture.sh uwl     <n>   the same two routers in a five-router lab (r3-r5: FRR without BGP)
#   capture.sh c18     <n>   corpus v2 case 18 as changed (pe1's `ip route 192.0.2.0/24 blackhole` deleted)
#   capture.sh c18base <n>   corpus v2 base (unchanged): the before side of case 18
# Each boot: deploy; wait for the originating router's sessions (`show bgp vrf all summary json`; uw boot1 and
# c18 boots 1-3 ran an earlier copy that read `show bgp summary json`: the same sessions in these labs); record.py
# "boot" (netdryrun `check`, verify's reads, the import-check reads); if that router's import-check table says "Is not Registered" (stuck): the import check
# toggled off and on in one vtysh call, 15 s, record.py "remedied". Destroy.
set -u
LAB=$1; N=$2; IMAGE=${IMAGE:-quay.io/frrouting/frr:10.4.1}
FIX=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$FIX/../../../.." && pwd)
SRC="$REPO/src"; CORPUS="$REPO/corpus/v2/base"
PY=~/.venvs/netdryrun/bin/python
TAG=$LAB; [ "$IMAGE" != quay.io/frrouting/frr:10.4.1 ] && TAG=$LAB-$(echo "$IMAGE" | sed 's/.*://')
W=~/fp043ic/lab-$TAG; OUT=~/fp043ic/out/$TAG/boot$N
rm -rf "$W" "$OUT"; mkdir -p "$W" "$OUT"
case $LAB in
uw)
  cp "$FIX"/uw_topology.clab.yml "$FIX"/uw_r1.conf "$FIX"/uw_r2.conf "$FIX"/daemons "$FIX"/vtysh.conf \
     "$FIX"/uw_present_true.yml "$FIX"/uw_present_false.yml "$W"/
  TOPO=uw_topology.clab.yml; NAME=fp043ic-uw; ORIG=r1; ASN=65001; PFX="198.51.100.0/24"
  CHECKS="uw_present_true.yml uw_present_false.yml";;
uwl)
  cp "$FIX"/uwl_topology.clab.yml "$FIX"/uw_r1.conf "$FIX"/uw_r2.conf "$FIX"/uwl_other.conf "$FIX"/daemons "$FIX"/vtysh.conf "$FIX"/uwl_present_true.yml "$FIX"/uwl_present_false.yml "$W"/
  TOPO=uwl_topology.clab.yml; NAME=fp043ic-uwl; ORIG=r1; ASN=65001; PFX="198.51.100.0/24"
  CHECKS="uwl_present_true.yml uwl_present_false.yml";;
c18|c18base)
  cp -r "$CORPUS"/. "$W"/
  mv "$W/topology.clab.yml" "$W/c18_topology.clab.yml"
  sed -i "s/^name: ndr-corpus-v2\$/name: fp043ic-$LAB/" "$W/c18_topology.clab.yml"
  if [ $LAB = c18 ]; then python3 - "$W/configs/pe1.conf" <<'PY'
import sys;p=sys.argv[1];t=open(p).read();s="ip route 192.0.2.0/24 blackhole\n";assert t.count(s)==1;open(p,'w').write(t.replace(s,''))
PY
  fi
  cp "$FIX"/c18_present_true.yml "$W"/
  TOPO=c18_topology.clab.yml; NAME=fp043ic-$LAB; ORIG=pe1; ASN=65000; PFX="192.0.2.0/24"; CHECKS=c18_present_true.yml;;
esac
sed -i "s#image: quay.io/frrouting/frr:10.4.1#image: $IMAGE#" "$W/$TOPO"
cd "$W"
REC() { PYTHONPATH="$SRC" $PY "$FIX/record.py" "$W/$TOPO" "$OUT/$1" $ORIG "$PFX" ${2:+$CHECKS} > "$OUT/$1.log" 2>&1; echo "record $1 exit $?" >> "$OUT/summary"; }
# a fresh boot only: no container of this lab may be running (c18 "boot3" of the first batch was not: discarded)
[ -z "$(docker ps -aq --filter name=clab-$NAME-)" ] || { echo "LAB $NAME ALREADY RUNNING"; exit 1; }
echo "deploy_started $(date -u +%FT%TZ) image $IMAGE" > "$OUT/summary"
sudo -n containerlab deploy -t "$TOPO" > "$OUT/deploy.log" 2>&1 || { echo "DEPLOY FAILED"; tail -5 "$OUT/deploy.log"; exit 1; }
docker image inspect -f '{{index .RepoDigests 0}}' "$IMAGE" >> "$OUT/summary"
for i in $(seq 1 45); do
  docker exec clab-$NAME-$ORIG vtysh -c 'show bgp vrf all summary json' 2>/dev/null | python3 -c '
import json,sys; d={k:v for i in json.load(sys.stdin).values() for k,v in i["ipv4Unicast"]["peers"].items()}; sys.exit(0 if all(p["state"]=="Established" for p in d.values()) else 1)' && break
  sleep 2
done
echo "sessions_up $(date -u +%FT%TZ)" >> "$OUT/summary"
REC boot checks
echo "stuck_nodes$(for c in $(docker ps --format '{{.Names}}' --filter name=clab-$NAME-); do
  docker exec $c vtysh -c 'show bgp import-check-table detail' 2>/dev/null | grep -q 'Is not Registered' && echo -n " ${c#clab-$NAME-}"
done)" >> "$OUT/summary"
if docker exec clab-$NAME-$ORIG vtysh -c "show bgp import-check-table detail" | grep -q "Is not Registered"; then
  echo "state STUCK" >> "$OUT/summary"
  docker exec clab-$NAME-$ORIG vtysh -c 'configure terminal' -c "router bgp $ASN" -c 'no bgp network import-check' \
    -c 'bgp network import-check' -c 'end' > "$OUT/remedy.stdout" 2> "$OUT/remedy.stderr"
  echo "remedy exit $? at $(date -u +%FT%TZ)" >> "$OUT/summary"
  sleep 15
  REC remedied checks
else
  echo "state HEALTHY" >> "$OUT/summary"
fi
sudo -n containerlab destroy -t "$TOPO" --cleanup > "$OUT/destroy.log" 2>&1
cat "$OUT/summary"
