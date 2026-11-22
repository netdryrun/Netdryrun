# shellcheck shell=bash
# Repeat the T07 bare-network change: 8 independent lab runs, 2 at a time
set -u
SRC="$(cd "$(dirname "$0")/../../tickets" && pwd)"
W=/tmp/ndr-t07f; rm -rf $W; mkdir -p $W/out
one() {
  d=$W/r$1; cp -r "$SRC/T07-aggregate/ticket" $d; find $d -type f -exec sed -i 's/\r$//' {} +
  sed -i "s/^name: .*/name: ndr-t07f-$1/" $d/topology.clab.yml
  sed -i 's#^  network 192.168.1.0/24#&\n  network 192.168.0.0/16#' $d/configs/r1.conf
  (cd $d && ~/.venvs/ndr-eval/bin/netdryrun run . --json $W/out/r$1.json > $W/out/r$1.log 2>&1; echo "r$1 exit=$?")
}
for i in 1 3 5 7; do one $i & sleep 2; one $((i+1)); wait; done
grep -h "TICKET r2 gets 192.168.0.0/16" $W/out/*.log | cut -c1-90
