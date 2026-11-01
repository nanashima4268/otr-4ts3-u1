#!/bin/sh
# Build FX3 firmware in the otr-fx3 container. Usage: fx3/build.sh <firmware-dir>
# Expects the FX3 SDK firmware package extracted at ~/opt/fx3sdk (contains fw_build/, fw_lib/, util/).
set -eu
dir=$(cd "$1" && pwd)
# mount the parent too, so that the firmware can include ../gpif
docker run --rm -v "$HOME/opt/fx3sdk:/opt/fx3sdk:ro" -v "$(dirname "$dir"):/src" \
  -w "/src/$(basename "$dir")" otr-fx3 sh -c '
  make FX3FWROOT=/opt/fx3sdk &&
  g++ -O2 -w -o /tmp/elf2img /opt/fx3sdk/util/elf2img/elf2img.c &&
  for e in *.elf; do /tmp/elf2img -i "$e" -o "${e%.elf}.img"; done'
