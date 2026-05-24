---
title: Local Fonts and Better Word Counts
translationKey: local-fonts-and-word-count
slug: "local-fonts-and-word-count"
author: Qiran
type: post
date: 2026-05-24
lastmod: 2026-05-24
ai_assisted: true
tags:
  - Building site
  - Technology
---

I made two small but important improvements to this site today: I moved the Chinese web font to local files, and I rewrote the word-counting logic.

The Chinese pages had been using **KingHwa OldSong** through an external CDN. In theory this was convenient, but in practice it was fragile. If the CDN was blocked, slow, changed domains, or returned an error, the browser would fall back to a system font. That made the site look different from what I intended.

Now the site hosts the sliced `.woff2` font files locally. This does not mean every visitor has to download the whole font at once. The font is split into many small files, and the browser only loads the pieces needed for the characters on the current page. It costs more repository space, but it makes the site more stable and predictable. I also enabled the same font for Japanese pages, since the typeface includes Japanese glyphs and works well for CJK text.

I also optimized the word-counting method. Hugo's built-in `.WordCount` is useful for English, but it is not precise enough for Chinese. The new logic counts CJK characters as individual characters, counts Latin words and numbers as word tokens, and combines both for mixed-language posts. This unified method is now used by post metadata, archive totals, the heatmap, and structured data.

These changes are not very visible as features, but they make the site feel more like a carefully maintained personal space. Typography and counting rules are small details, yet they affect the experience of reading and reviewing my own writing over time.
