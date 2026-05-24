---
title: 本地字体和更准确的字数统计
translationKey: local-fonts-and-word-count
slug: "local-fonts-and-word-count"
author: Qiran
type: post
date: 2026-05-24
lastmod: 2026-05-24
ai_assisted: true
cover:
  image: "https://upload.wikimedia.org/wikipedia/commons/thumb/f/ff/Mountain_and_lake_landscape_at_Glacier_National_Park.jpg/1280px-Mountain_and_lake_landscape_at_Glacier_National_Park.jpg"
  alt: "Glacier National Park mountain and lake landscape"
  caption: "Image: [PotatoCow25 / Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Mountain_and_lake_landscape_at_Glacier_National_Park.jpg), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)"
tags:
  - 建站
  - 技术
---

今天对这个网站做了两个小更新：把中文字体放到了本地，并且重新优化了字数统计方式。

之前中文页面使用的是通过外部 CDN 加载的 **京华老宋体**。这种方式配置起来很方便，但实际使用并不稳定。如果 CDN 被拦截、变慢、换了域名，或者直接返回错误，浏览器就会回退到系统默认字体。这样一来，页面最终显示出来的效果就和我原本设计的不一样。

现在网站改为本地托管切片后的 `.woff2` 字体文件。这并不是让访问者一次性下载完整字体，而是把字体拆成很多小文件。浏览器会根据当前页面用到的字符，自动加载需要的那几个分片。这样会让仓库体积变大一些，但页面显示更稳定，也不再依赖第三方字体服务。因为京华老宋体也包含日文字形，所以我也让日文页面以后可以使用这套字体。

另外，我也重新调整了字数统计方式。Hugo 内置的 `.WordCount` 对英文比较方便，但对中文和日文并不够准确。现在的新规则是：中文、日文、韩文字符按单字统计，英文和数字按词统计，如果文章是混排，就把两部分加在一起。这个统一的统计方式已经用在文章元信息、归档页总字数、博客热力图，以及结构化数据里。

这些更新看起来不像是很大的功能，但它们会影响我长期维护网站时的体验。字体决定了阅读的质感，字数统计则影响我回顾和整理写作记录的方式。对我来说，这些细节也是整理自己空间的一部分。
