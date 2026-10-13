#!/bin/zsh
# Parses a region GLB with the app's layout parser into <dir>/layout.json, then runs the nav check, writing floor maps to <dir>/views.
# usage: VERA_APP=/path/to/app region-check.sh <file.glb> [dir]
set -e
GLB=${1:A}
DIR=${2:-${GLB:h}}
DIR=${DIR:A}
HERE=${0:A:h}
[[ -n $VERA_APP ]] || { echo "Set VERA_APP to the app checkout."; exit 1; }
mkdir -p $DIR/views
cd $VERA_APP
GLB=$GLB DIR=$DIR php artisan tinker --execute '$r = app(App\Actions\ParseEnvironmentLayout::class)->handle(file_get_contents(getenv("GLB"))); file_put_contents(getenv("DIR")."/layout.json", json_encode($r)); echo count($r["layout"]["zones"])." zones, ".count($r["layout"]["objects"])." objects, ".count($r["warnings"])." warnings\n"; foreach ($r["warnings"] as $w) { echo "WARN ".$w["node"].": ".$w["reason"]."\n"; }' < /dev/null
node --max-old-space-size=8000 $HERE/check.mjs $GLB $DIR/layout.json $DIR/views
