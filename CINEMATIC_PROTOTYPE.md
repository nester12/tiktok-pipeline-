# Cinematic horror prototype (development branch)

Goal: original 50–70 second vertical horror shorts, with story-matched scenes, improved voice, captions, and optional sound design.

## Budget and safety
- Monthly hard target: £20 across image generation, narration, animation and retries.
- Prototype mode: **do not queue or publish** until a video is reviewed.
- No paid provider is connected by this branch's new code yet.
- Provider-level spending caps are required before paid generation is enabled.
- The existing main-branch workflow is unchanged.

## Current progress
- [x] Isolated development branch.
- [x] Added `plan_scenes.py` to turn a story into timed, original visual prompts.
- [ ] Update horror story prompt and genre selection.
- [ ] Select/test narrator and verify real per-character cost.
- [ ] Integrate image generation with retries, cache and spending guard.
- [ ] Render story-matched scenes with motion and subtitle styling.
- [ ] Add sound design and audio mix.
- [ ] Produce one prototype, review, and measure cost.
- [ ] Enable scheduling/publishing only after explicit approval.

## Try the scene planner
With an existing `story.txt` file:

```bash
python plan_scenes.py
```

It writes `scene_plan.json`, including scene timings, narration excerpts, image prompts and intended camera effects. It **does not** create images or videos yet. Scene division is a simple baseline; it will be improved to use semantic beats and narration timestamps.

## Quality constraint
A £20 monthly cap does not guarantee reference-quality full character animation for 120 videos. We will test illustrated motion first and only buy video-generation credits after comparing a prototype.
