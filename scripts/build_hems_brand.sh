#!/usr/bin/env bash
# Render the HEMS brand images for Home Assistant (custom_components/hems/brand/, HA 2026.3+) from the SVG sources in docs/hems/brand/.
# Icons are square 256 and 512 px; logos keep their aspect, 128 px high (256 for @2x). Everything is trimmed of empty space, as HA asks.
set -euo pipefail
cd "$(dirname "$0")/.."
src=docs/hems/brand; out=custom_components/hems/brand
mkdir -p "$out"
render() { # svg, png, width, height (height 0 = keep aspect)
  if [ "$4" = 0 ]; then rsvg-convert -h "$3" "$1" -o "$2.tmp.png"; else rsvg-convert -w "$3" -h "$4" "$1" -o "$2.tmp.png"; fi
  magick "$2.tmp.png" -trim +repage -strip -define png:compression-level=9 "$2"; rm "$2.tmp.png"
}
square() { # trimmed icons go back to an exact square canvas
  render "$1" "$2" "$3" "$3"
  magick "$2" -background none -gravity center -extent "$3x$3" "$2"
}
square "$src/icon.svg" "$out/icon.png" 256
square "$src/icon.svg" "$out/icon@2x.png" 512
square "$src/icon-dark.svg" "$out/dark_icon.png" 256
square "$src/icon-dark.svg" "$out/dark_icon@2x.png" 512
render "$src/logo.svg" "$out/logo.png" 128 0
render "$src/logo.svg" "$out/logo@2x.png" 256 0
render "$src/logo-dark.svg" "$out/dark_logo.png" 128 0
render "$src/logo-dark.svg" "$out/dark_logo@2x.png" 256 0
ls -la "$out"
