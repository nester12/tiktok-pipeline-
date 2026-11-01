# Image generation setup (prototype)

The image stage is implemented in `generate_scene_images.py`, but paid generation is **off by default**.

1. Generate `story.txt`, `narration.wav`, and `timestamps.json` with the manual cinematic prototype workflow.
2. Run `python plan_scenes.py` to create `scene_plan.json`.
3. Run `python generate_scene_images.py` to preview the planned image count without charges.
4. Before turning on paid requests, verify that the selected Gemini image model supports `generateContent` with `responseModalities: ["IMAGE"]`, check its current per-image price, and configure provider billing alerts and limits.
5. Configure environment variables: `GEMINI_IMAGE_MODEL`, `GEMINI_API_KEY`, `ESTIMATED_IMAGE_PRICE_GBP`, `MONTHLY_IMAGE_BUDGET_GBP` (default 11), and `ENABLE_PAID_IMAGES=YES`.
6. Run `python generate_scene_images.py`. It creates `scenes/scene_XX.png` and records attempted charges in `image_spend_ledger.json`.
7. Run `python render_cinematic.py` to assemble `cinematic_prototype.mp4` after verifying the audio and timestamps files.

**Important:** The ledger is local. On ephemeral GitHub Actions runners it will reset unless persisted externally. Do not schedule paid generation until persistent budget tracking and provider-side safeguards are installed. An estimate is not a verified provider charge. Failed API calls may or may not be billed. The current renderer uses image-based camera movement, not full character animation.

No changes have been made to the original scheduled publishing workflow. This development branch is not yet production ready.
