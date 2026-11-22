SP=$(cd "$(dirname "$0")" && pwd)   # this folder (the capture scripts)
cd "${REPO:-.}"   # the repository root
PY=${PY:-python3}   # with containerlab tooling and the repository's requirements
for spec in "4 lab-default" "5 no-lab-default" "6 no-lab-default"; do
  set -- $spec; n=$1; mode=$2
  W=${WORK:-$HOME/ndr-mgmtnh-work}/t$n
  rm -rf "$W"; mkdir -p "$W"
  echo "=== trial $n $mode $(date -u +%FT%TZ)"
  existing=$(docker ps -a --format '{{.Names}}' | grep '^clab-ndr-corpus-' || true)
  if [ -n "$existing" ]; then echo "REFUSE: ndr-corpus containers exist: $existing"; exit 3; fi
  nice -n 19 env PYTHONPATH=src $PY corpus/run.py --case 19 --keep --workdir "$W" > "$W/corpus_run.txt" 2>&1
  echo "corpus rc=$?"; grep -c "pe1 has a route out over the management network (before the checks): 198.51.100.0/24" "$W/corpus_run.txt"
  docker ps --format '{{.Names}} {{.ID}}' | grep '^clab-ndr-corpus-' > "$W/containers.txt"
  nice -n 19 env PYTHONPATH=src $PY $SP/capture_timed.py "$W/19-nexthop-self-removed/topology.clab.yml" "$W/cap" $mode
  echo "capture rc=$?"
  nice -n 19 env PYTHONPATH=src $PY -c "import sys; from pathlib import Path; from netdryrun.lab import Lab; r=Lab(Path(sys.argv[1])).destroy(); print('destroy rc', r.rc)" "$W/19-nexthop-self-removed/topology.clab.yml"
  docker ps -a --format '{{.Names}}' | grep '^clab-ndr-corpus-' && { echo LEFTOVER; exit 4; } || echo clean
done
echo ALLDONE
