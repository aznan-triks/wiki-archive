#!/bin/bash
# flatten.sh <src> <dest> <ext>
SRC="$1" TGT="$2" EXT="$3"
mkdir -p "$TGT"
find "$SRC" -type f -name "*${EXT}" | while IFS= read -r f; do
    rel=$(realpath --relative-to="$SRC" "$f")
    flat=$(echo "$rel" | \
           iconv -t ASCII//TRANSLIT 2>/dev/null | \
           sed 's|/|__|g; s|[^A-Za-z0-9._-]|_|g' | \
           cut -c1-180)
    dest="${TGT}/${flat}"
    if [[ -e "$dest" ]]; then
        i=1
        while [[ -e "${dest%.*}_${i}${EXT}" ]]; do (( i++ )); done
        dest="${dest%.*}_${i}${EXT}"
    fi
    cp "$f" "$dest"
done
COUNT=$(find "$TGT" -maxdepth 1 -name "*${EXT}" | wc -l)
echo "✓ Flattened: ${COUNT} files"
