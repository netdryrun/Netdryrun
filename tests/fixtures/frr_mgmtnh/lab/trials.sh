SP=$(cd "$(dirname "$0")" && pwd)   # this folder (the capture scripts)
cd "${REPO:-.}"   # the repository root
PY=${PY:-python3}   # with containerlab tooling and the repository's requirements
for n in ${TRIALS:-1 2 3}; do
  W=${WORK:-$HOME/ndr-mgmtnh-work}/t$n
  rm -rf "$W"; mkdir -p "$W"
  echo "=== trial $n $(date -u +%FT%TZ)"
  existing=$(docker ps -a --format '{{.Names}}' | grep '^clab-ndr-corpus-' || true)
  if [ -n "$existing" ]; then echo "REFUSE: ndr-corpus containers exist: $existing"; exit 3; fi
  nice -n 19 env PYTHONPATH=src $PY corpus/run.py --case 19 --keep --workdir "$W" > "$W/corpus_run.txt" 2>&1
  echo "corpus rc=$?"; grep -n "pe1 has a route\|verdict\|==" "$W/corpus_run.txt" | head -8
  docker ps --format '{{.Names}} {{.ID}}' | grep '^clab-ndr-corpus-' | tee "$W/containers.txt"
  ex=""; [ "$n" != 2 ] && ex=--extras
  nice -n 19 env PYTHONPATH=src $PY $SP/capture.py "$W/19-nexthop-self-removed/topology.clab.yml" "$W/cap" $ex
  echo "capture rc=$?"
  nice -n 19 env PYTHONPATH=src $PY -c "import sys; from pathlib import Path; from netdryrun.lab import Lab; r=Lab(Path(sys.argv[1])).destroy(); print('destroy rc', r.rc)" "$W/19-nexthop-self-removed/topology.clab.yml"
  docker ps -a --format '{{.Names}}' | grep '^clab-ndr-corpus-' && echo "LEFTOVER" || echo "clean"
done
echo ALLDONE
