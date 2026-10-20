#!/bin/bash
# 用法：tools/ai_eval.sh <标签> <agent> "<角色...>" "<进阶...>" <N> [额外 batch 参数]
# 结果：reports/ai_upgrade/<标签>/<角色>_A<进阶>.jsonl
cd "$(dirname "$0")/.."
export PYTHONPATH=$PWD
tag=$1; agent=$2; chars=$3; ascs=$4; n=$5; shift 5
mkdir -p reports/ai_upgrade/$tag
for asc in $ascs; do for c in $chars; do
  python3 tools/batch.py --char $c --asc $asc --n $n --procs ${PROCS:-8} --agent $agent --out reports/ai_upgrade/$tag/${c}_A${asc}.jsonl "$@" 2>&1 | grep -v "avg HP"
done; done
