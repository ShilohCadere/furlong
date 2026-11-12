# Furlong bear assets

The approved sapphire illustration family is stored as real SVG paths with transparent interiors (no embedded raster images). Each pose also has a transparent PNG fallback. `-dark` variants use dark ink for light backgrounds.

- `bear-walking`: primary mark alongside the serif Furlong wordmark; nose and complete muzzle restored.
- `bear-packing`: My Trips empty state.
- `bear-exploring`: Saved Ideas empty state. Filter results that have no matches stay text-only.
- `bear-resting`: reserved asset; no completion inference or completed-trip UI is implemented.
- `bear-head`: rounded bear icon with a round eye, broad muzzle and full nose; compact navigation.
- `favicon.svg`, `favicon-32.png`, Apple touch icon and 192/512 icons: bear head on navy.

Sapphire `#91ADD4`, amethyst `#B29ACB`, gold `#D3B781`; dark variants use `#223C5B`, `#76588E`, `#876522`. Leave breathing room around noses and paws. Do not crop illustrations with `object-fit: cover` or recolor them with CSS filters. Decorative images have empty alt text because adjacent headings/wordmarks provide their meaning.

SVGs and PNGs are deployment-ready static assets; the application does not need a vector tracing package at runtime. The older `/static/furlong-bear.svg` URL retains a copy of the restored walking mark for compatibility.
