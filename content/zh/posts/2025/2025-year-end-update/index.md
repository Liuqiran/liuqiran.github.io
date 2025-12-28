---
title: 更新 Hugo
translationKey: 2025-year-end-update
slug: 2025-year-end-update
draft: false
author: Qiran
type: post
date: 2025-12-25
lastmod: 2025-12-27
cover:
  image: /img/2025-year-end-update/cover.jpg
tags:
- 生活
- 建站
noindex: true
params:
  mt: true
  mt_source: google
kq_managed: true
kq_mt: true
robotsNoIndex: true
kq_mt_from: en
kq_mt_to: zh
---
经过几天的熬夜，我终于完成了评论系统的迁移，为网站添加了自定义按钮，并实现了其他一些功能。

新的评论系统 **Waline** 支持表情符号，界面简洁优雅。我还在每个页面的底部添加了浮动按钮——目录按钮和评论按钮——方便访客快速跳转到他们想要的部分。

如果不同语言网站上的文章内容相似，评论区将会合并。

此外，我还更新了归档页面上的字数统计功能。现在，它会同时统计网站的文章总数和总字数。

我还找到了在手机上撰写和更新文章的更佳方式。我最初想使用 GitJournal，但它会修改 front matter，导致我的网站构建失败。后来，我安装了 Termux 并拉取了整个代码库。编辑文件时，我使用 **Markor**，一款轻量级的离线 Markdown 编辑器。它简单易用、稳定可靠，而且对于未来的移动写作来说更加方便。我仍然想实现一些功能——比如自动将文章发布到其他平台——但这出乎意料地困难。我尝试了很多方法，但都不太理想。

最终，这个过程感觉就像是在装饰自己的小空间。我真的很享受这个过程。

