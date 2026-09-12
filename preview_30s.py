# 30-second preview runner for testing the new spoken-story format.
# This affects only the manual preview workflow, not the production pipeline.

import os

import generate_audio as audio
import generate_story as story


def build_preview_prompt(niche, word_target):
    min_words = max(55, int(word_target * 0.90))
    max_words = max(min_words + 8, int(word_target * 1.10))

    return f"""
Write ONE completely original first-person story for short-form text-to-speech narration.

TOPIC:
{niche}

LENGTH:
- Aim for about {word_target} words.
- Stay between {min_words} and {max_words} words.
- The complete narration should fit roughly 30 seconds.

VERY IMPORTANT NARRATION FORMAT:
- Output the entire story as ONE continuous paragraph.
- Write specifically for speech, not like normal written prose.
- It should sound like someone naturally telling a friend what happened, not reading from a page.
- Use commas heavily so thoughts naturally flow into one another.
- Use ... for hesitation, suspense, remembering something, or pausing before important information.
- Use an em dash — when the narrator interrupts their own thought, changes direction, or adds an important detail.
- Use full stops VERY rarely; prefer continuous spoken rhythm.
- Do not create lots of short standalone sentences.
- Naturally use spoken connectors where they fit, such as 'and then', 'so I'm like', 'but here's the thing', 'that's when', 'he goes', 'and at this point', and 'which obviously'.
- Dialogue must remain inside the same paragraph.
- Occasional CAPITAL words are allowed for strong spoken emphasis, but do not overuse them.
- Do not mechanically place ... everywhere; punctuation must follow the emotion and rhythm.
- Keep the first-person voice casual, believable and immediate.

STORY STRUCTURE:
- Open immediately with a strong curiosity hook.
- Establish the problem quickly.
- Escalate it with specific details.
- Plant at least one clue or detail that matters later.
- End with a satisfying reveal, payoff, or strong natural cliffhanger.
- Create completely original characters, setting, events and wording.
- No title, markdown, labels, hashtags, engagement bait, or commentary.

STYLE RHYTHM EXAMPLE — use only the punctuation/rhythm, NOT its plot or wording:
'I knew something was wrong when my roommate texted me asking why I was in his bedroom... which obviously made no sense because I was downstairs, literally sitting on the couch eating dinner, so at first I thought he was messing with me... and then he sent me a picture — and that's when I stopped eating'

Return ONLY the finished one-paragraph narration.
""".strip()


def generate_preview_story(word_target=72, niche=None):
    if niche is None:
        niche = story.select_story_niche()

    prompt = build_preview_prompt(niche, word_target)
    print(f"🎯 30s preview niche: {niche} | target words: {word_target}")

    gemini_key = os.environ.get("GEMINI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    failures = []

    if gemini_key:
        try:
            text = story.generate_with_gemini(gemini_key, prompt)
            print("✅ Preview story generated with Gemini.")
            return " ".join(text.strip().splitlines())
        except Exception as exc:
            failures.append(f"Gemini: {exc}")
            print(f"⚠️ Gemini preview generation failed: {exc}")

    if groq_key:
        models = []
        for model in (story.GROQ_MODEL, story.GROQ_FALLBACK_MODEL):
            if model and model not in models:
                models.append(model)
        for model in models:
            try:
                text = story.generate_with_groq_model(groq_key, prompt, model)
                print(f"✅ Preview story generated with Groq ({model}).")
                return " ".join(text.strip().splitlines())
            except Exception as exc:
                failures.append(f"Groq {model}: {exc}")
                print(f"⚠️ Groq preview generation failed ({model}): {exc}")

    details = "\n".join(f"  - {item}" for item in failures) or "  - No story API key was available"
    raise RuntimeError(f"All preview story providers failed:\n{details}")


def main():
    # Monkeypatch only this preview process; production code remains unchanged.
    audio.generate_story = generate_preview_story
    audio.TARGET_DURATION = 30.0
    audio.MIN_DURATION = 24.0
    audio.MAX_SINGLE_DURATION = 38.0
    audio.MAX_STORY_RETRIES = 2
    audio.main()


if __name__ == "__main__":
    main()
