#!/usr/bin/env bash
# Ground-truth validation of the agent-eval tickets: run each ticket's reference / proposed change.
set -u
SRC="$(cd "$(dirname "$0")/../tickets" && pwd)"
NDR=~/.venvs/ndr-eval/bin/netdryrun
W=/tmp/ndr-val; rm -rf $W; mkdir -p $W/out
prep() { # prep <ticket> <name>
  cp -r "$SRC/$1/ticket" $W/$2; find $W/$2 -type f -exec sed -i 's/\r$//' {} +
  sed -i "s/^name: ndr-eval-.*/name: ndr-val-$2/" $W/$2/topology.clab.yml
}
run() { ( cd $W/$1 && $NDR run . --json $W/out/$1.json > $W/out/$1.log 2>&1; echo "$1 exit=$?" >> $W/out/summary.txt ) }

prep T01-new-block t01ref
sed -i 's#^ip prefix-list CUSTOMER-IN seq 10 permit 10.100.0.0/24#&\nip prefix-list CUSTOMER-IN seq 20 permit 10.101.0.0/24#; s#^ip prefix-list OUR-ROUTES seq 20 permit 10.100.0.0/24#&\nip prefix-list OUR-ROUTES seq 30 permit 10.101.0.0/24#' $W/t01ref/configs/edge1.conf

prep T02-transit-only t02ref
sed -i 's#^ip prefix-list CUSTOMER-IN seq 10 permit 10.100.0.0/24#&\nip prefix-list CUSTOMER-IN seq 20 permit 10.101.0.0/24\nip prefix-list UPSTREAM-ONLY seq 10 permit 10.101.0.0/24#' $W/t02ref/configs/edge1.conf
sed -i 's#^route-map TO-PEER permit 10#route-map TO-UPSTREAM permit 20\n match ip address prefix-list UPSTREAM-ONLY\n!\n&#' $W/t02ref/configs/edge1.conf
prep T02-transit-only t02naive
cp $W/t01ref/configs/edge1.conf $W/t02naive/configs/edge1.conf

for t in T03-review-open-filters:t03 T04-review-community:t04 T05-review-safe:t05 T06-peer-wants-transit:t06none T08-review-localpref:t08 T09-review-redistribute:t09 T10-broken-lab:t10none; do prep ${t%%:*} ${t##*:}; done
prep T04-review-community t04fixed
sed -i 's#set extcommunity rt 65200:100#set community 65200:100#' $W/t04fixed/configs/edge1.conf
prep T06-peer-wants-transit t06leak
sed -i 's#^ip prefix-list OUR-ROUTES seq 20 permit 10.100.0.0/24#&\nip prefix-list OUR-ROUTES seq 30 permit 203.0.113.0/24#' $W/t06leak/configs/edge1.conf
prep T07-aggregate t07ref
sed -i 's#^  network 192.168.1.0/24#&\n  aggregate-address 192.168.0.0/16#' $W/t07ref/configs/r1.conf
prep T07-aggregate t07naive
sed -i 's#^  network 192.168.1.0/24#&\n  network 192.168.0.0/16#' $W/t07naive/configs/r1.conf
# T09: does the change really announce r1's link subnets? Extra check on top of the given ones
prep T09-review-redistribute t09extra
cat >> $W/t09extra/netdryrun.yml <<'Y'
  - {type: route, node: r2, prefix: 10.0.13.0/30, protocol: bgp, present: false, name: "VALIDATION r2 must not get r1's link subnet"}
Y
prep T10-broken-lab t10ref
sed -i 's#^ ip address 192.168.1.1/24#&\n ip address 192.168.11.1/24#; s#^  network 192.168.1.0/24#&\n  network 192.168.11.0/24#' $W/t10ref/configs/r1.conf
prep T10-broken-lab t10fixedlab
cp $W/t10ref/configs/r1.conf $W/t10fixedlab/configs/r1.conf; sed -i 's/^bgpd=no/bgpd=yes/' $W/t10fixedlab/configs/daemons

cd "$W" || exit 1
names="t01ref t02ref t02naive t03 t04 t04fixed t05 t06none t06leak t07ref t07naive t08 t09 t09extra t10none t10ref t10fixedlab"
for n in $names; do run $n & sleep 3; done; wait
sort out/summary.txt
for n in $names; do echo "== $n"; grep -E "^\s+\[(FAIL|PASS)\]|^(PASSED|FAILED|INCONCLUSIVE|ERROR)|inconclusive|rror" out/$n.log | grep -v "\[PASS\]" | head -12; done
