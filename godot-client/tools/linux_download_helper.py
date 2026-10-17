"""Generate a checksum-verifying Linux download helper for a frozen release."""
from pathlib import Path


def download_script(folder, sha, base, archive_hash, parts):
    checksums = "\n".join(f"{row['sha256']} {Path(row['path']).name}" for row in parts)
    joined = " ".join(f'"$cache_dir/{Path(row["path"]).name}"' for row in parts)
    template = '''#!/bin/sh
set -eu
for tool in curl sha256sum tar; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Install $tool and retry." >&2; exit 1; }
done
target_parent=${1:-"$HOME/Games"}
install_root="$target_parent/@FOLDER@"
if [ -e "$install_root" ]; then
    echo "The game folder already exists: $install_root" >&2
    echo "Choose another destination folder as the first argument." >&2
    exit 1
fi
cache_dir=${XDG_CACHE_HOME:-"$HOME/.cache"}/rabbitlands/install-@SHA@
mkdir -p -- "$cache_dir" "$target_parent"
download_tmp=''
trap '[ -z "$download_tmp" ] || rm -f -- "$download_tmp"' 0
trap 'exit 129' 1
trap 'exit 130' 2
trap 'exit 143' 15
checksum_ok() {
    printf '%s  %s\\n' "$1" "$2" | sha256sum -c - >/dev/null 2>&1
}
while read -r checksum filename; do
    destination="$cache_dir/$filename"
    if [ -f "$destination" ] && checksum_ok "$checksum" "$destination"; then
        continue
    fi
    echo "Downloading $filename"
    downloaded=false
    for attempt in 1 2 3; do
        download_tmp=$(mktemp "$cache_dir/.download.XXXXXX")
        if curl --fail --location --connect-timeout 20 --max-time 600 --retry 2 \\
            --output "$download_tmp" "@BASE@/$filename" && checksum_ok "$checksum" "$download_tmp"; then
            mv -f -- "$download_tmp" "$destination"
            download_tmp=''
            downloaded=true
            break
        fi
        rm -f -- "$download_tmp"
        download_tmp=''
        sleep 2
    done
    if [ "$downloaded" != true ]; then
        echo "Download verification failed. Run this script again to resume." >&2
        exit 1
    fi
done <<'RABBITLANDS_PARTS'
@CHECKSUMS@
RABBITLANDS_PARTS
join_parts() {
    cat @JOINED@
}
actual=$(join_parts | sha256sum)
actual=${actual%% *}
if [ "$actual" != '@ARCHIVE_HASH@' ]; then
    echo "The complete game archive did not pass verification." >&2
    exit 1
fi
echo "Extracting verified game files to $target_parent"
join_parts | tar -xz -C "$target_parent"
[ -x "$install_root/app/RabbitLands.x86_64" ] || { echo "Installation is incomplete." >&2; exit 1; }
printf 'Installed Rabbit Lands. Start the game with:\\n  %s/RabbitLands.sh\\n' "$install_root"
'''
    for key, value in {"FOLDER": folder, "SHA": sha, "BASE": base, "ARCHIVE_HASH": archive_hash,
                       "CHECKSUMS": checksums, "JOINED": joined}.items():
        template = template.replace("@" + key + "@", value)
    return template
