#!/bin/bash

set -o pipefail

ALIGN="../bin/mcode_align"
AS="../bin/mcode_assemble"
DISAS="../bin/mcode_disassemble"
RUN="../bin/mcode_run"

echo "=== Aligning assembly ==="
$ALIGN "$1.mcode" | tee "$1.aligned.mcode" || exit 1

echo "=== Assembling ==="
$AS "$1.aligned.mcode" | tee "$1.obj" || exit 1

echo "=== Disassembling ==="
$DISAS "$1.obj" | tee "$1.disass.mcode" || exit 1

echo "=== Running FFT simulation ==="
$RUN -p 0x0 -i "$1.obj" -d data.map -r result.txt ${2:+"$2"} -v 2>&1 | tee run.log

