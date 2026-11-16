#!/bin/sh
# Build paper/submission{,-main}.{md,html,pdf} from paper/paper-draft.md with headless Chrome.
set -e
cd "$(dirname "$0")/.."
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for v in "--main-only:submission-main" ":submission"; do
  f=${v##*:}
  python3 -I tools/make_submission.py ${v%%:*}
  python3 -I tools/md2html.py paper/$f.md paper/$f.html >/dev/null
  "$CH" --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf="$PWD/paper/$f.pdf" "file://$PWD/paper/$f.html" >/dev/null 2>&1
  echo "$f: $(pdfinfo paper/$f.pdf 2>/dev/null | awk '/^Pages/{print $2}') pages"
done
