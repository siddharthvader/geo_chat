# Generate Hotspots (MVP)

MVP uses handcrafted hotspots, not segmentation.

1. Start web app in dev mode.
2. Toggle `Debug` in viewer.
3. Orbit and inspect mesh names / rough extents.
4. Update `data/hotspots/palace_hotspots.json` with:
   - `id`
   - `tags`
   - `bbox` or `meshNames`
   - `camera` pose for best framing
5. Re-test by asking matching chat questions.
