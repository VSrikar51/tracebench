# 0001. Baseline: the model invents capabilities without tools or a real prompt

- **Date:** 2026-10-11
- **Model:** `qwen3.5:4b` via Ollama, thinking off, temperature 0, context 8192
- **Stage:** first call from Python, before tools or a detailed system prompt

## Setup

System prompt:

> You are a friendly support agent for an online pet store.

User message:

> Hi! What kinds of things can you help me with?

## Model reply

> Hello there! 🐾 Welcome to our virtual pet shop! I'm so excited to meet you.
>
> I'd love to help you find the perfect furry, feathered, or scaled friend for
> your home. Here are a few ways I can assist:
>
> *   **Finding Your New Best Friend:** Do you have a specific breed in mind, or
>     are you looking for advice on what might suit your lifestyle best? I can
>     share info on breeds like Golden Retrievers, French Bulldogs, or even
>     exotic pets like parrots and hamsters! 🐕🦜
> *   **Pet Care Tips:** Need help with training, nutrition, grooming, or
>     understanding pet behavior? I've got plenty of tips to keep your pup happy
>     and healthy.
> *   **Product Recommendations:** Looking for the perfect leash, a cozy bed, or
>     some tasty treats? Tell me what you're up for, and I'll suggest some great
>     options! 🎾🛏️
> *   **Adoption Stories:** If you're thinking about adopting, I can share
>     heartwarming stories from our shelter partners to help you decide.
>
> What are you in the mood for today? Are you looking to bring a new friend
> home, or do you just need some advice on your current pet? 🐱

Tokens: 41 in, 263 out. Finish reason: `stop`.

## What went wrong

- **Invented capabilities:** the store doesn't sell pets, has no shelter
  partners, and doesn't offer breed advice or adoption stories.
- **No grounding:** it offered product recommendations without any way to
  see the store's actual products.
- **Missed its real job:** it never mentioned orders, returns, refunds, or
  stock, which are what the agent is actually for.

## Why it happened

With only a one-line briefing and no tools, the model filled the gaps with
what a "pet store assistant" usually sounds like.

## What this motivates

- **Tools** that give the agent real store data (Step 3.3)
- **A detailed system prompt** that defines what it can and can't do (Step 3.4)
- **Evals** with a `hallucination` failure category to catch invented facts
  (Step 4)

This reply is the "before" example for the README.