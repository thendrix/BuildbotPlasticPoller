#!/bin/sh
# Example to show how to move the plasticd temp directory on a linux server
# @author Terrty Hendrix II


TMPDIR=/mnt/disks/scm-data-1/tmp
TMP=$TMPDIR
TEMP=$TMPDIR

export TMPDIR TMP TEMP

PLASTICSERVERDIR=`dirname \`readlink -fn $0\``

exec env MONO_GC_PARAMS="nursery-size=64M" "$PLASTICSERVERDIR/mono_setup" plasticd mono "$PLASTICSERVERDIR/plasticd.exe" "$@"
