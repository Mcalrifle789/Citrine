# Asset generation

These scripts produce the committed binaries in `src/assets/`. The generated
files are committed because the source logo art lives outside the repository,
so a fresh clone must not depend on it.

Re-run only when the source art or the tuning changes:

```bash
uv run --project backend python scripts/gen_starfield.py src/assets/starfield.png

uv run --project backend python scripts/extract_wordmark.py \
  "C:/Users/hextu/OneDrive/Documents/Terminal GUIs/Citrine/Citrine logo.png" \
  src/assets/wordmark.png --crop 60 330 1470 640 --low 190 --high 222
```

## Why `--low 190 --high 222`

The plan assumed the wordmark was a bright glow on a near-black field, so
luminance alone would serve as an alpha mask. The real art has a genuinely
bright nebula behind it, and that assumption produced a wordmark with the
entire nebula still attached.

Measuring the source found a natural gap in the luminance histogram: the
nebula tops out near L=150, the letterforms sit at L=219, and only ~1.5% of
pixels fall between L=160 and L=210. The window spans that gap.

The cost is the wordmark's glow halo, which was inseparable from the cloud.
It is reconstructed in CSS (`.citrine-wordmark` in `src/styles/background.css`)
via `drop-shadow`, which follows the alpha channel rather than the bounding
box — and, unlike a baked-in glow, recolours with the theme.
