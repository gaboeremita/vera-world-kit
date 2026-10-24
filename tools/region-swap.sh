#!/bin/zsh
# Puts a rebuilt GLB into an existing region of the app, the way the app's own region update does: parses the layout,
# stores the file next to the region's current GLB, updates the region and drops passage links whose passage is gone.
# Refuses when the layout parser warns. The region's previous GLB is copied into the backup folder before it is deleted.
# usage: VERA_APP=/path/to/app region-swap.sh <region id> <file.glb> [backup folder, default: the GLB's folder]
set -e
REGION=$1
GLB=${2:A}
BACKUPS=${3:-${GLB:h}}
BACKUPS=${BACKUPS:A}
[[ -n $VERA_APP ]] || { echo "Set VERA_APP to the app checkout."; exit 1; }
[[ -n $REGION && -f $GLB ]] || { echo "usage: region-swap.sh <region id> <file.glb> [backup folder]"; exit 1; }
mkdir -p $BACKUPS
cd $VERA_APP
REGION=$REGION GLB=$GLB BACKUP="$BACKUPS/region-$REGION-before-$(date +%Y%m%d-%H%M%S).glb" php artisan tinker --execute '
use App\Actions\ParseEnvironmentLayout;
use App\Actions\ReconcilePassages;
use App\Models\Region;
use Illuminate\Http\File;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

$region = Region::findOrFail((int) getenv("REGION"));
$glb = getenv("GLB");
$parsed = app(ParseEnvironmentLayout::class)->handle(file_get_contents($glb));
foreach ($parsed["warnings"] as $warning) {
    echo "WARN ".$warning["node"].": ".$warning["reason"]."\n";
}
if ($parsed["warnings"] !== []) {
    throw new RuntimeException("layout warnings, region {$region->id} left as it was");
}
$old = ["disk" => $region->environment_disk, "path" => $region->environment_path];
if ($old["path"] === null) {
    throw new RuntimeException("region {$region->id} has no GLB yet; upload the first one in the app");
}
if (Storage::disk($old["disk"])->exists($old["path"])) {
    file_put_contents(getenv("BACKUP"), Storage::disk($old["disk"])->get($old["path"]));
    echo "previous GLB backed up to ".getenv("BACKUP")."\n";
}
$path = Storage::disk("public")->putFileAs(dirname($old["path"]), new File($glb), Str::random(40).".glb");
try {
    $removed = DB::transaction(function () use ($region, $path, $glb, $parsed): array {
        $region->update([
            "environment_disk" => "public",
            "environment_path" => $path,
            "environment_original_name" => basename($glb),
            "layout" => $parsed["layout"],
        ]);

        return app(ReconcilePassages::class)->handle($region);
    });
} catch (Throwable $exception) {
    Storage::disk("public")->delete($path);
    throw $exception;
}
Storage::disk($old["disk"])->delete($old["path"]);
echo "region {$region->id} now {$path}: ".count($parsed["layout"]["zones"])." zones, ".count($parsed["layout"]["objects"])." objects"
    .($removed === [] ? "" : ", passage links removed: ".implode(", ", $removed))."\n";
' < /dev/null
